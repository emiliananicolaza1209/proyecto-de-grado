"""Cobros y entregas separados, importes en centavos e historial transaccional."""
import json
from sqlalchemy.orm.exc import StaleDataError
from ..extensions import db
from ..models import Producto, Movimiento, Cobro, Recepcion

METHODS = ('Efectivo', 'Transferencia', 'Tarjeta', 'Otro')


def collections(pid):
    result = []
    for c in db.session.scalars(db.select(Cobro).where(Cobro.product_id == pid).order_by(Cobro.id.desc())):
        receipts = db.session.scalars(db.select(Recepcion).where(Recepcion.collection_id == c.id).order_by(Recepcion.id.desc())).all()
        received = sum(r.amount_cents for r in receipts if not r.voided)
        result.append(dict(collection=c, receipts=receipts, received=received,
                           pending=0 if c.voided else c.amount_cents-received))
    return result


def summary(p):
    rows = collections(p.id)
    active = [r for r in rows if not r['collection'].voided]
    total = sum(r['collection'].amount_cents for r in active)
    received = sum(r['received'] for r in active)
    unknown = sum(r['pending'] for r in active if r['collection'].legacy)
    seller_pending = sum(r['pending'] for r in active if r['collection'].destination == 'Vendedora')
    direct_pending = sum(r['pending'] for r in active if r['collection'].destination == 'Negocio')
    return dict(rows=rows, total=total, received=received, pending=total-received,
                seller_pending=seller_pending, direct_pending=direct_pending, unknown=unknown,
                client_due=None if p.sale_value_cents is None or p.payment_status=='Por verificar' else p.sale_value_cents-p.paid_cents,
                inconsistent=total != p.paid_cents)


def context(pid, data):
    from .operacion_service import today, day, created_day
    p = db.session.get(Producto, pid)
    if not p or p.archived:
        raise ValueError('El equipo no existe o fue retirado.')
    if str(p.revision) != data.get('revision'):
        raise ValueError('Los importes cambiaron en otra ventana. Recarga antes de guardar.')
    note = data.get('reason','').strip()
    if not 3 <= len(note) <= 500:
        raise ValueError('Indica una observación de 3 a 500 caracteres.')
    effective = day(data.get('movement_date') or today())
    if effective > today() or effective < created_day(p):
        raise ValueError('La fecha no puede ser futura ni anterior al ingreso del equipo.')
    correction = data.get('date_reason','').strip()
    if effective != today() and not 3 <= len(correction) <= 500:
        raise ValueError('Explica el cambio de fecha automática.')
    if correction:
        note += ' | Motivo de fecha: '+correction[:500]
    return p, note, effective


def details(data):
    method = data.get('method')
    reference = data.get('reference','').strip()
    if method not in METHODS:
        raise ValueError('Selecciona el medio de pago.')
    if len(reference)>120 or (method in ('Transferencia','Tarjeta') and not reference):
        raise ValueError('Indica la referencia del comprobante (máximo 120 caracteres).')
    return method, reference


def finish(p, before, title, note, detail):
    after = p.to_dict()
    after['detalle_dinero'] = detail
    try:
        p.revision += 1
        db.session.add(Movimiento(product_id=p.id, action=title, reason=note,
            actor='Sesión local sin autenticación', before_data=json.dumps(before,ensure_ascii=False),
            after_data=json.dumps(after,ensure_ascii=False)))
        db.session.commit()
    except StaleDataError:
        db.session.rollback()
        raise ValueError('Otro proceso modificó el equipo. Recarga antes de continuar.')
    return p


