import unittest
import test_catalogs
from app.extensions import db
from app.models import Producto, Movimiento
from app.services.lote_service import create_lot
from app.services.inventario_service import stats
from app.services.operacion_service import today


class ModuleTests(unittest.TestCase):
    setUp = test_catalogs.CatalogTests.setUp
    tearDown = test_catalogs.CatalogTests.tearDown
    imei = test_catalogs.CatalogTests.imei

    def test_lots_share_stock_and_sales_change_it(self):
        with self.app.app_context():
            lot = create_lot({'supplier_id':self.fields['supplier_id'], 'exchange_rate':'4000','expected_count':'1'})
            second = lot.id
        for i, lot_id in enumerate((self.fields['lot_id'],second)):
            response = self.client.post('/inventario/nuevo',data={**self.fields,'lot_id':lot_id,'imei':self.imei(i),'condition':'Nuevo'})
            self.assertEqual(response.status_code,302)
        with self.app.app_context():
            products = db.session.scalars(db.select(Producto).order_by(Producto.id)).all()
            self.assertEqual(products[1].exchange_rate,'3245')  # La tasa del equipo puede diferir de la sugerida.
            self.assertNotEqual(products[0].lot_id,products[1].lot_id)
            self.assertEqual(stats()['total'],2)
            pid,revision=products[0].id,products[0].revision
        payload = {'csrf':self.csrf,'revision':str(revision),'action':'handoff','reason':'Entrega de prueba',
                   'loan_handler':'ENCARGADA','responsible':'LOCAL PRUEBA','purpose':'Venta','due_date':today()}
        denied = self.client.post(f'/inventario/{pid}',data=payload)
        self.assertIn('exclusivamente',denied.get_data(as_text=True))
        self.assertEqual(self.client.post(f'/ventas/{pid}',data=payload).status_code,302)
        page = self.client.get('/inventario?q=17+PRO+MAX').get_data(as_text=True)
        self.assertNotIn(self.imei(0),page)
        self.assertIn(self.imei(1),page)
        sales = self.client.get('/ventas').get_data(as_text=True)
        self.assertIn(self.imei(0),sales)
        self.assertIn(self.imei(1),sales)
        with self.app.app_context():
            self.assertEqual(stats()['total'],1)
            revision=db.session.get(Producto,pid).revision
        self.assertEqual(self.client.post(f'/ventas/{pid}',data={**payload,'revision':str(revision),'action':'return',
            'location_id':self.fields['location_id'],'condition':'Nuevo','return_condition':'Disponible'}).status_code,302)
        with self.app.app_context():
            self.assertEqual(stats()['total'],2)
            self.assertEqual(db.session.get(Producto,pid).lot_id,self.fields['lot_id'])
            self.assertEqual(db.session.query(Movimiento).filter_by(product_id=pid).count(),2)

    def test_lot_required_and_views(self):
        data={**self.fields,'lot_id':'','imei':self.imei(0),'condition':'Nuevo'}
        self.assertIn('Selecciona el lote',self.client.post('/inventario/nuevo',data=data).get_data(as_text=True))
        for path in ['/inventario/lotes',f"/inventario/lotes/{self.fields['lot_id']}",'/ventas','/inventario']:
            self.assertEqual(self.client.get(path).status_code,200)
        self.assertEqual(self.client.get('/modulos/ventas').location,'/ventas')
        self.assertIn('IPHONE 8 PLUS',self.client.get('/inventario/nuevo').get_data(as_text=True))
        self.assertNotIn('name="action" value="sell"',self.client.get('/inventario/nuevo').get_data(as_text=True))
