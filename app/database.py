"""Conexión dual y preparación explícita de PostgreSQL nuevo, sin importar SQLite."""
import os
import secrets
from pathlib import Path
import click
from flask import has_request_context, request, current_app
from sqlalchemy import event, inspect, text, Table, Column, Integer, MetaData
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session
from .extensions import db

WRITE_LOCK = 0x435053544f52
SCHEMA_VERSION = 1


def configure_database(app, root, config=None):
    config = config or {}
    raw = config.get('DATABASE_URL', '' if 'DATABASE' in config else os.getenv('DATABASE_URL', '')).strip()
    if raw:
        url = make_url(raw)
        if url.get_backend_name() not in ('postgresql', 'postgres'):
            raise ValueError('DATABASE_URL debe ser una conexión PostgreSQL.')
        url = url.set(drivername='postgresql+psycopg')
        if url.host and url.host.endswith('.render.com') and not url.query.get('sslmode'):
            url = url.update_query_dict({'sslmode': 'require'})
        app.config['SQLALCHEMY_DATABASE_URI'] = url
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True, 'pool_size': 3, 'max_overflow': 2,
            'connect_args': {'connect_timeout': 10, 'options': '-c timezone=UTC'},
        }
        if config.get('SQLALCHEMY_ENGINE_OPTIONS'):
            app.config['SQLALCHEMY_ENGINE_OPTIONS'].update(config['SQLALCHEMY_ENGINE_OPTIONS'])
        if not (os.getenv('SECRET_KEY') or config.get('SECRET_KEY')):
            raise ValueError('Configura SECRET_KEY en .env antes de usar PostgreSQL.')
    else:
        database = Path(app.config['DATABASE']).resolve()
        app.config['DATABASE'] = str(database)
        app.config['SQLALCHEMY_DATABASE_URI'] = URL.create('sqlite', database=str(database))
        if not app.testing and not os.getenv('SECRET_KEY') and not config.get('SECRET_KEY'):
            database.parent.mkdir(parents=True, exist_ok=True)
            secret_path = database.parent / '.session-secret'
            try:
                with secret_path.open('x') as handle:
                    handle.write(secrets.token_hex(32))
                secret_path.chmod(0o600)
            except FileExistsError:
                pass
            app.config['SECRET_KEY'] = secret_path.read_text().strip()
    app.config['SESSION_COOKIE_SECURE'] = config.get(
        'SESSION_COOKIE_SECURE', os.getenv('SESSION_COOKIE_SECURE', 'false').lower() == 'true')


def initialize_sqlite(app):
    database = Path(app.config['DATABASE'])
    from migrations.gestion_v16 import backup_before_upgrade, seed
    from migrations import upgrade
    backup_before_upgrade(database)
    upgrade(database)
    def foreign_keys(connection, _record):
        connection.execute('PRAGMA foreign_keys=ON')
    event.listen(db.engine, 'connect', foreign_keys)
    db.create_all()
    # v19 repara bases con la numeración de Andres (v11/v12 distintas); debe ir antes de v13.
    from migrations.reconciliacion_v19 import upgrade_v19
    from migrations.integracion import upgrade as integration, upgrade_v12, upgrade_v13
    from migrations.finanzas_v14 import upgrade as v14
    from migrations.finanzas_v15 import upgrade as v15
    from migrations.contabilidad_v17 import upgrade_v17, upgrade_v18
    upgrade_v19(database)
    integration(database)
    upgrade_v12(database)
    upgrade_v13(database)
    v14(database)
    v15(database)
    upgrade_v17(database)
    upgrade_v18(database)
    seed()


def begin_write():
    if db.engine.name == 'sqlite':
        db.session.execute(text('BEGIN IMMEDIATE'))
    else:
        db.session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': WRITE_LOCK})


@event.listens_for(Session, 'after_begin')
def _serialize_postgres_writes(session, transaction, connection):
    # Antes de leer, incluso si autenticación consulta primero al usuario.
    # Se libera al confirmar, revertir o cerrar la conexión.
    if (connection.dialect.name == 'postgresql' and has_request_context()
            and request.method in ('POST', 'PUT', 'PATCH', 'DELETE')
            and current_app.config.get('CP_SERIALIZE_WRITES')):
        connection.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': WRITE_LOCK})


def install_write_serialization(app):
    app.config['CP_SERIALIZE_WRITES'] = True


