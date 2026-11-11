"""Consulta resumen_ventas: operaciones Venta no anuladas por fecha de jornada (fuente del PDF de entrega)."""
import json
import secrets
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from sqlalchemy.exc import OperationalError
from werkzeug.datastructures import MultiDict

from _cleanup import release
from app import create_app
from app.extensions import db
from app.models import BancoDestino, PersonaBanco, PersonaContable, Producto
from app.models.gestion import AliadoCredito
from app.models.finanzas import Jornada, OperacionFinanciera as Op
from app.services import consultas_service as cs
from app.services import finanzas_service as f
from app.services.contabilidad_service import consolidar_periodo

CLAVES = {'consulta', 'estado', 'mensaje', 'periodo', 'zona', 'fuentes', 'metodo', 'cobertura', 'advertencias',
          'cifras', 'detalle', 'es_estimacion', 'generado_en'}


def data(**kw):
    d = MultiDict()
    for k, v in kw.items():
        for x in (v if isinstance(v, list) else [v]):
            d.add(k, str(x))
    return d


def dias_atras(n):
    return (date.fromisoformat(f.today()) - timedelta(days=n)).isoformat()


class VentasBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'DATABASE': str(Path(self.tmp.name) / 'db.sqlite'), 'SECRET_KEY': 'test'})
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.hoy = f.today()
        self.d = self.jornada(self.hoy)
        self.n = 0

    def tearDown(self):
        release(self.app)
        self.ctx.pop()
        self.tmp.cleanup()

    def jornada(self, dia):
        d = f.open_day(dia)
        cfg = dict(d.config)
        cfg['staff'] = [dict(name=n, role='Principal', salary=0, attended=True) for n in ('ANA', 'LUZ', 'MAR')]
        cfg['reviewed'] = True
        cfg['actor'] = 'ANA'
        d.config = cfg
        db.session.commit()
        return d

    def equipo(self, costo=100000000):
        self.n += 1
        p = Producto(imei=f'49015420323{self.n:04d}', model='IPHONE PRUEBA', capacity=128, color='NEGRO', condition='Nuevo',
                     cost_cents=costo, additional_costs=[], source_type='Lote', location='LOCAL', supplier='CP CELULARES',
                     status='Disponible')
        db.session.add(p)
        db.session.commit()
        return p

    def vender(self, d=None, monto='650000', con_equipo=True, descripcion='VENTA PRUEBA CLIENTE'):
        d = d or self.d
        p = self.equipo() if con_equipo else None
        params = dict(kind='Venta', description=descripcion, seller='ANA', token=secrets.token_hex(16), amount=monto, minor_cost='',
                      payment_account=['EFECTIVO'], payment_amount=[monto])
        if p:
            params.update(cost_type=['Equipo'], cost_name=[p.imei], cost_qty=['1'], cost_unit=[str(p.cost_cents / 100)])
        f.add_operation(d, data(**params))
        db.session.commit()
        return db.session.scalar(db.select(Op).where(Op.day_id == d.id).order_by(Op.id.desc()))

    def persona_banco(self):
        persona = PersonaContable(nombre='TITULAR PRUEBA', identificacion='TEST1', tipo='Natural')
        banco = BancoDestino(nombre='BANCO PRUEBA')
        db.session.add_all([persona, banco])
        db.session.flush()
        db.session.add(PersonaBanco(persona_id=persona.id, banco_id=banco.id))
        db.session.commit()
        return persona, banco

    def sin_incorporar(self, valor=90000000, dia=None):
        self.n += 1
        p = Producto(imei=f'49015420399{self.n:04d}', model='IPHONE MOD03', capacity=128, color='NEGRO', condition='Nuevo',
                     cost_cents=50000000, additional_costs=[], source_type='Lote', location='LOCAL', supplier='CP CELULARES',
                     status='Vendido', sale_date=dia or self.hoy, sale_value_cents=valor, seller='VENDEDOR X', responsible='CLIENTE X')
        db.session.add(p)
        db.session.commit()
        return p

    def cerrar(self, d):
        d.status = 'Cerrada'
        d.snapshot = {'totals': f.report(d)['totals']}
        db.session.commit()

    def consulta(self, ini=None, fin=None, rol='Propietario'):
        return cs.resumen_ventas(rol, ini or self.hoy, fin or self.hoy)


