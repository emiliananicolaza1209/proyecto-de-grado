from datetime import datetime
from app.extensions import db  # Utiliza la instancia de DB de tu proyecto

class PersonaContable(db.Model):
    __tablename__ = 'personas_contables'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    identificacion = db.Column(db.String(20), unique=True, nullable=False)
    tipo = db.Column(db.String(50), nullable=False) # 'Personal', 'Cliente', etc.
    declaro_renta_antes = db.Column(db.Boolean, nullable=False, default=False)
    
    consignaciones = db.relationship('ConsignacionBancaria', backref='destinatario', lazy=True)
    bancos_asociados = db.relationship('PersonaBanco', back_populates='persona', lazy='selectin')


class BancoDestino(db.Model):
    __tablename__ = 'bancos_destino'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(60), unique=True, nullable=False) # Ej: Bancolombia, Nequi, Davivienda
    
    consignaciones = db.relationship('ConsignacionBancaria', backref='banco', lazy=True)
    personas_asociadas = db.relationship('PersonaBanco', back_populates='banco', lazy='selectin')


class PersonaBanco(db.Model):
    """Banco registrado para una persona, sin duplicar su identificación."""
    __tablename__ = 'persona_banco'
    __table_args__ = (db.UniqueConstraint('persona_id','banco_id',name='uq_persona_banco'),)
    id = db.Column(db.Integer,primary_key=True)
    persona_id = db.Column(db.Integer,db.ForeignKey('personas_contables.id'),nullable=False,index=True)
    banco_id = db.Column(db.Integer,db.ForeignKey('bancos_destino.id'),nullable=False)
    persona = db.relationship('PersonaContable',back_populates='bancos_asociados')
    banco = db.relationship('BancoDestino',back_populates='personas_asociadas')


class ConsignacionBancaria(db.Model):
    __tablename__ = 'consignaciones_bancarias'
    
    id = db.Column(db.Integer, primary_key=True)
    persona_id = db.Column(db.Integer, db.ForeignKey('personas_contables.id'), nullable=False)
    banco_id = db.Column(db.Integer, db.ForeignKey('bancos_destino.id'), nullable=True)
    monto = db.Column(db.Numeric(14, 2), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    referencia = db.Column(db.String(100), nullable=True)
    finance_operation_id = db.Column(db.Integer, db.ForeignKey('finance_operation.id'))
    payment_index = db.Column(db.Integer)
    supplier_payment_id = db.Column(db.Integer, db.ForeignKey('finance_supplier_payment.id'), unique=True)
    activa = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (db.UniqueConstraint('finance_operation_id','payment_index',name='uq_consignacion_operacion_medio'),)


class HistorialConsignacion(db.Model):
    __tablename__ = 'historial_consignaciones'
    id = db.Column(db.Integer, primary_key=True)
    consignacion_id = db.Column(db.Integer, db.ForeignKey('consignaciones_bancarias.id'), nullable=False)
    accion = db.Column(db.String(30), nullable=False)
    motivo = db.Column(db.String(500), nullable=False)
    antes = db.Column(db.JSON)
    despues = db.Column(db.JSON)
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
