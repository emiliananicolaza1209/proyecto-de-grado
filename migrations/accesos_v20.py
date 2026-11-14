"""SQLite 20: tabla aditiva para restricciones de acceso por usuario."""
from app.sqlite_resources import sqlite_connection


def upgrade(path):
    with sqlite_connection(path) as conn:
        if conn.execute('SELECT 1 FROM schema_version WHERE version=20').fetchone(): return
        conn.execute('BEGIN')
        conn.execute('''CREATE TABLE IF NOT EXISTS permisos_usuario (
            usuario_id INTEGER PRIMARY KEY REFERENCES usuarios(id),
            permisos JSON NOT NULL)''')
        conn.execute('INSERT INTO schema_version(version) VALUES(20)')
