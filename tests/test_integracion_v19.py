"""Finanzas, inventario, POOL, crédito, chat y reportes comparten cifras.

Escenario sintético reproducible; nunca usa las ventas ni la base de la tienda.
Los importes esperados se calculan de forma independiente en el plan de pruebas.
"""
import copy
import secrets
import unittest

import test_gestion_v16 as fixture
from app.extensions import db
from app.models.finanzas import Jornada
from app.models.gestion import ComisionPool, CreditoVenta
from app.services import finanzas_service as f
from app.services import sociedad_service as so
from app.services import consultas_service as cs
from app.services import reporte_service as reports
from app.services import chat_service as chat


class IntegracionV19Tests(unittest.TestCase):
    setUp = fixture.GestionTests.setUp
    tearDown = fixture.GestionTests.tearDown
    product = fixture.GestionTests.product
    sale = fixture.GestionTests.sale
    settlement = fixture.GestionTests.settlement

    def jornada_completa(self, fuente_pool='ADMINISTRACIÓN DIRECTA'):
        self.d.date = self.day = '2026-10-12'
        self.d.config = {
            **f.defaults(self.day), 'actor': 'ANA', 'reviewed': True,
            'staff': [dict(name='ANA', role='Principal', salary=5000000, attended=True),
                      dict(name='LUZ', role='Secundaria', salary=2500000, attended=True)],
        }
        db.session.commit()
        p = self.product(pool=True)
        p.additional_costs = [dict(name='COMISIÓN DE COMPRA', amount_cents=2000000)]
        p.cost_cents += 2000000
        db.session.commit()
        buy = so.register_purchase(p, fixture.data(date=self.day, funding='620000', confirmed='1'))
        db.session.commit()
        self.assertEqual((buy.costos_pagados, buy.ganancia), (2000000, 10000000))
        op = self.sale(p, amount='800000', payment_amount=['800000'], cost_unit=['620000'])
        credit = db.session.scalar(db.select(CreditoVenta).where(CreditoVenta.operacion_id == op.id))
        self.assertEqual((credit.bruto, credit.neto), (80000000, 65600000))
        self.assertEqual(p.status, 'Vendido')
        extra = db.session.scalar(db.select(ComisionPool))
        self.assertEqual(extra.monto, 2000000)
        so.pay_pool_commission(fixture.data(
            commission_id=extra.id, date=self.day, confirmed='1',
            payment_source=fuente_pool, reference='PAGO REAL ADMINISTRACIÓN'))
        accessory = self.sale(
            credit=False, amount='100000', payment_amount=['100000'], minor_cost='5000',
            cost_type=['Proveedor'], cost_name=['OTROS'], cost_detail=['ACCESORIO EXTERNO'],
            cost_category=['Accesorios'], cost_qty=['1'], cost_unit=['30000'])
        f.pay_supplier(self.d, fixture.data(
            operation_id=accessory.id, cost_index=0, amount='30000', account='EFECTIVO',
            token=secrets.token_hex(16), reason='PAGO REAL PROVEEDOR'))
        for name, amount in [('ANA', '50000'), ('LUZ', '25000')]:
            f.pay_staff(self.d, fixture.data(
                staff_choice='Pago sueldo|' + name, amount=amount, payment_account='EFECTIVO',
                token=secrets.token_hex(16)))
        self.sale(credit=False, kind='PD', amount='9000', payment_amount=['9000'])
        self.sale(credit=False, kind='Servicio', amount='6000', payment_amount=['6000'])
        db.session.commit()
        return p, credit

    def cerrar(self, esperado):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session['csrf'] = 'integracion-v19'
        r = client.post('/finanzas', data=dict(
            csrf='integracion-v19', action='close', date=self.day, revision=self.d.revision,
            counted=str(esperado), acknowledge='1'))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.d.status, 'Cerrada')
        self.assertEqual(self.d.snapshot['difference'], 0)

    def comprobar_consultas(self, esperado=9100000):
        summary = cs.resumen_financiero('Propietario', '2026-10-12', '2026-10-12')
        self.assertEqual(summary['estado'], 'ok')
        self.assertEqual(summary['cifras']['definitivo']['owner_result'], esperado)
        report = reports.generar('Propietario', 'finanzas', 'rango',
                                 '2026-10-12', '2026-10-12', hoy='2026-10-13')
        self.assertEqual(report['resultados'][0]['cifras'], summary['cifras'])
        answer = chat.responder('Propietario', 'utilidad del 12 de octubre de 2026', hoy='2026-10-13')
        self.assertEqual(answer['herramienta'], 'resumen_financiero')
        self.assertIn('91.000', answer['respuesta'])
        self.assertIn('Utilidad del día', answer['respuesta'])

    def test_festivo_completo_cierra_y_chat_y_reportes_conservan_la_utilidad(self):
        self.jornada_completa()
        r = f.report(self.d)
        t = r['totals']
        self.assertEqual((t['debe'], t['haber'], t['liquidation'], t['service'], t['pd']),
                         (18600000, 500000, 7500000, 600000, 900000))
        self.assertEqual((t['owner_result'], t['cash_expected'], t['cash_to_deliver']),
                         (9100000, 28000000, 8000000))
        self.assertFalse(f.closing_tasks(self.d, r))
        self.cerrar(80000)
        self.comprobar_consultas()

    def test_pago_pool_desde_caja_cambia_entrega_y_no_vuelve_a_restar_utilidad(self):
        self.jornada_completa('EFECTIVO')
        t = f.report(self.d)['totals']
        self.assertEqual((t['owner_result'], t['cash_to_deliver']), (9100000, 6000000))
        self.cerrar(60000)
        self.comprobar_consultas()

    def test_desembolsos_posteriores_no_modifican_cierre_ni_utilidad_original(self):
        p, credit = self.jornada_completa()
        self.cerrar(80000)
        snapshot = copy.deepcopy(self.d.snapshot)
        original = self.d
        self.day = '2026-10-13'
        self.d = f.open_day(self.day)
        self.d.config = {**self.d.config, 'reviewed': True, 'actor': 'ANA',
                         'staff': [dict(name='ANA', role='Principal', salary=0, attended=True)]}
        db.session.commit()
        self.settlement(credit, 20000000, 'PARCIAL-V19')
        self.assertEqual(credit.estado, 'Parcial')
        self.assertEqual(f.report(self.d)['totals']['bank_received'], 20000000)
        self.settlement(credit, 45600000, 'FINAL-V19')
        now = f.report(self.d)['totals']
        self.assertEqual((credit.estado, p.payment_status), ('Pagado', 'Pagado'))
        self.assertEqual((now['bank_received'], now['debe'], now['sales_count']), (65600000, 0, 0))
        self.assertEqual(original.snapshot, snapshot)
        self.comprobar_consultas()
