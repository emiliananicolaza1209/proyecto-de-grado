from .gestion_comun import actor
"""Cálculos puros y escrituras transaccionales del cierre diario."""
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from collections import defaultdict
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.exc import IntegrityError
from ..extensions import db
from ..models import Producto, Cobro, Recepcion, Catalogo, PersonaContable
from ..models.finanzas import Jornada, OperacionFinanciera as Op, PagoProveedor as Pago, AuditoriaFinanciera as Audit
from .operacion_service import today
from .consignaciones_finanzas import BANCARIOS, destino, sincronizar_operacion, sincronizar_pago

FUNDS = ('CP VARIOS', 'CP HIDROGELES', 'BATERÍAS', 'MEMORIAS')
INTERNAL_PROVIDERS = set(FUNDS) | {'CP HIDROGEL','CP HIDRÓGEL', 'CP BATERIAS', 'CP MEMORIAS'}
KINDS = ('Venta', 'Servicio', 'PD', 'Entrada caja', 'Salida caja', 'Pago sueldo')
BASE_CAJA = 20000000  # Centavos de COP; permanece en caja al terminar cada jornada.
DEFAULT_ACCOUNTS = ['EFECTIVO', 'TRANSFERENCIA', 'DATÁFONO']
DRINK_PRICES = {'CORONA':400000,'AGUA':200000,'AGUA CON GAS':200000,'PONY':200000,
                'POKER':300000,'GASEOSA':200000,'COCACOLA':300000}

def display_account(name):
    upper=(name or '').upper()
    if upper.startswith('TRANSFERENCIA'):return 'TRANSFERENCIA'
    if upper.startswith(('DATÁFONO','DATAFONO')):
        return 'DATÁFONO · TARJETA POR IDENTIFICAR'
    return name

def payment_person(payments):
    people={p['person_id'] for p in payments if p.get('person_id')}
    return next(iter(people)) if len(people)==1 else None

def money(value):
    try:
        n = Decimal(str(value).strip().replace(',', '.'))
        if not n.is_finite() or n < 0 or n > 100000000000 or n != n.quantize(Decimal('.01')):
            raise ValueError()
        return int(n*100)
    except (InvalidOperation, ValueError):
        raise ValueError('Usa un importe positivo o cero, sin separadores de miles y con máximo dos decimales.')

