"""Lecturas del POOL dentro de la jornada, sin duplicar compras ni ventas."""
from sqlalchemy.orm import aliased
from ..extensions import db
from ..models import Producto
from ..models.finanzas import Jornada, OperacionFinanciera as Op
from ..models.gestion import CompraPool, ComisionPool, Sociedad


def context(day):
    purchases = db.session.execute(
        db.select(CompraPool, Producto).join(Producto, Producto.id == CompraPool.producto_id)
        .join(Op, Op.id == CompraPool.operacion_id).join(Jornada, Jornada.id == Op.day_id)
        .where(Jornada.date == day).order_by(Op.id.desc())).all()
    candidates = db.session.scalars(
        db.select(Producto).where(Producto.source_type == 'Retoma', Producto.status == 'Disponible',
            Producto.archived == 0, ~Producto.id.in_(db.select(CompraPool.producto_id)))
        .order_by(Producto.model, Producto.imei)).all()
    sale_candidates = db.session.execute(
        db.select(Op, Jornada.date).join(Jornada, Jornada.id == Op.day_id)
        .where(Op.kind == 'Venta', Op.voided == False, Jornada.date <= day)
        .order_by(Jornada.date.desc(), Op.id.desc())).all()
    sales = [(op, date) for op, date in sale_candidates
             if any(p.get('account') == 'RETOMA' for p in op.payments)]
    paid_op, paid_day = aliased(Op), aliased(Jornada)
    commissions = db.session.execute(
        db.select(ComisionPool, Jornada.date, paid_day.date)
        .join(Op, Op.id == ComisionPool.operacion_id).join(Jornada, Jornada.id == Op.day_id)
        .outerjoin(paid_op, paid_op.id == ComisionPool.pago_operacion_id)
        .outerjoin(paid_day, paid_day.id == paid_op.day_id)
        .where(Op.voided == False, Jornada.date <= day,
               db.or_(ComisionPool.pago_operacion_id.is_(None), paid_day.date == day))
        .order_by(Jornada.date, ComisionPool.id)).all()
    return dict(candidates=candidates, purchases=purchases, sales=sales, commissions=commissions,
                societies=db.session.scalars(db.select(Sociedad).where(Sociedad.activa == True)
                                            .order_by(Sociedad.nombre)).all())
