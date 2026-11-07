"""Indicadores operativos del inicio; no expone costos ni rentabilidad."""
from sqlalchemy import select, func
from ..extensions import db
from ..models import Producto
from .operacion_service import today


def operational_summary():
    current_day = today()
    base=Producto.archived == 0
    counts=dict(db.session.execute(select(Producto.status,func.count(Producto.id))
                .where(base).group_by(Producto.status)).all())
    overdue_filter=(base,Producto.status.in_(('En pasamano','Separado')),
                    Producto.due_date.is_not(None),Producto.due_date<current_day)
    pending_filter=(base,Producto.status.in_(('Vendido','Garantía')),
                    Producto.sale_value_cents.is_not(None),
                    Producto.sale_value_cents>Producto.paid_cents)
    overdue_count=db.session.scalar(select(func.count(Producto.id)).where(*overdue_filter)) or 0
    pending_count=db.session.scalar(select(func.count(Producto.id)).where(*pending_filter)) or 0
    overdue=db.session.scalars(select(Producto).where(*overdue_filter).order_by(Producto.due_date,Producto.id).limit(6)).all()
    pending=db.session.scalars(select(Producto).where(*pending_filter).order_by(Producto.id.desc()).limit(6)).all()
    recent=db.session.scalars(select(Producto).where(base).order_by(Producto.id.desc()).limit(6)).all()
    return dict(available=counts.get('Disponible',0),loaned=counts.get('En pasamano',0),
                sold=counts.get('Vendido',0),overdue=overdue,overdue_count=overdue_count,
                pending=pending,pending_count=pending_count,recent=recent,date=current_day)
