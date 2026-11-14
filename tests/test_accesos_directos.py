"""Accesos directos: rutas con ID, exportaciones, facturas adjuntas, reportes y chat con cada rol; errores 500 y tiempos de acceso."""
import itertools
import os
import re
import statistics
import time
import unittest
from pathlib import Path
from unittest import mock

from werkzeug.datastructures import MultiDict
from werkzeug.security import check_password_hash, generate_password_hash

import app.auth as auth
from test_chat_pantalla import PantallaBase
from test_matriz_permisos import FILAS, ROLES
from test_consulta_resumen_ventas import VentasBase, dias_atras
from app.extensions import db
from app.models import Catalogo, Producto
from app.models.gestion import AliadoCredito, CreditoVenta, FacturaLote, RegistroGestion, Usuario
from app.services import compras_service

SIN_SESION = 'anónimo'
FACTURA = b'%PDF-1.4 contenido de la factura que solo debe ver quien tiene permiso ' + b'z' * 300
PERMITEN_FACTURA = ('Propietario', 'Administrador', 'Inventario')
NO_PERMITEN_FACTURA = ('Vendedora', 'Socio')


class AccesosBase(PantallaBase):
    """Base con ventas, un lote con dos facturas reales en una carpeta temporal y todos los perfiles."""

    def setUp(self):
        super().setUp()
        self.raiz = Path(self.tmp.name)
        self.app.instance_path = str(self.raiz)  # las facturas se sirven desde <instance_path>/facturas: aquí, una carpeta temporal
        self.carpeta = self.raiz / 'facturas'
        self.carpeta.mkdir()
        self.vender(monto='650000')
        self.vender(monto='1200000', con_equipo=False)
        proveedor = db.session.scalar(db.select(Catalogo).where(Catalogo.kind == 'supplier', Catalogo.active == 1))
        self.lote = compras_service.create(MultiDict({'supplier_id': str(proveedor.id), 'currency': 'COP', 'expected_count': '1',
                                                      'entry_date': '2026-01-15'}))
        db.session.flush()
        self.nombre = 'ab' * 24 + '.pdf'
        (self.carpeta / self.nombre).write_bytes(FACTURA)
        self.fila = FacturaLote(lote_id=self.lote.id, nombre='factura.pdf', archivo=self.nombre, mime='application/pdf', sha256='0' * 64)
        db.session.add(self.fila)
        db.session.commit()
        self.fila_id, self.lote_id = self.fila.id, self.lote.id
        self.clientes = {rol: self.cliente(rol, **({'socio_id': None} if rol == 'Socio' else {})) for rol in
                         ('Propietario', 'Administrador', 'Vendedora', 'Inventario', 'Socio')}
        self.clientes[SIN_SESION] = self.app.test_client()

    def ids(self):
        d = db.session.scalar(db.select(Producto.id).where(Producto.status == 'Disponible'))
        v = db.session.scalar(db.select(Producto.id).where(Producto.status == 'Vendido'))
        return {'d': d or 1, 'v': v or 1, 'l': self.lote_id, 'f': self.fila_id}


