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

    database = Path(app.config["DATABASE"]).resolve()
    app.config["DATABASE"] = str(database)
    app.config["SQLALCHEMY_DATABASE_URI"] = URL.create(
        "sqlite",
        database=str(database),
    )

    if not app.testing and not os.getenv('SECRET_KEY') and not (config and config.get('SECRET_KEY')):
        database.parent.mkdir(parents=True, exist_ok=True)
        secret_path = database.parent / '.session-secret'
        try:
            with secret_path.open('x') as handle:
                handle.write(secrets.token_hex(32))
            secret_path.chmod(0o600)
        except FileExistsError:
            pass
        app.config['SECRET_KEY'] = secret_path.read_text().strip()

    # Ejecutar las migraciones existentes de inventario,
    # ventas, pagos y finanzas.
    from migrations import upgrade

    from migrations.gestion_v16 import backup_before_upgrade
    backup_before_upgrade(database)
    upgrade(database)

    # Inicializar SQLAlchemy.
    db.init_app(app)

    # Registrar todos los modelos antes de crear tablas faltantes.
    from . import models

    with app.app_context():

        def configure_sqlite(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        event.listen(db.engine, "connect", configure_sqlite)

        # Crea únicamente las tablas que aún no existen,
        # como las del módulo contable.
        db.create_all()
        # v19 repara bases con la numeración de Andres (v11/v12 distintas); debe ir antes de v13.
        from migrations.reconciliacion_v19 import upgrade_v19
        upgrade_v19(database)
        from migrations.integracion import upgrade as upgrade_integration
        upgrade_integration(database)
        from migrations.integracion import upgrade_v12, upgrade_v13
        upgrade_v12(database)
        upgrade_v13(database)
        from migrations.finanzas_v14 import upgrade as upgrade_finanzas_v14
        upgrade_finanzas_v14(database)
        from migrations.finanzas_v15 import upgrade as upgrade_finanzas_v15
        upgrade_finanzas_v15(database)
        from migrations.contabilidad_v17 import upgrade_v17, upgrade_v18
        upgrade_v17(database)
        upgrade_v18(database)
        from migrations.gestion_v16 import seed
        seed()

    # Blueprints de la aplicación.
    from .routes.main_routes import main
    from .routes.inventario_routes import inventory
    from .routes.catalogo_routes import catalogos
    from .routes.ventas_routes import ventas
    from .routes.lote_routes import lotes
    from .routes.finanzas_routes import finanzas
    from .routes.informacion_contable_routes import contabilidad_bp
    from .routes.chat_routes import chat

    # Protección de formularios.
    from .security import add_security_headers, protect_forms

    app.before_request(protect_forms)
    app.after_request(add_security_headers)

    for blueprint in (
        main,
        inventory,
        catalogos,
        ventas,
        lotes,
        finanzas,
        contabilidad_bp,
        chat,
    ):
        app.register_blueprint(blueprint)

    from .auth import init_auth
    init_auth(app)
    from .routes.gestion_routes import gestion
    app.register_blueprint(gestion)
    return app
