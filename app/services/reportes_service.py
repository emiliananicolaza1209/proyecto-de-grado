"""Consultas sin escrituras. Importes en centavos COP; fechas comerciales inclusivas."""
from datetime import date, datetime, timedelta
from collections import defaultdict
from decimal import Decimal
from ..extensions import db
from ..models import Producto, Lote, Cobro, Recepcion, ConsignacionBancaria
from ..models.finanzas import Jornada, OperacionFinanciera as Op
from ..models.gestion import (CreditoVenta, AliadoCredito, ControlLote, RegistroGestion,
                             ArticuloStock, CategoriaStock, PropiedadEquipo)
from .operacion_service import today
from . import finanzas_service as finance


def period(args):
    end = args.get('hasta') or today()
    start = args.get('desde') or end[:8]+'01'
    try:
        a, b = date.fromisoformat(start), date.fromisoformat(end)
        if a.isoformat()!=start or b.isoformat()!=end or a>b or (b-a).days>365:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('Selecciona fechas válidas, ordenadas y un rango máximo de 366 días.')
    return start, end


def snapshot():
    return dict(moneda='COP', unidad='centavos', generado=datetime.now().astimezone().isoformat(),
                zona='America/Bogota')


def operations(start, end, location='', seller='', voided=False):
    q=db.select(Op, Jornada.date).join(Jornada, Jornada.id==Op.day_id).where(
        Jornada.date>=start,Jornada.date<=end,Op.kind=='Venta')
    if not voided:q=q.where(Op.voided==False)
    if seller:q=q.where(Op.seller==seller)
    if location:q=q.join(Producto, Producto.id==Op.product_id).where(Producto.location==location)
    return db.session.execute(q.order_by(Jornada.date,Op.id)).all()


def sales(args):
    a,b=period(args);location=args.get('ubicacion','');seller=args.get('vendedor','')
    rows=operations(a,b,location,seller,args.get('anuladas')=='1')
    details=[dict(id=o.id,fecha=d,descripcion=o.description,vendedor=o.seller,
                  equipo=o.product_id,anulada=o.voided,venta_neta=o.amount,
                  costos=sum(c['amount'] for c in o.costs),costos_menores=o.minor_cost) for o,d in rows]
    known={o.product_id for o,_ in rows if not o.voided and o.product_id}
    q=db.select(Producto).where(Producto.sale_date>=a,Producto.sale_date<=b,
                              Producto.status.in_(['Vendido','Garantía']),Producto.archived==0)
    if location:q=q.where(Producto.location==location)
    if seller:q=q.where(Producto.seller==seller)
    missing=[p.id for p in db.session.scalars(q) if p.id not in known]
    return dict(**snapshot(),desde=a,hasta=b,filas=details,
                cantidad=sum(not o.voided for o,_ in rows),
                venta_neta=sum(o.amount for o,_ in rows if not o.voided),
                equipos_sin_incorporar=missing,
                advertencias=['Ventas netas incorporadas a Finanzas; no equivalen al dinero cobrado.']+
                (['Hay equipos vendidos sin incorporar: el resultado es parcial.'] if missing else [])+
                (['El filtro de ubicación solo incluye operaciones vinculadas a equipos.'] if location else []))


def inventory(args, costs=False, ownership=False):
    q=db.select(Producto).where(Producto.archived==0)
    for param,attr in [('ubicacion','location'),('estado','status'),('condicion','condition')]:
        if args.get(param):q=q.where(getattr(Producto,attr)==args[param])
    if args.get('q'):q=q.where(db.or_(Producto.imei.contains(args['q'][:120]),Producto.model.contains(args['q'][:120])))
    rows=[]
    for p in db.session.scalars(q.order_by(Producto.id)):
        row=dict(id=p.id,imei=p.imei,referencia=p.model,capacidad=p.capacity,color=p.color,
                 condicion=p.condition,ubicacion=p.location,estado=p.status,lote=p.lot_id)
        if costs:
            row.update(costo=p.cost_cents)
        if ownership:
            own=db.session.get(PropiedadEquipo,p.id)
            row.update(sociedad=own.sociedad_id if own else None,participaciones=own.participaciones if own else [])
        rows.append(row)
    return dict(**snapshot(),filas=rows,cantidad=len(rows),advertencias=['Inventario actual; no reconstruye existencias históricas.'])


