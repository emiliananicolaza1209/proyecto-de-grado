"""Mismo control de acceso sobre PostgreSQL aislado de CI."""
import os
import unittest
import test_accesos_v20 as cases
import test_postgres_integration as pg


@unittest.skipUnless(os.getenv('CPSTORE_TEST_PG_URL'),'Falta PostgreSQL de pruebas; no se utiliza DATABASE_URL')
class AccessPostgresTests(cases.AccessTests):
    setUp=pg.PostgresIntegrationTests.setUp
    clean_schema=pg.PostgresIntegrationTests.clean_schema
