from sqlalchemy import func
from datetime import datetime
from app.models.contabilidad import ConsignacionBancaria, PersonaContable
from app.extensions import db

# Tope de consignaciones bancarias fijado por la DIAN en 1.400 UVT
# (Para vigencia actual aprox. $69.719.000 COP, ajustable según la resolución de la vigencia)
TOPE_UVT_CONSIGNACIONES = 1400
VALOR_UVT_REF = 49799  # O el valor correspondiente al año gravable
TOPE_LIMITE_COP = TOPE_UVT_CONSIGNACIONES * VALOR_UVT_REF # ~$69.718.600

def evaluar_estado_renta(persona_id, anio=None):
    if not anio:
        anio = datetime.utcnow().year
        
    # Sumar todas las consignaciones del individuo en el año fiscal
    total_consignado = db.session.query(
        func.sum(ConsignacionBancaria.monto)
    ).filter(
        ConsignacionBancaria.persona_id == persona_id,
        func.extract('year', ConsignacionBancaria.fecha) == anio
    ).scalar() or 0.0
    
    monto_total = float(total_consignado)
    supera_tope = monto_total >= TOPE_LIMITE_COP
    porcentaje = min(round((monto_total / TOPE_LIMITE_COP) * 100, 2), 100)
    
    return {
        "total_consignado": monto_total,
        "tope_limite": TOPE_LIMITE_COP,
        "supera_tope": supera_tope,
        "porcentaje": porcentaje,      # <-- Clave requerida por la plantilla HTML
        "porcentaje_uso": porcentaje   # <-- Conservado por compatibilidad si lo usas en otro lado
    }