class FuenteYCifrasTests(VentasBase):
    def test_contrato_comun_y_cifras_en_centavos(self):
        self.vender()
        r = self.consulta()
        self.assertEqual(set(r), CLAVES)
        self.assertEqual((r['consulta'], r['estado']), ('resumen_ventas', 'ok'))
        self.assertFalse(r['es_estimacion'])
        self.assertEqual(r['periodo'], {'ini': self.hoy, 'fin': self.hoy, 'inclusivo': True})
        self.assertTrue(r['fuentes'] and r['metodo'])
        for clave in ('operaciones', 'venta_neta_cents'):
            self.assertIsInstance(r['cifras'][clave], int)

    def test_suma_las_operaciones_venta_de_la_jornada(self):
        self.vender(monto='650000')
        self.vender(monto='1200000')
        r = self.consulta()
        self.assertEqual((r['cifras']['operaciones'], r['cifras']['venta_neta_cents']), (2, 185000000))

    def test_coincide_con_la_pantalla_de_finanzas(self):
        self.vender(monto='650000')
        self.vender(monto='150000', con_equipo=False)
        totales = f.report(self.d)['totals']
        r = self.consulta()
        self.assertEqual(r['cifras']['venta_neta_cents'], totales['gross'])
        self.assertEqual(r['cifras']['operaciones'], totales['sales_count'])

    def test_coincide_con_informacion_contable_cuando_solo_hay_equipos(self):
        self.vender(monto='650000')
        self.vender(monto='1200000')
        contable = consolidar_periodo(self.hoy, self.hoy)['ventas']
        r = self.consulta()
        self.assertEqual((r['cifras']['operaciones'], r['cifras']['venta_neta_cents']), (contable['count'], contable['total_cents']))

    def test_diferencia_con_el_consolidado_es_exactamente_las_complementarias(self):
        self.vender(monto='650000')
        self.vender(monto='150000', con_equipo=False)
        contable = consolidar_periodo(self.hoy, self.hoy)['ventas']
        r = self.consulta()
        c = r['cifras']
        self.assertEqual(c['venta_neta_cents'] - contable['total_cents'], c['complementarias']['venta_neta_cents'])
        self.assertEqual(c['equipos']['venta_neta_cents'], contable['total_cents'])

    def test_desglose_equipos_y_complementarias_suma_el_total(self):
        self.vender(monto='650000')
        self.vender(monto='150000', con_equipo=False)
        self.vender(monto='80000', con_equipo=False)
        c = self.consulta()['cifras']
        self.assertEqual((c['equipos']['operaciones'], c['equipos']['venta_neta_cents']), (1, 65000000))
        self.assertEqual((c['complementarias']['operaciones'], c['complementarias']['venta_neta_cents']), (2, 23000000))
        self.assertEqual(c['equipos']['venta_neta_cents'] + c['complementarias']['venta_neta_cents'], c['venta_neta_cents'])
        self.assertEqual(c['equipos']['operaciones'] + c['complementarias']['operaciones'], c['operaciones'])

    def test_la_venta_es_neta_del_descuento_de_datafono(self):
        p = self.equipo()
        persona, _ = self.persona_banco()
        f.add_operation(self.d, data(kind='Venta', description='X', seller='ANA', token=secrets.token_hex(16), amount='1050000',
                                     minor_cost='', cost_type=['Equipo'], cost_name=[p.imei], cost_qty=['1'],
                                     cost_unit=[str(p.cost_cents / 100)], payment_account=['DATÁFONO'], payment_amount=['1050000'],
                                     payment_person_id=[str(persona.id)]))
        db.session.commit()
        self.assertEqual(self.consulta()['cifras']['venta_neta_cents'], 100000000)  # 1.050.000 / 1,05

    def test_no_trae_cobrado_ni_saldo_ni_utilidad_ni_costos(self):
        self.vender()
        texto = json.dumps(self.consulta(), ensure_ascii=False).lower()
        for ajeno in ('cobrado', 'saldo', 'utilidad', 'margen', 'costo', 'recepci'):
            self.assertNotIn(f'"{ajeno}', texto)
            self.assertNotIn(f'{ajeno}_cents', texto)

    def test_sin_datos_personales_ni_descripciones(self):
        self.vender(descripcion='VENTA PRUEBA CLIENTE')
        self.sin_incorporar()
        texto = json.dumps(self.consulta(), ensure_ascii=False)
        for privado in ('CLIENTE', 'VENDEDOR X', 'ANA', 'imei', '49015420', 'seller', 'password'):
            self.assertNotIn(privado, texto)


