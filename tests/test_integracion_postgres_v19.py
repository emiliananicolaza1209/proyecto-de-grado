"""Los mismos recorridos V19 en un esquema PostgreSQL temporal aislado."""
import os
import unittest
import test_integracion_v19 as scenarios
import test_postgres_integration as postgres


@unittest.skipUnless(os.getenv('CPSTORE_TEST_PG_URL'),
                     'Falta CPSTORE_TEST_PG_URL; PostgreSQL real no validado')
class IntegracionPostgresV19Tests(scenarios.IntegracionV19Tests):
    setUp = postgres.PostgresIntegrationTests.setUp
    tearDown = postgres.PostgresIntegrationTests.tearDown
    clean_schema = postgres.PostgresIntegrationTests.clean_schema