class FacturasTests(AccesosBase):
    def get(self, rol, ruta=None):
        r = self.clientes[rol].get(ruta or f'/inventario/facturas/{self.fila_id}')
        r.get_data()  # lee y cierra el archivo; los datos siguen disponibles en r.data
        r.close()
        return r

    def test_quien_tiene_permiso_recibe_el_archivo_exacto_como_descarga(self):
        for rol in PERMITEN_FACTURA:
            with self.subTest(rol=rol):
                r = self.get(rol)
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.data, FACTURA)
                self.assertEqual(r.mimetype, 'application/pdf')
                self.assertTrue(r.headers['Content-Disposition'].startswith('attachment'))  # nunca se abre dentro de la página
                self.assertEqual(r.headers['X-Content-Type-Options'], 'nosniff')
                self.assertEqual(r.headers['Cache-Control'], 'private, no-store')
                r.close()

    def test_los_demas_perfiles_y_los_anonimos_no_reciben_ni_un_byte(self):
        for rol in NO_PERMITEN_FACTURA + (SIN_SESION,):
            with self.subTest(rol=rol):
                r = self.get(rol)
                self.assertIn(r.status_code, (302, 403))
                self.assertNotIn(b'solo debe ver quien tiene permiso', r.data)
                self.assertNotIn(b'%PDF', r.data)

    def test_con_permiso_y_sin_la_factura_es_404_no_500(self):
        for rol in PERMITEN_FACTURA:
            for ident in (999999, 0, self.fila_id + 100):
                self.assertEqual(self.get(rol, f'/inventario/facturas/{ident}').status_code, 404, (rol, ident))

    def test_no_hay_diferencia_visible_entre_factura_existente_e_inexistente_para_quien_no_puede(self):
        for rol in NO_PERMITEN_FACTURA + (SIN_SESION,):
            reales = self.get(rol).status_code
            falsas = self.get(rol, '/inventario/facturas/999999').status_code
            self.assertEqual(reales, falsas, rol)

    def test_el_nombre_en_la_url_no_permite_salir_de_la_carpeta(self):
        fuera = self.raiz / 'secreto_fuera.pdf'
        fuera.write_bytes(b'%PDF-1.4 SECRETO FUERA DE LA CARPETA')
        (self.raiz / 'db.txt').write_text('SECRETO DE LA RAIZ')
        trucos = ('/inventario/facturas/../secreto_fuera.pdf', '/inventario/facturas/..%2fsecreto_fuera.pdf',
                  '/inventario/facturas/%2e%2e%2fsecreto_fuera.pdf', '/inventario/facturas/..\\secreto_fuera.pdf',
                  '/inventario/facturas/abc', '/inventario/facturas/1.pdf', '/inventario/facturas/1/../../db.txt',
                  '/inventario/facturas/%00', '/inventario/facturas/-1', f'/inventario/facturas/{self.fila_id}%2f..%2f..%2fdb.txt',
                  '/inventario/facturas/' + 'a' * 5000, '/static/../secreto_fuera.pdf', '/static/..%2fsecreto_fuera.pdf',
                  '/static/%2e%2e/%2e%2e/db.txt', '/static/../../instance/cpstore.sqlite')
        for ruta in trucos:
            r = self.get('Propietario', ruta)
            self.assertIn(r.status_code, (400, 404, 308, 301), (ruta, r.status_code))
            self.assertNotIn(b'SECRETO', r.data, ruta)
            self.assertNotIn(b'%PDF-1.4', r.data, ruta)

    def test_el_id_es_numerico_y_el_archivo_sale_de_la_base_no_de_la_url(self):
        regla = [r for r in self.app.url_map.iter_rules() if r.endpoint == 'gestion.factura'][0]
        self.assertEqual(regla.rule, '/inventario/facturas/<int:invoice_id>')

    def test_un_nombre_raro_guardado_en_la_base_tampoco_sale_de_la_carpeta(self):
        fuera = self.raiz / 'secreto_fuera.pdf'
        fuera.write_bytes(b'%PDF-1.4 SECRETO FUERA DE LA CARPETA')
        peligrosos = ('../secreto_fuera.pdf', '..\\secreto_fuera.pdf', str(fuera), str(fuera).replace('\\', '/'), 'sub/' + self.nombre,
                      '/etc/passwd', 'C:\\Windows\\win.ini', self.nombre.upper(), self.nombre[:-4] + '.exe', self.nombre[:-4], 'x' * 48 + '.pdf',
                      self.nombre + '.pdf', '', '.' + self.nombre)
        for archivo in peligrosos:
            self.fila.archivo = archivo
            db.session.commit()
            for rol in PERMITEN_FACTURA:
                r = self.get(rol)
                self.assertEqual(r.status_code, 404, (archivo, rol))
                self.assertNotIn(b'SECRETO', r.data)
                self.assertNotIn(b'%PDF', r.data)

    def test_un_enlace_simbolico_que_apunta_afuera_no_se_sirve(self):
        fuera = self.raiz / 'secreto_fuera.pdf'
        fuera.write_bytes(b'%PDF-1.4 SECRETO FUERA DE LA CARPETA')
        enlace = self.carpeta / ('cd' * 24 + '.pdf')
        try:
            os.symlink(fuera, enlace)
        except (OSError, NotImplementedError):
            self.skipTest('este equipo no permite crear enlaces simbólicos')
        self.fila.archivo = enlace.name
        db.session.commit()
        r = self.get('Propietario')
        self.assertEqual(r.status_code, 404)
        self.assertNotIn(b'SECRETO', r.data)

    def test_archivo_ausente_en_disco_es_404(self):
        (self.carpeta / self.nombre).unlink()
        self.assertEqual(self.get('Propietario').status_code, 404)

    def test_la_carpeta_de_facturas_no_se_sirve_por_el_estatico(self):
        for ruta in (f'/static/facturas/{self.nombre}', f'/facturas/{self.nombre}', f'/instance/facturas/{self.nombre}'):
            r = self.get('Propietario', ruta)
            self.assertEqual(r.status_code, 404, ruta)
            self.assertNotIn(b'%PDF', r.data)

    def test_el_nombre_que_ve_quien_descarga_viene_saneado(self):
        self.fila.nombre = '../../etc/passwd.pdf'
        db.session.commit()
        r = self.get('Propietario')
        nombre = r.headers['Content-Disposition'].split('filename=')[-1]
        self.assertNotIn('/', nombre)
        self.assertNotIn('..', nombre)
        self.assertIn('etc_passwd.pdf', nombre)


