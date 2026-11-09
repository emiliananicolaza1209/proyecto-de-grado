"""Seguridad: Inventario ve cuántos equipos hay por ubicación, no el capital de cada socio."""
import re
import unittest

from test_seguridad_costos import COSTO_A, COSTO_B, CostosBase, contiene
from app.extensions import db
from app.models.gestion import Socio


class InversionPorRolTests(CostosBase):
    URLS = ('/inventario/inversion', '/ventas/inversion')

    def texto(self, html):
        return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))

    def test_inventario_solo_ve_equipos_por_ubicacion(self):
        c = self.cliente('Inventario')
        nombres = [s.nombre for s in db.session.scalars(db.select(Socio))]
        self.assertTrue(nombres)
        for url in self.URLS:
            r = c.get(url)
            self.assertEqual(r.status_code, 200, url)
            html = r.get_data(as_text=True)
            visible = self.texto(html)
            self.assertIn('Equipos por ubicación', visible, url)
            self.assertIn('LOCAL', visible, url)
            self.assertRegex(visible, r'LOCAL\s+2\b', url)  # dos equipos disponibles en LOCAL
            for socio in nombres:
                self.assertNotIn(socio, html, url)
            self.assertNotIn('Propietario', visible, url)
            self.assertNotIn('Capital', visible, url)
            self.assertNotIn('$', visible, url)
            self.assertFalse(contiene(html, COSTO_A), url)
            self.assertFalse(contiene(html, COSTO_B), url)
            self.assertFalse(contiene(html, COSTO_A + COSTO_B), url)

    def test_administracion_sigue_viendo_capital_y_propietario(self):
        for rol in ('Propietario', 'Administrador'):
            html = self.cliente(rol).get('/inventario/inversion').get_data(as_text=True)
            visible = self.texto(html)
            self.assertIn('Inversión por ubicación y propietario', visible, rol)
            self.assertIn('Capital', visible, rol)
            self.assertTrue(contiene(html, COSTO_A + COSTO_B), rol)

    def test_socio_sigue_viendo_solo_lo_suyo(self):
        c = self.cliente('Socio', socio_id=self.otro_socio.id)
        html = c.get('/ventas/inversion').get_data(as_text=True)
        self.assertIn('Inversión por ubicación y propietario', self.texto(html))
        self.assertFalse(contiene(html, COSTO_A))
        self.assertFalse(contiene(html, COSTO_B))

    def test_vendedora_sigue_sin_acceso(self):
        c = self.cliente('Vendedora')
        for url in self.URLS:
            self.assertEqual(c.get(url).status_code, 403, url)


if __name__ == '__main__':
    unittest.main()
