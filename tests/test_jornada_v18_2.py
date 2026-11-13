"""Reglas de apertura/cierre, pagos y clasificación. Casos de negocio, no solo HTML."""
import secrets,unittest
from decimal import Decimal
from sqlalchemy import event
from werkzeug.datastructures import MultiDict
import test_gestion_v16 as fixture
from app.extensions import db
from app.models.finanzas import Jornada,OperacionFinanciera as Op,AuditoriaFinanciera
from app.models.gestion import ComisionPool
from app.services import finanzas_service as f,sociedad_service as so
from app.services.calendario_co import day_info,holidays
from app.services.contabilidad_service import resumir_por_banco

class JornadaTests(unittest.TestCase):
    setUp=fixture.GestionTests.setUp
    tearDown=fixture.GestionTests.tearDown
    product=fixture.GestionTests.product
    sale=fixture.GestionTests.sale
    def client(self):
        c=self.app.test_client()
        with c.session_transaction() as session:session['csrf']='qa-v182'
        return c
    def payload(self,**kw):
        cfg=f.defaults('2026-10-12')
        out={k:str(v/100) for k,v in cfg.items() if k in ('normal_base','sandra_extra','extra_a','extra_b','normal_return','sandra_sunday','sandra_control_sunday','sandra_control_work','sandra_control_absent')}
        out.update(csrf='qa-v182',actor='ANA',reviewed='1',staff_name=['ANA'],staff_role=['Principal'],staff_salary=['25000'],staff_attended=['0'])
        out.update(kw);return fixture.data(**out)
    def test_open_requires_review_and_rolls_back_the_whole_creation(self):
        client=self.client()
        html=client.get('/finanzas?date=2026-10-12&tab=personal').get_data(as_text=True)
        self.assertIn('Confirmar personal y abrir jornada',html)
        self.assertIsNone(f.find_day('2026-10-12'))
        p=self.payload(action='open',date='2026-10-12',reviewed='')
        response=client.post('/finanzas',data=p)
        self.assertEqual(response.status_code,200);self.assertIsNone(f.find_day('2026-10-12'))
        self.assertEqual(client.post('/finanzas',data=self.payload(action='open',date='2026-10-12')).status_code,302)
        d=f.find_day('2026-10-12');self.assertTrue(d.config['reviewed']);self.assertTrue(d.config['holiday'])
        self.assertEqual(d.config['staff'][0]['salary'],2500000)
    def test_saving_config_requires_review_even_when_day_exists(self):
        before=dict(self.d.config)
        with self.assertRaisesRegex(ValueError,'confirmar'):f.save_config(self.d,self.payload(reviewed=''))
        self.assertEqual(self.d.config,before)
    def test_unreviewed_day_rejects_operation_on_server(self):
        self.d.config={**self.d.config,'reviewed':False};db.session.commit()
        r=self.client().post('/finanzas',data={'csrf':'qa-v182','date':self.day,'revision':self.d.revision,'action':'operation','kind':'Venta'})
        self.assertIn('Confirma primero',r.get_data(as_text=True));self.assertEqual(db.session.scalar(db.select(db.func.count(Op.id))),0)
    def test_close_blocks_salary_then_accepts_real_payment_without_second_expense(self):
        self.d.config={**self.d.config,'staff':[dict(name='ANA',role='Principal',salary=2500000,attended=True)]};db.session.commit()
        before=f.report(self.d)['totals']
        client=self.client()
        r=client.post('/finanzas',data={'csrf':'qa-v182','action':'close','date':self.day,'revision':self.d.revision,'counted':'0','reason':'PRUEBA','acknowledge':'1'})
        self.assertIn('No se puede cerrar',r.get_data(as_text=True));self.assertEqual(self.d.status,'Abierta')
        f.add_operation(self.d,fixture.data(kind='Pago sueldo',description='PAGO ANA',seller='ANA',amount='25000',token=secrets.token_hex(16),payment_account=['EFECTIVO'],payment_amount=['25000']))
        db.session.commit();after=f.report(self.d)['totals']
        self.assertEqual(after['owner_result'],before['owner_result']);self.assertEqual(after['cash_expected'],before['cash_expected']-2500000)
        self.assertFalse(f.closing_tasks(self.d,f.report(self.d)))
        r=client.post('/finanzas',data={'csrf':'qa-v182','action':'close','date':self.day,'revision':self.d.revision,'counted':'0','reason':'FALTANTE DOCUMENTADO','acknowledge':'1'})
        self.assertEqual(r.status_code,302);self.assertEqual(self.d.status,'Cerrada')
    def test_commission_payment_and_overpayment(self):
        self.sale(credit=False,amount='2000000',payment_amount=['2000000'])
        unit=f.report(self.d)['totals']['unit_commission'];self.assertGreater(unit,0)
        p=fixture.data(kind='Pago comisión',seller='ANA',description='COMISIÓN ANA',amount=str(unit/100),token=secrets.token_hex(16),payment_account=['EFECTIVO'],payment_amount=[str(unit/100)])
        before=f.report(self.d)['totals'];f.add_operation(self.d,p);db.session.commit()
        after=f.report(self.d)['totals'];self.assertEqual(before['profit'],after['profit']);self.assertEqual(before['cash_expected']-unit,after['cash_expected'])
        p['token']=secrets.token_hex(16)
        with self.assertRaises(ValueError):f.add_operation(self.d,p)
        self.assertTrue(any('LUZ' in t['label'] for t in f.closing_tasks(self.d,f.report(self.d))))
    def test_pool_delivery_reversal_keeps_history_and_real_cash(self):
        p=self.product(pool=True,cost=50000000);self.sale(p,credit=False)
        c=db.session.scalar(db.select(ComisionPool));before=f.report(self.d)['totals']
        self.assertTrue(any('POOL' in t['label'] for t in f.closing_tasks(self.d,f.report(self.d))))
        so.pay_pool_commission(fixture.data(commission_id=c.id,date=self.day,confirmed='1'));db.session.commit();payment=c.pago_operacion_id
        paid=f.report(self.d)['totals'];self.assertEqual(paid['cash_expected'],before['cash_expected']-c.monto)
        with self.assertRaises(ValueError):so.reverse_pool_commission(self.d,fixture.data(commission_id=c.id,reason='PRUEBA'))
        so.reverse_pool_commission(self.d,fixture.data(commission_id=c.id,reason='DINERO REINTEGRADO',returned='1'));db.session.commit()
        self.assertTrue(db.session.get(Op,payment).voided);self.assertIsNone(c.pago_operacion_id)
        self.assertEqual(f.report(self.d)['totals']['cash_expected'],before['cash_expected'])
        self.assertEqual(f.report(self.d)['totals']['profit'],before['profit'])
        self.assertTrue(db.session.scalar(db.select(AuditoriaFinanciera.id).where(AuditoriaFinanciera.action=='Anular entrega de comisión POOL')))
    def test_dataphone_classification_does_not_guess_bank_or_duplicate_totals(self):
        self.sale(credit=False,amount='63000',payment_account=['DATÁFONO'],payment_amount=['63000'])
        result=resumir_por_banco([self.person],int(self.day[:4]))[self.person.id]
        rows=result['bancos'];self.assertEqual(result['total'],Decimal('63000'))
        card=next(b for b in rows if b['nombre'].upper() in ('DATÁFONO','DATAFONO'))
        self.assertEqual(card['total'],Decimal('63000'));self.assertEqual(card['cantidad'],1)
        self.assertFalse(any(b['nombre']=='Ingresos sin banco asociado' and b['total'] for b in rows))
        self.assertEqual(f.display_account('DATÁFONO'),'DATÁFONO')
    def test_staff_payments_are_available_and_no_global_search_in_finance(self):
        self.d.config={**self.d.config,'staff':[dict(name='ANA',role='Principal',salary=2500000,attended=True)]};db.session.commit()
        html=self.app.test_client().get('/finanzas?date='+self.day+'&tab=personal').get_data(as_text=True)
        self.assertIn('Pagar sueldos y comisiones',html);self.assertIn('Pagar a ANA',html);self.assertNotIn('id="quick-imei"',html)
    def test_calendar_2026_observed_holidays_and_sunday(self):
        for day in ['2026-01-12','2026-04-02','2026-04-03','2026-05-18','2026-06-08','2026-06-15','2026-07-13','2026-10-12','2026-11-16']:self.assertTrue(day_info(day)['holiday'],day)
        self.assertFalse(day_info('2026-11-11')['special']);self.assertTrue(day_info('2026-11-08')['sunday'])
        self.assertEqual(len(holidays(2026)),19)
    def test_close_review_links_reach_the_actual_payment_section(self):
        self.d.config={**self.d.config,'staff':[dict(name='ANA',role='Principal',salary=2500000,attended=True)]};db.session.commit()
        html=self.app.test_client().get('/finanzas?date='+self.day+'&tab=cierre').get_data(as_text=True)
        self.assertIn('tab=personal#pagos-personal',html);self.assertIn('Pendientes que impiden cerrar',html)
    def test_provider_balance_blocks_close_until_payment(self):
        op=self.sale(credit=False,amount='100000',payment_amount=['100000'],cost_type=['Proveedor'],cost_name=['OTROS'],cost_detail=['ACCESORIO'],cost_category=['Accesorios'],cost_qty=['1'],cost_unit=['10000'])
        self.assertTrue(any('Pagar proveedor' in t['label'] for t in f.closing_tasks(self.d,f.report(self.d))))
        before=f.report(self.d)['totals']
        f.pay_supplier(self.d,fixture.data(operation_id=op.id,cost_index=0,amount='10000',account='EFECTIVO',token=secrets.token_hex(16),reason='PAGO REAL'));db.session.commit()
        after=f.report(self.d)['totals'];self.assertFalse(f.closing_tasks(self.d,f.report(self.d)))
        self.assertEqual(before['profit'],after['profit']);self.assertEqual(before['cash_expected']-1000000,after['cash_expected'])
    def test_salary_button_posts_a_real_payment(self):
        self.d.config={**self.d.config,'staff':[dict(name='ANA',role='Principal',salary=2500000,attended=True)]};db.session.commit()
        client=self.client();r=client.post('/finanzas',data=dict(csrf='qa-v182',date=self.day,action='staff_payment',revision=self.d.revision,kind='Pago sueldo',seller='ANA',description='PAGO ANA',amount='25000',token=secrets.token_hex(16),payment_account='EFECTIVO',payment_amount='25000'))
        self.assertEqual(r.status_code,302);self.assertEqual(f.report(self.d)['totals']['salary_due'],0)
    def test_query_count_does_not_grow_per_drink_cost(self):
        for i in range(30):db.session.add(Op(day_id=self.d.id,token=secrets.token_hex(16),kind='Venta',description='BEBIDAS',seller='ANA',amount=100000,minor_cost=0,costs=[dict(type='Bebida',name='AGUA',quantity=1,unit=10000,amount=10000)],payments=[]))
        db.session.commit();queries=[]
        def record(*args):queries.append(1)
        event.listen(db.engine,'before_cursor_execute',record)
        try:r=f.report(self.d)
        finally:event.remove(db.engine,'before_cursor_execute',record)
        self.assertEqual(r['drinks']['AGUA']['cost'],300000)
        self.assertLess(len(queries),20)
