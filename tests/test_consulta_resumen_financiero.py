"""Consulta resumen_financiero: snapshot para cerradas, report/calculate para abiertas, solo flujos, sin fórmulas nuevas."""
import inspect
import json
import secrets
import unittest
from unittest import mock

from sqlalchemy.exc import OperationalError

from test_consulta_resumen_ventas import VentasBase, data, dias_atras
from app.extensions import db
from app.models.finanzas import Jornada
from app.services import consultas_service as cs
from app.services import finanzas_service as f
from app.services.contabilidad_service import consolidar_periodo

CLAVES = {'consulta', 'estado', 'mensaje', 'periodo', 'zona', 'fuentes', 'metodo', 'cobertura', 'advertencias',
          'cifras', 'detalle', 'es_estimacion', 'generado_en'}
FLUJOS = cs.FLUJOS_SUMABLES
PROHIBIDOS = ('control_total', 'control_cash', 'cash_expected', 'cash_to_deliver', 'banks', 'funds', 'opening', 'bank_', 'base')


class FinancieroBase(VentasBase):
    def movimiento(self, tipo, monto, descripcion, d=None):
        f.add_operation(d or self.d, data(kind=tipo, description=descripcion, seller='ANA', token=secrets.token_hex(16),
                                          amount=monto, minor_cost='', payment_account=['EFECTIVO'], payment_amount=[monto]))
        db.session.commit()

    def dia_con_movimientos(self, d=None):
        self.vender(d=d, monto='650000')
        self.vender(d=d, monto='1200000', con_equipo=False)
        self.movimiento('Servicio', '30000', 'GARANTIA', d)
        self.movimiento('PD', '20000', 'PAPELERIA', d)

    def totales(self, d=None):
        return f.report(d or self.d)['totals']

    def financiero(self, ini=None, fin=None, rol='Propietario'):
        return cs.resumen_financiero(rol, ini or self.hoy, fin or self.hoy)


class JornadaAbiertaTests(FinancieroBase):
    def test_contrato_comun(self):
        self.dia_con_movimientos()
        r = self.financiero()
        self.assertEqual(set(r), CLAVES)
        self.assertEqual(r['consulta'], 'resumen_financiero')
        self.assertFalse(r['es_estimacion'])
        self.assertEqual(r['periodo'], {'ini': self.hoy, 'fin': self.hoy, 'inclusivo': True})
        self.assertTrue(r['fuentes'] and r['metodo'])

    def test_abierta_usa_report_y_calculate_sin_formulas_nuevas(self):
        self.dia_con_movimientos()
        totales = self.totales()
        r = self.financiero()
        prov = r['cifras']['provisional']
        for clave in FLUJOS:
            self.assertEqual(prov[clave], totales[clave], clave)
        self.assertEqual(prov['jornadas'], 1)
        self.assertGreater(prov['gross'], 0)

    def test_abierta_es_provisional_y_no_se_mezcla_con_el_definitivo(self):
        self.dia_con_movimientos()
        r = self.financiero()
        self.assertEqual(r['cifras']['definitivo']['jornadas'], 0)
        for clave in FLUJOS:
            self.assertIsNone(r['cifras']['definitivo'][clave])  # no hay cerradas: null, no 0
        self.assertEqual(set(r['cifras']), {'definitivo', 'provisional'})  # no hay un total que los mezcle
        self.assertEqual(r['estado'], 'parcial')
        self.assertTrue(any('provisional' in a for a in r['advertencias']))

    def test_flag_para_no_degradar_el_estado_por_jornadas_abiertas(self):
        self.dia_con_movimientos()
        with mock.patch.object(cs, 'ABIERTAS_DEGRADAN_A_PARCIAL', False):
            r = self.financiero()
        self.assertEqual(r['estado'], 'ok')
        self.assertIsNotNone(r['cifras']['provisional']['owner_result'])

    def test_las_abiertas_se_pueden_excluir_por_configuracion(self):
        self.dia_con_movimientos()
        with mock.patch.object(cs, 'JORNADAS_ABIERTAS_COMO_PROVISIONAL', False):
            r = self.financiero()
        self.assertEqual(r['estado'], 'parcial')
        self.assertEqual(r['cifras']['provisional']['jornadas'], 0)
        self.assertIsNone(r['cifras']['provisional']['owner_result'])
        self.assertEqual(r['cobertura']['sin_jornada_total'], 1)


