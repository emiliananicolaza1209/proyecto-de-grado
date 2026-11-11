"""permanencia_inventario: días en inventario de cada equipo disponible, baja rotación sobre un umbral, costo solo para el Propietario, sin IMEI."""
import json
import unittest
from datetime import date, timedelta
from unittest import mock

from sqlalchemy.exc import OperationalError

from test_consulta_estado_inventario import InventarioBase
from app.extensions import db
from app.models import Catalogo, Producto
from app.models.lote import Lote
from app.services import consultas_service as cs

HOY = '2026-11-11'
CLAVES = {'consulta', 'estado', 'mensaje', 'periodo', 'zona', 'fuentes', 'metodo', 'cobertura', 'advertencias',
          'cifras', 'detalle', 'es_estimacion', 'generado_en'}


def hace(dias):
    return (date.fromisoformat(HOY) - timedelta(days=dias)).isoformat()


class PermanenciaBase(InventarioBase):
    def setUp(self):
        super().setUp()
        parche = mock.patch.object(cs, 'today', return_value=HOY)
        parche.start()
        self.addCleanup(parche.stop)
        self.local = self.item('location', 'LOCAL')
        self.i13 = self.item('reference', 'IPHONE 13')
        self.i14 = self.item('reference', 'IPHONE 14')

    def con_dias(self, dias, costo=100000000, referencia=None, ubicacion=None, **kw):
        p = self.equipo(costo=costo, referencia=referencia or self.i13, ubicacion=ubicacion or self.local, **kw)
        p.created_at = hace(dias) + ' 10:00:00'
        db.session.flush()
        return p

    def lote(self, dias):
        proveedor = db.session.scalar(db.select(Catalogo).where(Catalogo.kind == 'supplier', Catalogo.active == 1))
        lote = Lote(entry_date=hace(dias), supplier_id=proveedor.id, exchange_rate='1', expected_count=1)
        db.session.add(lote)
        db.session.flush()
        return lote

    def consulta(self, umbral=None, rol='Propietario'):
        return cs.permanencia_inventario(rol, umbral) if umbral is not None else cs.permanencia_inventario(rol)