class AnuladasTests(VentasBase):
    def test_una_operacion_anulada_no_suma(self):
        a = self.vender(monto='650000', con_equipo=False)
        self.vender(monto='1200000', con_equipo=False)
        a.voided = True
        db.session.commit()
        r = self.consulta()
        self.assertEqual((r['cifras']['operaciones'], r['cifras']['venta_neta_cents']), (1, 120000000))
        self.assertEqual(r['cifras']['venta_neta_cents'], f.report(self.d)['totals']['gross'])

    def test_una_venta_de_equipo_anulada_deja_de_contar(self):
        from app.services.operacion_service import operate
        persona, banco = self.persona_banco()
        aliado = db.session.scalar(db.select(AliadoCredito).where(AliadoCredito.nombre == 'SU+PAY'))
        aliado.porcentaje_bp, aliado.persona_id, aliado.banco_id = 1800, persona.id, banco.id
        p = self.equipo()
        f.add_operation(self.d, data(kind='Venta', description='X', seller='ANA', token=secrets.token_hex(16), amount='650000',
                                     minor_cost='', cost_type=['Equipo'], cost_name=[p.imei], cost_qty=['1'],
                                     cost_unit=[str(p.cost_cents / 100)], payment_account=['CRÉDITO'], payment_amount=['650000'],
                                     payment_ally_id=[str(aliado.id)], payment_person_id=[str(persona.id)],
                                     payment_bank_id=[str(banco.id)], credit_approved='1', payment_credit_mode=['Porcentaje'],
                                     payment_credit_rate=['18']))
        db.session.commit()
        self.assertEqual(self.consulta()['cifras']['venta_neta_cents'], 53300000)  # venta a crédito: neto del aliado
        operate(p.id, 'reverse_sale', data(reason='Prueba de anulación', revision=db.session.get(Producto, p.id).revision))
        r = self.consulta()
        self.assertEqual(r['cifras']['operaciones'], 0)
        self.assertEqual(r['cifras']['venta_neta_cents'], 0)
        self.assertEqual(r['estado'], 'ok')  # hay jornada: un cero real


class PorIncorporarTests(VentasBase):
    def test_avisa_de_equipos_vendidos_sin_operacion_y_no_los_suma(self):
        self.vender(monto='650000')
        self.sin_incorporar(valor=90000000)
        r = self.consulta()
        self.assertEqual(r['estado'], 'parcial')
        self.assertEqual(r['cifras']['venta_neta_cents'], 65000000)  # lo no incorporado no entra
        self.assertEqual(r['cifras']['por_incorporar'], {'equipos': 1, 'venta_neta_cents': 90000000})
        self.assertEqual(r['cobertura']['equipos_por_incorporar'], 1)
        self.assertTrue(any('no están incorporados' in a for a in r['advertencias']))
        self.assertFalse(r['cobertura']['completa'])

    def test_en_jornada_cerrada_una_venta_posterior_queda_por_incorporar(self):
        self.vender(monto='650000')
        self.cerrar(self.d)
        self.sin_incorporar(valor=90000000)
        r = self.consulta()
        self.assertEqual(r['cifras']['por_incorporar']['equipos'], 1)
        self.assertEqual(r['cifras']['definitivo']['venta_neta_cents'], 65000000)

    def test_sin_jornada_pero_con_equipo_por_incorporar_no_inventa_cero(self):
        dia = dias_atras(3)
        self.sin_incorporar(valor=90000000, dia=dia)
        r = self.consulta(ini=dia, fin=dia)
        self.assertEqual(r['estado'], 'parcial')
        self.assertIsNone(r['cifras']['venta_neta_cents'])
        self.assertIsNone(r['cifras']['operaciones'])
        self.assertEqual(r['cifras']['por_incorporar'], {'equipos': 1, 'venta_neta_cents': 90000000})

    def test_los_equipos_ya_incorporados_o_de_otro_periodo_no_avisan(self):
        self.vender()
        self.sin_incorporar(valor=70000000, dia=dias_atras(10))
        r = self.consulta()
        self.assertEqual(r['cifras']['por_incorporar']['equipos'], 0)
        self.assertEqual(r['estado'], 'ok')


