import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import patch
from flask import Flask, session
from app import create_app
from app.extensions import db
from app.navigation import safe_path
from app.runtime import configure_runtime


class NavigationSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=create_app({'TESTING':True,'DATABASE':str(Path(self.tmp.name)/'test.sqlite'),'SECRET_KEY':'test'})
        self.client=self.app.test_client()
    def tearDown(self):
        with self.app.app_context():db.session.remove();db.engine.dispose()
        self.tmp.cleanup()
    def test_return_url_keeps_local_filters_and_rejects_external_or_encoded_host(self):
        for bad in ('https://evil.example','//evil.example','/%2Fevil.example','/\\evil.example','/a%0d%0aLocation:evil', '/api/consultas/ventas','/static/file.js'):
            self.assertIsNone(safe_path(bad),bad)
        target='/ventas?estado=Vendido&saldo=1&q=IPHONE'
        self.assertEqual(safe_path(target),target)
        response=self.client.get('/usuarios',headers={'Referer':'http://localhost'+target})
        self.assertIn(b'href="/ventas?estado=Vendido&amp;saldo=1&amp;q=IPHONE"',response.data)
        response=self.client.get('/usuarios?volver=//evil.example',headers={'Referer':'https://evil.example/test'})
        self.assertNotIn(b'href="//evil.example',response.data)
        self.assertEqual(self.client.get('/usuarios',headers={'Referer':'https://['}).status_code,200)
    def test_sidebar_stays_separate_from_topbar_and_errors_have_back_link(self):
        page=self.client.get('/ventas').get_data(as_text=True)
        sidebar=page.split('<aside',1)[1].split('</aside>',1)[0]
        topbar=page.split('<header',1)[1].split('</header>',1)[0]
        self.assertIn('Navegación principal',sidebar)
        self.assertNotIn('Navegación principal',topbar)
        self.assertIn('data-app-back',page)
        error=self.client.get('/una-pagina-que-no-existe')
        self.assertEqual(error.status_code,404)
        self.assertIn(b'data-app-back',error.data)
    def test_security_headers_and_csrf(self):
        response=self.client.get('/')
        self.assertEqual(response.headers['X-Frame-Options'],'DENY')
        self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
        self.assertIn("script-src 'self'",response.headers['Content-Security-Policy'])
        self.assertNotIn("script-src 'self' 'unsafe-inline'",response.headers['Content-Security-Policy'])
        self.assertEqual(self.client.post('/usuarios',data={}).status_code,400)
        self.assertNotIn('onchange=',self.client.get('/modulos/tributario/').get_data(as_text=True))
    def test_health_exposes_no_rows_and_sets_no_session_cookie(self):
        response=self.client.get('/healthz')
        self.assertEqual(response.json,{'status':'ok'})
        self.assertNotIn('Set-Cookie',response.headers)


class ProductionConfigurationTests(unittest.TestCase):
    def app(self,**changes):
        app=Flask('production_test')
        app.config.update(APP_ENV='production',SECRET_KEY='a'*64,_SECRET_KEY_CONFIGURED=True,
            DATABASE_URL='postgresql://test:unused@db.invalid/test',TRUSTED_HOSTS=['app.example'],
            UPLOADS_ENABLED=False)
        app.config.update(changes)
        return app
    def test_production_fails_closed_for_missing_database_or_key(self):
        with patch.dict('os.environ',{},clear=True):
            for values in ({'DATABASE_URL':''},{'SECRET_KEY':'short'},{'_SECRET_KEY_CONFIGURED':False}):
                with self.assertRaises(ValueError):configure_runtime(self.app(**values))
    def test_secure_session_auth_and_trusted_host(self):
        app=self.app(AUTH_REQUIRED=False,SESSION_COOKIE_SECURE=False,DEBUG=True)
        configure_runtime(app)
        self.assertTrue(app.config['AUTH_REQUIRED']);self.assertFalse(app.config['DEBUG'])
        self.assertTrue(app.config['SESSION_COOKIE_SECURE'])
        @app.get('/')
        def index():session['value']='test';return 'ok'
        client=app.test_client()
        response=client.get('/',base_url='https://app.example')
        self.assertIn('Secure',response.headers['Set-Cookie'])
        self.assertIn('HttpOnly',response.headers['Set-Cookie'])
        self.assertIn('SameSite=Lax',response.headers['Set-Cookie'])
        self.assertEqual(client.get('/',base_url='https://evil.example').status_code,400)
    def test_uploads_cannot_be_enabled_on_ephemeral_storage(self):
        with self.assertRaises(ValueError):configure_runtime(self.app(UPLOADS_ENABLED=True,PERSISTENT_INSTANCE=False))
        app=self.app(UPLOADS_ENABLED=True,PERSISTENT_INSTANCE=True)
        configure_runtime(app);self.assertTrue(app.config['UPLOADS_ENABLED'])


if __name__=='__main__':unittest.main()
