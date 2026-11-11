"""Matriz de rutas por rol: falla si una ruta cambia de permisos o si aparece una ruta sin clasificar.

Cada fila dice qué roles pueden usar una ruta (o una acción de escritura de esa ruta):
P = Propietario, A = Administrador, V = Vendedora, I = Inventario, S = Socio.
"Puede usar" significa que la petición supera los controles de permisos (no responde 403 ni, en el caso del Socio,
lo devuelve a su página). Los datos de las peticiones de escritura son inválidos a propósito: lo que se mide es
el permiso, no el resultado de negocio.
"""
import tempfile
import unittest
from pathlib import Path

from werkzeug.datastructures import MultiDict
from werkzeug.security import generate_password_hash

from _cleanup import release
from app import create_app
from app.extensions import db
from app.models import Catalogo, Producto
from app.models.gestion import Socio, Usuario
from app.services import compras_service

ROLES = {'P': 'Propietario', 'A': 'Administrador', 'V': 'Vendedora', 'I': 'Inventario', 'S': 'Socio'}
SIN_CLASIFICAR = 'rutas sin clasificar en la matriz de permisos'

# (método, ruta, formulario, roles que pueden usarla). {d} = equipo disponible, {v} = equipo vendido, {l} = lote.
FILAS = [
    # --- cualquiera con sesión (el Socio queda confinado a su página) ---
    ('GET', '/', {}, 'PAVI'),
    ('GET', '/modulos/analitica', {}, 'PAVI'),
    ('GET', '/modulos/ventas', {}, 'PAVI'),
    ('GET', '/modulos/finanzas', {}, 'PAVI'),
    ('GET', '/modulos/usuarios', {}, 'PAVI'),
    ('GET', '/modulos/tributario', {}, 'PA'),  # el guardia lo trata como Información contable
    ('GET', '/inventario', {}, 'PAVI'),
    ('GET', '/inventario/verificar-imei?imei=490154203237518', {}, 'PAVI'),
    ('GET', '/inventario/catalogos', {}, 'PAVI'),
    ('GET', '/ventas', {}, 'PAVI'),
    ('GET', '/ventas/{v}', {}, 'PAVI'),
    ('GET', '/inventario/{d}', {}, 'PAVI'),
    # --- inventario ---
    ('GET', '/inventario/nuevo', {}, 'PAI'),
    ('POST', '/inventario/nuevo', {}, 'PAI'),
    ('POST', '/inventario/{d}', {'action': 'edit'}, 'PAI'),
    ('POST', '/inventario/{d}', {'action': 'transfer'}, 'PAVI'),
    ('POST', '/inventario/catalogos', {}, 'PAI'),
    ('GET', '/inventario/proveedores', {}, 'PAI'),
    ('POST', '/inventario/proveedores', {}, 'PAI'),
    ('GET', '/inventario/alias', {}, 'PAI'),
    ('POST', '/inventario/alias', {}, 'PAI'),
    ('GET', '/inventario/compras', {}, 'PAI'),
    ('POST', '/inventario/compras', {}, 'PAI'),
    ('GET', '/inventario/compras/{l}', {}, 'PAI'),
    ('POST', '/inventario/compras/{l}', {'action': 'add'}, 'PAI'),
    ('POST', '/inventario/compras/{l}', {'action': 'confirm'}, 'PA'),
    ('POST', '/inventario/compras/{l}', {'action': 'reopen'}, 'PA'),
    ('GET', '/inventario/compras/plantilla.xlsx', {}, 'PAI'),
    ('GET', '/inventario/facturas/1', {}, 'PAI'),
    ('GET', '/inventario/articulos', {}, 'PAI'),
    ('POST', '/inventario/articulos', {'action': 'adjust'}, 'PA'),
    ('GET', '/inventario/lotes', {}, 'PAI'),
    ('GET', '/inventario/lotes/{l}', {}, 'PAI'),
    ('POST', '/inventario/lotes', {}, 'PAI'),
    # --- ventas ---
    ('POST', '/ventas/{d}', {'action': 'sell'}, 'PAV'),
    ('POST', '/ventas/{d}', {'action': 'reserve'}, 'PAV'),
    ('POST', '/ventas/{d}', {'action': 'payment'}, 'PAV'),
    ('POST', '/ventas/{v}', {'action': 'void_collection'}, 'PA'),
    ('POST', '/ventas/{v}', {'action': 'reverse_sale'}, 'PA'),
    ('POST', '/ventas/{v}', {'action': 'correct_date'}, 'PA'),
    ('GET', '/ventas/recepciones', {}, 'PA'),
    ('GET', '/ventas/recepciones/{v}', {}, 'PA'),
    ('POST', '/ventas/recepciones/{v}', {'action': 'receive'}, 'PA'),
    # --- finanzas ---
    ('GET', '/finanzas', {}, 'PAV'),
    ('GET', '/finanzas?tab=proveedores', {}, 'PAV'),
    ('POST', '/finanzas', {'action': 'open'}, 'PA'),
    ('POST', '/finanzas', {'action': 'operation', 'kind': 'Venta'}, 'PAV'),
    ('POST', '/finanzas', {'action': 'operation', 'kind': 'PD'}, 'PA'),
    ('POST', '/finanzas', {'action': 'config'}, 'PA'),
    ('GET', '/finanzas/exportar?date=2026-01-01', {}, 'PA'),
    ('GET', '/finanzas/creditos', {}, 'PAV'),
    ('POST', '/finanzas/creditos', {'action': 'settle'}, 'PA'),
    ('POST', '/finanzas/creditos', {'action': 'ally'}, 'PA'),
    ('GET', '/finanzas/pool', {}, 'PA'),
    ('POST', '/finanzas/pool', {'action': 'purchase'}, 'PA'),
    ('GET', '/gestion/historial', {}, 'PA'),
    # --- sociedades e inversión ---
    ('GET', '/ventas/sociedades', {}, 'PAS'),
    ('GET', '/finanzas/sociedades', {}, 'PAS'),
    ('POST', '/ventas/sociedades', {'action': 'liquidate'}, 'PA'),
    ('POST', '/ventas/sociedades', {'action': 'dissolve'}, 'PA'),
    ('POST', '/ventas/sociedades', {'action': 'ownership'}, 'PA'),
    ('POST', '/finanzas/sociedades', {'action': 'society'}, 'P'),
    ('POST', '/finanzas/sociedades', {'action': 'partner'}, 'P'),
    ('GET', '/inventario/inversion', {}, 'PAIS'),
    ('GET', '/ventas/inversion', {}, 'PAIS'),
    # --- chat (solo quien tenga habilitada alguna consulta en ROLES_CONSULTAS: hoy el Propietario) ---
    ('POST', '/chat/consultar', {'pregunta': 'ventas de hoy'}, 'P'),
    # --- usuarios ---
    ('GET', '/usuarios', {}, 'P'),
    ('POST', '/usuarios', {'role': 'Socio'}, 'P'),
    # --- información contable ---
    ('GET', '/modulos/tributario/', {}, 'PA'),
    ('GET', '/modulos/tributario/export.csv?ini=2026-01-01&fin=2026-01-31', {}, 'PA'),
    ('GET', '/modulos/tributario/paquete.xlsx?ini=2026-01-01&fin=2026-01-31', {}, 'PA'),
    ('GET', '/modulos/tributario/paquete.pdf?ini=2026-01-01&fin=2026-01-31', {}, 'PA'),
    ('GET', '/modulos/tributario/personas/verificar?identificacion=1', {}, 'PA'),
    ('POST', '/modulos/tributario/ingreso-gasto/nuevo', {}, 'PA'),
    ('POST', '/modulos/tributario/consignacion/nueva', {}, 'PA'),
    ('POST', '/modulos/tributario/consignacion/1/editar', {}, 'PA'),
    ('POST', '/modulos/tributario/clasificacion/1', {}, 'PA'),
    ('POST', '/modulos/tributario/crear-banco', {}, 'PA'),
    ('POST', '/modulos/tributario/crear-destinatario', {}, 'PA'),
    ('POST', '/modulos/tributario/persona/bancos', {}, 'PA'),
    ('POST', '/modulos/tributario/persona/1/bancos', {}, 'PA'),
    ('POST', '/modulos/tributario/persona/1/antecedente', {}, 'PA'),
]