class DiasYUmbralTests(PermanenciaBase):
    def setUp(self):
        super().setUp()
        for dias in (10, 45, 60, 61, 200):
            self.con_dias(dias)
        db.session.commit()

    def test_contrato_comun_y_foto_de_hoy(self):
        r = self.consulta()
        self.assertEqual(set(r), CLAVES)
        self.assertEqual((r['consulta'], r['estado']), ('permanencia_inventario', 'ok'))
        self.assertFalse(r['es_estimacion'])
        self.assertEqual(r['periodo'], {'fecha_corte': HOY, 'umbral_dias': 60, 'nota': 'Foto del inventario de hoy; no es histórico.'})
        self.assertIn('no es una predicción', r['metodo'])

    def test_cuenta_los_dias_desde_el_ingreso_hasta_hoy(self):
        r = self.consulta()
        self.assertEqual([f['dias'] for f in r['detalle']['equipos_sobre_umbral']], [200, 61])
        self.assertEqual(r['cifras']['maximo_dias'], 200)
        self.assertEqual(r['cifras']['promedio_dias'], 75.2)  # (10 + 45 + 60 + 61 + 200) / 5
        self.assertEqual(r['cifras']['mediana_dias'], 60.0)
        self.assertEqual((r['cifras']['disponibles'], r['cifras']['con_fecha_de_ingreso'], r['cifras']['sin_fecha_de_ingreso']), (5, 5, 0))

    def test_sobre_el_umbral_significa_mas_dias_que_el_umbral(self):
        r = self.consulta(60)
        self.assertEqual(r['cifras']['sobre_umbral']['equipos'], 2)  # 61 y 200; el de exactamente 60 días no cuenta
        self.assertEqual(self.consulta(61)['cifras']['sobre_umbral']['equipos'], 1)
        self.assertEqual(self.consulta(200)['cifras']['sobre_umbral']['equipos'], 0)
        self.assertEqual(self.consulta(9)['cifras']['sobre_umbral']['equipos'], 5)

    def test_el_umbral_es_configurable(self):
        self.assertEqual(self.consulta()['cifras']['umbral_dias'], cs.UMBRAL_PERMANENCIA_DIAS)
        self.assertEqual(self.consulta('30')['cifras']['umbral_dias'], 30)  # puede llegar como texto
        with mock.patch.object(cs, 'UMBRAL_PERMANENCIA_DIAS', 100):
            r = self.consulta()
        self.assertEqual((r['cifras']['umbral_dias'], r['cifras']['sobre_umbral']['equipos']), (100, 1))

    def test_umbrales_invalidos(self):
        for malo in (0, -1, 'abc', cs.MAX_UMBRAL_DIAS + 1, True, 1.5, '3.5', '1e3'):
            with self.subTest(umbral=malo), self.assertRaises(cs.ParametroInvalido):
                self.consulta(malo)
        self.assertEqual(self.consulta(1)['cifras']['umbral_dias'], 1)
        self.assertEqual(self.consulta(cs.MAX_UMBRAL_DIAS)['cifras']['umbral_dias'], cs.MAX_UMBRAL_DIAS)

    def test_los_rangos_suman_todos_los_equipos_con_fecha(self):
        r = self.consulta()
        rangos = {x['rango']: x['equipos'] for x in r['detalle']['por_rango']}
        self.assertEqual(rangos, {'0 a 30 días': 1, '31 a 60 días': 2, '61 a 90 días': 1, '91 a 180 días': 0, 'más de 180 días': 1})
        self.assertEqual(sum(rangos.values()), r['cifras']['con_fecha_de_ingreso'])

    def test_la_lista_va_de_mas_antiguo_a_menos_y_trae_lo_necesario(self):
        fila = self.consulta()['detalle']['equipos_sobre_umbral'][0]
        self.assertEqual(set(fila), {'equipo_id', 'referencia', 'ubicacion', 'ingreso', 'dias', 'costo_inmovilizado_cents'})
        self.assertEqual((fila['referencia'], fila['ubicacion'], fila['ingreso'], fila['dias']), ('IPHONE 13', 'LOCAL', hace(200), 200))

    def test_agrupa_los_equipos_sobre_el_umbral_por_referencia(self):
        self.con_dias(100, referencia=self.i14)
        self.con_dias(300, referencia=self.i14)
        db.session.commit()
        filas = self.consulta()['detalle']['sobre_umbral_por_referencia']
        self.assertEqual([(f['referencia'], f['equipos'], f['dias_maximo']) for f in filas], [('IPHONE 14', 2, 300), ('IPHONE 13', 2, 200)])

    def test_la_lista_se_trunca_pero_el_total_es_completo(self):
        with mock.patch.object(cs, 'MAX_EQUIPOS_LISTADOS', 1):
            r = self.consulta()
        self.assertEqual(len(r['detalle']['equipos_sobre_umbral']), 1)
        self.assertTrue(r['detalle']['equipos_sobre_umbral_truncado'])
        self.assertEqual(r['cifras']['sobre_umbral']['equipos'], 2)
        self.assertTrue(any('total sobre el umbral es 2' in a for a in r['advertencias']))


