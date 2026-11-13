"""Panel operativo de solo lectura; las cantidades monetarias están en centavos COP.

La fecha de una venta es la jornada en que se incorporó a Finanzas; la de un
cobro es su fecha efectiva. Las recepciones de administración no son ingresos
nuevos. Un desembolso de aliado se cuenta una vez, aunque genere varios Cobros.
"""
from collections import Counter, defaultdict
from datetime import date, timedelta

from ..extensions import db
from ..models import Producto, Cobro
from ..models.finanzas import Jornada, OperacionFinanciera as Op
from ..models.gestion import AplicacionCredito, DesembolsoCredito
from .operacion_service import today
from .inicio_service import operational_summary


def period(args):
    preset = args.get('periodo', 'personalizado' if args.get('desde') or args.get('hasta') else '7')
    current = date.fromisoformat(today())
    if preset in ('7', '15', '30'):
        return (current - timedelta(days=int(preset)-1)).isoformat(), current.isoformat(), preset
    try:
        first, last = args.get('desde', ''), args.get('hasta', '')
        a, b = date.fromisoformat(first), date.fromisoformat(last)
        if (a.isoformat() != first or b.isoformat() != last or a > b
                or (b-a).days > 365 or b > current):
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('Selecciona fechas válidas, sin fechas futuras y un período máximo de 366 días.')
    return first, last, 'personalizado'


def summary(args, financial=False):
    first, last, preset = period(args)
    operational = operational_summary()
    counts = db.session.execute(db.select(Producto.status, db.func.count(Producto.id)).where(
        Producto.archived == 0).group_by(Producto.status)).all()
    state_styles = {'Disponible': 'blue', 'Vendido': 'green', 'Separado': 'amber',
                    'En pasamano': 'slate', 'Garantía': 'slate'}
    states = [dict(name=s, count=n, style=state_styles.get(s, 'slate')) for s, n in counts]
    current_sale = db.and_(Producto.archived == 0, db.or_(Producto.status == 'Vendido',
        db.and_(Producto.status == 'Garantía', Producto.warranty_previous == 'Vendido')))
    sold_in_period = db.and_(current_sale, Producto.sale_date >= first, Producto.sale_date <= last)
    models = db.session.execute(db.select(Producto.model, db.func.count(Producto.id)).where(
        sold_in_period).group_by(Producto.model).order_by(db.func.count(Producto.id).desc(), Producto.model).limit(5)).all()
    models = [dict(name=name, count=n) for name, n in models]
    total_models = sum(x['count'] for x in models)
    for row in models:
        row['width'] = round(row['count']*100/max((x['count'] for x in models), default=1), 2)
    recent = db.session.scalars(db.select(Producto).where(sold_in_period).order_by(
        Producto.sale_date.desc(), Producto.id.desc()).limit(5)).all()
    chart = dict(financial=financial, states=states, days=[])
    result = dict(operational=operational, first=first, last=last, preset=preset,
                  financial=financial, states=states, total_equipment=sum(n for _, n in counts),
                  models=models, model_count=total_models, recent=recent, chart=chart,
                  sales=0, sales_count=0, collections=0, methods=[], outstanding=0,
                  unverified=0, missing=0, warnings=[])
    if not financial:
        # Ningún importe agregado ni costos se serializa para perfiles operativos.
        return result

    operations = db.session.execute(db.select(Op, Jornada.date).join(Jornada,
        Jornada.id == Op.day_id).where(Jornada.date >= first, Jornada.date <= last,
        Op.kind == 'Venta', Op.voided == False).order_by(Jornada.date, Op.id)).all()
    daily = defaultdict(lambda: dict(sales=0, collections=0))
    methods = Counter()
    generated = set()
    for operation, day in operations:
        daily[day]['sales'] += operation.amount
        for index, payment in enumerate(operation.payments):
            account = payment['account']
            if account in ('CRÉDITO', 'RETOMA'):
                continue
            # Finanzas y su Cobro generado representan el mismo pago. Los abonos
            # posteriores del mismo equipo SI se cuentan en su propia fecha.
            daily[day]['collections'] += payment['amount']
            methods[account] += payment['amount']
            if operation.product_id:
                generated.add((operation.product_id, f'FINANZAS {operation.token} / MEDIO {index+1}'))

    linked_credit_collection = db.select(AplicacionCredito.cobro_id).where(
        AplicacionCredito.cobro_id.is_not(None))
    collections = db.session.scalars(db.select(Cobro).where(
        Cobro.effective_date >= first, Cobro.effective_date <= last,
        Cobro.voided == False, Cobro.legacy == False,
        Cobro.id.not_in(linked_credit_collection))).all()
    for collection in collections:
        if ((collection.product_id, collection.reference) in generated
                or collection.method == 'Retoma'):
            continue
        method = {'Efectivo': 'EFECTIVO', 'Transferencia': 'TRANSFERENCIA',
                  'Tarjeta': 'DATÁFONO'}.get(collection.method, 'OTRO')
        daily[collection.effective_date]['collections'] += collection.amount_cents
        methods[method] += collection.amount_cents

    for deposit in db.session.scalars(db.select(DesembolsoCredito).where(
            DesembolsoCredito.fecha >= first, DesembolsoCredito.fecha <= last,
            DesembolsoCredito.activo == True)):
        daily[deposit.fecha]['collections'] += deposit.monto
        methods['ALIADO'] += deposit.monto

    for i in range((date.fromisoformat(last)-date.fromisoformat(first)).days+1):
        day = (date.fromisoformat(first)+timedelta(days=i)).isoformat()
        chart['days'].append(dict(date=day, **daily[day]))
    names = {'EFECTIVO': 'Efectivo', 'TRANSFERENCIA': 'Transferencia',
             'DATÁFONO': 'Datáfono', 'ALIADO': 'Desembolso de aliado', 'OTRO': 'Otros medios'}
    total_collections = sum(methods.values())
    outstanding = db.session.scalar(db.select(db.func.sum(
        Producto.sale_value_cents-Producto.paid_cents)).where(current_sale,
        Producto.payment_status != 'Por verificar', Producto.sale_value_cents > Producto.paid_cents)) or 0
    missing = db.session.scalar(db.select(db.func.count(Producto.id)).where(sold_in_period,
        ~db.select(Op.id).where(Op.product_id == Producto.id, Op.kind == 'Venta',
            Op.voided == False).exists())) or 0
    unverified = db.session.scalar(db.select(db.func.count(Producto.id)).where(
        current_sale, Producto.payment_status == 'Por verificar')) or 0
    warnings = []
    if missing:
        warnings.append(f'{missing} venta(s) de equipos sin incorporar a Finanzas. El total de ventas es parcial.')
    if unverified:
        warnings.append(f'{unverified} equipo(s) con pagos por verificar; sus saldos no se incluyen en el total por cobrar.')
    result.update(sales=sum(o.amount for o, _ in operations), sales_count=len(operations),
        collections=total_collections, outstanding=outstanding, missing=missing,
        unverified=unverified, warnings=warnings, methods=[dict(name=names.get(k, k),
        amount=v, width=round(v*100/total_collections, 2) if total_collections else 0)
        for k, v in methods.most_common()])
    return result
