from decimal import Decimal, InvalidOperation
from ..extensions import db
from ..models.lote import Lote
from ..models import Producto
from .catalogo_service import get_item
from .operacion_service import today, day


def create_lot(data):
    supplier = get_item(data.get('supplier_id'), 'supplier')
    if not supplier or not supplier.active:
        raise ValueError('Selecciona un proveedor activo.')
    entry = day(data.get('entry_date') or today())
    if entry > today():
        raise ValueError('La fecha de ingreso no puede estar en el futuro.')
    note = data.get('note', '').strip()
    if len(note) > 500 or (entry != today() and len(note) < 3):
        raise ValueError('Indica el motivo si cambias la fecha (máximo 500 caracteres).')
    try:
        rate = Decimal(data.get('exchange_rate', ''))
        count = int(data.get('expected_count', ''))
        if not rate.is_finite() or not 0 < rate <= 1000000 or rate.as_tuple().exponent < -2 or not 1 <= count <= 10000:
            raise ValueError()
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Ingresa una tasa positiva con hasta 2 decimales y una cantidad de 1 a 10.000 equipos.')
    lot = Lote(entry_date=entry, supplier_id=supplier.id, exchange_rate=str(rate), expected_count=count, note=note)
    db.session.add(lot)
    db.session.commit()
    return lot


def get_lot(value):
    try:
        return db.session.get(Lote, int(value))
    except (ValueError, TypeError):
        return None


def list_lots():
    result = []
    for lot in db.session.scalars(db.select(Lote).order_by(Lote.id.desc())):
        products = db.session.scalars(db.select(Producto).where(Producto.lot_id == lot.id)).all()
        result.append(dict(lot=lot, count=len(products), available=sum(p.status == 'Disponible' and not p.archived for p in products),
                           sold=sum((p.status == 'Vendido' or (p.status == 'Garantía' and p.warranty_previous == 'Vendido')) and not p.archived for p in products),
                           other=sum(p.status not in ('Disponible','Vendido') and not (p.status == 'Garantía' and p.warranty_previous == 'Vendido') and not p.archived for p in products),
                           archived=sum(bool(p.archived) for p in products),
                           total=sum(p.cost_cents for p in products)))
    return result
