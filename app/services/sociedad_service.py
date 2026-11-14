"""Capital, utilidad, anticipos y entregas en especie como hechos separados."""
import secrets,json
from ..extensions import db
from ..models import Producto,Movimiento
from ..models.finanzas import Jornada,OperacionFinanciera as Op
from ..models.gestion import (Socio,Sociedad,Participacion,PropiedadEquipo,CompraPool,ResultadoSocio,
    LiquidacionSocio,AplicacionLiquidacion,DisolucionSociedad,ComisionPool,CreditoVenta)
from .gestion_comun import actor,audit,bp,distribute,get_id

POOL_SALE_COMMISSION = 2000000  # COP 20.000, causada una sola vez en la venta.

def snapshot(society_id=None):
    if not society_id:
        jon=db.session.scalar(db.select(Socio).order_by(Socio.id).limit(1))
        if not jon:raise ValueError('Falta el socio principal JONATAN.')
        return [dict(socio_id=jon.id,nombre=jon.nombre,capital_bp=10000,utilidad_bp=10000)]
    society=get_id(Sociedad,society_id)
    if not society.activa:raise ValueError('La sociedad está inactiva.')
    rows=db.session.scalars(db.select(Participacion).where(Participacion.sociedad_id==society.id).order_by(Participacion.socio_id)).all()
    if not rows or sum(r.capital_bp for r in rows)!=10000 or sum(r.utilidad_bp for r in rows)!=10000:
        raise ValueError('Capital y utilidad deben sumar 100 % por separado.')
    return [dict(socio_id=r.socio_id,nombre=get_id(Socio,r.socio_id).nombre,capital_bp=r.capital_bp,utilidad_bp=r.utilidad_bp) for r in rows]

