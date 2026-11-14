"""Unión Andres + desarrollo: las migraciones v17/v18 y el esquema final sobre bases de ambos orígenes.

Escenarios (todos sobre copias temporales; nunca se toca instance/ ni el respaldo):
  A. BD de ensayo con el esquema de Andres (v1..v12), reconstruido del commit histórico.
  B. BD con el esquema de desarrollo (hasta v16, sin las tablas contables de Andres).
  C. BD fresca.

La comprobación del respaldo privado original se conserva por separado en
validar_respaldo_andres.py y no se presenta como ejecutada por estos casos.
"""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from _cleanup import release
from app import create_app
from app.extensions import db
from migrations.contabilidad_v17 import upgrade_v17, upgrade_v18

ESQUEMA_ANDRES = Path(__file__).parent / 'fixtures' / 'andres_v12_c6ef7c0.sql'
TABLAS_ANDRES = ('reportes_generados', 'ingresos_gastos', 'correcciones_clasificacion')


def tablas(path):
    with closing(sqlite3.connect(str(path))) as conn:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def versiones(path):
    with closing(sqlite3.connect(str(path))) as conn:
        return [r[0] for r in conn.execute('SELECT version FROM schema_version ORDER BY version')]


def columnas(path, tabla):
    with closing(sqlite3.connect(str(path))) as conn:
        return {r[1] for r in conn.execute(f'PRAGMA table_info("{tabla}")')}


class UnionBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'union.sqlite'
        self.apps = []

    def tearDown(self):
        for app in self.apps:
            release(app)
        self.tmp.cleanup()

    def migrar(self):
        app = create_app({'TESTING': True, 'DATABASE': str(self.path), 'SECRET_KEY': 'tests'})
        self.apps.append(app)
        return app

    def assert_esquema_completo(self, app, esperadas=()):
        """Toda tabla y toda columna de los modelos unidos existe en la BD migrada."""
        existentes = tablas(self.path)
        with app.app_context():
            modelos = {t.name: {c.name for c in t.columns} for t in db.metadata.sorted_tables}
        faltan_tablas = (set(modelos) | set(esperadas)) - existentes
        self.assertFalse(faltan_tablas, f'Tablas que faltan: {sorted(faltan_tablas)}')
        faltan_cols = {t: sorted(c - columnas(self.path, t)) for t, c in modelos.items() if c - columnas(self.path, t)}
        self.assertFalse(faltan_cols, f'Columnas que faltan: {faltan_cols}')