def seed_catalogs(connection):
    """Solo catálogos del código; no ventas, personas ni usuarios."""
    from .models import Catalogo
    from .models.gestion import AliadoCredito, Socio
    from migrations.apple_catalog import GROUPS
    from migrations.legacy import normalize
    from migrations.finanzas_v14 import CELULARES, ACCESORIOS
    from sqlalchemy.dialects.postgresql import insert
    table = Catalogo.__table__
    def item(kind, name, parent=0, category=None, active=1):
        key = normalize(name, kind)
        values = dict(kind=kind, name=name, normal_key=key, parent_id=parent,
                      active=active, supplier_category=category)
        connection.execute(insert(table).values(**values).on_conflict_do_nothing(
            index_elements=['kind', 'normal_key', 'parent_id']))
        return connection.scalar(db.select(table.c.id).where(
            table.c.kind == kind, table.c.normal_key == key, table.c.parent_id == parent))
    for brand in ('APPLE', 'SAMSUNG', 'XIAOMI', 'MOTOROLA', 'GOOGLE'):
        item('brand', brand)
    item('brand', 'SIN MARCA / POR REVISAR', active=0)
    apple = item('brand', 'APPLE')
    for names, capacities, colors in GROUPS:
        for name in names.split('|'):
            ref = item('reference', 'IPHONE ' + name, apple)
            for cap in capacities:
                item('capacity', str(cap), ref)
            for color in colors.split('|'):
                item('color', color, ref)
    for name in dict.fromkeys(CELULARES + ACCESORIOS + ['CP HIDROGELES', 'BATERÍAS', 'MEMORIAS']):
        category = 'Ambos' if name in CELULARES and name in ACCESORIOS else 'Celulares' if name in CELULARES else 'Accesorios'
        item('supplier', name, category=category)
    item('location', 'LOCAL CP STORE')
    for name in ('ADDI', 'SISTECRÉDITO', 'SU+PAY', 'BANCO DE BOGOTÁ', 'IPHONE ALIADOS'):
        connection.execute(insert(AliadoCredito.__table__).values(nombre=name).on_conflict_do_nothing())
    connection.execute(insert(Socio.__table__).values(nombre='JONATAN').on_conflict_do_nothing())


def initialize_postgres():
    if db.engine.name != 'postgresql':
        raise click.ClickException('Configura DATABASE_URL para PostgreSQL. SQLite no se modifica.')
    metadata = MetaData()
    versions = Table('cp_schema_revision', metadata, Column('version', Integer, primary_key=True))
    with db.engine.begin() as conn:
        conn.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': WRITE_LOCK})
        tables = set(inspect(conn).get_table_names())
        if 'cp_schema_revision' in tables:
            version = conn.scalar(db.select(versions.c.version))
            if version != SCHEMA_VERSION:
                raise click.ClickException('Versión de esquema no compatible. No se modificó la base.')
            if not set(db.metadata.tables).issubset(tables):
                raise click.ClickException('Faltan tablas en un esquema existente. Requiere revisión.')
            return False
        if tables:
            raise click.ClickException('La base no está vacía. Este comando no borra ni reemplaza tablas existentes.')
        db.metadata.create_all(conn)
        seed_catalogs(conn)
        metadata.create_all(conn)
        conn.execute(versions.insert().values(version=SCHEMA_VERSION))
    return True


def register_database_commands(app):
    @app.cli.command('inicializar-postgres')
    def initialize():
        created = initialize_postgres()
        click.echo('PostgreSQL preparado con catálogos, sin movimientos de prueba.' if created else 'El esquema ya está inicializado. No se modificaron los datos.')

    @app.cli.command('comprobar-db')
    def check():
        try:
            with db.engine.connect() as conn:
                conn.execute(text('SELECT 1'))
                tables = set(inspect(conn).get_table_names())
                missing = set(db.metadata.tables) - tables
            click.echo(f'Motor: {db.engine.name}. Tablas del aplicativo: {len(set(db.metadata.tables) & tables)}.')
            if missing:
                raise click.ClickException('Faltan tablas. Ejecuta inicializar-postgres en la base nueva.')
            click.echo('Conexión y presencia de tablas correctas. Falta validar los flujos funcionales.')
        except click.ClickException:
            raise
        except Exception:
            raise click.ClickException('No se pudo comprobar la base. Revisa conexión, credenciales y acceso de red; no compartas la URL privada.') from None