class RutasConIdTests(AccesosBase):
    CANDIDATOS = ('{real}', '999999', '0')

    def rutas_con_id(self):
        """Todas las rutas GET con un ID en la ruta, tomadas de la tabla de URLs de la aplicación."""
        return [r for r in self.app.url_map.iter_rules() if 'GET' in r.methods and re.search(r'<(int:)?\w+>', r.rule)
                and r.endpoint not in ('static', 'main.module')]

    def llenar(self, regla, valor):
        return re.sub(r'<(?:int:)?\w+>', str(valor), regla.rule)

    def test_ninguna_ruta_con_id_da_500_con_ningun_perfil(self):
        ids = self.ids()
        fallos = []
        for regla in self.rutas_con_id():
            for valor in (ids['d'], ids['v'], ids['l'], ids['f'], 999999, 0):
                ruta = self.llenar(regla, valor)
                for rol, cliente in self.clientes.items():
                    r = cliente.get(ruta)
                    estado = r.status_code
                    r.close()
                    if estado >= 500:
                        fallos.append((rol, ruta, estado))
        self.assertEqual(fallos, [])

    def test_quien_no_puede_ver_una_ruta_recibe_lo_mismo_exista_o_no_el_recurso(self):
        """Sin pistas: un 403 (o la redirección del Socio) es idéntico para un ID real y para uno inventado."""
        ids = self.ids()
        con_ids = [(m, r, f, e) for m, r, f, e in FILAS if m == 'GET' and '{' in r]
        self.assertGreaterEqual(len(con_ids), 5)
        for metodo, ruta, form, esperado in con_ids:
            for letra, rol in ROLES.items():
                if letra in esperado:
                    continue
                real = self.clientes[rol].get(ruta.format(**ids)).status_code
                falso = self.clientes[rol].get(ruta.format(d=999999, v=999999, l=999999, f=999999)).status_code
                self.assertEqual(real, falso, (ruta, rol))
                self.assertIn(real, (302, 403), (ruta, rol))

    def test_con_permiso_un_id_inexistente_es_404_o_redireccion_nunca_500(self):
        for ruta in ('/inventario/999999', '/ventas/999999', '/ventas/recepciones/999999', '/inventario/compras/999999',
                     '/inventario/facturas/999999'):
            for rol in ('Propietario', 'Administrador'):
                self.assertIn(self.clientes[rol].get(ruta).status_code, (404, 302), (rol, ruta))

    def test_post_a_un_lote_inexistente_tampoco_da_500(self):
        c = self.clientes['Propietario']
        for accion in ('add', 'confirm', 'remove', 'invoice', 'zzz'):
            r = c.post('/inventario/compras/999999', data={'csrf': 'test', 'action': accion})
            self.assertEqual(r.status_code, 404, accion)

    def test_los_ids_de_otros_modulos_no_se_cruzan(self):
        ids = self.ids()
        r = self.clientes['Propietario'].get(f"/ventas/{ids['l'] + 5000}")
        self.assertEqual(r.status_code, 404)


