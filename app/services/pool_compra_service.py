"""Compra iniciada en el local: equipo, movimiento y revisión en una transacción.

Los pendientes se obtienen del último evento de revisión del historial existente.
No se altera el esquema ni se modifica el historial de compras anteriores.
"""
import json
from ..extensions import db
from ..models import Producto, Movimiento
from ..models.finanzas import OperacionFinanciera as Op
from ..models.gestion import RegistroGestion
from . import finanzas_service as finance
from .gestion_comun import audit

ENTITY = 'revision_compra_pool'


def register(day, form, buyer):
    finance.editable(day, form.get('revision'))
    if not day.config.get('reviewed'):
        raise ValueError('Confirma primero Personal y reglas.')
    token = form.get('token', '')
    if len(token) != 32 or db.session.scalar(db.select(Op.id).where(Op.token == token)):
        raise ValueError('Esta compra ya fue registrada o el formulario venció.')
    buyer = finance.text(buyer)
    paid = finance.money(form.get('purchase_cop'))
    gain = finance.money(form.get('purchase_gain'))
    commission = finance.money(form.get('purchase_commission') or '0')
    other = finance.money(form.get('purchase_other') or '0')
    funding = finance.money(form.get('funding'))
    if paid <= 0 or funding != paid + gain + commission + other:
        raise ValueError('El aporte total debe ser igual al pago al cliente + ganancia del local + comisión de compra + otros costos.')
    if form.get('confirmed') != '1':
        raise ValueError('Confirma el aporte recibido y los pagos efectuados antes de registrar la compra.')
    names, amounts = [], []
    if commission:
        names.append('COMISIÓN DE COMPRA POOL');amounts.append(str(commission // 100) + '.' + str(commission % 100).zfill(2))
    if other:
        names.append(finance.text(form.get('purchase_other_detail'), True, 120))
        amounts.append(str(other // 100) + '.' + str(other % 100).zfill(2))
    data = {key: form.get(key, '') for key in ('imei', 'brand_id', 'reference_id', 'capacity_id', 'color_id', 'location_id')}
    data.update(entry_type='Retoma', condition='Usado', purchase_cop=str(paid//100)+'.'+str(paid%100).zfill(2),
                additional_name=names, additional_amount=amounts)
    from .inventario_service import register_product
    from .sociedad_service import register_purchase
    from werkzeug.datastructures import MultiDict
    product = register_product(data, commit=False)
    # La nueva compra es directa; las partes de pago anteriores mantienen su flujo.
    purchase = register_purchase(product, MultiDict(dict(date=day.date, funding=form.get('funding'),
        confirmed='1', purchase_mode='Compra directa')), buyer=buyer, token=token)
    db.session.add(Movimiento(product_id=product.id, action='Compra POOL', actor=buyer,
        reason='Compra registrada en la jornada '+day.date,
        before_data='{}', after_data=json.dumps(product.to_dict(), ensure_ascii=False)))
    audit(ENTITY, product.id, 'Pendiente', {'operacion_id': purchase.operacion_id,
        'compradora': buyer, 'fecha_compra': day.date}, 'Revisar datos adicionales del equipo comprado en el local')
    finance.audit(day, 'Compra POOL', 'Alta de equipo y compra en el local',
        {'producto_id': product.id, 'operacion_id': purchase.operacion_id, 'compradora': buyer,
         'cliente': paid, 'ganancia': gain, 'subtotal_compra': paid+gain,
         'comision_compra': commission, 'otros_costos': other, 'aporte_total': funding})
    return product


def pending(product_id=None):
    latest = db.select(RegistroGestion.entidad_id, db.func.max(RegistroGestion.id).label('id')).where(
        RegistroGestion.entidad == ENTITY).group_by(RegistroGestion.entidad_id).subquery()
    query = db.select(RegistroGestion, Producto).join(latest, latest.c.id == RegistroGestion.id).join(
        Producto, Producto.id == RegistroGestion.entidad_id).where(RegistroGestion.accion == 'Pendiente')
    if product_id is not None:query = query.where(Producto.id == product_id)
    return db.session.execute(query.order_by(RegistroGestion.id.desc())).all()


def review(product_id, event_id, note):
    rows = pending(product_id)
    if not rows or str(rows[0][0].id) != str(event_id):
        raise ValueError('Esta revisión ya fue resuelta o cambió. Recarga la página.')
    event, product = rows[0]
    note = finance.text(note, True, 500)
    audit(ENTITY, product.id, 'Revisada', dict(event.datos, pendiente_id=event.id), note)
    # Solo cierra el pendiente: no cambia dinero, disponibilidad ni cierres.
    db.session.flush()
