import unittest
import test_catalogs
from app.extensions import db
from app.models import Producto, Movimiento
from app.services.catalogo_service import save_item

class ActionsTests(unittest.TestCase):
    setUp=test_catalogs.CatalogTests.setUp
    tearDown=test_catalogs.CatalogTests.tearDown
    imei=test_catalogs.CatalogTests.imei

    def prepare(self):
        self.client.post('/inventario/nuevo',data={**self.fields,'imei':self.imei(1),'condition':'Nuevo'})
        with self.app.app_context():
            p=db.session.scalar(db.select(Producto))
            return p.id,p.revision

    def test_edit_transfer_archive_restore(self):
        pid,rev=self.prepare()
        url=f'/inventario/{pid}'
        self.assertEqual(self.client.get(url).status_code,200)
        self.assertEqual(self.client.post(url,data={**self.fields,'action':'edit','revision':str(rev),'reason':'Corregir precio','imei':self.imei(1),'condition':'Usado','purchase_usd':'1000'}).status_code,302)
        with self.app.app_context():
            destination=save_item('location',{'name':'Bodega dos','active':'1'}).id
            p=db.session.get(Producto,pid)
            rev=p.revision;cost=p.cost_cents
        self.assertEqual(self.client.post(url,data={'csrf':self.csrf,'action':'transfer','revision':str(rev),'reason':'Enviar a bodega','location_id':destination}).status_code,302)
        page=self.client.get(url).get_data(as_text=True)
        self.assertIn('BODEGA DOS',page)
        with self.app.app_context():
            p=db.session.get(Producto,pid)
            self.assertEqual(p.location_id,destination)
            self.assertEqual(p.cost_cents,cost)
            rev=p.revision
        for action in ['archive','restore']:
            response=self.client.post(url,data={'csrf':self.csrf,'action':action,'revision':str(rev),'reason':'Corrección de registro','confirm_imei':self.imei(1)})
            self.assertEqual(response.status_code,302)
            with self.app.app_context():
                p=db.session.get(Producto,pid)
                self.assertEqual(p.archived,int(action=='archive'))
                rev=p.revision
            listing=self.client.get('/inventario').get_data(as_text=True)
            self.assertEqual(self.imei(1) in listing,action=='restore')
        with self.app.app_context():
            self.assertEqual(db.session.scalar(db.select(db.func.count(Movimiento.id))),4)

    def test_stale_invalid_and_duplicate_are_atomic(self):
        pid,rev=self.prepare();url=f'/inventario/{pid}'
        for data in [{'action':'transfer','revision':str(rev),'location_id':self.fields['location_id']},
                     {'action':'archive','revision':str(rev),'confirm_imei':'wrong'},
                     {'action':'archive','revision':'0','confirm_imei':self.imei(1)}]:
            self.assertEqual(self.client.post(url,data={**data,'csrf':self.csrf,'reason':'Prueba de validación'}).status_code,200)
        self.client.post('/inventario/nuevo',data={**self.fields,'imei':self.imei(2),'condition':'Nuevo'})
        response=self.client.post(url,data={**self.fields,'action':'edit','revision':str(rev),'reason':'Corregir IMEI','imei':self.imei(2),'condition':'Usado'})
        self.assertIn('pertenece a otro',response.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(db.session.get(Producto,pid).condition,'Nuevo')
            self.assertEqual(db.session.scalar(db.select(db.func.count(Movimiento.id))),0)
        self.assertEqual(self.client.post(url,data={'action':'archive'}).status_code,400)
