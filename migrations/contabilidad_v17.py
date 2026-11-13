"""MOD-06 información contable: v17 y v18.

Son las migraciones que en la rama `Andres` se llamaban v11 y v12. En `desarrollo` esos
números ya pertenecen a `integracion.py`, así que se renumeran. Son aditivas e idempotentes:
no se salen solo porque el número de versión exista; también comprueban que la tabla exista.
Conservan los datos de las bases que ya tenían las tablas con la numeración de Andres.
"""
import sqlite3
from contextlib import closing
from pathlib import Path

REPORTES = '''CREATE TABLE IF NOT EXISTS reportes_generados (
    id INTEGER PRIMARY KEY, fecha_ini TEXT NOT NULL, fecha_fin TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'Sesión local sin autenticación',
    totales_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)'''

INGRESOS_GASTOS = '''CREATE TABLE IF NOT EXISTS ingresos_gastos (
    id INTEGER PRIMARY KEY, tipo TEXT NOT NULL, concepto TEXT NOT NULL,
    categoria TEXT NOT NULL DEFAULT 'OTRO', valor_cents INTEGER NOT NULL,
    fecha TEXT NOT NULL, relacion TEXT NOT NULL DEFAULT '',
    soporte_ref TEXT NOT NULL DEFAULT '', responsable TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)'''

CORRECCIONES = '''CREATE TABLE IF NOT EXISTS correcciones_clasificacion (
    id INTEGER PRIMARY KEY, entidad TEXT NOT NULL DEFAULT 'ingreso_gasto',
    entidad_id INTEGER NOT NULL, anterior TEXT NOT NULL, nueva TEXT NOT NULL,
    motivo TEXT NOT NULL, actor TEXT NOT NULL DEFAULT 'Sesión local sin autenticación',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)'''


def _tabla_existe(conn, nombre):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nombre,)).fetchone() is not None


def _aplicar(path, version, tablas, sufijo_bak):
    """tablas: {nombre: DDL con CREATE TABLE IF NOT EXISTS}."""
    with closing(sqlite3.connect(str(path))) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY)')
        conn.commit()
        registrada = conn.execute('SELECT 1 FROM schema_version WHERE version=?', (version,)).fetchone()
        if registrada and all(_tabla_existe(conn, t) for t in tablas):
            return  # versión registrada y tablas presentes: nada que hacer
        backup = Path(str(path) + sufijo_bak)
        if not backup.exists():
            with closing(sqlite3.connect(str(backup))) as safe_copy:
                conn.backup(safe_copy)
        with conn:
            for ddl in tablas.values():
                conn.execute(ddl)  # IF NOT EXISTS: nunca toca filas existentes
            conn.execute('INSERT OR IGNORE INTO schema_version(version) VALUES(?)', (version,))


def upgrade_v17(path):
    """HU-TRI-002: trazabilidad de reportes para el contador."""
    _aplicar(path, 17, {'reportes_generados': REPORTES}, '.antes_v17.bak')


def upgrade_v18(path):
    """Ingresos/gastos (HU-FIN-001/002, HU-TRI-001) y auditoría de correcciones (HU-TRI-003)."""
    _aplicar(path, 18, {'ingresos_gastos': INGRESOS_GASTOS,
                        'correcciones_clasificacion': CORRECCIONES}, '.antes_v18.bak')
