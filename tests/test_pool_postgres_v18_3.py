"""Mismos recorridos en PostgreSQL: esquema temporal independiente."""
import os,unittest
import test_pool_v18_3 as cases
import test_postgres_integration as pg
@unittest.skipUnless(os.getenv('CPSTORE_TEST_PG_URL'),'Falta PostgreSQL de pruebas; no se utiliza DATABASE_URL')
class PoolDatesPostgresTests(cases.PoolDatesTests):
    setUp=pg.PostgresIntegrationTests.setUp
    clean_schema=pg.PostgresIntegrationTests.clean_schema