class JornadaCerradaTests(FinancieroBase):
    def test_cerrada_usa_su_snapshot_como_definitivo(self):
        self.dia_con_movimientos()
        self.cerrar(self.d)
        snapshot = self.d.snapshot['totals']
        r = self.financiero()
        defi = r['cifras']['definitivo']
        for clave in FLUJOS:
            self.assertEqual(defi[clave], snapshot[clave], clave)
        self.assertEqual(r['cifras']['provisional']['jornadas'], 0)
        self.assertEqual(r['estado'], 'ok')
        self.assertTrue(r['cobertura']['completa'])

    def test_el_snapshot_manda_sobre_el_calculo_actual(self):
        self.dia_con_movimientos()
        self.cerrar(self.d)
        snap = json.loads(json.dumps(self.d.snapshot))
        snap['totals']['owner_result'] = 12345  # lo guardado al cerrar, aunque hoy el cálculo diera otra cosa
        self.d.snapshot = snap
        db.session.commit()
        self.assertNotEqual(self.totales()['owner_result'], 12345)
        self.assertEqual(self.financiero()['cifras']['definitivo']['owner_result'], 12345)

    def test_cerrada_no_vuelve_a_llamar_a_report(self):
        self.dia_con_movimientos()
        self.cerrar(self.d)
        with mock.patch.object(f, 'report', side_effect=AssertionError('report no debe usarse en jornadas cerradas')):
            self.financiero()

    def test_definitivo_y_provisional_van_separados_en_un_periodo_mixto(self):
        ayer = self.jornada(dias_atras(1))
        self.dia_con_movimientos(ayer)
        self.cerrar(ayer)
        self.dia_con_movimientos()
        r = self.financiero(ini=dias_atras(1))
        self.assertEqual(r['cifras']['definitivo']['jornadas'], 1)
        self.assertEqual(r['cifras']['provisional']['jornadas'], 1)
        self.assertEqual(r['cifras']['definitivo']['gross'], ayer.snapshot['totals']['gross'])
        self.assertEqual(r['cifras']['provisional']['gross'], self.totales()['gross'])
        self.assertEqual([x['estado'] for x in r['detalle']['por_jornada']], ['Cerrada', 'Abierta'])
        self.assertEqual([x['fuente'] for x in r['detalle']['por_jornada']], ['snapshot', 'report'])

    def test_varios_dias_cerrados_suman_dia_a_dia(self):
        ayer = self.jornada(dias_atras(1))
        self.vender(d=ayer, monto='500000', con_equipo=False)
        self.cerrar(ayer)
        self.vender(monto='650000', con_equipo=False)
        self.cerrar(self.d)
        r = self.financiero(ini=dias_atras(1))
        for clave in FLUJOS:
            esperado = ayer.snapshot['totals'][clave] + self.d.snapshot['totals'][clave]
            self.assertEqual(r['cifras']['definitivo'][clave], esperado, clave)
        self.assertEqual(r['cifras']['definitivo']['sales_count'], 2)