class DescargasYExportacionesTests(AccesosBase):
    """Cada descarga existente: el perfil permitido recibe el archivo; los demás, nada."""
    DESCARGAS = (
        ('/finanzas/exportar?date={hoy}', 'text/csv', b'\xef\xbb\xbfFECHA;TIPO', ('Propietario', 'Administrador')),
        ('/modulos/tributario/export.csv?ini={ini}&fin={hoy}', 'text/csv', b'\xef\xbb\xbfCP STORE', ('Propietario', 'Administrador')),
        ('/modulos/tributario/paquete.xlsx?ini={ini}&fin={hoy}', None, b'PK', ('Propietario', 'Administrador')),
        ('/modulos/tributario/paquete.pdf?ini={ini}&fin={hoy}', 'application/pdf', b'%PDF', ('Propietario', 'Administrador')),
        ('/inventario/compras/plantilla.xlsx', None, b'PK', ('Propietario', 'Administrador', 'Inventario')),
        ('/inventario/facturas/{f}', 'application/pdf', b'%PDF', PERMITEN_FACTURA),
        ('/reportes/ventas?periodo=semana&formato=csv', 'text/csv', b'\xef\xbb\xbfReporte;', ('Propietario',)),
        ('/reportes/finanzas?periodo=mes&formato=csv', 'text/csv', b'\xef\xbb\xbfReporte;', ('Propietario',)),
        ('/reportes/inventario?formato=csv', 'text/csv', b'\xef\xbb\xbfReporte;', ('Propietario',)),
    )

    def llamar(self, plantilla, rol):
        ruta = plantilla.format(hoy=self.hoy, ini=dias_atras(3), f=self.fila_id)
        return self.clientes[rol].get(ruta)

    def test_el_perfil_permitido_descarga_y_los_demas_no_reciben_el_archivo(self):
        for plantilla, tipo, inicio, permitidos in self.DESCARGAS:
            for rol in self.clientes:
                with self.subTest(ruta=plantilla, rol=rol):
                    r = self.llamar(plantilla, rol)
                    if rol in permitidos:
                        self.assertEqual(r.status_code, 200)
                        self.assertTrue(r.data.startswith(inicio), r.data[:20])
                        if tipo:
                            self.assertEqual(r.mimetype, tipo)
                    else:
                        self.assertIn(r.status_code, (302, 403))
                        self.assertFalse(r.data.startswith(inicio))
                        self.assertNotIn(b'FECHA;TIPO', r.data)
                        self.assertNotIn(b'1.200.000', r.data)
                    r.close()

    def test_head_nunca_entrega_el_contenido_a_quien_no_tiene_permiso(self):
        for plantilla, _, _, permitidos in self.DESCARGAS:
            for rol in self.clientes:
                if rol in permitidos:
                    continue
                ruta = plantilla.format(hoy=self.hoy, ini=dias_atras(3), f=self.fila_id)
                r = self.clientes[rol].head(ruta)
                self.assertNotEqual(r.status_code, 200, (ruta, rol))

    def test_las_exportaciones_con_parametros_malos_dan_400_no_500(self):
        c = self.clientes['Propietario']
        for ruta, esperado in (('/finanzas/exportar', 400), ('/finanzas/exportar?date=x', 400), ('/finanzas/exportar?date=2999-01-01', 400),
                               ('/finanzas/exportar?date=2000-01-01', 404), ('/gestion/historial?id=abc', 400), ('/gestion/historial?id=1', 200),
                               ('/modulos/tributario/export.csv?ini=x&fin=y', 302), ('/modulos/tributario/paquete.xlsx?ini=2026-02-01&fin=2026-01-01', 302)):
            self.assertEqual(c.get(ruta).status_code, esperado, ruta)

    def test_las_descargas_sensibles_no_se_guardan_en_cache(self):
        for plantilla in ('/modulos/tributario/paquete.xlsx?ini={ini}&fin={hoy}', '/reportes/ventas?periodo=mes&formato=csv',
                          '/inventario/facturas/{f}'):
            r = self.llamar(plantilla, 'Propietario')
            self.assertIn('no-store', r.headers['Cache-Control'], plantilla)
            r.close()


