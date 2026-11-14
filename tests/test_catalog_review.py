"""Prevención de duplicados sin confundir variantes válidas del catálogo."""
import unittest
import test_catalogs
from app.extensions import db
from app.models import Catalogo
from app.services import catalogo_service as service


class CatalogReviewTests(unittest.TestCase):
    setUp = test_catalogs.CatalogTests.setUp
    tearDown = test_catalogs.CatalogTests.tearDown

    def post(self, kind='reference', **values):
        fields = dict(csrf=self.csrf, name='IPXHONE 17 PRO MAX', parent_id=self.brand, active='1')
        fields.update(values)
        return self.client.post('/inventario/catalogos?kind='+kind, data=fields)

    def count(self):
        with self.app.app_context():
            return db.session.scalar(db.select(db.func.count()).select_from(Catalogo))

    def test_different_generations_and_variants_are_not_duplicates(self):
        pairs = [('IPHONE 11 PRO MAX','IPHONE 12 PRO MAX'),
                 ('IPHONE SE (2.ª GENERACIÓN)','IPHONE SE (3.ª GENERACIÓN)'),
                 ('IPHONE 16','IPHONE 16E'), ('IPHONE X','IPHONE XR'), ('IPHONE 17','IPHONE 17 PRO'),
                 ('IPHONE 17 PRO','IPHONE 17 PRO MAX'), ('GALAXY S24','GALAXY S24 ULTRA')]
        for first, second in pairs:
            with self.subTest(pair=(first,second)):
                self.assertEqual(service.name_similarity(first, second, model=True),0)
        with self.app.app_context():
            # Un modelo nuevo con otro número no debe pedir una confirmación innecesaria.
            item=service.save_item('reference',dict(name='IPHONE 99 PRO MAX',parent_id=self.brand,active='1'))
            self.assertEqual(item.name,'IPHONE 99 PRO MAX')
            alerts=service.catalog_alerts()
            self.assertFalse(any(a['first']['name'].endswith('11 PRO MAX') and
                                 a['second']['name'].endswith('12 PRO MAX') for a in alerts))

    def test_typo_review_preserves_input_and_writes_only_after_confirmation(self):
        before=self.count();reply=self.post();html=reply.get_data(as_text=True)
        self.assertEqual(reply.status_code,200);self.assertEqual(self.count(),before)
        self.assertIn('id="catalog-review"',html);self.assertIn('Usar existente',html)
        self.assertIn('value="IPXHONE 17 PRO MAX"',html)
        self.assertIn('Es distinto: guardar',html)
        self.assertNotIn('Alertas de calidad del catálogo',html)
        self.assertEqual(self.post(confirm_similar='1').status_code,302)
        self.assertEqual(self.count(),before+1)
        # Incluso si se reenvía confirm_similar, un duplicado exacto no se guarda.
        html=self.post(confirm_similar='1').get_data(as_text=True)
        self.assertIn('Ya existe esta opción',html);self.assertNotIn('Es distinto: guardar',html)
        self.assertEqual(self.count(),before+1)

    def test_normalized_and_inactive_duplicates_cannot_be_bypassed(self):
        with self.app.app_context():
            item=db.session.get(Catalogo,self.ref);item.active=0;db.session.commit()
        before=self.count()
        for name in ('17 PRO MAX','IPHONE 17 PROMAX','ápple iphone 17 pro max'):
            html=self.post(name=name,confirm_similar='1').get_data(as_text=True)
            self.assertIn('Ya existe esta opción',html)
            self.assertIn('Revisar existente',html)
            self.assertNotIn('Es distinto: guardar',html)
        self.assertEqual(self.count(),before)

    def test_other_catalog_types_and_parent_scope(self):
        with self.app.app_context():
            base=service.save_item('location',dict(name='BODEGA DEL CENTRO',active='1'))
            original_id=base.id
        before=self.count()
        html=self.post(kind='location',name='BODEGA DEL CENTRRO').get_data(as_text=True)
        self.assertIn('Encontramos nombres similares',html);self.assertEqual(self.count(),before)
        self.assertEqual(self.post(kind='location',name='BODEGA DEL CENTRRO',confirm_similar='1').status_code,302)
        # La edición que solo cambia el estado no genera avisos por su propio nombre.
        self.assertEqual(self.post(kind='location',id=original_id,name='BODEGA DEL CENTRO',active='0').status_code,302)
        with self.app.app_context():
            samsung=db.session.scalar(db.select(Catalogo).where(Catalogo.kind=='brand',Catalogo.name=='SAMSUNG'))
            self.assertFalse(service.reference_suggestions('IPXHONE 17 PRO MAX',samsung.id))

    def test_edit_to_existing_name_is_rejected_without_losing_original(self):
        with self.app.app_context():
            item=service.save_item('location',dict(name='VITRINA PRINCIPAL',active='1'));first=item.id
            second=service.save_item('location',dict(name='EXHIBIDOR AUXILIAR',active='1')).id
        html=self.post(kind='location',id=second,name='VITRINA PRINCIPAL',confirm_similar='1').get_data(as_text=True)
        self.assertIn('Ya existe esta opción',html)
        with self.app.app_context():
            self.assertEqual(db.session.get(Catalogo,second).name,'EXHIBIDOR AUXILIAR')
            self.assertEqual(db.session.get(Catalogo,first).name,'VITRINA PRINCIPAL')

    def test_users_have_no_finance_subnav_and_other_modules_keep_theirs(self):
        html=self.client.get('/usuarios').get_data(as_text=True)
        self.assertIn('Usuarios y permisos',html);self.assertIn('Volver al resumen',html)
        # La matriz de permisos sí debe nombrar Créditos; no es una subnavegación.
        self.assertNotIn('Créditos y desembolsos',html.split('</aside>',1)[0])
        self.assertIn('data-module="creditos"',html)
        self.assertNotIn('class="g-nav"',html)
        sales=self.client.get('/ventas').get_data(as_text=True)
        self.assertIn('Sociedades y liquidaciones',sales)
        finance=self.client.get('/finanzas/creditos').get_data(as_text=True)
        self.assertIn('Jornada',finance);self.assertIn('Historial',finance)


if __name__=='__main__':unittest.main()