class CierreYCoberturaTests(VentasBase):
    def test_jornada_cerrada_usa_su_snapshot_como_definitivo(self):
        self.vender(monto='650000')
        self.vender(monto='1200000', con_equipo=False)
        self.cerrar(self.d)
        r = self.consulta()
        self.assertEqual(r['cifras']['definitivo'], {'operaciones': 2, 'venta_neta_cents': 185000000})
        self.assertEqual(r['cifras']['provisional'], {'operaciones': 0, 'venta_neta_cents': 0})
        self.assertEqual(r['cobertura']['cerradas'], 1)
        self.assertEqual(r['estado'], 'ok')

    def test_el_snapshot_manda_sobre_las_operaciones_si_no_coinciden(self):
        self.vender(monto='650000')
        self.cerrar(self.d)
        snap = json.loads(json.dumps(self.d.snapshot))
        snap['totals']['gross'] += 100
        self.d.snapshot = snap
        db.session.commit()
        r = self.consulta()
        self.assertEqual(r['cifras']['venta_neta_cents'], 65000100)
        self.assertEqual(r['estado'], 'parcial')
        self.assertTrue(any('no coincide con sus operaciones' in a for a in r['advertencias']))

    def test_snapshot_sin_la_venta_neta_devuelve_null(self):
        self.vender()
        self.cerrar(self.d)
        snap = json.loads(json.dumps(self.d.snapshot))
        snap['totals'].pop('gross')
        self.d.snapshot = snap
        db.session.commit()
        r = self.consulta()
        self.assertEqual(r['estado'], 'parcial')
        self.assertIsNone(r['cifras']['venta_neta_cents'])
        self.assertIsNone(r['cifras']['definitivo'])

    def test_jornada_abierta_va_como_provisional_separada_del_definitivo(self):
        ayer = self.jornada(dias_atras(1))
        self.vender(d=ayer, monto='500000', con_equipo=False)
        self.cerrar(ayer)
        self.vender(monto='650000', con_equipo=False)  # hoy, abierta
        r = self.consulta(ini=dias_atras(1))
        self.assertEqual(r['cifras']['definitivo'], {'operaciones': 1, 'venta_neta_cents': 50000000})
        self.assertEqual(r['cifras']['provisional'], {'operaciones': 1, 'venta_neta_cents': 65000000})
        self.assertEqual(r['cifras']['venta_neta_cents'], 115000000)
        self.assertEqual(r['estado'], 'ok')
        self.assertTrue(any('abierta' in a and 'provisionales' in a for a in r['advertencias']))

    def test_las_abiertas_se_pueden_excluir_por_configuracion(self):
        self.vender(monto='650000')
        with mock.patch.object(cs, 'JORNADAS_ABIERTAS_COMO_PROVISIONAL', False):
            r = self.consulta()
        self.assertEqual(r['estado'], 'parcial')
        self.assertIsNone(r['cifras']['venta_neta_cents'])  # ninguna jornada contable: no se inventa un cero
        self.assertEqual(r['cobertura']['sin_jornada_total'], 1)

    def test_dias_sin_jornada_son_cobertura_incompleta_no_cero(self):
        self.vender(monto='650000', con_equipo=False)
        r = self.consulta(ini=dias_atras(6))
        self.assertEqual(r['estado'], 'parcial')
        self.assertEqual(r['cobertura']['dias_periodo'], 7)
        self.assertEqual(r['cobertura']['con_jornada'], 1)
        self.assertEqual(r['cobertura']['sin_jornada_total'], 6)
        self.assertEqual(r['cobertura']['sin_jornada'], [dias_atras(n) for n in range(6, 0, -1)])
        self.assertEqual(r['cifras']['venta_neta_cents'], 65000000)  # solo lo que sí hay
        self.assertFalse(r['cobertura']['completa'])

    def test_jornada_sin_ventas_es_un_cero_real(self):
        r = self.consulta()
        self.assertEqual(r['estado'], 'ok')
        self.assertEqual((r['cifras']['operaciones'], r['cifras']['venta_neta_cents']), (0, 0))

    def test_no_crea_jornadas_ni_llama_open_day(self):
        antes = db.session.query(Jornada).count()
        with mock.patch.object(f, 'open_day', side_effect=AssertionError('open_day no se debe llamar')):
            self.consulta(ini=dias_atras(5))
        self.assertEqual(db.session.query(Jornada).count(), antes)


