"""Consulta estado_inventario: contrato común, reglas de cifras, permisos y errores."""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlalchemy.exc import OperationalError

from _cleanup import release
from app import create_app
from app.extensions import db
from app.models import Catalogo, Producto
from app.services import consultas_service as cs
from app.services.inventario_service import stats

CLAVES = {'consulta', 'estado', 'mensaje', 'periodo', 'zona', 'fuentes', 'metodo', 'cobertura', 'advertencias',
          'cifras', 'detalle', 'es_estimacion', 'generado_en'}


class InventarioBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'DATABASE': str(Path(self.tmp.name) / 'db.sqlite'), 'SECRET_KEY': 'test'})
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.n = 0

    def tearDown(self):
        release(self.app)
        self.ctx.pop()
        self.tmp.cleanup()

    def item(self, kind, nombre, parent=0):
        c = Catalogo(kind=kind, name=nombre, normal_key=nombre.lower().replace(' ', ''), parent_id=parent, active=1)
        db.session.add(c)
        db.session.flush()
        return c

    def equipo(self, estado='Disponible', costo=100000000, ubicacion=None, referencia=None, archivado=0, origen='Lote', **extra):
        self.n += 1
        p = Producto(imei=f'49015420323{self.n:04d}', model=referencia.name if referencia else 'IPHONE SIN CATALOGO', capacity=128,
                     color='NEGRO', condition='Nuevo', cost_cents=costo, additional_costs=[], source_type=origen,
                     location=ubicacion.name if ubicacion else 'SIN UBICACION', supplier='CP CELULARES', status=estado,
                     archived=archivado, location_id=ubicacion.id if ubicacion else None,
                     reference_id=referencia.id if referencia else None, **extra)
        db.session.add(p)
        db.session.flush()
        return p


