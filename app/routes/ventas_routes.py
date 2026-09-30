from ..extensions import db
from ..services import pago_service as payments
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from ..services import inventario_service as inventory
from ..services.operacion_service import operate, ALLOWED, today
from ..services.catalogo_service import list_items, CONDITIONS

ventas = Blueprint('ventas', __name__)


@ventas.get('/ventas')
def index():
    query = request.args.get('q', '').strip()
    state = request.args.get('estado', '')
    rows = inventory.list_products(query)
    if state:
        rows = [r for r in rows if r['status'] == state]
    return render_template('ventas/index.html', rows=rows, query=query, state=state, states=ALLOWED, active='ventas')


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
    return render_template('ventas/detalle.html', product=product.to_dict(), error=error,
                           money=payments.summary(product), methods=payments.METHODS, admin=False,
                           events=inventory.history(product_id), catalog=list_items(active_only=True),
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
