"""Respaldo y restauración (scripts/respaldo.py con SQLite probado de verdad; scripts/respaldo_postgres.py con herramientas simuladas)."""
import ast
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from werkzeug.datastructures import MultiDict

from test_consulta_resumen_ventas import VentasBase
from _cleanup import release
from app import create_app
from app.extensions import db
from app.models import Catalogo, Producto
from app.models.finanzas import OperacionFinanciera as Op
from app.models.gestion import FacturaLote
from app.services import compras_service
from app.services.inventario_service import stats

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'scripts'))
import respaldo as rp  # noqa: E402
import respaldo_postgres as rpg  # noqa: E402

SECRETO = 'valor-secreto-que-jamas-debe-copiarse-9f3a'


def sha(contenido):
    return hashlib.sha256(contenido).hexdigest()


class RespaldoBase(VentasBase):
    """Base real (todas las migraciones) con ventas, inventario y dos facturas adjuntas."""

    def setUp(self):
        super().setUp()
        self.raiz = Path(self.tmp.name)
        self.base = self.raiz / 'db.sqlite'
        self.soportes = self.raiz / 'facturas'
        self.soportes.mkdir()
        self.copias = self.raiz / 'copias'
        self.vender(monto='650000')
        self.vender(monto='1200000', con_equipo=False)
        self.equipo(costo=250000000)
        proveedor = db.session.scalar(db.select(Catalogo).where(Catalogo.kind == 'supplier', Catalogo.active == 1))
        lote = compras_service.create(MultiDict({'supplier_id': str(proveedor.id), 'currency': 'COP', 'expected_count': '1',
                                                 'entry_date': '2026-01-15'}))
        db.session.flush()
        self.facturas = {}
        for i, contenido in enumerate((b'%PDF-1.4 factura uno ' + b'x' * 500, b'%PDF-1.4 factura dos ' + b'y' * 900)):
            nombre = f'{i:02d}{"ab" * 23}.pdf'
            (self.soportes / nombre).write_bytes(contenido)
            self.facturas[nombre] = contenido
            db.session.add(FacturaLote(lote_id=lote.id, nombre=f'factura{i}.pdf', archivo=nombre, mime='application/pdf', sha256=sha(contenido)))
        db.session.commit()

    def copiar(self, **kw):
        salida = []
        r = rp.copiar(kw.pop('base', self.base), kw.pop('soportes', self.soportes), kw.pop('destino', self.copias), salida=salida.append, **kw)
        return r, '\n'.join(salida)

    def copia_buena(self):
        return self.copiar()[0]['copia']

    def destino(self, nombre='restaurado'):
        return self.raiz / nombre

    def sin_restos(self, carpeta):
        return [p.name for p in carpeta.iterdir() if p.name.startswith(('.en_curso_', '.restaurando_'))] if carpeta.exists() else []


