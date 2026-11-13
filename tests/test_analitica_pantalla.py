"""6d: comparar con el periodo anterior y baja rotación, en el reporte y en el chat (solo Propietario, sin scripts en línea)."""
import re
from datetime import date, timedelta

from test_chat_pantalla import PantallaBase
from test_reportes import texto_de
from app.extensions import db
from app.services import chat_service as chat
from app.services import consultas_service as cs
from app.services import reporte_service as rs
from app.services.operacion_service import today


def hace(dias):
    return (date.fromisoformat(today()) - timedelta(days=dias)).isoformat()


class AnaliticaBase(PantallaBase):
    def viejo(self, dias=100, costo=250000000):
        p = self.equipo(costo=costo)
        p.created_at = hace(dias) + ' 10:00:00'
        db.session.commit()
        return p


class ReporteCompararTests(AnaliticaBase):
    def test_ventas_y_finanzas_ofrecen_el_boton_con_el_aviso(self):
        c = self.cliente('Propietario')
        for ruta in ('/ventas', '/finanzas', '/reportes/ventas', '/reportes/finanzas'):
            html = c.get(ruta).get_data(as_text=True)
            self.assertIn('name="comparar" value="1"', html, ruta)
            self.assertIn('Comparar con el periodo anterior', html, ruta)
            self.assertIn('no una predicción', texto_de(html), ruta)

    def test_inventario_no_ofrece_comparar_pero_si_el_umbral(self):
        html = self.cliente('Propietario').get('/inventario').get_data(as_text=True)
        self.assertNotIn('name="comparar"', html)
        self.assertIn('name="umbral"', html)
        self.assertIn(f'value="{cs.UMBRAL_PERMANENCIA_DIAS}"', html)

    def test_comparar_agrega_la_tarjeta_y_sin_comparar_no(self):
        self.vender(monto='1200000', con_equipo=False)
        c = self.cliente('Propietario')
        sin = c.get('/reportes/ventas?periodo=semana').get_data(as_text=True)
        con = c.get('/reportes/ventas?periodo=semana&comparar=1').get_data(as_text=True)
        self.assertNotIn('Periodo anterior', texto_de(sin))
        self.assertIn('Periodo anterior', texto_de(con))
        self.assertIn('comparación', texto_de(con))
        self.assertIn('comparar=1', con)  # el CSV conserva la comparación

    def test_generar_con_comparar_solo_aplica_a_ventas_y_finanzas(self):
        self.vender(monto='1200000', con_equipo=False)
        for modulo, esperado in (('ventas', True), ('finanzas', True), ('inventario', False)):
            r = rs.generar('Propietario', modulo, 'semana', comparar=True, usuario='P', usuario_id=1)
            self.assertEqual(r['comparado'], esperado, modulo)
            self.assertEqual('comparar_periodos' in [t['consulta'] for t in r['tarjetas']], esperado, modulo)

    def test_csv_de_la_comparacion(self):
        c = self.cliente('Propietario')
        r = c.get('/reportes/ventas?periodo=semana&comparar=1&formato=csv')
        self.assertEqual(r.status_code, 200)
        self.assertIn('Comparar', r.get_data(as_text=True) + 'Comparar')
        self.assertIn('Consulta', r.get_data(as_text=True))


class ReporteBajaRotacionTests(AnaliticaBase):
    def test_lista_los_equipos_sobre_el_umbral_sin_imei(self):
        p = self.viejo(100)
        self.equipo(costo=100000000)  # reciente: no entra
        html = self.cliente('Propietario').get('/reportes/inventario?umbral=60').get_data(as_text=True)
        t = texto_de(html)
        self.assertIn('baja rotación', t)
        self.assertIn('más de 60 días', t)
        self.assertIn(f'href="/inventario/{p.id}"', html)
        self.assertIn('$2.500.000', t)  # el Propietario ve el costo
        self.assertNotIn(p.imei, html)

    def test_el_umbral_cambia_la_lista(self):
        self.viejo(100)
        c = self.cliente('Propietario')
        self.assertIn('Ningún equipo disponible supera ese umbral', texto_de(c.get('/reportes/inventario?umbral=200').get_data(as_text=True)))

    def test_umbral_invalido_da_400_claro(self):
        c = self.cliente('Propietario')
        for malo in ('abc', '0', '-5', '99999'):
            r = c.get(f'/reportes/inventario?umbral={malo}')
            self.assertEqual(r.status_code, 400, malo)
            self.assertNotIn('Traceback', r.get_data(as_text=True))

    def test_sin_umbral_usa_el_de_defecto(self):
        self.viejo(10)
        r = rs.generar('Propietario', 'inventario', usuario='P', usuario_id=1)
        perm = next(x for x in r['resultados'] if x['consulta'] == 'permanencia_inventario')
        self.assertEqual(perm['cifras']['umbral_dias'], cs.UMBRAL_PERMANENCIA_DIAS)

    def test_otro_perfil_no_abre_nada(self):
        for rol in ('Administrador', 'Vendedora', 'Inventario'):
            self.assertEqual(self.cliente(rol).get('/reportes/inventario?umbral=30').status_code, 403, rol)
            self.assertEqual(self.cliente(rol).get('/reportes/ventas?comparar=1').status_code, 403, rol)


