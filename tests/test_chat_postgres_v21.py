"""La lectura de cierres del chat también se verifica en PostgreSQL temporal."""
import os
import unittest
import test_chat_periodos_v21 as cases
import test_postgres_integration as pg


@unittest.skipUnless(os.getenv('CPSTORE_TEST_PG_URL'), 'Falta PostgreSQL de pruebas; no se utiliza DATABASE_URL')
class ChatCierrePostgresTests(cases.ChatCierreTests):
    clean_schema = pg.PostgresIntegrationTests.clean_schema

    def setUp(self):
        pg.PostgresIntegrationTests.setUp(self)
        self.hoy = self.day
        self.n = 0
        self.app.config['AUTH_REQUIRED'] = True
