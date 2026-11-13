"""6e: tarjetas analíticas en la pantalla Resumen (solo Propietario) con selector de periodo; los demás perfiles ven el Resumen como antes."""
import re
from datetime import date, timedelta

from test_analitica_pantalla import AnaliticaBase
from test_reportes import texto_de
from app.extensions import db
from app.models.gestion import RegistroGestion
from app.security import CSP
from app.services import chat_service as chat
from app.services import reporte_service as rs
from app.services.operacion_service import today

TITULOS = ('Ventas', 'Utilidad de la jornada', 'Inventario disponible', 'Créditos pendientes', 'Baja rotación del inventario')


class TarjetasTests(AnaliticaBase):
    def test_el_servicio_trae_las_cinco_tarjetas_con_fuente_estado_y_enlace(self):
        self.viejo(100)
        r = rs.resumen_tarjetas('Propietario', 'semana')
        self.assertEqual([a['tarjeta']['consulta'] for a in r['tarjetas']],
                         ['resumen_ventas', 'resumen_financiero', 'estado_inventario', 'creditos_pendientes', 'permanencia_inventario'])
        for a in r['tarjetas']:
            self.assertTrue(a['tarjeta']['fuente'])
            self.assertIn(a['tarjeta']['estado'], ('ok', 'parcial', 'sin_datos', 'sin_autorizacion', 'error_temporal'))
            self.assertEqual(len(a['enlace']), 4)

    def test_son_las_mismas_cifras_que_el_chat_y_las_consultas(self):
        self.vender(monto='1200000', con_equipo=False)
        self.viejo(100)
        r = rs.resumen_tarjetas('Propietario', 'mes', hoy=self.hoy)
        por = {a['tarjeta']['consulta']: a['tarjeta'] for a in r['tarjetas']}
        ch = chat.responder('Propietario', 'ventas de este mes', usuario='P', usuario_id=1, hoy=self.hoy)
        self.assertEqual(por['resumen_ventas']['cifras'], ch['tarjeta']['cifras'])
        inv = chat.responder('Propietario', 'inventario disponible', usuario='P', usuario_id=1)
        self.assertEqual(por['estado_inventario']['cifras'], inv['tarjeta']['cifras'])

    def test_el_periodo_solo_cambia_las_ventas_y_el_resultado_es_el_de_hoy(self):
        r = rs.resumen_tarjetas('Propietario', '15dias', hoy='2026-11-11')
        self.assertEqual(r['periodo']['ini'], '2026-10-28')
        ventas, financiero = r['tarjetas'][0]['tarjeta'], r['tarjetas'][1]['tarjeta']
        self.assertIn('2026-10-28 a 2026-11-11', ventas['periodo']['etiqueta'])
        self.assertEqual(financiero['periodo']['etiqueta'], 'Hoy: 2026-11-11')

    def test_periodo_desconocido_vuelve_a_semana(self):
        self.assertEqual(rs.resumen_tarjetas('Propietario', 'rango')['tipo'], 'semana')
        self.assertEqual(rs.resumen_tarjetas('Propietario', 'x')['tipo'], 'semana')

    def test_otro_perfil_recibe_sin_autorizacion_en_cada_tarjeta(self):
        r = rs.resumen_tarjetas('Administrador', 'semana')
        for a in r['tarjetas']:
            self.assertEqual(a['tarjeta']['estado'], 'sin_autorizacion')
            self.assertEqual(a['tarjeta']['cifras'], [])

    def test_ver_la_pantalla_no_escribe_nada(self):
        antes = db.session.scalar(db.select(db.func.count()).select_from(RegistroGestion))
        self.cliente('Propietario').get('/analitica')
        db.session.expire_all()
        self.assertEqual(db.session.scalar(db.select(db.func.count()).select_from(RegistroGestion)), antes)


