"""Fábrica de la aplicación: configuración, extensiones y controladores."""

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from .extensions import db


def create_app(config=None):
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env")

    app = Flask(
        __name__,
        instance_path=str(root / "instance"),
        instance_relative_config=True,
    )

    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY") or secrets.token_hex(32),
        DATABASE=str(
            root / os.getenv("DATABASE_PATH", "instance/cpstore.sqlite")
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

    if config:
        app.config.update(config)

    from .database import configure_database, initialize_sqlite, register_database_commands
    configure_database(app, root, config)
    db.init_app(app)
    from . import models
    with app.app_context():
        if db.engine.name == 'sqlite':
            initialize_sqlite(app)
    register_database_commands(app)

    # Blueprints de la aplicación.
    from .routes.main_routes import main
    from .routes.inventario_routes import inventory
    from .routes.catalogo_routes import catalogos
    from .routes.ventas_routes import ventas
    from .routes.lote_routes import lotes
    from .routes.finanzas_routes import finanzas
    from .routes.informacion_contable_routes import contabilidad_bp

    # Protección de formularios.
    from .security import protect_forms

    app.before_request(protect_forms)

    for blueprint in (
        main,
        inventory,
        catalogos,
        ventas,
        lotes,
        finanzas,
        contabilidad_bp,
    ):
        app.register_blueprint(blueprint)

    from .auth import init_auth
    init_auth(app)
    from .routes.gestion_routes import gestion
    app.register_blueprint(gestion)
    # PostgreSQL serializa las escrituras web antes de leer saldos o existencias.
    from .database import install_write_serialization
    install_write_serialization(app)
    return app
