"""Crea las tablas faltantes en la BD configurada (recreado el 2026-09-28)."""
from app import create_app
from app.extensions import db

app = create_app()
with app.app_context():
    db.create_all()
print('BD lista:', app.config['DATABASE'])
