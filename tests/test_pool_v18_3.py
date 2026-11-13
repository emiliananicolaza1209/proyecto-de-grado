"""Origen del gasto, entrega real y fuente del dinero: bases aisladas."""
import copy,secrets,unittest
from sqlalchemy import event
import test_gestion_v16 as fixture
from app.extensions import db
from app.models import PersonaContable
from app.models.contabilidad import PersonaBanco
from app.models.finanzas import Jornada,OperacionFinanciera as Op
from app.models.gestion import ComisionPool,CompraPool
from app.services import finanzas_service as f,sociedad_service as so
from app.services.pool_jornada import context

class PoolDatesTests(unittest.TestCase):
    setUp=fixture.GestionTests.setUp
    tearDown=fixture.GestionTests.tearDown
    product=fixture.GestionTests.product
    sale=fixture.GestionTests.sale
    def past_sale(self):
        self.d.date=self.day='2026-10-01';db.session.commit()
        op=self.sale(self.product(pool=True),credit=False)
        c=db.session.scalar(db.select(ComisionPool))
        current=Jornada(date='2026-10-12',config=copy.deepcopy(self.d.config));db.session.add(current);db.session.commit()
        return op,c,current
    def delivery(self,c,d,**kw):
        values=dict(commission_id=c.id,date=d.date,confirmed='1');values.update(kw)
        so.pay_pool_commission(fixture.data(**values));db.session.commit()
        return db.session.get(Op,c.pago_operacion_id)
    def client(self):
        client=self.app.test_client()
        with client.session_transaction() as s:s['csrf']='v183'
        return client
    def test_historical_pending_does_not_block_current_close_or_move_the_expense(self):
        op,c,current=self.past_sale()
        self.assertEqual(f.report(self.d)['totals']['debe'],13000000)
        self.assertEqual(f.report(self.d)['totals']['pool_extra_commission'],2000000)
        self.assertEqual(f.report(current)['totals']['pool_extra_commission'],0)
        self.assertTrue(any('POOL' in x['label'] for x in f.closing_tasks(self.d,f.report(self.d))))
        self.assertFalse(f.closing_tasks(current,f.report(current)))
        response=self.client().post('/finanzas',data=dict(csrf='v183',date=current.date,revision=current.revision,action='close',counted='0',acknowledge='1'))
        self.assertEqual(response.status_code,302);self.assertEqual(current.status,'Cerrada')
        self.assertIsNone(c.pago_operacion_id);self.assertEqual(len(context(current.date,False)['commissions']),1)
    def test_late_till_payment_changes_only_cash_on_delivery_date_once(self):
        op,c,current=self.past_sale();before=f.report(self.d)['totals'];cash=f.report(current)['totals']['cash_expected']
        payment=self.delivery(c,current,payment_source='EFECTIVO')
        self.assertEqual(payment.day_id,current.id)
        self.assertEqual(context(self.d.date,False)['commissions'][0][2],current.date)
        self.assertEqual(f.report(self.d)['totals']['debe'],before['debe'])
        self.assertEqual(f.report(self.d)['totals']['cash_expected'],before['cash_expected'])
        self.assertEqual(f.report(current)['totals']['cash_expected'],cash-c.monto)
        self.assertEqual(f.report(current)['totals']['debe'],0)
        with self.assertRaises(ValueError):self.delivery(c,current)
        self.assertEqual(f.report(current)['totals']['cash_expected'],cash-c.monto)
    def test_admin_direct_payment_preserves_cash_and_bank_income(self):
        op,c,current=self.past_sale();before=f.report(current)['totals']
        payment=self.delivery(c,current,payment_source='ADMINISTRACIÓN DIRECTA',reference='JONATAN PAGÓ AL PERSONAL')
        after=f.report(current)['totals']
        for key in ('cash_expected','bank_received','debe'):self.assertEqual(after[key],before[key])
        self.assertEqual(payment.payments[0]['account'],'ADMINISTRACIÓN DIRECTA')
        html=self.client().get('/finanzas?date='+current.date+'&tab=proveedores').get_data(as_text=True)
        self.assertIn('Pago directo de administración',html);self.assertIn('2026-10-01',html);self.assertIn('2026-10-12',html)
    def test_admin_delivery_requires_reference_and_valid_source(self):
        op,c,current=self.past_sale()
        for source in ('ADMINISTRACIÓN DIRECTA','BANCO INVENTADO'):
            with self.assertRaises(ValueError):self.delivery(c,current,payment_source=source)
            self.assertIsNone(c.pago_operacion_id)
        self.assertEqual(db.session.scalar(db.select(db.func.count(Op.id))),1)
    def test_reversal_preserves_closed_origin_and_restores_cash_only_once(self):
        op,c,current=self.past_sale();self.d.snapshot={'totals':f.report(self.d)['totals'],'config':copy.deepcopy(self.d.config)}
        self.d.status='Cerrada';db.session.commit();snapshot=copy.deepcopy(self.d.snapshot)
        payment=self.delivery(c,current);before=f.report(current)['totals']['cash_expected']
        so.reverse_pool_commission(current,fixture.data(commission_id=c.id,returned='1',reason='DINERO DEVUELTO'));db.session.commit()
        self.assertEqual(f.report(current)['totals']['cash_expected'],before+c.monto)
        self.assertEqual(self.d.snapshot,snapshot);self.assertEqual(self.d.status,'Cerrada');self.assertTrue(payment.voided)
        with self.assertRaises(ValueError):so.reverse_pool_commission(current,fixture.data(commission_id=c.id,returned='1',reason='NO DUPLICAR'))
    def test_admin_reversal_cannot_create_till_money(self):
        op,c,current=self.past_sale();before=f.report(current)['totals']['cash_expected']
        self.delivery(c,current,payment_source='ADMINISTRACIÓN DIRECTA',reference='PAGO ADMIN')
        so.reverse_pool_commission(current,fixture.data(commission_id=c.id,returned='1',reason='DEVUELTO A ADMIN'));db.session.commit()
        self.assertEqual(f.report(current)['totals']['cash_expected'],before)
    def test_purchase_commission_is_equipment_cost_and_requires_admin_funding(self):
        p=self.product(pool=True);p.additional_costs=[dict(name='COMISIÓN DE COMPRA',amount_cents=2000000)];p.cost_cents+=2000000;db.session.commit()
        with self.assertRaisesRegex(ValueError,'cubrir compra'):so.register_purchase(p,fixture.data(date=self.day,funding='500000',confirmed='1'))
        self.assertIsNone(db.session.get(CompraPool,p.id))
        buy=so.register_purchase(p,fixture.data(date=self.day,funding='620000',confirmed='1'));db.session.commit()
        self.assertEqual((buy.pago_cliente,buy.costos_pagados,buy.ganancia),(50000000,2000000,10000000))
        self.assertEqual(so.capital_basis(p),62000000)
        self.sale(p,credit=False,amount='800000',payment_amount=['800000'],cost_unit=['620000'])
        self.assertEqual(f.report(self.d)['totals']['debe'],26000000)
    def salary(self):
        self.d.config={**self.d.config,'staff':[dict(name='ANA',role='Principal',salary=2500000,attended=True),dict(name='LUZ',role='Secundaria',salary=1500000,attended=True)]};db.session.commit()
    def test_compact_payment_one_amount_server_derives_kind_recipient_and_distribution(self):
        self.salary();client=self.client();html=client.get('/finanzas?date='+self.day+'&tab=personal').get_data(as_text=True)
        self.assertEqual(html.count('id="pago-personal-form"'),1)
        panel=html.split('id="pagos-personal"',1)[1].split('</section>',1)[0]
        self.assertNotIn('name="payment_amount"',panel);self.assertNotIn('Quitar medio',panel)
        params=dict(csrf='v183',date=self.day,revision=self.d.revision,action='staff_payment',staff_choice='Pago sueldo|ANA',amount='25000',payment_account='EFECTIVO',token=secrets.token_hex(16),kind='Entrada caja',seller='LUZ',payment_amount='999999')
        response=client.post('/finanzas',data=params);self.assertEqual(response.status_code,302)
        op=db.session.scalar(db.select(Op));self.assertEqual((op.kind,op.seller,op.amount),('Pago sueldo','ANA',2500000))
        self.assertEqual(op.payments[0]['amount'],2500000);self.assertEqual(f.report(self.d)['totals']['salary_due'],1500000)
    def test_compact_payment_checks_balance_and_transfer_destination(self):
        self.salary()
        for amount,account in [('25001','EFECTIVO'),('25000','TRANSFERENCIA')]:
            with self.assertRaises(ValueError):f.pay_staff(self.d,fixture.data(staff_choice='Pago sueldo|ANA',amount=amount,payment_account=account,token=secrets.token_hex(16)))
        self.assertEqual(db.session.scalar(db.select(db.func.count(Op.id))),0)
    def test_personal_bank_queries_do_not_grow_per_holder(self):
        def measured():
            db.session.expire_all();queries=[]
            def record(*args):queries.append(1)
            event.listen(db.engine,'before_cursor_execute',record)
            try:self.assertEqual(self.app.test_client().get('/finanzas?date='+self.day+'&tab=personal').status_code,200)
            finally:event.remove(db.engine,'before_cursor_execute',record)
            return len(queries)
        baseline=measured()
        for i in range(30):
            person=PersonaContable(nombre='PERSONA '+str(i),identificacion='V183-'+str(i),tipo='Natural');db.session.add(person);db.session.flush();db.session.add(PersonaBanco(persona_id=person.id,banco_id=self.bank.id))
        db.session.commit();self.assertLessEqual(measured(),baseline+1)

    def test_movement_catalog_queries_do_not_grow_per_equipment(self):
        def measured():
            db.session.expire_all();queries=[]
            def record(*args):queries.append(1)
            event.listen(db.engine,'before_cursor_execute',record)
            try:self.assertEqual(self.app.test_client().get('/finanzas?date='+self.day+'&tab=movimientos').status_code,200)
            finally:event.remove(db.engine,'before_cursor_execute',record)
            return len(queries)
        baseline=measured()
        for i in range(25):self.product(pool=i%2==0,imei='8901542032'+str(i).zfill(5))
        self.assertLessEqual(measured(),baseline+1)
