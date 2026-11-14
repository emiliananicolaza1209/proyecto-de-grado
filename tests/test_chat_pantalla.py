"""Chat básico (commit B): la pantalla, su JavaScript propio y la política de contenido."""
import re
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from werkzeug.security import generate_password_hash

from test_consulta_resumen_ventas import VentasBase
from app.extensions import db
from app.models import Catalogo
from app.models.gestion import Usuario
from app.security import CSP
from app.services import chat_service as chat
from app.services import consultas_service as cs

RAIZ = Path(__file__).resolve().parent.parent
JS = RAIZ / 'app' / 'static' / 'js' / 'chat.js'
BOTONES = (('Ventas de hoy', 'ventas de hoy'), ('Inventario disponible', 'inventario disponible'),
           ('Créditos pendientes', 'créditos pendientes'), ('Resultado de esta semana', 'resultado de esta semana'))


class PantallaBase(VentasBase):
    def setUp(self):
        super().setUp()
        self.app.config['AUTH_REQUIRED'] = True

    def cliente(self, rol, **extra):
        u = db.session.scalar(db.select(Usuario).where(Usuario.login == rol.lower()))
        if u is None:  # varias peticiones del mismo perfil en una prueba reutilizan el usuario
            u = Usuario(nombre=f'{rol.upper()} PRUEBA', login=rol.lower(), rol=rol, password_hash=generate_password_hash('clave_prueba_123'), **extra)
            db.session.add(u)
            db.session.commit()
        c = self.app.test_client()
        with c.session_transaction() as s:
            s.update(usuario_id=u.id, usuario_version=u.session_version, csrf='test')
        return c


