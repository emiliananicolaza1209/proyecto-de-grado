"""Consulta creditos_pendientes: saldo = neto - recibido por aliado, sin mora, sin clientes, solo Propietario."""
import inspect
import json
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlalchemy.exc import OperationalError
from werkzeug.datastructures import MultiDict

from _cleanup import release
from app import create_app
from app.extensions import db
from app.models import BancoDestino, PersonaBanco, PersonaContable
from app.models.finanzas import OperacionFinanciera as Op
from app.models.gestion import AliadoCredito, CreditoVenta
from app.services import consultas_service as cs
from app.services import credito_service as cr
from app.services import finanzas_service as f

CLAVES = {'consulta', 'estado', 'mensaje', 'periodo', 'zona', 'fuentes', 'metodo', 'cobertura', 'advertencias',
          'cifras', 'detalle', 'es_estimacion', 'generado_en'}


def data(**kw):
    d = MultiDict()
    for k, v in kw.items():
        for x in (v if isinstance(v, list) else [v]):
            d.add(k, str(x))
    return d


class CreditosBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'DATABASE': str(Path(self.tmp.name) / 'db.sqlite'), 'SECRET_KEY': 'test'})
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.day = f.today()
        self.d = f.open_day(self.day)
        cfg = dict(self.d.config)
        cfg['staff'] = [dict(name=n, role='Principal', salary=0, attended=True) for n in ('ANA', 'LUZ', 'MAR')]
        cfg['reviewed'] = True
        cfg['actor'] = 'ANA'
        self.d.config = cfg
        self.person = PersonaContable(nombre='EMILY CLIENTE', identificacion='TEST1', tipo='Natural')
        self.bank = BancoDestino(nombre='BANCO PRUEBA')
        db.session.add_all([self.person, self.bank])
        db.session.flush()
        db.session.add(PersonaBanco(persona_id=self.person.id, banco_id=self.bank.id))
        db.session.commit()
        self.supay = db.session.scalar(db.select(AliadoCredito).where(AliadoCredito.nombre == 'SU+PAY'))
        self.addi = db.session.scalar(db.select(AliadoCredito).where(AliadoCredito.nombre == 'ADDI'))
        for a in (self.supay, self.addi):
            a.porcentaje_bp = 1800
            a.persona_id, a.banco_id = self.person.id, self.bank.id
        db.session.commit()
        self.n_ref = 0

    def tearDown(self):
        release(self.app)
        self.ctx.pop()
        self.tmp.cleanup()

    def venta_credito(self, ally=None, monto='650000'):
        ally = ally or self.supay
        params = dict(kind='Venta', description='VENTA PRUEBA CLIENTE', seller='ANA', token=secrets.token_hex(16), amount=monto,
                      minor_cost='', payment_account=['CRÉDITO'], payment_amount=[monto], payment_ally_id=[str(ally.id)],
                      payment_person_id=[str(self.person.id)], payment_bank_id=[str(self.bank.id)], credit_approved='1',
                      payment_credit_mode=['Porcentaje'], payment_credit_rate=['18'])
        f.add_operation(self.d, data(**params))
        db.session.commit()
        return db.session.scalar(db.select(CreditoVenta).order_by(CreditoVenta.id.desc()))

    def desembolso(self, credito, importe_cents):
        self.n_ref += 1
        pesos = str(importe_cents / 100)
        cr.settle(data(ally_id=credito.aliado_id, date=self.day, person_id=self.person.id, bank_id=self.bank.id,
                       token=secrets.token_hex(16), amount=pesos, reference=f'ABONO{self.n_ref}', credit_id=[credito.id],
                       allocation=[pesos]))
        db.session.commit()

    def aliado(self, respuesta, nombre):
        return next((a for a in respuesta['detalle']['por_aliado'] if a['aliado'] == nombre), None)