class EstadosYPermisosTests(VentasBase):
    def test_sin_datos_si_no_hay_jornadas_ni_equipos_por_incorporar(self):
        dia = dias_atras(20)
        r = self.consulta(ini=dia, fin=dia)
        self.assertEqual(r['estado'], 'sin_datos')
        self.assertIsNone(r['cifras'])

    def test_sin_autorizacion_para_todo_perfil_distinto_del_propietario(self):
        self.vender(monto='650000')
        for rol in ('Administrador', 'Vendedora', 'Inventario', 'Socio', '', None):
            with self.subTest(rol=rol):
                r = cs.resumen_ventas(rol, 'no-es-fecha', self.hoy)  # ni siquiera valida parámetros
                self.assertEqual(r['estado'], 'sin_autorizacion')
                self.assertIsNone(r['cifras'])
                self.assertNotIn('65000000', json.dumps(r))

    def test_error_temporal_de_la_base(self):
        self.vender()
        fallo = OperationalError('SELECT', {}, Exception('database is locked'))
        with mock.patch.object(cs, '_leer_operaciones_venta', side_effect=fallo):
            r = self.consulta()
        self.assertEqual(r['estado'], 'error_temporal')
        self.assertIsNone(r['cifras'])
        self.assertEqual(self.consulta()['estado'], 'ok')

    def test_es_solo_lectura(self):
        self.vender()
        antes = [(o.id, o.amount, o.voided) for o in db.session.scalars(db.select(Op))]
        self.consulta()
        self.assertFalse(db.session.new or db.session.dirty or db.session.deleted)
        db.session.expire_all()
        self.assertEqual(antes, [(o.id, o.amount, o.voided) for o in db.session.scalars(db.select(Op))])


