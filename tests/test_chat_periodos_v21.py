"""Regresiones: fechas colombianas, selección explícita y consulta de cierres reales."""
import json
import unittest
from unittest import mock

from test_chat_pantalla import PantallaBase
from app.extensions import db
from app.models.finanzas import Jornada, OperacionFinanciera
from app.services import chat_service as chat


class FechasColombianasTests(unittest.TestCase):
    def test_reconoce_dia_mes_sin_invertirlos(self):
        for texto in ('ventas del 12/10/2026', 'ventas del 12-10-2026', 'ventas del 12/10', 'ventas de 2026-10-12'):
            with self.subTest(texto=texto):
                periodo = chat.interpretar_periodo(texto, '2026-11-13')
                self.assertEqual((periodo['ini'], periodo['fin']), ('2026-10-12', '2026-10-12'))

    def test_rangos_inclusivos_y_anio_bisiesto(self):
        for texto, esperado in (
            ('ventas del 01/10/2026 al 12/10/2026', ('2026-10-01', '2026-10-12')),
            ('del 29/02/2024 hasta el 01/03/2024', ('2024-02-29', '2024-03-01')),
            ('del 2026-10-01 al 12/10/2026', ('2026-10-01', '2026-10-12')),
            ('ventas del 1 al 12/10/2026', ('2026-10-01', '2026-10-12')),
            ('ventas del 12/10/2026 al 15', ('2026-10-12', '2026-10-15')),
        ):
            with self.subTest(texto=texto):
                periodo = chat.interpretar_periodo(texto, '2026-11-13')
                self.assertEqual((periodo['ini'], periodo['fin']), esperado)

    def test_una_fecha_invalida_no_se_ignora_para_usar_hoy(self):
        for texto in ('ventas del 31/02/2026', 'ventas del 12/13/2026', 'ventas del 12/10/26',
                      'ventas del 2026-02-30', 'ventas del 12/10/2026 y 13/10/2026 y 14/10/2026'):
            with self.subTest(texto=texto), self.assertRaises(chat.PeriodoInvalido):
                chat.interpretar_periodo(texto, '2026-11-13')

    def test_cierre_no_cambia_una_peticion_de_ventas_a_utilidad(self):
        self.assertEqual(chat.detectar_intenciones('ventas del último cierre')[0], 'resumen_ventas')
        self.assertEqual(chat.detectar_intenciones('resultado del último cierre')[0], 'resumen_financiero')


class ChatCierreTests(PantallaBase):
    def preparar_cierre(self):
        jornada = self.jornada('2026-10-12')
        for monto in ['70000'] * 11 + ['83000']:
            self.vender(d=jornada, monto=monto, con_equipo=False)
        self.cerrar(jornada)
        return jornada

    def consultar_chat(self, pregunta, **campos):
        return self.cliente('Propietario').post('/chat/consultar', data={'csrf': 'test', 'pregunta': pregunta, **campos})

    def test_fecha_colombiana_devuelve_las_12_ventas_del_cierre_sin_recalcularlo(self):
        jornada = self.preparar_cierre()
        snapshot = json.dumps(jornada.snapshot, sort_keys=True)
        # Una corrección posterior no puede reescribir las cifras guardadas.
        op = db.session.scalar(db.select(OperacionFinanciera).where(OperacionFinanciera.day_id == jornada.id))
        op.amount += 100
        db.session.commit()
        respuesta = self.consultar_chat('ventas del 12/10/2026')
        self.assertEqual(respuesta.status_code, 200)
        dato = respuesta.get_json()
        self.assertEqual(dato['periodo']['ini'], '2026-10-12')
        cifras = {f['etiqueta']: f['valor'] for f in dato['tarjeta']['cifras']}
        self.assertEqual(cifras['Operaciones de venta'], '12')
        self.assertEqual(cifras['Venta neta'], '$853.000')
        self.assertIn('Definitivo (jornadas cerradas)', cifras)
        db.session.expire_all()
        self.assertEqual(json.dumps(jornada.snapshot, sort_keys=True), snapshot)

    def test_selector_de_fechas_y_fecha_escrita_tienen_precedencia_explicita(self):
        self.preparar_cierre()
        dato = self.consultar_chat('ventas', ini='2026-10-12', fin='2026-10-12').get_json()
        self.assertEqual(dato['periodo']['ini'], '2026-10-12')
        self.assertIn('Usé las fechas seleccionadas', dato['respuesta'])
        escrito = self.consultar_chat('ventas del 12/10/2026', ini=self.hoy, fin=self.hoy).get_json()
        self.assertEqual(escrito['periodo']['ini'], '2026-10-12')

    def test_ultimo_cierre_consulta_la_fecha_guardada_y_no_hoy(self):
        self.preparar_cierre()
        for pregunta in ('ventas de la última jornada cerrada', 'ventas del último cierre'):
            dato = self.consultar_chat(pregunta).get_json()
            self.assertEqual(dato['herramienta'], 'resumen_ventas')
            self.assertEqual(dato['periodo']['ini'], '2026-10-12')
            self.assertIn('$853.000', dato['respuesta'])
        html = self.cliente('Propietario').get('/chat').get_data(as_text=True)
        self.assertIn('data-ultimo-cierre="2026-10-12"', html)

    def test_sin_cierre_no_inventa_fecha_ni_cifra(self):
        dato = self.consultar_chat('ventas del último cierre').get_json()
        self.assertEqual(dato['estado'], 'sin_datos')
        self.assertIsNone(dato['periodo'])
        self.assertIn('Todavía no hay una jornada cerrada', dato['respuesta'])

    def test_fecha_invalida_o_rango_invertido_no_consultan_hoy(self):
        for pregunta, campos in [('ventas del 31/02/2026', {}), ('ventas', {'ini': self.hoy, 'fin': '2026-10-12'})]:
            dato = self.consultar_chat(pregunta, **campos).get_json()
            self.assertEqual(dato['estado'], 'periodo_invalido')
            self.assertIsNone(dato['tarjeta'])

    def test_sin_datos_muestra_el_periodo_que_realmente_consulto(self):
        dato = self.consultar_chat('ventas del 11/10/2026').get_json()
        self.assertEqual(dato['estado'], 'sin_datos')
        self.assertIn('2026-10-11', dato['respuesta'])
        self.assertEqual(dato['tarjeta']['periodo']['ini'], '2026-10-11')

    def test_usuario_sin_permiso_no_puede_ver_ni_descubrir_cierres(self):
        with mock.patch.object(db.session, 'scalar', side_effect=AssertionError('No debe leer jornadas')):
            self.assertIsNone(chat.ultima_jornada_cerrada('Vendedora'))
        self.assertEqual(self.cliente('Vendedora').post('/chat/consultar', data={'csrf': 'test', 'pregunta': 'ventas del último cierre'}).status_code, 403)

    def test_un_fallo_al_leer_cierres_no_se_presenta_como_ausencia_de_ventas(self):
        from sqlalchemy.exc import OperationalError
        with mock.patch.object(chat, 'ultima_jornada_cerrada', side_effect=OperationalError('SELECT', {}, Exception('temporal'))):
            dato = self.consultar_chat('ventas del último cierre').get_json()
        self.assertEqual(dato['estado'], 'error_temporal')
        self.assertNotIn('no hay', dato['respuesta'])