class EjemploDelPdfTests(CreditosBase):
    def test_bruto_650000_costo_18_neto_533000_y_abonos_hasta_saldo_cero(self):
        c = self.venta_credito()
        self.assertEqual((c.bruto, c.costo, c.neto), (65000000, 11700000, 53300000))
        r = cs.creditos_pendientes('Propietario')
        self.assertEqual(r['estado'], 'ok')
        self.assertEqual(r['cifras']['saldo_cents'], 53300000)
        self.assertEqual(r['cifras']['creditos_pendientes'], 1)
        self.desembolso(c, 20000000)  # abono de $200.000
        r = cs.creditos_pendientes('Propietario')
        self.assertEqual(r['cifras']['saldo_cents'], 33300000)  # queda $333.000
        self.assertEqual(r['cifras']['recibido_cents'], 20000000)
        self.assertEqual(self.aliado(r, 'SU+PAY')['saldo_cents'], 33300000)
        self.desembolso(c, 33300000)
        r = cs.creditos_pendientes('Propietario')
        self.assertEqual(r['estado'], 'ok')  # un cero real, no "sin datos"
        self.assertEqual(r['cifras']['saldo_cents'], 0)
        self.assertEqual(r['detalle']['por_aliado'], [])
        self.assertEqual(r['cobertura']['excluidos']['pagados'], 1)

    def test_saldo_es_neto_menos_recibido_y_no_depende_de_la_venta_ni_la_utilidad(self):
        c = self.venta_credito()
        self.desembolso(c, 10000000)
        db.session.refresh(c)
        r = cs.creditos_pendientes('Propietario')
        self.assertEqual(r['cifras']['saldo_cents'], c.neto - c.recibido)
        self.assertEqual(r['cifras']['neto_cents'], c.neto)
        self.assertEqual(r['cifras']['bruto_cents'], c.bruto)
        self.assertEqual(r['cifras']['costo_cents'], c.costo)


class ContratoYAgrupacionTests(CreditosBase):
    def test_contrato_comun(self):
        self.venta_credito()
        r = cs.creditos_pendientes('Propietario')
        self.assertEqual(set(r), CLAVES)
        self.assertEqual(r['consulta'], 'creditos_pendientes')
        self.assertFalse(r['es_estimacion'])
        self.assertEqual(r['zona'], cs.ZONA)
        self.assertTrue(r['fuentes'] and r['metodo'])
        self.assertIn('fecha_corte', r['periodo'])
        for clave in ('saldo_cents', 'bruto_cents', 'costo_cents', 'neto_cents', 'recibido_cents'):
            self.assertIsInstance(r['cifras'][clave], int)

    def test_saldo_por_aliado_y_total(self):
        a = self.venta_credito(self.supay, '650000')
        self.venta_credito(self.addi, '1000000')
        self.venta_credito(self.addi, '500000')
        self.desembolso(a, 10000000)
        r = cs.creditos_pendientes('Propietario')
        self.assertEqual(self.aliado(r, 'SU+PAY')['saldo_cents'], 43300000)
        self.assertEqual(self.aliado(r, 'ADDI')['creditos'], 2)
        self.assertEqual(self.aliado(r, 'ADDI')['saldo_cents'], 82000000 + 41000000)
        self.assertEqual(r['cifras']['saldo_cents'], sum(x['saldo_cents'] for x in r['detalle']['por_aliado']))
        self.assertEqual(r['cifras']['aliados_con_saldo'], 2)
        self.assertEqual(r['detalle']['por_aliado'][0]['aliado'], 'ADDI')  # ordenado por saldo

    def test_filtro_por_aliado(self):
        self.venta_credito(self.supay)
        self.venta_credito(self.addi)
        r = cs.creditos_pendientes('Propietario', aliado_id=self.addi.id)
        self.assertEqual([x['aliado'] for x in r['detalle']['por_aliado']], ['ADDI'])
        self.assertEqual(r['cifras']['saldo_cents'], 53300000)
        self.assertEqual(r['periodo']['filtros'], {'aliado_id': self.addi.id})
        r = cs.creditos_pendientes('Propietario', aliado_id=str(self.supay.id))
        self.assertEqual([x['aliado'] for x in r['detalle']['por_aliado']], ['SU+PAY'])

    def test_aliado_valido_sin_creditos_pendientes_es_cero_con_aviso(self):
        self.venta_credito(self.supay)
        r = cs.creditos_pendientes('Propietario', aliado_id=self.addi.id)
        self.assertEqual(r['estado'], 'ok')
        self.assertEqual(r['cifras']['saldo_cents'], 0)
        self.assertTrue(any('no tiene créditos pendientes' in a for a in r['advertencias']))

    def test_filtro_invalido_lanza_parametro_invalido(self):
        for valor in ('abc', 99999, -3, 0):
            with self.subTest(valor=valor), self.assertRaises(cs.ParametroInvalido):
                cs.creditos_pendientes('Propietario', aliado_id=valor)


