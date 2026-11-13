"""Alertas por reglas, con seguimiento auditable en registro_gestion existente."""
from datetime import date, datetime, timezone
from ..extensions import db
from ..models import Producto
from ..models.gestion import RegistroGestion, ArticuloStock, CreditoVenta
from ..models.finanzas import OperacionFinanciera
from .gestion_comun import audit
from .operacion_service import today, created_day
from .stock_service import balance


def config():
    row=db.session.scalar(db.select(RegistroGestion).where(RegistroGestion.entidad=='config_alertas').order_by(RegistroGestion.id.desc()).limit(1))
    return row.datos if row else {'dias_inventario':30}


def settings(days, reason):
    try:days=int(days)
    except (ValueError,TypeError):raise ValueError('El umbral debe ser un número entero.')
    if not 1<=days<=3650:raise ValueError('Usa entre 1 y 3650 días.')
    if len(reason.strip())<3:raise ValueError('Explica el cambio del umbral.')
    audit('config_alertas',0,'Configurar alertas',{'dias_inventario':days},reason)


def alerts():
    rows=[];threshold=config()['dias_inventario']
    for a in db.session.scalars(db.select(ArticuloStock).where(ArticuloStock.activo==True)):
        n=balance(a.id)
        if n<=a.minimo:
            rows.append(dict(key='stock:'+str(a.id),tipo='Stock bajo',descripcion=a.nombre,
                             detalle=f'{n} unidades; mínimo {a.minimo}.',recomendacion='Revisar compras y ajustar reposición según demanda, antes de comprometer ventas.'))
    for p in db.session.scalars(db.select(Producto).where(Producto.archived==0,Producto.status=='Disponible')):
        try:
            entry=p.lot.entry_date if p.lot else created_day(p)
            age=(date.fromisoformat(today())-date.fromisoformat(entry[:10])).days
        except (ValueError,TypeError):continue
        if age>=threshold:
            rows.append(dict(key='edad:'+str(p.id),tipo='Permanencia en inventario',descripcion=p.model,
                             detalle=f'Equipo #{p.id}: {age} días desde ingreso.',recomendacion='Revisar precio y demanda. La antigüedad no demuestra por sí sola baja rotación histórica.'))
    for c in db.session.scalars(db.select(CreditoVenta).join(OperacionFinanciera,OperacionFinanciera.id==CreditoVenta.operacion_id).where(
            OperacionFinanciera.voided==False,CreditoVenta.estado!='Anulado',CreditoVenta.neto>CreditoVenta.recibido)):
        rows.append(dict(key='credito:'+str(c.id),tipo='Crédito pendiente',descripcion=f'Crédito #{c.id}',
                         detalle=f'Saldo actual: {(c.neto-c.recibido)/100:,.2f} COP. No implica mora.',
                         recomendacion='Revisar la recepción con el aliado; registrar desembolso solo cuando esté confirmado.'))
    for c in db.session.scalars(db.select(RegistroGestion).where(RegistroGestion.entidad=='estado_alerta').order_by(RegistroGestion.id)):
        key=c.datos.get('key')
        for row in rows:
            if row['key']==key:row.update(estado=c.datos['estado'],motivo=c.motivo,responsable=c.actor)
    for row in rows:row.setdefault('estado','Pendiente')
    return rows


def transition(key, state, reason):
    if state not in ('Pendiente','En revisión','Cerrada'):raise ValueError('Estado inválido.')
    if len(reason.strip())<3 or len(reason)>500:raise ValueError('Registra un motivo de 3 a 500 caracteres.')
    if key not in {r['key'] for r in alerts()}:raise ValueError('La condición ya no está activa. Recarga las alertas.')
    audit('estado_alerta',0,'Cambiar estado',{'key':key,'estado':state},reason)


def consult(tool,args):
    from . import reportes_service as r
    if tool=='ventas':return r.sales(args)
    if tool=='inventario':return r.inventory(dict(args,estado='Disponible'),False)
    if tool=='finanzas':return r.financial(args)
    if tool=='creditos':return r.credits(args)
    raise ValueError('Selecciona una de las cuatro consultas permitidas.')