class SoloFlujosTests(FinancieroBase):
    def test_nunca_suma_ni_muestra_bases_de_caja_ni_saldos(self):
        self.dia_con_movimientos()
        self.cerrar(self.d)
        otra = self.jornada(dias_atras(1))
        self.dia_con_movimientos(otra)
        r = self.financiero(ini=dias_atras(1))
        self.assertEqual(set(r['cifras']['definitivo']) - {'jornadas'}, set(FLUJOS))
        self.assertEqual(set(r['cifras']['provisional']) - {'jornadas'}, set(FLUJOS))
        for fila in r['detalle']['por_jornada']:
            self.assertEqual(set(fila) - {'fecha', 'estado', 'fuente'}, set(FLUJOS))
        texto = json.dumps({k: r[k] for k in ('cifras', 'detalle', 'cobertura')}).lower()
        for prohibido in PROHIBIDOS:
            self.assertNotIn(prohibido, texto)

    def test_los_flujos_son_enteros_en_centavos(self):
        self.dia_con_movimientos()
        for clave, valor in self.financiero()['cifras']['provisional'].items():
            self.assertIsInstance(valor, int, clave)

    def test_la_lista_de_flujos_es_la_pedida(self):
        self.assertEqual(FLUJOS, ('gross', 'sales_count', 'debe', 'haber', 'service', 'liquidation', 'result', 'commission',
                                  'profit', 'owner_result'))

    def test_no_usa_consignaciones_ni_open_day_ni_formulas_propias(self):
        fuente = inspect.getsource(cs.resumen_financiero) + inspect.getsource(cs._bucket) + inspect.getsource(cs._totales_de_jornada)
        for prohibido in ('ConsignacionBancaria', 'open_day(', 'consolidar_periodo(', 'debe -', 'haber -', 'profit -', 'result -'):
            self.assertNotIn(prohibido, fuente)
        self.assertIn('finanzas_service.report', fuente)


class ValoresNulosTests(FinancieroBase):
    def cerrada_con_snapshot(self, d, cambios=None, quitar=()):
        self.dia_con_movimientos(d)
        self.cerrar(d)
        snap = json.loads(json.dumps(d.snapshot))
        snap['totals'].update(cambios or {})
        for clave in quitar:
            snap['totals'].pop(clave, None)
        d.snapshot = snap
        db.session.commit()

    def test_un_dia_con_null_hace_null_esa_cifra_del_total_con_la_fecha(self):
        ayer = self.jornada(dias_atras(1))
        self.cerrada_con_snapshot(ayer, cambios={'commission': None, 'profit': None, 'owner_result': None})
        self.dia_con_movimientos()
        self.cerrar(self.d)
        r = self.financiero(ini=dias_atras(1))
        defi = r['cifras']['definitivo']
        for clave in ('commission', 'profit', 'owner_result'):
            self.assertIsNone(defi[clave], clave)
        self.assertEqual(defi['gross'], ayer.snapshot['totals']['gross'] + self.d.snapshot['totals']['gross'])  # las demás siguen
        self.assertEqual(r['estado'], 'parcial')
        self.assertFalse(r['cobertura']['completa'])
        avisos = ' '.join(r['advertencias'])
        self.assertIn(dias_atras(1), avisos)
        self.assertIn('Utilidad del día', avisos)
        self.assertNotIn(self.hoy, avisos.split('Utilidad del día')[1].split('.')[0])  # el día completo no se acusa

    def test_clave_ausente_en_un_snapshot_antiguo_es_null_con_la_fecha(self):
        self.cerrada_con_snapshot(self.d, quitar=('owner_result', 'liquidation'))
        r = self.financiero()
        self.assertIsNone(r['cifras']['definitivo']['owner_result'])
        self.assertIsNone(r['cifras']['definitivo']['liquidation'])
        self.assertIsNotNone(r['cifras']['definitivo']['gross'])
        self.assertEqual(r['estado'], 'parcial')
        self.assertTrue(sum(self.hoy in a for a in r['advertencias']) >= 2)

    def test_cerrada_sin_snapshot_no_inventa_cifras(self):
        self.dia_con_movimientos()
        self.d.status = 'Cerrada'
        self.d.snapshot = None
        db.session.commit()
        r = self.financiero()
        for clave in FLUJOS:
            self.assertIsNone(r['cifras']['definitivo'][clave])
        self.assertEqual(r['cifras']['definitivo']['jornadas'], 1)
        self.assertEqual(r['estado'], 'parcial')

    def test_abierta_con_comision_fuera_de_tabla_devuelve_null(self):
        self.dia_con_movimientos()
        sin_comision = dict(self.totales(), commission=None, profit=None, owner_result=None, overflow=True)
        with mock.patch.object(f, 'report', return_value={'totals': sin_comision}):
            r = self.financiero()
        self.assertIsNone(r['cifras']['provisional']['commission'])
        self.assertIsNone(r['cifras']['provisional']['owner_result'])
        self.assertEqual(r['cifras']['provisional']['debe'], sin_comision['debe'])
        self.assertEqual(r['estado'], 'parcial')

    def test_un_valor_no_numerico_tampoco_se_suma(self):
        self.cerrada_con_snapshot(self.d, cambios={'gross': '123', 'sales_count': True})
        r = self.financiero()
        self.assertIsNone(r['cifras']['definitivo']['gross'])
        self.assertIsNone(r['cifras']['definitivo']['sales_count'])