class FechaDeIngresoTests(PermanenciaBase):
    def test_la_fecha_del_lote_manda_sobre_la_de_creacion(self):
        p = self.con_dias(5)
        p.lot_id = self.lote(90).id
        db.session.commit()
        fila = self.consulta()['detalle']['equipos_sobre_umbral'][0]
        self.assertEqual((fila['ingreso'], fila['dias']), (hace(90), 90))

    def test_sin_lote_se_usa_la_fecha_de_creacion_como_en_las_retomas(self):
        self.con_dias(75, origen='Retoma')
        db.session.commit()
        self.assertEqual(self.consulta()['detalle']['equipos_sobre_umbral'][0]['dias'], 75)

    def test_misma_regla_que_el_consolidado_contable(self):
        from app.services.contabilidad_service import _compra_fecha
        p = self.con_dias(5)
        p.lot_id = self.lote(40).id
        db.session.commit()
        self.assertEqual(self.consulta()['detalle']['por_rango'][1]['equipos'], 1)
        self.assertEqual(_compra_fecha(p), hace(40))

    def test_fechas_vacias_mal_escritas_o_futuras_no_se_inventan(self):
        self.con_dias(70)
        for texto in ('', 'ayer', '2026-13-45', hace(-3) + ' 10:00:00'):
            p = self.con_dias(1)
            p.created_at = texto
        db.session.commit()
        r = self.consulta()
        self.assertEqual(r['estado'], 'parcial')
        self.assertEqual((r['cifras']['disponibles'], r['cifras']['con_fecha_de_ingreso'], r['cifras']['sin_fecha_de_ingreso']), (5, 1, 4))
        self.assertEqual(r['cobertura'], {'completa': False, 'equipos_sin_fecha_de_ingreso': 4})
        self.assertEqual(r['cifras']['promedio_dias'], 70.0)  # solo con los que sí tienen fecha
        self.assertTrue(any('4 equipo(s) disponible(s) no tienen una fecha de ingreso válida' in a for a in r['advertencias']))

    def test_si_ninguno_tiene_fecha_valida_los_promedios_son_null(self):
        p = self.con_dias(1)
        p.created_at = ''
        db.session.commit()
        c = self.consulta()['cifras']
        self.assertEqual((c['promedio_dias'], c['mediana_dias'], c['maximo_dias']), (None, None, None))
        self.assertEqual(c['sobre_umbral']['equipos'], 0)


class AlcanceTests(PermanenciaBase):
    def test_solo_cuenta_disponibles_no_archivados(self):
        self.con_dias(100)
        self.con_dias(100, estado='Vendido')
        self.con_dias(100, estado='En pasamano')
        self.con_dias(100, estado='Separado')
        self.con_dias(100, estado='Garantía')
        self.con_dias(100, archivado=1)
        db.session.commit()
        r = self.consulta()
        self.assertEqual((r['cifras']['disponibles'], r['cifras']['sobre_umbral']['equipos']), (1, 1))

    def test_coincide_con_estado_inventario(self):
        for dias in (5, 70, 120):
            self.con_dias(dias, costo=123400000)
        db.session.commit()
        e = cs.estado_inventario('Propietario')['cifras']
        p = self.consulta()['cifras']
        self.assertEqual((p['disponibles'], p['costo_inmovilizado_cents']), (e['disponibles'], e['costo_inmovilizado_cents']))


class CostoYPrivacidadTests(PermanenciaBase):
    def setUp(self):
        super().setUp()
        self.con_dias(10, costo=111100000)
        self.con_dias(90, costo=222200000)
        self.con_dias(200, costo=333300000)
        db.session.commit()

    def test_el_propietario_ve_el_costo_inmovilizado(self):
        r = self.consulta()
        self.assertEqual(r['cifras']['costo_inmovilizado_cents'], 666600000)
        self.assertEqual(r['cifras']['sobre_umbral']['costo_inmovilizado_cents'], 555500000)
        self.assertEqual(r['detalle']['equipos_sobre_umbral'][0]['costo_inmovilizado_cents'], 333300000)
        self.assertEqual(sum(x['costo_inmovilizado_cents'] for x in r['detalle']['por_rango']), 666600000)
        self.assertEqual(r['detalle']['sobre_umbral_por_referencia'][0]['costo_inmovilizado_cents'], 555500000)

    def test_quien_no_ve_costos_no_los_recibe_ni_una_clave(self):
        with mock.patch.dict(cs.ROLES_CONSULTAS, {'permanencia_inventario': ('Propietario', 'Administrador', 'Inventario')}):
            for rol in ('Administrador', 'Inventario'):
                r = self.consulta(rol=rol)
                self.assertEqual(r['estado'], 'ok')
                self.assertEqual(r['cifras']['sobre_umbral'], {'equipos': 2})
                texto = json.dumps(r, ensure_ascii=False).lower()
                self.assertNotIn('costo', texto)
                for cifra in ('1111', '2222', '3333', '5555', '6666'):
                    self.assertNotIn(cifra, texto)

    def test_el_costo_se_puede_dar_a_otro_perfil_cambiando_la_constante(self):
        with mock.patch.dict(cs.ROLES_CONSULTAS, {'permanencia_inventario': ('Propietario', 'Administrador')}), \
                mock.patch.object(cs, 'ROLES_CON_COSTO', ('Propietario', 'Administrador')):
            self.assertEqual(self.consulta(rol='Administrador')['cifras']['costo_inmovilizado_cents'], 666600000)

    def test_nunca_devuelve_imei_proveedor_ni_personas(self):
        r = self.consulta()
        r.pop('metodo')  # el método explica que no se devuelve el IMEI; lo que importa es que no esté en los datos
        texto = json.dumps(r, ensure_ascii=False)
        for p in db.session.scalars(db.select(Producto)):
            self.assertNotIn(p.imei, texto)
        for privado in ('imei', 'IMEI', 'supplier', 'proveedor', 'seller', 'responsible', 'password', 'CP CELULARES'):
            self.assertNotIn(privado, texto)

    def test_importes_en_centavos_enteros(self):
        r = self.consulta()
        for valor in (r['cifras']['costo_inmovilizado_cents'], r['cifras']['sobre_umbral']['costo_inmovilizado_cents']):
            self.assertIsInstance(valor, int)