class PantallaTests(AnaliticaBase):
    def home(self, query='', rol='Propietario'):
        return self.cliente(rol).get('/analitica' + query)

    def test_el_propietario_ve_las_cinco_tarjetas_con_su_enlace(self):
        self.viejo(100)
        r = self.home()
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        t = texto_de(html)
        for titulo in TITULOS:
            self.assertIn(titulo, t, titulo)
        self.assertEqual(html.count('Ver el reporte'), 5)
        self.assertIn('href="/reportes/ventas?periodo=semana"', html)
        self.assertIn(f'href="/reportes/finanzas?periodo=rango&amp;ini={today()}&amp;fin={today()}"', html)
        self.assertIn('href="/reportes/inventario"', html)
        self.assertIn('href="/reportes/finanzas?periodo=semana"', html)
        self.assertIn('Fuente: Finanzas', t)
        self.assertIn('Fuente: Inventario', t)
        self.assertIn('/static/css/reportes.css', html)

    def test_los_enlaces_de_las_tarjetas_abren(self):
        c = self.cliente('Propietario')
        html = c.get('/analitica?periodo=mes').get_data(as_text=True)
        enlaces = set(re.findall(r'href="(/reportes/[^"]+)"', html))
        self.assertEqual(len(enlaces), 4)  # inventario aparece en dos tarjetas
        for url in enlaces:
            self.assertEqual(c.get(url.replace('&amp;', '&')).status_code, 200, url)

    def test_el_selector_ofrece_semana_15_dias_y_mes_y_conserva_la_eleccion(self):
        html = self.home('?periodo=15dias').get_data(as_text=True)
        selector = re.search(r'<select id="home-periodo" name="periodo".*?</select>', html, re.S).group(0)
        self.assertEqual(re.findall(r'<option value="([^"]+)"[^>]*>([^<]+)</option>', selector),
                         [('semana', 'Semana'), ('15dias', '15 días'), ('mes', 'Mes')])
        self.assertRegex(selector, r'<option value="15dias" selected>')
        self.assertIn('href="/reportes/ventas?periodo=15dias"', html)

    def test_periodo_invalido_no_rompe_la_pantalla(self):
        for q in ('?periodo=basura', '?periodo=rango', '?periodo='):
            self.assertEqual(self.home(q).status_code, 200, q)

    def test_estado_provisional_se_muestra_con_jornada_abierta(self):
        self.vender(monto='1200000', con_equipo=False)
        t = texto_de(self.home().get_data(as_text=True))
        self.assertRegex(t, r'Completo|Parcial|Sin datos')

    def test_los_demas_perfiles_ven_el_resumen_como_antes(self):
        for rol in ('Administrador', 'Vendedora', 'Inventario'):
            r = self.home('?periodo=mes', rol)
            self.assertEqual(r.status_code, 403, rol)
            html = self.cliente(rol).get('/').get_data(as_text=True)
            for rastro in ('home-analitica', 'Indicadores del negocio', 'Ver el reporte', 'Baja rotación del inventario'):
                self.assertNotIn(rastro, html, (rol, rastro))
            self.assertIn('Resumen del negocio', html)
            self.assertIn('Equipos disponibles', html)

    def test_sin_scripts_ni_estilos_en_linea(self):
        r = self.home()
        html = r.get_data(as_text=True)
        self.assertEqual(r.headers['Content-Security-Policy'], CSP)
        for atributos in re.findall(r'<script\b([^>]*)>', html):
            self.assertTrue('src=' in atributos or 'application/json' in atributos, atributos)
        self.assertIsNone(re.search(r'\son\w+\s*=', html))
        self.assertNotIn('javascript:', html.lower())
        self.assertNotIn('style="', html)

    def test_no_se_filtran_imei_ni_personas_en_las_tarjetas(self):
        p = self.viejo(100)
        html = self.home().get_data(as_text=True)
        analitica = html[html.index('home-analitica'):html.index('home-columns')]
        self.assertNotIn(p.imei, analitica)