def credits(args):
    a,b=period(args)
    q=db.select(CreditoVenta,AliadoCredito.nombre,Jornada.date).join(Op,Op.id==CreditoVenta.operacion_id).join(
        Jornada,Jornada.id==Op.day_id).join(AliadoCredito,AliadoCredito.id==CreditoVenta.aliado_id).where(
        Op.voided==False,CreditoVenta.estado!='Anulado',Jornada.date>=a,Jornada.date<=b)
    if args.get('aliado'):
        try:ident=int(args['aliado'])
        except ValueError:raise ValueError('Aliado inválido.')
        q=q.where(CreditoVenta.aliado_id==ident)
    if args.get('estado'):q=q.where(CreditoVenta.estado==args['estado'])
    rows=[dict(id=c.id,fecha=d,aliado=n,bruto=c.bruto,costo=c.costo,neto=c.neto,
               recibido=c.recibido,pendiente=c.neto-c.recibido,estado=c.estado) for c,n,d in db.session.execute(q)]
    return dict(**snapshot(),desde=a,hasta=b,filas=rows,pendiente=sum(r['pendiente'] for r in rows),
                advertencias=['Saldo actual de créditos originados en el periodo; no es saldo histórico ni mora.'])


def financial(args):
    a,b=period(args)
    if args.get('ubicacion') or args.get('vendedor'):
        raise ValueError('El cierre incluye reglas de toda la jornada; no admite reparto por ubicación o vendedor.')
    include=args.get('abiertas')=='1'
    fields=('debe','haber','service','pd','liquidation','commission','owner_result')
    sums={k:0 for k in fields};rows=[];warnings=[];funds=defaultdict(int);staff=defaultdict(lambda:[0,0])
    days=db.session.scalars(db.select(Jornada).where(Jornada.date>=a,Jornada.date<=b).order_by(Jornada.date)).all()
    for d in days:
        if d.status=='Cerrada' and d.snapshot:
            totals=d.snapshot['totals'];cfg=d.snapshot.get('config',d.config);origin='Cierre'
        elif d.status=='Abierta' and include:
            totals=finance.report(d)['totals'];cfg=d.config;origin='Provisional'
        else:
            warnings.append(d.date+': jornada sin cierre utilizable.');continue
        for k in fields:
            if totals.get(k) is None:sums[k]=None
            elif sums[k] is not None:sums[k]+=totals[k]
        for k,v in totals.get('funds',{}).items():funds[k]+=v
        for person in cfg.get('staff',[]):
            if person.get('attended',True):staff[person['name']][0]+=person['salary']
        for op in db.session.scalars(db.select(Op).where(Op.day_id==d.id,Op.kind=='Pago sueldo',Op.voided==False)):
            staff[op.seller][1]+=op.amount
        rows.append(dict(fecha=d.date,fuente=origin,**{k:totals.get(k) for k in fields}))
        warnings.extend(d.date+': '+w for w in totals.get('warnings',[]))
    expected=(date.fromisoformat(b)-date.fromisoformat(a)).days+1
    return dict(**snapshot(),desde=a,hasta=b,filas=rows,totales=sums,fondos=dict(funds),
                sueldos=[dict(persona=n,causado=v[0],pagado_misma_jornada=v[1],pendiente=v[0]-v[1]) for n,v in sorted(staff.items())],
                dias_sin_jornada=expected-len(days),dias_incluidos=len(rows),
                advertencias=list(dict.fromkeys(warnings))+['Sueldos por nombre y jornada; no aplican pagos a obligaciones de otros periodos. Los fondos son capital reservado, no ventas brutas.'])


