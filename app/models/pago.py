from sqlalchemy import text
from ..extensions import db


class Cobro(db.Model):
    """Pago reportado del cliente. No equivale a recepción por administración."""
    __tablename__ = 'customer_collection'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('equipment.id'), nullable=False, index=True)
    amount_cents = db.Column(db.Integer, nullable=False)
    destination = db.Column(db.String(20), nullable=False)
    collector = db.Column(db.String(120), nullable=False)
    method = db.Column(db.String(30), nullable=False)
    reference = db.Column(db.String(120), nullable=False, default='')
    effective_date = db.Column(db.String, nullable=False)
    note = db.Column(db.String(500), nullable=False)
    legacy = db.Column(db.Boolean, nullable=False, default=False)
    voided = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.String, server_default=text('CURRENT_TIMESTAMP'))


class Recepcion(db.Model):
    """Importe que la administradora confirma haber recibido de un cobro."""
    __tablename__ = 'admin_receipt'
    id = db.Column(db.Integer, primary_key=True)
    collection_id = db.Column(db.Integer, db.ForeignKey('customer_collection.id'), nullable=False, index=True)
    amount_cents = db.Column(db.Integer, nullable=False)
    administrator = db.Column(db.String(120), nullable=False)
    method = db.Column(db.String(30), nullable=False)
    reference = db.Column(db.String(120), nullable=False, default='')
    effective_date = db.Column(db.String, nullable=False)
    note = db.Column(db.String(500), nullable=False)
    voided = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.String, server_default=text('CURRENT_TIMESTAMP'))
