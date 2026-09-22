from datetime import datetime
from app.extensions import db  # Utiliza la instancia de DB de tu proyecto

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
    fecha = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    referencia = db.Column(db.String(100), nullable=True)