class PeriodoTests(VentasBase):
    def test_fechas_invalidas(self):
        for ini, fin in (('2026-13-40', self.hoy), ('hoy', self.hoy), (self.hoy, 'mañana'), ('', self.hoy), (None, None)):
            with self.subTest(ini=ini, fin=fin), self.assertRaises(cs.ParametroInvalido):
                cs.resumen_ventas('Propietario', ini, fin)

    def test_inicio_posterior_al_fin(self):
        with self.assertRaises(cs.ParametroInvalido):
            cs.resumen_ventas('Propietario', self.hoy, dias_atras(1))

    def test_periodo_completamente_futuro(self):
        manana = (date.fromisoformat(self.hoy) + timedelta(days=1)).isoformat()
        with self.assertRaises(cs.ParametroInvalido):
            cs.resumen_ventas('Propietario', manana, manana)

    def test_fin_futuro_se_recorta_a_hoy_con_aviso(self):
        self.vender(monto='650000', con_equipo=False)
        futuro = (date.fromisoformat(self.hoy) + timedelta(days=5)).isoformat()
        r = cs.resumen_ventas('Propietario', self.hoy, futuro)
        self.assertEqual(r['periodo']['fin'], self.hoy)
        self.assertTrue(any('futura' in a for a in r['advertencias']))
        self.assertEqual(r['cifras']['venta_neta_cents'], 65000000)

    def test_periodo_demasiado_largo(self):
        with self.assertRaises(cs.ParametroInvalido):
            cs.resumen_ventas('Propietario', dias_atras(cs.MAX_DIAS_PERIODO), self.hoy)
        cs.resumen_ventas('Propietario', dias_atras(cs.MAX_DIAS_PERIODO - 1), self.hoy)  # el límite exacto sí se acepta

    def test_la_lista_de_fechas_sin_jornada_es_acotada_pero_el_total_es_completo(self):
        with mock.patch.object(cs, 'MAX_FECHAS_LISTADAS', 3):
            r = self.consulta(ini=dias_atras(9))
        self.assertEqual(r['cobertura']['sin_jornada_total'], 9)
        self.assertEqual(len(r['cobertura']['sin_jornada']), 3)


class SinMultiplicarPorJoinsTests(VentasBase):
    """Caso T05 del paquete de Emily: una venta con varios pagos y varios costos cuenta una sola vez."""

    def venta_con_dos_pagos_y_tres_costos(self, monto='100000'):
        p = self.equipo(costo=50000000)
        persona, banco = self.persona_banco()
        f.add_operation(self.d, data(
            kind='Venta', description='VENTA T05', seller='ANA', token=secrets.token_hex(16), amount=monto, minor_cost='',
            payment_account=['EFECTIVO', 'TRANSFERENCIA'], payment_amount=['60000', '40000'],  # sin datáfono: este medio descuenta comisión
            payment_person_id=['', persona.id], payment_bank_id=['', banco.id],
            cost_type=['Equipo', 'Bebida', 'Bebida'], cost_name=[p.imei, 'AGUA', 'CORONA'], cost_qty=['1', '1', '1'],
            cost_unit=[str(p.cost_cents / 100), '2000', '4000']))
        db.session.commit()
        return db.session.scalar(db.select(Op).where(Op.day_id == self.d.id, Op.kind == 'Venta'))

    def test_la_venta_tiene_de_verdad_dos_pagos_y_tres_costos(self):
        o = self.venta_con_dos_pagos_y_tres_costos()
        self.assertEqual(len(o.payments), 2)
        self.assertEqual(len(o.costs), 3)
        self.assertEqual(sum(p['amount'] for p in o.payments), 10000000)

    def test_cuenta_una_operacion_y_la_venta_es_100000_sin_multiplicar_por_pagos_ni_costos(self):
        self.venta_con_dos_pagos_y_tres_costos()
        r = self.consulta()
        self.assertEqual(r['estado'], 'ok')
        self.assertEqual((r['cifras']['operaciones'], r['cifras']['venta_neta_cents']), (1, 10000000))
        # la jornada de la prueba está abierta: toda la venta va en el bloque provisional, una sola vez
        self.assertEqual(r['cifras']['provisional'], {'operaciones': 1, 'venta_neta_cents': 10000000})
        self.assertEqual(r['cifras']['definitivo'], {'operaciones': 0, 'venta_neta_cents': 0})

    def test_coincide_con_finanzas_y_sigue_bien_con_otra_venta(self):
        self.venta_con_dos_pagos_y_tres_costos()
        self.vender(monto='50000', con_equipo=False)
        totales = f.report(self.d)['totals']
        r = self.consulta()
        self.assertEqual((totales['sales_count'], totales['gross']), (2, 15000000))
        self.assertEqual((r['cifras']['operaciones'], r['cifras']['venta_neta_cents']), (2, 15000000))


if __name__ == '__main__':
    unittest.main()
