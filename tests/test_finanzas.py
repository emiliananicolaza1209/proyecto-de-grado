import unittest,tempfile,secrets
from pathlib import Path
from werkzeug.datastructures import MultiDict
from app import create_app
from app.extensions import db
from app.models.finanzas import OperacionFinanciera as Op
from app.models import Producto,Cobro,Recepcion
from app.services import finanzas_service as f

class FinanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=create_app({'TESTING':True,'DATABASE':str(Path(self.tmp.name)/'test.sqlite'),'SECRET_KEY':'tests'})
        self.client=self.app.test_client();self.day='2026-09-01'
        self.client.get('/finanzas?date='+self.day)
        with self.client.session_transaction() as s:self.csrf=s['csrf']
        self.post('open')
    def tearDown(self):self.tmp.cleanup()
    def post(self,action,expected=302,**kw):
        with self.app.app_context():
            d=f.find_day(self.day);revision=d.revision if d else 0
        values=dict(csrf=self.csrf,date=self.day,action=action,revision=str(revision),token=secrets.token_hex(16));values.update(kw)
        data=MultiDict()
        for k,v in values.items():
            for item in v if isinstance(v,list) else [v]:data.add(k,item)
        r=self.client.post('/finanzas',data=data)
        self.assertEqual(r.status_code,expected,r.get_data(as_text=True)[-2000:]);return r
    def totals(self):
        with self.app.app_context():return f.report(f.find_day(self.day))['totals']
    def sale(self,**kw):
        args=dict(kind='Venta',description='VIDRIOS',seller='ANA',amount='1000000',minor_cost='10000',payment_account=['EFECTIVO'],payment_amount=['1000000']);args.update(kw);return self.post('operation',**args)
    def test_excel_golden_results(self):
        for day,debe,haber,salaries,expected in [('2026-09-01',1669000,55000,[80000,74000],(565000,1049000,80000,969000,1625000,1335000)),('2026-09-06',225000,47000,[50000,0],(50000,128000,0,128000,210000,150000)),('2026-09-27',0,0,[50000,50000],(100000,-100000,0,-100000,-100000,-100000))]:
            cfg=f.defaults(day);cfg['staff']=[{'role':r,'salary':v*100} for r,v in zip(['Principal','Secundaria'],salaries)]
            funds={'CP VARIOS':(200000 if day.endswith('01') else 35000 if day.endswith('06') else 0)*100}
            t=f.calculate(cfg,day,debe*100,haber*100,0,1000000 if day.endswith('01') else 0,funds,29000000 if day.endswith('01') else 6000000 if day.endswith('06') else 0)
            self.assertEqual(tuple(t[k]//100 for k in ['liquidation','result','commission','profit','control_total','control_cash']),expected)
    def test_service_pd_and_cash(self):
        self.sale();before=self.totals()
        self.post('operation',kind='PD',description='RETIRO',seller='PROPIETARIO',amount='20000',payment_account=['EFECTIVO'],payment_amount=['20000'])
        after=self.totals();self.assertEqual(before['commission'],after['commission']);self.assertEqual(before['result'],after['result']);self.assertEqual(after['owner_result'],before['owner_result']-2000000)
        self.post('operation',kind='Servicio',description='GARANTIA',seller='ANA',amount='30000',payment_account=['EFECTIVO'],payment_amount=['30000'])
        self.assertEqual(self.totals()['result'],before['result']-3000000);self.assertEqual(self.totals()['cash_expected'],95000000)
    def test_mixed_payment_supplier_and_overpayment(self):
        self.sale(amount='105000',minor_cost='5000',payment_account=['EFECTIVO','TRANSFERENCIA POR IDENTIFICAR'],payment_amount=['55000','50000'],cost_name=['CP VARIOS','PROVEEDOR'],cost_type=['Fondo','Proveedor'],cost_qty=['3','1'],cost_unit=['10000','5000'])
        self.assertEqual(self.totals()['debe'],7000000)
        with self.app.app_context():oid=db.session.scalar(db.select(Op.id))
        self.post('supplier_payment',operation_id=str(oid),cost_index='1',amount='2000',account='EFECTIVO',reason='ABONO')
        self.assertEqual(self.totals()['cash_expected'],5300000)
        self.post('supplier_payment',expected=200,operation_id=str(oid),cost_index='1',amount='4000',account='EFECTIVO',reason='PAGO')
        self.assertEqual(self.totals()['debe'],7000000)
    def test_duplicate_invalid_money_csrf_and_stale(self):
        token=secrets.token_hex(16);self.sale(token=token);self.sale(token=token,expected=200);self.sale(amount='NaN',expected=200);self.sale(revision='0',expected=200)
        self.assertEqual(self.client.post('/finanzas',data={'date':self.day}).status_code,400)
        with self.app.app_context():self.assertEqual(db.session.scalar(db.select(db.func.count(Op.id))),1)
    def test_close_snapshot_and_reopen(self):
        self.sale()
        with self.app.app_context():
            d=f.find_day(self.day);cfg=dict(d.config);cfg.update(reviewed=True,actor='ANA');d.config=cfg;db.session.commit()
        self.post('close',counted='1000000');self.sale(expected=200)
        with self.app.app_context():d=f.find_day(self.day);self.assertEqual(d.snapshot['difference'],0);self.assertEqual(d.status,'Cerrada')
        self.post('reopen',reason='CORREGIR');self.sale();self.assertEqual(self.totals()['gross'],200000000)
    def test_collection_receipt_not_doubled(self):
        with self.app.app_context():
            p=Producto(imei='490154203237518',model='EQUIPO',capacity=128,color='AZUL',condition='Nuevo',cost_cents=50000,location='BODEGA',supplier='CP',status='Vendido',sale_date=self.day,sale_value_cents=100000,seller='ANA')
            db.session.add(p);db.session.flush();pid=p.id
            c=Cobro(product_id=pid,amount_cents=100000,destination='Vendedora',collector='ANA',method='Efectivo',reference='',effective_date=self.day,note='test',legacy=False,voided=False)
            db.session.add(c);db.session.flush();db.session.add(Recepcion(collection_id=c.id,amount_cents=100000,administrator='ADMIN',method='Efectivo',reference='',effective_date=self.day,note='test',voided=False));db.session.commit()
        t=self.totals();self.assertEqual(t['customer_collections'],100000);self.assertEqual(t['cash_expected'],100000);self.assertEqual(t['banks']['EFECTIVO'],100000)
        self.post('incorporate',product_id=str(pid));self.post('incorporate',product_id=str(pid),expected=200)
        self.assertEqual(self.totals()['gross'],100000);self.assertEqual(self.totals()['debe'],50000)
        with self.app.app_context():oid=db.session.scalar(db.select(Op.id).where(Op.product_id==pid))
        self.post('equipment_costs',operation_id=str(oid),minor_cost='10',cost_name=['CP VARIOS'],cost_type=['Fondo'],cost_qty=['1'],cost_unit=['50'],reason='FORRO INCLUIDO')
        self.assertEqual(self.totals()['gross'],100000);self.assertEqual(self.totals()['debe'],45000);self.assertEqual(self.totals()['haber'],1000)
        self.assertEqual(self.client.get('/finanzas?date='+self.day).status_code,200)
    def test_commission_boundaries_holiday_overflow(self):
        cfg=f.defaults(self.day);cfg['staff']=[{'role':'Principal','salary':0}];cfg['normal_base']=cfg['extra_a']=cfg['extra_b']=0
        def calc(debe):return f.calculate(cfg,self.day,debe,0,0,0,{},0)
        self.assertEqual(calc(36000000-1)['commission'],0);self.assertEqual(calc(36000000)['commission'],1000000);self.assertTrue(calc(1000000000)['overflow'])
        cfg['holiday']=True;self.assertEqual(calc(21000000)['commission'],1000000)
    def test_tabs_csv_migration(self):
        for tab in ['movimientos','proveedores','personal','cierre']:self.assertEqual(self.client.get('/finanzas?date='+self.day+'&tab='+tab).status_code,200)
        self.assertEqual(self.client.get('/modulos/finanzas').status_code,302)
        self.sale(description='=FORMULA');r=self.client.get('/finanzas/exportar?date='+self.day);self.assertIn("'=FORMULA",r.get_data(as_text=True))
        from migrations import upgrade
        upgrade(self.app.config['DATABASE']);self.assertEqual(self.totals()['gross'],100000000)
if __name__=='__main__':unittest.main()