class EstadosYPermisosTests(PermanenciaBase):
    def test_sin_datos_cuando_no_hay_equipos(self):
        r = self.consulta()
        self.assertEqual(r['estado'], 'sin_datos')
        self.assertIsNone(r['cifras'])
        self.assertIn('no es una predicción', r['metodo'])

    def test_cero_disponibles_con_inventario_registrado_es_ok(self):
        self.con_dias(10, estado='Vendido')
        db.session.commit()
        r = self.consulta()
        self.assertEqual(r['estado'], 'ok')
        self.assertEqual((r['cifras']['disponibles'], r['cifras']['sobre_umbral']['equipos'], r['cifras']['promedio_dias']), (0, 0, None))
        self.assertEqual(r['detalle']['equipos_sobre_umbral'], [])

    def test_sin_autorizacion_para_todo_perfil_distinto_del_propietario(self):
        self.con_dias(200, costo=987600000)
        db.session.commit()
        for rol in ('Administrador', 'Vendedora', 'Inventario', 'Socio', '', None):
            with self.subTest(rol=rol):
                r = cs.permanencia_inventario(rol, 'no-es-numero')  # primero la autorización, luego los parámetros
                self.assertEqual(r['estado'], 'sin_autorizacion')
                self.assertIsNone(r['cifras'])
                self.assertIsNone(r['detalle'])
                self.assertNotIn('9876', json.dumps(r))

    def test_error_temporal_de_la_base(self):
        self.con_dias(100)
        db.session.commit()
        fallo = OperationalError('SELECT', {}, Exception('database is locked'))
        with mock.patch.object(cs, '_leer_disponibles', side_effect=fallo):
            r = self.consulta()
        self.assertEqual(r['estado'], 'error_temporal')
        self.assertIsNone(r['cifras'])
        self.assertEqual(self.consulta()['estado'], 'ok')

    def test_un_error_de_programacion_no_se_disfraza(self):
        self.con_dias(100)
        db.session.commit()
        with mock.patch.object(cs, '_leer_disponibles', side_effect=KeyError('bug')):
            with self.assertRaises(KeyError):
                self.consulta()

    def test_es_solo_lectura(self):
        self.con_dias(100)
        db.session.commit()
        antes = [(p.id, p.revision, p.status, p.created_at) for p in db.session.scalars(db.select(Producto))]
        self.consulta()
        self.assertFalse(db.session.new or db.session.dirty or db.session.deleted)
        db.session.expire_all()
        self.assertEqual(antes, [(p.id, p.revision, p.status, p.created_at) for p in db.session.scalars(db.select(Producto))])

    def test_solo_el_propietario_en_la_configuracion(self):
        self.assertEqual(cs.ROLES_CONSULTAS['permanencia_inventario'], ('Propietario',))


if __name__ == '__main__':
    unittest.main()
