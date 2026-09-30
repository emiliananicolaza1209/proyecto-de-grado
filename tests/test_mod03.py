import unittest
import test_actions
from app.extensions import db
from app.models import Producto, Cobro, Recepcion
from app.services.pago_service import summary


class MoneyTests(unittest.TestCase):
    setUp = test_actions.ActionsTests.setUp
    tearDown = test_actions.ActionsTests.tearDown
    imei = test_actions.ActionsTests.imei
    prepare = test_actions.ActionsTests.prepare

    def start(self):
        self.pid, _ = self.prepare()
        self.send('sell', sale_value='3000', responsible='CLIENTE', seller='ANA')

    def send(self, action, expected=302, admin=False, **extra):
        with self.app.app_context():
            revision = db.session.get(Producto,self.pid).revision
        data = dict(csrf=self.csrf, revision=str(revision), action=action,
                    reason='Prueba del registro', method='Efectivo',
                    destination='Vendedora', collector='ANA', administrator='MARIA')
        data.update(extra)
        path = f'/ventas/recepciones/{self.pid}' if admin else f'/ventas/{self.pid}'
        response = self.client.post(path,data=data)
        self.assertEqual(response.status_code,expected,response.get_data(as_text=True))

    def totals(self):
        with self.app.app_context():
            p=db.session.get(Producto,self.pid)
            s=summary(p)
            return p.paid_cents, s['received'], s['seller_pending'], s['direct_pending']

    def cid(self):
        with self.app.app_context():
            return db.session.scalar(db.select(Cobro.id).where(Cobro.product_id==self.pid).order_by(Cobro.id.desc()))

    def test_partial_receipts_do_not_double_customer_payment(self):
        self.start()
        self.send('payment',amount='3000')
        cid=self.cid()
        self.send('receive',admin=True,collection_id=cid,amount='2000')
        self.assertEqual(self.totals(),(300000,200000,100000,0))
        self.send('receive',200,admin=True,collection_id=cid,amount='1001')
        self.assertEqual(self.totals(),(300000,200000,100000,0))
        self.send('receive',admin=True,collection_id=cid,amount='1000')
        self.assertEqual(self.totals(),(300000,300000,0,0))
        self.send('receive',200,admin=True,collection_id=cid,amount='1')
        for path in ['/ventas','/ventas/recepciones',f'/ventas/{self.pid}',f'/ventas/recepciones/{self.pid}']:
            self.assertEqual(self.client.get(path).status_code,200)

    def test_direct_payment_and_void_order(self):
        self.start()
        self.send('payment',amount='800',destination='Negocio')
        cid=self.cid()
        self.assertEqual(self.totals(),(80000,0,0,80000))
        self.send('receive',admin=True,collection_id=cid,amount='800')
        self.send('void_collection',200,record_id=cid)
        with self.app.app_context(): rid=db.session.scalar(db.select(Recepcion.id))
        self.send('void_receipt',admin=True,record_id=rid)
        self.send('void_collection',record_id=cid)
        self.assertEqual(self.totals(),(0,0,0,0))
        self.send('void_collection',200,record_id=cid)

    def test_invalid_payments_and_stale_revision(self):
        self.start()
        for extra in [dict(amount='3001'),dict(amount='0'),dict(amount='NaN'),dict(amount='10',collector=''),dict(amount='10',method='Transferencia',reference='')]:
            self.send('payment',200,**extra)
            self.assertEqual(self.totals(),(0,0,0,0))
        with self.app.app_context(): old=db.session.get(Producto,self.pid).revision
        self.send('payment',amount='10')
        self.send('payment',200,amount='10',revision=str(old))
        self.send('receive',200,admin=True,collection_id='9999',amount='10')
        self.send('payment',200,admin=True,amount='10')
        self.assertEqual(self.totals(),(1000,0,1000,0))

    def test_legacy_cobro_is_not_administrative_receipt(self):
        self.start()
        with self.app.app_context():
            p=db.session.get(Producto,self.pid)
            p.paid_cents=10000
            p.payment_status='Parcial'
            db.session.add(Cobro(product_id=p.id,amount_cents=10000,destination='Por verificar',collector='SIN IDENTIFICAR',method='Por verificar',reference='',effective_date='2026-01-01',note='Pago anterior',legacy=True))
            db.session.commit()
            self.assertEqual(summary(p)['unknown'],10000)
        self.send('receive',200,admin=True,collection_id=self.cid(),amount='100')
        self.assertEqual(self.totals(),(10000,0,0,0))