class BaseConEsquemaDeAndres(UnionBase):
    def preparar_base(self):
        """DDL histórico fijo: no lo genera el código que se está probando."""
        with closing(sqlite3.connect(str(self.path))) as conn, conn:
            conn.executescript(ESQUEMA_ANDRES.read_text(encoding='utf-8'))
            conn.execute("INSERT INTO personas_contables(id,nombre,identificacion,tipo) VALUES(101,'PERSONA DE ENSAYO','ENSAYO-101','Natural')")
            conn.execute("INSERT INTO bancos_destino(id,nombre) VALUES(101,'BANCO DE ENSAYO')")
            conn.execute("INSERT INTO consignaciones_bancarias(id,persona_id,banco_id,monto,fecha,referencia) VALUES(101,101,101,25000.25,'2026-09-30 10:11:12','ENSAYO-101')")
            conn.execute("""INSERT INTO equipment(id,imei,model,capacity,color,condition,cost_cents,location,supplier,
                status,seller,sale_value_cents,paid_cents,sale_date,payment_status)
                VALUES(101,'990000000000101','EQUIPO DE ENSAYO',128,'AZUL','Nuevo',30000000,
                    'LOCAL CP STORE','PROVEEDOR DE ENSAYO','Vendido','VENDEDORA DE ENSAYO',50000000,10000000,'2026-09-30','Abono')""")
            conn.execute("""INSERT INTO customer_collection(id,product_id,amount_cents,destination,collector,method,effective_date,note)
                VALUES(101,101,10000000,'Negocio','VENDEDORA DE ENSAYO','Efectivo','2026-09-30','COBRO FICTICIO')""")
            conn.execute("""INSERT INTO admin_receipt(id,collection_id,amount_cents,administrator,method,effective_date,note)
                VALUES(101,101,10000000,'ADMINISTRACION DE ENSAYO','Efectivo','2026-09-30','RECEPCION FICTICIA')""")
            # Configuración antigua deliberada, tanto abierta como cerrada: v19 no debe reescribirla.
            config = json.dumps({'opening': 1234500, 'accounts': ['EFECTIVO', 'BANCO'], 'staff': []})
            snapshot = json.dumps({'utilidad': 19500000, 'efectivo_entregado': 9500000, 'ensayo': True})
            conn.execute("INSERT INTO finance_day(id,date,status,config,snapshot) VALUES(101,'2026-09-30','Cerrada',?,?)", (config, snapshot))
            conn.execute("INSERT INTO finance_day(id,date,status,config) VALUES(102,'2026-09-29','Abierta',?)", (config,))
            conn.execute("""INSERT INTO finance_operation(id,day_id,token,kind,description,seller,amount,minor_cost,product_id,costs,payments)
                VALUES(101,101,'ENSAYO-OPERACION-101','Venta','VENTA FICTICIA','VENDEDORA DE ENSAYO',50000000,500000,101,
                    '[{"supplier":"PROVEEDOR DE ENSAYO","amount":30000000}]','[{"account":"EFECTIVO","amount":10000000}]')""")
            conn.execute("""INSERT INTO finance_supplier_payment(id,day_id,operation_id,cost_index,amount,account,token)
                VALUES(101,101,101,0,1000000,'EFECTIVO','ENSAYO-PAGO-101')""")
            conn.execute("INSERT INTO finance_audit(id,day_id,action,reason,detail) VALUES(101,101,'ENSAYO','REGISTRO FICTICIO','{}')")

    def setUp(self):
        super().setUp()
        self.preparar_base()
        with closing(sqlite3.connect(str(self.path))) as conn, conn:
            conn.execute("INSERT INTO reportes_generados(fecha_ini,fecha_fin,actor,totales_json) VALUES('2026-09-01','2026-09-30','ANA','{}')")
            conn.execute("INSERT INTO ingresos_gastos(tipo,concepto,valor_cents,fecha) VALUES('GASTO','ARRIENDO LOCAL',150000000,'2026-09-05')")
            conn.execute("INSERT INTO correcciones_clasificacion(entidad_id,anterior,nueva,motivo) VALUES(1,'OTRO','ARRIENDO','prueba')")
        self.antes = {t: self.filas(t) for t in TABLAS_ANDRES}
        with closing(sqlite3.connect(str(self.path))) as conn:
            self.columnas_legado = {t: tuple(r[1] for r in conn.execute(f'PRAGMA table_info("{t}")'))
                                    for t in tablas(self.path) - {'schema_version', 'catalog'}}
        self.antes_legado = self.estado_legado()

    def filas(self, tabla):
        with closing(sqlite3.connect(str(self.path))) as conn:
            return conn.execute(f'SELECT * FROM {tabla} ORDER BY id').fetchall()

    def estado_legado(self):
        """Compara columnas originales, aunque la migración añada otras nuevas."""
        with closing(sqlite3.connect(str(self.path))) as conn:
            return {t: conn.execute('SELECT ' + ','.join(f'"{c}"' for c in cols) +
                                    f' FROM "{t}" ORDER BY id').fetchall()
                    for t, cols in self.columnas_legado.items()}

    def test_parte_de_v1_a_v12_con_las_tablas_de_andres(self):
        self.assertEqual(versiones(self.path), list(range(1, 13)))
        self.assertTrue(set(TABLAS_ANDRES) <= tablas(self.path))
        self.assertNotIn('person_id', columnas(self.path, 'finance_operation'))
        self.assertNotIn('activa', columnas(self.path, 'consignaciones_bancarias'))
        self.assertNotIn('usuarios', tablas(self.path))

    def test_migra_a_la_version_unida_y_existen_las_tablas_de_ambos_lados(self):
        originales = tablas(self.path)
        app = self.migrar()
        self.assert_esquema_completo(app, esperadas=originales)
        for tabla in ('usuarios', 'persona_banco', 'historial_consignaciones'):  # lado desarrollo
            self.assertIn(tabla, tablas(self.path))
        self.assertTrue(set(TABLAS_ANDRES) <= tablas(self.path))  # lado Andres
        self.assertTrue({17, 18} <= set(versiones(self.path)))

    def test_conserva_filas_y_no_duplica_versiones(self):
        self.migrar()
        self.assertEqual({t: self.filas(t) for t in TABLAS_ANDRES}, self.antes)
        self.assertEqual(self.estado_legado(), self.antes_legado)
        with closing(sqlite3.connect(str(self.path))) as conn:
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        vs = versiones(self.path)
        self.assertEqual(len(vs), len(set(vs)))
        self.assertEqual(vs.count(17), 1)
        self.assertEqual(vs.count(18), 1)

    def test_segunda_migracion_no_cambia_nada(self):
        self.migrar()
        v1, t1 = versiones(self.path), tablas(self.path)
        datos = {t: self.filas(t) for t in TABLAS_ANDRES}
        datos_legado = self.estado_legado()
        self.migrar()
        self.assertEqual((versiones(self.path), tablas(self.path)), (v1, t1))
        self.assertEqual({t: self.filas(t) for t in TABLAS_ANDRES}, datos)
        self.assertEqual(self.estado_legado(), datos_legado)

    def test_deja_copias_bak_antes_de_cada_migracion(self):
        self.migrar()
        for sufijo, version in (('.antes_v19.bak', 19), ('.antes_v17.bak', 17), ('.antes_v18.bak', 18)):
            bak = Path(str(self.path) + sufijo)
            self.assertTrue(bak.exists(), sufijo)
            with closing(sqlite3.connect(str(bak))) as conn:  # la copia es el estado ANTERIOR a esa versión
                self.assertNotIn(version, [r[0] for r in conn.execute('SELECT version FROM schema_version')], sufijo)
                self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                for tabla in TABLAS_ANDRES:
                    self.assertEqual(conn.execute(f'SELECT * FROM {tabla} ORDER BY id').fetchall(), self.antes[tabla])

    def test_v19_agrega_la_estructura_de_desarrollo_sin_tocar_jornadas(self):
        with closing(sqlite3.connect(str(self.path))) as conn:
            jornadas = conn.execute('SELECT * FROM finance_day ORDER BY id').fetchall()
            self.assertNotIn('person_id', {r[1] for r in conn.execute('PRAGMA table_info(finance_operation)')})
        self.migrar()
        self.assertIn('person_id', columnas(self.path, 'finance_operation'))
        self.assertIn('activa', columnas(self.path, 'consignaciones_bancarias'))
        with closing(sqlite3.connect(str(self.path))) as conn:
            self.assertEqual(conn.execute('SELECT * FROM finance_day ORDER BY id').fetchall(), jornadas)
        self.assertEqual(self.estado_legado(), self.antes_legado)