class ExclusionesTests(CreditosBase):
    def test_creditos_anulados_y_operaciones_anuladas_no_suman(self):
        a = self.venta_credito(self.supay)
        b = self.venta_credito(self.addi)
        self.venta_credito(self.addi, '200000')
        op = db.session.get(Op, a.operacion_id)
        cr.cancel_unreceived(op, 'prueba')
        op.voided = True
        b.estado = 'Anulado'
        db.session.commit()
        r = cs.creditos_pendientes('Propietario')
        self.assertEqual(r['cifras']['saldo_cents'], 16400000)  # solo el tercero: 200.000 menos 18 %
        self.assertEqual(r['cobertura']['excluidos']['anulados'], 2)
        self.assertIsNone(self.aliado(r, 'SU+PAY'))

    def test_operacion_anulada_con_credito_aun_pendiente_no_suma(self):
        a = self.venta_credito()
        db.session.get(Op, a.operacion_id).voided = True
        db.session.commit()
        r = cs.creditos_pendientes('Propietario')
        self.assertEqual(r['cifras']['saldo_cents'], 0)
        self.assertEqual(r['cobertura']['excluidos']['operacion_anulada'], 1)

    def test_el_desembolso_no_aparece_como_venta_ni_utilidad(self):
        c = self.venta_credito()
        antes = f.report(self.d)['totals']
        self.desembolso(c, 53300000)
        despues = f.report(self.d)['totals']
        self.assertEqual((antes['debe'], antes['gross']), (despues['debe'], despues['gross']))
        texto = json.dumps(cs.creditos_pendientes('Propietario')).lower()
        for ajeno in ('venta', 'utilidad', 'debe'):
            self.assertNotIn(f'"{ajeno}', texto)


class AprobacionTests(CreditosBase):
    def test_credito_sin_aprobacion_va_aparte_y_fuera_del_saldo(self):
        ok = self.venta_credito(self.supay)
        sin = self.venta_credito(self.addi)
        sin.condiciones = dict(sin.condiciones, **{cs.CLAVE_APROBACION: False})
        db.session.commit()
        r = cs.creditos_pendientes('Propietario')
        self.assertEqual(r['estado'], 'parcial')
        self.assertEqual(r['cifras']['saldo_cents'], ok.neto)  # no incluye el no aprobado
        self.assertIsNone(self.aliado(r, 'ADDI'))
        self.assertEqual(r['detalle']['sin_aprobacion'], {'creditos': 1, 'neto_cents': 53300000, 'recibido_cents': 0, 'saldo_cents': 53300000})
        self.assertEqual(r['cobertura']['sin_aprobacion'], 1)
        self.assertTrue(any('sin aprobación' in a for a in r['advertencias']))

    def test_sin_la_marca_se_considera_aprobado_porque_el_registro_lo_exige(self):
        c = self.venta_credito()
        self.assertNotIn(cs.CLAVE_APROBACION, c.condiciones)  # hoy no se guarda: limitación documentada
        self.assertEqual(cs.creditos_pendientes('Propietario')['estado'], 'ok')

    def test_registrar_un_credito_sin_aprobar_sigue_siendo_imposible(self):
        with self.assertRaises(ValueError):
            params = dict(kind='Venta', description='X', seller='ANA', token=secrets.token_hex(16), amount='650000', minor_cost='',
                          payment_account=['CRÉDITO'], payment_amount=['650000'], payment_ally_id=[str(self.supay.id)],
                          payment_person_id=[str(self.person.id)], payment_bank_id=[str(self.bank.id)],
                          payment_credit_mode=['Porcentaje'], payment_credit_rate=['18'])
            f.add_operation(self.d, data(**params))
        db.session.rollback()


