from sqlalchemy import text
from ..extensions import db


class Lote(db.Model):
    __tablename__ = 'purchase_lot'
    id = db.Column(db.Integer, primary_key=True)
    entry_date = db.Column(db.String, nullable=False)
    created_at = db.Column(db.String, server_default=text('CURRENT_TIMESTAMP'))
    supplier_id = db.Column(db.Integer, db.ForeignKey('catalog.id'), nullable=False)
    exchange_rate = db.Column(db.String, nullable=False)
    expected_count = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String, nullable=False, default='')
    supplier = db.relationship('Catalogo', foreign_keys=[supplier_id])

    @property
    def code(self):
        return f'LOT-{self.id:05d}'
