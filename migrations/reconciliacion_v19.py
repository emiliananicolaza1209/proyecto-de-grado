"""v19: reconciliación estructural de bases con la numeración de Andres.

En la rama `Andres` los números v11 y v12 pertenecían al módulo contable; en `desarrollo`
pertenecen a `integracion.py` (columnas de personas, retomas y consignaciones). Una base que
ya registra v11/v12 de Andres hace que las de desarrollo se salten por número y falte su
estructura, y entonces v13 falla (`no such column: person_id`).

Esta migración es solo aditiva e idempotente: agrega las columnas e índices de las v11/v12 de
desarrollo que falten (si la tabla existe) y, solo cuando tuvo que corregir v12, los catálogos
base que esa migración habría sembrado. NO modifica filas de finance_day (base de caja ni medios
de jornadas abiertas). Debe correr antes de upgrade_v13.
"""
import sqlite3
import unicodedata
from contextlib import closing
from pathlib import Path

COLUMNAS_V11 = (
    ('personas_contables', 'declaro_renta_antes', 'BOOLEAN NOT NULL DEFAULT 0'),
    ('finance_operation', 'person_id', 'INTEGER REFERENCES personas_contables(id)'),
    ('equipment', 'person_id', 'INTEGER REFERENCES personas_contables(id)'),
)
COLUMNAS_V12 = (
    ('equipment', 'source_type', "TEXT NOT NULL DEFAULT 'Lote'"),
    ('equipment', 'purchase_cop_cents', 'INTEGER'),
    ('equipment', 'additional_costs', 'JSON'),
    ('consignaciones_bancarias', 'finance_operation_id', 'INTEGER REFERENCES finance_operation(id)'),
    ('consignaciones_bancarias', 'payment_index', 'INTEGER'),
    ('consignaciones_bancarias', 'supplier_payment_id', 'INTEGER REFERENCES finance_supplier_payment(id)'),
    ('consignaciones_bancarias', 'activa', 'BOOLEAN NOT NULL DEFAULT 1'),
    ('finance_supplier_payment', 'person_id', 'INTEGER REFERENCES personas_contables(id)'),
    ('finance_supplier_payment', 'bank_id', 'INTEGER REFERENCES bancos_destino(id)'),
)
INDICES_V12 = (
    ('ux_consignacion_finance_payment', 'consignaciones_bancarias', 'finance_operation_id,payment_index'),
    ('ux_consignacion_supplier_payment', 'consignaciones_bancarias', 'supplier_payment_id'),
)
PROVEEDORES_BASE = ('CP CELULARES', 'CP VARIOS', 'CP HIDROGELES', 'BATERÍAS', 'MEMORIAS')


def _tabla_existe(conn, nombre):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nombre,)).fetchone() is not None


def _columnas(conn, tabla):
    return {r[1] for r in conn.execute(f'PRAGMA table_info("{tabla}")')}


def _faltantes(conn, definiciones):
    return [(t, n, d) for t, n, d in definiciones if _tabla_existe(conn, t) and n not in _columnas(conn, t)]


def upgrade_v19(path):
    with closing(sqlite3.connect(str(path))) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY)')
        conn.commit()
        faltan_11 = _faltantes(conn, COLUMNAS_V11)
        faltan_12 = _faltantes(conn, COLUMNAS_V12)
        faltan_idx = [i for i in INDICES_V12 if _tabla_existe(conn, i[1]) and not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (i[0],)).fetchone()
            and not _faltantes(conn, [(i[1], c, '') for c in i[2].split(',')])]
        registrada = conn.execute('SELECT 1 FROM schema_version WHERE version=19').fetchone()
        if not (faltan_11 or faltan_12):
            # Nada que corregir: solo el índice si ya hay columnas, y el registro de versión.
            with conn:
                for nombre, tabla, cols in faltan_idx:
                    conn.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS {nombre} ON {tabla}({cols})')
                if not registrada:
                    conn.execute('INSERT OR IGNORE INTO schema_version(version) VALUES(19)')
            return
        backup = Path(str(path) + '.antes_v19.bak')
        if not backup.exists():
            with closing(sqlite3.connect(str(backup))) as safe_copy:
                conn.backup(safe_copy)
        v12_registrada = conn.execute('SELECT 1 FROM schema_version WHERE version=12').fetchone()
        with conn:
            for tabla, nombre, definicion in faltan_11 + faltan_12:
                conn.execute(f'ALTER TABLE "{tabla}" ADD COLUMN {nombre} {definicion}')
            for nombre, tabla, cols in INDICES_V12:
                if _tabla_existe(conn, tabla):
                    conn.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS {nombre} ON {tabla}({cols})')
            if faltan_12 and v12_registrada and _tabla_existe(conn, 'catalog'):
                for nombre in PROVEEDORES_BASE:
                    clave = ''.join(c for c in unicodedata.normalize('NFKD', nombre.casefold()) if c.isascii() and c.isalnum())
                    conn.execute("INSERT OR IGNORE INTO catalog(kind,name,normal_key,parent_id,active) VALUES('supplier',?,?,0,1)", (nombre, clave))
                conn.execute("INSERT OR IGNORE INTO catalog(kind,name,normal_key,parent_id,active) VALUES('location','LOCAL CP STORE','localcpstore',0,1)")
            conn.execute('INSERT OR IGNORE INTO schema_version(version) VALUES(19)')
