"""Validación de fuentes reales del panel; no utiliza datos del prototipo visual."""
import unittest
from datetime import date, timedelta
from unittest.mock import patch
from app.extensions import db
from app.models import Cobro, Recepcion, Producto
from app.models.finanzas import Jornada
from app.models.gestion import CreditoVenta, Usuario
from app.services import dashboard_service as dashboard, pago_service as payments, finanzas_service as finance
from app.services.operacion_service import operate
import test_gestion_v16 as fixtures


class DashboardTests(unittest.TestCase):
    setUp = fixtures.GestionTests.setUp
    tearDown = fixtures.GestionTests.tearDown
    product = fixtures.GestionTests.product
    sale = fixtures.GestionTests.sale
    settlement = fixtures.GestionTests.settlement

    def report(self, **kwargs):
        return dashboard.summary(dict(desde=self.day, hasta=self.day, **kwargs), financial=True)

    def test_linked_sale_and_administration_receipt_are_not_double_income(self):
        p = self.product(); self.sale(p, credit=False)
        c = db.session.scalar(db.select(Cobro).where(Cobro.product_id == p.id))
        payments.receive(p.id, fixtures.data(revision=p.revision, collection_id=c.id,
            amount='650000', administrator='ADMIN', method='Efectivo', reason='Recepción real', movement_date=self.day))
        r = self.report()
        self.assertEqual((r['sales'], r['collections']), (65000000, 65000000))
        self.assertEqual(sum(m['amount'] for m in r['methods']), r['collections'])
        self.assertEqual(db.session.query(Recepcion).count(), 1)

    def test_card_sales_exclude_surcharge_but_actual_collection_includes_it(self):
        p = self.product(cost=5000000)
        self.sale(p, credit=False, amount='105000', payment_account=['DATÁFONO'], payment_amount=['105000'])
        r = self.report()
        self.assertEqual((r['sales'], r['collections']), (10000000, 10500000))
        self.assertEqual(db.session.scalar(db.select(Cobro.amount_cents)), 10000000)

    def test_grouped_credit_is_counted_once_when_disbursed(self):
        self.sale(self.product())
        self.sale(self.product(imei='490154203237526'))
        credits = db.session.scalars(db.select(CreditoVenta)).all()
        self.assertEqual(self.report()['collections'], 0)
        self.settlement(credits[0], 106600000, credit_id=[c.id for c in credits], allocation=['533000','533000'])
        r = self.report()
        self.assertEqual((r['sales'], r['collections']), (106600000, 106600000))
        self.assertEqual([(m['name'],m['amount']) for m in r['methods']], [('Desembolso de aliado', 106600000)])
        self.assertEqual(db.session.query(Cobro).count(), 2)

    def test_manual_abonos_of_integrated_sale_and_reference_are_kept(self):
        p = self.product()
        operate(p.id, 'sell', fixtures.data(revision=p.revision, responsible='LOCAL', seller='ANA',
            sale_value='650000', reason='Venta de prueba', movement_date=self.day))
        # Confirmar venta ya crea su operación financiera sin cobrar al cliente.
        self.assertEqual(self.report()['sales'],65000000)
        for method, reference in [('Efectivo',''),('Transferencia','CREDITO referencia del cliente')]:
            payments.collect(p.id, fixtures.data(revision=p.revision, reason='Abono del cliente',
                movement_date=self.day, amount='200000', method=method, reference=reference,
                destination='Negocio'))
        r = self.report()
        self.assertEqual((r['sales'],r['collections'],r['outstanding']), (65000000,40000000,25000000))
        self.assertEqual(len(r['methods']),2)

    def test_voided_and_legacy_collections_are_excluded(self):
        p = self.product()
        for flags in (dict(legacy=True),dict(voided=True)):
            db.session.add(Cobro(product_id=p.id, amount_cents=99999999, destination='Negocio',
                collector='PRUEBA',method='Efectivo',effective_date=self.day,note='Dato anterior',**flags))
        db.session.commit()
        self.assertEqual(self.report()['collections'],0)

    def test_unincorporated_sale_is_explicitly_partial_and_inventory_is_current(self):
        p = self.product()
        # Registro histórico anterior a la incorporación automática: es un
        # caso soportado por la migración, no una venta nueva del controlador.
        p.status='Vendido';p.sale_date=self.day;p.sale_value_cents=65000000
        p.payment_status='Pendiente';db.session.commit()
        r = self.report()
        self.assertEqual((r['missing'],r['sales']), (1,0))
        self.assertTrue(any('parcial' in w for w in r['warnings']))
        self.assertEqual(r['states'][0]['name'], 'Vendido')

    def test_read_only_zero_range_does_not_create_days(self):
        before = db.session.query(Jornada).count()
        r = dashboard.summary({'desde':'2020-01-01','hasta':'2020-01-03'},financial=True)
        self.assertEqual((r['sales'],r['collections']), (0,0))
        self.assertEqual(len(r['chart']['days']),3)
        self.assertEqual(db.session.query(Jornada).count(), before)

    def test_invalid_period_is_400_and_health_is_anonymous(self):
        client = self.app.test_client()
        for args in ('desde=2026-10-02&hasta=2026-10-01', 'desde=2020-01-01&hasta=2026-01-01',
                     'desde=bad&hasta=bad'):
            self.assertEqual(client.get('/?'+args).status_code,400)
        self.app.config['AUTH_REQUIRED']=True
        self.assertEqual(client.get('/healthz').json, {'status':'ok'})
        self.assertEqual(client.get('/').status_code,302)

    def test_operational_role_gets_no_aggregate_money_in_html_or_json(self):
        self.sale(credit=False, amount='1234567', payment_amount=['1234567'])
        u=Usuario(nombre='PRUEBA',login='inventario',password_hash='unused',rol='Inventario')
        db.session.add(u);db.session.commit();self.app.config['AUTH_REQUIRED']=True
        client=self.app.test_client()
        with client.session_transaction() as s:s['usuario_id']=u.id;s['usuario_version']=u.session_version
        response=client.get('/',query_string={'desde':self.day,'hasta':self.day})
        self.assertEqual(response.status_code,200)
        self.assertNotIn(b'123456700',response.data)
        self.assertNotIn(b'Ventas netas registradas',response.data)
        self.assertNotIn(b'Cobros por medio de pago',response.data)
        self.assertIn(b'"financial": false',response.data)
        self.assertEqual(client.get('/reportes?tipo=finanzas').status_code,403)


if __name__=='__main__':unittest.main()
