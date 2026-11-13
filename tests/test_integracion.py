from jornada_fixtures import opening
"""Casos de caja, pagos mixtos, auditoría y control contable."""
from _cleanup import release
import secrets
import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.extensions import db
from app.models import PersonaContable, BancoDestino, PersonaBanco, ConsignacionBancaria, HistorialConsignacion, Producto
from app.services import finanzas_service as finance


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=create_app({'TESTING':True,'DATABASE':str(Path(self.tmp.name)/'data.sqlite'),'SECRET_KEY':'tests'})
        self.client=self.app.test_client()
        self.day='2026-10-01'
        self.client.get('/finanzas?date='+self.day)
        with self.client.session_transaction() as session:self.csrf=session['csrf']
        self.post('open',**opening(self.day,('ANA',)))
        with self.app.app_context():
            db.session.add_all([PersonaContable(nombre='EMILY',identificacion='889',tipo='Natural'),BancoDestino(nombre='BANCO TEST')]);db.session.commit()
            self.bank_person_id=db.session.scalar(db.select(PersonaContable.id));self.bank_id=db.session.scalar(db.select(BancoDestino.id))
            db.session.add(PersonaBanco(persona_id=self.bank_person_id,banco_id=self.bank_id));db.session.commit()

    def tearDown(self):release(self.app);self.tmp.cleanup()

    def post(self, action, **values):
        with self.app.app_context():
            day=finance.find_day(self.day)
            revision=day.revision if day else 0
        data=dict(csrf=self.csrf,date=self.day,revision=str(revision),token=secrets.token_hex(16),action=action)
        data.update(values)
        return self.client.post('/finanzas',data=data)

    def test_mixed_cash_split_edit_and_contribution(self):
        self.assertEqual(self.post('operation',kind='Venta',description='VENTA MIXTA',seller='ANA',amount='700000',
            payment_account=['EFECTIVO','DATÁFONO'],payment_amount=['500000','210000'],payment_person_id=['',str(self.bank_person_id)],payment_bank_id=['',str(self.bank_id)],
            cost_name=['CP VARIOS'],cost_type=['Fondo'],cost_qty=['1'],cost_unit=['580000'],minor_cost='0').status_code,302)
        from app.models.finanzas import OperacionFinanciera, AuditoriaFinanciera
        with self.app.app_context():
            day=finance.find_day(self.day);r=finance.report(day)
            split=r['allocations'][0]['parts']
            self.assertEqual([(p['profit'],p['cost']) for p in split],[(12000000,38000000),(0,20000000)])
            self.assertEqual(r['totals']['cash_to_deliver'],50000000)
            op=db.session.scalar(db.select(OperacionFinanciera))
            oid=op.id
        response=self.post('edit_operation',operation_id=str(oid),kind='Venta',description='VENTA MIXTA CORREGIDA',
            seller='ANA',amount='700000',minor_cost='0',payment_account=['EFECTIVO','DATÁFONO'],
            payment_amount=['500000','210000'],payment_person_id=['',str(self.bank_person_id)],payment_bank_id=['',str(self.bank_id)],cost_name=['CP VARIOS'],cost_type=['Fondo'],cost_qty=['1'],
            cost_unit=['580000'],reason='CORREGIR NOMBRE')
        self.assertEqual(response.status_code,302)
        with self.app.app_context():
            self.assertTrue(db.session.scalar(db.select(AuditoriaFinanciera.id).where(AuditoriaFinanciera.action=='Edición de movimiento')))
        self.assertEqual(self.post('operation',kind='Salida caja',description='PAGO PROVEEDOR',seller='ANA',
            amount='600000',payment_account=['EFECTIVO'],payment_amount=['600000']).status_code,302)
        with self.app.app_context():self.assertEqual(finance.report(finance.find_day(self.day))['totals']['base_shortfall'],10000000)
        self.assertEqual(self.post('contribution',administrator='ADMINISTRADOR',amount='100000',reason='REPOSICIÓN BASE').status_code,302)
        with self.app.app_context():self.assertEqual(finance.report(finance.find_day(self.day))['totals']['base_shortfall'],0)

    def test_accounting_history_does_not_touch_sales(self):
        self.client.post('/modulos/tributario/crear-destinatario',data=dict(csrf=self.csrf,nombre='ANA',identificacion='123',tipo='Natural',declaro_renta_antes='1'))
        self.client.post('/modulos/tributario/crear-banco',data=dict(csrf=self.csrf,nombre_banco='BANCO'))
        with self.app.app_context():
            person=db.session.scalar(db.select(PersonaContable).where(PersonaContable.identificacion=='123'));bank=db.session.get(BancoDestino,self.bank_id)
            person_id=person.id;bank_id=bank.id
            self.assertTrue(person.declaro_renta_antes)
        self.assertEqual(self.client.post('/modulos/tributario/persona/bancos',data=dict(csrf=self.csrf,persona_id=person_id,banco_id=bank_id)).status_code,302)
        self.assertEqual(self.client.post('/modulos/tributario/consignacion/nueva',data=dict(csrf=self.csrf,persona_id=person_id,
            banco_id=bank_id,fecha='2026-10-01',monto='1000.00',referencia='UNO')).status_code,302)
        with self.app.app_context():cid=db.session.scalar(db.select(ConsignacionBancaria.id))
        self.assertEqual(self.client.post(f'/modulos/tributario/consignacion/{cid}/editar',data=dict(csrf=self.csrf,
            persona_id=person_id,banco_id=bank_id,fecha='2026-10-02',monto='1500.00',referencia='DOS',motivo='CORRECCIÓN BANCO')).status_code,302)
        with self.app.app_context():
            c=db.session.get(ConsignacionBancaria,cid)
            self.assertEqual(str(c.monto),'1500.00')
            self.assertEqual(db.session.scalar(db.select(db.func.count(HistorialConsignacion.id))),2)
        self.assertEqual(self.client.get('/modulos/tributario/').status_code,200)

    def test_salaries_required_and_paid_only_when_recorded(self):
        cfg=finance.defaults(self.day)
        amounts={key:str(cfg[key]/100) for key in ('normal_base','sandra_extra','extra_a','extra_b','normal_return',
            'sandra_sunday','sandra_control_sunday','sandra_control_work','sandra_control_absent')}
        response=self.post('config',actor='ADMIN',reviewed='1',staff_name=['ANA'],staff_role=['Principal'],
            staff_salary=['80000'],staff_attended=['0'],accounts='EFECTIVO',**amounts)
        self.assertEqual(response.status_code,302)
        with self.app.app_context():
            d=finance.find_day(self.day);t=finance.report(d)['totals']
            self.assertEqual(t['salary_due'],8000000)
            self.assertEqual(t['cash_expected'],finance.BASE_CAJA)
        self.assertEqual(self.post('operation',kind='Pago sueldo',description='SUELDO ANA',seller='ANA',
            amount='80000',payment_account=['EFECTIVO'],payment_amount=['80000']).status_code,302)
        with self.app.app_context():
            t=finance.report(finance.find_day(self.day))['totals']
            self.assertEqual(t['salary_due'],0)
            self.assertEqual(t['base_shortfall'],8000000)

    def test_sale_updates_inventory_finance_person_and_audit(self):
        from app.models.finanzas import OperacionFinanciera, AuditoriaFinanciera
        today=finance.today()
        with self.app.app_context():
            day=finance.open_day(today)
            person=PersonaContable(nombre='CLIENTE',identificacion='998',tipo='Natural')
            p=Producto(imei='490154203237518',model='IPHONE',capacity=128,color='AZUL',condition='Nuevo',
                cost_cents=50000000,location='BODEGA',supplier='CP',status='Disponible')
            db.session.add_all([p,person]);db.session.commit()
            pid=p.id;person_id=person.id;revision=p.revision
        result=self.client.post(f'/ventas/{pid}',data=dict(csrf=self.csrf,revision=revision,action='sell',
            reason='VENTA CONFIRMADA',sale_value='700000',seller='ANA',responsible='CLIENTE',person_id=person_id))
        self.assertEqual(result.status_code,302,result.get_data(as_text=True)[-1000:])
        with self.app.app_context():
            p=db.session.get(Producto,pid);self.assertEqual(p.status,'Vendido')
            o=db.session.scalar(db.select(OperacionFinanciera).where(OperacionFinanciera.product_id==pid))
            self.assertIsNotNone(o);self.assertEqual(o.person_id,person_id)
            revision=p.revision
        result=self.client.post(f'/ventas/{pid}',data=dict(csrf=self.csrf,revision=revision,action='edit_sale',
            reason='CORRECCIÓN PRECIO',sale_value='720000',seller='ANA',responsible='CLIENTE',person_id=person_id))
        self.assertEqual(result.status_code,302,result.get_data(as_text=True)[-1000:])
        with self.app.app_context():
            self.assertEqual(db.session.get(Producto,pid).sale_value_cents,72000000)
            self.assertEqual(db.session.scalar(db.select(OperacionFinanciera).where(OperacionFinanciera.product_id==pid)).amount,72000000)
            self.assertTrue(db.session.scalar(db.select(AuditoriaFinanciera.id).where(AuditoriaFinanciera.action=='Corrección de venta MOD03')))


if __name__=='__main__':unittest.main()