# Rutas que no dependen del rol: son públicas por diseño o se rigen por la sesión misma.
PUBLICAS = {('auth.login', 'GET'), ('auth.login', 'POST'), ('auth.logout', 'POST'), ('static', 'GET')}
# Variantes que solo existen para las pruebas y en producción redirigen a las nuevas.
EQUIVALENTES_DE_PRUEBA = {'lotes.index', 'lotes.detail'}


class MatrizPermisos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.app = create_app({'TESTING': True, 'DATABASE': str(Path(cls.tmp.name) / 'db.sqlite'), 'SECRET_KEY': 'test',
                              'AUTH_REQUIRED': True, 'PROPAGATE_EXCEPTIONS': False})
        cls.addClassCleanup(cls._limpiar)
        cls.app.logger.disabled = True  # /inventario/facturas/<id> inexistente da 500 (pendiente 8); aquí solo se mide el permiso
        with cls.app.app_context():
            socio = Socio(nombre='SOCIO MATRIZ', activo=True)
            db.session.add(socio)
            for imei, estado in (('490154203237518', 'Disponible'), ('490154203237526', 'Vendido')):
                db.session.add(Producto(imei=imei, model='IPHONE MATRIZ', capacity=128, color='NEGRO', condition='Nuevo', cost_cents=100000000,
                                        additional_costs=[], source_type='Lote', location='LOCAL', supplier='CP CELULARES', status=estado,
                                        sale_value_cents=150000000 if estado == 'Vendido' else None))
            proveedor = db.session.scalar(db.select(Catalogo).where(Catalogo.kind == 'supplier', Catalogo.active == 1))
            lote = compras_service.create(MultiDict({'supplier_id': str(proveedor.id), 'currency': 'COP', 'expected_count': '1', 'entry_date': '2026-01-15'}))
            db.session.commit()  # el lote existe de verdad: el permiso se comprueba antes de buscar el recurso, no después
            cls.ids = {'d': db.session.scalar(db.select(Producto.id).where(Producto.status == 'Disponible')),
                       'v': db.session.scalar(db.select(Producto.id).where(Producto.status == 'Vendido')), 'l': lote.id}
            cls.sesiones = {}
            for letra, rol in ROLES.items():
                u = Usuario(nombre=rol, login=rol.lower(), rol=rol, password_hash=generate_password_hash('clave_prueba_123'),
                            socio_id=socio.id if rol == 'Socio' else None)
                db.session.add(u)
                db.session.commit()
                cls.sesiones[letra] = (u.id, u.session_version)

    @classmethod
    def _limpiar(cls):
        release(cls.app)
        cls.tmp.cleanup()

    def cliente(self, letra):
        c = self.app.test_client()
        uid, version = self.sesiones[letra]
        with c.session_transaction() as s:
            s.update(usuario_id=uid, usuario_version=version, csrf='test')
        return c

    def puede(self, letra, metodo, ruta, form):
        c = self.cliente(letra)
        if metodo == 'GET':
            r = c.get(ruta, follow_redirects=False)
        else:
            r = c.post(ruta, data=MultiDict(dict(form, csrf='test')), follow_redirects=False)
        r.close()
        if r.status_code == 403:
            return False
        if letra == 'S' and r.status_code == 302 and r.headers.get('Location', '').endswith('/ventas/sociedades') \
                and not ruta.split('?')[0].endswith(('/ventas/sociedades', '/finanzas/sociedades')):
            return False  # el Socio es devuelto a su página
        return True

    def test_cada_ruta_tiene_los_permisos_esperados(self):
        fallos = []
        for metodo, ruta, form, esperado in FILAS:
            url = ruta.format(**self.ids)
            real = ''.join(letra for letra in ROLES if self.puede(letra, metodo, url, form))
            if real != esperado:
                fallos.append(f'{metodo} {ruta} {form or ""}: esperado {esperado!r}, real {real!r}')
        self.assertEqual(fallos, [], 'Cambió el permiso de estas rutas:\n' + '\n'.join(fallos))

    def test_toda_ruta_de_la_aplicacion_esta_clasificada(self):
        adaptador = self.app.url_map.bind('localhost')
        cubiertas = set()
        for metodo, ruta, _, _ in FILAS:
            endpoint, _ = adaptador.match(ruta.format(**self.ids).split('?')[0], method=metodo)
            cubiertas.add((endpoint, metodo))
        existentes = set()
        for regla in self.app.url_map.iter_rules():
            for metodo in regla.methods - {'HEAD', 'OPTIONS'}:
                existentes.add((regla.endpoint, metodo))
        sin = sorted(e for e in existentes - cubiertas - PUBLICAS if e[0] not in EQUIVALENTES_DE_PRUEBA)
        self.assertEqual(sin, [], SIN_CLASIFICAR + ': añádelas a FILAS con los roles que deben poder usarlas')

    def test_las_acciones_de_escritura_no_quedan_abiertas_al_socio(self):
        for metodo, ruta, form, esperado in FILAS:
            if metodo == 'POST':
                self.assertNotIn('S', esperado, ruta)

    def test_nada_responde_sin_sesion(self):
        anonimo = self.app.test_client()
        for metodo, ruta, form, _ in FILAS:
            url = ruta.format(**self.ids)
            r = anonimo.get(url) if metodo == 'GET' else anonimo.post(url, data=dict(form))
            self.assertIn(r.status_code, (302, 400), f'{metodo} {ruta} respondió {r.status_code} sin sesión')
            if r.status_code == 302:
                self.assertIn('/iniciar-sesion', r.headers['Location'], f'{metodo} {ruta}')
            r.close()

    def test_las_rutas_publicas_son_solo_las_declaradas(self):
        self.assertEqual({e for e, _ in PUBLICAS}, {'auth.login', 'auth.logout', 'static'})


if __name__ == '__main__':
    unittest.main()