class CoberturaYEstadosTests(FinancieroBase):
    def test_dias_sin_jornada_son_cobertura_incompleta_no_cero(self):
        self.dia_con_movimientos()
        self.cerrar(self.d)
        r = self.financiero(ini=dias_atras(6))
        self.assertEqual(r['estado'], 'parcial')
        self.assertEqual(r['cobertura']['dias_periodo'], 7)
        self.assertEqual(r['cobertura']['con_jornada'], 1)
        self.assertEqual(r['cobertura']['sin_jornada_total'], 6)
        self.assertEqual(r['cobertura']['sin_jornada'], [dias_atras(n) for n in range(6, 0, -1)])
        self.assertEqual(r['cifras']['definitivo']['gross'], self.d.snapshot['totals']['gross'])  # solo lo que sí hay
        self.assertTrue(any('no significa resultado cero' in a for a in r['advertencias']))

    def test_sin_datos_si_no_hay_jornadas_en_el_periodo(self):
        r = self.financiero(ini=dias_atras(20), fin=dias_atras(18))
        self.assertEqual(r['estado'], 'sin_datos')
        self.assertIsNone(r['cifras'])
        self.assertIsNone(r['detalle'])

    def test_jornada_sin_movimientos_es_un_cero_real(self):
        self.cerrar(self.d)
        r = self.financiero()
        self.assertEqual(r['estado'], 'ok')
        self.assertEqual(r['cifras']['definitivo']['gross'], 0)
        self.assertEqual(r['cifras']['definitivo']['sales_count'], 0)

    def test_nunca_crea_jornadas_ni_llama_open_day(self):
        antes = db.session.query(Jornada).count()
        with mock.patch.object(f, 'open_day', side_effect=AssertionError('open_day no se debe llamar')):
            self.financiero(ini=dias_atras(5))
            self.financiero(ini=dias_atras(5), fin=dias_atras(3))
        self.assertEqual(db.session.query(Jornada).count(), antes)

    def test_periodo_invalido(self):
        for ini, fin in (('2026-13-40', self.hoy), (self.hoy, dias_atras(1)), (None, None)):
            with self.subTest(ini=ini, fin=fin), self.assertRaises(cs.ParametroInvalido):
                cs.resumen_financiero('Propietario', ini, fin)

    def test_fin_futuro_se_recorta_con_aviso(self):
        self.cerrar(self.d)
        r = cs.resumen_financiero('Propietario', self.hoy, '2999-01-01')
        self.assertEqual(r['periodo']['fin'], self.hoy)
        self.assertTrue(any('futura' in a for a in r['advertencias']))

    def test_error_temporal_de_la_base(self):
        self.dia_con_movimientos()
        fallo = OperationalError('SELECT', {}, Exception('database is locked'))
        with mock.patch.object(cs, '_leer_jornadas', side_effect=fallo):
            r = self.financiero()
        self.assertEqual(r['estado'], 'error_temporal')
        self.assertIsNone(r['cifras'])
        self.assertNotEqual(self.financiero()['estado'], 'error_temporal')

    def test_error_temporal_al_calcular_una_jornada_abierta(self):
        self.dia_con_movimientos()
        fallo = OperationalError('SELECT', {}, Exception('database is locked'))
        with mock.patch.object(f, 'report', side_effect=fallo):
            self.assertEqual(self.financiero()['estado'], 'error_temporal')

    def test_es_solo_lectura(self):
        self.dia_con_movimientos()
        antes = [(j.date, j.status, j.revision) for j in db.session.scalars(db.select(Jornada))]
        self.financiero()
        self.assertFalse(db.session.new or db.session.dirty or db.session.deleted)
        db.session.expire_all()
        self.assertEqual(antes, [(j.date, j.status, j.revision) for j in db.session.scalars(db.select(Jornada))])


