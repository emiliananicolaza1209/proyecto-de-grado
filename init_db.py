"""Preparación explícita; no crea tablas PostgreSQL fuera del inicializador versionado."""
from app import create_app
from app.extensions import db
from app.database import initialize_postgres
app = create_app()
with app.app_context():
    if db.engine.name == 'postgresql':
        initialize_postgres()
    print('Base preparada. Ejecuta comprobar-db para verificarla.')
