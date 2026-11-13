"""docs/ACEPTACION.md: que la lista esté completa y que cada prueba que cita exista de verdad; y los criterios sobre arranque y claves."""
import importlib
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
DOC = RAIZ / 'docs' / 'ACEPTACION.md'
NOMBRE_DE_PRUEBA = re.compile(r'`(test_\w+\.\w+\.test_\w+)`')
sys.path.insert(0, str(RAIZ / 'tests'))


def filas_de_tabla(texto):
    return [l for l in texto.splitlines() if l.startswith('|') and not re.match(r'^\|[-\s|]+\|$', l)]


class ListaDeAceptacionTests(unittest.TestCase):
    def setUp(self):
        self.texto = DOC.read_text(encoding='utf-8')

    def test_cada_prueba_citada_existe(self):
        citadas = sorted(set(NOMBRE_DE_PRUEBA.findall(self.texto)))
        self.assertGreater(len(citadas), 80)
        faltan = []
        for nombre in citadas:
            modulo, clase, metodo = nombre.split('.')
            try:
                m = importlib.import_module(modulo)
                if not callable(getattr(getattr(m, clase), metodo, None)):
                    faltan.append(nombre)
            except (ImportError, AttributeError):
                faltan.append(nombre)
        self.assertEqual(faltan, [], 'La lista de aceptación cita pruebas que no existen')

    def test_las_columnas_pedidas(self):
        encabezados = [l for l in self.texto.splitlines() if l.startswith('| Caso |')]
        self.assertGreaterEqual(len(encabezados), 10)
        for e in encabezados:
            self.assertEqual([c.strip() for c in e.strip('|').split('|')],
                             ['Caso', 'Resultado esperado', 'Resultado real', 'Quién validó', 'Pendiente'])

    def test_cada_fila_automatizada_cita_al_menos_una_prueba(self):
        for fila in filas_de_tabla(self.texto):
            if '**AUTOMATIZADO**' in fila:
                self.assertRegex(fila, NOMBRE_DE_PRUEBA.pattern, fila[:80])

    def test_cada_fila_automatizada_dice_quien_la_valido(self):
        for fila in filas_de_tabla(self.texto):
            if '**AUTOMATIZADO** `' in fila:
                self.assertIn('Suite automática', fila, fila[:80])

    def test_estan_los_ocho_criterios_del_plan(self):
        titulos = re.findall(r'^### Criterio (\d) — (.+)$', self.texto, re.M)
        self.assertEqual([int(n) for n, _ in titulos], list(range(1, 9)))
        resumen = ' '.join(t.lower() for _, t in titulos)
        for palabra in ('https', 'permisos', 'validación', 'sesiones', 'conservados', 'restauración', 'duplicaciones', 'bloqueados', 'evidencias'):
            self.assertIn(palabra, resumen)

    def test_estan_los_16_casos_de_las_cuatro_consultas(self):
        ids = re.findall(r'\|\s*(?:\*\*\w+\*\* )?((?:EI|CP|RV|RF)-\d)\b', self.texto)
        self.assertEqual(sorted(ids), sorted(f'{p}-{n}' for p in ('EI', 'CP', 'RV', 'RF') for n in range(1, 5)))

    def test_hay_casos_manuales_para_la_url_desplegada_y_pendientes(self):
        seccion = self.texto.split('## C.')[1].split('## D.')[0]
        casos = re.findall(r'^\| (C\d+) ', seccion, re.M)
        self.assertGreaterEqual(len(casos), 15)
        self.assertIn('## D. Pendientes', self.texto)

    def test_marca_lo_que_no_se_probo_con_postgresql_y_lo_que_esta_sin_probar(self):
        self.assertIn('(PG)', self.texto)
        self.assertIn('sin probar', self.texto)
        self.assertIn('Nada de esto se ha ejecutado contra PostgreSQL', self.texto)

    def test_la_suite_citada_no_es_un_marcador_sin_llenar(self):
        self.assertNotIn('{{SUITE}}', self.texto)
        self.assertRegex(self.texto, r'\*\*Suite automática completa al 11-nov-2026:\*\* `\d+` pruebas')

    def test_dice_que_las_pruebas_automaticas_no_prueban_la_url_desplegada(self):
        self.assertIn('no** que la URL desplegada esté bien configurada', self.texto)


class AceptacionTests(unittest.TestCase):
    def test_arranque_sin_depuracion(self):
        codigo = (RAIZ / 'run.py').read_text(encoding='utf-8')
        self.assertNotRegex(codigo, r'debug\s*=\s*True')
        self.assertNotIn('use_debugger', codigo)
        from app import create_app
        entorno = {k: v for k, v in os.environ.items() if k not in ('FLASK_DEBUG', 'FLASK_ENV')}
        with mock.patch.dict(os.environ, entorno, clear=True):
            import tempfile
            from _cleanup import release
            tmp = tempfile.TemporaryDirectory()
            app = create_app({'DATABASE': str(Path(tmp.name) / 'db.sqlite'), 'SECRET_KEY': 'x'})
            try:
                self.assertFalse(app.debug)
                self.assertFalse(app.config.get('DEBUG'))
                self.assertEqual(app.test_client().get('/console').status_code, 404)  # no existe la consola interactiva del depurador
            finally:
                release(app)
                tmp.cleanup()

    def test_el_repositorio_no_trae_claves_ni_env(self):
        self.assertIn('.env', (RAIZ / '.gitignore').read_text(encoding='utf-8').splitlines())
        git = shutil.which('git')
        if git:
            r = subprocess.run([git, 'ls-files'], cwd=RAIZ, capture_output=True, text=True, encoding='utf-8', timeout=60)
            versionados = r.stdout.splitlines()
            self.assertFalse([f for f in versionados if Path(f).name == '.env' or f.endswith(('.pem', '.key'))])
            self.assertFalse([f for f in versionados if f.startswith('instance/')])
        patrones = (r"SECRET_KEY['\"]?\s*[:=]\s*['\"][^'\"\s]{8,}['\"]", r'sk_[0-9a-f]{32,}', r'postgres(ql)?://(?!usuario:clave@)\w+:\w+@')
        for carpeta in ('app', 'scripts', 'migrations'):
            for ruta in (RAIZ / carpeta).rglob('*'):
                if ruta.suffix in ('.py', '.html', '.js', '.json', '.md') and ruta.is_file():
                    texto = ruta.read_text(encoding='utf-8', errors='ignore')
                    for patron in patrones:
                        self.assertIsNone(re.search(patron, texto), f'{ruta}: {patron}')
        for suelto in ('run.py', 'init_db.py', 'seed_runner.py'):
            texto = (RAIZ / suelto).read_text(encoding='utf-8', errors='ignore')
            for patron in patrones:
                self.assertIsNone(re.search(patron, texto), f'{suelto}: {patron}')


if __name__ == '__main__':
    unittest.main()
