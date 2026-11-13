from jornada_fixtures import opening
import unittest,tempfile,secrets
from pathlib import Path
from werkzeug.datastructures import MultiDict
from app import create_app
from app.extensions import db
from app.models.finanzas import OperacionFinanciera as Op, PagoProveedor
from app.models import Producto,Cobro,Recepcion,Catalogo,PersonaContable,BancoDestino,PersonaBanco
from app.services import finanzas_service as f

class FinanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=create_app({'TESTING':True,'DATABASE':str(Path(self.tmp.name)/'test.sqlite'),'SECRET_KEY':'tests'})
        self.client=self.app.test_client();self.day='2026-09-01'
        self.client.get('/finanzas?date='+self.day)
        with self.client.session_transaction() as s:self.csrf=s['csrf']
        self.post('open',**opening(self.day,('ANA','MARIA','PROPIETARIO')))
    def tearDown(self):
        with self.app.app_context():
            db.session.remove();db.engine.dispose()
        self.tmp.cleanup()
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
    def test_other_requires_detail_and_empty_minor_cost_defaults_zero(self):
        params=dict(amount='100000',minor_cost='',payment_amount=['100000'],cost_type=['Proveedor'],
                    cost_name=['OTROS'],cost_category=['Accesorios'],cost_qty=['1'],cost_unit=['10000'])
        response=self.sale(expected=200,**params)
        self.assertIn('Describe el costo de Otros',response.get_data(as_text=True))
        self.sale(**params,cost_detail=['DOMICILIO PARA EL CLIENTE'])
        with self.app.app_context():
            op=db.session.scalar(db.select(Op));self.assertEqual(op.minor_cost,0)
            self.assertEqual(op.costs[0]['detail'],'DOMICILIO PARA EL CLIENTE')

    def test_dataphone_gross_is_net_sale_and_accounting_records_gross(self):
        with self.app.app_context():
            db.session.add(PersonaContable(nombre='EMILY',identificacion='1122',tipo='Natural'));db.session.commit()
            person=db.session.scalar(db.select(PersonaContable.id))
        self.sale(amount='1100000',minor_cost='',payment_account=['DATÁFONO'],payment_amount=['1155000'],
                  payment_person_id=[str(person)],payment_bank_id=[''])
        with self.app.app_context():
            from app.models.contabilidad import ConsignacionBancaria
            op=db.session.scalar(db.select(Op));c=db.session.scalar(db.select(ConsignacionBancaria))
            self.assertEqual(op.amount,110000000);self.assertEqual(c.monto,1155000)
        self.assertEqual(self.totals()['debe'],110000000)

    def test_bank_breakdown_pd_cash_and_technical_service(self):
        with self.app.app_context():
            db.session.add(PersonaContable(nombre='EMILY',identificacion='1122',tipo='Natural'))
            db.session.add(Catalogo(kind='supplier',name='TECNICO',normal_key='tecnico',parent_id=0,active=1,
                                    supplier_category='Accesorios'))
            db.session.commit()
            person=db.session.scalar(db.select(PersonaContable.id))
        self.sale(amount='1155000',minor_cost='',payment_account=['DATÁFONO'],payment_amount=['1155000'],
                  payment_person_id=[str(person)],cost_type=['Proveedor'],cost_name=['TECNICO'],
                  cost_category=['Servicio técnico'],cost_qty=['1'],cost_unit=['980000'])
        self.post('operation',kind='PD',description='PAPELERIA DEL LOCAL',seller='ANA',amount='20000',
                  payment_account=['EFECTIVO'],payment_amount=['20000'])
        t=self.totals()
        self.assertEqual(t['sales_count'],1)
        self.assertEqual(t['bank_gross']['DATÁFONO'],115500000)
        self.assertEqual(t['bank_net']['DATÁFONO'],110000000)
        self.assertEqual(t['bank_profit']['DATÁFONO'],12000000)
        self.assertEqual(t['bank_received'],115500000)
        self.assertEqual(t['pd'],2000000)
        self.assertEqual(t['cash_expected'],18000000)

    def test_closed_day_trend_uses_snapshot_values(self):
        with self.app.app_context():
            day=f.find_day(self.day)
            day.status='Cerrada'
            day.snapshot={'totals':{**f.report(day)['totals'],'gross':12345000,'sales_count':2,'owner_result':450000},
                          'counted':0,'difference':0,'config':day.config}
            db.session.commit()
        page=self.client.get('/finanzas?date='+self.day+'&tab=cierre').get_data(as_text=True)
        self.assertIn('Ventas netas recientes',page)
        self.assertIn('123.450,00',page)
        self.assertIn('style="--bar:100.0%"',page)

    def test_entering_gross_price_uses_card_net_for_debe_and_equipment_sale(self):
        with self.app.app_context():
            db.session.add(PersonaContable(nombre='EMILY',identificacion='1122',tipo='Natural'))
            db.session.add(Producto(imei='490154203237518',model='IPHONE',capacity=128,color='AZUL',
                                    condition='Nuevo',cost_cents=98000000,location='LOCAL',supplier='CP',status='Disponible'))
            db.session.commit()
            person=db.session.scalar(db.select(PersonaContable.id));pid=db.session.scalar(db.select(Producto.id))
        self.sale(amount='1155000',minor_cost='',payment_account=['DATÁFONO'],payment_amount=['1155000'],
                  payment_person_id=[str(person)],cost_type=['Equipo'],cost_name=['490154203237518'],
                  cost_qty=['1'],cost_unit=['980000'])
        with self.app.app_context():
            p=db.session.get(Producto,pid)
            self.assertEqual((p.sale_value_cents,p.paid_cents,p.status),(110000000,110000000,'Vendido'))
            op=db.session.scalar(db.select(Op))
            self.assertEqual(op.amount,110000000)
        self.assertEqual(self.totals()['debe'],12000000)

    def test_edit_bank_payment_after_supplier_payment_reconciles(self):
        with self.app.app_context():
            db.session.add_all([Catalogo(kind='supplier',name='PRUEBA',normal_key='prueba',parent_id=0,active=1),
                PersonaContable(nombre='EMILY',identificacion='1122',tipo='Natural'),BancoDestino(nombre='BANCO')]);db.session.commit()
            person=db.session.scalar(db.select(PersonaContable.id));bank=db.session.scalar(db.select(BancoDestino.id))
            db.session.add(PersonaBanco(persona_id=person,banco_id=bank));db.session.commit()
        self.sale(amount='100000',minor_cost='',payment_account=['TRANSFERENCIA'],payment_amount=['100000'],
            payment_person_id=[str(person)],payment_bank_id=[str(bank)],cost_type=['Proveedor'],
            cost_name=['PRUEBA'],cost_qty=['1'],cost_unit=['10000'])
        with self.app.app_context():oid=db.session.scalar(db.select(Op.id))
        self.post('supplier_payment',operation_id=str(oid),cost_index='0',amount='10000',account='EFECTIVO',reason='PAGADO')
        self.post('edit_operation',operation_id=str(oid),description='VIDRIOS',seller='ANA',amount='100000',minor_cost='',
            cost_type=['Proveedor'],cost_name=['PRUEBA'],cost_detail=[''],cost_category=['Accesorios'],cost_qty=['1'],cost_unit=['10000'],
            payment_account=['EFECTIVO'],payment_amount=['100000'],reason='CORRECCION DEL MEDIO')
        with self.app.app_context():
            from app.models.contabilidad import ConsignacionBancaria
            self.assertFalse(db.session.scalar(db.select(ConsignacionBancaria)).activa)

    def test_finance_equipment_sale_updates_both_modules_without_double_cash(self):
        with self.app.app_context():
            p=Producto(imei='490154203237518',model='IPHONE',capacity=128,color='AZUL',condition='Usado',
                       cost_cents=50000000,location='BODEGA',supplier='CP',status='Disponible')
            db.session.add(p);db.session.commit();pid=p.id
        self.sale(amount='1100000',minor_cost='',payment_account=['EFECTIVO','DATÁFONO'],
            payment_amount=['500000','630000'],payment_person_id=['',''],cost_type=['Equipo'],
            cost_name=['490154203237518'],cost_qty=['1'],cost_unit=['500000'],expected=200)
        with self.app.app_context():
            db.session.add(PersonaContable(nombre='EMILY',identificacion='1122',tipo='Natural'));db.session.commit()
            person=db.session.scalar(db.select(PersonaContable.id))
        self.sale(amount='1100000',minor_cost='',payment_account=['EFECTIVO','DATÁFONO'],
            payment_amount=['500000','630000'],payment_person_id=['',str(person)],cost_type=['Equipo'],
            cost_name=['490154203237518'],cost_qty=['1'],cost_unit=['500000'])
        with self.app.app_context():
            from app.services.pago_service import summary
            p=db.session.get(Producto,pid)
            self.assertEqual((p.status,p.payment_status,p.paid_cents),('Vendido','Pagado',110000000))
            self.assertEqual(summary(p)['total'],110000000)
        self.assertEqual(self.totals()['cash_expected'],70000000)

    def test_pool_assigned_cost_is_at_least_purchase_and_admin_gain_is_separate(self):
        with self.app.app_context():
            p=Producto(imei='490154203237518',model='IPHONE POOL',capacity=128,color='AZUL',condition='Usado',
                      cost_cents=50000000,purchase_cop_cents=48000000,source_type='Retoma',
                      location='LOCAL',supplier='CP CELULARES',status='Disponible')
            day=f.find_day(self.day);day.config={**day.config,'staff':[dict(name='ANA',role='Principal',salary=0,attended=True)]}
            db.session.add(p);db.session.commit();pid=p.id
        args=dict(amount='700000',minor_cost='',payment_account=['EFECTIVO'],payment_amount=['700000'],
                  cost_type=['Equipo'],cost_name=['490154203237518'],cost_qty=['1'])
        response=self.sale(expected=200,**args,cost_unit=['499999'])
        self.assertIn('igual o mayor',response.get_data(as_text=True))
        with self.app.app_context():self.assertEqual(db.session.get(Producto,pid).status,'Disponible')
        self.sale(**args,cost_unit=['580000'])
        with self.app.app_context():
            p=db.session.get(Producto,pid)
            self.assertEqual((p.cost_cents,p.pool_assigned_cost_cents,p.pool_admin_gain_cents),
                             (50000000,58000000,8000000))
            self.assertIn('adicional para administración',p.last_note)
            day=f.find_day(self.day);result=f.report(day)
            self.assertEqual(result['totals']['debe'],10000000)  # Comisión POOL extra de 20.000
            self.assertEqual(result['totals']['pool_extra_commission'],2000000)
            self.assertEqual(result['totals']['pool_admin_gain'],8000000)
            self.assertEqual(result['owned_device_plan'][0]['cost'],58000000)
        self.assertIn('Adicional para administración',self.client.get(f'/inventario/{pid}').get_data(as_text=True))
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
        self.assertEqual(self.totals()['result'],before['result']-3000000);self.assertEqual(self.totals()['cash_expected'],115000000)
    def test_mixed_payment_supplier_and_overpayment(self):
        with self.app.app_context():
            db.session.add_all([Catalogo(kind='supplier',name='PROVEEDOR',normal_key='proveedor',parent_id=0,active=1),PersonaContable(nombre='EMILY',identificacion='777',tipo='Natural'),BancoDestino(nombre='BANCO')]);db.session.commit()
            person=db.session.scalar(db.select(PersonaContable.id));bank=db.session.scalar(db.select(BancoDestino.id))
            db.session.add(PersonaBanco(persona_id=person,banco_id=bank));db.session.commit()
        self.sale(amount='105000',minor_cost='5000',payment_account=['EFECTIVO','TRANSFERENCIA'],payment_amount=['55000','50000'],payment_person_id=['',str(person)],payment_bank_id=['',str(bank)],cost_name=['CP VARIOS','PROVEEDOR'],cost_type=['Fondo','Proveedor'],cost_qty=['3','1'],cost_unit=['10000','5000'])
        self.assertEqual(self.totals()['debe'],7000000)
        self.assertEqual(self.totals()['internal_bank_funds'],3000000)
        self.assertEqual(self.totals()['transfer'],4500000)
        with self.app.app_context():oid=db.session.scalar(db.select(Op.id))
        self.post('supplier_payment',operation_id=str(oid),cost_index='1',amount='2000',account='EFECTIVO',reason='ABONO')
        self.assertEqual(self.totals()['cash_expected'],25300000)
        self.post('supplier_payment',expected=200,operation_id=str(oid),cost_index='1',amount='4000',account='EFECTIVO',reason='PAGO')
        self.assertEqual(self.totals()['debe'],7000000)
    def test_excel_october_23_step_by_step_bank_fund(self):
        # Hoja «13»: DEBE 285.000, HABER 25.000, TOTAL 67.000,
        # TOTAL TRANSFER 50.000 y EFECTIVO CONTROL 17.000.
        def cost(name, typ, amount):
            return dict(name=name,type=typ,category='Accesorios',quantity=1,unit=amount,amount=amount)
        with self.app.app_context():
            d=f.find_day(self.day);cfg=dict(d.config)
            cfg['staff']=[dict(name='MARIA',role='Principal',salary=8000000,attended=True),
                          dict(name='LEYDIS',role='Secundaria',salary=7400000,attended=True),
                          dict(name='SANDRA',role='Secundaria',salary=7400000,attended=True)]
            d.config=cfg
            operations=[
                Op(day_id=d.id,token=secrets.token_hex(16),kind='Venta',description='EFECTIVO',seller='MARIA',
                   amount=66500000,minor_cost=2500000,costs=[cost('PROVEEDOR','Proveedor',42000000)],
                   payments=[dict(account='EFECTIVO',amount=66500000)]),
                Op(day_id=d.id,token=secrets.token_hex(16),kind='Venta',description='COMPLEMENTO',seller='MARIA',
                   amount=20000000,minor_cost=0,costs=[cost('CELULARES','Proveedor',20000000)],
                   payments=[dict(account='DATÁFONO',amount=20000000)]),
                Op(day_id=d.id,token=secrets.token_hex(16),kind='Venta',description='VIDRIO',seller='MARIA',
                   amount=2000000,minor_cost=0,costs=[],payments=[dict(account='DATÁFONO',amount=2000000)]),
                Op(day_id=d.id,token=secrets.token_hex(16),kind='Venta',description='SILICON CP VARIOS',seller='MARIA',
                   amount=3000000,minor_cost=0,costs=[cost('CP VARIOS','Fondo',1000000)],
                   payments=[dict(account='DATÁFONO',amount=3000000)]),
            ]
            db.session.add_all(operations);db.session.flush()
            db.session.add(PagoProveedor(day_id=d.id,operation_id=operations[0].id,cost_index=0,
                                         amount=38000000,account='EFECTIVO',token=secrets.token_hex(16)))
            db.session.commit()
            report=f.report(d);t=report['totals']
            self.assertEqual([t[key]//100 for key in ('debe','haber','liquidation','result','control_total','transfer','control_cash')],
                             [285000,25000,639000,-379000,67000,50000,17000])
            self.assertEqual(t['internal_bank_funds'],1000000)
            self.assertEqual(t['banks']['EFECTIVO'],66500000)
            self.assertEqual(t['cash_expected'],48500000)
        page=self.client.get('/finanzas?date='+self.day+'&tab=movimientos').get_data(as_text=True)
        self.assertIn('Medio de pago',page)
        self.assertIn('DATÁFONO · $ 30.000',page)
        closing=self.client.get('/finanzas?date='+self.day+'&tab=cierre').get_data(as_text=True)
        self.assertNotIn('Efectivo a entregar, sin base',closing)
        self.assertIn('Bancos en el control Excel (ganancia + capital propio)',closing)
    def test_fondo_propio_no_sale_de_caja_hasta_registrar_pago(self):
        self.sale(amount='30000',minor_cost='0',cost_name=['CP VARIOS'],cost_type=['Fondo'],
                  cost_qty=['1'],cost_unit=['10000'],payment_account=['EFECTIVO'],payment_amount=['30000'])
        t=self.totals()
        self.assertEqual(t['funds']['CP VARIOS'],1000000)
        self.assertEqual(t['transfer'],0)
        self.assertEqual(t['cash_expected'],23000000)
        self.assertEqual(t['internal_bank_funds'],0)
    def test_duplicate_invalid_money_csrf_and_stale(self):
        token=secrets.token_hex(16);self.sale(token=token);self.sale(token=token,expected=200);self.sale(amount='NaN',expected=200);self.sale(revision='0',expected=200)
        self.assertEqual(self.client.post('/finanzas',data={'date':self.day}).status_code,400)
        with self.app.app_context():self.assertEqual(db.session.scalar(db.select(db.func.count(Op.id))),1)
    def test_close_snapshot_and_reopen(self):
        self.sale()
        with self.app.app_context():
            d=f.find_day(self.day);cfg=dict(d.config);cfg.update(reviewed=True,actor='ANA',staff=[{'name':'ANA','role':'Principal','salary':0,'attended':True}]);d.config=cfg;db.session.commit()
        # La nueva regla exige pagar la comisión causada antes de cerrar.
        self.assertEqual(self.totals()['unit_commission'],2000000)
        self.post('operation',kind='Pago comisión',seller='ANA',description='PAGO COMISIÓN',amount='20000',payment_account=['EFECTIVO'],payment_amount=['20000'])
        self.post('close',counted='980000');self.sale(expected=200)
        with self.app.app_context():d=f.find_day(self.day);self.assertEqual(d.snapshot['difference'],0);self.assertEqual(d.status,'Cerrada')
        self.post('reopen',reason='CORREGIR');self.sale();self.assertEqual(self.totals()['gross'],200000000)
    def test_collection_receipt_not_doubled(self):
        with self.app.app_context():
            p=Producto(imei='490154203237518',model='EQUIPO',capacity=128,color='AZUL',condition='Nuevo',cost_cents=50000,location='BODEGA',supplier='CP',status='Vendido',sale_date=self.day,sale_value_cents=100000,seller='ANA')
            db.session.add(p);db.session.flush();pid=p.id
            c=Cobro(product_id=pid,amount_cents=100000,destination='Vendedora',collector='ANA',method='Efectivo',reference='',effective_date=self.day,note='test',legacy=False,voided=False)
            db.session.add(c);db.session.flush();db.session.add(Recepcion(collection_id=c.id,amount_cents=100000,administrator='ADMIN',method='Efectivo',reference='',effective_date=self.day,note='test',voided=False));db.session.commit()
        t=self.totals();self.assertEqual(t['customer_collections'],100000);self.assertEqual(t['cash_expected'],20100000);self.assertEqual(t['banks']['EFECTIVO'],100000)
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
