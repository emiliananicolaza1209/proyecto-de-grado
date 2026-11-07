"""Alertas de consignaciones por año gravable; no son dictámenes tributarios."""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import func
from app.models.contabilidad import ConsignacionBancaria, BancoDestino
from app.extensions import db

UVT_POR_ANIO = {2025: 49799, 2026: 52374}
TOPE_UVT_CONSIGNACIONES = 1400


def resumir_por_banco(personas, anio):
    """Distribución anual de las mismas consignaciones activas del total personal.

    Conserva bancos asociados sin ingresos y bancos con movimientos históricos,
    aunque ya no estén asociados. Los movimientos sin banco forman un grupo
    separado: no se les asigna un banco ni se excluyen del total.
    """
    grupos = {
        p.id: {
            link.banco_id: dict(banco_id=link.banco_id, nombre=link.banco.nombre,
                                total=Decimal('0.00'), cantidad=0)
            for link in p.bancos_asociados
        } for p in personas
    }
    if not grupos:
        return {}
    inicio, fin = datetime(anio, 1, 1), datetime(anio + 1, 1, 1)
    registros = db.session.execute(
        db.select(ConsignacionBancaria.persona_id, ConsignacionBancaria.banco_id,
                  BancoDestino.nombre, func.sum(ConsignacionBancaria.monto),
                  func.count(ConsignacionBancaria.id))
        .outerjoin(BancoDestino, BancoDestino.id == ConsignacionBancaria.banco_id)
        .where(ConsignacionBancaria.persona_id.in_(grupos),
               ConsignacionBancaria.activa == True,
               ConsignacionBancaria.fecha >= inicio, ConsignacionBancaria.fecha < fin)
        .group_by(ConsignacionBancaria.persona_id, ConsignacionBancaria.banco_id,
                  BancoDestino.nombre)
    )
    for persona_id, banco_id, nombre, monto, cantidad in registros:
        grupos[persona_id][banco_id] = dict(
            banco_id=banco_id, nombre=nombre or 'Ingresos sin banco asociado',
            total=monto or Decimal('0.00'), cantidad=cantidad)
    resultado = {}
    for persona_id, bancos in grupos.items():
        total = sum((b['total'] for b in bancos.values()), Decimal('0.00'))
        for b in bancos.values():
            b['porcentaje'] = ((b['total'] * 100 / total).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP) if total else Decimal('0.00'))
            b['ancho'] = min(Decimal(100), max(Decimal(0), b['porcentaje']))
        resultado[persona_id] = dict(total=total, bancos=sorted(
            bancos.values(), key=lambda b: (b['banco_id'] is None, -b['total'], b['nombre'].casefold())))
    return resultado


def evaluar_estado_renta(persona_id, anio=None):
    anio = anio or datetime.now().year
    uvt = UVT_POR_ANIO.get(anio)
    inicio=datetime(anio,1,1);fin=datetime(anio+1,1,1)
    total = db.session.scalar(db.select(func.sum(ConsignacionBancaria.monto)).where(
        ConsignacionBancaria.persona_id==persona_id,
        ConsignacionBancaria.activa==True,
        ConsignacionBancaria.fecha>=inicio,ConsignacionBancaria.fecha<fin)) or Decimal(0)
    limite = int((Decimal(TOPE_UVT_CONSIGNACIONES * uvt)).quantize(
        Decimal('1E3'),rounding=ROUND_HALF_UP)) if uvt else None
    porcentaje = min(round(float(total / Decimal(limite)*100),2),100) if limite else 0
    return dict(total_consignado=total,tope_limite=limite,
                supera_tope=total>limite if limite else False,
                porcentaje=porcentaje,porcentaje_uso=porcentaje,
                pendiente_uvt=not bool(uvt),anio=anio)
