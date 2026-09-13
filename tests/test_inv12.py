"""Regresión de búsqueda, compras consecutivas, costos y cobertura opcional."""
import unittest
import json
import sqlite3
import test_catalogs
from app.extensions import db
from app.models import Producto, Movimiento, Catalogo
from app.services.inventario_service import similar_data
from app.services.lote_service import list_lots
from app.services.catalogo_service import save_item
from migrations import upgrade


class Inventory12Tests(unittest.TestCase):
    setUp = test_catalogs.CatalogTests.setUp
    tearDown = test_catalogs.CatalogTests.tearDown
    imei = test_catalogs.CatalogTests.imei

    def create(self, index=0, **extra):
        response = self.client.post('/inventario/nuevo', data={**self.fields,
            'imei':self.imei(index), 'condition':'0 ciclos', **extra})
        self.assertEqual(response.status_code,302,response.get_data(as_text=True)[-1000:])
        with self.app.app_context():
            return db.session.scalar(db.select(Producto.id).where(Producto.imei==self.imei(index)))

    def test_consecutive_preserves_override_and_warranty_but_not_imei(self):
        first = self.create(exchange_rate='4000', warranty_enabled='1', warranty_until='2027-09-12', action='similar')
        with self.app.app_context():
            data = similar_data(first)
            self.assertNotIn('imei',data)
            self.assertEqual(data['exchange_rate'],'4000')
            self.assertEqual(data['warranty_until'],'2027-09-12')
            self.assertEqual(db.session.get(Producto,first).cost_cents,445500000)
        page = self.client.get(f'/inventario/nuevo?similar={first}').get_data(as_text=True)
        self.assertIn('value="4000"', page)
        second = self.create(1, **data)
        with self.app.app_context():
            a,b = db.session.get(Producto,first), db.session.get(Producto,second)
            self.assertEqual(a.cost_cents,b.cost_cents)
            self.assertEqual(a.lot_id,b.lot_id)
            self.assertEqual(a.warranty_until,b.warranty_until)
        self.assertIn('ya está registrado',self.client.post('/inventario/nuevo',data={**self.fields,
            'imei':self.imei(1),'condition':'Nuevo'}).get_data(as_text=True))

    def test_warranty_validation_and_edit_history(self):
        for invalid in ('','2026-02-30','texto'):
            page=self.client.post('/inventario/nuevo',data={**self.fields,'imei':self.imei(0),
                'condition':'Nuevo','warranty_enabled':'1','warranty_until':invalid}).get_data(as_text=True)
            self.assertIn('Indica hasta qué fecha',page)
        pid=self.create(warranty_until='incorrecta')  # Apagada: no exige ni usa la fecha.
        with self.app.app_context():
            self.assertIsNone(db.session.get(Producto,pid).warranty_until)
            revision=db.session.get(Producto,pid).revision
        response=self.client.post(f'/inventario/{pid}',data={**self.fields,'imei':self.imei(0),
            'revision':str(revision),'action':'edit','reason':'Corregir cobertura y tasa',
            'condition':'0 ciclos','exchange_rate':'4100','warranty_form':'1',
            'warranty_enabled':'1','warranty_until':'2027-01-01'})
        self.assertEqual(response.status_code,302)
        with self.app.app_context():
            p=db.session.get(Producto,pid)
            self.assertEqual(p.exchange_rate,'4100')
            self.assertEqual(p.warranty_until,'2027-01-01')
            self.assertEqual(p.status,'Disponible')
            event=db.session.scalar(db.select(Movimiento).where(Movimiento.product_id==pid))
            self.assertEqual(json.loads(event.after_data)['warranty_until'],'2027-01-01')

    def test_live_counts_sold_and_warranty_of_sold(self):
        pids=[self.create(i) for i in range(3)]
        with self.app.app_context():
            revision=db.session.get(Producto,pids[0]).revision
        payload={'csrf':self.csrf,'revision':str(revision),'action':'sell','reason':'Venta de prueba',
                 'seller':'PRUEBA','responsible':'CLIENTE','sale_value':'5000000'}
        self.assertEqual(self.client.post(f'/ventas/{pids[0]}',data=payload).status_code,302)
        html=self.client.get('/inventario?fragment=1&q=17+pro+max').get_data(as_text=True)
        self.assertIn('2 equipos disponibles',html)
        self.assertNotIn(self.imei(0),html)
        self.assertIn(self.imei(1),html)
        self.assertNotIn('Cambiar bodega',html)
        html=self.client.get('/inventario?fragment=1&vendidos=1&q=17').get_data(as_text=True)
        self.assertIn('1 equipos vendidos',html)
        with self.app.app_context():
            p=db.session.get(Producto,pids[0])
            revision=p.revision
        self.assertEqual(self.client.post(f'/ventas/{pids[0]}',data={**payload,'revision':str(revision),'action':'warranty'}).status_code,302)
        with self.app.app_context():
            summary=list_lots()[0]
            self.assertEqual((summary['available'],summary['sold'],summary['other']),(2,1,0))
        self.assertIn(self.imei(0),self.client.get('/inventario?vendidos=1').get_data(as_text=True))
        self.assertIn('2 disponibles · 1 vendidos',self.client.get(f"/inventario/lotes/{self.fields['lot_id']}").get_data(as_text=True))
        html=self.client.get('/inventario?fragment=1&q='+self.imei(1)[:13]).get_data(as_text=True)
        self.assertIn(self.imei(1),html)

    def test_catalog_unicode_uppercase_and_migration_idempotent(self):
        with self.app.app_context():
            item=save_item('supplier',{'name':'  compañía pérez  ','active':'1'})
            self.assertEqual(item.name,'COMPAÑÍA PÉREZ')
            ref=db.session.scalar(db.select(Catalogo).where(Catalogo.kind=='reference',Catalogo.name=='IPHONE 11 PRO MAX'))
            self.assertIsNotNone(ref)
            options=db.session.scalars(db.select(Catalogo).where(Catalogo.parent_id==ref.id)).all()
            self.assertEqual({c.name for c in options if c.kind=='capacity'},{'64','256','512'})
            self.assertIn('VERDE MEDIANOCHE',{c.name for c in options if c.kind=='color'})
        self.create()
        upgrade(self.database)
        upgrade(self.database)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM equipment').fetchone()[0],1)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM schema_version WHERE version=8').fetchone()[0],1)
