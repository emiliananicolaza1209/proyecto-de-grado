"""Regresión del ciclo de vida: conexiones SQLite reales, retenidas hasta verificar cierre."""
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from app import create_app
from app.extensions import db
from app.respaldo import backup, restore
from app.sqlite_resources import sqlite_connection


@contextmanager
def tracked_connections():
    original = sqlite3.connect
    opened = []

    class TrackedConnection(sqlite3.Connection):
        def close(self):
            try:
                return super().close()
            finally:
                self.was_closed = True

    def connect(*args, **kwargs):
        kwargs['factory'] = TrackedConnection
        conn = original(*args, **kwargs)
        conn.was_closed = False
        # Keep real connections alive: do not allow GC to hide a resource leak.
        opened.append(conn)
        return conn

    try:
        with patch('sqlite3.connect', side_effect=connect):
            yield opened
    finally:
        # Test cleanup runs AFTER the assertions, including when they fail.
        for conn in opened:
            conn.close()


class SQLiteResourceTests(unittest.TestCase):
    def assert_closed(self, connections):
        self.assertTrue(connections, 'The scenario must exercise real SQLite connections.')
        self.assertEqual(sum(not c.was_closed for c in connections), 0,
                         'Production code left SQLite connections open.')
        for conn in connections:
            with self.assertRaises(sqlite3.ProgrammingError):
                conn.execute('SELECT 1')

    def test_initialization_closes_migration_and_backup_connections(self):
        with tempfile.TemporaryDirectory() as temp, tracked_connections() as connections:
            app = create_app({'TESTING':True, 'DATABASE':str(Path(temp)/'db.sqlite'), 'SECRET_KEY':'test'})
            with app.app_context():
                db.session.remove(); db.engine.dispose()
            self.assert_closed(connections)

    def test_backup_and_restore_release_files_before_return(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            app=create_app({'TESTING':True, 'DATABASE':str(root/'live.sqlite'), 'SECRET_KEY':'test'})
            app.instance_path=str(root/'instance')
            with app.app_context():
                try:
                    with tracked_connections() as connections:
                        backup(root/'backup.zip')
                        restore(root/'backup.zip',root/'restored')
                        self.assert_closed(connections)
                finally:
                    db.session.remove(); db.engine.dispose()

    def test_transaction_commit_rollback_and_exception_close(self):
        with tempfile.TemporaryDirectory() as temp, tracked_connections() as connections:
            path=Path(temp)/'transactions.sqlite'
            with sqlite_connection(path) as conn:
                conn.execute('CREATE TABLE amounts(value INTEGER NOT NULL)')
                conn.execute('INSERT INTO amounts VALUES (120000)')
            with self.assertRaisesRegex(ValueError,'cancelled'):
                with sqlite_connection(path) as conn:
                    conn.execute('INSERT INTO amounts VALUES (999999)')
                    raise ValueError('cancelled')
            with sqlite_connection(path) as conn:
                self.assertEqual(conn.execute('SELECT value FROM amounts').fetchall(),[(120000,)])
            self.assert_closed(connections)

    def test_commit_error_rolls_back_and_closes_connection(self):
        with tempfile.TemporaryDirectory() as temp, tracked_connections() as connections:
            path=Path(temp)/'deferred.sqlite'
            with sqlite_connection(path) as conn:
                conn.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY)')
                conn.execute('CREATE TABLE child(parent_id INTEGER REFERENCES parent(id) DEFERRABLE INITIALLY DEFERRED)')
            with self.assertRaises(sqlite3.IntegrityError):
                with sqlite_connection(path) as conn:
                    conn.execute('PRAGMA foreign_keys=ON')
                    conn.execute('INSERT INTO child VALUES (999)')
            with sqlite_connection(path) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM child').fetchone()[0],0)
            self.assert_closed(connections)


if __name__=='__main__':unittest.main()
