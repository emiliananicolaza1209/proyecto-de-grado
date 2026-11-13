"""Seguridad: los costos de compra no viajan al navegador de quien no los necesita."""
import secrets
import tempfile
import unittest
from pathlib import Path

from werkzeug.datastructures import MultiDict
from werkzeug.security import generate_password_hash

from _cleanup import release
from app import create_app
from app.extensions import db
from app.models import Producto
from app.models.finanzas import OperacionFinanciera as Op
from app.models.gestion import Socio, Usuario
from app.services import finanzas_service as fin

COSTO_A = 387654300  # equipo en Disponible: $3.876.543
COSTO_B = 291234500  # otro equipo en Disponible: $2.912.345
BLOQUES = ('finance-equipment-costs', 'finance-stock-costs')


def formas(cents):
    """Formas en que un importe podría aparecer en el HTML."""
    pesos = cents / 100
    return {str(cents), f'{pesos:.2f}', f'{pesos:,.2f}', f'{pesos:,.0f}',
            f'{pesos:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'),
            f'{pesos:,.0f}'.replace(',', '.')}


def bloques_con_datos(html):
    """Bloques de costos de Finanzas que traen contenido (un bloque vacío '{}' no filtra nada)."""
    import re
    return [b for b in BLOQUES for m in re.finditer(r'id="%s">(.*?)</script>' % b, html, re.S) if m.group(1).strip() not in ('', '{}')]


def contiene(html, cents):
    return any(f in html for f in formas(cents))


class CostosBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'DATABASE': str(Path(self.tmp.name) / 'db.sqlite'), 'SECRET_KEY': 'test'})
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.dia = fin.today()
        self.d = fin.open_day(self.dia)
        cfg = dict(self.d.config)
        cfg['staff'] = [dict(name=n, role='Principal', salary=0, attended=True) for n in ('ANA', 'LUZ')]
        cfg['reviewed'] = True
        cfg['actor'] = 'ANA'
        self.d.config = cfg
        self.a = self.equipo('490154203237518', COSTO_A)
        self.b = self.equipo('490154203237526', COSTO_B)
        self.otro_socio = Socio(nombre='SOCIO AJENO', activo=True)
        db.session.add(self.otro_socio)
        db.session.commit()
        self.app.config['AUTH_REQUIRED'] = True

    def tearDown(self):
        release(self.app)
        self.ctx.pop()
        self.tmp.cleanup()

    def equipo(self, imei, costo):
        p = Producto(imei=imei, model='IPHONE PRUEBA', capacity=128, color='NEGRO', condition='Nuevo', cost_cents=costo,
                     additional_costs=[], source_type='Lote', location='LOCAL', supplier='CP CELULARES', status='Disponible')
        db.session.add(p)
        db.session.commit()
        return p

    def cliente(self, rol, **extra):
        u = Usuario(nombre=rol, login=rol.lower(), rol=rol, password_hash=generate_password_hash('clave_prueba_123'), **extra)
        db.session.add(u)
        db.session.commit()
        c = self.app.test_client()
        with c.session_transaction() as s:
            s.update(usuario_id=u.id, usuario_version=u.session_version, csrf='test')
        return c

    def venta(self, cliente, imei, cost_unit):
        return cliente.post('/finanzas', data=MultiDict([
            ('csrf', 'test'), ('action', 'operation'), ('kind', 'Venta'), ('date', self.dia), ('revision', str(self.d.revision)),
            ('description', 'VENTA PRUEBA'), ('seller', 'ANA'), ('token', secrets.token_hex(16)), ('amount', '4500000'),
            ('minor_cost', ''), ('cost_type', 'Equipo'), ('cost_name', imei), ('cost_qty', '1'), ('cost_unit', cost_unit),
            ('payment_account', 'EFECTIVO'), ('payment_amount', '4500000')]))