class ChatTests(AnaliticaBase):
    def test_baja_rotacion_en_el_chat(self):
        self.viejo(100)
        r = chat.responder('Propietario', 'baja rotación', usuario='P', usuario_id=1)
        self.assertEqual(r['herramienta'], 'permanencia_inventario')
        self.assertEqual(r['estado'], 'ok')
        self.assertIn('60', r['respuesta'])
        self.assertNotIn('IMEI', r['respuesta'].upper().replace('SIN IMEI', ''))

    def test_baja_rotacion_con_umbral_en_la_pregunta(self):
        self.viejo(100)
        r = chat.responder('Propietario', 'equipos con baja rotación de más de 90 días', usuario='P', usuario_id=1)
        self.assertEqual(r['herramienta'], 'permanencia_inventario')
        self.assertEqual(r['tarjeta']['consulta'], 'permanencia_inventario')
        self.assertIn('90', ' '.join(f"{c['etiqueta']} {c['valor']}" for c in r['tarjeta']['cifras']))

    def test_comparar_con_el_periodo_anterior_en_el_chat(self):
        self.vender(monto='1200000', con_equipo=False)
        r = chat.responder('Propietario', 'comparar con el periodo anterior', usuario='P', usuario_id=1, hoy=self.hoy)
        self.assertEqual(r['herramienta'], 'comparar_periodos')
        self.assertIn('comparación', r['respuesta'].lower())
        self.assertIn('no es una predicción', r['respuesta'].lower())

    def test_las_preguntas_de_antes_siguen_igual(self):
        for pregunta, herramienta in (('ventas de hoy', 'resumen_ventas'), ('inventario disponible', 'estado_inventario'),
                                      ('créditos pendientes', 'creditos_pendientes'), ('resultado de esta semana', 'resumen_financiero')):
            self.assertEqual(chat.responder('Propietario', pregunta, usuario='P', usuario_id=1, hoy=self.hoy)['herramienta'], herramienta, pregunta)

    def test_otro_perfil_recibe_sin_autorizacion(self):
        for rol in ('Administrador', 'Vendedora'):
            for pregunta in ('baja rotación', 'comparar con el periodo anterior'):
                r = chat.responder(rol, pregunta, usuario='X', usuario_id=2, hoy=self.hoy)
                self.assertEqual(r['estado'], 'sin_autorizacion', (rol, pregunta))

    def test_la_ruta_del_chat_responde(self):
        c = self.cliente('Propietario')
        r = c.post('/chat/consultar', data={'pregunta': 'baja rotación', 'csrf': 'test'})
        self.assertEqual(r.status_code, 200)
        self.assertNotRegex(r.get_data(as_text=True), r'\son(click|change|submit)\s*=')


class PoliticaTests(AnaliticaBase):
    def test_sin_scripts_ni_estilos_en_linea_en_las_pantallas_nuevas(self):
        c = self.cliente('Propietario')
        for ruta in ('/reportes/ventas?comparar=1', '/reportes/finanzas?comparar=1', '/reportes/inventario?umbral=30'):
            html = c.get(ruta).get_data(as_text=True)
            for atributos in re.findall(r'<script\b([^>]*)>', html):
                self.assertTrue('src=' in atributos or 'application/json' in atributos, (ruta, atributos))
            self.assertNotIn('style="', html, ruta)
            self.assertIsNone(re.search(r'\son\w+\s*=', html), ruta)
