"""Controlador de inventario: recibe HTTP y delega las reglas al servicio."""
from flask import abort, Blueprint, flash, jsonify, redirect, render_template, request, url_for
from ..services import inventario_service as service
from ..services.catalogo_service import CONDITIONS, list_items
from datetime import date
from ..services.operacion_service import today, ALLOWED

inventory = Blueprint('inventory', __name__)


@inventory.get('/inventario')
def index():
    query = request.args.get('q', '').strip()
    archived = request.args.get('eliminados') == '1'
    sold = request.args.get('vendidos') == '1' and not archived
    rows = service.list_products(query, archived)
    if not archived:
        rows = [r for r in rows if (r['status']=='Vendido' or (r['status']=='Garantía' and r['warranty_previous']=='Vendido'))] if sold else [r for r in rows if r['status']=='Disponible']
    location = request.args.get('bodega','')
    if location:
        rows = [r for r in rows if str(r['location_id'])==location]
    counts = {}
    for row in rows:
        key = row['reference_id']
        counts.setdefault(key, {'model':row['model'], 'count':0})['count'] += 1
    context = dict(rows=rows, query=query, archived=archived, sold=sold, counts=list(counts.values()), active='inventario',
                           total=service.stats()['total'], locations=list_items('location',True), location=location)
    if request.args.get('fragment') == '1':
        return render_template('inventario/resultados.html', **context)
    return render_template('inventario/index.html', **context)


@inventory.route('/inventario/nuevo', methods=['GET', 'POST'])
def new():
    from ..services.lote_service import list_lots, get_lot
    data = request.form.to_dict() if request.method == 'POST' else service.similar_data(request.args.get('similar'))
    if request.method == 'GET' and request.args.get('lote'):
        data['lot_id'] = request.args['lote']
    lot = get_lot(data.get('lot_id'))
    if lot:
        data['supplier_id'] = str(lot.supplier_id)
        data.setdefault('exchange_rate', lot.exchange_rate)
    error = None
    if request.method == 'POST':
        try:
            product = service.register_product(data)
            flash('Equipo registrado correctamente.')
            if data.get('action') == 'similar':
                return redirect(url_for('inventory.new', similar=product.id))
            return redirect(url_for('inventory.index', q=product.imei))
        except ValueError as exc:
            error = str(exc)
    return render_template('inventario/nuevo.html', data=data, error=error, active='inventario',
                           catalog=list_items(active_only=True), conditions=CONDITIONS, lots=list_lots(), lot=lot)


@inventory.get('/inventario/verificar-imei')
def check_imei():
    imei = request.args.get('imei', '').strip()
    valid = service.valid_imei(imei)
    return jsonify(valid=valid, exists=service.exists(imei) if valid else False)


@inventory.route('/inventario/<int:product_id>', methods=['GET', 'POST'])
def detail(product_id):
    product = service.get_product(product_id)
    if product is None:
        abort(404)
    data = request.form.to_dict() if request.method == 'POST' else service.similar_data(product_id)
    if request.method == 'GET':
        data.update(imei=product.imei, revision=str(product.revision))
    error = None
    if request.method == 'POST':
        try:
            service.change_product(product_id, data.get('action'), data)
            flash('Operación guardada en el historial del equipo.')
            return redirect(url_for('inventory.detail', product_id=product_id))
        except ValueError as exc:
            error = str(exc)
    options = list_items()
    current_ids = {getattr(product,k+'_id') for k in ('reference','color','capacity','supplier','location')}
    options = [r for r in options if r['active'] or r['id'] in current_ids]
    return render_template('inventario/detalle.html', product=product.to_dict(),data=data,error=error,
                           events=service.history(product_id),catalog=options,conditions=CONDITIONS,
                           now_date=today(),operations=ALLOWED.get(product.status,[])+([('correct_date','Corregir fecha del último movimiento')] if product.movement_date else []),active='inventario')