class ChatYReportesPorPerfilTests(AccesosBase):
    def test_solo_el_propietario_usa_el_chat_y_los_reportes(self):
        rutas = (('GET', '/chat'), ('POST', '/chat/consultar'), ('GET', '/reportes/ventas'), ('GET', '/reportes/finanzas'),
                 ('GET', '/reportes/inventario'), ('GET', '/reportes/ventas?formato=csv'))
        for metodo, ruta in rutas:
            for rol, cliente in self.clientes.items():
                with self.subTest(ruta=ruta, rol=rol):
                    if metodo == 'GET':
                        r = cliente.get(ruta)
                    else:
                        with cliente.session_transaction() as s:
                            s.setdefault('csrf', 'test')
                            token = s['csrf']
                        r = cliente.post(ruta, data={'csrf': token, 'pregunta': 'ventas de hoy'})
                    if rol == 'Propietario':
                        self.assertEqual(r.status_code, 200)
                    else:
                        self.assertIn(r.status_code, (302, 400, 403))
                        self.assertNotIn(b'1.200.000', r.data)
                        self.assertNotIn(b'Fuente:', r.data)

    def test_ni_siquiera_con_una_consulta_habilitada_se_filtran_las_otras(self):
        from app.services import consultas_service as cs
        with mock.patch.dict(cs.ROLES_CONSULTAS, {'resumen_ventas': ('Propietario', 'Vendedora')}):
            c = self.clientes['Vendedora']
            with c.session_transaction() as s:
                token = s['csrf']
            otras = [c.post('/chat/consultar', data={'csrf': token, 'pregunta': p}).get_json() for p in
                     ('resultado de hoy', 'inventario disponible', 'créditos pendientes')]
            self.assertTrue(all(o['estado'] == 'sin_autorizacion' for o in otras))
            self.assertNotIn('$', ' '.join(o['respuesta'] for o in otras))
            propia = c.post('/chat/consultar', data={'csrf': token, 'pregunta': 'ventas de hoy'}).get_json()
            self.assertIn('$1.200.000', propia['respuesta'])


