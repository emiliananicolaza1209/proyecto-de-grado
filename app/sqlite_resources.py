"""Una conexión SQLite pertenece al bloque que la abre.

El contexto nativo maneja commit/rollback pero no cierra la conexión.
Este contexto mantiene esa semántica y garantiza close al salir, incluso
por return, excepción del cuerpo o error al confirmar la transacción.
"""
import sqlite3
from contextlib import contextmanager


@contextmanager
def sqlite_connection(*args, **kwargs):
    connection = sqlite3.connect(*args, **kwargs)
    try:
        with connection:
            yield connection
    finally:
        connection.close()
