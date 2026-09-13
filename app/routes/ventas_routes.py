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
            operate(product_id, request.form.get('action'), request.form)
            flash('Movimiento comercial registrado. La disponibilidad está actualizada.')
            return redirect(url_for('ventas.detail', product_id=product_id))
        except ValueError as exc:
            error = str(exc)
    return render_template('ventas/detalle.html', product=product.to_dict(), error=error,
                           events=inventory.history(product_id), catalog=list_items(active_only=True),
                           conditions=CONDITIONS, now_date=today(),
                           operations=ALLOWED.get(product.status, []) + ([('correct_date','Corregir fecha del último movimiento')] if product.movement_date else []), active='ventas')