class FugaDeCostosTests(CostosBase):
    def test_vendedora_no_recibe_bloques_de_costos_ni_cifras_en_finanzas(self):
        c = self.cliente('Vendedora')
        html = c.get('/finanzas?accion=registrar').get_data(as_text=True)
        self.assertEqual(bloques_con_datos(html), [])
        self.assertFalse(contiene(html, COSTO_A))
        self.assertFalse(contiene(html, COSTO_B))

    def test_vendedora_no_ve_costos_en_ventas_ni_creditos(self):
        c = self.cliente('Vendedora')
        for url in ('/ventas', f'/ventas/{self.a.id}', '/finanzas/creditos', '/'):
            html = c.get(url).get_data(as_text=True)
            self.assertEqual(bloques_con_datos(html), [], url)
            self.assertFalse(contiene(html, COSTO_A), url)
            self.assertFalse(contiene(html, COSTO_B), url)

    def test_administracion_si_recibe_los_bloques(self):
        for rol in ('Propietario', 'Administrador'):
            html = self.cliente(rol).get('/finanzas?accion=registrar').get_data(as_text=True)
            self.assertIn('finance-equipment-costs', bloques_con_datos(html), rol)
            self.assertIn(str(COSTO_A), html, rol)

    def test_inventario_y_socio_nunca_reciben_los_bloques_de_finanzas(self):
        for rol, extra in (('Inventario', {}), ('Socio', {'socio_id': self.otro_socio.id})):
            c = self.cliente(rol, **extra)
            for url in ('/finanzas', '/finanzas/creditos', '/ventas/sociedades', '/ventas/inversion', '/inventario/inversion', '/'):
                r = c.get(url, follow_redirects=True)
                html = r.get_data(as_text=True)
                self.assertEqual(bloques_con_datos(html), [], f'{rol} {url}')

    def test_socio_solo_recibe_cifras_de_su_participacion(self):
        c = self.cliente('Socio', socio_id=self.otro_socio.id)
        for url in ('/ventas/sociedades', '/finanzas/sociedades', '/ventas/inversion', '/inventario/inversion'):
            html = c.get(url, follow_redirects=True).get_data(as_text=True)
            self.assertFalse(contiene(html, COSTO_A), url)
            self.assertFalse(contiene(html, COSTO_B), url)

    def test_vendedora_vende_y_el_servidor_toma_el_costo_de_inventario(self):
        c = self.cliente('Vendedora')
        self.assertEqual(self.venta(c, self.a.imei, '').status_code, 302)  # el navegador ya no envía el costo
        db.session.expire_all()
        op = db.session.scalar(db.select(Op).order_by(Op.id.desc()))
        self.assertEqual(db.session.get(Producto, self.a.id).status, 'Vendido')
        self.assertEqual(op.costs[0]['amount'], COSTO_A)

    def test_vendedora_no_puede_fijar_el_costo_ni_usar_el_error_como_oraculo(self):
        c = self.cliente('Vendedora')
        r = self.venta(c, self.b.imei, '1.00')  # costo falso enviado a mano: se ignora
        self.assertEqual(r.status_code, 302)
        db.session.expire_all()
        op = db.session.scalar(db.select(Op).order_by(Op.id.desc()))
        self.assertEqual(op.costs[0]['amount'], COSTO_B)

    def test_administracion_mantiene_la_validacion_del_costo(self):
        c = self.cliente('Administrador')
        html = self.venta(c, self.b.imei, '1.00').get_data(as_text=True)
        self.assertIn('debe coincidir con el costo registrado', html)
        self.assertEqual(db.session.get(Producto, self.b.id).status, 'Disponible')

    def test_la_plantilla_oculta_el_campo_de_costo_a_la_vendedora(self):
        html = self.cliente('Vendedora').get('/finanzas?accion=registrar').get_data(as_text=True)
        self.assertIn('data-costs-hidden="1"', html)
        self.assertNotIn('data-costs-hidden', self.cliente('Propietario').get('/finanzas?accion=registrar').get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