class PermisosYPrivacidadTests(FinancieroBase):
    def test_sin_autorizacion_para_todo_perfil_distinto_del_propietario(self):
        self.dia_con_movimientos()
        self.cerrar(self.d)
        for rol in ('Administrador', 'Vendedora', 'Inventario', 'Socio', '', None):
            with self.subTest(rol=rol):
                r = cs.resumen_financiero(rol, 'no-es-fecha', self.hoy)  # ni siquiera valida parámetros
                self.assertEqual(r['estado'], 'sin_autorizacion')
                self.assertIsNone(r['cifras'])
                self.assertIsNone(r['detalle'])
                self.assertNotIn(str(self.d.snapshot['totals']['gross']), json.dumps(r))

    def test_la_lista_de_roles_es_configurable(self):
        self.dia_con_movimientos()
        with mock.patch.dict(cs.ROLES_CONSULTAS, {'resumen_financiero': ('Propietario', 'Administrador')}):
            self.assertEqual(cs.resumen_financiero('Administrador', self.hoy, self.hoy)['consulta'], 'resumen_financiero')
            self.assertNotEqual(cs.resumen_financiero('Administrador', self.hoy, self.hoy)['estado'], 'sin_autorizacion')

    def test_no_devuelve_personas_descripciones_vendedores_ni_sueldos_por_persona(self):
        self.dia_con_movimientos()
        self.cerrar(self.d)
        texto = json.dumps(self.financiero(), ensure_ascii=False)
        for privado in ('ANA', 'LUZ', 'MAR', 'GARANTIA', 'PAPELERIA', 'VENTA PRUEBA', 'salary', 'staff', 'sandra', 'seller',
                        'imei', 'password'):
            self.assertNotIn(privado, texto)


class RotuloYDiferenciaTests(FinancieroBase):
    def test_owner_result_se_rotula_resultado_final_del_dia(self):
        self.dia_con_movimientos()
        r = self.financiero()
        self.assertEqual(r['detalle']['etiquetas']['owner_result'], 'Utilidad del día')
        self.assertEqual(set(r['detalle']['etiquetas']), set(FLUJOS))

    def test_el_metodo_aclara_que_no_es_el_margen_bruto_de_informacion_contable(self):
        self.cerrar(self.d)
        r = self.financiero()
        self.assertEqual(r['estado'], 'ok')
        for texto in ('Utilidad del día', 'NO es lo mismo', 'Margen bruto de equipos', 'Información contable'):
            self.assertIn(texto, r['metodo'])

    def test_el_resultado_del_dia_difiere_del_margen_bruto_por_definicion_no_por_error(self):
        self.vender(monto='650000')
        contable = consolidar_periodo(self.hoy, self.hoy)['ventas']
        margen_bruto = contable['utilidad_cents']
        prov = self.financiero()['cifras']['provisional']
        self.assertEqual(prov['debe'], margen_bruto)  # antes de descontar la jornada, ambas coinciden
        self.assertNotEqual(prov['owner_result'], margen_bruto)  # el resultado del día ya descontó la liquidación
        self.assertEqual(prov['result'], margen_bruto - prov['haber'] - prov['liquidation'] - prov['service'])  # identidad de calculate
        self.assertGreater(prov['liquidation'], 0)


if __name__ == '__main__':
    unittest.main()