class SinMoraNiClientesTests(CreditosBase):
    def test_sin_mora_ni_antiguedad_ni_vencimiento(self):
        self.venta_credito()
        r = cs.creditos_pendientes('Propietario')
        datos = json.dumps({k: r[k] for k in ('cifras', 'detalle', 'cobertura', 'advertencias')}, ensure_ascii=False).lower()
        for prohibido in ('mora', 'vencid', 'vencimiento', 'antigüedad', 'antiguedad', 'dias_', 'días', 'fecha'):
            self.assertNotIn(prohibido, datos, prohibido)  # ninguna cifra ni clave habla de mora o de fechas
        self.assertIn('no se afirma mora', r['metodo'])  # el límite queda explicado en el método
        self.assertEqual(set(inspect.signature(cs.creditos_pendientes).parameters), {'rol', 'aliado_id'})  # sin fechas

    def test_no_devuelve_clientes_personas_bancos_ni_descripciones(self):
        self.venta_credito()
        texto = json.dumps(cs.creditos_pendientes('Propietario'), ensure_ascii=False)
        for privado in ('EMILY', 'CLIENTE', 'TEST1', 'BANCO PRUEBA', 'VENTA PRUEBA', '"ANA"', 'seller', 'person', 'password'):
            self.assertNotIn(privado, texto)

    def test_es_solo_lectura(self):
        c = self.venta_credito()
        antes = (c.neto, c.recibido, c.estado)
        cs.creditos_pendientes('Propietario')
        self.assertFalse(db.session.new or db.session.dirty or db.session.deleted)
        db.session.expire_all()
        c = db.session.get(CreditoVenta, c.id)
        self.assertEqual(antes, (c.neto, c.recibido, c.estado))


class EstadosYPermisosTests(CreditosBase):
    def test_sin_datos_si_nunca_se_registro_un_credito(self):
        r = cs.creditos_pendientes('Propietario')
        self.assertEqual(r['estado'], 'sin_datos')
        self.assertIsNone(r['cifras'])
        self.assertIsNone(r['detalle'])

    def test_parcial_si_hay_saldo_inconsistente_y_el_valor_es_null(self):
        a = self.venta_credito(self.supay)
        self.venta_credito(self.addi)
        a.recibido = a.neto + 100  # recibido mayor que el neto: dato inconsistente
        db.session.commit()
        r = cs.creditos_pendientes('Propietario')
        self.assertEqual(r['estado'], 'parcial')
        self.assertIsNone(self.aliado(r, 'SU+PAY')['saldo_cents'])
        self.assertEqual(self.aliado(r, 'ADDI')['saldo_cents'], 53300000)  # los demás siguen siendo calculables
        self.assertIsNone(r['cifras']['saldo_cents'])  # el total no se inventa
        self.assertEqual(r['cobertura']['inconsistentes'], 1)

    def test_sin_autorizacion_no_revela_nada(self):
        self.venta_credito()
        for rol in ('Administrador', 'Vendedora', 'Inventario', 'Socio', '', None):
            with self.subTest(rol=rol):
                r = cs.creditos_pendientes(rol, aliado_id='no-es-id')
                self.assertEqual(r['estado'], 'sin_autorizacion')
                self.assertIsNone(r['cifras'])
                self.assertIsNone(r['detalle'])
                self.assertNotIn('5330', json.dumps(r))

    def test_la_lista_de_roles_es_configurable(self):
        self.venta_credito()
        with mock.patch.dict(cs.ROLES_CONSULTAS, {'creditos_pendientes': ('Propietario', 'Administrador')}):
            self.assertEqual(cs.creditos_pendientes('Administrador')['cifras']['saldo_cents'], 53300000)

    def test_error_temporal_de_la_base(self):
        self.venta_credito()
        fallo = OperationalError('SELECT', {}, Exception('database is locked'))
        with mock.patch.object(cs, '_leer_creditos', side_effect=fallo):
            r = cs.creditos_pendientes('Propietario')
        self.assertEqual(r['estado'], 'error_temporal')
        self.assertIsNone(r['cifras'])
        self.assertEqual(cs.creditos_pendientes('Propietario')['estado'], 'ok')


if __name__ == '__main__':
    unittest.main()