class CopiarTests(RespaldoBase):
    def test_la_copia_se_llama_con_fecha_y_hora_y_trae_base_soportes_y_verificacion(self):
        momento = datetime(2026, 11, 12, 18, 30, 5, tzinfo=rp.COLOMBIA)
        r, _ = self.copiar(momento=momento)
        self.assertEqual(r['copia'].name, 'cpstore_20261112_183005')
        self.assertRegex(r['copia'].name, rp.PATRON_COPIA)
        self.assertEqual(sorted(p.name for p in r['copia'].iterdir()), ['cpstore.sqlite', 'soportes', 'verificacion.json'])
        self.assertEqual(sorted(p.name for p in (r['copia'] / 'soportes').iterdir()), sorted(self.facturas))

    def test_el_nombre_usa_la_hora_de_colombia_por_defecto(self):
        r, _ = self.copiar()
        self.assertRegex(r['copia'].name, r'^cpstore_\d{8}_\d{6}$')
        self.assertEqual(r['verificacion']['creada_en'][-6:], '-05:00')

    def test_la_verificacion_trae_esquema_conteos_controles_y_huellas(self):
        v = self.copia_buena() and rp.leer_verificacion(next(self.copias.iterdir()))
        original = sqlite3.connect(self.base)
        versiones = [x[0] for x in original.execute('SELECT version FROM schema_version ORDER BY version')]
        self.assertEqual(v['version_esquema'], {'version': max(versiones), 'versiones': versiones})
        tablas = [x[0] for x in original.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        self.assertEqual(v['tablas'], {t: original.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tablas})
        original.close()
        self.assertGreaterEqual(len(v['tablas']), 40)
        ventas = db.session.scalars(db.select(Op).where(Op.kind == 'Venta', Op.voided == False)).all()  # noqa: E712
        self.assertEqual(v['control']['ventas_netas'], {'operaciones': len(ventas), 'total_cents': sum(o.amount for o in ventas)})
        s = stats()
        self.assertEqual(v['control']['inventario_disponible'], {'equipos': s['total'], 'costo_cents': s['cost']})
        self.assertEqual({x['archivo']: x['sha256'] for x in v['soportes']}, {n: sha(c) for n, c in self.facturas.items()})
        self.assertEqual(v['base']['sha256'], sha((next(self.copias.iterdir()) / 'cpstore.sqlite').read_bytes()))
        self.assertEqual(v['motor'], 'sqlite')
        self.assertEqual(v['avisos'], [a for a in v['avisos'] if 'mismo disco' in a])  # el único aviso: mismo disco en la prueba

    def test_los_totales_de_control_no_son_cero_en_la_prueba(self):
        v = self.copiar()[0]['verificacion']
        self.assertGreater(v['control']['ventas_netas']['total_cents'], 0)
        self.assertGreater(v['control']['inventario_disponible']['equipos'], 0)

    def test_la_copia_es_consistente_aunque_haya_una_escritura_sin_terminar(self):
        escritor = sqlite3.connect(self.base, isolation_level=None)
        escritor.execute('BEGIN IMMEDIATE')
        escritor.execute('INSERT INTO schema_version (version) VALUES (999)')
        try:
            r, _ = self.copiar()
        finally:
            escritor.execute('ROLLBACK')
            escritor.close()
        copia = sqlite3.connect(r['copia'] / 'cpstore.sqlite')
        self.assertEqual(copia.execute('SELECT COUNT(*) FROM schema_version WHERE version = 999').fetchone()[0], 0)
        self.assertEqual(copia.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        copia.close()
        self.assertEqual(sorted(p.name for p in r['copia'].iterdir()), ['cpstore.sqlite', 'soportes', 'verificacion.json'])  # sin -journal

    def test_no_copia_env_claves_ni_secret_key_y_lo_avisa(self):
        for nombre in ('.env', '.session-secret', 'llave.pem', 'api.key', 'SECRET_KEY.txt'):
            (self.soportes / nombre).write_text(f'SECRET_KEY={SECRETO}\n')
        (self.raiz / '.env').write_text(f'SECRET_KEY={SECRETO}\n')
        (self.raiz / '.session-secret').write_text(SECRETO)
        with mock.patch.dict(os.environ, {'SECRET_KEY': SECRETO}):
            r, texto = self.copiar()
        self.assertEqual(sorted(p.name for p in (r['copia'] / 'soportes').iterdir()), sorted(self.facturas))
        for ruta in r['copia'].rglob('*'):
            self.assertFalse(rp.es_secreto(ruta.name), ruta.name)
            if ruta.is_file():
                self.assertNotIn(SECRETO.encode(), ruta.read_bytes(), ruta.name)
        self.assertEqual(sorted(r['verificacion']['excluidos']), ['.env', '.session-secret', 'SECRET_KEY.txt', 'api.key', 'llave.pem'])
        self.assertIn('NO incluye el archivo .env, las claves ni SECRET_KEY', texto)
        self.assertIn('Se omitieron 5 archivo(s)', texto)
        self.assertIn('.env', r['verificacion']['no_incluye'])

    def test_avisa_que_la_copia_tiene_datos_personales(self):
        self.assertIn('datos personales', self.copiar()[1])

    def test_avisa_si_la_copia_queda_en_el_mismo_disco(self):
        r, texto = self.copiar()
        self.assertIn('mismo disco', texto)

    def test_avisa_si_la_base_y_los_soportes_no_coinciden(self):
        nombre = next(iter(self.facturas))
        (self.soportes / nombre).write_bytes(b'otro contenido')  # la huella guardada en la base ya no coincide
        (self.soportes / 'huerfano.pdf').write_bytes(b'%PDF-1.4 sin factura en la base')
        v = self.copiar()[0]['verificacion']
        texto = ' '.join(v['avisos'])
        self.assertIn('no coincide con la huella guardada en la base', texto)
        self.assertIn('ninguna factura de la base lo cita', texto)

    def test_sin_carpeta_de_soportes_la_copia_se_hace_y_avisa_lo_que_falta(self):
        r, _ = self.copiar(soportes=self.raiz / 'no_existe')
        self.assertEqual(r['verificacion']['soportes'], [])
        self.assertIn('no está en la carpeta de soportes', ' '.join(r['verificacion']['avisos']))

    def test_no_sobrescribe_una_copia_existente(self):
        momento = datetime(2026, 11, 12, 18, 30, 5, tzinfo=rp.COLOMBIA)
        r, _ = self.copiar(momento=momento)
        antes = (r['copia'] / 'cpstore.sqlite').read_bytes()
        with self.assertRaises(rp.ErrorRespaldo) as e:
            self.copiar(momento=momento)
        self.assertIn('Ya existe una copia', str(e.exception))
        self.assertEqual(antes, (r['copia'] / 'cpstore.sqlite').read_bytes())
        self.assertEqual(self.sin_restos(self.copias), [])

    def test_errores_claros_de_uso(self):
        with self.assertRaises(rp.ErrorRespaldo) as e:
            self.copiar(base=self.raiz / 'no_hay.sqlite')
        self.assertIn('No existe la base de datos', str(e.exception))
        with self.assertRaises(rp.ErrorRespaldo):
            self.copiar(destino=self.soportes / 'copias')  # dentro de los soportes
        with self.assertRaises(rp.ErrorRespaldo):
            self.copiar(destino=self.base.parent)  # la carpeta de la base

    def test_un_fallo_a_la_mitad_no_deja_archivos_a_medias(self):
        with mock.patch.object(rp, '_copiar_soportes', side_effect=RuntimeError('se cortó la luz')):
            with self.assertRaises(RuntimeError):
                self.copiar()
        self.assertEqual(list(self.copias.iterdir()), [])

    def test_si_la_copia_de_la_base_no_pasa_la_revision_se_descarta(self):
        with mock.patch.object(rp, 'integridad', return_value='página 3 dañada'):
            with self.assertRaises(rp.ErrorRespaldo) as e:
                self.copiar()
        self.assertEqual(e.exception.codigo, 3)
        self.assertEqual(list(self.copias.iterdir()), [])

    def test_no_toca_la_base_original(self):
        antes = sha(self.base.read_bytes())
        self.copiar()
        self.assertEqual(antes, sha(self.base.read_bytes()))


class RestaurarTests(RespaldoBase):
    def test_restaura_en_una_ruta_nueva_y_verifica_todo(self):
        copia = self.copia_buena()
        salida = []
        r = rp.restaurar(copia, self.destino(), salida=salida.append)
        destino = self.destino()
        self.assertEqual(sorted(p.name for p in destino.iterdir()), ['cpstore.sqlite', 'soportes'])
        self.assertTrue(all(p['ok'] for p in r['pruebas']))
        nombres = [p['prueba'] for p in r['pruebas']]
        for esperado in ('PRAGMA integrity_check', 'Versión del esquema (schema_version)', 'Conteos por tabla', 'Total de control: ventas netas',
                         'Total de control: inventario disponible', 'Huellas de los soportes'):
            self.assertIn(esperado, nombres)
        texto = '\n'.join(salida)
        self.assertIn('[OK] PRAGMA integrity_check', texto)
        self.assertNotIn('FALLA', texto)
        self.assertEqual(sha((destino / 'cpstore.sqlite').read_bytes()), rp.leer_verificacion(copia)['base']['sha256'])
        self.assertEqual({p.name: sha(p.read_bytes()) for p in (destino / 'soportes').iterdir()}, {n: sha(c) for n, c in self.facturas.items()})
        self.assertEqual(self.sin_restos(self.raiz), [])

    def test_los_totales_restaurados_son_los_de_antes(self):
        copia = self.copia_buena()
        rp.restaurar(copia, self.destino(), salida=lambda *_: None)
        medidas = rp.inspeccionar_base(self.destino() / 'cpstore.sqlite')
        original = rp.inspeccionar_base(self.base)
        self.assertEqual(medidas['tablas'], original['tablas'])
        self.assertEqual(medidas['control'], original['control'])
        self.assertEqual(medidas['version_esquema'], original['version_esquema'])

    def test_la_aplicacion_abre_la_base_restaurada_con_las_mismas_cifras(self):
        from app.services import consultas_service as cs
        copia = self.copia_buena()
        rp.restaurar(copia, self.destino(), salida=lambda *_: None)
        original = cs.resumen_ventas('Propietario', self.hoy, self.hoy)['cifras']
        inventario_original = stats()
        app2 = create_app({'TESTING': True, 'DATABASE': str(self.destino() / 'cpstore.sqlite'), 'SECRET_KEY': 'otra'})
        try:
            with app2.app_context():
                restaurado = cs.resumen_ventas('Propietario', self.hoy, self.hoy)['cifras']
                self.assertEqual(restaurado, original)
                self.assertEqual(stats(), inventario_original)
        finally:
            release(app2)

    def test_se_niega_si_el_destino_ya_existe_y_no_toca_nada(self):
        copia = self.copia_buena()
        destino = self.destino()
        destino.mkdir()
        (destino / 'importante.txt').write_text('no me toques')
        with self.assertRaises(rp.ErrorRespaldo) as e:
            rp.restaurar(copia, destino, salida=lambda *_: None)
        self.assertEqual(e.exception.codigo, 2)
        self.assertIn('El destino ya existe', str(e.exception))
        self.assertIn('nunca sobrescribe', str(e.exception))
        self.assertEqual([p.name for p in destino.iterdir()], ['importante.txt'])
        self.assertEqual((destino / 'importante.txt').read_text(), 'no me toques')
        self.assertEqual(self.sin_restos(self.raiz), [])

    def test_se_niega_si_el_destino_es_un_archivo(self):
        copia = self.copia_buena()
        self.destino().write_text('soy un archivo')
        with self.assertRaises(rp.ErrorRespaldo):
            rp.restaurar(copia, self.destino(), salida=lambda *_: None)
        self.assertEqual(self.destino().read_text(), 'soy un archivo')

    def test_se_niega_si_la_carpeta_superior_no_existe_sin_crear_nada(self):
        copia = self.copia_buena()
        with self.assertRaises(rp.ErrorRespaldo) as e:
            rp.restaurar(copia, self.raiz / 'no' / 'existe' / 'destino', salida=lambda *_: None)
        self.assertIn('carpeta superior', str(e.exception))
        self.assertFalse((self.raiz / 'no').exists())

    def test_nunca_restaura_encima_de_la_base_en_uso(self):
        copia = self.copia_buena()
        for destino in (self.base, self.soportes, self.raiz):
            with self.assertRaises(rp.ErrorRespaldo):
                rp.restaurar(copia, destino, salida=lambda *_: None)
        self.assertTrue(self.base.is_file())

    def test_un_fallo_a_la_mitad_no_deja_archivos_a_medias(self):
        copia = self.copia_buena()
        with mock.patch.object(rp, 'verificar_restauracion', side_effect=OSError('disco lleno')):
            with self.assertRaises(OSError):
                rp.restaurar(copia, self.destino(), salida=lambda *_: None)
        self.assertFalse(self.destino().exists())
        self.assertEqual(self.sin_restos(self.raiz), [])


class CopiaDaniadaTests(RespaldoBase):
    def alterar(self, funcion):
        copia = self.copia_buena()
        funcion(copia)
        return copia

    def assertSeNiega(self, copia, texto, codigo=3):
        with self.assertRaises(rp.ErrorRespaldo) as e:
            rp.restaurar(copia, self.destino(), salida=lambda *_: None)
        self.assertEqual(e.exception.codigo, codigo)
        self.assertIn(texto, str(e.exception))
        self.assertFalse(self.destino().exists(), 'no debe quedar un destino a medias')
        self.assertEqual(self.sin_restos(self.raiz), [])

    def test_base_con_bytes_cambiados(self):
        def f(copia):
            ruta = copia / 'cpstore.sqlite'
            datos = bytearray(ruta.read_bytes())
            datos[4096:4196] = b'\x00' * 100
            ruta.write_bytes(bytes(datos))
        self.assertSeNiega(self.alterar(f), 'no coincide con su huella')

    def test_base_truncada(self):
        self.assertSeNiega(self.alterar(lambda c: (c / 'cpstore.sqlite').write_bytes((c / 'cpstore.sqlite').read_bytes()[:1500])),
                           'no coincide con su huella')

    def test_base_cambiada_por_basura_aunque_se_arregle_la_huella(self):
        def f(copia):
            basura = b'esto no es una base de datos' * 400
            (copia / 'cpstore.sqlite').write_bytes(basura)
            v = json.loads((copia / 'verificacion.json').read_text(encoding='utf-8'))
            v['base']['sha256'] = sha(basura)
            (copia / 'verificacion.json').write_text(json.dumps(v), encoding='utf-8')
        self.assertSeNiega(self.alterar(f), 'integridad')

    def test_soporte_alterado(self):
        nombre = next(iter(self.facturas))
        self.assertSeNiega(self.alterar(lambda c: (c / 'soportes' / nombre).write_bytes(b'alterado')), f'el soporte {nombre} no coincide')

    def test_soporte_que_falta(self):
        nombre = next(iter(self.facturas))
        self.assertSeNiega(self.alterar(lambda c: (c / 'soportes' / nombre).unlink()), f'falta el soporte {nombre}')

    def test_archivo_de_mas_en_los_soportes(self):
        self.assertSeNiega(self.alterar(lambda c: (c / 'soportes' / 'intruso.pdf').write_bytes(b'x')), 'no figura en la verificación')

    def test_sin_archivo_de_verificacion(self):
        self.assertSeNiega(self.alterar(lambda c: (c / 'verificacion.json').unlink()), 'no tiene verificacion.json')

    def test_verificacion_ilegible(self):
        self.assertSeNiega(self.alterar(lambda c: (c / 'verificacion.json').write_text('{ no es json')), 'está dañado')

    def test_verificacion_incompleta(self):
        def f(copia):
            v = json.loads((copia / 'verificacion.json').read_text(encoding='utf-8'))
            del v['tablas']
            (copia / 'verificacion.json').write_text(json.dumps(v), encoding='utf-8')
        self.assertSeNiega(self.alterar(f), 'no tiene la sección "tablas"')

    def test_la_copia_no_existe(self):
        self.assertSeNiega(self.raiz / 'no_hay_copia', 'No existe la carpeta de la copia', codigo=2)

    def test_conteos_que_no_coinciden_tras_restaurar_se_detectan_y_se_deshace(self):
        def f(copia):
            v = json.loads((copia / 'verificacion.json').read_text(encoding='utf-8'))
            v['tablas']['equipment'] += 1
            v['control']['ventas_netas']['total_cents'] += 100
            (copia / 'verificacion.json').write_text(json.dumps(v), encoding='utf-8')
        copia = self.alterar(f)
        with self.assertRaises(rp.ErrorRespaldo) as e:
            rp.restaurar(copia, self.destino(), salida=lambda *_: None)
        self.assertEqual(e.exception.codigo, 4)
        self.assertIn('Conteos por tabla', str(e.exception))
        self.assertIn('ventas netas', str(e.exception))
        self.assertFalse(self.destino().exists())
        self.assertEqual(self.sin_restos(self.raiz), [])

    def test_verificar_detecta_lo_mismo_sin_restaurar(self):
        copia = self.alterar(lambda c: (c / 'soportes' / next(iter(self.facturas))).write_bytes(b'x'))
        with self.assertRaises(rp.ErrorRespaldo) as e:
            rp.verificar_copia(copia)
        self.assertIn('dañada o fue modificada', str(e.exception))

    def test_una_copia_buena_pasa_verificar(self):
        self.assertEqual(rp.verificar_copia(self.copia_buena())['motor'], 'sqlite')


class LineaDeComandosTests(RespaldoBase):
    def correr(self, *args):
        return subprocess.run([sys.executable, str(RAIZ / 'scripts' / 'respaldo.py'), *map(str, args)], capture_output=True, text=True,
                              encoding='utf-8', timeout=120, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})

    def test_copiar_verificar_y_restaurar_por_consola(self):
        r = self.correr('copiar', '--base', self.base, '--soportes', self.soportes, '--destino', self.copias)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('Copia creada:', r.stdout)
        self.assertIn('NO incluye el archivo .env', r.stdout)
        copia = next(self.copias.iterdir())
        r = self.correr('verificar', '--copia', copia)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('está íntegra', r.stdout)
        r = self.correr('restaurar', '--copia', copia, '--destino', self.destino())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('[OK] PRAGMA integrity_check', r.stdout)
        self.assertNotIn('FALLA', r.stdout)

    def test_destino_existente_da_error_claro_y_codigo_2(self):
        copia = self.copia_buena()
        self.destino().mkdir()
        r = self.correr('restaurar', '--copia', copia, '--destino', self.destino())
        self.assertEqual(r.returncode, 2)
        self.assertIn('ERROR: El destino ya existe', r.stderr)
        self.assertEqual(r.stdout, '')
        self.assertNotIn('Traceback', r.stderr)

    def test_copia_corrupta_da_error_claro_y_codigo_3(self):
        copia = self.copia_buena()
        (copia / 'cpstore.sqlite').write_bytes(b'copia danada')
        r = self.correr('restaurar', '--copia', copia, '--destino', self.destino())
        self.assertEqual(r.returncode, 3)
        self.assertIn('ERROR: La copia está dañada', r.stderr)
        self.assertNotIn('Traceback', r.stderr)
        self.assertFalse(self.destino().exists())

    def test_base_inexistente_da_error_claro(self):
        r = self.correr('copiar', '--base', self.raiz / 'nada.sqlite', '--soportes', self.soportes, '--destino', self.copias)
        self.assertEqual(r.returncode, 2)
        self.assertIn('No existe la base de datos', r.stderr)

    def test_usa_database_path_por_defecto(self):
        r = subprocess.run([sys.executable, str(RAIZ / 'scripts' / 'respaldo.py'), 'copiar', '--soportes', str(self.soportes),
                            '--destino', str(self.copias)], capture_output=True, text=True, encoding='utf-8', timeout=120,
                           env={**os.environ, 'DATABASE_PATH': str(self.base), 'PYTHONIOENCODING': 'utf-8'})
        self.assertEqual(r.returncode, 0, r.stderr)


class CodigoYDocumentacionTests(unittest.TestCase):
    def test_el_script_de_sqlite_usa_solo_la_biblioteca_estandar(self):
        arbol = ast.parse((RAIZ / 'scripts' / 'respaldo.py').read_text(encoding='utf-8'))
        modulos = {n.names[0].name.split('.')[0] for n in ast.walk(arbol) if isinstance(n, ast.Import)}
        modulos |= {n.module.split('.')[0] for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)}
        self.assertLessEqual(modulos, set(sys.stdlib_module_names))
        self.assertNotIn('app', modulos)

    def test_los_scripts_nunca_leen_ni_guardan_claves(self):
        for nombre in ('respaldo.py', 'respaldo_postgres.py'):
            codigo = (RAIZ / 'scripts' / nombre).read_text(encoding='utf-8')
            self.assertNotRegex(codigo, r"environ(\.get\(|\[)\s*['\"]SECRET_KEY")
            self.assertNotRegex(codigo, r"(password|passwd|clave)\s*=\s*['\"][^'\"]+['\"]")
        self.assertNotRegex((RAIZ / 'scripts' / 'respaldo_postgres.py').read_text(encoding='utf-8'), r'postgres(ql)?://(?!usuario:clave@)\w+:\w+@')

    def test_la_documentacion_cubre_lo_pedido(self):
        doc = (RAIZ / 'docs' / 'RECUPERACION.md').read_text(encoding='utf-8')
        for frase in ('cpstore_AAAAMMDD_HHMMSS', 'Cada cuánto copiar', 'otro disco', '.env', 'SECRET_KEY', 'nunca sobrescribe',
                      'SIN PROBAR', 'pg_dump', 'pg_restore', 'CPSTORE_PG_URL', 'integrity_check', 'instance/facturas', 'verificacion.json',
                      'Ley 1581', 'respaldo.py copiar', 'respaldo.py restaurar'):
            self.assertIn(frase, doc, frase)
        self.assertNotRegex(doc, r'postgres(ql)?://(?!usuario:clave@)\w+:\w+@')  # ni siquiera de ejemplo con clave


