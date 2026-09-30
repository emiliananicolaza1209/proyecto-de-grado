"""Migración versionada del esquema heredado. No se ejecuta desde las rutas."""
import sqlite3
from pathlib import Path


def upgrade_v1(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        db.execute('CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY)')
        if db.execute('SELECT 1 FROM schema_version WHERE version=1').fetchone():
            return
        # Copia coherente antes de modificar una base que contiene equipos.
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='equipment'").fetchone():
            backup_path = path.with_name(path.name + '.antes_mvc.bak')
            if not backup_path.exists():
                with sqlite3.connect(path) as source, sqlite3.connect(backup_path) as backup:
                    source.backup(backup)
        db.execute('BEGIN')
        db.execute('''CREATE TABLE IF NOT EXISTS equipment (
            id INTEGER PRIMARY KEY, imei TEXT NOT NULL UNIQUE,
            model TEXT NOT NULL, capacity INTEGER NOT NULL CHECK(capacity > 0),
            color TEXT NOT NULL, condition TEXT NOT NULL,
            cost_cents INTEGER NOT NULL CHECK(cost_cents >= 0),
            location TEXT NOT NULL, supplier TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Disponible',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')
        from .legacy import migrate
        migrate(db)
        columns = {r['name'] for r in db.execute('PRAGMA table_info(equipment)')}
        for name, column_type in [('purchase_usd', 'TEXT'), ('exchange_rate', 'TEXT'),
                                  ('shipping_cents', 'INTEGER'), ('subtotal_cents', 'INTEGER')]:
            if name not in columns:
                db.execute(f'ALTER TABLE equipment ADD COLUMN {name} {column_type}')

        db.execute('INSERT INTO schema_version(version) VALUES(1)')


def upgrade(path):
    upgrade_v1(path)
    with sqlite3.connect(path) as connection:
        if not connection.execute('SELECT 1 FROM schema_version WHERE version=2').fetchone():
            connection.execute('BEGIN')
            connection.execute('ALTER TABLE equipment ADD COLUMN archived INTEGER NOT NULL DEFAULT 0')
            connection.execute('ALTER TABLE equipment ADD COLUMN revision INTEGER NOT NULL DEFAULT 1')
            connection.execute('''CREATE TABLE equipment_event (
                id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES equipment(id),
                action TEXT NOT NULL, reason TEXT NOT NULL, before_data TEXT NOT NULL,
                after_data TEXT NOT NULL, actor TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
            connection.execute('INSERT INTO schema_version(version) VALUES(2)')
    upgrade_v3(path)
    upgrade_v4(path)
    upgrade_v5(path)
    upgrade_v6(path)
    upgrade_v7(path)
    upgrade_v8(path)
    upgrade_v9(path)
    from .finance import upgrade as finance_upgrade
    finance_upgrade(path)


def upgrade_v9(path):
    with sqlite3.connect(path) as connection:
        if connection.execute('SELECT 1 FROM schema_version WHERE version=9').fetchone():
            return
        with sqlite3.connect(str(path) + '.antes_MOD03.bak') as backup:
            connection.backup(backup)
        connection.execute('BEGIN')
        connection.execute('ALTER TABLE equipment ADD COLUMN loan_handler TEXT')
        connection.execute('ALTER TABLE equipment ADD COLUMN loan_price_cents INTEGER')
        connection.execute("""CREATE TABLE customer_collection (
            id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES equipment(id),
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
            destination TEXT NOT NULL, collector TEXT NOT NULL, method TEXT NOT NULL,
            reference TEXT NOT NULL DEFAULT '', effective_date TEXT NOT NULL,
            note TEXT NOT NULL, legacy BOOLEAN NOT NULL DEFAULT 0,
            voided BOOLEAN NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        connection.execute("""CREATE TABLE admin_receipt (
            id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES customer_collection(id),
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0), administrator TEXT NOT NULL,
            method TEXT NOT NULL, reference TEXT NOT NULL DEFAULT '', effective_date TEXT NOT NULL,
            note TEXT NOT NULL, voided BOOLEAN NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        connection.execute('CREATE INDEX ix_customer_collection_product_id ON customer_collection(product_id)')
        connection.execute('CREATE INDEX ix_admin_receipt_collection_id ON admin_receipt(collection_id)')
        # Conservar los importes anteriores; no atribuirlos a una persona ni inventar entregas.
        connection.execute("""INSERT INTO customer_collection
            (product_id,amount_cents,destination,collector,method,effective_date,note,legacy)
            SELECT id,paid_cents,'Por verificar','SIN IDENTIFICAR','Por verificar',
            COALESCE(payment_date,substr(created_at,1,10)),
            'Saldo anterior a MOD03; falta identificar quién cobró y qué recibió administración.',1
            FROM equipment WHERE paid_cents > 0""")
        connection.execute('INSERT INTO schema_version(version) VALUES(9)')


def upgrade_v8(path):
    """Cobertura opcional y presentación uniforme, sin borrar registros históricos."""
    with sqlite3.connect(path) as connection:
        if connection.execute('SELECT 1 FROM schema_version WHERE version=8').fetchone():
            return
        with sqlite3.connect(str(path) + '.antes_INV12.bak') as backup:
            connection.backup(backup)
        connection.execute('BEGIN')
        connection.execute('ALTER TABLE equipment ADD COLUMN warranty_until TEXT')
        from .apple_catalog import seed
        seed(connection)
        for item_id, name in connection.execute('SELECT id,name FROM catalog').fetchall():
            connection.execute('UPDATE catalog SET name=? WHERE id=?', (' '.join(name.split()).upper(), item_id))
        connection.execute('INSERT INTO schema_version(version) VALUES(8)')


def upgrade_v7(path):
    with sqlite3.connect(path) as connection:
        if connection.execute('SELECT 1 FROM schema_version WHERE version=7').fetchone():
            return
        backup_path = Path(str(path) + '.antes_modulos_02_03.bak')
        if not backup_path.exists():
            with sqlite3.connect(backup_path) as backup:
                connection.backup(backup)
        connection.execute('BEGIN')
        connection.execute('''CREATE TABLE purchase_lot (
            id INTEGER PRIMARY KEY, entry_date TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            supplier_id INTEGER NOT NULL REFERENCES catalog(id), exchange_rate TEXT NOT NULL,
            expected_count INTEGER NOT NULL CHECK(expected_count > 0), note TEXT NOT NULL DEFAULT '')''')
        connection.execute('ALTER TABLE equipment ADD COLUMN lot_id INTEGER REFERENCES purchase_lot(id)')
        for field in ('seller','loan_date','sale_date','last_note'):
            connection.execute(f'ALTER TABLE equipment ADD COLUMN {field} TEXT')
        from .apple_catalog import seed
        seed(connection)
        connection.execute('INSERT INTO schema_version(version) VALUES(7)')


def upgrade_v3(path):
    with sqlite3.connect(path) as connection:
        if connection.execute('SELECT 1 FROM schema_version WHERE version=3').fetchone():
            return
        connection.row_factory = sqlite3.Row
        connection.execute('BEGIN')
        def norm(value):
            import re, unicodedata
            value = ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c))
            return re.sub(r'[^a-z0-9]', '', value)
        def brand(name, active=1):
            key = norm(name)
            connection.execute('INSERT OR IGNORE INTO catalog(kind,name,normal_key,parent_id,active) VALUES(?,?,?,?,?)', ('brand',name,key,0,active))
            return connection.execute("SELECT id FROM catalog WHERE kind='brand' AND normal_key=? AND parent_id=0", (key,)).fetchone()['id']
        brands = {'Apple': brand('Apple'), 'Samsung': brand('Samsung'), 'Xiaomi': brand('Xiaomi'),
                  'Motorola': brand('Motorola'), 'Google': brand('Google'),
                  'Sin marca / por revisar': brand('Sin marca / por revisar', 0)}
        for reference in connection.execute("SELECT * FROM catalog WHERE kind='reference' AND parent_id=0"):
            key = norm(reference['name'])
            target = 'Apple' if 'iphone' in key or key.startswith('apple') else 'Samsung' if 'samsung' in key or key.startswith('galaxy') else 'Xiaomi' if any(x in key for x in ('xiaomi','redmi','poco')) else 'Motorola' if 'motorola' in key or key.startswith('moto') else 'Google' if 'pixel' in key or key.startswith('google') else 'Sin marca / por revisar'
            connection.execute('UPDATE catalog SET parent_id=? WHERE id=?', (brands[target],reference['id']))
        connection.execute('INSERT INTO schema_version(version) VALUES(3)')


def upgrade_v4(path):
    """Normaliza la presentación de catálogos ya creados sin modificar sus claves."""
    with sqlite3.connect(path) as connection:
        if connection.execute('SELECT 1 FROM schema_version WHERE version=4').fetchone():
            return
        connection.execute('BEGIN')
        connection.execute("UPDATE catalog SET name=UPPER(name) WHERE kind != 'capacity'")
        connection.execute('INSERT INTO schema_version(version) VALUES(4)')

def upgrade_v6(path):
    with sqlite3.connect(path) as connection:
        if connection.execute('SELECT 1 FROM schema_version WHERE version=6').fetchone(): return
        connection.execute('BEGIN')
        for name, definition in [('paid_cents','INTEGER NOT NULL DEFAULT 0'),('purpose','TEXT'),('due_date','TEXT'),('battery','INTEGER'),('warranty_previous','TEXT')]:
            connection.execute(f'ALTER TABLE equipment ADD COLUMN {name} {definition}')
        connection.execute("UPDATE equipment SET payment_status='Por verificar' WHERE status='Vendido'")
        connection.execute('INSERT INTO schema_version(version) VALUES(6)')

def upgrade_v5(path):
    """Estados de pasamano y recaudo, sin eliminar la información existente."""
    with sqlite3.connect(path) as connection:
        if connection.execute('SELECT 1 FROM schema_version WHERE version=5').fetchone(): return
        connection.execute('BEGIN')
        columns = {row[1] for row in connection.execute('PRAGMA table_info(equipment)')}
        for name, typ, default in [
            ('responsible','TEXT',''), ('movement_date','TEXT',''),
            ('payment_status','TEXT',"'No aplica'"), ('sale_value_cents','INTEGER',''), ('payment_date','TEXT','')]:
            if name not in columns:
                clause = f"ALTER TABLE equipment ADD COLUMN {name} {typ}" + (f" NOT NULL DEFAULT {default}" if default else '')
                connection.execute(clause)
        connection.execute('INSERT INTO schema_version(version) VALUES(5)')