def save_society(f):
    from .finanzas_service import text,money
    name=text(f.get('name'));s=get_id(Sociedad,f.get('id')) if f.get('id') else Sociedad(nombre=name)
    s.nombre=name;new_active=f.get('active','1')=='1'
    ids=f.getlist('partner_id');capital=f.getlist('capital');profits=f.getlist('profit')
    if not ids or len(ids)!=len(set(ids)) or not len(ids)==len(capital)==len(profits):raise ValueError('Revisa los socios y las participaciones.')
    socios=[get_id(Socio,i) for i in ids]
    if any(not p.activo for p in socios):raise ValueError('Selecciona socios activos.')
    if f.get('capital_mode')=='Importes':
        amounts=[money(x) for x in capital];total=sum(amounts)
        if not total:raise ValueError('La inversión debe ser positiva.')
        weights=[v*10000//total for v in amounts]
        for i in range(10000-sum(weights)):weights[i%len(weights)]+=1
    else:weights=[bp(x) for x in capital];amounts=[0]*len(weights)
    gains=[bp(x) for x in profits]
    if sum(weights)!=10000 or sum(gains)!=10000:raise ValueError('Capital y utilidad deben sumar 100 % por separado.')
    previous=[dict(socio_id=p.socio_id,capital_bp=p.capital_bp,utilidad_bp=p.utilidad_bp)
              for p in db.session.scalars(db.select(Participacion).where(Participacion.sociedad_id==s.id))] if s.id else []
    s.activa=new_active
    db.session.add(s);db.session.flush()
    db.session.execute(db.delete(Participacion).where(Participacion.sociedad_id==s.id))
    for p,cap,gain,amt in zip(socios,weights,gains,amounts):
        db.session.add(Participacion(sociedad_id=s.id,socio_id=p.id,capital_bp=cap,utilidad_bp=gain,aportado=amt))
    db.session.flush();audit('sociedad',s.id,'Actualizar reglas para nuevas compras',{'antes':previous,'despues':snapshot(s.id) if s.activa else []})
    return s

def assign_ownership(p,society_id=None,capital=None):
    if p.status not in ('Disponible','Anulado lote'):raise ValueError('La propiedad se define antes de vender o entregar el equipo.')
    if db.session.scalar(db.select(ResultadoSocio.id).where(ResultadoSocio.producto_id==p.id)):
        raise ValueError('Hay resultados de este equipo. No se pueden cambiar sus participaciones históricas.')
    row=db.session.get(PropiedadEquipo,p.id)
    before=dict(sociedad_id=row.sociedad_id,participaciones=row.participaciones,capital=row.capital) if row else {}
    parts=snapshot(society_id)
    buy=db.session.get(CompraPool,p.id)
    basis=capital if capital is not None else p.cost_cents+(buy.ganancia if buy else 0)
    if row is None:row=PropiedadEquipo(producto_id=p.id)
    row.sociedad_id=int(society_id) if society_id else None;row.participaciones=parts;row.capital=basis
    db.session.add(row)
    audit('equipo',p.id,'Definir propiedad',{'antes':before,'capital':row.capital,'participaciones':row.participaciones})
    return row

def capital_basis(p):
    if p.source_type!='Retoma':return p.cost_cents
    buy=db.session.get(CompraPool,p.id)
    return p.cost_cents+(buy.ganancia if buy else 0)

def on_sale(day,op):
    if op.kind!='Venta' or not op.product_id:return
    p=get_id(Producto,op.product_id)
    ownership=db.session.get(PropiedadEquipo,p.id)
    if not ownership:
        ownership=PropiedadEquipo(producto_id=p.id,capital=capital_basis(p),participaciones=snapshot())
        db.session.add(ownership);db.session.flush()
    if db.session.scalar(db.select(ResultadoSocio.id).where(ResultadoSocio.operacion_id==op.id)):return
    if p.source_type=='Retoma':
        attending=[x['name'] for x in day.config.get('staff',[]) if x.get('attended',True)]
        if not attending:raise ValueError('Confirma el personal del día antes de vender un equipo del POOL.')
        total=POOL_SALE_COMMISSION;each,rem=divmod(total,len(attending))
        split=[dict(nombre=n,importe=each+(1 if i<rem else 0)) for i,n in enumerate(attending)]
        db.session.add(ComisionPool(operacion_id=op.id,monto=total,reparto=split))
        costs=list(op.costs)+[dict(type='Comisión POOL',name='COMISIÓN EXTRA POOL',quantity=1,unit=total,amount=total)]
        op.costs=costs
        assigned=p.pool_assigned_cost_cents or p.cost_cents
        gain=assigned-ownership.capital
        p.pool_admin_gain_cents=gain
    else:
        gain=op.amount-sum(c['amount'] for c in op.costs)-op.minor_cost
    capital_parts=distribute(ownership.capital,[x['capital_bp'] for x in ownership.participaciones])
    gain_parts=distribute(gain,[x['utilidad_bp'] for x in ownership.participaciones])
    for part,cap,g in zip(ownership.participaciones,capital_parts,gain_parts):
        db.session.add(ResultadoSocio(producto_id=p.id,operacion_id=op.id,sociedad_id=ownership.sociedad_id,
            socio_id=part['socio_id'],capital=cap,utilidad=g,condiciones=part))
    audit('equipo',p.id,'Distribuir capital y utilidad',{'capital':ownership.capital,'utilidad':gain,'operacion':op.id})

def settleable(result):
    op=get_id(Op,result.operacion_id)
    if op.voided:return False
    if op.product_id:
        p=get_id(Producto,op.product_id)
        return p.paid_cents>=p.sale_value_cents
    return not db.session.scalar(db.select(CreditoVenta.id).where(CreditoVenta.operacion_id==op.id,CreditoVenta.recibido<CreditoVenta.neto))

def balances(socio_id=None,start=None,end=None):
    q=db.select(ResultadoSocio).join(Op,Op.id==ResultadoSocio.operacion_id).join(Jornada,Jornada.id==Op.day_id).where(Op.voided==False)
    if socio_id:q=q.where(ResultadoSocio.socio_id==socio_id)
    if start:q=q.where(Jornada.date>=start)
    if end:q=q.where(Jornada.date<=end)
    result=[]
    for r in db.session.scalars(q):
        paid=db.session.execute(db.select(db.func.coalesce(db.func.sum(AplicacionLiquidacion.utilidad),0),db.func.coalesce(db.func.sum(AplicacionLiquidacion.capital),0)).where(AplicacionLiquidacion.resultado_id==r.id)).one()
        result.append(dict(row=r,product=get_id(Producto,r.producto_id),partner=get_id(Socio,r.socio_id),
            gain=r.utilidad-paid[0],capital=r.capital-paid[1],paid=paid[0],ready=settleable(r),date=get_id(Jornada,get_id(Op,r.operacion_id).day_id).date))
    return result

def cash_event(date,amount,description,source,entry=False):
    from .finanzas_service import find_day
    if source!='Caja' or not amount:return
    d=find_day(date)
    if not d or d.status!='Abierta':raise ValueError('Para usar caja, abre la jornada de la fecha del pago.')
    o=Op(day_id=d.id,token=secrets.token_hex(16),kind='Entrada caja' if entry else 'Salida caja',
        description=description,seller=actor(),amount=amount,minor_cost=0,costs=[],payments=[dict(account='EFECTIVO',amount=amount)])
    db.session.add(o);d.revision+=1

def liquidate(f):
    from .finanzas_service import valid_date,money,text
    partner=get_id(Socio,f.get('partner_id'));start=valid_date(f.get('start'));end=valid_date(f.get('end'));date=valid_date(f.get('date'))
    if start>end or end>date:raise ValueError('Revisa el intervalo y la fecha de pago.')
    rows=[x for x in balances(partner.id,start,end) if x['gain'] or (f.get('include_capital')=='1' and x['capital'])]
    if not rows:raise ValueError('No hay saldo pendiente en el período seleccionado.')
    gain=sum(x['gain'] for x in rows);cap=sum(x['capital'] for x in rows) if f.get('include_capital')=='1' else 0
    total=gain+cap
    if total<=0:raise ValueError('La liquidación neta no es positiva. Las pérdidas se conservan para compensarlas con utilidades posteriores.')
    if money(f.get('amount'))!=total:raise ValueError(f'El pago confirmado debe coincidir con el neto pendiente: {total/100:,.2f} COP.')
    advance=any(not x['ready'] for x in rows)
    if advance and f.get('advance')!='1':raise ValueError('Hay ventas sin recaudar. Confirma expresamente el anticipo y su fuente.')
    if f.get('confirmed')!='1':raise ValueError('Solo se liquida después de confirmar la entrega real del dinero.')
    token=f.get('token','')
    if len(token)!=32 or db.session.scalar(db.select(LiquidacionSocio.id).where(LiquidacionSocio.token==token)):raise ValueError('Pago duplicado o formulario vencido.')
    source=text(f.get('source'));source='Caja' if source=='CAJA' else source
    if source not in ('Caja','ADMINISTRACIÓN','TRANSFERENCIA'):raise ValueError('Selecciona la fuente del pago.')
    ref=text(f.get('reference'),True,150)
    l=LiquidacionSocio(socio_id=partner.id,desde=start,hasta=end,fecha=date,monto=total,capital=cap,
        anticipo=advance,fuente=source,referencia=ref,detalle={'utilidad':gain,'responsable':actor()},token=token)
    db.session.add(l);db.session.flush()
    for x in rows:db.session.add(AplicacionLiquidacion(liquidacion_id=l.id,resultado_id=x['row'].id,utilidad=x['gain'],capital=x['capital'] if cap else 0))
    cash_event(date,total,'LIQUIDACIÓN SOCIO '+partner.nombre,source)
    audit('liquidacion',l.id,'Confirmar pago',{'capital':cap,'utilidad':gain,'anticipo':advance},ref)
    return l

def dissolve(f):
    from .finanzas_service import valid_date,money,text
    p=get_id(Producto,f.get('product_id'));own=get_id(PropiedadEquipo,p.id)
    if p.status!='Disponible' or p.archived or not own.sociedad_id:raise ValueError('Selecciona un equipo disponible de una sociedad.')
    partner=get_id(Socio,f.get('partner_id'))
    part=next((x for x in own.participaciones if x['socio_id']==partner.id),None)
    if not part:raise ValueError('El socio no participa en este equipo.')
    mode=f.get('mode');valuation=p.cost_cents if f.get('valuation')=='Costo' else money(f.get('value'))
    if valuation<=0:raise ValueError('La valoración debe ser positiva.')
    value=distribute(valuation,[x['capital_bp'] for x in own.participaciones])
    share=value[own.participaciones.index(part)];date=valid_date(f.get('date'))
    from .operacion_service import created_day
    if date<created_day(p):raise ValueError('La entrega no puede ser anterior al ingreso del equipo.')
    reference=text(f.get('reference'),True,150);source=f.get('source')
    if source not in ('Caja','ADMINISTRACIÓN','TRANSFERENCIA'):raise ValueError('Selecciona la fuente de dinero.')
    if f.get('confirmed')!='1':raise ValueError('Confirma la entrega y el acuerdo de los socios.')
    token=f.get('token','')
    if len(token)!=32 or db.session.scalar(db.select(DisolucionSociedad.id).where(DisolucionSociedad.token==token)):raise ValueError('Acuerdo ya registrado.')
    before=dict(capital=own.capital,participaciones=own.participaciones,estado=p.status)
    if mode=='Dinero':
        buyer=get_id(Socio,f.get('buyer_id'))
        if not buyer.activo or buyer.id==partner.id:raise ValueError('Selecciona otro socio que compra la participación.')
        amount=money(f.get('amount'))
        if amount!=share:raise ValueError(f'La participación a pagar es {share/100:,.2f} COP con esta valoración.')
        parts=[dict(x) for x in own.participaciones]
        dest=next((x for x in parts if x['socio_id']==buyer.id),None)
        if not dest:dest=dict(socio_id=buyer.id,nombre=buyer.nombre,capital_bp=0,utilidad_bp=0);parts.append(dest)
        dest['capital_bp']+=part['capital_bp'];dest['utilidad_bp']+=part['utilidad_bp']
        own.participaciones=[x for x in parts if x['socio_id']!=partner.id]
        # El acuerdo conserva el costo contable; su valoración queda en la liquidación de salida.
        cash_event(date,amount,'DEVOLUCIÓN CAPITAL '+partner.nombre,source)
    elif mode=='Equipo':
        compensation=valuation-share
        amount=money(f.get('amount') or '0')
        if amount!=compensation:raise ValueError(f'Quien recibe todo el equipo debe compensar {compensation/100:,.2f} COP a los demás socios.')
        p.status='Entregado a socio';p.archived=1
        cash_event(date,amount,'COMPENSACIÓN POR EQUIPO '+p.imei,source,entry=True)
    else:raise ValueError('Selecciona dinero o entrega del equipo.')
    row=DisolucionSociedad(sociedad_id=own.sociedad_id,socio_id=partner.id,producto_id=p.id,fecha=date,
        modalidad=mode,valor_equipo=valuation,dinero=amount,detalle={'antes':before,'despues':own.participaciones,
        'criterio':f.get('valuation'),'referencia':reference,'fuente':source,'valor_participacion':share},token=token)
    db.session.add(row);db.session.flush()
    db.session.add(Movimiento(product_id=p.id,action='Acuerdo de sociedad',reason=reference,actor=actor(),
        before_data=json.dumps({'status':before['estado']}),after_data=json.dumps(p.to_dict())))
    audit('disolucion',row.id,'Confirmar '+mode,row.detalle,reference)
    return row

def register_purchase(p,f,*,buyer=None,token=None):
    from .finanzas_service import find_day,money,valid_date,text
    if p.source_type!='Retoma' or p.status!='Disponible':raise ValueError('Selecciona una retoma disponible.')
    if db.session.get(CompraPool,p.id):raise ValueError('La compra del POOL ya está registrada en Finanzas.')
    if token is not None and (len(token)!=32 or db.session.scalar(db.select(Op.id).where(Op.token==token))):
        raise ValueError('Esta compra ya fue registrada o el formulario venció.')
    date=valid_date(f.get('date'));d=find_day(date)
    if not d or d.status!='Abierta':raise ValueError('Abre la jornada financiera de esta compra.')
    amount=money(f.get('funding'));extra=sum(x['amount_cents'] for x in p.additional_costs or [])
    base=p.purchase_cop_cents or p.cost_cents
    if amount<p.cost_cents:raise ValueError('El aporte debe cubrir compra y costos adicionales. Si faltan costos por pagar, regístralos antes de confirmar esta operación.')
    mode=f.get('purchase_mode','Compra directa')
    origin=None
    if mode=='Parte de pago':
        origin=get_id(Op,f.get('origin_sale_id'))
        if origin.kind!='Venta' or origin.voided:raise ValueError('Selecciona la venta que recibe esta parte de pago.')
        # La entrega de un equipo no es efectivo; debe existir un medio explícito de retoma.
        if not any(x.get('account')=='RETOMA' and x.get('equipment_id')==p.id and x['amount']==base for x in origin.payments):
            raise ValueError('Registra primero la venta con medio Retoma y el valor recibido de este equipo; evita inventar una entrada de efectivo.')
    elif mode!='Compra directa':raise ValueError('Tipo de compra inválido.')
    if f.get('confirmed')!='1':raise ValueError('Confirma el aporte recibido y los pagos efectuados.')
    gain=amount-p.cost_cents
    op=Op(day_id=d.id,token=token or secrets.token_hex(16),kind='Compra POOL',description='COMPRA POOL '+p.imei,seller=buyer or actor(),
        amount=gain,minor_cost=0,costs=[],payments=[],product_id=None)
    db.session.add(op);db.session.flush()
    row=CompraPool(producto_id=p.id,tipo=mode,venta_origen_id=origin.id if origin else None,operacion_id=op.id,
        aporte=amount,pago_cliente=base,costos_pagados=extra,ganancia=gain)
    db.session.add(row);db.session.flush()
    assign_ownership(p,f.get('society_id') or None,capital=amount)
    d.revision+=1;audit('equipo',p.id,'Compra POOL y ganancia del día',{'aporte':amount,'cliente':base,'costos':extra,'ganancia':gain,'modo':mode})
    return row

def pay_pool_commission(f):
    from .finanzas_service import find_day,valid_date,text
    c=get_id(ComisionPool,f.get('commission_id'));origin=get_id(Op,c.operacion_id)
    if c.pago_operacion_id or origin.voided:raise ValueError('Comisión pagada o venta anulada.')
    d=find_day(valid_date(f.get('date')))
    if not d or d.status!='Abierta':raise ValueError('Abre la jornada en que se entregó el dinero.')
    if d.date < get_id(Jornada,origin.day_id).date:
        raise ValueError('La entrega de la comisión no puede ser anterior a su venta.')
    if f.get('confirmed')!='1':raise ValueError('Confirma la entrega de la comisión extra.')
    source=f.get('payment_source') or 'EFECTIVO'
    if source not in ('EFECTIVO','ADMINISTRACIÓN DIRECTA'):raise ValueError('Selecciona de dónde salió el dinero de la comisión.')
    reference=text(f.get('reference'),source=='ADMINISTRACIÓN DIRECTA',300)
    op=Op(day_id=d.id,token=secrets.token_hex(16),kind='Salida caja',description='PAGO COMISIÓN EXTRA POOL #'+str(origin.id),
        seller=actor(),amount=c.monto,minor_cost=0,costs=[],payments=[dict(account=source,amount=c.monto,reference=reference)])
    db.session.add(op);db.session.flush();c.pago_operacion_id=op.id;d.revision+=1
    audit('comision_pool',c.id,'Confirmar entrega',{'reparto':c.reparto,'venta':origin.id,
        'fecha_origen':get_id(Jornada,origin.day_id).date,'fecha_entrega':d.date,
        'fuente':source,'referencia':reference,'pago':op.id})

def refresh_result(op,reason):
    rows=db.session.scalars(db.select(ResultadoSocio).where(ResultadoSocio.operacion_id==op.id)).all()
    if not rows:return
    ids=[r.id for r in rows]
    if db.session.scalar(db.select(AplicacionLiquidacion.id).where(AplicacionLiquidacion.resultado_id.in_(ids))):
        raise ValueError('Hay pagos liquidados a socios. Concilia la devolución antes de alterar esta utilidad.')
    p=get_id(Producto,op.product_id);own=get_id(PropiedadEquipo,p.id)
    gain=(p.pool_assigned_cost_cents or p.cost_cents)-own.capital if p.source_type=='Retoma' else op.amount-sum(c['amount'] for c in op.costs)-op.minor_cost
    values=distribute(gain,[r.condiciones['utilidad_bp'] for r in rows])
    previous=[{'socio':r.socio_id,'utilidad':r.utilidad} for r in rows]
    for r,v in zip(rows,values):r.utilidad=v
    audit('operacion',op.id,'Recalcular utilidades no liquidadas',{'antes':previous,'utilidad':gain},reason)


def reverse_pool_commission(d,f):
    from .finanzas_service import text, audit as day_audit
    c=get_id(ComisionPool,f.get('commission_id'))
    if not c.pago_operacion_id:raise ValueError('La comisión no tiene una entrega activa.')
    payment=get_id(Op,c.pago_operacion_id)
    if payment.day_id!=d.id or d.status!='Abierta' or payment.voided:raise ValueError('Reabre la jornada de la entrega para corregirla.')
    # Revertir la entrega no cambia el gasto causado ni el cierre de la venta.
    if f.get('returned')!='1':raise ValueError('Confirma el reintegro real del dinero antes de anular la entrega.')
    reason=text(f.get('reason'),True,500)
    payment.voided=True;c.pago_operacion_id=None
    day_audit(d,'Anular entrega de comisión POOL',reason,{'commission':c.id,'payment':payment.id,'amount':payment.amount,'returned':True,'source':payment.payments[0]['account']})
    audit('comision_pool',c.id,'Reintegro de entrega',{'payment':payment.id,'amount':payment.amount},reason)
