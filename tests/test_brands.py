import unittest
import test_catalogs
from app.services import catalogo_service as catalogos
from app.extensions import db

class BrandTests(unittest.TestCase):
    setUp = test_catalogs.CatalogTests.setUp
    tearDown = test_catalogs.CatalogTests.tearDown
    imei = test_catalogs.CatalogTests.imei

    def test_brand_model_relationship_and_suggestion(self):
        with self.app.app_context():
            samsung = next(item for item in catalogos.list_items('brand') if item['name'] == 'SAMSUNG')
            samsung = catalogos.get_item(samsung['id'], 'brand')
            model = catalogos.save_item('reference', {'name':'Galaxy S26 Ultra','parent_id':samsung.id,'active':'1'})
            self.assertEqual(model.parent_id, samsung.id)
            self.assertEqual(model.name, 'GALAXY S26 ULTRA')
            self.assertEqual(model.display_name, 'SAMSUNG GALAXY S26 ULTRA')
            self.assertTrue(catalogos.reference_suggestions('Galaxy S26 Ultra',samsung.id))
            self.assertFalse(catalogos.reference_suggestions('Galaxy S26 Ultra',self.brand))

    def test_similar_model_needs_confirmation(self):
        response=self.client.post('/inventario/catalogos?kind=reference', data={'csrf':self.csrf,'name':'iPxhone 17 Pro Max','active':'1','parent_id':self.brand})
        page=response.get_data(as_text=True)
        self.assertIn('Alerta de modelo parecido',page)
        self.assertIn('Confirmo que es un modelo',page)
        response=self.client.post('/inventario/catalogos?kind=reference', data={'csrf':self.csrf,'name':'iPxhone 17 Pro Max','active':'1','parent_id':self.brand,'confirm_similar':'1'})
        self.assertEqual(response.status_code,302)

    def test_wrong_brand_rejected_on_equipment(self):
        with self.app.app_context():
            samsung=catalogos.get_item(next(item['id'] for item in catalogos.list_items('brand') if item['name']=='SAMSUNG'),'brand')
        response=self.client.post('/inventario/nuevo',data={**self.fields,'brand_id':samsung.id,'imei':self.imei(1),'condition':'Nuevo'})
        self.assertIn('modelo debe pertenecer',response.get_data(as_text=True))

    def test_capacity_is_predefined_and_names_are_uppercase(self):
        response = self.client.post('/inventario/catalogos?kind=capacity', data={
            'csrf': self.csrf, 'name': '65', 'active': '1', 'parent_id': self.ref})
        self.assertIn('capacidad predeterminada', response.get_data(as_text=True))
        with self.app.app_context():
            capacity = next(catalogos.get_item(i['id']) for i in catalogos.list_items('capacity') if i['parent_id']==self.ref and i['name']=='1024')
            color = catalogos.save_item('color', {'name': 'azul titanio', 'active': '1', 'parent_id': self.ref})
            self.assertEqual(capacity.name, '1024')
            self.assertEqual(color.name, 'AZUL TITANIO')

    def test_existing_typo_is_reported_by_catalog_audit(self):
        with self.app.app_context():
            unknown = catalogos.save_item('brand', {'name': 'Sin marca temporal', 'active': '0'})
            catalogos.save_item('reference', {'name': 'IPHXONE 17 PRO MAX', 'parent_id': unknown.id, 'active': '1'})
            alerts = catalogos.catalog_alerts()
            self.assertTrue(any(alert['score'] >= 88 for alert in alerts))
