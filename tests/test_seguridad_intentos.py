"""Seguridad: límite de intentos de acceso por usuario y por red, con auditoría de los fallos."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from werkzeug.security import generate_password_hash

import app.auth as auth
from _cleanup import release
from app import create_app
from app.extensions import db
from app.models.gestion import RegistroGestion, Usuario

CLAVE = 'clave_prueba_123'
AVISO = 'Espera cinco minutos'


class IntentosTests(unittest.TestCase):
    def setUp(self):
        auth._attempts.clear()
        auth._attempts_ip.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'DATABASE': str(Path(self.tmp.name) / 'db.sqlite'), 'SECRET_KEY': 'test',
                               'AUTH_REQUIRED': True})
        with self.app.app_context():
            db.session.add_all([
                Usuario(nombre='ANA', login='ana', rol='Vendedora', password_hash=generate_password_hash(CLAVE)),
                Usuario(nombre='LUIS', login='luis', rol='Vendedora', password_hash=generate_password_hash(CLAVE)),
                Usuario(nombre='OFF', login='off', rol='Vendedora', password_hash=generate_password_hash(CLAVE), activo=False)])
            db.session.commit()
        self.reloj = 1000.0

    def tearDown(self):
        auth._attempts.clear()
        auth._attempts_ip.clear()
        release(self.app)
        self.tmp.cleanup()

    def intento(self, login, clave='mala', ip='10.0.0.1'):
        c = self.app.test_client()
        c.get('/iniciar-sesion', environ_overrides={'REMOTE_ADDR': ip})
        with c.session_transaction() as s:
            csrf = s['csrf']
        with mock.patch('app.auth.time.monotonic', side_effect=lambda: self.reloj):
            r = c.post('/iniciar-sesion', data={'csrf': csrf, 'login': login, 'password': clave},
                       environ_overrides={'REMOTE_ADDR': ip})
        return r.status_code == 302, AVISO in r.get_data(as_text=True)  # (entró, bloqueado)

    def registros(self, accion=None):
        with self.app.app_context():
            q = db.select(RegistroGestion).where(RegistroGestion.entidad == 'acceso').order_by(RegistroGestion.id)
            if accion:
                q = q.where(RegistroGestion.accion == accion)
            return [(r.entidad_id, r.accion, r.motivo, r.actor, dict(r.datos)) for r in db.session.scalars(q)]

    def test_cinco_fallos_del_mismo_usuario_bloquean_el_sexto(self):
        self.assertEqual([self.intento('ana')[1] for _ in range(6)], [False] * 5 + [True])
        self.assertEqual(self.intento('ana', CLAVE), (False, True))  # ni la clave correcta entra durante el bloqueo

    def test_veinte_fallos_desde_una_red_bloquean_a_todos_sus_usuarios(self):
        for i in range(20):
            self.assertEqual(self.intento(f'inventado{i}'), (False, False), i)  # cada nombre distinto, uno solo por vez
        self.assertEqual(self.intento('luis', CLAVE), (False, True))  # un usuario real que nunca falló también espera
        self.assertEqual(self.intento('inventado99'), (False, True))

    def test_otra_red_no_se_ve_afectada(self):
        for i in range(20):
            self.intento(f'inventado{i}')
        self.assertEqual(self.intento('luis', CLAVE, ip='10.0.0.2'), (True, False))

    def test_el_bloqueo_vence_a_los_cinco_minutos(self):
        for _ in range(5):
            self.intento('ana')
        self.assertTrue(self.intento('ana', CLAVE)[1])
        self.reloj += 301
        self.assertEqual(self.intento('ana', CLAVE), (True, False))

    def test_un_acceso_correcto_no_cuenta_y_reinicia_el_contador_del_usuario(self):
        for _ in range(4):
            self.intento('ana')
        self.assertEqual(self.intento('ana', CLAVE), (True, False))
        self.assertEqual([self.intento('ana')[1] for _ in range(5)], [False] * 5)  # vuelve a tener sus cinco

    def test_cada_fallo_queda_en_la_auditoria_sin_la_clave(self):
        self.intento('ana', 'secreto-que-no-debe-guardarse')
        self.intento('nadie', 'otra-clave-secreta')
        self.intento('off', CLAVE)
        filas = self.registros('Inicio de sesión fallido')
        self.assertEqual([f[2] for f in filas], ['Contraseña incorrecta', 'Usuario inexistente', 'Usuario inactivo'])
        with self.app.app_context():
            ids = {u.login: u.id for u in db.session.scalars(db.select(Usuario))}
        self.assertEqual([f[0] for f in filas], [ids['ana'], 0, ids['off']])
        self.assertEqual([f[4]['login'] for f in filas], ['ana', 'nadie', 'off'])
        for f in filas:
            self.assertEqual(f[3], 'Acceso (sin sesión)')
            self.assertEqual(f[4]['ip'], '10.0.0.1')
        volcado = json.dumps(filas) + json.dumps(self.registros())
        self.assertNotIn('secreto-que-no-debe-guardarse', volcado)
        self.assertNotIn('otra-clave-secreta', volcado)
        self.assertNotIn(CLAVE, volcado)

    def test_el_bloqueo_queda_auditado_una_sola_vez_y_sin_inundar_la_tabla(self):
        for _ in range(40):
            self.intento('ana')
        self.assertEqual(len(self.registros('Inicio de sesión fallido')), 5)  # los bloqueados ya no escriben
        bloqueos = self.registros('Bloqueo temporal de acceso')
        self.assertEqual(len(bloqueos), 1)
        self.assertEqual(bloqueos[0][4]['por'], 'usuario')

    def test_el_bloqueo_por_red_tambien_queda_auditado_y_acotado(self):
        for i in range(60):
            self.intento(f'x{i}')
        self.assertEqual(len(self.registros('Inicio de sesión fallido')), 20)
        bloqueos = self.registros('Bloqueo temporal de acceso')
        self.assertEqual([b[4]['por'] for b in bloqueos], ['red'])

    def test_un_acceso_correcto_no_genera_registro_de_fallo(self):
        self.assertEqual(self.intento('luis', CLAVE), (True, False))
        self.assertEqual(self.registros(), [])

    def test_los_contadores_antiguos_se_podan_de_la_memoria(self):
        for i in range(1100):
            auth._attempts[('1.1.1.1', f'u{i}')].append(10.0)
            auth._attempts_ip[f'ip{i}'].append(10.0)
        self.reloj = 10.0 + auth.VENTANA + 5
        self.intento('ana')
        self.assertLess(len(auth._attempts), 50)
        self.assertLess(len(auth._attempts_ip), 50)

    def test_limitacion_en_memoria_documentada(self):
        doc = (Path(__file__).resolve().parent.parent / 'docs' / 'SEGURIDAD.md').read_text(encoding='utf-8')
        self.assertIn('en memoria', doc)
        self.assertIn('LIMITACIÓN CONOCIDA', Path(auth.__file__).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