class ContratoYCifrasTests(InventarioBase):
    def setUp(self):
        super().setUp()
        self.local = self.item('location', 'LOCAL')
        self.bodega = self.item('location', 'BODEGA')
        self.i13 = self.item('reference', 'IPHONE 13')
        self.i14 = self.item('reference', 'IPHONE 14')
        self.equipo(ubicacion=self.local, referencia=self.i13, costo=100000000)
        self.equipo(ubicacion=self.local, referencia=self.i14, costo=200000000)
        self.equipo(ubicacion=self.bodega, referencia=self.i14, costo=300000000, origen='Retoma')
        self.equipo('Vendido', ubicacion=self.local, referencia=self.i13, costo=999000000)
        self.equipo('En pasamano', ubicacion=self.local, referencia=self.i13, costo=888000000)
        self.equipo('Separado', ubicacion=self.local, referencia=self.i13, costo=777000000)
        self.equipo('Garantía', ubicacion=self.local, referencia=self.i13, costo=666000000)
        self.equipo(archivado=1, ubicacion=self.local, referencia=self.i13, costo=555000000)  # archivado: no cuenta
        db.session.commit()

    def test_contrato_comun_completo(self):
        r = cs.estado_inventario('Propietario')
        self.assertEqual(set(r), CLAVES)
        self.assertEqual(r['consulta'], 'estado_inventario')
        self.assertEqual(r['estado'], 'ok')
        self.assertIn(r['estado'], cs.ESTADOS)
        self.assertFalse(r['es_estimacion'])
        self.assertEqual(r['zona'], cs.ZONA)
        self.assertTrue(r['fuentes'] and r['metodo'])
        self.assertIn('fecha_corte', r['periodo'])

    def test_solo_cuenta_disponibles_no_archivados(self):
        r = cs.estado_inventario('Propietario')
        self.assertEqual(r['cifras']['disponibles'], 3)
        self.assertEqual(r['cifras']['retomas_pool'], 1)
        self.assertEqual(r['cifras']['costo_inmovilizado_cents'], 600000000)

    def test_coincide_con_el_resumen_del_sistema(self):
        r = cs.estado_inventario('Propietario')
        s = stats()
        self.assertEqual((r['cifras']['disponibles'], r['cifras']['costo_inmovilizado_cents']), (s['total'], s['cost']))

    def test_desglose_por_ubicacion_y_referencia(self):
        d = cs.estado_inventario('Propietario')['detalle']
        ubic = {f['ubicacion']: (f['disponibles'], f['costo_inmovilizado_cents']) for f in d['por_ubicacion']}
        self.assertEqual(ubic, {'LOCAL': (2, 300000000), 'BODEGA': (1, 300000000)})
        ref = {f['referencia']: f['disponibles'] for f in d['por_referencia']}
        self.assertEqual(ref, {'IPHONE 14': 2, 'IPHONE 13': 1})
        self.assertEqual(sum(f['disponibles'] for f in d['por_ubicacion']), 3)
        self.assertEqual(sum(f['disponibles'] for f in d['por_referencia']), 3)
        self.assertTrue(all('ubicacion_id' in f for f in d['por_ubicacion']))

    def test_filtros_por_id(self):
        r = cs.estado_inventario('Propietario', ubicacion_id=self.local.id)
        self.assertEqual((r['cifras']['disponibles'], r['cifras']['costo_inmovilizado_cents']), (2, 300000000))
        r = cs.estado_inventario('Propietario', referencia_id=str(self.i14.id))  # el ID puede llegar como texto
        self.assertEqual(r['cifras']['disponibles'], 2)
        r = cs.estado_inventario('Propietario', ubicacion_id=self.bodega.id, referencia_id=self.i14.id)
        self.assertEqual(r['cifras']['disponibles'], 1)
        self.assertEqual(r['periodo']['filtros'], {'ubicacion_id': self.bodega.id, 'referencia_id': self.i14.id})

    def test_filtro_valido_sin_coincidencias_es_cero_real_con_aviso(self):
        r = cs.estado_inventario('Propietario', ubicacion_id=self.bodega.id, referencia_id=self.i13.id)
        self.assertEqual(r['estado'], 'ok')
        self.assertEqual(r['cifras']['disponibles'], 0)
        self.assertEqual(r['cifras']['costo_inmovilizado_cents'], 0)
        self.assertTrue(any('coincide' in a for a in r['advertencias']))

    def test_filtros_invalidos_lanzan_parametro_invalido(self):
        for kw in ({'ubicacion_id': 'abc'}, {'ubicacion_id': 99999}, {'ubicacion_id': -1}, {'referencia_id': self.local.id},
                   {'ubicacion_id': self.i13.id}):
            with self.subTest(kw=kw), self.assertRaises(cs.ParametroInvalido):
                cs.estado_inventario('Propietario', **kw)

    def test_no_devuelve_imei_ni_datos_de_personas(self):
        texto = json.dumps(cs.estado_inventario('Propietario'), ensure_ascii=False)
        for p in db.session.scalars(db.select(Producto)):
            self.assertNotIn(p.imei, texto)
        self.assertNotIn('imei', texto.lower())
        for prohibido in ('supplier', 'proveedor', 'seller', 'responsible', 'password'):
            self.assertNotIn(prohibido, texto.lower())

    def test_importes_en_centavos_enteros(self):
        r = cs.estado_inventario('Propietario')
        self.assertIsInstance(r['cifras']['costo_inmovilizado_cents'], int)
        for f in r['detalle']['por_ubicacion'] + r['detalle']['por_referencia']:
            self.assertIsInstance(f['costo_inmovilizado_cents'], int)

    def test_es_solo_lectura(self):
        antes = [(p.id, p.revision, p.status) for p in db.session.scalars(db.select(Producto).order_by(Producto.id))]
        cs.estado_inventario('Propietario')
        self.assertFalse(db.session.new or db.session.dirty or db.session.deleted)
        db.session.expire_all()
        despues = [(p.id, p.revision, p.status) for p in db.session.scalars(db.select(Producto).order_by(Producto.id))]
        self.assertEqual(antes, despues)


class PermisosTests(InventarioBase):
    def setUp(self):
        super().setUp()
        self.equipo(costo=123400000, ubicacion=self.item('location', 'LOCAL'), referencia=self.item('reference', 'IPHONE 13'))
        db.session.commit()

    def test_sin_autorizacion_para_todo_perfil_distinto_del_propietario(self):
        for rol in ('Administrador', 'Vendedora', 'Inventario', 'Socio', '', None, 'Contador'):
            with self.subTest(rol=rol):
                r = cs.estado_inventario(rol)
                self.assertEqual(r['estado'], 'sin_autorizacion')
                self.assertIsNone(r['cifras'])
                self.assertIsNone(r['detalle'])
                self.assertNotIn('1234000', json.dumps(r))  # ni cifras ni indicios de que existan datos

    def test_la_autorizacion_va_antes_que_la_validacion_de_parametros(self):
        r = cs.estado_inventario('Vendedora', ubicacion_id='no-es-id')
        self.assertEqual(r['estado'], 'sin_autorizacion')

    def test_el_costo_solo_lo_ve_quien_esta_en_roles_con_costo(self):
        with mock.patch.dict(cs.ROLES_CONSULTAS, {'estado_inventario': ('Propietario', 'Administrador', 'Vendedora')}):
            admin = cs.estado_inventario('Administrador')
            vendedora = cs.estado_inventario('Vendedora')
        self.assertEqual(admin['estado'], 'ok')
        self.assertEqual(admin['cifras']['disponibles'], 1)
        self.assertNotIn('costo_inmovilizado_cents', admin['cifras'])
        for rol_resp in (admin, vendedora):
            texto = json.dumps(rol_resp)
            self.assertNotIn('costo', texto)
            self.assertNotIn('1234000', texto)
        with mock.patch.object(cs, 'ROLES_CON_COSTO', ('Propietario', 'Administrador')):
            with mock.patch.dict(cs.ROLES_CONSULTAS, {'estado_inventario': ('Propietario', 'Administrador')}):
                self.assertEqual(cs.estado_inventario('Administrador')['cifras']['costo_inmovilizado_cents'], 123400000)  # configurable


