"""Versión 2 del esquema PostgreSQL: agrega solo ingresos_gastos, correcciones_clasificacion y reportes_generados.

Las pruebas que necesitan PostgreSQL real son optativas (CPSTORE_TEST_PG_URL, una base de desarrollo, nunca producción) y trabajan en un
esquema temporal propio que se elimina al terminar; nunca usan DATABASE_URL ni tocan el esquema public.
"""
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import click
from sqlalchemy import Table, create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateTable

from _cleanup import release
from app import create_app
from app.database import SCHEMA_V2_TABLES, SCHEMA_VERSION, initialize_postgres, seed_catalogs
from app.extensions import db

NUEVAS = {'ingresos_gastos', 'correcciones_clasificacion', 'reportes_generados'}


class DefinicionTests(unittest.TestCase):
    """Corren siempre (sin PostgreSQL)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'DATABASE': str(Path(self.tmp.name) / 'db.sqlite'), 'SECRET_KEY': 'test'})
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.ctx.pop)
        self.addCleanup(release, self.app)

    def test_valor_cents_de_ingresos_gastos_es_biginteger(self):
        from sqlalchemy import BigInteger
        from sqlalchemy.dialects import postgresql
        from sqlalchemy.schema import CreateTable
        columna = db.metadata.tables['ingresos_gastos'].c.valor_cents
        self.assertIsInstance(columna.type, BigInteger)
        ddl = str(CreateTable(db.metadata.tables['ingresos_gastos']).compile(dialect=postgresql.dialect()))
        self.assertRegex(ddl, r'valor_cents\s+BIGINT')

    def test_la_version_del_esquema_es_2_y_las_tablas_nuevas_son_exactamente_tres(self):
        self.assertEqual(SCHEMA_VERSION, 2)
        self.assertEqual(set(SCHEMA_V2_TABLES), NUEVAS)
        self.assertEqual(len(SCHEMA_V2_TABLES), 3)
        self.assertTrue(NUEVAS.issubset(db.metadata.tables))

    def test_el_ddl_de_las_tablas_nuevas_es_valido_en_postgresql_y_no_toca_otras_tablas(self):
        for nombre in SCHEMA_V2_TABLES:
            sql = str(CreateTable(db.metadata.tables[nombre]).compile(dialect=postgresql.dialect()))
            self.assertIn(f'CREATE TABLE {nombre}', sql)
            self.assertNotIn('PRAGMA', sql)
            self.assertNotIn('REFERENCES', sql)  # no dependen de otras tablas: crearlas no puede afectar ninguna existente
            self.assertNotIn('ALTER', sql.upper())

    def test_no_se_puede_usar_con_sqlite(self):
        with self.assertRaises(click.ClickException):
            initialize_postgres()

    def test_el_comando_de_actualizacion_solo_actualiza_una_base_existente(self):
        with patch('app.database.initialize_postgres', return_value='actualizada') as update:
            r = self.app.test_cli_runner().invoke(args=['actualizar-postgres'])
        self.assertEqual(r.exit_code, 0)
        update.assert_called_once_with(allow_create=False)
        self.assertIn('tres tablas', r.output)

    def test_el_codigo_solo_crea_las_tablas_nuevas_al_subir_de_version(self):
        fuente = (Path(__file__).resolve().parent.parent / 'app' / 'database.py').read_text(encoding='utf-8')
        subida = fuente[fuente.index('if version == 1:'):fuente.index('raise click.ClickException(\'Versión de esquema no compatible')]
        for peligroso in ('drop_all', 'DROP ', 'DELETE', 'TRUNCATE', 'create_all', 'ALTER', 'insert('):
            self.assertNotIn(peligroso, subida)


@unittest.skipUnless(os.getenv('CPSTORE_TEST_PG_URL'), 'Falta CPSTORE_TEST_PG_URL; PostgreSQL real no validado')
class EsquemaV2PostgresTests(unittest.TestCase):
    def setUp(self):
        self.schema = 'cp_test_' + uuid.uuid4().hex
        url = make_url(os.environ['CPSTORE_TEST_PG_URL']).set(drivername='postgresql+psycopg')
        self.control = create_engine(url, pool_pre_ping=True)
        with self.control.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        self.addCleanup(self.clean_schema)
        self.app = create_app({
            'TESTING': True, 'SECRET_KEY': 'test', 'DATABASE_URL': url.render_as_string(hide_password=False),
            'SQLALCHEMY_ENGINE_OPTIONS': {'connect_args': {'options': f'-c search_path={self.schema} -c timezone=UTC', 'connect_timeout': 10}}})
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.addCleanup(self.ctx.pop)
        self.addCleanup(db.engine.dispose)
        self.addCleanup(db.session.remove)

    def clean_schema(self):
        with self.control.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))
        with self.control.connect() as conn:
            quedan = conn.scalar(text('SELECT count(*) FROM pg_namespace WHERE nspname = :n'), {'n': self.schema})
        self.control.dispose()
        self.assertEqual(quedan, 0, 'El esquema temporal debe borrarse al terminar')

    # --- ayudas -------------------------------------------------------------------------------------------------------
    def tablas(self):
        with db.engine.connect() as conn:
            return set(inspect(conn).get_table_names())

    def version(self):
        with db.engine.connect() as conn:
            return conn.scalar(text('SELECT version FROM cp_schema_revision'))

    def conteos(self):
        with db.engine.connect() as conn:
            return {t: conn.scalar(text(f'SELECT count(*) FROM "{t}"')) for t in sorted(inspect(conn).get_table_names())}

    def base_en_version_1(self, con_tablas_nuevas=()):
        """Una base como la que dejó la versión 1: sin las tres tablas contables, con catálogos y revisión 1."""
        resto = [t for t in db.metadata.sorted_tables if t.name not in NUEVAS or t.name in con_tablas_nuevas]
        with db.engine.begin() as conn:
            db.metadata.create_all(conn, tables=resto)
            seed_catalogs(conn)
            conn.execute(text('CREATE TABLE cp_schema_revision (version INTEGER PRIMARY KEY)'))
            conn.execute(text('INSERT INTO cp_schema_revision(version) VALUES (1)'))

    # --- pruebas ------------------------------------------------------------------------------------------------------
    def test_una_base_nueva_se_crea_ya_en_version_2_con_las_tres_tablas(self):
        self.assertEqual(initialize_postgres(), 'creada')
        self.assertEqual(self.version(), 2)
        self.assertTrue(NUEVAS.issubset(self.tablas()))
        self.assertEqual(set(db.metadata.tables) | {'cp_schema_revision'}, self.tablas())
        self.assertFalse(initialize_postgres())
        self.assertEqual(self.version(), 2)

    def test_actualizar_se_niega_a_crear_una_base_vacia(self):
        with self.assertRaisesRegex(click.ClickException, 'No existe una versión'):
            initialize_postgres(allow_create=False)
        self.assertFalse(self.tablas())

    def test_actualizar_una_base_existente_conserva_sus_filas(self):
        self.base_en_version_1()
        antes = self.conteos()
        self.assertEqual(initialize_postgres(allow_create=False), 'actualizada')
        despues = self.conteos()
        self.assertEqual({t: n for t, n in despues.items() if t not in NUEVAS}, antes)
        self.assertTrue(NUEVAS.issubset(self.tablas()))
        self.assertEqual(set(db.metadata.tables) | {'cp_schema_revision'}, self.tablas())
        self.assertFalse(initialize_postgres())  # repetirla no hace nada
        self.assertEqual(self.version(), 2)

    def test_una_base_en_version_1_sube_a_2_y_no_toca_ningun_dato(self):
        self.base_en_version_1()
        self.assertFalse(NUEVAS & self.tablas())
        antes = self.conteos()
        self.assertGreater(antes['catalog'], 0)
        self.assertEqual(initialize_postgres(), 'actualizada')
        self.assertEqual(self.version(), 2)
        despues = self.conteos()
        self.assertEqual({t: n for t, n in despues.items() if t not in NUEVAS}, antes)  # ninguna otra tabla cambió
        self.assertEqual({despues[t] for t in NUEVAS}, {0})
        self.assertEqual(set(db.metadata.tables) | {'cp_schema_revision'}, self.tablas())
        self.assertFalse(initialize_postgres())  # idempotente

    def test_subir_dos_veces_o_con_una_tabla_nueva_ya_creada_respeta_sus_filas(self):
        self.base_en_version_1(con_tablas_nuevas=('ingresos_gastos',))
        with db.engine.begin() as conn:
            conn.execute(text("INSERT INTO ingresos_gastos (tipo, concepto, categoria, valor_cents, fecha, relacion, soporte_ref, responsable, created_at) "
                              "VALUES ('INGRESO', 'prueba', 'OTRO', 1000, '2026-11-11', '', '', '', now())"))
        self.assertEqual(initialize_postgres(), 'actualizada')
        self.assertEqual(self.conteos()['ingresos_gastos'], 1)
        self.assertTrue(NUEVAS.issubset(self.tablas()))
        self.assertFalse(initialize_postgres())
        self.assertEqual(self.conteos()['ingresos_gastos'], 1)

    def test_una_version_desconocida_se_rechaza_sin_modificar_nada(self):
        self.base_en_version_1()
        with db.engine.begin() as conn:
            conn.execute(text('UPDATE cp_schema_revision SET version = 7'))
        antes_tablas, antes_conteos = self.tablas(), self.conteos()
        with self.assertRaisesRegex(click.ClickException, 'no compatible'):
            initialize_postgres()
        self.assertEqual((self.tablas(), self.conteos(), self.version()), (antes_tablas, antes_conteos, 7))
        with db.engine.begin() as conn:
            conn.execute(text('UPDATE cp_schema_revision SET version = 0'))
        with self.assertRaisesRegex(click.ClickException, 'no compatible'):
            initialize_postgres()
        self.assertFalse(NUEVAS & self.tablas())

    def test_una_base_en_version_1_incompleta_no_se_toca(self):
        self.base_en_version_1()
        with db.engine.begin() as conn:
            conn.execute(text('DROP TABLE usuarios CASCADE'))
        with self.assertRaisesRegex(click.ClickException, 'Faltan tablas'):
            initialize_postgres()
        self.assertFalse(NUEVAS & self.tablas())
        self.assertEqual(self.version(), 1)

    def test_una_base_en_version_2_incompleta_se_rechaza(self):
        initialize_postgres()
        with db.engine.begin() as conn:
            conn.execute(text('DROP TABLE reportes_generados'))
        with self.assertRaisesRegex(click.ClickException, 'Faltan tablas'):
            initialize_postgres()
        self.assertEqual(self.version(), 2)

    def test_si_algo_falla_a_la_mitad_no_queda_nada_a_medias(self):
        self.base_en_version_1()
        original, llamadas = Table.create, []

        def fallando(tabla, bind=None, checkfirst=False):
            llamadas.append(tabla.name)
            if len(llamadas) == 2:
                raise RuntimeError('fallo simulado')
            return original(tabla, bind, checkfirst)

        antes = self.conteos()
        with patch.object(Table, 'create', autospec=True, side_effect=fallando):
            with self.assertRaises(RuntimeError):
                initialize_postgres()
        self.assertFalse(NUEVAS & self.tablas())  # la primera tabla creada se deshizo con la transacción
        self.assertEqual((self.version(), self.conteos()), (1, antes))
        self.assertEqual(initialize_postgres(), 'actualizada')  # y se puede volver a intentar
        self.assertEqual(self.version(), 2)


if __name__ == '__main__':
    unittest.main()
