"""Compra atómica en el local, costo comercial y comisiones sin doble utilidad."""
import copy
import json
import secrets
import unittest
from datetime import date, timedelta
from unittest.mock import patch
from werkzeug.security import generate_password_hash
import test_gestion_v16 as fixture
from app.extensions import db
from app.models import Producto, Catalogo, Movimiento
from app.models.finanzas import Jornada, OperacionFinanciera as Op
from app.models.gestion import CompraPool, ComisionPool, CreditoVenta, RegistroGestion, Usuario
from app.services import finanzas_service as finance, sociedad_service as society
from app.services import pool_compra_service as purchase


class AjustesPoolTests(unittest.TestCase):
    setUp = fixture.GestionTests.setUp
    tearDown = fixture.GestionTests.tearDown
    sale = fixture.GestionTests.sale
    settlement = fixture.GestionTests.settlement

    def form(self, **changes):
        reference = db.session.scalar(db.select(Catalogo).where(Catalogo.kind=='reference', Catalogo.active==1))
        def item(kind, parent=None):
            query = db.select(Catalogo).where(Catalogo.kind==kind, Catalogo.active==1)
            if parent:query = query.where(Catalogo.parent_id==parent)
            return db.session.scalar(query)
        data = dict(date=self.day, revision=self.d.revision, token=secrets.token_hex(16),
            imei='990000000001232', brand_id=reference.parent_id, reference_id=reference.id,
            color_id=item('color',reference.id).id, capacity_id=item('capacity',reference.id).id,
            location_id=item('location').id, purchase_cop='500000', purchase_gain='100000',
            purchase_commission='20000', purchase_other='0', funding='620000', confirmed='1', seller='ANA')
        # El catálogo de demostración también contiene bodegas; la compra recibe en local.
        local = next(c for c in db.session.scalars(db.select(Catalogo).where(Catalogo.kind=='location',Catalogo.active==1)) if 'BODEGA' not in c.name.upper())
        data['location_id']=local.id
        data.update(changes)
        return fixture.data(**data)

    def buy(self, **changes):
        product = purchase.register(self.d,self.form(**changes),'ANA')
        db.session.commit()
        return product

    def client(self, role='Vendedora'):
        self.app.config['AUTH_REQUIRED']=True
        user=Usuario(nombre='ANA',login=secrets.token_hex(5),rol=role,password_hash=generate_password_hash('PruebaSegura2026!'))
        db.session.add(user);db.session.commit()
        client=self.app.test_client()
        with client.session_transaction() as session:
            session['usuario_id']=user.id;session['usuario_version']=user.session_version;session['csrf']='ajustes'
        return client

    def test_buy_creates_equipment_movement_and_pending_once_with_daily_gain(self):
        form=self.form();product=purchase.register(self.d,form,'ANA');db.session.commit()
        buy=db.session.get(CompraPool,product.id);op=db.session.get(Op,buy.operacion_id)
        self.assertEqual((product.cost_cents,buy.pago_cliente,buy.ganancia,buy.aporte),(52000000,50000000,10000000,62000000))
        self.assertEqual(buy.pago_cliente+buy.ganancia,60000000)
        self.assertEqual((op.seller,op.token,product.status),('ANA',form['token'],'Disponible'))
        self.assertEqual(db.session.scalar(db.select(db.func.count(Movimiento.id))),1)
        totals=finance.report(self.d)['totals']
        self.assertEqual((totals['debe'],totals['gross'],totals['sales_count']),(10000000,0,0))
        self.assertEqual(len(purchase.pending()),1)
        with self.assertRaises(ValueError):purchase.register(self.d,form,'ANA')
        db.session.rollback()
        with self.assertRaises(ValueError):purchase.register(self.d,self.form(),'ANA')
        db.session.rollback()
        self.assertEqual(db.session.scalar(db.select(db.func.count(Producto.id))),1)
        self.assertEqual(db.session.scalar(db.select(db.func.count(Op.id))),1)

    def test_purchase_failure_after_product_flush_rolls_back_everything(self):
        with patch('app.services.sociedad_service.assign_ownership',side_effect=ValueError('Fallo de prueba después de crear el equipo')):
            with self.assertRaises(ValueError):purchase.register(self.d,self.form(),'ANA')
            db.session.rollback()
        for model in (Producto,CompraPool,Op,Movimiento):
            self.assertEqual(db.session.scalar(db.select(db.func.count()).select_from(model)),0)
        self.assertEqual(purchase.pending(),[])

    def test_invalid_total_and_missing_confirmation_do_not_create_equipment(self):
        for change in ({'funding':'600000'},{'confirmed':''},{'purchase_commission':'-1'}, {'purchase_other':'1000','funding':'621000'}):
            with self.assertRaises(ValueError):purchase.register(self.d,self.form(**change),'ANA')
            db.session.rollback()
            self.assertEqual(db.session.scalar(db.select(db.func.count(Producto.id))),0)
        p=self.buy(purchase_commission='0',funding='600000')
        self.assertEqual((p.cost_cents,society.capital_basis(p)),(50000000,60000000))

    def test_closed_day_cannot_acquire_and_review_does_not_change_money(self):
        p=self.buy();before=copy.deepcopy(finance.report(self.d)['totals']);event=purchase.pending()[0][0]
        self.d.status='Cerrada';self.d.snapshot={'totals':before};db.session.commit()
        with self.assertRaises(ValueError):purchase.register(self.d,self.form(),'ANA')
        db.session.rollback()
        purchase.review(p.id,event.id,'Garantía y datos físicos comprobados');db.session.commit()
        self.assertEqual(purchase.pending(),[])
        self.assertEqual(self.d.snapshot,{'totals':before})
        self.assertEqual(db.session.scalar(db.select(db.func.count(Op.id))),1)
        with self.assertRaises(ValueError):purchase.review(p.id,event.id,'Repetido')

    def test_seller_registers_purchase_under_own_identity_and_cannot_review_or_reconcile_legacy(self):
        client=self.client()
        data=self.form(seller='OTRA PERSONA',action='pool_purchase',csrf='ajustes')
        response=client.post('/finanzas',data=data)
        self.assertEqual(response.status_code,302)
        buy=db.session.scalar(db.select(CompraPool));self.assertEqual(db.session.get(Op,buy.operacion_id).seller,'ANA')
        event=purchase.pending()[0][0]
        response=client.post(f'/inventario/{buy.producto_id}/revision-pool',data=dict(csrf='ajustes',pending_id=event.id,note='No permitido'))
        self.assertEqual(response.status_code,403)
        response=client.post('/finanzas',data=dict(csrf='ajustes',action='pool_purchase',product_id=buy.producto_id))
        self.assertEqual(response.status_code,403)

    def test_seller_commercial_cost_is_saved_and_private_acquisition_cost_is_not_sent(self):
        p=self.buy();client=self.client()
        html=client.get('/finanzas?date='+self.day+'&accion=registrar').get_data(as_text=True)
        payload=html.split('id="finance-equipment-costs">',1)[1].split('</script>',1)[0]
        self.assertEqual(json.loads(payload),{})
        form=fixture.data(csrf='ajustes',action='operation',date=self.day,revision=self.d.revision,
            kind='Venta',description='POOL COMERCIAL VARIABLE',seller='ANA',token=secrets.token_hex(16),amount='1100000',minor_cost='',
            cost_type=['Equipo'],cost_name=[p.imei],cost_qty=['1'],cost_unit=['800000'],
            payment_account=['CRÉDITO'],payment_amount=['1100000'],payment_ally_id=[self.ally.id],
            payment_person_id=[self.person.id],payment_bank_id=[self.bank.id],credit_approved='1',
            payment_credit_mode=['Porcentaje'],payment_credit_rate=['18'])
        response=client.post('/finanzas',data=form);self.assertEqual(response.status_code,302)
        op=db.session.scalar(db.select(Op).where(Op.kind=='Venta'));db.session.refresh(p)
        self.assertEqual((p.cost_cents,p.pool_assigned_cost_cents,p.pool_admin_gain_cents),(52000000,80000000,18000000))
        self.assertEqual(op.amount,90200000)
        self.assertEqual(op.amount-sum(c['amount'] for c in op.costs),8200000)
        self.assertEqual(finance.report(self.d)['totals']['debe'],18200000)

    def test_late_credit_and_sale_commission_do_not_duplicate_origin_profit(self):
        self.day=(date.fromisoformat(self.day)-timedelta(days=1)).isoformat();self.d.date=self.day;db.session.commit()
        p=self.buy();op=self.sale(p,cost_unit=['800000'],amount='1100000',payment_amount=['1100000'])
        credit=db.session.scalar(db.select(CreditoVenta));commission=db.session.scalar(db.select(ComisionPool))
        before=finance.report(self.d)['totals']['debe']
        later=(date.fromisoformat(self.day)+timedelta(days=1)).isoformat()
        receiving=Jornada(date=later,config=copy.deepcopy(self.d.config));db.session.add(receiving);db.session.commit()
        self.settlement(credit,20000000,date=later)
        self.settlement(credit,70200000,ref='FINAL',date=later)
        society.pay_pool_commission(fixture.data(commission_id=commission.id,date=later,confirmed='1',payment_source='ADMINISTRACIÓN DIRECTA',reference='ADMIN ENTREGA'))
        db.session.commit()
        self.assertEqual(finance.report(self.d)['totals']['debe'],before)
        self.assertEqual(finance.report(receiving)['totals']['debe'],0)
        self.assertEqual(credit.recibido,90200000)

    def test_package_editor_keeps_automatic_commission_once(self):
        p=self.buy();op=self.sale(p,credit=False,amount='800000',payment_amount=['800000'],cost_unit=['620000'])
        client=self.app.test_client()
        html=client.get('/finanzas?date='+self.day).get_data(as_text=True)
        editor=html.split('class="linked-cost-rows"',1)[1].split('</div>',1)[0]
        self.assertNotIn('COMISIÓN EXTRA POOL',editor)
        finance.update_equipment_costs(self.d,fixture.data(operation_id=op.id,minor_cost='0',reason='Comprobar paquete'))
        db.session.commit()
        self.assertEqual(sum(c['amount'] for c in op.costs if c['type']=='Comisión POOL'),2000000)

    def test_two_principals_are_rejected_without_changing_configuration(self):
        cfg=copy.deepcopy(self.d.config)
        values={key:str(cfg[key]//100) for key in ('normal_base','sandra_extra','extra_a','extra_b','normal_return','sandra_sunday','sandra_control_sunday','sandra_control_work','sandra_control_absent')}
        form=fixture.data(**values,reviewed='1',actor='ANA',staff_name=['ANA','LUZ'],staff_role=['Principal','Principal'],staff_salary=['0','0'],staff_attended=['0','1'])
        with self.assertRaisesRegex(ValueError,'Solo puede haber una'):finance.save_config(self.d,form)
        self.assertEqual(self.d.config,cfg)
        form.setlist('staff_role',['Principal','Secundaria']);finance.save_config(self.d,form)
        self.assertEqual([p['role'] for p in self.d.config['staff']],['Principal','Secundaria'])


if __name__=='__main__':unittest.main()