class PaginaTests(PantallaBase):
    def pagina(self):
        r = self.cliente('Propietario').get('/chat')
        self.assertEqual(r.status_code, 200)
        return r, r.get_data(as_text=True)

    def test_tiene_caja_de_pregunta_historial_y_formulario_con_csrf(self):
        _, html = self.pagina()
        self.assertIn('id="chat-form"', html)
        self.assertIn('method="post"', html)
        self.assertIn('action="/chat/consultar"', html)
        self.assertIn('<input type="hidden" name="csrf" value="test">', html)  # el token de la sesión
        self.assertRegex(html, r'<input id="chat-pregunta" name="pregunta"[^>]*maxlength="300"')
        self.assertIn('id="chat-historial"', html)
        self.assertIn('role="log"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('for="chat-pregunta"', html)  # la caja tiene etiqueta accesible

    def test_los_cuatro_botones_de_ejemplo(self):
        _, html = self.pagina()
        for etiqueta, pregunta in BOTONES:
            self.assertRegex(html, rf'<button type="button" class="btn btn-light chat-ejemplo" data-pregunta="{pregunta}">{etiqueta}</button>')
        self.assertEqual(html.count('chat-ejemplo"'), 4)

    def test_cada_boton_formula_una_pregunta_que_el_chat_entiende(self):
        esperado = {'ventas de hoy': 'resumen_ventas', 'inventario disponible': 'estado_inventario',
                    'créditos pendientes': 'creditos_pendientes', 'resultado de esta semana': 'resumen_financiero'}
        for _, pregunta in BOTONES:
            self.assertEqual(chat.detectar_intenciones(pregunta)[0], esperado[pregunta])

    def test_usa_su_archivo_js_y_su_css_sin_nada_en_linea(self):
        _, html = self.pagina()
        self.assertIn('/static/js/chat.js', html)
        self.assertIn('/static/css/chat.css', html)
        for etiqueta in re.findall(r'<script\b([^>]*)>', html):
            self.assertTrue('src=' in etiqueta or 'application/json' in etiqueta, f'script en línea: {etiqueta}')
        self.assertIsNone(re.search(r'\son(click|change|submit|load|input|keyup|keydown)\s*=', html))
        self.assertNotIn('javascript:', html.lower())
        self.assertNotIn('style="', html)  # tampoco estilos en línea

    def test_la_politica_de_contenido_permite_la_pagina(self):
        r, _ = self.pagina()
        self.assertEqual(r.headers['Content-Security-Policy'], CSP)
        self.assertIn("script-src 'self'", CSP)
        self.assertIn("connect-src 'self'", CSP)  # el fetch del chat va al mismo origen
        self.assertNotIn("script-src 'self' 'unsafe-inline'", CSP)

    def test_explica_que_solo_consulta_y_los_periodos(self):
        _, html = self.pagina()
        self.assertIn('solo consulta', html)
        self.assertIn('Sin periodo, las ventas y el resultado usan hoy', html)
        self.assertIn('del 1 al 15 de octubre', html)
        self.assertIn('se borra al recargar', html)


class PermisosYMenuTests(PantallaBase):
    def test_solo_el_propietario_abre_la_pantalla(self):
        self.assertEqual(self.cliente('Propietario').get('/chat').status_code, 200)
        for rol in ('Administrador', 'Vendedora', 'Inventario'):
            self.assertEqual(self.cliente(rol).get('/chat').status_code, 403, rol)
        self.assertEqual(self.cliente('Socio').get('/chat').status_code, 302)
        self.assertEqual(self.app.test_client().get('/chat').status_code, 302)

    def test_la_entrada_del_menu_es_solo_para_el_propietario(self):
        propietario = self.cliente('Propietario').get('/').get_data(as_text=True)
        self.assertRegex(propietario, r'<a class="[^"]*"\s+href="/chat"[^>]*>.*?Chat de consultas')
        for rol in ('Administrador', 'Vendedora', 'Inventario'):
            html = self.cliente(rol).get('/').get_data(as_text=True)
            self.assertNotIn('href="/chat"', html, rol)
            self.assertNotIn('Chat de consultas', html, rol)

    def test_el_menu_marca_el_chat_como_activo_en_su_pagina(self):
        html = self.cliente('Propietario').get('/chat').get_data(as_text=True)
        self.assertRegex(html, r'class="active" aria-current="page"\s+href="/chat"')

    def test_si_se_habilita_otro_perfil_en_la_configuracion_aparece_su_entrada(self):
        with mock.patch.dict(cs.ROLES_CONSULTAS, {'resumen_ventas': ('Propietario', 'Administrador')}):
            admin = self.cliente('Administrador')
            self.assertEqual(admin.get('/chat').status_code, 200)
            self.assertIn('href="/chat"', admin.get('/').get_data(as_text=True))

    def test_el_endpoint_y_la_pantalla_se_hablan(self):
        """El formulario envía exactamente los campos que el endpoint espera."""
        c = self.cliente('Propietario')
        html = c.get('/chat').get_data(as_text=True)
        csrf = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
        r = c.post(re.search(r'action="([^"]+)"', html.split('id="chat-form"')[1]).group(1), data={'csrf': csrf, 'pregunta': 'ventas de hoy'})
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertEqual(j['herramienta'], 'resumen_ventas')
        self.assertTrue(j['tarjeta']['cifras'])
        self.assertEqual({'etiqueta', 'valor'}, set(j['tarjeta']['cifras'][0]))
        for clave in ('titulo', 'estado', 'provisional', 'periodo', 'cifras', 'fuente', 'advertencias', 'notas'):
            self.assertIn(clave, j['tarjeta'])  # lo que chat.js dibuja


class JavaScriptTests(unittest.TestCase):
    def setUp(self):
        self.js = JS.read_text(encoding='utf-8')

    def test_el_archivo_existe_y_es_propio(self):
        self.assertTrue(JS.is_file())
        self.assertIn("'use strict'", self.js)

    def test_nunca_interpreta_html_de_la_respuesta(self):
        for peligroso in ('innerHTML', 'outerHTML', 'insertAdjacentHTML', 'document.write', 'eval(', 'new Function', 'setTimeout("'):
            self.assertNotIn(peligroso, self.js)
        self.assertIn('textContent', self.js)

    def test_envia_el_formulario_con_csrf_al_mismo_origen(self):
        self.assertIn('new FormData(form)', self.js)
        self.assertIn("credentials: 'same-origin'", self.js)
        self.assertIn('form.action', self.js)
        self.assertNotIn('http://', self.js)
        self.assertNotIn('https://', self.js)

    def test_maneja_sesion_vencida_permiso_y_fallos_de_red(self):
        for pista in ('r.redirected', 'application/json', 'r.status === 403', 'catch (e)', 'finally'):
            self.assertIn(pista, self.js)

    def test_no_guarda_nada_en_el_navegador(self):
        for almacen in ('localStorage', 'sessionStorage', 'indexedDB', 'document.cookie'):
            self.assertNotIn(almacen, self.js)  # el historial solo vive en pantalla

    def test_cubre_cada_estado_con_su_rotulo(self):
        for estado in ('ok', 'parcial', 'sin_datos', 'sin_autorizacion', 'error_temporal', 'fuera_de_alcance', 'periodo_invalido'):
            self.assertIn(estado, self.js)
        self.assertIn('Provisional', self.js)

    def test_tiene_sintaxis_valida(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node no está instalado')
        r = subprocess.run([node, '--check', str(JS)], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)


class MensajeParcialTests(VentasBase):
    def test_inventario_parcial_no_habla_de_jornadas_provisionales(self):
        self.equipo()  # sin ubicación ni referencia de catálogo
        r = chat.responder('Propietario', 'inventario disponible', usuario='P', usuario_id=1)
        self.assertEqual(r['estado'], 'parcial')
        t = r['respuesta']
        self.assertIn('Resultado parcial: algunos equipos no están clasificados en el catálogo', t)
        self.assertIn('el total de equipos disponibles sí está completo', t)
        for prohibido in ('provisional', 'jornada', 'cobertura'):
            self.assertNotIn(prohibido, t.lower())

    def test_cada_consulta_explica_su_parcial_con_sus_propias_palabras(self):
        self.vender(monto='650000', con_equipo=False)
        r = chat.responder('Propietario', 'ventas de esta semana', usuario='P', usuario_id=1, hoy=self.hoy)
        if r['estado'] == 'parcial':
            self.assertIn('la cobertura del periodo está incompleta', r['respuesta'])
        self.assertEqual(set(chat.PARCIAL), {'estado_inventario', 'creditos_pendientes', 'comparar_periodos',
                                                'permanencia_inventario', 'otras'})
        # La comparación sí es parcial también por jornadas abiertas (lo dice su propio texto); las demás no mezclan lo provisional.
        self.assertNotIn('provisional', ' '.join(v for k, v in chat.PARCIAL.items() if k != 'comparar_periodos').lower())

    def test_lo_provisional_se_sigue_diciendo_aparte_cuando_hay_jornadas_abiertas(self):
        self.vender(monto='650000', con_equipo=False)
        t = chat.responder('Propietario', 'resultado de hoy', usuario='P', usuario_id=1)['respuesta']
        self.assertIn('Incluye jornadas abiertas: esa parte es provisional', t)


if __name__ == '__main__':
    unittest.main()
