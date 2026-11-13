"""Regresiones de unidades, referencias legibles y formularios reales."""
import csv
import io
import json
import secrets
import unittest
from datetime import datetime
from decimal import Decimal
from html.parser import HTMLParser
from openpyxl import load_workbook
from app.extensions import db
from app.models import Producto, Cobro
from app.models.contabilidad import PersonaContable, BancoDestino, ConsignacionBancaria
from app.models.finanzas import Jornada, OperacionFinanciera as Op
from app.services import reportes_service as reports, reportes_presentacion as presentation
from test_reportes_v17 import ReportsTests as ReportFixture


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__();self.tags=[];self.feed(html)
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class PresentationTests(unittest.TestCase):
    def setUp(self):
        import test_reportes_v17 as report_fixture
        report_fixture.ReportsTests.setUp(self)
        # La presentación de movimientos requiere una jornada preparada en V18.2.
        d=db.session.get(Jornada,self.did)
        d.config={**d.config,'reviewed':True,'actor':'ANA','staff':[dict(name='ANA',role='Principal',salary=0,attended=True)]}
        db.session.commit()
    tearDown = ReportFixture.tearDown
    login_role = ReportFixture.login_role

    def accounting_record(self):
        person=PersonaContable(id=44,nombre='TITULAR DE PRUEBA',identificacion='000044',tipo='Natural')
        bank=BancoDestino(id=77,nombre='BANCO DE PRUEBA')
        db.session.add_all([person,bank]);db.session.flush()
        db.session.add(ConsignacionBancaria(persona_id=person.id,banco_id=bank.id,
            monto=Decimal('120000.25'),fecha=datetime.fromisoformat(self.day)))
        db.session.commit()

    def test_accounting_names_and_pesos_without_changing_source_contract(self):
        self.accounting_record();raw=reports.accounting(self.args)
        self.assertEqual(raw['filas'][0]['monto'],12000025)
        view=presentation.present('contable',raw,self.args)
        self.assertIn('Banco destino',[c['label'] for c in view['columns']])
        cells=[c['text'] for c in view['rows'][0]]
        self.assertIn('BANCO DE PRUEBA',cells);self.assertIn('TITULAR DE PRUEBA',cells)
        self.assertIn('$ 120.000,25',cells)
        self.assertEqual(raw['filas'][0]['banco_id'],77)
        self.assertNotIn('banco',raw['filas'][0]);self.assertEqual(raw['unidad'],'centavos')
        html=self.client.get('/reportes',query_string=dict(self.args,tipo='contable')).get_data(as_text=True)
        self.assertIn('BANCO DE PRUEBA',html);self.assertIn('$ 120.000,25',html)
        self.assertNotIn('<th>banco_id</th>',html);self.assertNotIn('<pre>',html)

    def test_human_exports_use_names_and_numeric_pesos_technical_export_is_unchanged(self):
        self.accounting_record()
        query=dict(self.args,presentacion='usuario')
        response=self.client.get('/reportes/exportar/contable/xlsx',query_string=query)
        self.assertEqual(response.status_code,200)
        book=load_workbook(io.BytesIO(response.data));sheet=book['Datos']
        labels=[c.value for c in sheet[1]];row=[c.value for c in sheet[2]]
        self.assertEqual(row[labels.index('Banco destino')],'BANCO DE PRUEBA')
        self.assertEqual(row[labels.index('Valor consignado · COP')],120000.25)
        self.assertIn('COP',sheet.cell(2,labels.index('Valor consignado · COP')+1).number_format)
        response=self.client.get('/reportes/exportar/contable/csv',query_string=query)
        lines=list(csv.reader(io.StringIO(response.data.decode('utf-8-sig')),delimiter=';'))
        row=next(row for row in lines if 'BANCO DE PRUEBA' in row)
        self.assertIn('120000,25',row)
        response=self.client.get('/reportes/exportar/contable/xlsx',query_string=self.args)
        raw=load_workbook(io.BytesIO(response.data))['Datos'];labels=[c.value for c in raw[1]]
        self.assertIn('banco_id',labels);self.assertEqual(raw.cell(2,labels.index('monto')+1).value,12000025)

    def test_human_export_still_neutralizes_spreadsheet_formulas(self):
        response=self.client.get('/reportes/exportar/ventas/xlsx',query_string=dict(self.args,presentacion='usuario'))
        sheet=load_workbook(io.BytesIO(response.data))['Datos']
        self.assertEqual(sheet['C2'].value,"'=SUM(A1)")
        self.assertEqual(sheet['G2'].value,100000)

    def test_negative_financial_result_remains_a_numeric_amount_in_exports(self):
        d=db.session.get(Jornada,self.did);d.status='Cerrada'
        totals={k:0 for k in ('debe','haber','service','pd','liquidation','commission','owner_result')}
        totals['owner_result']=-1234567
        d.snapshot=dict(totals=totals,config=dict(staff=[]));db.session.commit()
        args=dict(self.args,presentacion='usuario')
        response=self.client.get('/reportes/exportar/finanzas/xlsx',query_string=args)
        sheet=load_workbook(io.BytesIO(response.data))['Datos']
        self.assertEqual(sheet.cell(2,sheet.max_column).value,-12345.67)
        response=self.client.get('/reportes/exportar/finanzas/csv',query_string=args)
        rows=list(csv.reader(io.StringIO(response.data.decode('utf-8-sig')),delimiter=';'))
        values=next(row for row in rows if row and row[0]==self.day)
        self.assertEqual(values[-1],'-12345,67')

    def test_human_exports_enforce_existing_permissions(self):
        self.login_role('Vendedora')
        self.assertEqual(self.client.get('/reportes/exportar/contable/xlsx?presentacion=usuario').status_code,403)
        self.assertEqual(self.client.get('/reportes?tipo=contable').status_code,403)
        self.assertEqual(self.client.get('/reportes?tipo=inventario').status_code,200)

    def test_filtering_and_download_links_keep_the_requested_range(self):
        response=self.client.get('/reportes',query_string=dict(self.args,tipo='ventas',vendedor='ANA'))
        html=response.get_data(as_text=True);page=Page(html)
        exports=[attrs['href'] for tag,attrs in page.tags if tag=='a' and '/reportes/exportar/' in attrs.get('href','')]
        self.assertEqual(len(exports),2)
        for href in exports:
            self.assertIn('desde='+self.day,href);self.assertIn('hasta='+self.day,href)
            self.assertIn('vendedor=ANA',href);self.assertIn('presentacion=usuario',href)
        self.assertNotIn('ID del aliado',html)
        before=db.session.query(Jornada).count();self.client.get('/reportes',query_string=dict(self.args,tipo='contable'))
        self.assertEqual(db.session.query(Jornada).count(),before)

    def test_finance_overview_opens_a_dedicated_form_without_nested_disclosures(self):
        query=dict(date=self.day)
        html=self.client.get('/finanzas',query_string=query).get_data(as_text=True)
        self.assertNotIn('id="operation-form"',html);self.assertIn('accion=registrar',html)
        self.assertNotIn('class="f-tabs"',html)
        html=self.client.get('/finanzas',query_string=dict(query,accion='registrar')).get_data(as_text=True)
        self.assertIn('id="operation-form"',html);self.assertIn('Costos y procedencia',html)
        self.assertNotIn('Agregar procedencias, costos o bebidas</summary>',html)
        self.assertIn('Volver a movimientos',html)
        html=self.client.get('/finanzas',query_string=dict(query,accion='compra_pool')).get_data(as_text=True)
        self.assertIn('<h2>Registrar compra POOL</h2>',html);self.assertNotIn('id="operation-form"',html)
        self.assertNotIn('<details class="panel f-new"',html)

    def operation_form(self,amount='100000'):
        d=db.session.get(Jornada,self.did)
        # V18.2: el escenario de registro parte de personal previamente confirmado.
        d.config={**d.config,'reviewed':True,'actor':'ANA','staff':[dict(name='ANA',role='Principal',salary=0,attended=True)]}
        db.session.commit()
        with self.client.session_transaction() as s:token=s['csrf']
        return dict(csrf=token,date=self.day,action='operation',return_tab='movimientos',revision=d.revision,
            token=secrets.token_hex(16),kind='Venta',description='VENTA UI',seller='__other__',seller_other='ANA',
            amount=amount,minor_cost='',payment_account='EFECTIVO',payment_amount='100000')

    def test_dedicated_form_uses_the_original_post_validation_and_redirect(self):
        self.client.get('/finanzas',query_string=dict(date=self.day,accion='registrar'))
        before=db.session.query(Op).count()
        response=self.client.post('/finanzas',data=self.operation_form())
        self.assertEqual(response.status_code,302)
        self.assertIn('date='+self.day,response.headers['Location'])
        self.assertEqual(db.session.query(Op).count(),before+1)
        op=db.session.scalar(db.select(Op).where(Op.description=='VENTA UI'))
        self.assertEqual(op.amount,10000000)
        self.assertEqual(op.payments,[dict(account='EFECTIVO',amount=10000000)])

    def test_invalid_amount_returns_to_the_form_without_creating_an_operation(self):
        self.client.get('/finanzas',query_string=dict(date=self.day,accion='registrar'))
        before=db.session.query(Op).count();response=self.client.post('/finanzas',data=self.operation_form('90000'))
        self.assertEqual(response.status_code,200)
        html=response.get_data(as_text=True)
        self.assertIn('id="operation-form"',html);self.assertIn('id="finance-restore"',html)
        self.assertIn('VENTA UI',html);self.assertEqual(db.session.query(Op).count(),before)

    def test_receipts_show_colombian_currency(self):
        p=Producto(imei='990000000000001',model='EQUIPO UI',capacity=128,color='NEGRO',condition='Nuevo',
            cost_cents=200000000,location='LOCAL CP STORE',supplier='PRUEBA',status='Vendido',
            sale_value_cents=270000000,paid_cents=270000000,sale_date=self.day)
        db.session.add(p);db.session.flush()
        db.session.add(Cobro(product_id=p.id,amount_cents=270000000,collector='ANA',destination='Negocio',
            method='Efectivo',effective_date=self.day,note='Prueba de presentación'))
        db.session.commit()
        html=self.client.get('/ventas/recepciones').get_data(as_text=True)
        self.assertIn('$ 2.700.000,00',html);self.assertNotIn('2700000.0',html)
        self.assertIn('class="ui-search-form"',html)


del ReportFixture
