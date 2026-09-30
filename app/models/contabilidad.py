from datetime import datetime, timezone, timedelta
from app.extensions import db  # Utiliza la instancia de DB de tu proyecto

COLOMBIA = timezone(timedelta(hours=-5))


def ahora_colombia():
    """Fecha/hora Colombia sin zona (consistente con movement_date/sale_date)."""
    return datetime.now(COLOMBIA).replace(tzinfo=None)

class PersonaContable(db.Model):
    __tablename__ = 'personas_contables'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    identificacion = db.Column(db.String(20), unique=True, nullable=False)
    tipo = db.Column(db.String(50), nullable=False) # 'Personal', 'Cliente', etc.

    consignaciones = db.relationship('ConsignacionBancaria', backref='destinatario', lazy=True)


class BancoDestino(db.Model):
    __tablename__ = 'bancos_destino'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(60), unique=True, nullable=False) # Ej: Bancolombia, Nequi, Davivienda

    consignaciones = db.relationship('ConsignacionBancaria', backref='banco', lazy=True)


class ConsignacionBancaria(db.Model):
    __tablename__ = 'consignaciones_bancarias'

    id = db.Column(db.Integer, primary_key=True)
    persona_id = db.Column(db.Integer, db.ForeignKey('personas_contables.id'), nullable=False)
    banco_id = db.Column(db.Integer, db.ForeignKey('bancos_destino.id'), nullable=False)
    monto = db.Column(db.Numeric(14, 2), nullable=False)
    fecha = db.Column(db.DateTime, default=ahora_colombia, nullable=False)
    referencia = db.Column(db.String(100), nullable=True)


class ReporteGenerado(db.Model):
    """HU-TRI-002: quién y cuándo generó cada consolidado para el contador."""
    __tablename__ = 'reportes_generados'

    id = db.Column(db.Integer, primary_key=True)
    fecha_ini = db.Column(db.String(10), nullable=False)
    fecha_fin = db.Column(db.String(10), nullable=False)
    actor = db.Column(db.String(120), nullable=False, default='Sesión local sin autenticación')
    totales_json = db.Column(db.Text, nullable=False, default='{}')
    created_at = db.Column(db.DateTime, default=ahora_colombia, nullable=False)


class IngresoGasto(db.Model):
    """HU-FIN-001/002 y HU-TRI-001: ingresos y gastos no ligados a una venta."""
    __tablename__ = 'ingresos_gastos'

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(10), nullable=False)  # INGRESO | GASTO
    concepto = db.Column(db.String(120), nullable=False)
    categoria = db.Column(db.String(30), nullable=False, default='OTRO')
    valor_cents = db.Column(db.Integer, nullable=False)
    fecha = db.Column(db.String(10), nullable=False)  # YYYY-MM-DD
    relacion = db.Column(db.String(120), nullable=False, default='')
    soporte_ref = db.Column(db.String(100), nullable=False, default='')
    responsable = db.Column(db.String(120), nullable=False, default='')
    created_at = db.Column(db.DateTime, default=ahora_colombia, nullable=False)


class CorreccionClasificacion(db.Model):
    """HU-TRI-003: solo cambia la categoría; conserva anterior/nueva + motivo."""
    __tablename__ = 'correcciones_clasificacion'

    id = db.Column(db.Integer, primary_key=True)
    entidad = db.Column(db.String(30), nullable=False, default='ingreso_gasto')
    entidad_id = db.Column(db.Integer, nullable=False)
    anterior = db.Column(db.String(30), nullable=False)
    nueva = db.Column(db.String(30), nullable=False)
    motivo = db.Column(db.String(500), nullable=False)
    actor = db.Column(db.String(120), nullable=False, default='Sesión local sin autenticación')
    created_at = db.Column(db.DateTime, default=ahora_colombia, nullable=False)
