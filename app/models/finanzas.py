"""Jornadas versionadas, operaciones y pagos financieros; importes en centavos."""
from ..extensions import db

class Jornada(db.Model):
    __tablename__ = 'finance_day'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), unique=True, nullable=False)
    status = db.Column(db.String(12), nullable=False, default='Abierta')
    revision = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': revision}
    config = db.Column(db.JSON, nullable=False)
    snapshot = db.Column(db.JSON)

class OperacionFinanciera(db.Model):
    __table_args__ = (db.CheckConstraint('amount >= 0', name='ck_operation_amount'), db.CheckConstraint('minor_cost >= 0', name='ck_operation_minor_cost'),)
    __tablename__ = 'finance_operation'
    id = db.Column(db.Integer, primary_key=True)
    day_id = db.Column(db.Integer, db.ForeignKey('finance_day.id'), nullable=False, index=True)
    token = db.Column(db.String(64), unique=True, nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    description = db.Column(db.String(300), nullable=False)
    seller = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.BigInteger, nullable=False)
    minor_cost = db.Column(db.BigInteger, nullable=False, default=0)
    product_id = db.Column(db.Integer, db.ForeignKey('equipment.id'), unique=True)
    person_id = db.Column(db.Integer, db.ForeignKey('personas_contables.id'))
    costs = db.Column(db.JSON, nullable=False)
    payments = db.Column(db.JSON, nullable=False)
    voided = db.Column(db.Boolean, nullable=False, default=False)

class PagoProveedor(db.Model):
    __table_args__ = (db.CheckConstraint('amount > 0', name='ck_supplier_payment_amount'),)
    __tablename__ = 'finance_supplier_payment'
    id = db.Column(db.Integer, primary_key=True)
    day_id = db.Column(db.Integer, db.ForeignKey('finance_day.id'), nullable=False)
    operation_id = db.Column(db.Integer, db.ForeignKey('finance_operation.id'), nullable=False)
    cost_index = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.BigInteger, nullable=False)
    account = db.Column(db.String(120), nullable=False)
    person_id = db.Column(db.Integer, db.ForeignKey('personas_contables.id'))
    bank_id = db.Column(db.Integer, db.ForeignKey('bancos_destino.id'))
    token = db.Column(db.String(64), unique=True, nullable=False)

class AuditoriaFinanciera(db.Model):
    __tablename__ = 'finance_audit'
    id = db.Column(db.Integer, primary_key=True)
    day_id = db.Column(db.Integer, db.ForeignKey('finance_day.id'), nullable=False)
    action = db.Column(db.String(60), nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    detail = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.String, server_default=db.text('CAST(CURRENT_TIMESTAMP AS TEXT)'))
