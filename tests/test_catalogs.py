import sqlite3
import tempfile
import unittest
from pathlib import Path
from app import create_app
from app.services.catalogo_service import CONDITIONS
from migrations.legacy import add_item
from contextlib import contextmanager
from flask import current_app

@contextmanager
def connection():
    db = sqlite3.connect(current_app.config["DATABASE"])
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()

from app.services.inventario_service import valid_imei


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = str(Path(self.temp.name) / 'test.sqlite')
        self.app = create_app({'TESTING': True, 'DATABASE': self.database, 'SECRET_KEY': 'test'})
        self.client = self.app.test_client()
        self.client.get('/inventario/nuevo')
        with self.client.session_transaction() as session:
            self.csrf = session['csrf']
        with self.app.app_context(), connection() as db:
            self.brand = add_item(db, 'brand', 'Apple')
            self.ref = add_item(db, 'reference', 'iPhone 17 Pro Max', self.brand)
            self.fields = {'brand_id': self.brand, 'reference_id': self.ref,
                'color_id': add_item(db, 'color', 'Azul', self.ref),
                'capacity_id': add_item(db, 'capacity', '256', self.ref),
                'supplier_id': add_item(db, 'supplier', 'Proveedor de prueba'),
                'location_id': add_item(db, 'location', 'Bodega de prueba'),
                'purchase_usd': '1070', 'exchange_rate':'3245', 'shipping_cop':'175000', 'csrf': self.csrf}

        with self.app.app_context():
            from app.services.lote_service import create_lot
            lot = create_lot({'supplier_id': self.fields['supplier_id'], 'exchange_rate':'3245', 'expected_count':'20'})
            self.fields['lot_id'] = lot.id

    def tearDown(self):
        self.temp.cleanup()

    def imei(self, n):
        prefix = f'49015420323{n:03d}'
        return next(prefix + str(d) for d in range(10) if valid_imei(prefix + str(d)))

    def test_conditions_duplicates_and_similar(self):
        for i, condition in enumerate(CONDITIONS):
            response = self.client.post('/inventario/nuevo', data={**self.fields, 'imei': self.imei(i), 'condition': condition, 'action': 'similar'})
            self.assertEqual(response.status_code, 302)
            page = self.client.get(response.location).get_data(as_text=True)
            self.assertNotIn('value="'+self.imei(i)+'"', page)
            self.assertIn('value="1070"', page)
        response = self.client.post('/inventario/nuevo', data={**self.fields, 'imei': self.imei(0), 'condition': 'Nuevo'})
        self.assertIn('ya está registrado', response.get_data(as_text=True))
        with self.app.app_context(), connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM equipment').fetchone()[0], len(CONDITIONS))

    def test_catalog_duplicate_validation(self):
        for name in ('17 pro max', 'IPHONE 17 PROMAX', 'apple iphone 17 pro max'):
            response = self.client.post('/inventario/catalogos?kind=reference', data={'csrf': self.csrf,'name': name,'active':'1','parent_id':self.brand,'confirm_similar':'1'})
            self.assertIn('Ya existe esta opción', response.get_data(as_text=True))

    def test_foreign_color_and_inactive(self):
        with self.app.app_context(), connection() as db:
            other = add_item(db, 'reference', 'Otro modelo', self.brand)
            color = add_item(db, 'color', 'Negro', other)
        response = self.client.post('/inventario/nuevo', data={**self.fields,'color_id':color,'imei':self.imei(0),'condition':'Usado'})
        self.assertIn('deben pertenecer', response.get_data(as_text=True))
        self.client.post('/inventario/catalogos?kind=reference',data={'csrf':self.csrf,'id':self.ref,'name':'Apple iPhone 17 Pro Max','active':'0'})
        response = self.client.post('/inventario/nuevo', data={**self.fields,'imei':self.imei(0),'condition':'Usado'})
        self.assertIn('opción activa',response.get_data(as_text=True))

    def test_pages_and_csrf(self):
        for path in ('/', '/inventario', '/inventario/nuevo', '/inventario/catalogos', '/inventario/catalogos?kind=color', '/inventario/catalogos?kind=capacity'):
            self.assertEqual(self.client.get(path).status_code,200)
        self.assertEqual(self.client.post('/inventario/catalogos',data={'name':'bad'}).status_code,400)

    def test_legacy_migration_idempotent(self):
        path = str(Path(self.temp.name) / 'old.sqlite')
        db = sqlite3.connect(path)
        db.execute('''CREATE TABLE equipment(id INTEGER PRIMARY KEY,imei TEXT UNIQUE,model TEXT,capacity INTEGER,color TEXT,condition TEXT,cost_cents INTEGER,location TEXT,supplier TEXT,status TEXT,created_at TEXT)''')
        db.execute("INSERT INTO equipment VALUES(1,'490154203237518','iPhone 17 pro max',256,'Azul','Nuevo',10050,'Bodega','Proveedor','Disponible','2026-09-07')")
        db.commit(); db.close()
        for _ in range(2):
            app = create_app({'TESTING':True,'DATABASE':path})
        with app.app_context(), connection() as db:
            row = db.execute('SELECT * FROM equipment').fetchone()
            self.assertEqual(row['cost_cents'],10050)
            self.assertEqual(row['imei'],'490154203237518')
            self.assertIsNotNone(row['reference_id'])
            self.assertGreaterEqual(db.execute('SELECT COUNT(*) FROM catalog').fetchone()[0],11)
            self.assertNotEqual(db.execute("SELECT parent_id FROM catalog WHERE kind='reference'").fetchone()[0],0)

if __name__ == '__main__':
    unittest.main()
