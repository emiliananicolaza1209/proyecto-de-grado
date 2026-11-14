from .gestion_comun import actor
"""Transiciones y dinero: una transacción por operación, con revisión optimista."""
import json
import secrets
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from sqlalchemy.orm.exc import StaleDataError
from ..extensions import db
from ..models import Producto, Movimiento
from .catalogo_service import get_item, CONDITIONS

COLOMBIA = timezone(timedelta(hours=-5))
def today():
    return datetime.now(COLOMBIA).date().isoformat()

def created_day(p):
    return datetime.fromisoformat(p.created_at).replace(tzinfo=timezone.utc).astimezone(COLOMBIA).date().isoformat() if p.created_at else ''

def money(raw):
    try:
        value = Decimal(str(raw))
        if not value.is_finite() or not 0 < value <= 999999999 or value != value.quantize(Decimal('.01')):
            raise ValueError()
        return int(value * 100)
    except (ValueError, InvalidOperation, OverflowError):
        raise ValueError('Ingresa un importe positivo de hasta $999.999.999 con máximo dos decimales.')

def day(raw):
    try:
        value = datetime.strptime(raw, '%Y-%m-%d').date()
        if value.isoformat() != raw: raise ValueError()
        return raw
    except (TypeError, ValueError):
        raise ValueError('La fecha debe ser válida y tener formato año-mes-día.')

ALLOWED = {
    'Disponible': [('handoff','Entregar equipo'),('reserve','Crear separado'),('sell','Confirmar venta'),('warranty','Ingresar a garantía')],
    'En pasamano': [('return','Registrar devolución'),('sell','Confirmar venta')],
    'Separado': [('payment','Registrar abono'),('sell','Convertir en venta'),('cancel','Cancelar separado sin cobros')],
    'Vendido': [('payment','Registrar cobro del cliente'),('edit_sale','Corregir venta'),('reverse_sale','Anular venta y volver a disponible'),('warranty','Ingresar a garantía')],
    'Garantía': [('close_warranty','Cerrar garantía')],
}