class ErroresSinTrazaTests(AccesosBase):
    QUERIES = ('', '?date=x', '?date=2999-01-01', '?ini=x&fin=y', '?id=abc', '?q=%00', '?start=x&end=y', '?anio=zz', '?detalle_bancos=abc',
               '?kind=zzz', '?periodo=x&formato=zzz', '?tab=zzz')

    def test_ninguna_ruta_get_da_500_con_parametros_raros(self):
        c = self.clientes['Propietario']
        fallos = []
        for regla in self.app.url_map.iter_rules():
            if 'GET' not in regla.methods or regla.endpoint == 'static' or re.search(r'<', regla.rule):
                continue
            for q in self.QUERIES:
                estado = c.get(regla.rule + q).status_code
                if estado >= 500:
                    fallos.append((regla.rule + q, estado))
        self.assertEqual(fallos, [])

    def test_ninguna_ruta_post_da_500_con_formularios_basura(self):
        c = self.clientes['Propietario']
        basura = (dict(), dict(action='zzz'), dict(id='abc', action='x'), dict(action='sell', sale_value='x', revision='x'),
                  dict(date='x', action='open'), dict(amount='x', kind='Venta', action='operation'),
                  dict(role='Socio', password='x', login='x', id='abc'), dict(pregunta='x' * 400), dict(pregunta=''))
        fallos = []
        for regla in self.app.url_map.iter_rules():
            if 'POST' not in regla.methods or regla.endpoint in ('static', 'auth.logout', 'auth.login'):
                continue
            ruta = re.sub(r'<(?:int:)?\w+>', '1', regla.rule)
            for datos in basura:
                estado = c.post(ruta, data={'csrf': 'test', **datos}).status_code
                if estado >= 500:
                    fallos.append((ruta, tuple(datos), estado))
        self.assertEqual(fallos, [])

    def test_los_errores_no_muestran_trazas_ni_rutas_del_servidor(self):
        c = self.clientes['Propietario']
        for ruta in ('/finanzas/exportar', '/gestion/historial?id=abc', '/inventario/compras/999999', '/inventario/facturas/999999'):
            cuerpo = c.get(ruta).get_data(as_text=True)
            for pista in ('Traceback', 'File "', 'sqlalchemy', 'sqlite3', 'instance_path', str(self.raiz)):
                self.assertNotIn(pista, cuerpo, (ruta, pista))


class TiempoDeAccesoTests(VentasBase):
    """Pendiente 9: el tiempo de respuesta no debe delatar qué usuarios existen."""
    CLAVE = 'zorro_Luna_cobre_77_tinta'

    def setUp(self):
        super().setUp()
        self.app.config['AUTH_REQUIRED'] = True
        auth._attempts.clear()
        auth._attempts_ip.clear()
        auth._ficticio.clear()
        db.session.add_all([Usuario(nombre='ANA', login='ana', rol='Vendedora', password_hash=generate_password_hash(self.CLAVE)),
                            Usuario(nombre='OFF', login='off', rol='Vendedora', password_hash=generate_password_hash(self.CLAVE), activo=False)])
        db.session.commit()
        self.n = 0

    def tearDown(self):
        auth._attempts.clear()
        auth._attempts_ip.clear()
        super().tearDown()

    def intento(self, login, clave):
        self.n += 1
        c = self.app.test_client()
        c.get('/iniciar-sesion')
        with c.session_transaction() as s:
            csrf = s['csrf']
        return c.post('/iniciar-sesion', data={'csrf': csrf, 'login': login, 'password': clave}, environ_overrides={'REMOTE_ADDR': f'10.1.{self.n // 250}.{self.n % 250}'})

    CASOS = (('ana', 'clave-mala', False), ('ana', 'zorro_Luna_cobre_77_tinta', True), ('nadie', 'clave-mala', False), ('nadie', 'zorro_Luna_cobre_77_tinta', False),
             ('off', 'clave-mala', False), ('off', 'zorro_Luna_cobre_77_tinta', False), ('', '', False))

    def test_siempre_se_calcula_exactamente_un_hash(self):
        for login, clave, entra in self.CASOS:
            with self.subTest(login=login, clave=clave):
                with mock.patch.object(auth, 'check_password_hash', wraps=check_password_hash) as espia:
                    r = self.intento(login, clave)
                self.assertEqual(espia.call_count, 1)
                self.assertEqual(r.status_code, 302 if entra else 200)

    def test_para_un_usuario_inexistente_se_usa_un_hash_ficticio_del_mismo_metodo(self):
        with mock.patch.object(auth, 'check_password_hash', wraps=check_password_hash) as espia:
            self.intento('nadie', 'x')
            self.intento('ana', 'x')
        ficticio, real = espia.call_args_list[0].args[0], espia.call_args_list[1].args[0]
        self.assertEqual(ficticio.split('$')[0], real.split('$')[0])  # mismo método y mismo costo (p. ej. scrypt:32768:8:1)
        self.assertNotEqual(ficticio, real)
        self.assertEqual(len(ficticio), len(real))

    def test_el_hash_ficticio_se_crea_una_sola_vez_y_no_depende_del_usuario(self):
        with mock.patch.object(auth, 'generate_password_hash', wraps=generate_password_hash) as espia:
            for login in ('a', 'b', 'c', 'd'):
                self.intento(login, 'x')
        self.assertEqual(espia.call_count, 1)

    def test_la_respuesta_es_identica_exista_o_no_el_usuario(self):
        textos = set()
        for login, clave in (('ana', 'mala'), ('nadie', 'mala'), ('off', 'mala'), ('off', self.CLAVE), ('nadie', self.CLAVE)):
            html = self.intento(login, clave).get_data(as_text=True)
            textos.add(re.search(r'Usuario o contraseña incorrectos\.', html).group(0))
        self.assertEqual(textos, {'Usuario o contraseña incorrectos.'})

    def test_un_usuario_inactivo_con_la_clave_correcta_no_entra(self):
        self.assertEqual(self.intento('off', self.CLAVE).status_code, 200)
        self.assertEqual(self.intento('ana', self.CLAVE).status_code, 302)

    def test_el_tiempo_no_delata_al_usuario_inexistente(self):
        def mediana(login, clave):
            tiempos = []
            for _ in range(5):
                t0 = time.perf_counter()
                self.intento(login, clave)
                tiempos.append(time.perf_counter() - t0)
            return statistics.median(tiempos)
        existente, inexistente, inactivo = mediana('ana', 'mala'), mediana('nadie', 'mala'), mediana('off', 'mala')
        # Antes de la corrección el usuario inexistente respondía varias veces más rápido; ahora hacen el mismo trabajo.
        self.assertGreater(inexistente, existente * 0.4, (existente, inexistente))
        self.assertGreater(inactivo, existente * 0.4, (existente, inactivo))
        self.assertLess(inexistente, existente * 2.5, (existente, inexistente))

    def test_el_registro_de_auditoria_sigue_distinguiendo_los_motivos(self):
        self.intento('nadie', 'x')
        self.intento('ana', 'x')
        self.intento('off', 'x')
        motivos = [r.motivo for r in db.session.scalars(db.select(RegistroGestion).where(RegistroGestion.accion == 'Inicio de sesión fallido').order_by(RegistroGestion.id))]
        self.assertEqual(motivos, ['Usuario inexistente', 'Contraseña incorrecta', 'Usuario inactivo'])


