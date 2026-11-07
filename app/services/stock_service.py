from ..extensions import db
from ..models.gestion import ArticuloStock,CategoriaStock,UnidadStock,MovimientoStock
from .gestion_comun import get_id,actor,audit

def balance(ident):
    return db.session.scalar(db.select(db.func.coalesce(db.func.sum(MovimientoStock.cantidad),0)).where(MovimientoStock.articulo_id==ident)) or 0

def movement(article,quantity,cost,reason,lot=None,operation=None,serial=None):
    if not quantity or balance(article.id)+quantity<0:raise ValueError('Cantidad inválida o existencias insuficientes: '+article.nombre)
    unit=None
    if article.serializado:
        if abs(quantity)!=1 or not serial or len(serial)>100:raise ValueError('Cada repuesto serializado requiere una unidad y su serial (hasta 100 caracteres).')
        unit=db.session.scalar(db.select(UnidadStock).where(UnidadStock.articulo_id==article.id,UnidadStock.serial==serial))
        if quantity>0:
            if unit and unit.disponible:raise ValueError('El serial ya está disponible.')
            if unit is None:
                unit=UnidadStock(articulo_id=article.id,serial=serial);db.session.add(unit)
            unit.disponible=True
        else:
            if not unit or not unit.disponible:raise ValueError('Serial no disponible.')
            unit.disponible=False
        db.session.flush()
    row=MovimientoStock(articulo_id=article.id,cantidad=quantity,costo_unitario=cost,motivo=reason,
        lote_id=lot,operacion_id=operation,unidad_id=unit.id if unit else None,actor=actor())
    db.session.add(row);db.session.flush()
    return row

def parse_cost(name,quantity,unit):
    from .finanzas_service import money
    parts=name.strip().split('/',1);article=get_id(ArticuloStock,parts[0])
    category=get_id(CategoriaStock,article.categoria_id)
    if not article.activo or not category.activa:raise ValueError('El artículo o su categoría no está activo.')
    q=int(quantity)
    if q<1 or q>10000:raise ValueError('Revisa la cantidad del artículo.')
    if money(unit)!=article.costo_administracion:raise ValueError('El costo del artículo debe coincidir con el fijado por administración.')
    serial=parts[1].strip() if len(parts)>1 else None
    if article.serializado and (q!=1 or not serial):raise ValueError('Usa ID/SERIAL para el repuesto serializado.')
    if balance(article.id)<q:raise ValueError('No hay cantidad suficiente: '+article.nombre)
    return dict(type='Fondo',name=article.fondo,detail=article.nombre,category='Accesorios',quantity=q,
        unit=article.costo_administracion,amount=q*article.costo_administracion,stock_id=article.id,serial=serial)

def apply_sale(op):
    for c in op.costs:
        if c.get('stock_id'):
            a=get_id(ArticuloStock,c['stock_id'])
            movement(a,-c['quantity'],c['unit'],'Venta en Finanzas',operation=op.id,serial=c.get('serial'))

def reverse_sale(op,reason):
    # Un evento compensatorio conserva el registro de la salida.
    rows=db.session.scalars(db.select(MovimientoStock).where(MovimientoStock.operacion_id==op.id)).all()
    if any(r.cantidad>0 for r in rows):raise ValueError('El inventario de esta venta ya fue reintegrado.')
    for r in rows:
        unit=db.session.get(UnidadStock,r.unidad_id) if r.unidad_id else None
        movement(get_id(ArticuloStock,r.articulo_id),-r.cantidad,r.costo_unitario,'Anulación: '+reason,
            operation=op.id,serial=unit.serial if unit else None)