def operate(pid, action, data):
    if action == 'payment':
        from .pago_service import collect
        return collect(pid, data)
    p = db.session.get(Producto, pid)
    if not p: raise ValueError('El equipo no existe.')
    if p.archived or str(p.revision) != data.get('revision'):
        raise ValueError('Equipo eliminado o modificado en otra ventana. Recarga la página.')
    if action != 'correct_date' and action not in [a for a,_ in ALLOWED.get(p.status,[])]:
        raise ValueError('Esta operación no está permitida en el estado actual.')
    reason = data.get('reason','').strip()
    if not 3 <= len(reason) <= 500: raise ValueError('Indica un motivo de entre 3 y 500 caracteres.')
    effective = day(data.get('movement_date') or today())
    if effective > today(): raise ValueError('Un movimiento realizado no puede tener fecha futura.')
    baseline = p.movement_date or created_day(p)
    if action != 'correct_date' and baseline and effective < baseline: raise ValueError('La fecha no puede ser anterior al último movimiento.')
    correction = data.get('date_reason','').strip()
    if (effective != today() or action=='correct_date') and not 3 <= len(correction) <= 500:
        raise ValueError('Explica por qué el movimiento se registra con otra fecha.')
    before = p.to_dict()
    values = dict(movement_date=effective, last_note=reason)
    if action == 'handoff':
        values['loan_date'] = effective
        handler = ' '.join(data.get('loan_handler','').upper().split())
        if not 2 <= len(handler) <= 120:
            raise ValueError('Indica la vendedora encargada del pasamano.')
        values['loan_handler'] = handler
        values['loan_price_cents'] = money(data['loan_price']) if data.get('loan_price','').strip() else None
    if action == 'sell':
        seller = data.get('seller','').strip().upper()
        if not 2 <= len(seller) <= 120:
            raise ValueError('Indica quién realizó la venta (entre 2 y 120 caracteres).')
        person_id=data.get('person_id','').strip()
        if person_id:
            from ..models import PersonaContable
            try: person_id=int(person_id)
            except ValueError: raise ValueError('Selecciona una persona del registro contable.')
            if not db.session.get(PersonaContable,person_id): raise ValueError('La persona no existe en información contable.')
        values.update(seller=seller, sale_date=effective,person_id=person_id or None)
    if action == 'edit_sale':
        from ..models.finanzas import Jornada, OperacionFinanciera, AuditoriaFinanciera
        amount=money(data.get('sale_value'))
        if amount<p.paid_cents:raise ValueError('El precio corregido no puede ser inferior a los cobros vigentes.')
        seller=' '.join(data.get('seller','').upper().split())
        if not 2<=len(seller)<=120:raise ValueError('Indica el vendedor de esta venta.')
        responsible=' '.join(data.get('responsible','').upper().split())
        if not 2<=len(responsible)<=120:raise ValueError('Indica la persona o negocio responsable.')
        linked=db.session.scalar(db.select(OperacionFinanciera).where(OperacionFinanciera.product_id==pid))
        if linked:
            finance_day=db.session.get(Jornada,linked.day_id)
            if finance_day.status!='Abierta':raise ValueError('Reabre primero la jornada cerrada para corregir esta venta.')
            from ..models.gestion import CreditoVenta,ResultadoSocio
            if db.session.scalar(db.select(CreditoVenta.id).where(CreditoVenta.operacion_id==linked.id)):
                raise ValueError('Esta venta tiene un crédito asociado. Conserva su contrato y corrige desde Finanzas.')
            before_finance={'amount':linked.amount,'seller':linked.seller}
            linked.amount=amount;linked.seller=seller
            from .sociedad_service import refresh_result
            refresh_result(linked,reason)
            finance_day.revision+=1
            db.session.add(AuditoriaFinanciera(day_id=finance_day.id,action='Corrección de venta MOD03',
                reason=reason,detail={'product_id':pid,'operation_id':linked.id,'before':before_finance,
                    'after':{'amount':amount,'seller':seller}}))
        person_id=data.get('person_id','').strip()
        if person_id:
            from ..models import PersonaContable
            try: person_id=int(person_id)
            except ValueError: raise ValueError('Selecciona una persona del registro contable.')
            if not db.session.get(PersonaContable,person_id): raise ValueError('La persona no existe en información contable.')
        if linked:
            linked.person_id=person_id or None
        values.update(sale_value_cents=amount,seller=seller,responsible=responsible,person_id=person_id or None,
                      payment_status='Pagado' if amount==p.paid_cents else 'Parcial' if p.paid_cents else 'Pendiente')
    if action=='correct_date':
        event = db.session.scalar(db.select(Movimiento).where(Movimiento.product_id==pid, Movimiento.action.notin_(['Corrección de fecha','Edición','Traslado','Eliminación del inventario','Restauración'])).order_by(Movimiento.id.desc()))
        if not event: raise ValueError('No hay un movimiento para corregir.')
        if event.action in ('Cobro del cliente','Recepción en administración','Anulación de cobro','Anulación de recepción'):
            raise ValueError('Corrige el registro de dinero desde su historial: anúlalo y vuelve a registrarlo con la fecha correcta.')
        previous = json.loads(event.before_data).get('movement_date') or created_day(p)
        if previous and effective < previous: raise ValueError('La corrección no puede preceder al movimiento anterior.')
        if p.due_date and effective > p.due_date: raise ValueError('La corrección supera la fecha límite.')
        if event.action in ('Registrar abono','Registrar cobro del cliente'):
            values['payment_date']=effective
        elif event.action=='Entregar equipo':
            values['loan_date']=effective
        elif event.action in ('Confirmar venta','Convertir en venta'):
            values['sale_date']=effective
    if action in ('handoff','reserve'):
        responsible = ' '.join(data.get('responsible','').upper().split())
        if not 2 <= len(responsible) <= 120: raise ValueError('Indica un responsable de 2 a 120 caracteres.')
        due = day(data.get('due_date',''))
        if due < effective: raise ValueError('La fecha límite debe ser posterior o igual a la salida.')
        values.update(responsible=responsible,due_date=due)
        if action == 'handoff':
            purpose = data.get('purpose')
            if purpose not in ('Venta','Reemplazo por garantía','Otro'): raise ValueError('Selecciona el propósito del préstamo.')
            values.update(status='En pasamano',purpose=purpose)
        else:
            values.update(status='Separado',sale_value_cents=money(data.get('sale_value')),paid_cents=0,payment_status='Pendiente')
    elif action in ('return','close_warranty'):
        target = get_item(data.get('location_id'),'location')
        if not target or not target.active: raise ValueError('Selecciona una bodega de recepción activa.')
        condition = data.get('condition')
        if condition not in CONDITIONS: raise ValueError('Selecciona la condición recibida.')
        battery = data.get('battery','').strip()
        if battery and (not battery.isascii() or not battery.isdigit() or not 0 <= int(battery) <= 100):
            raise ValueError('La batería debe estar entre 0 y 100, o vacía si no aplica.')
        target_status = data.get('return_condition','Disponible')
        if target_status not in ('Disponible','Garantía'): raise ValueError('Selecciona un resultado válido.')
        if action == 'close_warranty': target_status = p.warranty_previous or 'Disponible'
        values.update(status=target_status,location_id=target.id,location=target.name,condition=condition,battery=int(battery) if battery else None)
        if action == 'return': values.update(responsible=None,purpose=None,due_date=None,loan_handler=None,loan_price_cents=None,warranty_previous='Disponible' if target_status=='Garantía' else None)
        else: values['warranty_previous']=None
    elif action == 'sell':
        if p.status == 'En pasamano' and p.purpose != 'Venta': raise ValueError('Devuelve el préstamo de reemplazo antes de vender el equipo.')
        amount = money(data.get('sale_value'))
        if amount < p.paid_cents: raise ValueError('La venta no puede ser menor que los abonos.')
        responsible = data.get('responsible','').strip().upper() or p.responsible
        if not responsible or len(responsible)>120: raise ValueError('Indica el vendedor responsable.')
        values.update(status='Vendido',sale_value_cents=amount,responsible=responsible,due_date=None,purpose=None,
                      payment_status='Pagado' if p.paid_cents==amount else 'Parcial' if p.paid_cents else 'Pendiente')
    elif action == 'reverse_sale':
        from ..models import Cobro
        from ..models.finanzas import Jornada, OperacionFinanciera, PagoProveedor, AuditoriaFinanciera
        if p.paid_cents or db.session.scalar(db.select(Cobro.id).where(Cobro.product_id==pid,Cobro.voided==False)):
            raise ValueError('La venta tiene cobros. Concilia y anula los cobros antes de anular la venta; la anulación no devuelve dinero automáticamente.')
        linked=db.session.scalar(db.select(OperacionFinanciera).where(OperacionFinanciera.product_id==pid,OperacionFinanciera.voided==False))
        if linked:
            finance_day=db.session.get(Jornada,linked.day_id)
            if finance_day.status!='Abierta':raise ValueError('Reabre la jornada financiera de la venta antes de anularla.')
            if any(x['account']!='CRÉDITO' for x in linked.payments) or db.session.scalar(db.select(PagoProveedor.id).where(PagoProveedor.operation_id==linked.id)):
                raise ValueError('La venta tiene pagos vinculados en Finanzas. Concílialos antes de anularla.')
            from ..models.gestion import AplicacionLiquidacion,ResultadoSocio,ComisionPool
            if db.session.scalar(db.select(AplicacionLiquidacion.id).join(ResultadoSocio,ResultadoSocio.id==AplicacionLiquidacion.resultado_id).where(ResultadoSocio.operacion_id==linked.id)):
                raise ValueError('Hay pagos a socios asociados a esta venta.')
            if db.session.scalar(db.select(ComisionPool.id).where(ComisionPool.operacion_id==linked.id,ComisionPool.pago_operacion_id.is_not(None))):
                raise ValueError('La comisión extra del POOL ya fue entregada. Concilia el reintegro antes de anular.')
            from .credito_service import cancel_unreceived
            from .stock_service import reverse_sale
            cancel_unreceived(linked,reason);reverse_sale(linked,reason)
            linked.voided=True;linked.product_id=None;finance_day.revision+=1
            db.session.add(AuditoriaFinanciera(day_id=finance_day.id,action='Anulación de venta MOD03',reason=reason,
                detail={'product_id':pid,'operation_id':linked.id,'amount':linked.amount}))
        values.update(status='Disponible',sale_date=None,sale_value_cents=None,paid_cents=0,payment_status='No aplica',
                      payment_date=None,responsible=None,seller=None,person_id=None,due_date=None,purpose=None,
                      loan_handler=None,loan_price_cents=None,pool_assigned_cost_cents=None,pool_admin_gain_cents=0)
    elif action == 'cancel':
        from ..models import Cobro
        if db.session.scalar(db.select(Cobro.id).where(Cobro.product_id==pid,Cobro.voided==False)):
            raise ValueError('Este separado tiene cobros registrados. El reembolso y la cancelación con dinero requieren conciliación; no se borrarán los cobros.')
        if p.paid_cents: raise ValueError('Concilia los abonos antes de cancelar el separado.')
        values.update(status='Disponible',paid_cents=0,sale_value_cents=None,payment_status='No aplica',payment_date=None,responsible=None,due_date=None)
    elif action == 'warranty':
        values.update(status='Garantía',warranty_previous=p.status)
    try:
        for k,v in values.items(): setattr(p,k,v)
        if action=='sell':
            from ..models.finanzas import Jornada, OperacionFinanciera
            from .finanzas_service import incorporate
            finance_day=db.session.scalar(db.select(Jornada).where(Jornada.date==p.sale_date))
            if finance_day and finance_day.status=='Abierta' and not db.session.scalar(
                    db.select(OperacionFinanciera.id).where(OperacionFinanciera.product_id==pid)):
                incorporate(finance_day,pid,secrets.token_hex(16))
                finance_day.revision+=1
        # Incrementa incluso si un movimiento solo añade una observación.
        p.revision += 1
        db.session.flush()
        db.session.add(Movimiento(product_id=pid,action='Corrección de fecha' if action=='correct_date' else dict(ALLOWED[before['status']])[action],
            reason=reason + (' | Motivo de fecha: '+correction if correction else ''),
            actor=actor(),before_data=json.dumps(before,ensure_ascii=False),after_data=json.dumps(p.to_dict(),ensure_ascii=False)))
        db.session.commit()
    except StaleDataError:
        db.session.rollback()
        raise ValueError('Otro proceso modificó el equipo. Recarga antes de continuar.')
    return p
