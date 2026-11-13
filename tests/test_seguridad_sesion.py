"""Seguridad de sesión: expiración por inactividad y atributos de la cookie."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from werkzeug.security import generate_password_hash

from _cleanup import release
from app import create_app
from app.extensions import db
from app.models.gestion import Usuario

CLAVE = 'clave_prueba_123'


class SesionBase(unittest.TestCase):
    def crear(self, **config):
        self.tmp = tempfile.TemporaryDirectory()
        base = {'TESTING': True, 'DATABASE': str(Path(self.tmp.name) / 'db.sqlite'), 'SECRET_KEY': 'test', 'AUTH_REQUIRED': True}
        base.update(config)
        self.app = create_app(base)
        with self.app.app_context():
            db.session.add(Usuario(nombre='V', login='v', rol='Vendedora', password_hash=generate_password_hash(CLAVE)))
            db.session.commit()
        return self.app

    def tearDown(self):
        release(self.app)
        self.tmp.cleanup()

    def entrar(self, cliente=None):
        c = cliente or self.app.test_client()
        c.get('/iniciar-sesion')
        with c.session_transaction() as s:
            csrf = s['csrf']
        r = c.post('/iniciar-sesion', data={'csrf': csrf, 'login': 'v', 'password': CLAVE})
        self.assertEqual(r.status_code, 302)
        return c, r


class InactividadTests(SesionBase):
    def setUp(self):
        self.crear(SESSION_IDLE_MINUTES=30)

    def test_con_actividad_la_sesion_sigue_viva(self):
        c, _ = self.entrar()
        t0 = time.time()
        for minutos in (10, 25, 40, 65):  # cada petición renueva el reloj: nunca pasan 30 min sin actividad
            with mock.patch('app.auth.time.time', return_value=t0 + minutos * 60):
                self.assertEqual(c.get('/ventas').status_code, 200, minutos)

    def test_tras_la_inactividad_pide_acceso_de_nuevo(self):
        c, _ = self.entrar()
        with mock.patch('app.auth.time.time', return_value=time.time() + 31 * 60):
            r = c.get('/ventas')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/iniciar-sesion', r.headers['Location'])
        self.assertIn('expirada=1', r.headers['Location'])
        aviso = c.get('/iniciar-sesion?expirada=1').get_data(as_text=True)
        self.assertIn('inactividad', aviso)
        self.assertEqual(c.get('/ventas').status_code, 302)  # la sesión quedó limpia, no se reactiva sola

    def test_justo_antes_del_limite_aun_vale(self):
        c, _ = self.entrar()
        with mock.patch('app.auth.time.time', return_value=time.time() + 29 * 60):
            self.assertEqual(c.get('/ventas').status_code, 200)

    def test_los_estaticos_no_renuevan_la_sesion(self):
        c, _ = self.entrar()
        t0 = time.time()
        with mock.patch('app.auth.time.time', return_value=t0 + 20 * 60):
            r = c.get('/static/css/global.css')
            r.close()
        with mock.patch('app.auth.time.time', return_value=t0 + 40 * 60):
            self.assertEqual(c.get('/ventas').status_code, 302)  # 40 min desde la última petición real

    def test_la_cookie_vencida_no_se_reutiliza(self):
        c, _ = self.entrar()
        cookie = c.get_cookie('session').value
        otro = self.app.test_client()
        otro.set_cookie('session', cookie)
        with mock.patch('app.auth.time.time', return_value=time.time() + 31 * 60):
            self.assertEqual(otro.get('/ventas').status_code, 302)

    def test_cada_acceso_nuevo_reinicia_el_reloj(self):
        c, _ = self.entrar()
        t0 = time.time()
        with mock.patch('app.auth.time.time', return_value=t0 + 31 * 60):
            self.assertEqual(c.get('/ventas').status_code, 302)
            c2, _ = self.entrar(c)
            self.assertEqual(c2.get('/ventas').status_code, 200)


class ConfiguracionTests(SesionBase):
    def test_el_tiempo_de_inactividad_es_configurable(self):
        self.crear(SESSION_IDLE_MINUTES=5)
        c, _ = self.entrar()
        with mock.patch('app.auth.time.time', return_value=time.time() + 6 * 60):
            self.assertEqual(c.get('/ventas').status_code, 302)

    def test_por_defecto_son_30_minutos(self):
        with mock.patch.dict(os.environ, {'SESSION_IDLE_MINUTES': ''}):
            self.crear()
        self.assertEqual(self.app.config['SESSION_IDLE_MINUTES'], 30)

    def test_la_variable_de_entorno_fija_la_inactividad_y_un_valor_invalido_cae_a_30(self):
        with mock.patch.dict(os.environ, {'SESSION_IDLE_MINUTES': '12'}):
            self.crear()
        self.assertEqual(self.app.config['SESSION_IDLE_MINUTES'], 12)
        release(self.app)
        self.tmp.cleanup()
        with mock.patch.dict(os.environ, {'SESSION_IDLE_MINUTES': 'abc'}):
            self.crear()
        self.assertEqual(self.app.config['SESSION_IDLE_MINUTES'], 30)

    def test_cookie_httponly_samesite_y_sin_secure_por_defecto(self):
        with mock.patch.dict(os.environ, {'SESSION_COOKIE_SECURE': ''}):
            self.crear()
        _, r = self.entrar()
        cookie = r.headers.get('Set-Cookie')
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Lax', cookie)
        self.assertNotIn('Secure', cookie)

    def test_secure_se_activa_por_variable_de_entorno(self):
        with mock.patch.dict(os.environ, {'SESSION_COOKIE_SECURE': '1'}):
            self.crear()
        self.assertTrue(self.app.config['SESSION_COOKIE_SECURE'])
        c = self.app.test_client()
        r = c.get('/iniciar-sesion', base_url='https://localhost')
        self.assertIn('Secure', r.headers.get('Set-Cookie', ''))

    def test_secure_se_activa_por_configuracion(self):
        self.crear(SESSION_COOKIE_SECURE=True)
        r = self.app.test_client().get('/iniciar-sesion', base_url='https://localhost')
        self.assertIn('Secure', r.headers.get('Set-Cookie', ''))

    def test_limitacion_documentada_sin_invalidacion_en_servidor(self):
        """La limitación conocida queda fijada: cerrar sesión no invalida una copia de la cookie."""
        self.crear()
        c, _ = self.entrar()
        copia = self.app.test_client()
        copia.set_cookie('session', c.get_cookie('session').value)
        c.get('/ventas')
        with c.session_transaction() as s:
            csrf = s['csrf']
        c.post('/cerrar-sesion', data={'csrf': csrf})
        self.assertEqual(copia.get('/ventas').status_code, 200)  # limitación documentada en docs/SEGURIDAD.md
        doc = (Path(__file__).resolve().parent.parent / 'docs' / 'SEGURIDAD.md').read_text(encoding='utf-8')
        self.assertIn('sin invalidación en servidor', doc)

    def test_editar_o_desactivar_al_usuario_si_invalida_la_sesion(self):
        self.crear()
        c, _ = self.entrar()
        with self.app.app_context():
            u = db.session.scalar(db.select(Usuario))
            u.activo = False
            db.session.commit()
        self.assertEqual(c.get('/ventas').status_code, 302)


if __name__ == '__main__':
    unittest.main()
