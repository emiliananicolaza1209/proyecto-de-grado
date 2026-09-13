from sqlalchemy import text
from ..extensions import db


class Producto(db.Model):
    """Equipo serializado. Los nombres originales son una copia del ingreso."""
    __tablename__ = 'equipment'
    id = db.Column(db.Integer, primary_key=True)
    lot_id = db.Column(db.Integer, db.ForeignKey('purchase_lot.id'))
    lot = db.relationship('Lote', lazy='joined')
    archived = db.Column(db.Integer, nullable=False, default=0)
    revision = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': revision}
    imei = db.Column(db.String(15), nullable=False, unique=True)
    model = db.Column(db.String(120), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    color = db.Column(db.String(120), nullable=False)
    condition = db.Column(db.String(30), nullable=False)
    cost_cents = db.Column(db.Integer, nullable=False)
    location = db.Column(db.String(120), nullable=False)
    supplier = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(30), nullable=False, default='Disponible')
    responsible = db.Column(db.String(120))
    seller = db.Column(db.String(120))
    loan_date = db.Column(db.String)
    sale_date = db.Column(db.String)
    last_note = db.Column(db.String)
    movement_date = db.Column(db.String)
    payment_status = db.Column(db.String(20), nullable=False, default='No aplica')
    sale_value_cents = db.Column(db.Integer)
    payment_date = db.Column(db.String)
    paid_cents = db.Column(db.Integer, nullable=False, default=0)
    purpose = db.Column(db.String)
    due_date = db.Column(db.String)
    battery = db.Column(db.Integer)
    warranty_previous = db.Column(db.String)
    warranty_until = db.Column(db.String)
    created_at = db.Column(db.String, server_default=text('CURRENT_TIMESTAMP'))
    reference_id = db.Column(db.Integer, db.ForeignKey('catalog.id'))
    color_id = db.Column(db.Integer, db.ForeignKey('catalog.id'))
    capacity_id = db.Column(db.Integer, db.ForeignKey('catalog.id'))
    supplier_id = db.Column(db.Integer, db.ForeignKey('catalog.id'))
    location_id = db.Column(db.Integer, db.ForeignKey('catalog.id'))
    purchase_usd = db.Column(db.String)
    exchange_rate = db.Column(db.String)
    shipping_cents = db.Column(db.Integer)
    subtotal_cents = db.Column(db.Integer)
    reference_item = db.relationship('Catalogo', foreign_keys=[reference_id], lazy='joined')
    color_item = db.relationship('Catalogo', foreign_keys=[color_id], lazy='joined')
    supplier_item = db.relationship('Catalogo', foreign_keys=[supplier_id], lazy='joined')
    location_item = db.relationship('Catalogo', foreign_keys=[location_id], lazy='joined')

    def to_dict(self):
        data = {column.name: getattr(self, column.name) for column in self.__table__.columns}
        data['lot_code'] = self.lot.code if self.lot else 'Sin lote anterior'
        data['entry_date'] = self.lot.entry_date if self.lot else self.created_at
        for field, item in [('model', self.reference_item), ('color', self.color_item),
                            ('supplier', self.supplier_item), ('location', self.location_item)]:
            if item is not None:
                data[field] = item.display_name if field == 'model' else item.name
        return data
