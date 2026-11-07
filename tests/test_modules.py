import unittest
import test_catalogs
from app.extensions import db
from app.models import Producto, Movimiento
from app.models.finanzas import Jornada, OperacionFinanciera, AuditoriaFinanciera
from app.services.lote_service import create_lot
from app.services.inventario_service import stats
from app.services.operacion_service import today


class ModuleTests(unittest.TestCase):
    setUp = test_catalogs.CatalogTests.setUp
    tearDown = test_catalogs.CatalogTests.tearDown
    imei = test_catalogs.CatalogTests.imei

    def test_home_operational_dashboard_tracks_status_and_followup(self):
        self.assertEqual(self.client.post('/inventario/nuevo',data={**self.fields,'imei':self.imei(0),'condition':'Nuevo'}).status_code,302)
        with self.app.app_context():
            p=db.session.scalar(db.select(Producto))
            p.status='En pasamano';p.responsible='LOCAL';p.due_date='2020-01-01'
            db.session.commit()
        page=self.client.get('/').get_data(as_text=True)
        self.assertIn('Resumen de trabajo',page)
        self.assertIn('Devoluciones vencidas · 1',page)
        self.assertIn(self.imei(0),page)
        self.assertIn('/ventas?estado=En+pasamano',page)

    def test_navigation_and_sales_search_keep_existing_routes(self):
        response=self.client.get('/ventas?q=IPHONE')
        self.assertEqual(response.status_code,200)
        page=response.get_data(as_text=True)
        self.assertIn('data-filter-table="ventas-tabla"',page)
        self.assertIn('Equipos encontrados',page)
        self.assertIn('action="/ventas"',page)
        self.assertIn('experiencia.js',page)
        self.assertIn('aria-label="Navegación principal"',page)

    def test_all_filters_and_reverse_unpaid_sale_preserves_history(self):
        for i in range(2):
            self.assertEqual(self.client.post('/inventario/nuevo',data={**self.fields,'imei':self.imei(i),'condition':'Nuevo'}).status_code,302)
        with self.app.app_context():
            products=db.session.scalars(db.select(Producto).order_by(Producto.id)).all()
            p=products[0];p.status='Vendido';p.sale_value_cents=100000;p.paid_cents=0;p.payment_status='Pendiente'
            p.sale_date=today();p.movement_date=today();db.session.commit();pid=p.id;revision=p.revision
        page=self.client.get('/inventario?todos=1').get_data(as_text=True)
        self.assertIn(self.imei(0),page);self.assertIn(self.imei(1),page);self.assertIn('status-sold',page)
        page=self.client.get('/ventas?saldo=1').get_data(as_text=True)
        self.assertIn(self.imei(0),page);self.assertNotIn(self.imei(1),page)
        response=self.client.post(f'/ventas/{pid}',data={'csrf':self.csrf,'revision':str(revision),'action':'reverse_sale','reason':'Venta registrada por error'})
        self.assertEqual(response.status_code,302)
        with self.app.app_context():
            product=db.session.get(Producto,pid);self.assertEqual(product.status,'Disponible')
            event=db.session.scalar(db.select(Movimiento).where(Movimiento.product_id==pid))
            self.assertIn('Anular venta',event.action);self.assertIn('Vendido',event.before_data)

    def test_reverse_sale_refuses_active_money(self):
        self.assertEqual(self.client.post('/inventario/nuevo',data={**self.fields,'imei':self.imei(0),'condition':'Nuevo'}).status_code,302)
        with self.app.app_context():
            p=db.session.scalar(db.select(Producto));p.status='Vendido';p.paid_cents=100;p.sale_value_cents=1000
            p.sale_date=today();p.movement_date=today();db.session.commit();pid=p.id;revision=p.revision
        response=self.client.post(f'/ventas/{pid}',data={'csrf':self.csrf,'revision':str(revision),'action':'reverse_sale','reason':'Error de registro'})
        self.assertIn('tiene cobros',response.get_data(as_text=True))
        with self.app.app_context():self.assertEqual(db.session.get(Producto,pid).status,'Vendido')

    def test_sold_lot_and_detail_show_status_and_offer_correction(self):
        self.assertEqual(self.client.post('/inventario/nuevo',data={**self.fields,'imei':self.imei(0),'condition':'Nuevo'}).status_code,302)
        with self.app.app_context():
            p=db.session.scalar(db.select(Producto));p.status='Vendido';p.sale_value_cents=100000
            p.sale_date=today();p.movement_date=today();db.session.commit();pid=p.id
        lot=self.client.get(f"/inventario/lotes/{self.fields['lot_id']}").get_data(as_text=True)
        self.assertIn('availability status-sold',lot)
        detail=self.client.get(f'/inventario/{pid}').get_data(as_text=True)
        self.assertIn('pill status-sold',detail)
        self.assertIn(f'/ventas/{pid}?accion=reverse_sale#operaciones',detail)
        sales=self.client.get(f'/ventas/{pid}?accion=reverse_sale').get_data(as_text=True)
        self.assertIn('data-action="reverse_sale" open',sales)

    def test_sales_cards_and_search_keep_pending_filter(self):
        for i in range(2):
            self.assertEqual(self.client.post('/inventario/nuevo',data={**self.fields,'imei':self.imei(i),'condition':'Nuevo'}).status_code,302)
        with self.app.app_context():
            p=db.session.scalar(db.select(Producto).where(Producto.imei==self.imei(0)))
            p.status='Vendido';p.sale_value_cents=100000;p.paid_cents=20000
            p.sale_date=today();p.movement_date=today();db.session.commit()
        page=self.client.get('/ventas?saldo=1').get_data(as_text=True)
        self.assertIn(self.imei(0),page);self.assertNotIn(self.imei(1),page)
        self.assertIn('name="saldo" value="1" checked',page)
        self.assertIn('aria-current="page"',page)
        self.assertIn('sales-state status-sold',page)
        page=self.client.get(f'/ventas?saldo=1&q={self.imei(0)}').get_data(as_text=True)
        self.assertIn('name="saldo" value="1" checked',page)
        self.assertIn(self.imei(0),page)
        page=self.client.get('/ventas?estado=Disponible').get_data(as_text=True)
        self.assertIn(self.imei(1),page);self.assertNotIn(self.imei(0),page)

    def test_reverse_sale_voids_empty_finance_operation_and_allows_resale(self):
        self.assertEqual(self.client.post('/inventario/nuevo',data={**self.fields,'imei':self.imei(0),'condition':'Nuevo'}).status_code,302)
        with self.app.app_context():
            p=db.session.scalar(db.select(Producto));p.status='Vendido';p.sale_value_cents=100000
            p.sale_date=today();p.movement_date=today()
            day=Jornada(date=today(),config={},status='Abierta')
            db.session.add(day);db.session.flush()
            op=OperacionFinanciera(day_id=day.id,token='operacion-venta-prueba',kind='Venta',description='Venta equivocada',seller='ANA',
                                   amount=100000,minor_cost=0,product_id=p.id,costs=[],payments=[],voided=False)
            db.session.add(op);db.session.commit();pid=p.id;revision=p.revision;op_id=op.id
        response=self.client.post(f'/ventas/{pid}',data={'csrf':self.csrf,'revision':str(revision),
            'action':'reverse_sale','reason':'Venta registrada a otro equipo'})
        self.assertEqual(response.status_code,302)
        with self.app.app_context():
            p=db.session.get(Producto,pid);op=db.session.get(OperacionFinanciera,op_id)
            self.assertEqual(p.status,'Disponible');self.assertTrue(op.voided);self.assertIsNone(op.product_id)
            self.assertEqual(db.session.scalar(db.select(db.func.count(AuditoriaFinanciera.id))),1)
            revision=p.revision
        response=self.client.post(f'/ventas/{pid}',data={'csrf':self.csrf,'revision':str(revision),
            'action':'sell','reason':'Venta correcta','seller':'ANA','responsible':'CLIENTE','sale_value':'2000'})
        self.assertEqual(response.status_code,302)
        with self.app.app_context():
            self.assertEqual(db.session.get(Producto,pid).status,'Vendido')
            new_op=db.session.scalar(db.select(OperacionFinanciera).where(OperacionFinanciera.product_id==pid))
            self.assertIsNotNone(new_op);self.assertNotEqual(new_op.id,op_id)

    def test_reverse_sale_refuses_closed_finance_day(self):
        self.assertEqual(self.client.post('/inventario/nuevo',data={**self.fields,'imei':self.imei(0),'condition':'Nuevo'}).status_code,302)
        with self.app.app_context():
            p=db.session.scalar(db.select(Producto));p.status='Vendido';p.sale_value_cents=100000
            p.sale_date=today();p.movement_date=today()
            day=Jornada(date=today(),config={},status='Cerrada')
            db.session.add(day);db.session.flush()
            db.session.add(OperacionFinanciera(day_id=day.id,token='operacion-cerrada',kind='Venta',description='Venta cerrada',
                seller='ANA',amount=100000,minor_cost=0,product_id=p.id,costs=[],payments=[],voided=False))
            db.session.commit();pid=p.id;revision=p.revision
        response=self.client.post(f'/ventas/{pid}',data={'csrf':self.csrf,'revision':str(revision),
            'action':'reverse_sale','reason':'Venta registrada por error'})
        self.assertIn('Reabre la jornada financiera',response.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(db.session.get(Producto,pid).status,'Vendido')
            self.assertFalse(db.session.scalar(db.select(OperacionFinanciera)).voided)

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
