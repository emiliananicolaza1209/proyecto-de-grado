"""Seguridad: contraseñas de al menos 12 caracteres y sin claves comunes."""
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from _cleanup import release
from app import create_app
from app.extensions import db
from app.models.gestion import Socio, Usuario
from app.passwords import MINIMO, problema_de_clave, validar_clave

BUENAS = ['correcto-caballo-bateria-9', 'Mi.Perro.Come.Arepa.2026', 'zorro_Luna_cobre_77_tinta', 'T4ller#Rojo#Vidrio#58']
COMUNES = ['password1234', 'Password-2026!', 'Contraseña123456', 'contrasena2026', 'qwertyuiop12', '123456789012',
           'aaaaaaaaaaaa', 'abababababab', 'abcdefghijkl', '987654321098', 'Administrador#2026', 'CPStore.2026.CPStore',
           'Bucaramanga2026!', 'iloveyou1234', 'Prueba-Propietario-01', '1q2w3e4r5t6y', '111111111111', '!!!!!!!!!!!!']


class ValidadorTests(unittest.TestCase):
    def test_minimo_de_doce_caracteres(self):
        self.assertEqual(MINIMO, 12)
        self.assertIn('al menos 12', problema_de_clave('Corta#1x'))
        self.assertIn('al menos 12', problema_de_clave(''))
        self.assertIn('al menos 12', problema_de_clave(None))
        self.assertIsNone(problema_de_clave('zorro_Luna_cobre_77_tinta'))

    def test_maximo_para_no_cargar_el_servidor(self):
        self.assertIn('no puede superar', problema_de_clave('a1B' * 50))

    def test_rechaza_claves_comunes_y_sus_variantes(self):
        for clave in COMUNES:
            with self.subTest(clave=clave):
                self.assertIsNotNone(problema_de_clave(clave), clave)

    def test_acepta_claves_propias(self):
        for clave in BUENAS:
            with self.subTest(clave=clave):
                self.assertIsNone(problema_de_clave(clave), clave)

    def test_rechaza_claves_con_el_usuario_o_el_nombre(self):
        self.assertIn('usuario ni el nombre', problema_de_clave('zorro_Luna_ana.perez_77', 'ana.perez', 'Ana'))
        self.assertIn('usuario ni el nombre', problema_de_clave('tinta_Roja_MARIA-LOPEZ_9', 'ml', 'María López'))
        self.assertIsNone(problema_de_clave('zorro_Luna_cobre_77_tinta', 'ana', 'Ana'))  # datos cortos no cuentan

    def test_validar_clave_lanza_valueerror(self):
        with self.assertRaises(ValueError):
            validar_clave('password1234')
        validar_clave('zorro_Luna_cobre_77_tinta')

    def test_las_tildes_y_mayusculas_no_evaden_la_lista(self):
        for clave in ('CONTRASEÑA-123456', 'Contraseña_Segura', 'ADMINISTRADOR-2026'):
            self.assertIsNotNone(problema_de_clave(clave), clave)


class UsuariosRutaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'DATABASE': str(Path(self.tmp.name) / 'db.sqlite'), 'SECRET_KEY': 'test',
                               'AUTH_REQUIRED': True})
        with self.app.app_context():
            p = Usuario(nombre='DUEÑO', login='dueno', rol='Propietario', password_hash=generate_password_hash('zorro_Luna_cobre_77_tinta'))
            db.session.add(p)
            db.session.commit()
            self.pid, self.pv = p.id, p.session_version
        self.c = self.app.test_client()
        with self.c.session_transaction() as s:
            s.update(usuario_id=self.pid, usuario_version=self.pv, csrf='test')

    def tearDown(self):
        release(self.app)
        self.tmp.cleanup()

    def guardar(self, clave, login='nuevo', **extra):
        datos = dict(csrf='test', name='NUEVO', login=login, role='Vendedora', active='1', password=clave)
        datos.update(extra)
        r = self.c.post('/usuarios', data=datos, follow_redirects=True)
        return r.get_data(as_text=True)

    def existe(self, login):
        with self.app.app_context():
            return db.session.scalar(db.select(Usuario).where(Usuario.login == login))

    def test_crear_usuario_con_clave_comun_se_rechaza_y_no_crea_nada(self):
        for clave in ('password1234', 'Contraseña123456', 'abcdefghijkl'):
            html = self.guardar(clave)
            self.assertIsNone(self.existe('nuevo'), clave)
            self.assertTrue('demasiado comunes' in html or 'secuencia' in html or 'más usadas' in html, clave)

    def test_crear_usuario_con_clave_corta_se_rechaza(self):
        self.assertIn('al menos 12', self.guardar('Corta#1x'))
        self.assertIsNone(self.existe('nuevo'))

    def test_crear_usuario_con_su_propio_nombre_en_la_clave_se_rechaza(self):
        html = self.guardar('zorro_Luna_nuevo_77', login='nuevo')
        self.assertIn('usuario ni el nombre', html)
        self.assertIsNone(self.existe('nuevo'))

    def test_clave_buena_crea_el_usuario_con_hash(self):
        self.guardar('zorro_Luna_cobre_88_tinta')
        u = self.existe('nuevo')
        self.assertIsNotNone(u)
        self.assertNotIn('zorro', u.password_hash)
        self.assertTrue(check_password_hash(u.password_hash, 'zorro_Luna_cobre_88_tinta'))

    def test_cambiar_clave_a_una_comun_se_rechaza_y_conserva_la_anterior(self):
        self.guardar('zorro_Luna_cobre_88_tinta')
        u = self.existe('nuevo')
        html = self.guardar('password1234', id=str(u.id))
        self.assertIn('demasiado comunes', html)
        with self.app.app_context():
            actual = db.session.get(Usuario, u.id)
            self.assertTrue(check_password_hash(actual.password_hash, 'zorro_Luna_cobre_88_tinta'))

    def test_editar_sin_clave_no_la_toca_ni_la_exige(self):
        self.guardar('zorro_Luna_cobre_88_tinta')
        u = self.existe('nuevo')
        self.guardar('', id=str(u.id), name='NUEVO CAMBIADO')
        with self.app.app_context():
            actual = db.session.get(Usuario, u.id)
            self.assertEqual(actual.nombre, 'NUEVO CAMBIADO')
            self.assertTrue(check_password_hash(actual.password_hash, 'zorro_Luna_cobre_88_tinta'))

    def test_usuario_nuevo_sin_clave_se_rechaza(self):
        self.assertIn('al menos 12', self.guardar(''))
        self.assertIsNone(self.existe('nuevo'))

    def test_socio_exige_socio_asociado_y_misma_politica(self):
        with self.app.app_context():
            socio = Socio(nombre='S1', activo=True)
            db.session.add(socio)
            db.session.commit()
            sid = socio.id
        self.guardar('password1234', login='socio1', role='Socio', partner_id=str(sid))
        self.assertIsNone(self.existe('socio1'))
        self.guardar('zorro_Luna_cobre_99_tinta', login='socio1', role='Socio', partner_id=str(sid))
        self.assertIsNotNone(self.existe('socio1'))


class CrearPropietarioCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'DATABASE': str(Path(self.tmp.name) / 'db.sqlite'), 'SECRET_KEY': 'test'})

    def tearDown(self):
        release(self.app)
        self.tmp.cleanup()

    def crear(self, clave, usuario='jefe'):
        runner = self.app.test_cli_runner()
        return runner.invoke(args=['crear-propietario', '--usuario', usuario, '--nombre', 'Jefe Prueba',
                                   '--password', clave], input=f'{clave}\n')

    def test_la_linea_de_comandos_aplica_la_misma_politica(self):
        r = self.crear('password1234')
        self.assertNotEqual(r.exit_code, 0)
        with self.app.app_context():
            self.assertIsNone(db.session.scalar(db.select(Usuario)))
        r = self.crear('zorro_Luna_cobre_77_tinta')
        self.assertEqual(r.exit_code, 0, r.output)
        with self.app.app_context():
            self.assertEqual(db.session.scalar(db.select(Usuario)).rol, 'Propietario')

    def test_la_linea_de_comandos_rechaza_la_clave_con_el_usuario(self):
        r = self.crear('zorro_Luna_jefeprueba_7', usuario='jefeprueba')
        self.assertNotEqual(r.exit_code, 0)


if __name__ == '__main__':
    unittest.main()
