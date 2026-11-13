"""Mismos recorridos V18.2 sobre PostgreSQL en esquema temporal independiente."""
import os,unittest
import test_jornada_v18_2 as cases
import test_postgres_integration as pg
@unittest.skipUnless(os.getenv('CPSTORE_TEST_PG_URL'),'Falta PostgreSQL de pruebas; no se utiliza DATABASE_URL')
class JornadaPostgresTests(cases.JornadaTests):
    setUp=pg.PostgresIntegrationTests.setUp
    clean_schema=pg.PostgresIntegrationTests.clean_schema
