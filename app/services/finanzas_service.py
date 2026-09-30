"""Cálculos puros y escrituras transaccionales del cierre diario."""
from datetime import date
from decimal import Decimal, InvalidOperation
from collections import defaultdict
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.exc import IntegrityError
from ..extensions import db
from ..models import Producto, Cobro, Recepcion
from ..models.finanzas import Jornada, OperacionFinanciera as Op, PagoProveedor as Pago, AuditoriaFinanciera as Audit
from .operacion_service import today

FUNDS = ('CP VARIOS', 'CP HIDROGEL', 'CP BATERÍAS', 'CP MEMORIAS')
KINDS = ('Venta', 'Servicio', 'PD', 'Entrada caja', 'Salida caja')
DEFAULT_ACCOUNTS = ['EFECTIVO', 'TRANSFERENCIA POR IDENTIFICAR', 'TARJETA POR IDENTIFICAR']

def money(value):
    try:
        n = Decimal(str(value).strip().replace(',', '.'))
        if not n.is_finite() or n < 0 or n > 100000000000 or n != n.quantize(Decimal('.01')):
            raise ValueError()
        return int(n*100)
    except (InvalidOperation, ValueError):
        raise ValueError('Usa un importe positivo o cero, sin separadores de miles y con máximo dos decimales.')

def text(value, required=True, limit=120):
    v = ' '.join(str(value or '').strip().split())
    if (required and not v) or len(v)>limit:
        raise ValueError(f'Completa el texto (máximo {limit} caracteres).')
    return v.upper()

def valid_date(value):
    try: d=date.fromisoformat(value)
    except (ValueError,TypeError): raise ValueError('Fecha inválida.')
    if d.isoformat()>today(): raise ValueError('No se puede registrar una jornada futura.')
    return d.isoformat()

def defaults(day):
    return dict(holiday=False,opening=0,normal_base=29100000,sandra_extra=3000000,
                extra_a=3000000,extra_b=9000000,normal_return=38100000,
                sandra=False,sandra_sunday=5000000,sandra_control_sunday=4000000,
                sandra_control_work=6000000,sandra_control_absent=3000000,
                threshold_normal=35000000,threshold_sunday=20000000,
                threshold_person=1000000,step_base=10000000,step_person=500000,
                sandra_step=False,require_principal=True,commission_first=1000000,
                commission_step=500000,commission_levels=24,staff=[],
                accounts=DEFAULT_ACCOUNTS,holidays=[],reviewed=False,actor='',note='')

def find_day(day):
    valid_date(day)
    return db.session.scalar(db.select(Jornada).where(Jornada.date==day))

def audit(d,action,reason,detail):
    db.session.add(Audit(day_id=d.id,action=action,reason=reason or 'Registro de jornada',detail=detail))

def commit(d):
    d.revision += 1
    try: db.session.commit()
    except (StaleDataError,IntegrityError):
        db.session.rollback()
        raise ValueError('La jornada cambió o este registro ya existe. Recarga antes de continuar.')

def editable(d,revision):
    if not d or d.status!='Abierta': raise ValueError('Abre una jornada para registrar movimientos.')
    if str(d.revision)!=str(revision): raise ValueError('La jornada cambió en otra ventana. Recarga antes de continuar.')

def open_day(day):
    if find_day(day): return find_day(day)
    previous=db.session.scalar(db.select(Jornada).where(Jornada.date<day).order_by(Jornada.date.desc()))
    cfg=defaults(day)
    if previous:
        cfg={**previous.config,'staff':[], 'opening':0,'sandra':False,'holiday':False,'reviewed':False,'actor':'','note':''}
    cfg['holiday']=day in cfg.get('holidays',[])
    d=Jornada(date=day,config=cfg)
    db.session.add(d)
    try: db.session.commit()
    except IntegrityError: db.session.rollback();return find_day(day)
    return d

