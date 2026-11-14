from ..extensions import db
from ..services import pago_service as payments
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from ..services import inventario_service as inventory
from ..services.operacion_service import operate, ALLOWED, today
from ..services.catalogo_service import list_items, CONDITIONS
from ..models import PersonaContable

ventas = Blueprint('ventas', __name__)


@ventas.get('/ventas')
def index():
    query = request.args.get('q', '').strip()
    state = request.args.get('estado', '')
    pending_only = request.args.get('saldo') == '1'
    rows = inventory.list_products(query)
    counts = dict(available=sum(r['status']=='Disponible' for r in rows),
                  loaned=sum(r['status']=='En pasamano' for r in rows),
                  sold=sum(r['status']=='Vendido' for r in rows),
                  pending=sum(r['status']=='Vendido' and r.get('sale_value_cents') is not None
                              and r['sale_value_cents'] > (r.get('paid_cents') or 0) for r in rows))
    if state:
        rows = [r for r in rows if r['status'] == state]
    if pending_only:
        rows = [r for r in rows if r['status']=='Vendido' and r.get('sale_value_cents') is not None
                and r['sale_value_cents'] > (r.get('paid_cents') or 0)]
    return render_template('ventas/index.html', rows=rows, query=query, state=state, states=ALLOWED,
                           counts=counts, pending_only=pending_only, active='ventas')


@ventas.route('/ventas/<int:product_id>', methods=['GET', 'POST'])
def detail(product_id):
    product = inventory.get_product(product_id)
    if not product:
        abort(404)
    error = None
    if request.method == 'POST':
        try:
            action = request.form.get('action')
            if action == 'void_collection':
                payments.void_record(product_id, request.form)
            else:
                operate(product_id, action, request.form)
            flash('Movimiento comercial registrado. La disponibilidad está actualizada.')
            return redirect(url_for('ventas.detail', product_id=product_id))
        except ValueError as exc:
            db.session.rollback()
            error = str(exc)
    from ..models.gestion import CreditoVenta
    from ..models.finanzas import OperacionFinanciera
    credits=db.session.scalars(db.select(CreditoVenta).join(OperacionFinanciera,OperacionFinanciera.id==CreditoVenta.operacion_id).where(OperacionFinanciera.product_id==product.id,CreditoVenta.estado!='Anulado')).all()
    return render_template('ventas/detalle.html', product=product.to_dict(), error=error,credits=credits,
                           money=payments.summary(product), methods=payments.METHODS, admin=False,
                           events=inventory.history(product_id), catalog=list_items(active_only=True),
                           accounting_people=db.session.scalars(db.select(PersonaContable).order_by(PersonaContable.nombre)).all(),
                           conditions=CONDITIONS, now_date=today(),
                           operations=ALLOWED.get(product.status, []) + ([('correct_date','Corregir fecha del último movimiento')] if product.movement_date else []), active='ventas')


@ventas.get('/ventas/recepciones')
def receipts():
    query = request.args.get('q', '').strip()
    rows = []
    for item in inventory.list_products(query):
        product = inventory.get_product(item['id'])
        totals = payments.summary(product)
        if totals['rows']:
            rows.append(dict(product=item, money=totals))
    by_seller = {}
    for item in rows:
        for row in item['money']['rows']:
            c = row['collection']
            if not c.voided and c.destination == 'Vendedora':
                by_seller[c.collector] = by_seller.get(c.collector, 0) + row['pending']
    return render_template('ventas/recepciones.html', rows=rows, by_seller=by_seller, query=query, active='ventas')


@ventas.route('/ventas/recepciones/<int:product_id>', methods=['GET', 'POST'])
def receipt_detail(product_id):
    product = inventory.get_product(product_id)
    if not product:
        abort(404)
    error = None
    if request.method == 'POST':
        try:
            action = request.form.get('action')
            if action == 'receive':
                payments.receive(product_id, request.form)
            elif action == 'void_receipt':
                payments.void_record(product_id, request.form, receipt=True)
            else:
                raise ValueError('Acción no válida en recepción de dinero.')
            flash('Recepción actualizada sin volver a sumar el pago del cliente.')
            return redirect(url_for('ventas.receipt_detail', product_id=product_id))
        except ValueError as exc:
            db.session.rollback()
            error = str(exc)
    return render_template('ventas/detalle.html', product=product.to_dict(), error=error,
        money=payments.summary(product), methods=payments.METHODS, admin=True,
        events=inventory.history(product_id), operations=[], now_date=today(), active='ventas')
