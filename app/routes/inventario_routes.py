"""Controlador de inventario: recibe HTTP y delega las reglas al servicio."""
from flask import abort, Blueprint, flash, jsonify, redirect, render_template, request, url_for
from ..services import inventario_service as service
from ..services.catalogo_service import CONDITIONS, list_items
from datetime import date
from ..services.operacion_service import today, ALLOWED

inventory = Blueprint('inventory', __name__)


@inventory.post('/inventario/<int:product_id>/revision-pool')
def review_pool(product_id):
    from ..auth import can
    if not can('admin'):abort(403)
    from ..database import begin_write
    from ..extensions import db
    from ..services.pool_compra_service import review
    try:
        begin_write()
        review(product_id, request.form.get('pending_id'), request.form.get('note'))
        db.session.commit()
        flash('Compra POOL revisada. Se conserva el equipo y su movimiento original.')
    except ValueError as exc:
        db.session.rollback();flash(str(exc), 'error')
    return redirect(url_for('inventory.detail', product_id=product_id))


@inventory.get('/inventario')
def index():
    query = request.args.get('q', '').strip()
    archived = request.args.get('eliminados') == '1'
    sold = request.args.get('vendidos') == '1' and not archived
    all_items = request.args.get('todos') == '1' and not archived and not sold
    rows = service.list_products(query, archived)
    if not archived and not all_items:
        rows = [r for r in rows if (r['status']=='Vendido' or (r['status']=='Garantía' and r['warranty_previous']=='Vendido'))] if sold else [r for r in rows if r['status']=='Disponible']
    location = request.args.get('bodega','')
    if location:
        rows = [r for r in rows if str(r['location_id'])==location]
    if request.args.get('condicion'):rows=[r for r in rows if r['condition']==request.args['condicion']]
    if request.args.get('estado'):rows=[r for r in rows if r['status']==request.args['estado']]
    counts = {}
    for row in rows:
        key = row['reference_id']
        counts.setdefault(key, {'model':row['model'], 'count':0})['count'] += 1
    from ..auth import can
    from ..services.pool_compra_service import pending
    context = dict(rows=rows, query=query, archived=archived, sold=sold, all_items=all_items, counts=list(counts.values()), active='inventario',pool=service.pool_summary(),pool_pending=pending() if can('admin') else [],
                           total=service.stats()['total'], locations=list_items('location',True), location=location)
    if request.args.get('fragment') == '1':
        return render_template('inventario/resultados.html', **context)
    return render_template('inventario/index.html', **context)


@inventory.route('/inventario/nuevo', methods=['GET', 'POST'])
def new():
    from ..services.lote_service import list_lots, get_lot
    data = request.form.to_dict() if request.method == 'POST' else service.similar_data(request.args.get('similar'))
    if request.method=='POST':
        data['additional_name']=request.form.getlist('additional_name')
        data['additional_amount']=request.form.getlist('additional_amount')
    if request.method == 'GET' and request.args.get('lote'):
        data['lot_id'] = request.args['lote']
    if request.method=='GET' and request.args.get('tipo')=='Retoma':
        data['entry_type']='Retoma'
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
    template='inventario/retoma.html' if data.get('entry_type')=='Retoma' else 'inventario/nuevo.html'
    return render_template(template, data=data, error=error, active='inventario',
                           catalog=list_items(active_only=True), conditions=CONDITIONS, lots=list_lots(), lot=lot)


@inventory.get('/inventario/verificar-imei')
def check_imei():
    imei = request.args.get('imei', '').strip()
    valid = service.valid_imei(imei)
    from ..models import Producto
    from ..extensions import db
    known=db.session.scalar(db.select(Producto).where(Producto.imei==imei)) if valid else None
    identification={'reference_id':known.reference_id,'model':known.model,'capacity':known.capacity,'color':known.color,'source':'Registro interno','verified_physical':False} if known else None
    return jsonify(valid=valid,exists=bool(known),identification=identification,notice='Comprueba físicamente color y capacidad; el IMEI por sí solo no los confirma.')


@inventory.route('/inventario/<int:product_id>', methods=['GET', 'POST'])
def detail(product_id):
    product = service.get_product(product_id)
    if product is None:
        abort(404)
    data = request.form.to_dict() if request.method == 'POST' else service.similar_data(product_id)
    if request.method=='POST':
        data['additional_name']=request.form.getlist('additional_name')
        data['additional_amount']=request.form.getlist('additional_amount')
    if request.method == 'GET':
        data.update(imei=product.imei, revision=str(product.revision))
    from ..auth import can
    if not can('costos') and request.method=='GET':return redirect(url_for('ventas.detail',product_id=product_id))
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
    from ..services.pool_compra_service import pending
    return render_template('inventario/detalle.html', product=product.to_dict(),data=data,error=error,
                           pool_pending=pending(product_id) if can('admin') else [],
                           events=service.history(product_id),catalog=options,conditions=CONDITIONS,
                           now_date=today(),operations=ALLOWED.get(product.status,[])+([('correct_date','Corregir fecha del último movimiento')] if product.movement_date else []),active='inventario')