class EstadosTests(InventarioBase):
    def test_sin_datos_cuando_no_hay_equipos_registrados(self):
        r = cs.estado_inventario('Propietario')
        self.assertEqual(r['estado'], 'sin_datos')
        self.assertIsNone(r['cifras'])
        self.assertIsNone(r['detalle'])
        self.assertTrue(r['mensaje'])

    def test_solo_archivados_tambien_es_sin_datos(self):
        self.equipo(archivado=1)
        db.session.commit()
        self.assertEqual(cs.estado_inventario('Propietario')['estado'], 'sin_datos')

    def test_cero_disponibles_con_inventario_registrado_es_ok_no_sin_datos(self):
        self.equipo('Vendido')
        db.session.commit()
        r = cs.estado_inventario('Propietario')
        self.assertEqual(r['estado'], 'ok')
        self.assertEqual(r['cifras']['disponibles'], 0)

    def test_parcial_si_hay_equipos_sin_ubicacion_o_referencia(self):
        local = self.item('location', 'LOCAL')
        ref = self.item('reference', 'IPHONE 13')
        self.equipo(ubicacion=local, referencia=ref)
        self.equipo()  # sin catálogo
        db.session.commit()
        r = cs.estado_inventario('Propietario')
        self.assertEqual(r['estado'], 'parcial')
        self.assertEqual(r['cifras']['disponibles'], 2)  # el total no se pierde
        nombres = [f['ubicacion'] for f in r['detalle']['por_ubicacion']]
        self.assertIn('Sin ubicación', nombres)
        self.assertEqual(r['cobertura']['equipos_sin_clasificar'], 1)
        self.assertTrue(r['advertencias'])

    def test_error_temporal_de_la_base_no_devuelve_cifras_y_la_sesion_sigue_usable(self):
        self.equipo(ubicacion=self.item('location', 'LOCAL'), referencia=self.item('reference', 'IPHONE 13'))
        db.session.commit()
        fallo = OperationalError('SELECT', {}, Exception('database is locked'))
        with mock.patch.object(cs, '_leer_disponibles', side_effect=fallo):
            r = cs.estado_inventario('Propietario')
        self.assertEqual(r['estado'], 'error_temporal')
        self.assertIsNone(r['cifras'])
        self.assertIn('intenta', r['mensaje'].lower())
        self.assertEqual(cs.estado_inventario('Propietario')['estado'], 'ok')  # se recupera al reintentar

    def test_un_error_de_programacion_no_se_disfraza_de_error_temporal(self):
        self.equipo()
        db.session.commit()
        with mock.patch.object(cs, '_leer_disponibles', side_effect=KeyError('bug')):
            with self.assertRaises(KeyError):
                cs.estado_inventario('Propietario')


class PortabilidadTests(unittest.TestCase):
    def test_el_modulo_no_usa_sql_de_sqlite_ni_flask_request(self):
        fuente = (Path(__file__).resolve().parent.parent / 'app' / 'services' / 'consultas_service.py').read_text(encoding='utf-8')
        for prohibido in ('strftime', 'julianday', 'func.date', 'sql_text', 'PRAGMA', 'open_day(', 'BEGIN IMMEDIATE'):
            self.assertNotIn(prohibido, fuente)
        self.assertIsNone(re.search(r'from flask import[^\n]*\b(request|session|g)\b', fuente))
        self.assertNotIn('db.session.add', fuente)
        self.assertNotIn('db.session.commit', fuente)


if __name__ == '__main__':
    unittest.main()
