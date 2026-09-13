import unittest
from decimal import Decimal
import test_catalogs
from app.services.costo_service import purchase_cost
from test_catalogs import connection

class CostTests(unittest.TestCase):
    def test_excel_and_rounding(self):
        for usd, rate, shipping, expected in [('1070','3245','175000','3647150.00'),('1180','3245','175000','4004100.00'),('980','3245','130000','3310100.00'),('0.01','0.50','0','0.01')]:
            _, subtotal, total = purchase_cost(dict(purchase_usd=usd,exchange_rate=rate,shipping_cop=shipping))
            self.assertEqual(total,Decimal(expected))
    def test_invalid_values(self):
        base = dict(purchase_usd='1070',exchange_rate='3245',shipping_cop='0')
        for key,value in [('purchase_usd',''),('purchase_usd','NaN'),('exchange_rate','0'),('shipping_cop','-1'),('shipping_cop','1.001'),('purchase_usd','1000000')]:
            with self.assertRaises(ValueError): purchase_cost({**base,key:value})

class StoredCostTests(unittest.TestCase):
    setUp = test_catalogs.CatalogTests.setUp
    tearDown = test_catalogs.CatalogTests.tearDown
    imei = test_catalogs.CatalogTests.imei
    def test_server_ignores_submitted_total(self):
        self.client.post('/inventario/nuevo',data={**self.fields,'imei':self.imei(7),'condition':'Open box','cost':'1','cost_cents':'1'})
        with self.app.app_context(),connection() as db:
            row=db.execute('SELECT * FROM equipment').fetchone()
            self.assertEqual(row['cost_cents'],364715000)
            self.assertEqual(row['subtotal_cents'],347215000)
            self.assertEqual(row['shipping_cents'],17500000)
            self.assertEqual(row['exchange_rate'],'3245')
