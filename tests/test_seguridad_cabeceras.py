"""Seguridad: cabeceras en todas las respuestas y política de contenido compatible con el sitio."""
import re
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

from _cleanup import release
from app import create_app
from app.extensions import db
from app.models.gestion import Usuario
from app.security import CSP

RAIZ = Path(__file__).resolve().parent.parent
PLANTILLAS = RAIZ / 'app' / 'templates'


def directivas(csp):
    return {p.split()[0]: p.split()[1:] for p in csp.split(';') if p.strip()}


class CabecerasTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'DATABASE': str(Path(self.tmp.name) / 'db.sqlite'), 'SECRET_KEY': 'test',
                               'AUTH_REQUIRED': True})
        with self.app.app_context():
            db.session.add(Usuario(nombre='P', login='p', rol='Propietario', password_hash=generate_password_hash('clave_prueba_123')))
            db.session.commit()
            u = db.session.scalar(db.select(Usuario))
            self.uid, self.version = u.id, u.session_version
        self.c = self.app.test_client()
        with self.c.session_transaction() as s:
            s.update(usuario_id=self.uid, usuario_version=self.version, csrf='test')

    def tearDown(self):
        release(self.app)
        self.tmp.cleanup()

    def revisar(self, r, ruta):
        h = r.headers
        self.assertEqual(h.get('X-Frame-Options'), 'DENY', ruta)
        self.assertEqual(h.get('X-Content-Type-Options'), 'nosniff', ruta)
        self.assertEqual(h.get('Referrer-Policy'), 'same-origin', ruta)
        self.assertEqual(h.get('Content-Security-Policy'), CSP, ruta)

    def test_todas_las_respuestas_llevan_las_cabeceras(self):
        anonimo = self.app.test_client()
        for ruta in ('/iniciar-sesion', '/', '/inventario', '/ventas', '/finanzas', '/modulos/tributario/', '/usuarios',
                     '/static/css/global.css', '/no-existe'):
            r = self.c.get(ruta)
            self.revisar(r, ruta)
            r.close()
        self.revisar(anonimo.get('/'), '/ (anónimo, redirección)')
        self.revisar(self.c.post('/finanzas', data={'csrf': 'mala'}), 'POST sin CSRF (400)')
        self.revisar(self.c.get('/modulos/tributario/paquete.xlsx?ini=2026-01-01&fin=2026-01-31'), 'paquete.xlsx')

    def test_no_se_pisan_las_cabeceras_propias_de_la_descarga(self):
        r = self.c.get('/modulos/tributario/paquete.pdf?ini=2026-01-01&fin=2026-01-31')
        self.assertEqual(r.headers['Cache-Control'], 'no-store')
        self.assertEqual(r.headers['X-Content-Type-Options'], 'nosniff')

    def test_politica_estricta_donde_importa(self):
        d = directivas(CSP)
        self.assertEqual(d['script-src'], ["'self'"])           # sin 'unsafe-inline' ni 'unsafe-eval' en scripts
        self.assertEqual(d['frame-ancestors'], ["'none'"])
        self.assertEqual(d['object-src'], ["'none'"])
        self.assertEqual(d['form-action'], ["'self'"])
        self.assertEqual(d['base-uri'], ["'self'"])
        self.assertNotIn("'unsafe-eval'", CSP)
        self.assertNotIn('*', d['default-src'] + d['script-src'] + d['connect-src'])

    def test_el_sitio_no_usa_nada_que_la_politica_bloquee(self):
        d = directivas(CSP)
        for archivo in PLANTILLAS.rglob('*.html'):
            html = archivo.read_text(encoding='utf-8')
            rel = archivo.relative_to(PLANTILLAS)
            for m in re.finditer(r'<script\b([^>]*)>', html):
                atributos = m.group(1)
                self.assertTrue('src=' in atributos or 'application/json' in atributos, f'script en línea en {rel}')
            self.assertIsNone(re.search(r'\son(click|change|submit|load|input|error|focus|blur|keyup|keydown)\s*=', html),
                              f'manejador de evento en línea en {rel}')
            self.assertIsNone(re.search(r'javascript:', html, re.I), f'URL javascript: en {rel}')
            for host in re.findall(r'(?:src|href)="(https?://[^/"]+)', html):
                permitido = host in d['style-src'] + d['script-src'] + d['font-src'] + d['img-src']
                self.assertTrue(permitido, f'{host} usado en {rel} no está permitido por la política')

    def test_el_selector_de_anio_contable_se_envia_sin_manejador_en_linea(self):
        html = self.c.get('/modulos/tributario/').get_data(as_text=True)
        self.assertIn('data-auto-submit', html)
        self.assertNotIn('onchange=', html)
        js = (RAIZ / 'app' / 'static' / 'js' / 'navigation.js').read_text(encoding='utf-8')
        self.assertIn('select[data-auto-submit]', js)


if __name__ == '__main__':
    unittest.main()
