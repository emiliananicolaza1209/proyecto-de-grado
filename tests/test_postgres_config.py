import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
from app import create_app
from app.extensions import db

class PostgresConfigurationTests(unittest.TestCase):
    def test_postgres_start_does_not_run_sqlite_or_create_tables(self):
        with patch('migrations.upgrade', side_effect=AssertionError('SQLite invoked')), patch.object(db, 'create_all', side_effect=AssertionError('DDL on startup')):
            app = create_app({'TESTING': True, 'SECRET_KEY': 'test', 'DATABASE_URL': 'postgresql://user:password@localhost/cp_test'})
        with app.app_context():
            self.assertEqual(db.engine.name, 'postgresql')
            self.assertEqual(db.engine.driver, 'psycopg')
            for table in db.metadata.sorted_tables:
                sql = str(CreateTable(table).compile(dialect=postgresql.dialect()))
                self.assertNotIn('PRAGMA', sql)
            self.assertIn('BIGINT', str(CreateTable(db.metadata.tables['equipment']).compile(dialect=postgresql.dialect())))
            db.engine.dispose()

    def test_sqlite_tests_do_not_inherit_cloud_database(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'DATABASE_URL': 'postgresql://invalid:invalid@invalid/invalid'}):
            app = create_app({'TESTING': True, 'SECRET_KEY': 'test', 'DATABASE': str(Path(tmp)/'test.sqlite')})
            with app.app_context():
                self.assertEqual(db.engine.name, 'sqlite')
                db.session.remove(); db.engine.dispose()

    def test_postgres_requires_secret(self):
        with patch.dict('os.environ', {'SECRET_KEY': ''}):
            with self.assertRaisesRegex(ValueError, 'SECRET_KEY'):
                create_app({'TESTING': True, 'DATABASE_URL': 'postgresql://user:password@localhost/cp_test'})
