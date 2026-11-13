from jornada_fixtures import opening
"""Distribución mixta, datáfono sin banco y correcciones de pagos."""
from app.sqlite_resources import sqlite_connection
import secrets
import tempfile
import unittest
import sqlite3
from decimal import Decimal
from pathlib import Path
from werkzeug.datastructures import MultiDict

from app import create_app
from app.extensions import db
from app.models import PersonaContable, BancoDestino, PersonaBanco, ConsignacionBancaria, Catalogo
from app.models.finanzas import OperacionFinanciera, PagoProveedor, AuditoriaFinanciera
from app.services import finanzas_service as finance
from migrations.finanzas_v14 import upgrade as upgrade_v14


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=create_app({'TESTING':True,'DATABASE':str(Path(self.tmp.name)/'data.sqlite'),'SECRET_KEY':'tests'})
        self.client=self.app.test_client();self.day='2026-10-20'
        self.client.get('/finanzas?date='+self.day)
        with self.client.session_transaction() as session:self.csrf=session['csrf']
        self.post('open',**opening(self.day,('EMILY',)))
        with self.app.app_context():
            person=PersonaContable(nombre='EMILY',identificacion='111',tipo='Natural')
            bank=BancoDestino(nombre='BANCO PRUEBA')
            db.session.add_all([person,bank]);db.session.flush()
            self.person,self.bank=person.id,bank.id
            db.session.add(PersonaBanco(persona_id=person.id,banco_id=bank.id));db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove();db.engine.dispose()
        self.tmp.cleanup()

    def post(self,action,**kwargs):
        with self.app.app_context():
            day=finance.find_day(self.day)
            revision=day.revision if day else 0
        fields=dict(csrf=self.csrf,date=self.day,action=action,revision=str(revision),token=secrets.token_hex(16),**kwargs)
        values=MultiDict((key,item) for key,value in fields.items() for item in (value if isinstance(value,list) else [value]))
        return self.client.post('/finanzas',data=values)

    def test_external_imei_and_obligations_are_as_of_selected_date(self):
        args=dict(kind='Venta',description='EQUIPO EXTERNO',seller='EMILY',amount='700000',
                  payment_account=['EFECTIVO'],payment_amount=['700000'],cost_type=['Proveedor'],
                  cost_name=['CURI'],cost_category=['Celulares'],cost_qty=['1'],cost_unit=['580000'])
        self.assertIn('IMEI',self.post('operation',**args).get_data(as_text=True))
        self.assertEqual(self.post('operation',**args,cost_external_imei=['490154203237518']).status_code,302)
        with self.app.app_context():
            from app.models import Producto
            op=db.session.scalar(db.select(OperacionFinanciera))
            self.assertEqual(op.costs[0]['external_imei'],'490154203237518')
            self.assertEqual(db.session.query(Producto).count(),0)
            self.assertEqual(finance.obligations('2026-10-19'),[])
            self.assertEqual(finance.obligations('2026-10-20')[0]['origin_date'],'2026-10-20')
            future=finance.open_day('2026-10-21')
            db.session.add(PagoProveedor(day_id=future.id,operation_id=op.id,cost_index=0,
                                         amount=10000000,account='EFECTIVO',token=secrets.token_hex(16)))
            db.session.commit()
            self.assertEqual(finance.obligations('2026-10-20')[0]['balance'],58000000)
            self.assertEqual(finance.obligations('2026-10-21')[0]['balance'],48000000)

    def test_five_means_no_duplicate_person_and_card_without_bank(self):
        form=self.client.get('/finanzas?date='+self.day+'&accion=registrar').get_data(as_text=True)
        self.assertIn('+ Agregar medio',form)
        self.assertNotIn('Medio 5',form)
        self.assertNotIn('Persona registrada en información contable (opcional)',form)
        result=self.post('operation',kind='Venta',description='ACCESORIOS',seller='EMILY',amount='50000',
            payment_account=['EFECTIVO','TRANSFERENCIA','DATÁFONO','EFECTIVO','DATÁFONO'],
            payment_amount=['10000','10000','10500','10000','10500'],payment_person_id=['',str(self.person),str(self.person),'',str(self.person)],
            payment_bank_id=['',str(self.bank),'','',''])
        self.assertEqual(result.status_code,302,result.get_data(as_text=True)[:700])
        with self.app.app_context():
            o=db.session.scalar(db.select(OperacionFinanciera))
            self.assertEqual(len(o.payments),5)
            self.assertEqual(o.person_id,self.person)
            cards=[c for c in db.session.scalars(db.select(ConsignacionBancaria)) if c.banco_id is None]
            self.assertEqual(len(cards),2)
            self.assertEqual(sum(c.monto for c in cards),Decimal('21000.00'))
        self.assertIn('DATÁFONO',self.client.get('/modulos/tributario/').get_data(as_text=True))
        self.assertIn('DATÁFONO',self.client.get('/finanzas?date='+self.day+'&tab=cierre').get_data(as_text=True))

    def test_device_cost_allocation_and_supplier_edit_history(self):
        response=self.post('operation',kind='Venta',description='EQUIPO',seller='EMILY',amount='700000',
            payment_account=['EFECTIVO','DATÁFONO'],payment_amount=['500000','210000'],
            payment_person_id=['',str(self.person)],payment_bank_id=['',''],
            cost_type=['Proveedor'],cost_name=['CURI'],cost_category=['Celulares'],cost_qty=['1'],cost_unit=['580000'],cost_external_imei=['490154203237518'])
        self.assertEqual(response.status_code,302)
        with self.app.app_context():
            operation=db.session.scalar(db.select(OperacionFinanciera));oid=operation.id
            obligation=finance.obligations()[0]
            self.assertEqual((obligation['from_cash'],obligation['from_admin']),(38000000,20000000))
        self.assertEqual(self.post('supplier_payment',operation_id=str(oid),cost_index='0',amount='200000',
            account='EFECTIVO',reason='PRIMER ABONO').status_code,302)
        with self.app.app_context():pid=db.session.scalar(db.select(PagoProveedor.id))
        self.assertEqual(self.post('edit_supplier_payment',payment_id=str(pid),amount='150000',
            account='TRANSFERENCIA',payment_person_id=str(self.person),payment_bank_id=str(self.bank),reason='CORREGIR PAGO').status_code,302)
        with self.app.app_context():
            c=db.session.scalar(db.select(ConsignacionBancaria).where(ConsignacionBancaria.supplier_payment_id==pid))
            self.assertEqual(c.monto,Decimal('150000.00'))
            self.assertEqual(db.session.get(PagoProveedor,pid).amount,15000000)
            self.assertTrue(db.session.scalar(db.select(AuditoriaFinanciera.id).where(AuditoriaFinanciera.action=='Edición de pago a proveedor')))
        self.assertEqual(self.post('edit_supplier_payment',payment_id=str(pid),amount='150000',
            account='EFECTIVO',reason='SE PAGÓ EN CAJA').status_code,302)
        with self.app.app_context():
            self.assertFalse(db.session.scalar(db.select(ConsignacionBancaria).where(ConsignacionBancaria.supplier_payment_id==pid)).activa)
            self.assertEqual(finance.obligations()[0]['balance'],43000000)

    def test_supplier_catalog_and_drink_prices(self):
        with self.app.app_context():
            categories={p.name:p.supplier_category for p in db.session.scalars(db.select(Catalogo).where(Catalogo.kind=='supplier'))}
            self.assertEqual(categories['CP CELULARES'],'Celulares')
            self.assertEqual(categories['CP VARIOS'],'Accesorios')
            self.assertEqual(categories['GABRIEL'],'Ambos')
            self.assertEqual(finance.DRINK_PRICES['CORONA'],400000)
        result=self.post('operation',kind='Venta',description='BEBIDA',seller='EMILY',amount='5000',
            payment_account=['EFECTIVO'],payment_amount=['5000'],cost_type=['Bebida'],
            cost_name=['CORONA'],cost_qty=['1'],cost_unit=['3500'])
        self.assertEqual(result.status_code,200)
        with self.app.app_context():self.assertEqual(db.session.scalar(db.select(db.func.count(OperacionFinanciera.id))),0)

    def test_migration_preserves_existing_accounting_records(self):
        with self.app.app_context():
            row=ConsignacionBancaria(persona_id=self.person,banco_id=self.bank,monto=Decimal('123.00'),
                                     referencia='ANTERIOR')
            db.session.add(row);db.session.commit();record_id=row.id
            db.engine.dispose()
        path=Path(self.tmp.name)/'data.sqlite'
        with sqlite_connection(path) as conn:
            conn.execute('CREATE TABLE consignaciones_antiguas AS SELECT * FROM consignaciones_bancarias')
            conn.execute('DELETE FROM schema_version WHERE version=14')
            conn.execute('PRAGMA foreign_keys=OFF')
            conn.execute('DROP TABLE consignaciones_bancarias')
            conn.execute('''CREATE TABLE consignaciones_bancarias (
                id INTEGER PRIMARY KEY,persona_id INTEGER NOT NULL REFERENCES personas_contables(id),
                banco_id INTEGER NOT NULL REFERENCES bancos_destino(id),monto NUMERIC(14,2) NOT NULL,
                fecha DATETIME NOT NULL,referencia VARCHAR(100),
                finance_operation_id INTEGER REFERENCES finance_operation(id),payment_index INTEGER,
                supplier_payment_id INTEGER REFERENCES finance_supplier_payment(id),activa BOOLEAN NOT NULL DEFAULT 1)''')
            conn.execute('INSERT INTO consignaciones_bancarias SELECT * FROM consignaciones_antiguas')
            conn.execute('DROP TABLE consignaciones_antiguas')
        upgrade_v14(path);upgrade_v14(path)
        with sqlite_connection(path) as conn:
            self.assertEqual(conn.execute('SELECT id,referencia FROM consignaciones_bancarias').fetchall(),[(record_id,'ANTERIOR')])
            self.assertEqual(conn.execute("SELECT [notnull] FROM pragma_table_info('consignaciones_bancarias') WHERE name='banco_id'").fetchone()[0],0)
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(),[])


if __name__=='__main__':unittest.main()