class BaseConEsquemaDeDesarrollo(UnionBase):
    def setUp(self):
        super().setUp()
        # Base fresca con el código unido y luego se le quita lo que solo existe por Andres:
        # queda con el esquema de desarrollo (v1..v16, sin v17/v18 ni tablas contables de Andres).
        release(self.migrar())
        with closing(sqlite3.connect(str(self.path))) as conn, conn:
            for t in TABLAS_ANDRES:
                conn.execute(f'DROP TABLE {t}')
            conn.execute('DELETE FROM schema_version WHERE version IN (17,18)')
        for sufijo in ('.antes_v17.bak', '.antes_v18.bak'):
            Path(str(self.path) + sufijo).unlink(missing_ok=True)
        self.apps.clear()
        self.assertFalse(set(TABLAS_ANDRES) & tablas(self.path))
        self.assertNotIn(17, versiones(self.path))

    def test_migra_a_la_version_unida_y_existen_las_tablas_de_ambos_lados(self):
        app = self.migrar()
        self.assert_esquema_completo(app)
        self.assertTrue(set(TABLAS_ANDRES) <= tablas(self.path))
        self.assertTrue({17, 18} <= set(versiones(self.path)))

    def test_recrea_la_tabla_aunque_el_numero_de_version_ya_este_registrado(self):
        """Revisa la tabla y no solo el número: v17 registrada + tabla borrada se repara."""
        app = self.migrar()
        release(app)
        with closing(sqlite3.connect(str(self.path))) as conn, conn:
            conn.execute('DROP TABLE reportes_generados')
        self.assertIn(17, versiones(self.path))
        upgrade_v17(self.path)
        self.assertIn('reportes_generados', tablas(self.path))
        self.assertEqual(versiones(self.path).count(17), 1)

    def test_v17_y_v18_son_idempotentes(self):
        self.migrar()
        for _ in range(2):
            upgrade_v17(self.path)
            upgrade_v18(self.path)
        vs = versiones(self.path)
        self.assertEqual((vs.count(17), vs.count(18)), (1, 1))


class BaseFresca(UnionBase):
    def test_base_fresca_tiene_todo_y_v17_v18(self):
        app = self.migrar()
        self.assert_esquema_completo(app)
        self.assertTrue(set(TABLAS_ANDRES) <= tablas(self.path))
        self.assertTrue({17, 18} <= set(versiones(self.path)))


if __name__ == '__main__':
    unittest.main()