def net_payment(payment):
    """Importe de venta sin el recargo del 5 % cobrado al cliente por datáfono."""
    if payment['account']=='CRÉDITO':return payment['net']
    if payment['account']=='DATÁFONO' and payment.get('surcharge_5'):
        return int((Decimal(payment['amount'])/Decimal('1.05')).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    return payment['amount']

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
    return dict(holiday=False,opening=BASE_CAJA,normal_base=29100000,sandra_extra=3000000,
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
        cfg={**previous.config,'staff':[], 'opening':BASE_CAJA,'sandra':False,'holiday':False,'reviewed':False,'actor':'','note':''}
    cfg['accounts']=DEFAULT_ACCOUNTS[:]
    cfg['holiday']=day in cfg.get('holidays',[])
    d=Jornada(date=day,config=cfg)
    db.session.add(d)
    try: db.session.commit()
    except IntegrityError: db.session.rollback();return find_day(day)
    return d

def save_config(d,form):
    cfg=dict(d.config)
    cfg['opening']=BASE_CAJA
    for k in ('normal_base','sandra_extra','extra_a','extra_b','normal_return',
              'sandra_sunday','sandra_control_sunday','sandra_control_work','sandra_control_absent'):
        cfg[k]=money(form.get(k,''))
    for k in ('holiday','sandra','sandra_step','require_principal','reviewed'):
        cfg[k]=form.get(k)=='1'
    cfg['actor']=text(form.get('actor'))
    cfg['note']=text(form.get('note'),False,500)
    cfg['accounts']=DEFAULT_ACCOUNTS[:]
    names=form.getlist('staff_name'); roles=form.getlist('staff_role'); salaries=form.getlist('staff_salary')
    attendance=form.getlist('staff_attended')
    if not len(names)==len(roles)==len(salaries): raise ValueError('Lista de personal incompleta.')
    staff=[]
    for index,(n,r,s) in enumerate(zip(names,roles,salaries)):
        if not n.strip() and not s.strip(): continue
        if r not in ('Principal','Secundaria'): raise ValueError('Función inválida.')
        staff.append(dict(name=text(n),role=r,salary=money(s),attended=str(index) in attendance))
    if not staff or not any(p['attended'] for p in staff): raise ValueError('Registra y confirma la asistencia de al menos una persona.')
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
    attending=[x for x in cfg['staff'] if x.get('attended',True)]
    p=sum(x['role']=='Principal' for x in attending);s=len(attending)-p;a=int(cfg['sandra'])
    salaries=sum(x['salary'] for x in attending)
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
    bank_gross=defaultdict(int);bank_net=defaultdict(int);bank_profit=defaultdict(int)
    bank_internal=defaultdict(int)
    pool_admin_gain=0
    credit_net=credit_gross=credit_profit=pool_purchase_gain=pool_extra=bank_sale_net=0
    retoma_received=retoma_control=0
    internal_bank_funds=0
    cash=d.config.get('opening', BASE_CAJA);warnings=[]
    allocations=[]
    for o in active:
        if o.kind=='Venta':
            if o.product_id:
                product=db.session.get(Producto,o.product_id)
                if product and product.source_type=='Retoma':
                    pool_admin_gain+=product.pool_admin_gain_cents or 0
            margin=o.amount-sum(c['amount'] for c in o.costs)
            debe+=margin;haber+=o.minor_cost;gross+=o.amount
            own_funds=0
            for c in o.costs:
                if c['type']=='Fondo' or (c['type']=='Proveedor' and c['name'] in INTERNAL_PROVIDERS):
                    name='CP HIDROGELES' if c['name'] in ('CP HIDROGEL','CP HIDRÓGEL') else 'BATERÍAS' if c['name']=='CP BATERIAS' else 'MEMORIAS' if c['name']=='CP MEMORIAS' else c['name']
                    funds[name]+=c['amount']
                    own_funds+=c['amount']
            # Solo operaciones complementarias: MOD03 conserva sus propios cobros.
            remaining_profit=max(0,margin)
            payment_split=[]
            for payment in sorted(o.payments,key=lambda x:x['account']!='EFECTIVO'):
                if payment['account'] not in ('CRÉDITO','RETOMA'):banks[display_account(payment['account'])]+=payment['amount']
                if payment['account']=='EFECTIVO': cash+=payment['amount']
                net=net_payment(payment)
                if payment['account'] in ('TRANSFERENCIA','DATÁFONO','CRÉDITO'):bank_sale_net+=net
                profit_here=min(net,remaining_profit)
                remaining_profit-=profit_here
                cost_here=net-profit_here
                if payment['account'] not in ('EFECTIVO','RETOMA'): transfer+=profit_here
                if payment['account']=='RETOMA':
                    retoma_received+=net;retoma_control+=profit_here
                if payment['account']=='CRÉDITO':
                    credit_gross+=payment['amount'];credit_net+=net;credit_profit+=profit_here
                if payment['account'] in ('TRANSFERENCIA','DATÁFONO'):
                    bank_gross[payment['account']]+=payment['amount']
                    bank_net[payment['account']]+=net
                    bank_profit[payment['account']]+=profit_here
                payment_split.append(dict(account=payment['account'],amount=payment['amount'],net=net,profit=profit_here,cost=cost_here))
            # En el Excel, TOTAL TRANSFER incluye tanto la ganancia bancaria
            # como los fondos de mercancía propia recibidos por banco/datáfono.
            # Son una reserva interna; no son un pago ni una salida de caja.
            bank_cost=sum(part['cost'] for part in payment_split if part['account'] not in ('EFECTIVO','RETOMA'))
            own_in_bank=min(own_funds,bank_cost)
            retoma_control+=min(own_funds-own_in_bank,sum(part['cost'] for part in payment_split if part['account']=='RETOMA'))
            internal_bank_funds+=own_in_bank
            transfer+=own_in_bank
            pending_own=own_in_bank
            for part in payment_split:
                if part['account'] not in ('TRANSFERENCIA','DATÁFONO'): continue
                assigned=min(pending_own,part['cost'])
                bank_internal[part['account']]+=assigned
                pending_own-=assigned
            if payment_split: allocations.append(dict(operation=o,parts=payment_split,margin=margin,
                                                      own_in_bank=own_in_bank))
        else:
            if o.kind=='Compra POOL':
                from ..models.gestion import CompraPool
                buy=db.session.scalar(db.select(CompraPool).where(CompraPool.operacion_id==o.id))
                if buy:
                    debe+=buy.ganancia;pool_purchase_gain+=buy.ganancia
                    cash+=buy.aporte-buy.costos_pagados-(buy.pago_cliente if buy.tipo=='Compra directa' else 0)
            if o.kind=='Servicio': service+=o.amount
            if o.kind=='PD': pd+=o.amount
            for pay in o.payments:
                if pay['account']=='EFECTIVO': cash+=pay['amount']*(1 if o.kind=='Entrada caja' else -1)
    paid_in_finance={o.product_id for o in active if o.product_id and o.payments}
    for c in collections:
        if (c.reference or '').startswith('CREDITO '):continue
        if c.product_id in paid_in_finance:continue
        if c.legacy: warnings.append(f'Cobro {c.id}: saldo anterior pendiente de conciliación.');continue
        key='EFECTIVO' if c.method=='Efectivo' else c.method.upper()+' · MOD03 SIN CUENTA'
        banks[display_account(key)]+=c.amount_cents
        # Cobros de MOD03 se atribuyen a la fecha de recaudo, no crean
        # una segunda ganancia en la fecha de la venta.
        if c.method in ('Transferencia','Tarjeta'):
            method='TRANSFERENCIA' if c.method=='Transferencia' else 'DATÁFONO'
            bank_gross[method]+=c.amount_cents
            bank_net[method]+=c.amount_cents
        if c.destination=='Negocio' and c.method=='Efectivo': cash+=c.amount_cents
    for r in receipts:
        c=db.session.get(Cobro,r.collection_id)
        if c.product_id in paid_in_finance:continue
        if c.destination=='Vendedora' and r.method=='Efectivo': cash+=r.amount_cents
    from ..models.gestion import DesembolsoCredito
    received_credits=sum(x.monto for x in db.session.scalars(db.select(DesembolsoCredito).where(DesembolsoCredito.fecha==d.date,DesembolsoCredito.activo==True)))
    bank_gross['TRANSFERENCIA']+=received_credits;bank_net['TRANSFERENCIA']+=received_credits
    banks['TRANSFERENCIA']+=received_credits
    supplier_payments=db.session.scalars(db.select(Pago).where(Pago.day_id==d.id)).all()
    cash-=sum(x.amount for x in supplier_payments if x.account=='EFECTIVO')
    integrated={o.product_id for o in active if o.product_id}
    pending_sales=[p for p in sales if p.id not in integrated]
    if pending_sales: warnings.append('Hay ventas de equipos sin incorporar al resultado. Revísalas antes del cierre.')
    if any(c.destination=='Vendedora' for c in collections): warnings.append('El efectivo cobrado por vendedoras entra a caja de administración solo al confirmar su recepción.')
    if any(c.method!='Efectivo' and not (c.reference or '').startswith(('FINANZAS ','CREDITO ')) for c in collections): warnings.append('Hay cobros manuales MOD03 sin cuenta bancaria concreta; aparecen agrupados por medio.')
    if any('POR IDENTIFICAR' in p.get('account','').upper() for o in active for p in o.payments):
        warnings.append('Existen medios históricos sin titular identificado; aparecen consolidados pero requieren conciliación.')
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
    if totals['control_cash'] is not None:totals['control_cash']-=retoma_control
    totals.update(retoma_received=retoma_received,retoma_control=retoma_control)
    from ..models.gestion import ComisionPool
    extras=db.session.scalars(db.select(ComisionPool).join(Op,Op.id==ComisionPool.operacion_id).where(Op.day_id==d.id,Op.voided==False)).all()
    totals['pool_extra_commission']=sum(x.monto for x in extras)
    totals['pool_extra_pending']=sum(x.monto for x in extras if not x.pago_operacion_id)
    salary_paid=sum(o.amount for o in active if o.kind=='Pago sueldo')
    salary_due=max(0,sum(x['salary'] for x in d.config['staff'] if x.get('attended',True))-salary_paid)
    base_shortfall=max(0,BASE_CAJA-cash)
    payroll_shortfall=max(0,BASE_CAJA+salary_due-cash)
    if base_shortfall: warnings.append(f'Faltan ${base_shortfall/100:,.0f} para reponer la base de caja de $200.000; solicita aporte al administrador o propietario.')
    if salary_due: warnings.append(f'Sueldos pendientes de pago: ${salary_due/100:,.0f}. Registra cada pago o solicita fondos para cubrirlo.')
    if totals['owner_result'] is not None and totals['owner_result']<0:
        warnings.append(f'El resultado del día está en rojo: ${-totals["owner_result"]/100:,.0f}. Revisa el aporte necesario con administración.')
    totals.update(gross=gross,cash_expected=cash,banks=dict(banks),internal_bank_funds=internal_bank_funds,
                  bank_gross=dict(bank_gross),bank_net=dict(bank_net),bank_profit=dict(bank_profit),
                  bank_internal=dict(bank_internal),
                  bank_received=sum(bank_gross.values()),bank_net_total=sum(bank_net.values()),
                  bank_profit_total=sum(bank_profit.values()),
                  pool_admin_gain=pool_admin_gain,pool_purchase_gain=pool_purchase_gain,credit_net=credit_net,credit_gross=credit_gross,credit_profit=credit_profit,credit_received=received_credits,bank_sale_net=bank_sale_net,bank_and_credit_profit=sum(bank_profit.values())+credit_profit,
                  customer_collections=sum(c.amount_cents for c in collections if not c.legacy),
                  cash_to_deliver=cash-BASE_CAJA,base_shortfall=base_shortfall,payroll_shortfall=payroll_shortfall,
                  salary_due=salary_due,base=BASE_CAJA,admin_receipts=sum(r.amount_cents for r in receipts),
                  sales_count=sum(o.kind=='Venta' for o in active),warnings=warnings)
    owned_device_plan=[]
    for o in active:
        if not o.product_id:continue
        equipment=db.session.get(Producto,o.product_id)
        cost=sum(c['amount'] for c in o.costs if c['type']=='Equipo propio')
        collected=db.session.scalars(db.select(Cobro).where(Cobro.product_id==o.product_id,Cobro.voided==False,Cobro.legacy==False)).all()
        direct_cash=sum(c.amount_cents for c in collected if c.method=='Efectivo' and c.destination=='Negocio')
        received_cash=sum(x.amount_cents for x in db.session.scalars(db.select(Recepcion).join(Cobro,Recepcion.collection_id==Cobro.id).where(
            Cobro.product_id==o.product_id,Cobro.voided==False,Recepcion.voided==False,Recepcion.method=='Efectivo')))
        cash=min(cost,max(0,direct_cash+received_cash-max(0,o.amount-sum(c['amount'] for c in o.costs))))
        owned_device_plan.append(dict(operation=o,source=equipment.source_type if equipment else 'Lote',
                                      cost=cost,pool_admin_gain=equipment.pool_admin_gain_cents if equipment else 0,
                                      from_cash=cash,from_admin=cost-cash))
    return dict(drinks=dict(drinks),supplier_payments=supplier_payments,totals=totals,operations=ops,
                owned_device_plan=owned_device_plan,
                allocations=allocations,pending_sales=pending_sales,collections=collections,receipts=receipts)

def parse_costs(f, require_external_imei=False):
    costs=[]
    names=f.getlist('cost_name');types=f.getlist('cost_type');quantities=f.getlist('cost_qty');units=f.getlist('cost_unit')
    categories=f.getlist('cost_category');details=f.getlist('cost_detail');imeis=f.getlist('cost_external_imei')
    if not len(names)==len(types)==len(quantities)==len(units): raise ValueError('Detalle de costos incompleto.')
    if len(names)>8: raise ValueError('Máximo ocho líneas: cinco accesorios, equipo y consumos.')
    accessory=0
    for i,(name,typ,q,u) in enumerate(zip(names,types,quantities,units)):
        if not name.strip():
            if u.strip(): raise ValueError('Indica la procedencia de cada costo.')
            continue
        if typ=='Artículo':
            from .stock_service import parse_cost
            costs.append(parse_cost(name,q,u));continue
        if typ not in ('Proveedor','Equipo','Fondo','Bebida'): raise ValueError('Tipo de costo inválido.')
        name=text(name)
        detail=text(details[i] if i<len(details) else '',False,300)
        if name in ('OTRO','OTROS') and not detail:
            raise ValueError('Describe el costo de Otros: domicilio, proveedor, bebida regalada u otro concepto.')
        if typ=='Fondo' and name not in INTERNAL_PROVIDERS: raise ValueError('Selecciona un fondo del catálogo.')
        supplier=db.session.scalar(db.select(Catalogo).where(
            Catalogo.kind=='supplier',Catalogo.active==1,Catalogo.name==name)) if typ=='Proveedor' else None
        if typ=='Proveedor' and not supplier and name not in ('OTRO','OTROS'):
            raise ValueError('Selecciona un proveedor activo o créalo primero en Catálogos.')
        if typ=='Equipo':
            disponible=db.session.scalar(db.select(Producto).where(Producto.imei==name,Producto.status=='Disponible',Producto.archived==0))
            if not disponible:raise ValueError('Selecciona el IMEI de un equipo disponible.')
            if not u.strip():  # quien vende sin ver costos: el costo sale de Inventario, nunca del navegador
                from .sociedad_service import capital_basis
                u=f'{(capital_basis(disponible) if disponible.source_type=="Retoma" else disponible.cost_cents)/100:.2f}'
        qty=int(q)
        if not 1<=qty<=10000: raise ValueError('Cantidad fuera de rango.')
        category=categories[i] if i<len(categories) and categories[i] else (
            'Celulares' if typ=='Equipo' else ((supplier.supplier_category or 'Accesorios') if supplier else 'Accesorios'))
        if category=='Ambos':raise ValueError(f'Indica si {name} corresponde a un celular o un accesorio.')
        if supplier and category!='Servicio técnico' and supplier.supplier_category in ('Celulares','Accesorios') and category!=supplier.supplier_category:
            raise ValueError(f'{name} está registrado como proveedor de {supplier.supplier_category.lower()}.')
        if category not in ('Celulares','Accesorios','Servicio técnico') or (typ=='Equipo' and category!='Celulares') or (typ in ('Fondo','Bebida') and category!='Accesorios'):
            raise ValueError('Revisa la clasificación de este costo.')
        if typ=='Bebida' and name not in ('OTRO','OTROS') and (name not in DRINK_PRICES or money(u)!=DRINK_PRICES[name]):
            raise ValueError('Selecciona una bebida y su valor predeterminado.')
        if category=='Accesorios' and typ in ('Proveedor','Fondo'):accessory+=1
        external=typ=='Proveedor' and category=='Celulares' and name not in INTERNAL_PROVIDERS
        imei=(imeis[i] if i<len(imeis) else '').strip()
        if external and require_external_imei and not imei:
            raise ValueError('Ingresa el IMEI del celular del proveedor externo.')
        if external and imei and (len(imei)!=15 or not imei.isascii() or not imei.isdigit()):
            raise ValueError('El IMEI externo debe tener 15 dígitos.')
        if external and imei and qty!=1: raise ValueError('Registra cada celular externo por separado, con su IMEI.')
        cost=dict(name=name,detail=detail,type=typ,category=category,quantity=qty,unit=money(u),amount=qty*money(u))
        if external and imei:cost['external_imei']=imei
        if supplier:cost['supplier_id']=supplier.id
        costs.append(cost)
    if accessory>5: raise ValueError('Máximo cinco procedencias de accesorios.')
    return costs


def selected_responsible(d,f,kind):
    value=f.get('seller','')
    attending={p['name'] for p in d.config.get('staff',[]) if p.get('attended',True)}
    if value=='__other__':
        if kind=='Pago sueldo':raise ValueError('Un sueldo solo se paga a personal presente.')
        return text(f.get('seller_other'))
    result=text(value)
    if attending and result not in attending:
        raise ValueError('Selecciona una persona que trabaja hoy u Otro.')
    return result


def parse_payments(d,f):
    accounts=f.getlist('payment_account');values=f.getlist('payment_amount')
    people=f.getlist('payment_person_id');banks=f.getlist('payment_bank_id')
    if len(accounts)!=len(values):raise ValueError('Detalle de medios incompleto.')
    if len(people)<len(accounts):people+=['']*(len(accounts)-len(people))
    if len(banks)<len(accounts):banks+=['']*(len(accounts)-len(banks))
    payments=[]
    for index,(account,value,person,bank) in enumerate(zip(accounts,values,people,banks)):
        if not value.strip():continue
        if account not in (*DEFAULT_ACCOUNTS,'CRÉDITO','RETOMA'):raise ValueError('Selecciona un medio válido.')
        amount=money(value)
        if amount:
            if account=='RETOMA':
                from .retoma_service import retoma_payment
                payments.append(retoma_payment(f,index,amount));continue
            if account=='CRÉDITO':
                from .credito_service import credit_payment
                payments.append(credit_payment(f,index,amount,person,bank));continue
            item=dict(account=account,amount=amount)
            if account=='DATÁFONO':item['surcharge_5']=True
            if account in BANCARIOS:item['person_id'],item['bank_id']=destino(person,bank,account)
            payments.append(item)
    if len(payments)>5:raise ValueError('Máximo cinco medios de pago.')
    traded=[p['equipment_id'] for p in payments if p['account']=='RETOMA']
    if len(traded)!=len(set(traded)):raise ValueError('La misma retoma no puede usarse dos veces en una venta.')
    return payments

def payment_total(payments,kind):
    return sum(net_payment(p) if kind=='Venta' else p['amount'] for p in payments)

def sale_net_amount(entered, payments):
    """Acepta el total cobrado bruto o el precio neto y guarda siempre el neto."""
    net=payment_total(payments,'Venta')
    gross=sum(p['amount'] for p in payments)
    if not net or entered not in (gross,net):
        raise ValueError('El valor de la venta debe coincidir con el total cobrado o con el neto de los medios. En datáfono el neto es cobro / 1,05.')
    return net

def add_operation(d,f):
    kind=f.get('kind');token=f.get('token','')
    if kind not in KINDS or len(token)!=32: raise ValueError('Operación inválida. Recarga el formulario.')
    if db.session.scalar(db.select(Op.id).where(Op.token==token)): raise ValueError('Esta operación ya fue registrada.')
    description=text(f.get('description'),True,300);seller=selected_responsible(d,f,kind)
    amount=money(f.get('amount'));minor=money(f.get('minor_cost') or '0') if kind=='Venta' else 0
    if amount<=0: raise ValueError('El importe debe ser mayor que cero.')
    costs=parse_costs(f,require_external_imei=True) if kind=='Venta' else []
    payments=parse_payments(d,f)
    if kind!='Venta' and any(p['account'] in ('CRÉDITO','RETOMA') for p in payments):raise ValueError('Crédito y retoma solo pueden utilizarse en una venta.')
    if kind=='Venta':
        charged_amount=amount
        amount=sale_net_amount(amount,payments)
    elif payment_total(payments,kind)!=amount:
        raise ValueError('Indica la cuenta de salida/entrada por el importe completo.')
    if kind=='Pago sueldo':
        employee=next((p for p in d.config['staff'] if p['name']==seller and p.get('attended',True)),None)
        if not employee: raise ValueError('Selecciona una persona con asistencia confirmada en esta jornada.')
        previous=sum(o.amount for o in db.session.scalars(db.select(Op).where(Op.day_id==d.id,Op.kind=='Pago sueldo',Op.seller==seller,Op.voided==False)))
        if previous+amount>employee['salary']: raise ValueError('El pago excede el sueldo configurado para esta persona.')
    person_id=payment_person(payments) if kind=='Venta' else None
    equipment_costs=[c for c in costs if c['type']=='Equipo']
    if equipment_costs:
        if kind!='Venta' or len(equipment_costs)!=1 or equipment_costs[0]['quantity']!=1:
            raise ValueError('Registra un solo equipo por venta. Los demás costos pueden ser accesorios.')
        from ..models import Movimiento
        equipment=db.session.scalar(db.select(Producto).where(Producto.imei==equipment_costs[0]['name']))
        if not equipment or equipment.archived or equipment.status!='Disponible':
            raise ValueError('El equipo ya no está disponible; recarga la página.')
        if any(x.get('equipment_id')==equipment.id for x in payments):raise ValueError('El equipo vendido no puede recibirse como parte de pago de sí mismo.')
        assigned=equipment_costs[0]['unit']
        if equipment.source_type=='Retoma':
            from .sociedad_service import capital_basis
            if assigned<capital_basis(equipment):
                raise ValueError('El costo asignado al equipo del POOL debe ser igual o mayor que su costo total de compra.')
        elif assigned!=equipment.cost_cents:
            raise ValueError('El costo del equipo de lote debe coincidir con el costo registrado en Inventario.')
        equipment_costs[0]['type']='Equipo propio'
        before=equipment.to_dict()
        from .sociedad_service import capital_basis
        pool_gain=assigned-capital_basis(equipment) if equipment.source_type=='Retoma' else 0
        if equipment.source_type=='Retoma':
            equipment.pool_assigned_cost_cents=assigned
            equipment.pool_admin_gain_cents=pool_gain
        equipment.status='Vendido';equipment.sale_date=d.date;equipment.sale_value_cents=amount
        equipment.seller=seller;equipment.responsible=seller;equipment.person_id=person_id
        equipment.paid_cents=sum(net_payment(p) for p in payments if p['account']!='CRÉDITO')
        equipment.payment_status='Pagado' if equipment.paid_cents==amount else ('Abono' if equipment.paid_cents else 'Pendiente')
        equipment.payment_date=d.date if equipment.paid_cents==amount else None
        equipment.movement_date=d.date
        equipment.last_note=(f'Venta en Finanzas. POOL: costo de compra ${equipment.cost_cents/100:,.2f}; '
                             f'costo asignado ${assigned/100:,.2f}; adicional para administración '
                             f'${pool_gain/100:,.2f}.' if equipment.source_type=='Retoma'
                             else 'Venta registrada en Finanzas')
        equipment.revision+=1
        db.session.flush()
        db.session.add(Movimiento(product_id=equipment.id,action='Confirmar venta',reason=equipment.last_note,
            actor=actor(),before_data=json.dumps(before,ensure_ascii=False),
            after_data=json.dumps(equipment.to_dict(),ensure_ascii=False)))
        for index,payment in enumerate(payments):
            if payment['account']=='CRÉDITO':continue
            db.session.add(Cobro(product_id=equipment.id,amount_cents=net_payment(payment),destination='Negocio',
                collector='PAGO DIRECTO AL NEGOCIO',method={'EFECTIVO':'Efectivo','TRANSFERENCIA':'Transferencia','DATÁFONO':'Tarjeta','RETOMA':'Retoma'}[payment['account']],
                reference=f'FINANZAS {token} / MEDIO {index+1}',effective_date=d.date,
                note='Cobro registrado en Finanzas; datáfono expresado sin recargo'))
    o=Op(day_id=d.id,token=token,kind=kind,description=description,seller=seller,amount=amount,minor_cost=minor,
         costs=costs,payments=payments,person_id=person_id,product_id=equipment.id if equipment_costs else None)
    db.session.add(o);db.session.flush();sincronizar_operacion(d.date,o)
    from .credito_service import attach
    attach(o)
    from .sociedad_service import on_sale
    on_sale(d,o)
    from .stock_service import apply_sale
    apply_sale(o)
    audit(d,'Registro '+kind,description,{'amount':amount,'charged_amount':charged_amount if kind=='Venta' else amount,'actor':seller,
          'pool_admin_gain_cents':pool_gain if equipment_costs else 0})


def protect_managed_operation(operation):
    """No desvincular una caja de los acuerdos que originaron su movimiento."""
    from ..models.gestion import CompraPool, ComisionPool
    if not operation:return
    purchase=db.session.scalar(db.select(CompraPool.producto_id).where(
        (CompraPool.operacion_id==operation.id)|(CompraPool.venta_origen_id==operation.id)))
    commission=db.session.scalar(db.select(ComisionPool.id).where(ComisionPool.pago_operacion_id==operation.id))
    society=operation.description.startswith(('LIQUIDACIÓN SOCIO ','DEVOLUCIÓN CAPITAL ','COMPENSACIÓN POR EQUIPO '))
    if purchase or commission or society:
        raise ValueError('Este movimiento está vinculado a una compra POOL, comisión pagada o liquidación de socios. Debe conciliarse con su acuerdo de origen; no se puede editar o anular por separado.')

def edit_operation(d, f):
    original=db.session.get(Op,int(f.get('operation_id') or 0))
    protect_managed_operation(original)
    if original and any(c.get('stock_id') for c in original.costs):raise ValueError('Esta venta descontó existencias; anúlala y regístrala de nuevo para corregir cantidades.')
    if original and any(p['account']=='RETOMA' for p in original.payments):raise ValueError('Esta venta recibió un equipo como parte de pago. Concilia esa retoma antes de cambiar sus medios.')
    from ..models.gestion import CreditoVenta
    if db.session.scalar(db.select(CreditoVenta.id).where(CreditoVenta.operacion_id==int(f.get('operation_id') or 0))):
        raise ValueError('Esta venta conserva un contrato de crédito. Anula la venta sin recaudos y regístrala de nuevo para corregir sus condiciones.')
    try: operation_id=int(f.get('operation_id',''))
    except (ValueError, TypeError): raise ValueError('Selecciona una operación válida.')
    o=db.session.get(Op,operation_id)
    if not o or o.day_id!=d.id or o.voided or o.product_id:
        raise ValueError('Solo se pueden editar movimientos complementarios de esta jornada. La venta de un equipo se corrige desde Ventas y pagos.')
    if o.description.startswith('APORTE CONFIRMADO:'):
        raise ValueError('Un aporte confirmado no se edita. Anula el registro con motivo y confirma el importe correcto.')
    linked_payments=db.session.scalars(db.select(Pago).where(Pago.operation_id==o.id)).all()
    reason=text(f.get('reason'),True,500)
    before={'description':o.description,'seller':o.seller,'amount':o.amount,'minor_cost':o.minor_cost,
            'costs':o.costs,'payments':o.payments,'person_id':o.person_id}
    kind=o.kind
    description=text(f.get('description'),True,300);seller=selected_responsible(d,f,kind)
    amount=money(f.get('amount'));minor=money(f.get('minor_cost') or '0') if kind=='Venta' else 0
    if amount<=0: raise ValueError('El importe debe ser mayor que cero.')
    costs=parse_costs(f) if kind=='Venta' else []
    payments=parse_payments(d,f)
    if any(p['account'] in ('CRÉDITO','RETOMA') for p in payments) or any(c.get('stock_id') or c['type']=='Equipo' for c in costs):
        raise ValueError('Para añadir un crédito, retoma o artículo de inventario, registra una nueva venta después de conciliar la anterior. Esta corrección admite los medios de cobro habituales.')
    if kind=='Venta':amount=sale_net_amount(amount,payments)
    elif not payments or payment_total(payments,kind)!=amount:
        raise ValueError('El desglose por medios debe sumar el valor de la operación.')
    old_costs=[{'detail':'',**c} for c in o.costs]
    if linked_payments and (costs!=old_costs or amount!=o.amount or minor!=o.minor_cost):
        raise ValueError('Ya hay pagos a proveedores: conserva valor y costos. Puedes corregir los medios de cobro y el responsable.')
    if kind=='Pago sueldo':
        employee=next((p for p in d.config['staff'] if p['name']==seller and p.get('attended',True)),None)
        if not employee:raise ValueError('El destinatario no tiene asistencia confirmada.')
        previous=sum(p.amount for p in db.session.scalars(db.select(Op).where(Op.day_id==d.id,Op.kind=='Pago sueldo',
            Op.seller==seller,Op.voided==False,Op.id!=o.id)))
        if previous+amount>employee['salary']:raise ValueError('La corrección excede el sueldo configurado.')
    person_id=payment_person(payments) if kind=='Venta' else None
    o.description=description;o.seller=seller;o.amount=amount;o.minor_cost=minor;o.costs=costs;o.payments=payments;o.person_id=person_id
    sincronizar_operacion(d.date,o)
    audit(d,'Edición de movimiento',reason,{'operation':o.id,'before':before,'after':{
        'description':description,'seller':seller,'amount':amount,'minor_cost':minor,'costs':costs,'payments':payments,'person_id':person_id}})


def confirm_contribution(d, f):
    """Aporte real confirmado; nunca cuenta como venta ni resultado comercial."""
    administrator=text(f.get('administrator'))
    if len(administrator)<2: raise ValueError('Indica quién confirmó y entregó el aporte.')
    amount=money(f.get('amount'))
    if amount<=0: raise ValueError('El aporte debe ser mayor que cero.')
    reason=text(f.get('reason'),True,500)
    token=f.get('token','')
    if len(token)!=32 or db.session.scalar(db.select(Op.id).where(Op.token==token)):
        raise ValueError('Aporte duplicado o formulario vencido. Recarga la página.')
    db.session.add(Op(day_id=d.id,token=token,kind='Entrada caja',description='APORTE CONFIRMADO: '+reason,
                      seller=administrator,amount=amount,minor_cost=0,costs=[],payments=[dict(account='EFECTIVO',amount=amount)]))
    audit(d,'Aporte de caja confirmado',reason,{'administrator':administrator,'amount':amount,'account':'EFECTIVO'})

def incorporate(d,pid,token):
    p=db.session.get(Producto,int(pid))
    if not p or p.sale_date!=d.date or p.status not in ('Vendido','Garantía') or not p.sale_value_cents:
        raise ValueError('La venta no está disponible para esta jornada.')
    if db.session.scalar(db.select(Op.id).where(Op.product_id==p.id)): raise ValueError('El equipo ya tiene un resultado registrado.')
    matches=db.session.scalars(db.select(PersonaContable).where(PersonaContable.nombre==p.responsible)).all() if p.responsible else []
    operation=Op(day_id=d.id,token=token,kind='Venta',description=p.model+' · '+p.imei,seller=p.seller or 'SIN VENDEDORA',
        amount=p.sale_value_cents,minor_cost=0,product_id=p.id,person_id=p.person_id or (matches[0].id if len(matches)==1 else None),
        costs=[dict(name='COSTO DE INVENTARIO',type='Equipo propio',quantity=1,unit=p.cost_cents,amount=p.cost_cents)],payments=[])
    db.session.add(operation);db.session.flush()
    from .sociedad_service import on_sale
    on_sale(d,operation)
    audit(d,'Incorporar venta','Costo y valor tomados del equipo',{'equipment_id':p.id})

def obligations(as_of=None):
    paid=defaultdict(int)
    paid_cash=defaultdict(int)
    supplier_types={s.name:s.supplier_category for s in db.session.scalars(db.select(Catalogo).where(Catalogo.kind=='supplier'))}
    payments_query=db.select(Pago).join(Jornada,Pago.day_id==Jornada.id)
    if as_of: payments_query=payments_query.where(Jornada.date<=as_of)
    for p in db.session.scalars(payments_query):
        paid[(p.operation_id,p.cost_index)]+=p.amount
        if p.account=='EFECTIVO':paid_cash[p.operation_id]+=p.amount
    result=[]
    operations_query=db.select(Op).join(Jornada,Op.day_id==Jornada.id).where(Op.voided==False)
    if as_of: operations_query=operations_query.where(Jornada.date<=as_of)
    for o in db.session.scalars(operations_query):
        origin=db.session.get(Jornada,o.day_id)
        cash_received=sum(p['amount'] for p in o.payments if p['account']=='EFECTIVO')
        profit=max(0,o.amount-sum(c['amount'] for c in o.costs))
        cash_for_devices=max(0,cash_received-profit-paid_cash[o.id])
        for i,c in enumerate(o.costs):
            if c['type'] not in ('Proveedor','Equipo','Bebida') or (c['type']=='Proveedor' and c['name'] in INTERNAL_PROVIDERS):continue
            balance=c['amount']-paid[(o.id,i)]
            if balance:
                device=c.get('category',supplier_types.get(c['name']))=='Celulares' or c['type']=='Equipo'
                cash_part=min(balance,cash_for_devices) if device else balance
                if device:cash_for_devices-=cash_part
                result.append(dict(operation=o,index=i,cost=c,balance=balance,origin_date=origin.date,
                    from_cash=cash_part,from_admin=balance-cash_part,device=device))
    return result

def pay_supplier(d,f):
    oid=int(f.get('operation_id'));idx=int(f.get('cost_index'))
    item=next((x for x in obligations() if x['operation'].id==oid and x['index']==idx),None)
    if not item: raise ValueError('La obligación ya fue pagada o no existe.')
    origin=db.session.get(Jornada,item['operation'].day_id)
    if origin.date>d.date: raise ValueError('No puedes pagar antes de registrar la obligación.')
    amount=money(f.get('amount'));account=f.get('account')
    if not 0<amount<=item['balance'] or account not in DEFAULT_ACCOUNTS: raise ValueError('Revisa importe y cuenta de pago.')
    if len(f.get('token',''))!=32: raise ValueError('Recarga el formulario de pago.')
    person_id,bank_id=destino(f.get('payment_person_id'),f.get('payment_bank_id'),account) if account in BANCARIOS else (None,None)
    payment=Pago(day_id=d.id,operation_id=oid,cost_index=idx,amount=amount,account=account,token=f['token'],person_id=person_id,bank_id=bank_id)
    db.session.add(payment);db.session.flush();sincronizar_pago(d.date,payment)
    audit(d,'Pago proveedor',text(f.get('reason'),True,500),{'operation':oid,'cost':idx,'amount':amount,'account':account})


def edit_supplier_payment(d,f):
    try:pid=int(f.get('payment_id',''))
    except (ValueError,TypeError):raise ValueError('Selecciona un pago válido.')
    payment=db.session.get(Pago,pid)
    if not payment or payment.day_id!=d.id:raise ValueError('Solo puedes editar pagos de esta jornada abierta.')
    operation=db.session.get(Op,payment.operation_id)
    if not operation or operation.voided or payment.cost_index>=len(operation.costs):
        raise ValueError('La obligación cambió; revisa antes de corregir el pago.')
    cost=operation.costs[payment.cost_index]
    other=sum(p.amount for p in db.session.scalars(db.select(Pago).where(
        Pago.operation_id==operation.id,Pago.cost_index==payment.cost_index,Pago.id!=pid)))
    amount=money(f.get('amount'))
    account=f.get('account')
    if not 0<amount<=cost['amount']-other or account not in DEFAULT_ACCOUNTS:
        raise ValueError('El pago corregido debe ser positivo y no superar el saldo de la obligación.')
    person_id,bank_id=destino(f.get('payment_person_id'),f.get('payment_bank_id'),account) if account in BANCARIOS else (None,None)
    reason=text(f.get('reason'),True,500)
    before=dict(amount=payment.amount,account=payment.account,person_id=payment.person_id,bank_id=payment.bank_id)
    payment.amount=amount;payment.account=account;payment.person_id=person_id;payment.bank_id=bank_id
    sincronizar_pago(d.date,payment)
    audit(d,'Edición de pago a proveedor',reason,{'payment':pid,'operation':operation.id,'cost':payment.cost_index,
        'before':before,'after':dict(amount=amount,account=account,person_id=person_id,bank_id=bank_id)})


def update_equipment_costs(d,f):
    o=db.session.get(Op,int(f.get('operation_id')))
    if not o or o.day_id!=d.id or not o.product_id or o.voided:
        raise ValueError('La operación de equipo no está disponible.')
    if db.session.scalar(db.select(Pago.id).where(Pago.operation_id==o.id)):
        raise ValueError('Corrige primero los pagos a proveedores antes de cambiar este detalle.')
    if any(c.get('stock_id') for c in o.costs):raise ValueError('Esta venta tiene movimientos de existencias. Anula y vuelve a registrar para corregir cantidades.')
    costs=parse_costs(f)
    if any(c.get('stock_id') for c in costs):raise ValueError('Registra accesorios de inventario como venta con existencias; no se agregan mediante corrección del costo del equipo.')
    if any(c['type']=='Equipo' for c in costs):
        raise ValueError('El costo del equipo ya viene del inventario. Agrega únicamente costos complementarios.')
    own=[c for c in o.costs if c['type'] in ('Equipo propio','Comisión POOL')]
    before={'costs':o.costs,'minor_cost':o.minor_cost}
    o.costs=own+costs;o.minor_cost=money(f.get('minor_cost','0'))
    from .sociedad_service import refresh_result
    refresh_result(o,f.get('reason'))
    audit(d,'Costos de paquete',text(f.get('reason'),True,500),{'operation':o.id,'before':before,'after':{'costs':o.costs,'minor_cost':o.minor_cost}})