class PostgresSinProbarTests(unittest.TestCase):
    URL = 'postgresql://usuario_cp:cl%40ve%3Asecreta@db.ejemplo.com:5433/cpstore?sslmode=require'

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        self.soportes = self.raiz / 'facturas'
        self.soportes.mkdir()
        (self.soportes / 'a.pdf').write_bytes(b'%PDF-1.4 uno')
        (self.soportes / '.env').write_text('SECRET_KEY=x')
        self.llamadas = []

    def tearDown(self):
        self.tmp.cleanup()

    def falso(self, orden, env=None, capture_output=None, text=None, input=None, check=None):
        self.llamadas.append({'orden': list(orden), 'env': dict(env or {}), 'input': input})
        herramienta = orden[0]
        salida = ''
        if herramienta == 'pg_dump':
            Path(orden[orden.index('--file') + 1]).write_bytes(b'PGDMP volcado de prueba')
        elif herramienta == 'psql':
            sql = input or ''
            if 'pg_tables' in sql:
                salida = 'equipment\nfinance_operation\nschema_version\n'
            elif 'COUNT(*) FROM "' in sql:
                salida = '3'
            elif 'FROM finance_operation' in sql:
                salida = '2,1500000'
            elif 'FROM equipment' in sql:
                salida = '3,700000'
            elif 'FROM schema_version' in sql:
                salida = '19\n'
            elif 'pg_database' in sql:
                salida = '1' if self.existe else ''
        return subprocess.CompletedProcess(orden, 0, salida, '')

    existe = False

    def con_url(self):
        return mock.patch.dict(os.environ, {rpg.VARIABLE_POR_DEFECTO: self.URL})

    def test_lee_la_url_de_la_variable_y_la_reparte_en_variables_pg(self):
        with self.con_url():
            entorno, base = rpg.entorno_desde_url()
        self.assertEqual(base, 'cpstore')
        self.assertEqual((entorno['PGHOST'], entorno['PGPORT'], entorno['PGUSER'], entorno['PGPASSWORD'], entorno['PGSSLMODE']),
                         ('db.ejemplo.com', '5433', 'usuario_cp', 'cl@ve:secreta', 'require'))

    def test_sin_variable_o_con_formato_malo_da_error_claro(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(rpg.VARIABLE_POR_DEFECTO, None)
            with self.assertRaises(rp.ErrorRespaldo) as e:
                rpg.entorno_desde_url()
        self.assertIn(rpg.VARIABLE_POR_DEFECTO, str(e.exception))
        with mock.patch.dict(os.environ, {'OTRA': 'mysql://x'}):
            with self.assertRaises(rp.ErrorRespaldo):
                rpg.entorno_desde_url('OTRA')

    def test_acepta_otra_variable(self):
        with mock.patch.dict(os.environ, {'MI_URL': self.URL}):
            self.assertEqual(rpg.entorno_desde_url('MI_URL')[1], 'cpstore')

    def test_copiar_arma_pg_dump_sin_la_clave_ni_la_url_en_la_linea_de_ordenes(self):
        salida = []
        with self.con_url(), mock.patch.object(subprocess, 'run', side_effect=self.falso):
            r = rpg.copiar(self.soportes, self.raiz / 'copias', salida=salida.append)
        volcado = next(c for c in self.llamadas if c['orden'][0] == 'pg_dump')
        self.assertEqual(volcado['orden'][:4], ['pg_dump', '--format=custom', '--no-owner', '--no-privileges'])
        for llamada in self.llamadas:
            linea = ' '.join(llamada['orden']) + ' ' + (llamada['input'] or '')
            self.assertNotIn('cl@ve', linea)
            self.assertNotIn('secreta', linea)
            self.assertNotIn('postgresql://', linea)
            self.assertEqual(llamada['env']['PGPASSWORD'], 'cl@ve:secreta')  # la clave solo viaja en el entorno del proceso hijo
        textos = '\n'.join(salida) + json.dumps(r['verificacion'])
        self.assertNotIn('secreta', textos)
        self.assertNotIn('postgresql://', textos)

    def test_copiar_deja_verificacion_con_marca_sin_probar_y_sin_secretos(self):
        with self.con_url(), mock.patch.object(subprocess, 'run', side_effect=self.falso):
            r = rpg.copiar(self.soportes, self.raiz / 'copias', salida=lambda *_: None)
        v = r['verificacion']
        self.assertTrue(v['sin_probar'])
        self.assertEqual(v['motor'], 'postgresql')
        self.assertEqual(v['control']['ventas_netas'], {'operaciones': 2, 'total_cents': 1500000})
        self.assertEqual(v['control']['inventario_disponible'], {'equipos': 3, 'costo_cents': 700000})
        self.assertEqual(v['version_esquema']['version'], 19)
        self.assertEqual([s['archivo'] for s in v['soportes']], ['a.pdf'])
        self.assertEqual(v['excluidos'], ['.env'])
        self.assertEqual(sorted(p.name for p in r['copia'].iterdir()), ['base.dump', 'soportes', 'verificacion.json'])

    def test_copiar_siempre_muestra_el_aviso_sin_probar(self):
        salida = []
        with self.con_url(), mock.patch.object(subprocess, 'run', side_effect=self.falso):
            rpg.copiar(self.soportes, self.raiz / 'copias', salida=salida.append)
        self.assertIn('SIN PROBAR', salida[0])
        self.assertIn('SIN PROBAR', rpg.__doc__)
        self.assertIn('SIN PROBAR', rpg.AVISO_SIN_PROBAR)

    def test_si_falta_una_herramienta_el_error_es_claro_y_no_queda_nada(self):
        with self.con_url(), mock.patch.object(subprocess, 'run', side_effect=FileNotFoundError):
            with self.assertRaises(rp.ErrorRespaldo) as e:
                rpg.copiar(self.soportes, self.raiz / 'copias', salida=lambda *_: None)
        self.assertIn('No se encontró pg_dump', str(e.exception))
        self.assertEqual(list((self.raiz / 'copias').iterdir()), [])

    def test_si_pg_dump_falla_no_queda_nada_a_medias(self):
        def malo(orden, **kw):
            return subprocess.CompletedProcess(orden, 1, '', 'pg_dump: error: connection refused')
        with self.con_url(), mock.patch.object(subprocess, 'run', side_effect=malo):
            with self.assertRaises(rp.ErrorRespaldo) as e:
                rpg.copiar(self.soportes, self.raiz / 'copias', salida=lambda *_: None)
        self.assertIn('connection refused', str(e.exception))
        self.assertEqual(list((self.raiz / 'copias').iterdir()), [])

    def copia_hecha(self):
        with self.con_url(), mock.patch.object(subprocess, 'run', side_effect=self.falso):
            copia = rpg.copiar(self.soportes, self.raiz / 'copias', salida=lambda *_: None)['copia']
        self.llamadas.clear()
        return copia

    def test_restaurar_crea_una_base_nueva_y_nunca_toca_la_actual(self):
        copia = self.copia_hecha()
        with self.con_url(), mock.patch.object(subprocess, 'run', side_effect=self.falso):
            r = rpg.restaurar(copia, 'cpstore_prueba', self.raiz / 'soportes_prueba', salida=lambda *_: None)
        ordenes = [c['orden'][0] for c in self.llamadas]
        self.assertIn('createdb', ordenes)
        self.assertNotIn('dropdb', ordenes)
        restore = next(c for c in self.llamadas if c['orden'][0] == 'pg_restore' and '--dbname' in c['orden'])
        self.assertEqual(restore['orden'][restore['orden'].index('--dbname') + 1], 'cpstore_prueba')
        self.assertTrue(all(p['ok'] for p in r['pruebas']))
        self.assertTrue((self.raiz / 'soportes_prueba' / 'a.pdf').is_file())
        self.assertEqual(restore['env']['PGDATABASE'], 'cpstore_prueba')  # la base real (cpstore) no se toca

    def test_restaurar_se_niega_si_la_base_ya_existe(self):
        copia = self.copia_hecha()
        self.existe = True
        with self.con_url(), mock.patch.object(subprocess, 'run', side_effect=self.falso):
            with self.assertRaises(rp.ErrorRespaldo) as e:
                rpg.restaurar(copia, 'cpstore_prueba', self.raiz / 'soportes_prueba', salida=lambda *_: None)
        self.assertIn('Ya existe una base llamada cpstore_prueba', str(e.exception))
        self.assertNotIn('createdb', [c['orden'][0] for c in self.llamadas])
        self.assertFalse((self.raiz / 'soportes_prueba').exists())

    def test_restaurar_se_niega_con_la_base_actual_nombres_raros_o_soportes_existentes(self):
        copia = self.copia_hecha()
        with self.con_url(), mock.patch.object(subprocess, 'run', side_effect=self.falso):
            for nombre in ('cpstore', 'x; DROP DATABASE cpstore', '1base', '', 'a' * 64):
                with self.subTest(nombre=nombre), self.assertRaises(rp.ErrorRespaldo):
                    rpg.restaurar(copia, nombre, self.raiz / 'soportes_prueba', salida=lambda *_: None)
            (self.raiz / 'ya_existe').mkdir()
            with self.assertRaises(rp.ErrorRespaldo) as e:
                rpg.restaurar(copia, 'cpstore_prueba', self.raiz / 'ya_existe', salida=lambda *_: None)
        self.assertIn('ya existe', str(e.exception))
        self.assertNotIn('createdb', [c['orden'][0] for c in self.llamadas])

    def test_restaurar_con_copia_danada_se_corta_antes_de_crear_nada(self):
        copia = self.copia_hecha()
        (copia / 'base.dump').write_bytes(b'alterado')
        with self.con_url(), mock.patch.object(subprocess, 'run', side_effect=self.falso):
            with self.assertRaises(rp.ErrorRespaldo) as e:
                rpg.restaurar(copia, 'cpstore_prueba', self.raiz / 'soportes_prueba', salida=lambda *_: None)
        self.assertEqual(e.exception.codigo, 3)
        self.assertNotIn('createdb', [c['orden'][0] for c in self.llamadas])

    def test_si_la_restauracion_falla_se_borra_la_base_creada_y_los_soportes_temporales(self):
        copia = self.copia_hecha()

        def falla_al_restaurar(orden, **kw):
            if orden[0] == 'pg_restore' and '--dbname' in orden:
                self.llamadas.append({'orden': list(orden), 'env': kw.get('env'), 'input': None})
                return subprocess.CompletedProcess(orden, 1, '', 'pg_restore: error: out of memory')
            return self.falso(orden, **kw)
        with self.con_url(), mock.patch.object(subprocess, 'run', side_effect=falla_al_restaurar):
            with self.assertRaises(rp.ErrorRespaldo):
                rpg.restaurar(copia, 'cpstore_prueba', self.raiz / 'soportes_prueba', salida=lambda *_: None)
        self.assertIn('dropdb', [c['orden'][0] for c in self.llamadas])
        self.assertFalse((self.raiz / 'soportes_prueba').exists())
        self.assertEqual([p.name for p in self.raiz.iterdir() if p.name.startswith('.restaurando_')], [])

    def test_por_consola_sin_variable_da_error_claro(self):
        env = {k: v for k, v in os.environ.items() if k != rpg.VARIABLE_POR_DEFECTO}
        r = subprocess.run([sys.executable, str(RAIZ / 'scripts' / 'respaldo_postgres.py'), 'copiar', '--destino', str(self.raiz / 'c')],
                           capture_output=True, text=True, encoding='utf-8', env={**env, 'PYTHONIOENCODING': 'utf-8'}, timeout=60)
        self.assertEqual(r.returncode, 2)
        self.assertIn('SIN PROBAR', r.stdout)
        self.assertIn(rpg.VARIABLE_POR_DEFECTO, r.stderr)
        self.assertFalse((self.raiz / 'c').exists())


if __name__ == '__main__':
    unittest.main()
