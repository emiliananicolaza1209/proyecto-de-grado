"""Retomas y conciliación bancaria entre Finanzas y Contabilidad."""
from _cleanup import release
import secrets
import unittest
from decimal import Decimal
from werkzeug.datastructures import MultiDict

from app.extensions import db
from app.models import Producto, PersonaContable, BancoDestino, PersonaBanco, ConsignacionBancaria, Catalogo
from app.models.finanzas import OperacionFinanciera
from app.services import finanzas_service as finance
from app.services.contabilidad_service import evaluar_estado_renta
import test_catalogs


class PoolTests(unittest.TestCase):
    setUp=test_catalogs.CatalogTests.setUp
    tearDown=test_catalogs.CatalogTests.tearDown
    imei=test_catalogs.CatalogTests.imei

    def test_retoma_costos_pool_sin_lote_y_sin_usd(self):
        fields={k:v for k,v in self.fields.items() if k not in ('lot_id','purchase_usd','exchange_rate','shipping_cop')}
        with self.app.app_context():
            fields['location_id']=db.session.scalar(db.select(Catalogo.id).where(Catalogo.kind=='location',Catalogo.name=='LOCAL CP STORE'))
        fields.update(entry_type='Retoma',imei=self.imei(0),condition='Usado',purchase_cop='800000',
                      additional_name=['COMISIÓN','BATERÍA'],additional_amount=['20000','75000'])
        response=self.client.post('/inventario/nuevo?tipo=Retoma',data=MultiDict((k,item) for k,v in fields.items() for item in (v if isinstance(v,list) else [v])))
        self.assertEqual(response.status_code,302,response.get_data(as_text=True)[-1500:])
        with self.app.app_context():
            p=db.session.scalar(db.select(Producto).where(Producto.imei==self.imei(0)))
            self.assertEqual((p.source_type,p.supplier,p.lot_id,p.condition),('Retoma','CP CELULARES',None,'Usado'))
            self.assertEqual((p.purchase_cop_cents,p.cost_cents),(80000000,89500000))
            self.assertEqual(len(p.additional_costs),2)
        self.assertIn('POOL',self.client.get('/inventario').get_data(as_text=True))
        self.assertIn('Comisión'.upper(),self.client.get('/inventario/'+str(p.id)).get_data(as_text=True))
        bad={**fields,'imei':self.imei(1),'purchase_usd':'200'}
        self.assertIn('pesos',self.client.post('/inventario/nuevo?tipo=Retoma',data=bad).get_data(as_text=True))
        bad={**fields,'imei':self.imei(1),'additional_name':['X']*6,'additional_amount':['1']*6}
        self.assertIn('máximo cinco',self.client.post('/inventario/nuevo?tipo=Retoma',data=bad).get_data(as_text=True))


class LinkedConsignmentTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from app import create_app
        self.tmp=tempfile.TemporaryDirectory();self.app=create_app({'TESTING':True,'DATABASE':str(Path(self.tmp.name)/'test.sqlite'),'SECRET_KEY':'tests'})
        self.client=self.app.test_client();self.day='2026-10-01'
        self.client.get('/finanzas?date='+self.day)
        with self.client.session_transaction() as session:self.csrf=session['csrf']
        with self.app.app_context():
            person=PersonaContable(nombre='EMILY',identificacion='8001',tipo='Natural')
            bank=BancoDestino(nombre='BANCO TEST');db.session.add_all([person,bank]);db.session.commit()
            self.person_id=person.id;self.bank_id=bank.id
            db.session.add(PersonaBanco(persona_id=person.id,banco_id=bank.id));db.session.commit()
        self.post('open')

    def tearDown(self):release(self.app);self.tmp.cleanup()

    def post(self,action,**values):
        with self.app.app_context():
            day=finance.find_day(self.day);revision=day.revision if day else 0
        data=dict(csrf=self.csrf,date=self.day,revision=str(revision),token=secrets.token_hex(16),action=action)
        data.update(values)
        return self.client.post('/finanzas',data=MultiDict((k,item) for k,v in data.items() for item in (v if isinstance(v,list) else [v])))

    def test_transferencia_edicion_anulacion_y_sin_duplicados(self):
        payment=dict(payment_account=['EFECTIVO','TRANSFERENCIA'],payment_amount=['50000','20000'],
                     payment_person_id=['',str(self.person_id)],payment_bank_id=['',str(self.bank_id)])
        fields=dict(kind='Venta',description='ACCESORIOS',seller='EMILY',amount='70000',minor_cost='0',**payment)
        self.assertEqual(self.post('operation',**fields).status_code,302)
        with self.app.app_context():
            o=db.session.scalar(db.select(OperacionFinanciera));cid=db.session.scalar(db.select(ConsignacionBancaria.id))
            self.assertEqual(evaluar_estado_renta(self.person_id,2026)['total_consignado'],Decimal('20000.00'))
            self.assertEqual(o.payments[1]['person_id'],self.person_id)
            oid=o.id
        fields.update(payment_amount=['40000','30000'])
        self.assertEqual(self.post('edit_operation',operation_id=str(oid),reason='CORREGIR MEDIO',**fields).status_code,302)
        with self.app.app_context():
            self.assertEqual(db.session.get(ConsignacionBancaria,cid).monto,Decimal('30000.00'))
            self.assertEqual(db.session.scalar(db.select(db.func.count(ConsignacionBancaria.id))),1)
        self.assertEqual(self.post('void',operation_id=str(oid),reason='VENTA ANULADA').status_code,302)
        with self.app.app_context():
            self.assertFalse(db.session.get(ConsignacionBancaria,cid).activa)
            self.assertEqual(evaluar_estado_renta(self.person_id,2026)['total_consignado'],0)

    def test_rechaza_medio_sin_persona_y_permite_alta(self):
        accounting_page=self.client.get('/modulos/tributario/').get_data(as_text=True)
        self.assertIn('Registrar una persona',accounting_page)
        self.assertIn('Agregar banco a una persona',accounting_page)
        self.assertIn('Registrar persona o banco',self.client.get('/finanzas?date='+self.day).get_data(as_text=True))
        self.assertEqual(self.client.get('/modulos/tributario/acceso').status_code,404)
        r=self.post('operation',kind='Venta',description='FORRO',seller='EMILY',amount='50000',
                    payment_account=['TRANSFERENCIA'],payment_amount=['50000'],payment_person_id=[''],payment_bank_id=[''])
        self.assertEqual(r.status_code,200)
        with self.app.app_context():self.assertEqual(db.session.scalar(db.select(db.func.count(OperacionFinanciera.id))),0)
        response=self.client.post('/modulos/tributario/crear-destinatario',data={'csrf':self.csrf,'nombre':'ANA','identificacion':'1222','tipo':'Natural'})
        self.assertEqual(response.status_code,302)
        response=self.client.post('/modulos/tributario/crear-banco',data={'csrf':self.csrf,'nombre_banco':'OTRO BANCO'})
        self.assertEqual(response.status_code,302)
        with self.app.app_context():
            self.assertIsNotNone(db.session.scalar(db.select(PersonaContable).where(PersonaContable.identificacion=='1222')))
            self.assertIsNotNone(db.session.scalar(db.select(BancoDestino).where(BancoDestino.nombre=='OTRO BANCO')))

    def test_proveedor_interno_acumula_sin_obligacion(self):
        r=self.post('operation',kind='Venta',description='CUBO',seller='EMILY',amount='30000',minor_cost='0',
            payment_account=['EFECTIVO'],payment_amount=['30000'],cost_type=['Proveedor'],cost_name=['CP VARIOS'],cost_qty=['1'],cost_unit=['10000'])
        self.assertEqual(r.status_code,302,r.get_data(as_text=True)[-1000:])
        with self.app.app_context():
            report=finance.report(finance.find_day(self.day))
            self.assertEqual(report['totals']['funds']['CP VARIOS'],1000000)
            self.assertEqual(report['totals']['debe'],2000000)
            self.assertFalse(finance.obligations())

    def test_pago_bancario_proveedor_tambien_se_refleja_una_vez(self):
        with self.app.app_context():
            db.session.add(Catalogo(kind='supplier',name='EXTERNO',normal_key='externo',parent_id=0,active=1));db.session.commit()
        result=self.post('operation',kind='Venta',description='ACCESORIO',seller='EMILY',amount='20000',minor_cost='0',
            payment_account=['EFECTIVO'],payment_amount=['20000'],cost_type=['Proveedor'],cost_name=['EXTERNO'],
            cost_qty=['1'],cost_unit=['6000'])
        self.assertEqual(result.status_code,302)
        with self.app.app_context():oid=db.session.scalar(db.select(OperacionFinanciera.id))
        result=self.post('supplier_payment',operation_id=str(oid),cost_index='0',amount='6000',account='TRANSFERENCIA',
                         payment_person_id=str(self.person_id),payment_bank_id=str(self.bank_id),reason='PAGO EXTERNO')
        self.assertEqual(result.status_code,302,result.get_data(as_text=True)[-700:])
        with self.app.app_context():
            c=db.session.scalar(db.select(ConsignacionBancaria))
            self.assertEqual(c.monto,Decimal('6000.00'))
            self.assertIsNotNone(c.supplier_payment_id)
            self.assertEqual(evaluar_estado_renta(self.person_id,2026)['total_consignado'],Decimal('6000.00'))


if __name__=='__main__':unittest.main()
