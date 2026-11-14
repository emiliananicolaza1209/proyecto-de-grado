"""La prueba de migración debe cerrar también las conexiones del pool descartado.

Retiene conexiones SQLite reales para impedir que su destrucción por el GC
oculte el error de ciclo de vida en sistemas que permiten borrar archivos abiertos.
"""
import sqlite3
import unittest

from sqlalchemy import event
from sqlalchemy.engine import Engine
import test_finance_distribution_v14 as fixture


class MigrationConnectionTests(unittest.TestCase):
    def test_migration_releases_every_real_connection(self):
        connections = []

        def connected(connection, _record):
            connections.append(connection)

        case = fixture.DistributionTests('test_migration_preserves_existing_accounting_records')
        result = unittest.TestResult()
        event.listen(Engine, 'connect', connected)
        try:
            case.run(result)
            self.assertTrue(result.wasSuccessful(), str(result.errors + result.failures))
            self.assertTrue(connections, 'Debe abrir conexiones reales, no simuladas.')
            for connection in connections:
                with self.assertRaises(sqlite3.ProgrammingError):
                    connection.execute('SELECT 1')
        finally:
            event.remove(Engine, 'connect', connected)
            for connection in connections:
                connection.close()
            if hasattr(case, 'tmp'):
                case.tmp.cleanup()
