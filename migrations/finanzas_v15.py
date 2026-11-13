"""Conserva por equipo la asignación comercial y la reserva de administración del POOL."""
import sqlite3
from app.sqlite_resources import sqlite_connection
from pathlib import Path


def upgrade(path):
    with sqlite_connection(path) as conn:
        if conn.execute('SELECT 1 FROM schema_version WHERE version=15').fetchone():
            return
        backup=Path(str(path)+'.antes_pool_v15.bak')
        if not backup.exists():
            with sqlite_connection(backup) as target:
                conn.backup(target)
        existing={row[1] for row in conn.execute('PRAGMA table_info(equipment)')}
        if 'pool_assigned_cost_cents' not in existing:
            conn.execute('ALTER TABLE equipment ADD COLUMN pool_assigned_cost_cents INTEGER')
        if 'pool_admin_gain_cents' not in existing:
            conn.execute('ALTER TABLE equipment ADD COLUMN pool_admin_gain_cents INTEGER NOT NULL DEFAULT 0')
        conn.execute('INSERT INTO schema_version(version) VALUES(15)')
