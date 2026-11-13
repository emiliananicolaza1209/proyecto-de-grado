"""Totales por banco consistentes con el control anual y sin alterar movimientos."""
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from werkzeug.datastructures import MultiDict
from app import create_app
from app.extensions import db
from app.models import PersonaContable, BancoDestino, PersonaBanco, ConsignacionBancaria
from app.models.finanzas import OperacionFinanciera
from app.services.contabilidad_service import evaluar_estado_renta, resumir_por_banco
from app.services import finanzas_service as finance


class BankSummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=create_app(dict(TESTING=True,DATABASE=str(Path(self.tmp.name)/'db.sqlite'),SECRET_KEY='test'))
        self.ctx=self.app.app_context();self.ctx.push()
        self.emily=PersonaContable(nombre='EMILY PRUEBA',identificacion='QA01',tipo='Natural')
        self.sandra=PersonaContable(nombre='SANDRA PRUEBA',identificacion='QA02',tipo='Natural')
        self.b1=BancoDestino(nombre='BANCOLOMBIA');self.b2=BancoDestino(nombre='BANCO DE BOGOTÁ');self.b3=BancoDestino(nombre='NEQUI')
        db.session.add_all([self.emily,self.sandra,self.b1,self.b2,self.b3]);db.session.flush()
        for p,b in [(self.emily,self.b1),(self.emily,self.b2),(self.emily,self.b3),(self.sandra,self.b1)]:
            db.session.add(PersonaBanco(persona_id=p.id,banco_id=b.id))
        db.session.commit()
        self.client=self.app.test_client()
        with self.client.session_transaction() as session:session['csrf']='test'

    def tearDown(self):
        db.session.remove();db.engine.dispose();self.ctx.pop();self.tmp.cleanup()

    def deposit(self,amount,bank=None,person=None,date='2026-10-01',active=True):
        row=ConsignacionBancaria(persona_id=(person or self.emily).id,banco_id=bank.id if bank else None,
                                monto=Decimal(amount),fecha=datetime.fromisoformat(date),activa=active)
        db.session.add(row);db.session.commit();return row

    def summary(self,person=None,year=2026):
        p=person or self.emily
        return resumir_por_banco([p],year)[p.id]

    def test_same_year_active_entries_and_person_only(self):
        self.deposit('130000',self.b1);self.deposit('35000',self.b2)
        self.deposit('1000',self.b1,date='2025-12-31T23:59:59')
        self.deposit('1000',self.b2,date='2027-01-01T00:00:00')
        self.deposit('1000',self.b1,active=False);self.deposit('6155000',self.b1,person=self.sandra)
        result=self.summary();rows={b['banco_id']:b for b in result['bancos']}
        self.assertEqual(result['total'],Decimal('165000'))
        self.assertEqual(result['total'],evaluar_estado_renta(self.emily.id,2026)['total_consignado'])
        self.assertEqual(rows[self.b1.id]['porcentaje'],Decimal('78.79'))
        self.assertEqual(rows[self.b2.id]['porcentaje'],Decimal('21.21'))
        self.assertEqual((rows[self.b3.id]['total'],rows[self.b3.id]['porcentaje']),(0,0))
        self.assertEqual(self.summary(self.sandra)['total'],Decimal('6155000'))
        self.assertEqual(self.summary(year=2025)['total'],Decimal('1000'))

    def test_missing_bank_and_historic_unlinked_bank_reconcile(self):
        historic=BancoDestino(nombre='BANCO HISTÓRICO');db.session.add(historic);db.session.commit()
        self.deposit('100.10',historic);self.deposit('200.20')
        result=self.summary();rows={b['banco_id']:b for b in result['bancos']}
        self.assertEqual(result['total'],Decimal('300.30'))
        self.assertIn(historic.id,rows);self.assertIn(None,rows)
        self.assertEqual(rows[None]['total'],Decimal('200.20'))
        self.assertEqual(sum(b['total'] for b in rows.values()),evaluar_estado_renta(self.emily.id,2026)['total_consignado'])

    def test_zero_amounts_and_full_year_not_history_limit(self):
        self.assertEqual(self.summary()['total'],0)
        self.assertTrue(all(b['porcentaje']==0 for b in self.summary()['bancos']))
        db.session.add_all([ConsignacionBancaria(persona_id=self.emily.id,banco_id=self.b1.id,monto=Decimal('1.01'),
            fecha=datetime(2026,1,1)) for _ in range(160)])
        db.session.commit();result=self.summary()
        self.assertEqual(result['total'],Decimal('161.60'))
        self.assertEqual(result['bancos'][0]['cantidad'],160)
        self.assertEqual(result['bancos'][0]['porcentaje'],100)
        self.assertEqual(resumir_por_banco([],2026),{})

    def test_edit_bank_and_amount_updates_summary_without_modifying_sale(self):
        row=self.deposit('1000',self.b1)
        operation=OperacionFinanciera(day_id=finance.open_day('2026-10-01').id,token='bank-summary-op',kind='Venta',description='PRUEBA',seller='ANA',amount=100000,minor_cost=0,costs=[],payments=[])
        db.session.add(operation);db.session.commit()
        reply=self.client.post(f'/modulos/tributario/consignacion/{row.id}/editar',data=dict(csrf='test',persona_id=self.emily.id,
            banco_id=self.b2.id,monto='1500.50',fecha='2026-10-01',motivo='CORRECCIÓN DE BANCO'))
        self.assertEqual(reply.status_code,302)
        rows={b['banco_id']:b for b in self.summary()['bancos']}
        self.assertEqual(rows[self.b1.id]['total'],0);self.assertEqual(rows[self.b2.id]['total'],Decimal('1500.50'))
        self.assertEqual(operation.amount,100000)

    def test_finance_transfer_and_card_count_once_with_unassigned_card_group(self):
        day=finance.open_day('2026-10-01');cfg=dict(day.config)
        cfg.update(reviewed=True,actor='ANA',staff=[dict(name='ANA',role='Principal',salary=0,attended=True)])
        day.config=cfg;db.session.commit()
        finance.add_operation(day,MultiDict([('kind','Venta'),('description','MEDIOS MIXTOS'),('seller','ANA'),('token','a'*32),
            ('amount','3000'),('minor_cost',''),('payment_account','TRANSFERENCIA'),('payment_account','DATÁFONO'),
            ('payment_amount','2000'),('payment_amount','1050'),('payment_person_id',str(self.emily.id)),('payment_person_id',str(self.emily.id)),
            ('payment_bank_id',str(self.b1.id)),('payment_bank_id','')]))
        db.session.commit();result=self.summary();rows={b['banco_id']:b for b in result['bancos']}
        self.assertEqual(result['total'],Decimal('3050'))
        self.assertEqual(rows[self.b1.id]['total'],Decimal('2000'));self.assertEqual(rows[None]['total'],Decimal('1050'))
        count=db.session.query(ConsignacionBancaria).count()
        self.client.get('/modulos/tributario/?detalle_bancos='+str(self.emily.id))
        self.client.get('/modulos/tributario/?detalle_bancos='+str(self.emily.id))
        self.assertEqual(db.session.query(ConsignacionBancaria).count(),count)

    def test_detail_selection_year_fallback_empty_page_and_existing_progress(self):
        self.deposit('1000',self.b1,date='2025-01-01')
        reply=self.client.get('/modulos/tributario/?anio=2025&detalle_bancos='+str(self.emily.id))
        html=reply.get_data(as_text=True);self.assertEqual(reply.status_code,200)
        self.assertIn('id="desglose-bancos" open',html)
        self.assertIn('Uso del umbral',html);self.assertIn('Historial de consignaciones',html)
        self.assertIn('100.00 % del total',html)
        self.assertIn('name="anio" value="2025"',html)
        self.assertEqual(self.client.get('/modulos/tributario/?detalle_bancos=999999').status_code,200)
        db.session.execute(db.delete(ConsignacionBancaria));db.session.execute(db.delete(PersonaBanco));db.session.execute(db.delete(PersonaContable));db.session.commit()
        empty=self.client.get('/modulos/tributario/').get_data(as_text=True)
        self.assertNotIn('id="bank-breakdown-form"',empty)

if __name__=='__main__':unittest.main()
