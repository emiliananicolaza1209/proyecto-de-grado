from _cleanup import release
import unittest,tempfile,secrets,io
from pathlib import Path
from werkzeug.datastructures import MultiDict,FileStorage
from werkzeug.security import generate_password_hash
from app import create_app
from app.extensions import db
from app.models import Producto,Catalogo,PersonaContable,BancoDestino,PersonaBanco,ConsignacionBancaria,Cobro
from app.models.finanzas import Jornada,OperacionFinanciera as Op
from app.models.gestion import *
from app.services import finanzas_service as f,credito_service as cr,sociedad_service as so,compras_service as co,stock_service as st

def data(**kw):
    d=MultiDict()
    for k,v in kw.items():
        for x in (v if isinstance(v,list) else [v]):d.add(k,str(x))
    return d

class GestionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=create_app(dict(TESTING=True,DATABASE=str(Path(self.tmp.name)/'db.sqlite'),SECRET_KEY='test'))
        self.ctx=self.app.app_context();self.ctx.push();self.day=f.today();self.d=f.open_day(self.day)
        cfg=dict(self.d.config);cfg['staff']=[dict(name=n,role='Principal',salary=0,attended=True) for n in ('ANA','LUZ','MAR')];cfg['reviewed']=True;cfg['actor']='ANA';self.d.config=cfg
        self.person=PersonaContable(nombre='EMILY',identificacion='TEST1',tipo='Natural');self.bank=BancoDestino(nombre='BANCO PRUEBA')
        db.session.add_all([self.person,self.bank]);db.session.flush();db.session.add(PersonaBanco(persona_id=self.person.id,banco_id=self.bank.id));db.session.commit()
        self.ally=db.session.scalar(db.select(AliadoCredito).where(AliadoCredito.nombre=='SU+PAY'));self.ally.porcentaje_bp=1800
        self.ally.persona_id=self.person.id;self.ally.banco_id=self.bank.id;db.session.commit()
    def tearDown(self):release(self.app);self.ctx.pop();self.tmp.cleanup()
    def product(self,pool=False,cost=50000000,imei='490154203237518'):
        p=Producto(imei=imei,model='IPHONE PRUEBA',capacity=128,color='NEGRO',condition='Usado' if pool else 'Nuevo',cost_cents=cost,
            purchase_cop_cents=cost if pool else None,additional_costs=[],source_type='Retoma' if pool else 'Lote',location='LOCAL',supplier='CP CELULARES',status='Disponible')
        db.session.add(p);db.session.commit();return p
    def sale(self,p=None,credit=True,**changes):
        params=dict(kind='Venta',description='VENTA PRUEBA',seller='ANA',token=secrets.token_hex(16),amount='650000',minor_cost='',
            payment_account=['CRÉDITO'] if credit else ['EFECTIVO'],payment_amount=['650000'],payment_ally_id=[str(self.ally.id)],
            payment_person_id=[str(self.person.id)],payment_bank_id=[str(self.bank.id)],credit_approved='1',payment_credit_mode=['Porcentaje'],payment_credit_rate=['18'])
        if p:params.update(cost_type=['Equipo'],cost_name=[p.imei],cost_qty=['1'],cost_unit=[str(p.cost_cents/100)])
        params.update(changes);f.add_operation(self.d,data(**params));db.session.commit()
        return db.session.scalar(db.select(Op).order_by(Op.id.desc()))
    def settlement(self,c,amount=None,ref='ABONO',**kw):
        args=dict(ally_id=self.ally.id,date=self.day,person_id=self.person.id,bank_id=self.bank.id,token=secrets.token_hex(16),
            amount=str((amount or c.neto)/100),reference=ref,credit_id=[c.id],allocation=[str((amount or c.neto)/100)])
        args.update(kw);batch=cr.settle(data(**args));db.session.commit();return batch
    def test_credit_18_percent_and_actual_deposit_only_on_receipt(self):
        self.sale();c=db.session.scalar(db.select(CreditoVenta));self.assertEqual((c.bruto,c.costo,c.neto),(65000000,11700000,53300000))
        self.assertEqual(db.session.query(ConsignacionBancaria).count(),0)
        before=f.report(self.d)['totals'];self.assertEqual(before['credit_net'],53300000);self.assertEqual(before['bank_received'],0)
        self.settlement(c);after=f.report(self.d)['totals'];self.assertEqual(after['bank_received'],53300000);self.assertEqual(after['debe'],before['debe'])
        self.assertEqual(db.session.query(ConsignacionBancaria).count(),1)
    def test_manual_net_plus_actual_initial_no_double_discount(self):
        o=self.sale(amount='1400000',payment_account=['EFECTIVO','CRÉDITO'],payment_amount=['500000','900000'],
            payment_ally_id=['',self.ally.id],payment_credit_mode=['','Neto pactado'],payment_credit_net=['','900000'],payment_credit_rate=['',''],
            payment_person_id=['',self.person.id],payment_bank_id=['',self.bank.id])
        self.assertEqual(o.amount,140000000);self.assertEqual(f.report(self.d)['totals']['cash_expected'],70000000)
    def test_financed_equipment_partial_then_full_no_duplicate_bank(self):
        p=self.product();self.sale(p);c=db.session.scalar(db.select(CreditoVenta))
        self.assertEqual((p.status,p.paid_cents,p.payment_status),('Vendido',0,'Pendiente'))
        self.settlement(c,20000000);self.assertEqual(c.estado,'Parcial');self.assertEqual(p.paid_cents,20000000)
        self.settlement(c,33300000,'FINAL');self.assertEqual((c.estado,p.payment_status),('Pagado','Pagado'))
        t=f.report(self.d)['totals'];self.assertEqual(t['bank_received'],53300000);self.assertEqual(t['debe'],3300000)
    def test_group_disbursement_exact_allocations(self):
        self.sale();self.sale();rows=db.session.scalars(db.select(CreditoVenta)).all()
        self.settlement(rows[0],106600000,credit_id=[x.id for x in rows],allocation=['533000','533000'])
        self.assertEqual(db.session.query(DesembolsoCredito).count(),1);self.assertEqual(db.session.query(AplicacionCredito).count(),2)
    def test_reject_overpayment_duplicate_reference_and_wrong_bank(self):
        self.sale();c=db.session.scalar(db.select(CreditoVenta))
        with self.assertRaises(ValueError):self.settlement(c,60000000)
        db.session.rollback();self.settlement(c,20000000)
        with self.assertRaises(ValueError):self.settlement(c,10000000)
        db.session.rollback();self.assertEqual(c.recibido,20000000)
        b=BancoDestino(nombre='NO ASOCIADO');db.session.add(b);db.session.commit()
        with self.assertRaises(ValueError):self.settlement(c,10000000,'OTRO',bank_id=b.id)
    def test_rates_are_snapshots(self):
        self.sale();c=db.session.scalar(db.select(CreditoVenta));self.ally.porcentaje_bp=2500;db.session.commit()
        self.assertEqual((c.neto,c.condiciones['rate_bp']),(53300000,1800))
    def test_pool_purchase_gain_and_resale_extra(self):
        p=self.product(True);so.register_purchase(p,data(date=self.day,funding='600000',confirmed='1',purchase_mode='Compra directa'));db.session.commit()
        t=f.report(self.d)['totals'];self.assertEqual((t['debe'],t['cash_expected']),(10000000,30000000))
        self.sale(p,False,amount='800000',payment_amount=['800000'],cost_unit=['700000'])
        t=f.report(self.d)['totals'];self.assertEqual(t['debe'],18000000);self.assertEqual(p.pool_admin_gain_cents,10000000)
        c=db.session.scalar(db.select(ComisionPool));self.assertEqual(sum(x['importe'] for x in c.reparto),2000000)
        self.assertEqual([x['importe'] for x in c.reparto],[666667,666667,666666])
        so.pay_pool_commission(data(commission_id=c.id,date=self.day,confirmed='1'));db.session.commit()
        newer=f.report(self.d)['totals'];self.assertEqual(newer['debe'],t['debe']);self.assertEqual(newer['cash_expected'],t['cash_expected']-2000000)
    def test_no_pool_purchase_duplicate_or_below_invested(self):
        p=self.product(True);so.register_purchase(p,data(date=self.day,funding='600000',confirmed='1'));db.session.commit()
        with self.assertRaises(ValueError):so.register_purchase(p,data(date=self.day,funding='600000',confirmed='1'))
        with self.assertRaises(ValueError):self.sale(p,False,cost_unit=['500000'])
        db.session.rollback();self.assertEqual(p.status,'Disponible')
    def partnership(self,p):
        jon=db.session.scalar(db.select(Socio).where(Socio.nombre=='JONATAN'));other=Socio(nombre='ELÍAS');db.session.add(other);db.session.commit()
        s=so.save_society(data(name='SOCIEDAD PRUEBA',partner_id=[jon.id,other.id],capital=['50','50'],profit=['60','40'],active='1'));db.session.flush()
        so.assign_ownership(p,s.id);db.session.commit();return s,jon,other
    def test_society_advance_and_no_double_payment(self):
        p=self.product();s,jon,other=self.partnership(p);self.sale(p,amount='800000',payment_amount=['800000'],payment_credit_rate=['0'])
        args=data(partner_id=other.id,start=self.day,end=self.day,date=self.day,amount='120000',source='ADMINISTRACIÓN',reference='PAGO1',confirmed='1',token=secrets.token_hex(16))
        with self.assertRaises(ValueError):so.liquidate(args)
        db.session.rollback();args['advance']='1';l=so.liquidate(args);db.session.commit();self.assertTrue(l.anticipo)
        b=so.balances(other.id)[0];self.assertEqual((b['gain'],b['capital']),(0,25000000))
        with self.assertRaises(ValueError):so.liquidate(args)
    def test_dissolution_equipment_requires_compensation(self):
        p=self.product();s,jon,other=self.partnership(p)
        args=data(product_id=p.id,partner_id=other.id,mode='Equipo',valuation='Acuerdo',value='600000',amount='0',date=self.day,source='ADMINISTRACIÓN',reference='ACUERDO',confirmed='1',token=secrets.token_hex(16))
        with self.assertRaises(ValueError):so.dissolve(args)
        args['amount']='300000';so.dissolve(args);db.session.commit();self.assertEqual((p.status,p.archived),('Entregado a socio',1));self.assertEqual(db.session.query(Op).count(),0)
    def test_dissolution_cash_preserves_stock_and_reassigns_share(self):
        p=self.product();s,jon,other=self.partnership(p)
        so.dissolve(data(product_id=p.id,partner_id=other.id,buyer_id=jon.id,mode='Dinero',valuation='Costo',amount='250000',date=self.day,source='ADMINISTRACIÓN',reference='ACUERDO',confirmed='1',token=secrets.token_hex(16)))
        db.session.commit();own=db.session.get(PropiedadEquipo,p.id);self.assertEqual(p.status,'Disponible');self.assertEqual(own.participaciones[0]['capital_bp'],10000)
    def lot_fixture(self):
        supplier=db.session.scalar(db.select(Catalogo).where(Catalogo.kind=='supplier',Catalogo.active==1))
        lot=co.create(data(supplier_id=supplier.id,currency='COP',expected_count='1',entry_date=self.day))
        db.session.flush();return lot,db.session.get(ControlLote,lot.id)
    def equipment_line(self):
        ref=db.session.scalar(db.select(Catalogo).where(Catalogo.kind=='reference',Catalogo.active==1))
        def child(k):return db.session.scalar(db.select(Catalogo).where(Catalogo.kind==k,Catalogo.parent_id==ref.id,Catalogo.active==1)).id
        loc=db.session.scalar(db.select(Catalogo).where(Catalogo.kind=='location',Catalogo.active==1))
        return dict(tipo='Equipo',imei='490154203237518',reference_id=ref.id,color_id=child('color'),capacity_id=child('capacity'),location_id=loc.id,condition='Nuevo',purchase_price='500000',shipping_cop='10000',cantidad='1')
    def test_draft_confirmation_reopen_history(self):
        lot,c=self.lot_fixture();co.add_lines(lot,c,[self.equipment_line()]);db.session.commit()
        self.assertEqual(db.session.query(Producto).count(),0);co.confirm(lot,c);db.session.commit()
        p=db.session.scalar(db.select(Producto));self.assertEqual(p.cost_cents,51000000)
        co.reopen(lot,c,'CORREGIR COMPRA');db.session.commit();self.assertEqual(p.archived,1)
        co.confirm(lot,c);db.session.commit();self.assertEqual(db.session.query(Producto).count(),1);self.assertEqual(p.archived,0)
    def test_duplicate_import_does_not_add_any_row(self):
        lot,c=self.lot_fixture();db.session.commit()
        with self.assertRaises(ValueError):co.add_lines(lot,c,[self.equipment_line(),self.equipment_line()])
        self.assertEqual(db.session.query(LineaLote).count(),0)
    def test_stock_quantity_sale_and_no_negative_stock(self):
        cat=CategoriaStock(nombre='ACCESORIOS');db.session.add(cat);db.session.flush()
        a=ArticuloStock(categoria_id=cat.id,nombre='CUBO ORIGINAL',costo_administracion=2000000,fondo='CP VARIOS');db.session.add(a);db.session.flush()
        st.movement(a,3,1500000,'Compra inicial');db.session.commit()
        self.sale(credit=False,amount='100000',payment_amount=['100000'],cost_type=['Artículo'],cost_name=[a.id],cost_qty=['2'],cost_unit=['20000'])
        self.assertEqual(st.balance(a.id),1);t=f.report(self.d)['totals'];self.assertEqual((t['debe'],t['cash_expected']),(6000000,30000000))
        with self.assertRaises(ValueError):st.parse_cost(str(a.id),2,'20000')
    def test_auth_role_server_blocks_and_invalidates_sessions(self):
        self.app.config['AUTH_REQUIRED']=True;u=Usuario(nombre='VENDEDORA',login='ana',password_hash=generate_password_hash('clave_prueba_123'),rol='Vendedora');db.session.add(u);db.session.commit()
        client=self.app.test_client();self.assertEqual(client.get('/finanzas').status_code,302)
        client.get('/iniciar-sesion')
        with client.session_transaction() as s:csrf=s['csrf']
        result=client.post('/iniciar-sesion',data={'csrf':csrf,'login':'ana','password':'clave_prueba_123'});self.assertEqual(result.status_code,302)
        self.assertEqual(client.get('/usuarios').status_code,403)
        with client.session_transaction() as s:s['csrf']='test'
        r=client.post('/finanzas/sociedades',data={'csrf':'test','action':'partner','name':'NO'});self.assertEqual(r.status_code,403)
        u.session_version+=1;db.session.commit();self.assertEqual(client.get('/ventas').status_code,302)
    def test_all_new_pages_render_and_excel_template(self):
        client=self.app.test_client()
        for url in ['/inventario/compras','/inventario/articulos','/inventario/proveedores','/inventario/alias','/finanzas/creditos','/finanzas/pool','/finanzas/sociedades','/usuarios','/gestion/historial','/iniciar-sesion']:
            with self.subTest(url=url):self.assertEqual(client.get(url,follow_redirects=True).status_code,200)
        result=client.get('/inventario/compras/plantilla.xlsx');self.assertEqual(result.status_code,200);self.assertTrue(result.data.startswith(b'PK'))
        lot,c=self.lot_fixture();db.session.commit();self.assertEqual(client.get('/inventario/compras/'+str(lot.id)).status_code,200)
    def test_retoma_part_payment_is_not_bank_or_cash_and_cannot_be_reused(self):
        p=self.product(True)
        params=dict(credit=False,amount='1000000',payment_account=['EFECTIVO','RETOMA'],payment_amount=['500000','500000'],payment_retoma_id=['',p.id])
        o=self.sale(**params);t=f.report(self.d)['totals']
        self.assertEqual((t['cash_expected'],t['bank_received'],t['retoma_received']),(70000000,0,50000000))
        self.assertEqual(t['transfer'],0)
        with self.assertRaises(ValueError):self.sale(**params)
        db.session.rollback()
        buy=so.register_purchase(p,data(date=self.day,funding='600000',confirmed='1',purchase_mode='Parte de pago',origin_sale_id=o.id));db.session.commit()
        self.assertEqual(buy.ganancia,10000000)
        self.assertEqual(f.report(self.d)['totals']['cash_expected'],130000000)
        with self.assertRaises(ValueError):f.protect_managed_operation(o)
    def test_retoma_duplicate_within_sale_and_non_sale_rejected(self):
        p=self.product(True)
        params=dict(credit=False,amount='1000000',payment_account=['RETOMA','RETOMA'],payment_amount=['500000','500000'],payment_retoma_id=[p.id,p.id])
        with self.assertRaises(ValueError):self.sale(**params)
        db.session.rollback()
        with self.assertRaises(ValueError):self.sale(credit=False,kind='PD',amount='500000',payment_account=['RETOMA'],payment_amount=['500000'],payment_retoma_id=[p.id])
        self.assertEqual(db.session.query(Op).count(),0)
    def test_restore_cannot_bypass_dissolution_or_lot_reversal(self):
        from app.services.inventario_service import change_product
        p=self.product();p.archived=1
        for state in ('Entregado a socio','Anulado lote'):
            p.status=state;db.session.commit()
            with self.subTest(state=state),self.assertRaises(ValueError):
                change_product(p.id,'restore',{'revision':str(p.revision),'reason':'RESTAURAR POR ERROR'})
    def test_society_reactivation_preserves_equipment_snapshot(self):
        p=self.product();s,jon,other=self.partnership(p)
        original=db.session.get(PropiedadEquipo,p.id).participaciones
        params=dict(id=s.id,name=s.nombre,partner_id=[jon.id,other.id],capital=['50','50'],profit=['50','50'],active='0')
        so.save_society(data(**params));db.session.commit();self.assertFalse(s.activa)
        params['active']='1';so.save_society(data(**params));db.session.commit();self.assertTrue(s.activa)
        self.assertEqual(db.session.get(PropiedadEquipo,p.id).participaciones,original)
    def test_pool_purchase_cannot_be_edited_as_a_daily_movement(self):
        p=self.product(True);buy=so.register_purchase(p,data(date=self.day,funding='600000',confirmed='1'));db.session.commit()
        with self.assertRaises(ValueError):f.edit_operation(self.d,data(operation_id=buy.operacion_id))
        self.assertEqual(buy.ganancia,10000000)
    def test_existing_cash_sale_cannot_gain_an_untracked_credit_on_edit(self):
        o=self.sale(credit=False)
        with self.assertRaises(ValueError):
            f.edit_operation(self.d,data(operation_id=o.id,reason='CAMBIO DE MEDIO',description=o.description,seller='ANA',amount='650000',
                payment_account=['CRÉDITO'],payment_amount=['650000'],payment_ally_id=[self.ally.id],payment_person_id=[self.person.id],
                payment_bank_id=[self.bank.id],credit_approved='1',payment_credit_rate=['18'],payment_credit_mode=['Porcentaje']))
        self.assertEqual(db.session.query(CreditoVenta).count(),0)
        self.assertEqual(o.payments[0]['account'],'EFECTIVO')
    def test_financed_pool_allows_metadata_corrections_but_not_changed_costs(self):
        from app.services.inventario_service import change_product
        p=self.product(True);line=self.equipment_line();ref=db.session.get(Catalogo,line['reference_id'])
        supplier=db.session.scalar(db.select(Catalogo).where(Catalogo.kind=='supplier',Catalogo.name=='CP CELULARES'))
        p.reference_id=ref.id;p.color_id=line['color_id'];p.capacity_id=line['capacity_id'];p.supplier_id=supplier.id;p.location_id=line['location_id'];db.session.commit()
        so.register_purchase(p,data(date=self.day,funding='600000',confirmed='1'));db.session.commit()
        form={**{k:str(v) for k,v in line.items()},'brand_id':str(ref.parent_id),'supplier_id':str(supplier.id),'condition':'Usado','purchase_cop':'500000','reason':'CORREGIR REFERENCIA','revision':str(p.revision)}
        form.pop('shipping_cop');form.pop('purchase_price')
        change_product(p.id,'edit',form);self.assertEqual(p.model,ref.display_name);self.assertEqual(p.cost_cents,50000000)
        form.update(revision=str(p.revision),purchase_cop='550000')
        with self.assertRaises(ValueError):change_product(p.id,'edit',form)
    def test_vendedora_cannot_read_payroll_settings_or_financial_export(self):
        self.app.config['AUTH_REQUIRED']=True
        u=Usuario(nombre='VENDEDORA',login='v',rol='Vendedora',password_hash=generate_password_hash('clave_prueba_123'));db.session.add(u);db.session.commit()
        client=self.app.test_client()
        with client.session_transaction() as session:session.update(usuario_id=u.id,usuario_version=u.session_version)
        page=client.get('/finanzas?tab=personal')
        self.assertEqual(page.status_code,200);self.assertNotIn(b'name="action" value="config"',page.data)
        self.assertEqual(client.get('/finanzas/exportar?date='+self.day).status_code,403)

    def test_pool_credit_from_jornada_updates_equipment_and_extra_commission(self):
        p=self.product(True)
        operation=self.sale(p)
        credit=db.session.scalar(db.select(CreditoVenta).where(CreditoVenta.operacion_id==operation.id))
        self.assertEqual((p.status,p.payment_status,credit.neto),('Vendido','Pendiente',53300000))
        extra=db.session.scalar(db.select(ComisionPool).where(ComisionPool.operacion_id==operation.id))
        self.assertEqual(extra.monto,2000000)
        self.assertEqual(f.report(self.d)['totals']['debe'],1300000)
        self.settlement(credit)
        self.assertEqual((p.payment_status,p.paid_cents),('Pagado',53300000))
        self.assertEqual(db.session.query(ComisionPool).count(),1)

    def test_external_credit_keeps_imei_without_adding_owned_inventory(self):
        supplier=Catalogo(kind='supplier',name='EXTERNO PRUEBA',normal_key='EXTERNOPRUEBA',parent_id=0,active=1,supplier_category='Celulares')
        db.session.add(supplier);db.session.commit()
        operation=self.sale(cost_type=['Proveedor'],cost_name=[supplier.name],cost_category=['Celulares'],
            cost_qty=['1'],cost_unit=['500000'],cost_external_imei=['490154203237518'])
        credit=db.session.scalar(db.select(CreditoVenta).where(CreditoVenta.operacion_id==operation.id))
        self.assertIsNone(operation.product_id)
        self.assertEqual(operation.costs[0]['external_imei'],'490154203237518')
        self.assertEqual(db.session.query(Producto).count(),0)
        self.settlement(credit)
        self.assertEqual(credit.estado,'Pagado')
        self.assertEqual(f.report(self.d)['totals']['debe'],3300000)
        self.assertEqual(db.session.query(Producto).count(),0)

    def test_pool_purchase_from_jornada_is_not_sale_and_rejects_duplicate(self):
        p=self.product(True);client=self.app.test_client()
        with client.session_transaction() as session:session['csrf']='test'
        payload=dict(csrf='test',date=self.day,action='pool_purchase',revision=str(self.d.revision),
            product_id=str(p.id),funding='600000',purchase_mode='Compra directa',confirmed='1',return_tab='movimientos')
        result=client.post('/finanzas',data=payload,follow_redirects=True)
        self.assertEqual(result.status_code,200)
        buy=db.session.get(CompraPool,p.id);self.assertIsNotNone(buy)
        self.assertEqual(buy.ganancia,10000000)
        totals=f.report(self.d)['totals']
        self.assertEqual((totals['sales_count'],totals['debe'],totals['cash_expected']),(0,10000000,30000000))
        self.assertEqual(p.status,'Disponible')
        client.post('/finanzas',data=payload)
        self.assertEqual(db.session.query(CompraPool).count(),1)
        self.assertEqual(db.session.query(Op).count(),1)
        self.assertIn(b'Compras POOL de esta jornada',result.data)

    def test_pool_purchase_validation_and_closed_day_leave_no_partial_changes(self):
        p=self.product(True);client=self.app.test_client()
        with client.session_transaction() as session:session['csrf']='test'
        payload=dict(csrf='test',date=self.day,action='pool_purchase',revision=str(self.d.revision),product_id=str(p.id),funding='400000',confirmed='1')
        result=client.post('/finanzas',data=payload)
        self.assertIn('El aporte debe cubrir'.encode(),result.data)
        self.assertIn(b'id="finance-restore"',result.data)
        self.assertEqual(db.session.query(CompraPool).count(),0)
        self.d.status='Cerrada';self.d.snapshot={'totals':f.report(self.d)['totals'],'counted':0,'difference':0};db.session.commit()
        payload['funding']='600000';client.post('/finanzas',data=payload)
        self.assertEqual(db.session.query(Op).count(),0)

    def test_navigation_in_sales_and_summary_preserve_closed_snapshot(self):
        from flask import url_for
        with self.app.test_request_context():
            self.assertEqual(url_for('gestion.sociedades'),'/ventas/sociedades')
            self.assertEqual(url_for('gestion.inversion'),'/ventas/inversion')
        client=self.app.test_client()
        for path in ['/ventas','/ventas/sociedades','/ventas/inversion']:
            page=client.get(path).get_data(as_text=True)
            self.assertIn('href="/ventas/sociedades"',page)
            self.assertIn('href="/ventas/inversion"',page)
        page=client.get('/finanzas?date='+self.day).get_data(as_text=True)
        self.assertIn('data-summary="debe"',page)
        self.assertIn('data-summary="haber"',page)
        self.assertNotIn('Créditos netos vendidos hoy',page)
        self.assertNotIn('href="/ventas/sociedades"',page)
        self.assertNotIn('href="/ventas/inversion"',page)
        self.assertEqual(client.get('/finanzas/pool').status_code,302)
        self.assertIn('#compra-pool',client.get('/finanzas/pool').location)
        self.assertEqual(client.get('/finanzas/sociedades').status_code,200)
        self.assertEqual(client.get('/inventario/inversion').status_code,200)
        totals=f.report(self.d)['totals'];totals['debe']=12345600
        self.d.status='Cerrada';self.d.snapshot={'totals':totals,'counted':0,'difference':0};db.session.commit()
        page=client.get('/finanzas?date='+self.day).get_data(as_text=True)
        self.assertIn('$ 123.456,00',page)
        self.assertNotIn('id="pool-purchase-form"',page)

    def test_pool_commission_in_jornada_respects_origin_and_debits_once(self):
        from datetime import date,timedelta
        from app.services.pool_jornada import context
        p=self.product(True);self.sale(p,False)
        commission=db.session.scalar(db.select(ComisionPool))
        yesterday=(date.fromisoformat(self.day)-timedelta(days=1)).isoformat()
        self.assertEqual(context(yesterday)['commissions'],[])
        old=f.open_day(yesterday);db.session.commit()
        with self.assertRaises(ValueError):so.pay_pool_commission(data(commission_id=commission.id,date=yesterday,confirmed='1'))
        db.session.rollback()
        before=f.report(self.d)['totals'];client=self.app.test_client()
        with client.session_transaction() as session:session['csrf']='test'
        payload=dict(csrf='test',date=self.day,action='pool_commission',revision=str(self.d.revision),
            commission_id=str(commission.id),confirmed='1',return_tab='proveedores')
        result=client.post('/finanzas',data=payload,follow_redirects=True)
        self.assertEqual(result.status_code,200)
        self.assertIsNotNone(commission.pago_operacion_id)
        after=f.report(self.d)['totals']
        self.assertEqual(after['debe'],before['debe'])
        self.assertEqual(after['cash_expected'],before['cash_expected']-2000000)
        client.post('/finanzas',data=payload)
        self.assertEqual(f.report(self.d)['totals']['cash_expected'],after['cash_expected'])
        self.assertIn(('Entregada el '+self.day).encode(),result.data)

    def test_vendedora_cannot_register_pool_purchase_from_jornada(self):
        p=self.product(True);self.app.config['AUTH_REQUIRED']=True
        u=Usuario(nombre='VENDEDORA',login='prueba',rol='Vendedora',password_hash=generate_password_hash('clave_prueba_123'))
        db.session.add(u);db.session.commit();client=self.app.test_client()
        with client.session_transaction() as session:session.update(usuario_id=u.id,usuario_version=u.session_version,csrf='test')
        result=client.post('/finanzas',data=dict(csrf='test',date=self.day,action='pool_purchase',revision=str(self.d.revision),product_id=p.id,funding='600000',confirmed='1'))
        self.assertEqual(result.status_code,403)
        self.assertEqual(db.session.query(CompraPool).count(),0)
        page=client.get('/finanzas').get_data(as_text=True)
        self.assertNotIn('id="pool-purchase-form"',page)
        self.assertNotIn('data-summary="debe"',page)
        self.assertIn('data-summary="sales_count"',page)