def purchases(args):
    a,b=period(args);rows=[]
    for lot in db.session.scalars(db.select(Lote).where(Lote.entry_date>=a,Lote.entry_date<=b).order_by(Lote.id)):
        control=db.session.get(ControlLote,lot.id)
        products=db.session.scalars(db.select(Producto).where(Producto.lot_id==lot.id,Producto.archived==0)).all()
        rows.append(dict(id=lot.id,codigo=lot.code,fecha=lot.entry_date,proveedor=lot.supplier.name,
                         estado=control.estado if control else 'Histórico',esperados=lot.expected_count,
                         equipos=len(products),capital_equipos=sum(p.cost_cents for p in products)))
    return dict(**snapshot(),desde=a,hasta=b,filas=rows,advertencias=['Capital de equipos activos; no incluye automáticamente artículos ni pagos al proveedor.'])


def accounting(args):
    a,b=period(args)
    rows=[]
    for c in db.session.scalars(db.select(ConsignacionBancaria).where(ConsignacionBancaria.activa==True,
            ConsignacionBancaria.fecha>=datetime.fromisoformat(a),
            ConsignacionBancaria.fecha<datetime.fromisoformat(b)+timedelta(days=1))):
        rows.append(dict(id=c.id,fecha=c.fecha.date().isoformat(),persona_id=c.persona_id,banco_id=c.banco_id,
                         monto=int(Decimal(c.monto)*100),operacion=c.finance_operation_id))
    return dict(**snapshot(),desde=a,hasta=b,filas=rows,total=sum(r['monto'] for r in rows),
                advertencias=['Consignaciones activas del periodo; no representan una declaración tributaria ni la utilidad del negocio.'])


def audit_report(args):
    a,b=period(args);q=db.select(RegistroGestion).where(RegistroGestion.fecha>=a,RegistroGestion.fecha<(
        date.fromisoformat(b)+timedelta(days=1)).isoformat())
    for key in ('entidad','actor'):
        if args.get(key):q=q.where(getattr(RegistroGestion,key)==args[key][:120])
    # Only the metadata, not JSON snapshots that may contain personal fields.
    rows=[dict(id=r.id,fecha=r.fecha,entidad=r.entidad,registro=r.entidad_id,accion=r.accion,actor=r.actor,motivo=r.motivo)
          for r in db.session.scalars(q.order_by(RegistroGestion.id.desc()).limit(5000))]
    return dict(**snapshot(),desde=a,hasta=b,filas=rows,advertencias=['Auditoría de gestión; máximo 5.000 filas. Los historiales de equipos y finanzas se conservan en sus módulos.'])


def consolidated(args):
    data=financial(args);concept=args.get('concepto','fondos');person=args.get('persona','').strip()
    if concept not in ('fondos','sueldos'):raise ValueError('Selecciona fondos o sueldos. Originales requiere clasificación del negocio.')
    rows=[]
    if concept=='fondos':
        rows=[dict(concepto=k,capital_reservado=v) for k,v in sorted(data['fondos'].items()) if not person or k==person]
    else:
        rows=[r for r in data['sueldos'] if not person or r['persona']==person]
    return dict(**snapshot(),desde=data['desde'],hasta=data['hasta'],filas=rows,
                dias_incluidos=data['dias_incluidos'],dias_sin_jornada=data['dias_sin_jornada'],
                advertencias=data['advertencias'])


REPORTS={'ventas':sales,'inventario':inventory,'creditos':credits,'finanzas':financial,
         'compras':purchases,'contable':accounting,'auditoria':audit_report,'consolidado_adicional':consolidated}


def comparison(args):
    a,b=period(args);span=(date.fromisoformat(b)-date.fromisoformat(a)).days+1
    previous_end=date.fromisoformat(a)-timedelta(days=1)
    prior=dict(args,desde=(previous_end-timedelta(days=span-1)).isoformat(),hasta=previous_end.isoformat())
    current=sales(args);before=sales(prior);delta=current['venta_neta']-before['venta_neta']
    return dict(actual=current,anterior=before,diferencia=delta,
                variacion_porcentaje=round(delta*100/before['venta_neta'],2) if before['venta_neta'] else None)
