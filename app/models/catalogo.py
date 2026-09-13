from sqlalchemy.orm import foreign
from ..extensions import db


class Catalogo(db.Model):
    __tablename__ = 'catalog'
    __table_args__ = (db.UniqueConstraint('kind', 'normal_key', 'parent_id'),)
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(30), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    normal_key = db.Column(db.String(120), nullable=False)
    parent_id = db.Column(db.Integer, nullable=False, default=0)
    active = db.Column(db.Integer, nullable=False, default=1)
    parent = db.relationship('Catalogo', primaryjoin=lambda: foreign(Catalogo.parent_id) == Catalogo.id, remote_side=[id], viewonly=True, lazy='joined')

    @property
    def display_name(self):
        if self.kind == 'reference' and self.parent and not self.normal_key.startswith(self.parent.normal_key):
            return f'{self.parent.name} {self.name}'
        return self.name

    def to_dict(self):
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}