def save_config(d,form):
    cfg=dict(d.config)
    for k in ('opening','normal_base','sandra_extra','extra_a','extra_b','normal_return',
              'sandra_sunday','sandra_control_sunday','sandra_control_work','sandra_control_absent'):
        cfg[k]=money(form.get(k,''))
    for k in ('holiday','sandra','sandra_step','require_principal','reviewed'):
        cfg[k]=form.get(k)=='1'
    cfg['actor']=text(form.get('actor'))
    cfg['note']=text(form.get('note'),False,500)
    accounts=[text(a) for a in form.get('accounts','').splitlines() if a.strip()]
    cfg['accounts']=list(dict.fromkeys(['EFECTIVO']+accounts))
    if len(cfg['accounts'])>50: raise ValueError('Máximo 50 cuentas.')
    names=form.getlist('staff_name'); roles=form.getlist('staff_role'); salaries=form.getlist('staff_salary')
    if not len(names)==len(roles)==len(salaries): raise ValueError('Lista de personal incompleta.')
    staff=[]
    for n,r,s in zip(names,roles,salaries):
        if not n.strip() and not s.strip(): continue
        if r not in ('Principal','Secundaria'): raise ValueError('Función inválida.')
        staff.append(dict(name=text(n),role=r,salary=money(s)))
    if len(staff)>30 or len({p['name'] for p in staff})!=len(staff): raise ValueError('Revisa nombres repetidos o el número de personas.')
    holiday_dates=[]
    for value in form.get('holidays','').splitlines():
        if value.strip():
            try: holiday_dates.append(date.fromisoformat(value.strip()).isoformat())
            except ValueError: raise ValueError('Los festivos usan formato AAAA-MM-DD, uno por línea.')
    cfg['holidays']=sorted(set(holiday_dates))
    cfg['holiday']=cfg['holiday'] or d.date in cfg['holidays']
    cfg['staff']=staff
    audit(d,'Configuración',cfg['note'],{'before':d.config,'after':cfg})
    d.config=cfg