def collect(pid, data):
    from .operacion_service import money
    p, note, effective = context(pid, data)
    if p.status not in ('Vendido','Separado') and not (p.status=='Garantía' and p.warranty_previous=='Vendido'):
        raise ValueError('Confirma la venta o el separado antes de registrar un cobro.')
    if p.payment_status=='Por verificar' or summary(p)['inconsistent']:
        raise ValueError('Los pagos anteriores requieren conciliación.')
    if p.movement_date and effective < p.movement_date:
        raise ValueError('El cobro no puede ser anterior al último movimiento comercial.')
    amount = money(data.get('amount'))
    if not p.sale_value_cents or amount > p.sale_value_cents-p.paid_cents:
        raise ValueError('El importe supera el saldo pendiente del cliente.')
    destination = data.get('destination')
    if destination not in ('Vendedora','Negocio'):
        raise ValueError('Indica si el dinero lo recibió una vendedora o llegó directamente al negocio.')
    collector = ' '.join(data.get('collector','').upper().split()) if destination=='Vendedora' else 'PAGO DIRECTO AL NEGOCIO'
    if not 2 <= len(collector) <= 120:
        raise ValueError('Indica el nombre de la vendedora que recibió este pago.')
    method, reference = details(data)
    before = p.to_dict()
    db.session.add(Cobro(product_id=pid,amount_cents=amount,destination=destination,
        collector=collector,method=method,reference=reference,effective_date=effective,note=note))
    p.paid_cents += amount
    p.payment_status = 'Pagado' if p.paid_cents==p.sale_value_cents else 'Parcial'
    p.payment_date = effective
    p.movement_date = effective
    p.last_note = note
    return finish(p,before,'Cobro del cliente',note,
                  dict(importe_cop=amount/100,recibido_por=collector,destino=destination,medio=method,fecha=effective,comprobante=reference))


def receive(pid, data):
    from .operacion_service import money
    p, note, effective = context(pid, data)
    try:
        cid=int(data.get('collection_id',''))
    except (ValueError,TypeError):
        raise ValueError('Selecciona un cobro del equipo.')
    row=next((r for r in collections(pid) if r['collection'].id==cid),None)
    if not row or row['collection'].voided or row['collection'].legacy:
        raise ValueError('El cobro no existe, fue anulado o requiere conciliación.')
    if summary(p)['inconsistent']:
        raise ValueError('Los pagos anteriores requieren conciliación.')
    if effective < row['collection'].effective_date:
        raise ValueError('La recepción no puede ser anterior al cobro.')
    amount=money(data.get('amount'))
    if amount > row['pending']:
        raise ValueError('El importe supera el dinero pendiente de recibir de este cobro.')
    administrator=' '.join(data.get('administrator','').upper().split())
    if not 2 <= len(administrator) <= 120:
        raise ValueError('Indica quién confirma la recepción en administración.')
    method,reference=details(data)
    before=p.to_dict()
    db.session.add(Recepcion(collection_id=cid,amount_cents=amount,administrator=administrator,
        method=method,reference=reference,effective_date=effective,note=note))
    # No incrementar paid_cents: este dinero ya fue contabilizado al cobrar al cliente.
    return finish(p,before,'Recepción en administración',note,
                  dict(cobro=cid,importe_cop=amount/100,administradora=administrator,medio=method,fecha=effective,comprobante=reference))


def void_record(pid, data, receipt=False):
    """Corrección de registro, no reembolso bancario ni cancelación de la venta."""
    p,note,effective=context(pid,data)
    try:
        record_id=int(data.get('record_id',''))
    except (ValueError,TypeError):
        raise ValueError('Registro inválido.')
    record=db.session.get(Recepcion if receipt else Cobro,record_id)
    c=db.session.get(Cobro,record.collection_id) if record and receipt else record
    if not c or c.product_id!=pid or record.voided or c.legacy:
        raise ValueError('Registro inexistente, anulado o anterior al control de cobros.')
    if effective < record.effective_date:
        raise ValueError('La corrección no puede ser anterior al registro.')
    if summary(p)['inconsistent']:
        raise ValueError('Los importes requieren conciliación.')
    if not receipt and any(not r.voided for r in db.session.scalars(db.select(Recepcion).where(Recepcion.collection_id==c.id))):
        raise ValueError('Primero corrige las recepciones asociadas a este cobro.')
    before=p.to_dict()
    record.voided=True
    if not receipt:
        p.paid_cents -= c.amount_cents
        p.payment_status='Pagado' if p.paid_cents==p.sale_value_cents else 'Parcial' if p.paid_cents else 'Pendiente'
        remaining=[r['collection'].effective_date for r in collections(pid) if not r['collection'].voided]
        p.payment_date=max(remaining,default=None)
    return finish(p,before,'Anulación de recepción' if receipt else 'Anulación de cobro',note,
                  dict(registro=record_id,importe_cop=record.amount_cents/100,fecha=effective))
