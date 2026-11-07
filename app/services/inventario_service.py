from .gestion_comun import actor
"""Reglas de ingreso y consulta de equipos. Sin formularios ni respuestas HTTP."""
from decimal import Decimal
from sqlalchemy.exc import IntegrityError
from ..extensions import db
from ..models import Producto, Movimiento
from .catalogo_service import get_item
from sqlalchemy.orm.exc import StaleDataError
import json
from .catalogo_service import CONDITIONS, normalize, selected, clean
from .costo_service import purchase_cost, retoma_cost
from ..models import Catalogo
from datetime import date


def valid_imei(value):
    if len(value) != 15 or not value.isascii() or not value.isdigit():
        return False
    return sum(int(x) if i % 2 == 0 else (2*int(x)//10 + 2*int(x)%10)
               for i, x in enumerate(value)) % 10 == 0


def exists(imei):
    return db.session.scalar(db.select(Producto.id).where(Producto.imei == imei)) is not None


def stats():
    row = db.session.execute(db.select(db.func.count(Producto.id), db.func.coalesce(db.func.sum(Producto.cost_cents), 0)).where(Producto.archived == 0, Producto.status == 'Disponible')).one()
    return {'total': row[0], 'cost': row[1]}


def pool_summary():
    pool=db.session.scalars(db.select(Producto).where(Producto.source_type=='Retoma',Producto.archived==0)).all()
    available=[p for p in pool if p.status=='Disponible']
    sold=[p for p in pool if p.status=='Vendido' or (p.status=='Garantía' and p.warranty_previous=='Vendido')]
    return dict(total=len(pool),available=len(available),sold=len(sold),
                investment=sum(p.cost_cents for p in available),
                realized_margin=sum((p.sale_value_cents or 0)-p.cost_cents for p in sold),
                administration_gain=sum(p.pool_admin_gain_cents or 0 for p in sold),
                operating_margin=sum((p.sale_value_cents or 0)-(p.pool_assigned_cost_cents or p.cost_cents) for p in sold))


def list_products(query='', archived=False):
    rows = [item.to_dict() for item in db.session.scalars(db.select(Producto).where(Producto.archived == int(archived)).order_by(Producto.id.desc()))]
    needle = clean(query)
    from ..models.gestion import AliasReferencia
    alias=db.session.scalar(db.select(AliasReferencia).where(AliasReferencia.clave==needle,AliasReferencia.activo==True)) if needle else None
    return [r for r in rows if not query or query in r['imei'] or (needle and needle in clean(r['model'])) or (alias and r['reference_id']==alias.referencia_id)]


def similar_data(item_id):
    try:
        source = db.session.get(Producto, int(item_id))
    except (ValueError, TypeError):
        return {}
    if source is None:
        return {}
    data = {key: str(getattr(source, key)) for key in ('reference_id','color_id','capacity_id','supplier_id','location_id','condition')}
    data['lot_id'] = str(source.lot_id or '')
    data['entry_type'] = 'Retoma' if source.source_type=='Retoma' else 'Lote'
    if source.source_type=='Retoma':
        data['purchase_cop']=str(Decimal(source.purchase_cop_cents or 0)/100)
        data['additional_name']=[x['name'] for x in source.additional_costs or []]
        data['additional_amount']=[str(Decimal(x['amount_cents'])/100) for x in source.additional_costs or []]
    data['warranty_enabled'] = '1' if source.warranty_until else ''
    data['warranty_until'] = source.warranty_until or ''
    reference = get_item(source.reference_id, 'reference')
    if reference:
        data['brand_id'] = str(reference.parent_id)
    if source.purchase_usd is not None:
        data.update(purchase_usd=source.purchase_usd, exchange_rate=source.exchange_rate,
                    shipping_cop=str(Decimal(source.shipping_cents)/100))
    return data


def warranty_date(data):
    if data.get('warranty_enabled') != '1':
        return None
    value = data.get('warranty_until', '')
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('Indica hasta qué fecha cubre la garantía.')
    return value


def register_product(data):
    from .lote_service import get_lot
    entry_type=data.get('entry_type','Lote')
    if entry_type not in ('Lote','Retoma'):raise ValueError('Selecciona lote o retoma como origen del equipo.')
    lot=get_lot(data.get('lot_id')) if entry_type=='Lote' else None
    if entry_type=='Lote':
        if lot is None:raise ValueError('Selecciona el lote de esta compra antes de ingresar el equipo.')
        from ..models.gestion import ControlLote
        ctl=db.session.get(ControlLote,lot.id)
        if ctl and not ctl.heredado:raise ValueError('Agrega el equipo al borrador del lote y confirma el lote completo desde Compras y lotes.')
        if str(data.get('purchase_cop','')).strip() or data.get('additional_name'):
            raise ValueError('Los lotes usan USD y TRM; la compra en COP es solo para retomas.')
        data=dict(data,supplier_id=str(lot.supplier_id))
        data.setdefault('exchange_rate',lot.exchange_rate)
    else:
        if str(data.get('lot_id','')).strip():raise ValueError('Una retoma pertenece al POOL y no puede tener lote.')
        supplier=db.session.scalar(db.select(Catalogo).where(Catalogo.kind=='supplier',Catalogo.name=='CP CELULARES'))
        if not supplier or not supplier.active:raise ValueError('Activa el proveedor CP CELULARES en Catálogos.')
        data=dict(data,supplier_id=str(supplier.id))
    imei = data.get('imei', '').strip()
    if not valid_imei(imei):
        raise ValueError('El IMEI debe tener 15 dígitos y un dígito de control válido.')
    items = selected(data)
    if entry_type=='Retoma':
        base_cents,extra_costs,total_cents=retoma_cost(data)
    else:
        purchase,subtotal,cost=purchase_cost(data)
        base_cents=0;extra_costs=[];total_cents=int(cost*100)
    condition = data.get('condition', '')
    if condition not in CONDITIONS:
        raise ValueError('Selecciona una condición válida.')
    if entry_type=='Retoma' and condition!='Usado':raise ValueError('Todo equipo del POOL se registra como Usado.')
    if entry_type=='Retoma' and 'BODEGA' in items['location'].name.upper():
        raise ValueError('Selecciona el local que recibe la retoma; luego podrás trasladarla si hace falta.')
    product = Producto(lot_id=lot.id if lot else None,source_type=entry_type,
                       purchase_cop_cents=base_cents if entry_type=='Retoma' else None,
                       additional_costs=extra_costs if entry_type=='Retoma' else None,
                       warranty_until=warranty_date(data), imei=imei, model=items['reference'].display_name, capacity=int(items['capacity'].name),
                       color=items['color'].name, condition=condition, cost_cents=total_cents,
                       location=items['location'].name, supplier=items['supplier'].name,
                       purchase_usd=str(purchase['purchase_usd']) if entry_type=='Lote' else None,
                       exchange_rate=str(purchase['exchange_rate']) if entry_type=='Lote' else None,
                       shipping_cents=int(purchase['shipping_cop']*100) if entry_type=='Lote' else None,
                       subtotal_cents=int(subtotal*100) if entry_type=='Lote' else base_cents,
                       **{kind+'_id': items[kind].id for kind in ('reference','color','capacity','supplier','location')})
    try:
        db.session.add(product)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ValueError('Este IMEI ya está registrado. Búscalo en el inventario.')
    return product


def get_product(product_id):
    return db.session.get(Producto, product_id)


def history(product_id):
    rows = db.session.scalars(db.select(Movimiento).where(Movimiento.product_id == product_id).order_by(Movimiento.id.desc()))
    result = []
    labels = {'imei':'IMEI','model':'Referencia','capacity':'Capacidad GB','color':'Color',
              'condition':'Condición','warranty_until':'Garantía hasta','supplier':'Proveedor','location':'Ubicación',
              'cost_cents':'Costo total COP','purchase_usd':'Compra USD','exchange_rate':'Precio dólar COP/USD',
              'shipping_cents':'Envío COP','subtotal_cents':'Subtotal COP','archived':'Retirado del inventario',
              'source_type':'Origen','purchase_cop_cents':'Precio de retoma COP','additional_costs':'Comisiones y reparaciones'}
    labels.update({'status':'Estado del equipo','responsible':'Responsable','movement_date':'Fecha del movimiento',
                   'payment_status':'Estado del pago','sale_value_cents':'Valor de venta COP','payment_date':'Fecha de pago',
                   'seller':'Vendido por','loan_handler':'Encargada del pasamano','loan_price_cents':'Precio acordado de pasamano COP',
                   'detalle_dinero':'Detalle de dinero','loan_date':'Fecha del préstamo','sale_date':'Fecha de venta','last_note':'Observación'})
    for row in rows:
        labels.update({'paid_cents':'Dinero recibido COP','purpose':'Propósito','due_date':'Fecha límite','battery':'Batería %','warranty_previous':'Estado anterior a garantía'})
        before, after = json.loads(row.before_data), json.loads(row.after_data)
        changes = []
        from ..auth import can
        for key, label in labels.items():
            if not can('costos') and key in ('cost_cents','purchase_usd','exchange_rate','shipping_cents','subtotal_cents','purchase_cop_cents','additional_costs'):continue
            a, b = before.get(key), after.get(key)
            if a != b:
                if key.endswith('_cents'):
                    a = str(Decimal(a)/100) if a is not None else 'Sin dato'
                    b = str(Decimal(b)/100) if b is not None else 'Sin dato'
                changes.append((label, a, b))
        result.append(dict(action=row.action, reason=row.reason, actor=row.actor, created_at=row.created_at, changes=changes))
    return result


def change_product(product_id, action, data):
    if action not in ('edit','transfer','archive','restore'):
        raise ValueError('El estado y los pagos se gestionan exclusivamente desde Ventas y pagos.')
    product = get_product(product_id)
    if product is None:
        raise ValueError('El equipo no existe.')
    if str(product.revision) != data.get('revision'):
        raise ValueError('El equipo cambió en otra ventana. Recarga la página antes de continuar.')
    reason = data.get('reason', '').strip()
    if not 3 <= len(reason) <= 500:
        raise ValueError('Escribe un motivo de entre 3 y 500 caracteres.')
    if action not in ('edit','transfer','archive','restore','handoff','return','sell','mark_paid'):
        raise ValueError('Acción desconocida.')
    if action == 'restore':
        if product.status in ('Entregado a socio','Anulado lote'):
            raise ValueError('Este retiro pertenece a una sociedad o a un lote revertido. Debe corregirse desde ese proceso, no restaurando el equipo por separado.')
        if not product.archived:
            raise ValueError('El equipo ya está activo.')
    elif product.archived:
        raise ValueError('No puedes modificar un equipo eliminado.')
    elif product.status != 'Disponible':
        raise ValueError('Solo puedes editar, trasladar o eliminar equipos disponibles.')
    before = product.to_dict()
    values = {}
    if action == 'edit':
        from ..models.gestion import CompraPool
        financed_purchase=db.session.get(CompraPool,product.id)
        if product.lot:
            data = dict(data, supplier_id=str(product.lot.supplier_id))
        imei = data.get('imei', '').strip()
        if not valid_imei(imei):
            raise ValueError('Ingresa un IMEI válido de 15 dígitos.')
        # La ubicación se modifica exclusivamente mediante un traslado.
        items = {}
        brand = get_item(data.get('brand_id'), 'brand')
        if not brand or not brand.active:
            raise ValueError('Selecciona una marca activa.')
        for kind in ('reference','color','capacity','supplier'):
            item = get_item(data.get(kind+'_id'), kind)
            if item is None or (not item.active and item.id != getattr(product, kind+'_id')):
                raise ValueError('Selecciona opciones activas del catálogo.')
            items[kind] = item
        if items['reference'].parent_id != brand.id:
            raise ValueError('El modelo debe pertenecer a la marca seleccionada.')
        if any(items[k].parent_id != items['reference'].id for k in ('color','capacity')):
            raise ValueError('El color y la capacidad deben pertenecer al modelo seleccionado.')
        if data.get('condition') not in CONDITIONS:
            raise ValueError('Selecciona una condición válida.')
        if product.source_type=='Retoma' and data['condition']!='Usado':
            raise ValueError('Los equipos del POOL conservan la condición Usado.')
        if product.source_type=='Retoma' and items['supplier'].id!=product.supplier_id:
            raise ValueError('La retoma debe continuar con proveedor CP CELULARES.')
        values.update(imei=imei,model=items['reference'].display_name,color=items['color'].name,
                      capacity=int(items['capacity'].name),supplier=items['supplier'].name,
                      condition=data['condition'],**{k+'_id':v.id for k,v in items.items()})
        if 'warranty_form' in data:
            values['warranty_until'] = warranty_date(data)
        # No inventar el desglose de compras anteriores.
        if product.source_type=='Retoma':
            purchase_cop,extras,total=retoma_cost(data)
            if financed_purchase and (purchase_cop!=product.purchase_cop_cents or extras!=(product.additional_costs or []) or total!=product.cost_cents):
                raise ValueError('La compra del POOL ya tiene financiación confirmada. Puedes corregir los datos del equipo, pero sus costos requieren conciliar esa financiación con administración.')
            values.update(purchase_cop_cents=purchase_cop,additional_costs=extras,
                          subtotal_cents=purchase_cop,cost_cents=total)
        elif product.purchase_usd is not None or any(data.get(k,'').strip() for k in ('purchase_usd','exchange_rate','shipping_cop')):
            purchase, subtotal, total = purchase_cost(data)
            values.update(purchase_usd=str(purchase['purchase_usd']),exchange_rate=str(purchase['exchange_rate']),
                          shipping_cents=int(purchase['shipping_cop']*100),subtotal_cents=int(subtotal*100),cost_cents=int(total*100))
    elif action == 'transfer':
        target = get_item(data.get('location_id'), 'location')
        if target is None or not target.active:
            raise ValueError('Selecciona una bodega de destino activa.')
        if target.id == product.location_id:
            raise ValueError('La bodega de destino debe ser diferente de la actual.')
        values.update(location_id=target.id,location=target.name)
    elif action == 'archive':
        if data.get('confirm_imei','').strip() != product.imei:
            raise ValueError('Escribe el IMEI del equipo para confirmar la eliminación.')
        values['archived'] = 1
    else:
        values['archived'] = 0
    if all(getattr(product,k) == v for k,v in values.items()):
        raise ValueError('No hay cambios para guardar.')
    try:
        for key,value in values.items():
            setattr(product,key,value)
        if action=='edit' and 'cost_cents' in values:
            from ..models.gestion import PropiedadEquipo
            ownership=db.session.get(PropiedadEquipo,product.id)
            if ownership and not financed_purchase:
                ownership.capital=values['cost_cents']
        db.session.flush()
        db.session.refresh(product)
        names = {'edit':'Edición','transfer':'Traslado','archive':'Eliminación del inventario','restore':'Restauración','handoff':'Salida a pasamano','return':'Devolución de pasamano','sell':'Venta confirmada','mark_paid':'Pago recibido'}
        db.session.add(Movimiento(product_id=product.id,action=names[action],reason=reason,
                                  before_data=json.dumps(before,ensure_ascii=False),
                                  after_data=json.dumps(product.to_dict(),ensure_ascii=False),
                                  actor=actor()))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ValueError('El IMEI ya pertenece a otro equipo, incluso si fue eliminado.')
    except StaleDataError:
        db.session.rollback()
        raise ValueError('Otro proceso modificó el equipo. Recarga e intenta de nuevo.')
    return product
