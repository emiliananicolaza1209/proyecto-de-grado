from sqlalchemy import text
from ..extensions import db


class Movimiento(db.Model):
    __tablename__ = 'equipment_event'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('equipment.id'), nullable=False)
    action = db.Column(db.String, nullable=False)
    reason = db.Column(db.String, nullable=False)
    before_data = db.Column(db.Text, nullable=False)
    after_data = db.Column(db.Text, nullable=False)
    actor = db.Column(db.String, nullable=False)
    created_at = db.Column(db.String, server_default=text('CURRENT_TIMESTAMP'))