class CreditosSoloParaAdministracionTests(AccesosBase):
    """Pendiente 7: la lista de créditos (comisiones y montos de todas las ventas) la leen solo Propietario y Administrador."""

    def credito(self):
        persona, banco = self.persona_banco()
        aliado = db.session.scalar(db.select(AliadoCredito).where(AliadoCredito.nombre == 'SU+PAY'))
        aliado.porcentaje_bp, aliado.persona_id, aliado.banco_id = 1800, persona.id, banco.id
        db.session.commit()
        return persona, banco, aliado

    def venta_a_credito(self, persona, banco, aliado, token, descripcion='VENTA A CREDITO'):
        return MultiDict([('kind', 'Venta'), ('description', descripcion), ('seller', 'ANA'), ('token', token), ('amount', '650000'),
                          ('minor_cost', ''), ('payment_account', 'CRÉDITO'), ('payment_amount', '650000'),
                          ('payment_ally_id', str(aliado.id)), ('payment_person_id', str(persona.id)), ('payment_bank_id', str(banco.id)),
                          ('credit_approved', '1'), ('payment_credit_mode', 'Porcentaje'), ('payment_credit_rate', '18')])

    def test_leer_y_escribir_en_la_pantalla_de_creditos_es_solo_de_administracion(self):
        for rol in ('Propietario', 'Administrador'):
            self.assertEqual(self.clientes[rol].get('/finanzas/creditos').status_code, 200, rol)
        for rol in ('Vendedora', 'Inventario'):
            self.assertEqual(self.clientes[rol].get('/finanzas/creditos').status_code, 403, rol)
            for accion in ('settle', 'ally', 'zzz'):
                r = self.clientes[rol].post('/finanzas/creditos', data={'csrf': 'test', 'action': accion})
                self.assertEqual(r.status_code, 403, (rol, accion))
        self.assertEqual(self.clientes['Socio'].get('/finanzas/creditos').status_code, 302)
        self.assertEqual(self.clientes[SIN_SESION].get('/finanzas/creditos').status_code, 302)

    def test_la_vendedora_no_recibe_ni_una_cifra_de_creditos(self):
        from app.services import finanzas_service
        persona, banco, aliado = self.credito()
        finanzas_service.add_operation(self.d, self.venta_a_credito(persona, banco, aliado, 'a' * 32, 'VENTA A CREDITO DE OTRA PERSONA'))
        db.session.commit()
        self.assertEqual(db.session.query(CreditoVenta).count(), 1)
        cuerpo = self.clientes['Vendedora'].get('/finanzas/creditos').get_data(as_text=True)
        for dato in ('533.000', '117.000', 'VENTA A CREDITO DE OTRA PERSONA', 'Comisión', 'SU+PAY'):
            self.assertNotIn(dato, cuerpo)
        self.assertIn('533.000', self.clientes['Administrador'].get('/finanzas/creditos').get_data(as_text=True))

    def test_el_enlace_del_menu_solo_lo_ven_quienes_pueden_abrirlo(self):
        for rol in ('Propietario', 'Administrador'):
            html = self.clientes[rol].get('/finanzas').get_data(as_text=True)
            self.assertIn('/finanzas/creditos', html, rol)
            self.assertIn('Créditos y desembolsos', html, rol)
        html = self.clientes['Vendedora'].get('/finanzas').get_data(as_text=True)
        self.assertNotIn('/finanzas/creditos', html)
        self.assertNotIn('Créditos y desembolsos', html)
        self.assertIn('Jornada', html)  # el resto del menú de la Vendedora sigue igual

    def test_la_vendedora_sigue_registrando_ventas_a_credito_desde_finanzas(self):
        persona, banco, aliado = self.credito()
        html = self.clientes['Vendedora'].get('/finanzas?accion=registrar').get_data(as_text=True)
        self.assertIn('SU+PAY', html)  # la lista de aliados llega al formulario de venta sin pasar por la pantalla de créditos
        datos = self.venta_a_credito(persona, banco, aliado, 'b' * 32)
        for clave, valor in (('csrf', 'test'), ('action', 'operation'), ('date', self.hoy), ('revision', str(self.d.revision))):
            datos.add(clave, valor)
        r = self.clientes['Vendedora'].post('/finanzas', data=datos)
        self.assertEqual(r.status_code, 302)
        db.session.expire_all()
        self.assertEqual(db.session.query(CreditoVenta).count(), 1)

    def test_el_chat_y_los_reportes_siguen_cerrados_para_la_vendedora(self):
        for ruta in ('/reportes/finanzas', '/chat'):
            self.assertEqual(self.clientes['Vendedora'].get(ruta).status_code, 403, ruta)


class DocumentacionTests(unittest.TestCase):
    def test_seguridad_marca_7_8_y_9_como_corregidos(self):
        doc = (Path(__file__).resolve().parent.parent / 'docs' / 'SEGURIDAD.md').read_text(encoding='utf-8')
        self.assertRegex(doc, r'7\.\s+\*\*Lectura de créditos[^\n]*CORREGIDO')
        self.assertRegex(doc, r'8\.\s+\*\*Errores 500[^\n]*CORREGIDO')
        self.assertRegex(doc, r'9\.\s+\*\*Enumeración de usuarios[^\n]*CORREGIDO')
        self.assertNotIn('PENDIENTE (a la espera de decisión)', doc)
        self.assertIn('Facturas adjuntas', doc)


if __name__ == '__main__':
    unittest.main()
