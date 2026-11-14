"""El recorrido de ajustes también corre en el PostgreSQL efímero de CI."""
import os
import unittest
import test_ajustes_pool_v19 as cases
import test_postgres_integration as pg


@unittest.skipUnless(os.getenv('CPSTORE_TEST_PG_URL'), 'Falta PostgreSQL de pruebas; no se utiliza DATABASE_URL')
class AjustesPoolPostgresTests(cases.AjustesPoolTests):
    setUp=pg.PostgresIntegrationTests.setUp
    clean_schema=pg.PostgresIntegrationTests.clean_schema
