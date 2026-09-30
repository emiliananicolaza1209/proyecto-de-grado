"""Fábrica de la aplicación: configuración, extensiones y controladores."""
import os
import secrets
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask
from sqlalchemy import event
from sqlalchemy.engine import URL
from .extensions import db


def create_app(config=None):
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / '.env')
    app = Flask(__name__, instance_path=str(root / 'instance'), instance_relative_config=True)
    app.config.from_mapping(SECRET_KEY=os.getenv('SECRET_KEY') or secrets.token_hex(32),
                            DATABASE=str(root / os.getenv('DATABASE_PATH', 'instance/cpstore.sqlite')),
                            SQLALCHEMY_TRACK_MODIFICATIONS=False, MAX_CONTENT_LENGTH=1024*1024,
                            SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
    if config:
        app.config.update(config)
    database = Path(app.config['DATABASE']).resolve()
    app.config['DATABASE'] = str(database)
    app.config['SQLALCHEMY_DATABASE_URI'] = URL.create('sqlite', database=str(database))
    from migrations import upgrade
    upgrade(database)
    db.init_app(app)
    from . import models
    with app.app_context():
        def configure_sqlite(connection, _record):
            connection.execute('PRAGMA foreign_keys=ON')
        event.listen(db.engine, 'connect', configure_sqlite)
    from .routes.inventario_routes import inventory
    from .routes.catalogo_routes import catalogos
    from .routes.main_routes import main
    from .routes.ventas_routes import ventas
    from .routes.lote_routes import lotes
    from .routes.finanzas_routes import finanzas
    from .security import protect_forms
    app.before_request(protect_forms)
    for blueprint in (main, inventory, catalogos, ventas, lotes, finanzas):
        app.register_blueprint(blueprint)
    return app
