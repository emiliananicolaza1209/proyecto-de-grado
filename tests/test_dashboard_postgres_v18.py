"""Las mismas reglas del panel contra PostgreSQL real, en esquema cp_test aislado."""
import os
import unittest
from test_dashboard_v18 import DashboardTests as BaseDashboard
from test_postgres_integration import PostgresIntegrationTests as PostgresBase

@unittest.skipUnless(os.getenv('CPSTORE_TEST_PG_URL'), 'PostgreSQL real no configurado; falta CPSTORE_TEST_PG_URL')
class DashboardPostgresTests(BaseDashboard):
    setUp=PostgresBase.setUp
    tearDown=PostgresBase.tearDown
    clean_schema=PostgresBase.clean_schema

# Evitar que unittest vuelva a descubrir clases importadas como pruebas locales.
del BaseDashboard, PostgresBase
