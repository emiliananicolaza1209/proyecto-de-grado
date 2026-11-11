"""Pruebas optativas contra PostgreSQL real, en un esquema temporal aislado.
CPSTORE_TEST_PG_URL debe apuntar a una base de desarrollo, nunca a producción.
No utiliza DATABASE_URL para evitar ejecutar pruebas por accidente en datos reales.
"""
import os
import uuid
import unittest
from unittest.mock import patch
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from app import create_app
from app.extensions import db
from app.database import initialize_postgres
import test_gestion_v16 as gestion_tests

@unittest.skipUnless(os.getenv('CPSTORE_TEST_PG_URL'), 'Falta CPSTORE_TEST_PG_URL; PostgreSQL real no validado')
class PostgresIntegrationTests(unittest.TestCase):
    product = gestion_tests.GestionTests.product
    sale = gestion_tests.GestionTests.sale
    settlement = gestion_tests.GestionTests.settlement
    test_credit_18_percent_and_actual_deposit_only_on_receipt = gestion_tests.GestionTests.test_credit_18_percent_and_actual_deposit_only_on_receipt
    test_manual_net_plus_actual_initial_no_double_discount = gestion_tests.GestionTests.test_manual_net_plus_actual_initial_no_double_discount
    test_financed_equipment_partial_then_full_no_duplicate_bank = gestion_tests.GestionTests.test_financed_equipment_partial_then_full_no_duplicate_bank

    def setUp(self):
        self.schema = 'cp_test_' + uuid.uuid4().hex
        url = make_url(os.environ['CPSTORE_TEST_PG_URL']).set(drivername='postgresql+psycopg')
        self.control = create_engine(url, pool_pre_ping=True)
        with self.control.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        self.addCleanup(self.clean_schema)
        def postgres_app(config):
            config.update(DATABASE_URL=url.render_as_string(hide_password=False),
                          SQLALCHEMY_ENGINE_OPTIONS={'connect_args': {
                              'options': f'-c search_path={self.schema} -c timezone=UTC',
                              'connect_timeout': 10}})
            app = create_app(config)
            with app.app_context():
                initialize_postgres()
            return app
        with patch('test_gestion_v16.create_app', postgres_app):
            gestion_tests.GestionTests.setUp(self)

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.ctx.pop()
        self.tmp.cleanup()

    def clean_schema(self):
        with self.control.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))
        self.control.dispose()

    def test_reinitialize_keeps_records_and_large_money(self):
        from app.models import Producto
        p = self.product(cost=3000000000)
        self.assertFalse(initialize_postgres())
        db.session.expire_all()
        self.assertEqual(db.session.get(Producto, p.id).cost_cents, 3000000000)
