from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from ..services.lote_service import create_lot, get_lot, list_lots
from ..services.catalogo_service import list_items
from ..services.inventario_service import list_products
from ..services.operacion_service import today

lotes = Blueprint('lotes', __name__)


@lotes.route('/inventario/lotes', methods=['GET', 'POST'])
def index():
    error = None
    if request.method == 'POST':
        try:
            lot = create_lot(request.form)
            flash('Lote creado. Ahora registra sus equipos.')
            return redirect(url_for('lotes.detail', lot_id=lot.id))
        except ValueError as exc:
            error = str(exc)
    return render_template('inventario/lotes.html', lots=list_lots(), suppliers=list_items('supplier', True),
                           now_date=today(), data=request.form, error=error, active='inventario')


@lotes.get('/inventario/lotes/<int:lot_id>')
def detail(lot_id):
    lot = get_lot(lot_id)
    if not lot:
        abort(404)
    rows = [r for r in list_products() + list_products(archived=True) if r['lot_id'] == lot_id]
    summary = next(r for r in list_lots() if r['lot'].id == lot_id)
    return render_template('inventario/lote.html', lot=lot, rows=rows, summary=summary, active='inventario')
