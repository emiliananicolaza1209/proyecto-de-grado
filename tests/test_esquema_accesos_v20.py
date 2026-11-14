"""Actualización aditiva 2 → 3, repetición y rollback de DDL PostgreSQL."""
import os
import unittest
from unittest.mock import patch
from sqlalchemy import Table, inspect, text
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.schema import CreateTable
from app.extensions import db
from app.database import initialize_postgres
from app.models.gestion import PermisosUsuario
import test_postgres_esquema_v2 as fixture


class AccessSchemaDefinitionTests(unittest.TestCase):
    def test_additive_table_ddl_has_user_fk_and_no_business_columns(self):
        sql=str(CreateTable(PermisosUsuario.__table__).compile(dialect=dialect()))
        self.assertIn('REFERENCES usuarios (id)',sql)
        self.assertIn('permisos JSON NOT NULL',sql)
        self.assertNotIn('finance_operation',sql)
        self.assertNotIn('ALTER',sql)


@unittest.skipUnless(os.getenv('CPSTORE_TEST_PG_URL'),'Falta PostgreSQL de pruebas; no se utiliza DATABASE_URL')
class AccessSchemaPostgresTests(unittest.TestCase):
    setUp=fixture.EsquemaV2PostgresTests.setUp
    clean_schema=fixture.EsquemaV2PostgresTests.clean_schema

    def old_v2(self):
        initialize_postgres()
        with db.engine.begin() as conn:
            conn.execute(text('DROP TABLE permisos_usuario'))
            conn.execute(text('UPDATE cp_schema_revision SET version=2'))
            conn.execute(text("INSERT INTO usuarios (id,nombre,login,password_hash,rol,activo,session_version) VALUES (900,'PRUEBA','prueba-v2','hash-no-utilizable','Administrador',true,7)"))

    def test_v2_to_v3_keeps_users_money_and_session_versions(self):
        self.old_v2()
        with db.engine.connect() as conn:
            counts={t:conn.scalar(text(f'SELECT count(*) FROM "{t}"')) for t in inspect(conn).get_table_names()}
        self.assertEqual(initialize_postgres(allow_create=False),'actualizada')
        with db.engine.connect() as conn:
            for table,count in counts.items():self.assertEqual(conn.scalar(text(f'SELECT count(*) FROM "{table}"')),count)
            self.assertEqual(conn.scalar(text('SELECT session_version FROM usuarios WHERE id=900')),7)
            self.assertEqual(conn.scalar(text('SELECT version FROM cp_schema_revision')),3)
        self.assertFalse(initialize_postgres(allow_create=False))

    def test_creation_failure_keeps_v2_and_previous_records(self):
        self.old_v2();original=Table.create
        def fail(table,*args,**kwargs):
            if table.name=='permisos_usuario':raise RuntimeError('DDL simulado')
            return original(table,*args,**kwargs)
        with patch.object(Table,'create',autospec=True,side_effect=fail):
            with self.assertRaises(RuntimeError):initialize_postgres(allow_create=False)
        with db.engine.connect() as conn:
            self.assertEqual(conn.scalar(text('SELECT version FROM cp_schema_revision')),2)
            self.assertEqual(conn.scalar(text('SELECT session_version FROM usuarios WHERE id=900')),7)
            self.assertNotIn('permisos_usuario',inspect(conn).get_table_names())
