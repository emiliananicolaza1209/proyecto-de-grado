import unittest,tempfile,io
from pathlib import Path
from datetime import date,timedelta
from unittest.mock import patch
from openpyxl import load_workbook
from app import create_app
from app.extensions import db
from app.models.finanzas import Jornada,OperacionFinanciera as Op
from app.models.gestion import Usuario,ArticuloStock,CategoriaStock,RegistroGestion
from app.services import reportes_service as reports,alertas_service as alerts,finanzas_service as finance
from werkzeug.security import generate_password_hash


class ReportsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=create_app({'TESTING':True,'DATABASE':str(Path(self.tmp.name)/'test.sqlite'),'SECRET_KEY':'test'})
        self.ctx=self.app.app_context();self.ctx.push();self.client=self.app.test_client()
        self.day=date.today().isoformat()
        d=finance.open_day(self.day);self.did=d.id
        for i in range(2):
            db.session.add(Op(day_id=d.id,token=str(i),kind='Venta',description='=SUM(A1)',seller='ANA',amount=10000000,minor_cost=0,
                              costs=[{'type':'Proveedor','name':'PRUEBA','quantity':1,'unit':100,'amount':100}]*2,payments=[{'account':'EFECTIVO','amount':5000000}]*2))
        db.session.add(Op(day_id=d.id,token='void',kind='Venta',description='Anulada',seller='ANA',amount=999,minor_cost=0,costs=[],payments=[],voided=True))
        db.session.commit()
        self.args={'desde':self.day,'hasta':self.day}
    def tearDown(self):
        db.session.remove();db.engine.dispose();self.ctx.pop();self.tmp.cleanup()
    def test_sales_not_multiplied_by_costs_or_payments(self):
        r=reports.sales(self.args);self.assertEqual((r['cantidad'],r['venta_neta']),(2,20000000))
        r=reports.sales(dict(self.args,anuladas='1'));self.assertEqual(len(r['filas']),3);self.assertEqual(r['venta_neta'],20000000)
    def test_no_data_does_not_create_day(self):
        before=db.session.query(Jornada).count()
        reports.financial({'desde':'2020-01-01','hasta':'2020-01-03'})
        self.assertEqual(db.session.query(Jornada).count(),before)
    def test_closed_snapshot_and_no_sum_cash(self):
        d=db.session.get(Jornada,self.did);d.status='Cerrada'
        d.snapshot={'totals':{k:100 for k in ('debe','haber','service','pd','liquidation','commission','owner_result')},'config':{'staff':[]}}
        db.session.commit();r=reports.financial(self.args)
        self.assertEqual(r['totales']['owner_result'],100);self.assertNotIn('cash_expected',r['totales'])
        self.assertEqual(r['filas'][0]['fuente'],'Cierre')
    def test_open_days_excluded_without_permission(self):
        r=reports.financial(self.args);self.assertEqual(r['dias_incluidos'],0)
        r=reports.financial(dict(self.args,abiertas='1'));self.assertEqual(r['dias_incluidos'],1)
    def test_dates_validation_and_previous_zero(self):
        for args in ({'desde':'2026-01-02','hasta':'2026-01-01'},{'desde':'2020-01-01','hasta':'2026-01-01'}):
            with self.assertRaises(ValueError):reports.period(args)
        r=reports.comparison(self.args);self.assertIsNone(r['variacion_porcentaje']);self.assertEqual(r['diferencia'],20000000)
    def test_html_and_xlsx_and_formula_protection(self):
        for kind in reports.REPORTS:
            with self.subTest(kind=kind):
                response=self.client.get('/reportes',query_string=dict(self.args,tipo=kind))
                self.assertEqual(response.status_code,200)
        response=self.client.get('/reportes/exportar/ventas/xlsx',query_string=self.args)
        self.assertEqual(response.status_code,200)
        wb=load_workbook(io.BytesIO(response.data));self.assertEqual(wb['Datos']['C2'].value,"'=SUM(A1)")
        self.assertIn('Metadatos',wb.sheetnames)
        self.assertEqual(self.client.get('/analitica',query_string=self.args).status_code,200)
    def login_role(self,role):
        u=Usuario(nombre='Ana',login='ana',password_hash=generate_password_hash('password_test'),rol=role)
        db.session.add(u);db.session.commit();self.app.config['AUTH_REQUIRED']=True
        with self.client.session_transaction() as s:s['usuario_id']=u.id;s['usuario_version']=1;s['csrf']='test'
    def test_permission_enforced_on_exports_and_agent(self):
        self.login_role('Vendedora')
        self.assertEqual(self.client.get('/reportes?tipo=finanzas').status_code,403)
        self.assertEqual(self.client.get('/reportes/exportar/ventas/xlsx').status_code,403)
        self.assertEqual(self.client.get('/analitica').status_code,403)
        self.assertEqual(self.client.post('/analitica/consultar',data={'csrf':'test','consulta':'finanzas'}).status_code,403)
        self.assertEqual(self.client.get('/reportes?tipo=inventario').status_code,200)
    def test_alert_state_and_config_persist(self):
        cat=CategoriaStock(nombre='Prueba');db.session.add(cat);db.session.flush()
        a=ArticuloStock(nombre='Artículo',categoria_id=cat.id,minimo=2);db.session.add(a);db.session.commit()
        key='stock:'+str(a.id);self.assertIn(key,[r['key'] for r in alerts.alerts()])
        alerts.transition(key,'Cerrada','Compra revisada');alerts.settings('45','Revisado');db.session.commit();db.session.remove()
        self.assertEqual(alerts.config()['dias_inventario'],45)
        self.assertEqual(next(r for r in alerts.alerts() if r['key']==key)['estado'],'Cerrada')
        with self.assertRaises(ValueError):alerts.transition(key,'Borrada','motivo')
    def test_agent_returns_source_values_and_audits(self):
        with self.client.session_transaction() as s:s['csrf']='test'
        response=self.client.post('/analitica/consultar',data=dict(self.args,csrf='test',consulta='ventas'))
        self.assertEqual(response.status_code,200);self.assertIn(b'200000.00',response.data)
        self.assertEqual(db.session.query(RegistroGestion).filter_by(entidad='consulta_agente').count(),1)
        self.assertEqual(self.client.post('/analitica/consultar',data=dict(self.args,csrf='test',consulta='SQL')).status_code,400)
    def test_csrf_required(self):
        self.assertEqual(self.client.post('/analitica',data={'action':'config','days':'3'}).status_code,400)
    def test_api_matches_service_and_denies_unlisted_tool(self):
        response=self.client.get('/api/consultas/ventas',query_string=self.args)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['venta_neta'],reports.sales(self.args)['venta_neta'])
        self.assertEqual(self.client.get('/api/consultas/borrar').status_code,400)
    def test_location_not_applied_to_financial_close(self):
        with self.assertRaises(ValueError):reports.financial(dict(self.args,ubicacion='LOCAL'))


if __name__=='__main__':unittest.main()