def calculate(cfg,day,debe,haber,service,pd,funds,transfer):
    special=cfg['holiday'] or date.fromisoformat(day).weekday()==6
    p=sum(x['role']=='Principal' for x in cfg['staff']);s=len(cfg['staff'])-p;a=int(cfg['sandra'])
    salaries=sum(x['salary'] for x in cfg['staff'])
    liquidation=salaries+(a*cfg['sandra_sunday'] if special else cfg['normal_base']+a*cfg['sandra_extra']+cfg['extra_a']+cfg['extra_b'])
    result=debe-haber-liquidation-service
    first=(cfg['threshold_sunday'] if special else cfg['threshold_normal'])+cfg['threshold_person']*(p+s+a)
    step=cfg['step_base']+cfg['step_person']*(p+s+(a if cfg['sandra_step'] else 0))
    unit=0;overflow=False
    if result>=first and (p>0 or not cfg['require_principal']):
        last=first+(cfg['commission_levels']-1)*step
        overflow=result>=last+cfg['step_base']
        unit=cfg['commission_first']+min((result-first)//step,cfg['commission_levels']-1)*cfg['commission_step']
    commission=None if overflow else unit*(p+s+a)
    profit=None if overflow else result-commission
    sandra_control=(cfg['sandra_control_sunday'] if a else 0) if special else (cfg['sandra_control_work'] if a else cfg['sandra_control_absent'])
    total=None if overflow else sum(funds.values())+sandra_control-pd+haber+profit+(0 if special else cfg['normal_return'])
    return dict(special=special,debe=debe,haber=haber,service=service,pd=pd,liquidation=liquidation,
                result=result,commission=commission,unit_commission=None if overflow else unit,
                profit=profit,owner_result=None if overflow else profit-pd,
                control_total=total,control_cash=None if overflow else total-transfer,
                first=first,step=step,overflow=overflow,funds=dict(funds),transfer=transfer)

def sources(day):
    collections=db.session.scalars(db.select(Cobro).where(Cobro.effective_date==day,Cobro.voided==False)).all()
    receipts=db.session.scalars(db.select(Recepcion).join(Cobro,Recepcion.collection_id==Cobro.id).where(
        Recepcion.effective_date==day,Recepcion.voided==False,Cobro.voided==False)).all()
    sales=db.session.scalars(db.select(Producto).where(Producto.sale_date==day,Producto.status.in_(['Vendido','Garantía']))).all()
    return collections,receipts,sales

def report(d):
    ops=db.session.scalars(db.select(Op).where(Op.day_id==d.id).order_by(Op.id.desc())).all()
    active=[o for o in ops if not o.voided]
    collections,receipts,sales=sources(d.date)
    banks=defaultdict(int);funds=defaultdict(int);debe=haber=service=pd=transfer=gross=0
    cash=d.config['opening'];warnings=[]
    for o in active:
        if o.kind=='Venta':
            margin=o.amount-sum(c['amount'] for c in o.costs)
            debe+=margin;haber+=o.minor_cost;gross+=o.amount
            for c in o.costs:
                if c['type']=='Fondo': funds[c['name']]+=c['amount']
            # Solo operaciones complementarias: MOD03 conserva sus propios cobros.
            for payment in o.payments:
                banks[payment['account']]+=payment['amount']
                if payment['account']=='EFECTIVO': cash+=payment['amount']
                else:
                    # Distribución proporcional explícita del control para pagos mixtos.
                    included=margin+sum(c['amount'] for c in o.costs if c['type']!='Equipo')
                    transfer+=int((Decimal(included)*payment['amount']/o.amount).quantize(Decimal('1'))) if o.amount else 0
        else:
            if o.kind=='Servicio': service+=o.amount
            if o.kind=='PD': pd+=o.amount
            for pay in o.payments:
                if pay['account']=='EFECTIVO': cash+=pay['amount']*(1 if o.kind=='Entrada caja' else -1)
    for c in collections:
        if c.legacy: warnings.append(f'Cobro {c.id}: saldo anterior pendiente de conciliación.');continue
        key='EFECTIVO' if c.method=='Efectivo' else c.method.upper()+' · MOD03 SIN CUENTA'
        banks[key]+=c.amount_cents
        if c.destination=='Negocio' and c.method=='Efectivo': cash+=c.amount_cents
    for r in receipts:
        c=db.session.get(Cobro,r.collection_id)
        if c.destination=='Vendedora' and r.method=='Efectivo': cash+=r.amount_cents
    supplier_payments=db.session.scalars(db.select(Pago).where(Pago.day_id==d.id)).all()
    cash-=sum(x.amount for x in supplier_payments if x.account=='EFECTIVO')
    integrated={o.product_id for o in active if o.product_id}
    pending_sales=[p for p in sales if p.id not in integrated]
    if pending_sales: warnings.append('Hay ventas de equipos sin incorporar al resultado. Revísalas antes del cierre.')
    if any(c.destination=='Vendedora' for c in collections): warnings.append('El efectivo cobrado por vendedoras entra a caja de administración solo al confirmar su recepción.')
    if any(c.method!='Efectivo' for c in collections): warnings.append('MOD03 aún no identifica la cuenta bancaria concreta: sus cobros aparecen agrupados por medio.')
    if any(o.product_id for o in active): warnings.append('El control Excel de transferencias no distribuye cobros de equipos entre días. Usa la conciliación de caja para dinero real.')
    for o in active:
        if o.product_id:
            p=db.session.get(Producto,o.product_id)
            if p.status not in ('Vendido','Garantía') or p.sale_value_cents!=o.amount:
                warnings.append(f'La venta del equipo {p.imei} cambió en MOD03. Anula y vuelve a revisar su registro financiero.')
    drinks=defaultdict(lambda:dict(quantity=0,cost=0,paid=0))
    for o in active:
        for idx,c in enumerate(o.costs):
            if c['type']=='Bebida':
                item=drinks[c['name']];item['quantity']+=c['quantity'];item['cost']+=c['amount']
                item['paid']+=sum(x.amount for x in db.session.scalars(db.select(Pago).where(Pago.operation_id==o.id,Pago.cost_index==idx)))
    totals=calculate(d.config,d.date,debe,haber,service,pd,funds,transfer)
    totals.update(gross=gross,cash_expected=cash,banks=dict(banks),customer_collections=sum(c.amount_cents for c in collections if not c.legacy),
                  admin_receipts=sum(r.amount_cents for r in receipts),sales_count=sum(o.kind=='Venta' for o in active),warnings=warnings)
    return dict(drinks=dict(drinks),supplier_payments=supplier_payments,totals=totals,operations=ops,pending_sales=pending_sales,collections=collections,receipts=receipts)

def parse_costs(f):
    costs=[]
    names=f.getlist('cost_name');types=f.getlist('cost_type');quantities=f.getlist('cost_qty');units=f.getlist('cost_unit')
    if not len(names)==len(types)==len(quantities)==len(units): raise ValueError('Detalle de costos incompleto.')
    if len(names)>8: raise ValueError('Máximo ocho líneas: cinco accesorios, equipo y consumos.')
    accessory=0
    for name,typ,q,u in zip(names,types,quantities,units):
        if not name.strip():
            if u.strip(): raise ValueError('Indica la procedencia de cada costo.')
            continue
        if typ not in ('Proveedor','Equipo','Fondo','Bebida'): raise ValueError('Tipo de costo inválido.')
        name=text(name)
        if typ=='Fondo' and name not in FUNDS: raise ValueError('Selecciona un fondo del catálogo.')
        qty=int(q)
        if not 1<=qty<=10000: raise ValueError('Cantidad fuera de rango.')
        if typ in ('Proveedor','Fondo'): accessory+=1
        costs.append(dict(name=name,type=typ,quantity=qty,unit=money(u),amount=qty*money(u)))
    if accessory>5: raise ValueError('Máximo cinco procedencias de accesorios.')
    return costs

def add_operation(d,f):
    kind=f.get('kind');token=f.get('token','')
    if kind not in KINDS or len(token)!=32: raise ValueError('Operación inválida. Recarga el formulario.')
    if db.session.scalar(db.select(Op.id).where(Op.token==token)): raise ValueError('Esta operación ya fue registrada.')
    description=text(f.get('description'),True,300);seller=text(f.get('seller'))
    amount=money(f.get('amount'));minor=money(f.get('minor_cost','0')) if kind=='Venta' else 0
    if amount<=0: raise ValueError('El importe debe ser mayor que cero.')
    costs=parse_costs(f) if kind=='Venta' else []
    if len(f.getlist('payment_account'))!=len(f.getlist('payment_amount')): raise ValueError('Detalle de medios incompleto.')
    payments=[]
    for account,value in zip(f.getlist('payment_account'),f.getlist('payment_amount')):
        if not value.strip(): continue
        if account not in d.config['accounts']: raise ValueError('Selecciona una cuenta configurada.')
        v=money(value)
        if v: payments.append(dict(account=account,amount=v))
    if len(payments)>3: raise ValueError('Máximo tres medios de pago.')
    paid=sum(x['amount'] for x in payments)
    if kind=='Venta' and paid!=amount: raise ValueError('Para ventas complementarias, la suma de los medios debe coincidir con la venta. Los abonos de equipos se registran en MOD03.')
    if kind!='Venta' and paid!=amount: raise ValueError('Indica la cuenta de salida/entrada por el importe completo.')
    o=Op(day_id=d.id,token=token,kind=kind,description=description,seller=seller,amount=amount,minor_cost=minor,costs=costs,payments=payments)
    db.session.add(o);audit(d,'Registro '+kind,description,{'amount':amount,'actor':seller})

def incorporate(d,pid,token):
    p=db.session.get(Producto,int(pid))
    if not p or p.sale_date!=d.date or p.status not in ('Vendido','Garantía') or not p.sale_value_cents:
        raise ValueError('La venta no está disponible para esta jornada.')
    if db.session.scalar(db.select(Op.id).where(Op.product_id==p.id)): raise ValueError('El equipo ya tiene un resultado registrado.')
    db.session.add(Op(day_id=d.id,token=token,kind='Venta',description=p.model+' · '+p.imei,seller=p.seller or 'SIN VENDEDORA',
        amount=p.sale_value_cents,minor_cost=0,product_id=p.id,
        costs=[dict(name='COSTO DE INVENTARIO',type='Equipo propio',quantity=1,unit=p.cost_cents,amount=p.cost_cents)],payments=[]))
    audit(d,'Incorporar venta','Costo y valor tomados del equipo',{'equipment_id':p.id})

def obligations():
    paid=defaultdict(int)
    for p in db.session.scalars(db.select(Pago)):paid[(p.operation_id,p.cost_index)]+=p.amount
    result=[]
    for o in db.session.scalars(db.select(Op).where(Op.voided==False)):
        for i,c in enumerate(o.costs):
            if c['type'] not in ('Proveedor','Equipo','Bebida'):continue
            balance=c['amount']-paid[(o.id,i)]
            if balance:result.append(dict(operation=o,index=i,cost=c,balance=balance))
    return result

def pay_supplier(d,f):
    oid=int(f.get('operation_id'));idx=int(f.get('cost_index'))
    item=next((x for x in obligations() if x['operation'].id==oid and x['index']==idx),None)
    if not item: raise ValueError('La obligación ya fue pagada o no existe.')
    origin=db.session.get(Jornada,item['operation'].day_id)
    if origin.date>d.date: raise ValueError('No puedes pagar antes de registrar la obligación.')
    amount=money(f.get('amount'));account=f.get('account')
    if not 0<amount<=item['balance'] or account not in d.config['accounts']: raise ValueError('Revisa importe y cuenta de pago.')
    if len(f.get('token',''))!=32: raise ValueError('Recarga el formulario de pago.')
    db.session.add(Pago(day_id=d.id,operation_id=oid,cost_index=idx,amount=amount,account=account,token=f['token']))
    audit(d,'Pago proveedor',text(f.get('reason'),True,500),{'operation':oid,'cost':idx,'amount':amount,'account':account})


def update_equipment_costs(d,f):
    o=db.session.get(Op,int(f.get('operation_id')))
    if not o or o.day_id!=d.id or not o.product_id or o.voided:
        raise ValueError('La operación de equipo no está disponible.')
    if db.session.scalar(db.select(Pago.id).where(Pago.operation_id==o.id)):
        raise ValueError('Corrige primero los pagos a proveedores antes de cambiar este detalle.')
    costs=parse_costs(f)
    if any(c['type']=='Equipo' for c in costs):
        raise ValueError('El costo del equipo ya viene del inventario. Agrega únicamente costos complementarios.')
    own=[c for c in o.costs if c['type']=='Equipo propio']
    before={'costs':o.costs,'minor_cost':o.minor_cost}
    o.costs=own+costs;o.minor_cost=money(f.get('minor_cost','0'))
    audit(d,'Costos de paquete',text(f.get('reason'),True,500),{'operation':o.id,'before':before,'after':{'costs':o.costs,'minor_cost':o.minor_cost}})
