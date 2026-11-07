"""Conciliación idempotente de medios bancarios de Finanzas con Contabilidad."""
from datetime import datetime
from decimal import Decimal

from ..extensions import db
from ..models.contabilidad import BancoDestino, ConsignacionBancaria, HistorialConsignacion, PersonaContable
from .personas_contables import banco_de_persona

BANCARIOS = ('TRANSFERENCIA', 'DATÁFONO')


def destino(persona, banco, account='TRANSFERENCIA'):
    try:
        persona_id = int(persona)
    except (ValueError, TypeError):
        raise ValueError('Selecciona la persona titular de la transferencia o el datáfono.')
    if not db.session.get(PersonaContable, persona_id):
        raise ValueError('La persona ya no existe en Información contable.')
    if account=='DATÁFONO':return persona_id,None
    try:bank_id=int(banco)
    except (ValueError, TypeError):raise ValueError('Selecciona el banco destino de la transferencia.')
    if not db.session.get(BancoDestino, bank_id):
        raise ValueError('La persona o el banco ya no existe en Información contable.')
    if not banco_de_persona(persona_id,bank_id):
        raise ValueError('El banco no está asociado a esa persona. Abre Información contable y agrégalo a su ficha.')
    return persona_id, bank_id


def _datos(c):
    return dict(persona_id=c.persona_id, banco_id=c.banco_id, monto=str(c.monto),
                fecha=c.fecha.isoformat(), referencia=c.referencia, activa=c.activa)


def _update(c, person_id, bank_id, amount, day, reference, active):
    before=_datos(c) if c else None
    if c is None:
        c=ConsignacionBancaria()
        db.session.add(c)
    c.persona_id=person_id;c.banco_id=bank_id;c.monto=Decimal(amount)/100
    c.fecha=datetime.fromisoformat(day);c.referencia=reference[:100];c.activa=active
    if before!=_datos(c):
        db.session.flush()
        db.session.add(HistorialConsignacion(consignacion_id=c.id,accion='Sincronización',
            motivo='Medio bancario registrado o corregido en Finanzas',antes=before,despues=_datos(c)))
    return c


def sincronizar_operacion(day, operation):
    existing={c.payment_index:c for c in db.session.scalars(db.select(ConsignacionBancaria).where(
        ConsignacionBancaria.finance_operation_id==operation.id))}
    for index,payment in enumerate(operation.payments):
        if payment['account'] not in BANCARIOS:
            continue
        person_id,bank_id=destino(payment.get('person_id'),payment.get('bank_id'),payment['account'])
        c=_update(existing.pop(index,None),person_id,bank_id,payment['amount'],day,
                  f'FINANZAS {operation.id} / MEDIO {index+1}',not operation.voided)
        c.finance_operation_id=operation.id;c.payment_index=index
    for c in existing.values():
        if c.activa:
            before=_datos(c);c.activa=False
            db.session.add(HistorialConsignacion(consignacion_id=c.id,accion='Anulación',
                motivo='Medio bancario retirado o movimiento anulado en Finanzas',antes=before,despues=_datos(c)))


def sincronizar_pago(day, payment):
    if payment.account not in BANCARIOS:
        previous=db.session.scalar(db.select(ConsignacionBancaria).where(ConsignacionBancaria.supplier_payment_id==payment.id))
        if previous and previous.activa:
            before=_datos(previous);previous.activa=False
            db.session.add(HistorialConsignacion(consignacion_id=previous.id,accion='Anulación',
                motivo='Pago a proveedor corregido a efectivo',antes=before,despues=_datos(previous)))
        return
    person_id,bank_id=destino(payment.person_id,payment.bank_id,payment.account)
    existing=db.session.scalar(db.select(ConsignacionBancaria).where(ConsignacionBancaria.supplier_payment_id==payment.id))
    c=_update(existing,person_id,bank_id,payment.amount,day,f'PAGO PROVEEDOR {payment.id}',True)
    c.supplier_payment_id=payment.id
