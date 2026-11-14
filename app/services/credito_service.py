"""Créditos: utilidad en fecha de venta; consignación solamente al desembolsar."""
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from ..extensions import db
from ..models import Producto,Cobro,ConsignacionBancaria,HistorialConsignacion
from ..models.finanzas import OperacionFinanciera as Op,Jornada
from ..models.gestion import AliadoCredito,CreditoVenta,DesembolsoCredito,AplicacionCredito
from .gestion_comun import audit,bp,get_id,actor
from .consignaciones_finanzas import destino

def credit_payment(f,index,amount,person,bank):
    from .finanzas_service import money
    def at(key):
        values=f.getlist(key)
        return values[index] if index<len(values) else ''
    ally=get_id(AliadoCredito,at('payment_ally_id'))
    if not ally.activo:raise ValueError('El aliado no está activo.')
    if f.get('credit_approved')!='1':raise ValueError('Confirma que el crédito fue aprobado en la plataforma.')
    mode=at('payment_credit_mode') or 'Porcentaje'
    if mode=='Neto pactado':
        net=money(at('payment_credit_net'))
        if not 0<net<=amount:raise ValueError('El neto pactado debe ser positivo y no superar el crédito bruto.')
        rate=None
    elif mode=='Porcentaje':
        rate=bp(at('payment_credit_rate')) if at('payment_credit_rate').strip() else ally.porcentaje_bp
        net=int((Decimal(amount)*(10000-rate)/10000).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
        if net<=0:raise ValueError('El neto del crédito debe ser mayor que cero.')
    else:raise ValueError('Selecciona porcentaje o neto pactado.')
    person_id,bank_id=destino(person or ally.persona_id,bank or ally.banco_id)
    return dict(account='CRÉDITO',amount=amount,net=net,fee=amount-net,ally_id=ally.id,ally_name=ally.nombre,
        mode=mode,rate_bp=rate,person_id=person_id,bank_id=bank_id)

def attach(operation):
    for i,p in enumerate(operation.payments):
        if p['account']=='CRÉDITO':
            db.session.add(CreditoVenta(operacion_id=operation.id,indice=i,aliado_id=p['ally_id'],
                bruto=p['amount'],costo=p['fee'],neto=p['net'],condiciones=dict(p)))
    db.session.flush()

def operation_collected(op):
    from .finanzas_service import net_payment
    return sum(net_payment(p) for p in op.payments if p['account']!='CRÉDITO')+sum(
        c.recibido for c in db.session.scalars(db.select(CreditoVenta).where(CreditoVenta.operacion_id==op.id,CreditoVenta.estado!='Anulado')))

def settle(f):
    from .finanzas_service import money,valid_date,find_day
    ally=get_id(AliadoCredito,f.get('ally_id'));date=valid_date(f.get('date'))
    d=find_day(date)
    if d and d.status!='Abierta':raise ValueError('La fecha de recepción está cerrada. Reábrela con motivo para registrar el desembolso.')
    token=f.get('token','')
    if len(token)!=32 or db.session.scalar(db.select(DesembolsoCredito.id).where(DesembolsoCredito.token==token)):
        raise ValueError('Este desembolso ya fue registrado o el formulario venció.')
    person,bank=destino(f.get('person_id'),f.get('bank_id'))
    ids=f.getlist('credit_id');amounts=f.getlist('allocation')
    if len(ids)!=len(amounts) or len(ids)!=len(set(ids)):raise ValueError('Distribución inválida.')
    rows=[]
    for cid,raw in zip(ids,amounts):
        if not raw.strip():continue
        n=money(raw)
        if not n:continue
        c=get_id(CreditoVenta,cid);op=get_id(Op,c.operacion_id);origin=get_id(Jornada,op.day_id)
        if op.voided or c.estado=='Anulado' or c.aliado_id!=ally.id or n>c.neto-c.recibido:
            raise ValueError('Una aplicación excede el saldo o pertenece a otro aliado.')
        if origin.date>date:raise ValueError('El desembolso no puede ser anterior a la venta.')
        rows.append((c,op,n))
    total=money(f.get('amount'))
    if not total or sum(n for _,_,n in rows)!=total:raise ValueError('Las aplicaciones deben sumar exactamente el desembolso.')
    ref=f.get('reference','').strip()
    if not ref or len(ref)>100:raise ValueError('Ingresa una referencia bancaria de hasta 100 caracteres.')
    if db.session.scalar(db.select(DesembolsoCredito.id).where(DesembolsoCredito.aliado_id==ally.id,
        DesembolsoCredito.referencia==ref,DesembolsoCredito.fecha==date,DesembolsoCredito.activo==True)):
        raise ValueError('Ya existe un desembolso de este aliado con la misma fecha y referencia.')
    deposit=ConsignacionBancaria(persona_id=person,banco_id=bank,monto=Decimal(total)/100,
        fecha=datetime.fromisoformat(date),referencia='CRÉDITO '+ref,activa=True)
    db.session.add(deposit);db.session.flush()
    batch=DesembolsoCredito(aliado_id=ally.id,fecha=date,monto=total,persona_id=person,banco_id=bank,
        referencia=ref,consignacion_id=deposit.id,token=token)
    db.session.add(batch);db.session.flush()
    for c,op,n in rows:
        c.recibido+=n;c.estado='Pagado' if c.recibido==c.neto else 'Parcial'
        collection=None
        if op.product_id:
            p=get_id(Producto,op.product_id)
            collection=Cobro(product_id=p.id,amount_cents=n,destination='Negocio',collector=actor(),
                method='Transferencia',reference=f'CREDITO {batch.id}/{c.id}',effective_date=date,
                note='Desembolso del aliado. No genera una segunda venta ni utilidad.')
            db.session.add(collection);db.session.flush()
            p.paid_cents+=n;p.payment_status='Pagado' if p.paid_cents>=p.sale_value_cents else 'Abono'
            p.payment_date=date if p.payment_status=='Pagado' else p.payment_date
        db.session.add(AplicacionCredito(desembolso_id=batch.id,credito_id=c.id,monto=n,cobro_id=collection.id if collection else None))
    audit('desembolso',batch.id,'Confirmar recepción',{'importe':total,'aplicaciones':[{'credito':c.id,'importe':n} for c,_,n in rows]},ref)
    return batch

def cancel_unreceived(op,reason):
    rows=db.session.scalars(db.select(CreditoVenta).where(CreditoVenta.operacion_id==op.id)).all()
    if any(c.recibido for c in rows):raise ValueError('El crédito tiene desembolsos. Requiere devolución bancaria antes de anular.')
    for c in rows:c.estado='Anulado'
    if rows:audit('operacion',op.id,'Anular créditos pendientes',{},reason)
