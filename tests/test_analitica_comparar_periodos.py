"""comparar_periodos: ventas netas y resultado final contra el periodo anterior de igual duración. Una comparación, no una predicción."""
import json
import unittest
from datetime import date, timedelta
from unittest import mock

from sqlalchemy.exc import OperationalError

from test_consulta_resumen_ventas import VentasBase, dias_atras
from app.extensions import db
from app.models.finanzas import Jornada, OperacionFinanciera as Op
from app.services import consultas_service as cs

CLAVES = {'consulta', 'estado', 'mensaje', 'periodo', 'zona', 'fuentes', 'metodo', 'cobertura', 'advertencias',
          'cifras', 'detalle', 'es_estimacion', 'generado_en'}


class ComparacionBase(VentasBase):
    """Seis días de jornadas: hoy-5 a hoy-3 (periodo anterior) y hoy-2 a hoy (periodo pedido); hoy queda abierta."""

    def armar(self, anterior=(1000000, 1000000, 1000000), actual=(1500000, 1500000, 1500000), cerrar_hoy=False, omitir=()):
        montos = {5: anterior[0], 4: anterior[1], 3: anterior[2], 2: actual[0], 1: actual[1], 0: actual[2]}
        self.jornadas = {0: self.d}
        for n in (5, 4, 3, 2, 1):
            if n in omitir:
                continue
            self.jornadas[n] = self.jornada(dias_atras(n))
        for n, d in self.jornadas.items():
            if n in omitir:
                continue
            if montos[n]:
                self.vender(d=d, monto=str(montos[n]), con_equipo=False)
            if n or cerrar_hoy:
                self.cerrar(d)
        return dias_atras(2), self.hoy

    def comparar(self, ini=None, fin=None, rol='Propietario'):
        return cs.comparar_periodos(rol, ini or dias_atras(2), fin or self.hoy)

    def resultado_directo(self, ini, fin):
        c = cs.resumen_financiero('Propietario', ini, fin)['cifras']
        return sum(b['owner_result'] for b in (c['definitivo'], c['provisional']) if b['jornadas'])


class ComparacionCompletaTests(ComparacionBase):
    def setUp(self):
        super().setUp()
        self.ini, self.fin = self.armar(cerrar_hoy=True)

    def test_contrato_comun_y_es_una_comparacion(self):
        r = self.comparar()
        self.assertEqual(set(r), CLAVES)
        self.assertEqual((r['consulta'], r['estado']), ('comparar_periodos', 'ok'))
        self.assertFalse(r['es_estimacion'])
        self.assertTrue(r['cifras']['es_comparacion'])
        self.assertFalse(r['cifras']['es_prediccion'])
        self.assertIn('COMPARACIÓN', r['metodo'])
        self.assertIn('no es una predicción', r['metodo'])
        self.assertEqual(r['advertencias'][0], cs.AVISO_COMPARACION)

    def test_el_periodo_anterior_es_el_inmediato_y_de_igual_duracion(self):
        p = self.comparar()['periodo']
        self.assertEqual((p['ini'], p['fin'], p['dias']), (dias_atras(2), self.hoy, 3))
        self.assertEqual((p['anterior']['ini'], p['anterior']['fin'], p['anterior']['dias']), (dias_atras(5), dias_atras(3), 3))
        self.assertEqual(date.fromisoformat(p['anterior']['fin']) + timedelta(days=1), date.fromisoformat(p['ini']))

    def test_la_duracion_se_conserva_para_cualquier_longitud(self):
        for dias in (1, 2, 3, 7, 30):
            ini = dias_atras(dias - 1)
            anterior = cs._periodo_anterior(ini, self.hoy)
            self.assertEqual(cs._dias(*anterior), dias)
            self.assertEqual(date.fromisoformat(anterior[1]) + timedelta(days=1), date.fromisoformat(ini))

    def test_ventas_netas_comparan_resumen_ventas_de_los_dos_periodos(self):
        v = self.comparar()['cifras']['ventas_netas']
        self.assertEqual((v['actual_cents'], v['anterior_cents']), (450000000, 300000000))
        self.assertEqual(v['actual_cents'], cs.resumen_ventas('Propietario', self.ini, self.fin)['cifras']['venta_neta_cents'])
        self.assertEqual(v['anterior_cents'], cs.resumen_ventas('Propietario', dias_atras(5), dias_atras(3))['cifras']['venta_neta_cents'])
        self.assertEqual(v['diferencia_cents'], 150000000)
        self.assertEqual((v['variacion_bp'], v['variacion_pct']), (5000, 50.0))
        self.assertTrue(v['comparable'])
        self.assertFalse(v['provisional'])

    def test_resultado_final_suma_el_resultado_del_dia_de_cada_jornada(self):
        v = self.comparar()['cifras']['resultado_final']
        self.assertEqual(v['actual_cents'], self.resultado_directo(self.ini, self.fin))
        self.assertEqual(v['anterior_cents'], self.resultado_directo(dias_atras(5), dias_atras(3)))
        self.assertEqual(v['diferencia_cents'], v['actual_cents'] - v['anterior_cents'])
        self.assertTrue(v['comparable'])

    def test_los_importes_son_enteros_en_centavos_y_el_porcentaje_sale_de_enteros(self):
        r = self.comparar()['cifras']
        for clave in ('ventas_netas', 'resultado_final'):
            for campo in ('actual_cents', 'anterior_cents', 'diferencia_cents'):
                self.assertIsInstance(r[clave][campo], int, (clave, campo))
        self.assertIsInstance(r['ventas_netas']['variacion_bp'], int)

    def test_redondeo_de_la_variacion(self):
        casos = ((100, 133, 3300), (300, 301, 33), (3, 4, 3333), (3, 5, 6667), (1000, 500, -5000), (7, 7, 0), (100, 99, -100), (3, 2, -3333),
                 (6, 5, -1667))
        for anterior, actual, esperado in casos:
            v, _ = cs._variacion((actual, False, []), (anterior, False, []), 'x')
            self.assertEqual(v['variacion_bp'], esperado, (anterior, actual))

    def test_todo_se_lee_de_las_mismas_consultas_sin_formulas_propias(self):
        with mock.patch.object(cs, 'resumen_ventas', wraps=cs.resumen_ventas) as rv, \
                mock.patch.object(cs, 'resumen_financiero', wraps=cs.resumen_financiero) as rf:
            self.comparar()
        self.assertEqual([c.args[1:] for c in rv.call_args_list], [(self.ini, self.fin), (dias_atras(5), dias_atras(3))])
        self.assertEqual([c.args[1:] for c in rf.call_args_list], [(self.ini, self.fin), (dias_atras(5), dias_atras(3))])


class SinCoberturaTests(ComparacionBase):
    def assertSinComparacion(self, r, claves=('ventas_netas', 'resultado_final')):
        for clave in claves:
            v = r['cifras'][clave]
            self.assertFalse(v['comparable'], clave)
            for campo in ('diferencia_cents', 'variacion_bp', 'variacion_pct'):
                self.assertIsNone(v[campo], (clave, campo))  # nunca una cifra o un porcentaje inventados
        self.assertEqual(r['estado'], 'parcial')
        self.assertFalse(r['cobertura']['completa'])

    def test_falta_cobertura_en_el_periodo_actual(self):
        ini, fin = self.armar(cerrar_hoy=True, omitir=(1,))
        r = self.comparar(ini, fin)
        self.assertSinComparacion(r)
        self.assertIsNone(r['cifras']['ventas_netas']['actual_cents'])
        self.assertEqual(r['cifras']['ventas_netas']['anterior_cents'], 300000000)  # el anterior sí estaba completo: se informa solo
        self.assertTrue(any('periodo actual no tiene cobertura completa' in a and '1 día(s) sin jornada' in a for a in r['advertencias']))

    def test_falta_cobertura_en_el_periodo_anterior(self):
        ini, fin = self.armar(cerrar_hoy=True, omitir=(4,))
        r = self.comparar(ini, fin)
        self.assertSinComparacion(r)
        self.assertEqual(r['cifras']['ventas_netas']['actual_cents'], 450000000)
        self.assertIsNone(r['cifras']['ventas_netas']['anterior_cents'])
        self.assertTrue(any('periodo anterior no tiene cobertura completa' in a for a in r['advertencias']))

    def test_falta_cobertura_en_los_dos(self):
        ini, fin = self.armar(cerrar_hoy=True, omitir=(4, 1))
        r = self.comparar(ini, fin)
        self.assertSinComparacion(r)
        avisos = ' '.join(r['advertencias'])
        self.assertIn('periodo actual', avisos)
        self.assertIn('periodo anterior', avisos)

    def test_ninguna_respuesta_sin_cobertura_trae_un_porcentaje(self):
        ini, fin = self.armar(cerrar_hoy=True, omitir=(1,))
        texto = json.dumps(self.comparar(ini, fin), ensure_ascii=False)
        self.assertNotIn('"variacion_pct": 5', texto)
        r = json.loads(texto)
        self.assertIsNone(r['cifras']['ventas_netas']['variacion_pct'])
        self.assertIsNone(r['cifras']['resultado_final']['variacion_pct'])

    def test_un_equipo_vendido_sin_incorporar_quita_la_cobertura_de_ventas(self):
        ini, fin = self.armar(cerrar_hoy=True)
        self.sin_incorporar(valor=90000000, dia=self.hoy)
        r = self.comparar(ini, fin)
        self.assertFalse(r['cifras']['ventas_netas']['comparable'])
        self.assertTrue(any('sin incorporar a Finanzas' in a for a in r['advertencias']))
        self.assertTrue(r['cifras']['resultado_final']['comparable'])  # el resultado final sí tiene sus jornadas completas

    def test_una_cifra_nula_en_un_snapshot_deja_el_resultado_sin_comparar(self):
        ini, fin = self.armar(cerrar_hoy=True)
        d = self.jornadas[1]
        snap = json.loads(json.dumps(d.snapshot))
        snap['totals'].pop('owner_result')
        d.snapshot = snap
        db.session.commit()
        r = self.comparar(ini, fin)
        self.assertFalse(r['cifras']['resultado_final']['comparable'])
        self.assertTrue(r['cifras']['ventas_netas']['comparable'])
        self.assertTrue(any('no se puede calcular en alguna jornada' in a for a in r['advertencias']))

    def test_el_periodo_anterior_en_cero_no_da_porcentaje(self):
        ini, fin = self.armar(anterior=(0, 0, 0), cerrar_hoy=True)
        v = self.comparar(ini, fin)['cifras']['ventas_netas']
        self.assertTrue(v['comparable'])
        self.assertEqual((v['anterior_cents'], v['diferencia_cents']), (0, 450000000))
        self.assertIsNone(v['variacion_bp'])
        self.assertIsNone(v['variacion_pct'])

    def test_resultado_anterior_negativo_no_da_porcentaje(self):
        v, avisos = cs._variacion((100, False, []), (-500, False, []), 'Resultado final')
        self.assertEqual((v['diferencia_cents'], v['variacion_pct']), (600, None))
        self.assertTrue(any('cero o negativo' in a for a in avisos))

    def test_la_variacion_puede_ser_negativa(self):
        ini, fin = self.armar(anterior=(2000000, 2000000, 2000000), actual=(1000000, 1000000, 1000000), cerrar_hoy=True)
        v = self.comparar(ini, fin)['cifras']['ventas_netas']
        self.assertEqual((v['diferencia_cents'], v['variacion_bp'], v['variacion_pct']), (-300000000, -5000, -50.0))


class ProvisionalTests(ComparacionBase):
    def test_con_la_jornada_de_hoy_abierta_se_marca_provisional_y_es_parcial(self):
        ini, fin = self.armar(cerrar_hoy=False)
        r = self.comparar(ini, fin)
        self.assertEqual(r['estado'], 'parcial')
        self.assertTrue(r['cifras']['ventas_netas']['provisional'])
        self.assertTrue(r['cifras']['resultado_final']['provisional'])
        self.assertTrue(r['cifras']['ventas_netas']['comparable'])  # provisional no es falta de cobertura: se compara y se marca
        self.assertTrue(any('jornadas abiertas' in a for a in r['advertencias']))
        self.assertEqual(r['cifras']['ventas_netas']['actual_cents'], 450000000)

    def test_todo_cerrado_no_es_provisional(self):
        ini, fin = self.armar(cerrar_hoy=True)
        r = self.comparar(ini, fin)
        self.assertEqual(r['estado'], 'ok')
        self.assertFalse(r['cifras']['ventas_netas']['provisional'])
        self.assertTrue(r['cobertura']['completa'])


class EstadosYPermisosTests(ComparacionBase):
    def test_sin_datos_en_ninguno_de_los_dos_periodos(self):
        r = cs.comparar_periodos('Propietario', dias_atras(40), dias_atras(38))
        self.assertEqual(r['estado'], 'sin_datos')
        self.assertIsNone(r['cifras'])
        self.assertIn('COMPARACIÓN', r['metodo'])
        self.assertEqual(r['advertencias'][0], cs.AVISO_COMPARACION)

    def test_con_datos_en_uno_solo_no_es_sin_datos_y_no_compara(self):
        ini, fin = self.armar(anterior=(1000000, 1000000, 1000000), cerrar_hoy=True, omitir=(5, 4, 3))
        r = self.comparar(ini, fin)
        self.assertEqual(r['estado'], 'parcial')
        self.assertFalse(r['cifras']['ventas_netas']['comparable'])
        self.assertIsNone(r['cifras']['ventas_netas']['variacion_pct'])
        self.assertTrue(any('no hay jornadas de Finanzas en el periodo' in a for a in r['advertencias']))

    def test_sin_autorizacion_para_todo_perfil_distinto_del_propietario(self):
        ini, fin = self.armar(cerrar_hoy=True)
        for rol in ('Administrador', 'Vendedora', 'Inventario', 'Socio', '', None):
            with self.subTest(rol=rol):
                r = cs.comparar_periodos(rol, 'no-es-fecha', fin)  # ni siquiera valida parámetros
                self.assertEqual(r['estado'], 'sin_autorizacion')
                self.assertIsNone(r['cifras'])
                self.assertIsNone(r['detalle'])
                self.assertIn('COMPARACIÓN', r['metodo'])  # siempre dice qué es, sin cifras
                self.assertNotIn('450000000', json.dumps(r))

    def test_habilitar_un_perfil_exige_habilitar_tambien_las_consultas_de_las_que_se_alimenta(self):
        ini, fin = self.armar(cerrar_hoy=True)
        with mock.patch.dict(cs.ROLES_CONSULTAS, {'comparar_periodos': ('Propietario', 'Administrador')}):
            self.assertEqual(cs.comparar_periodos('Administrador', ini, fin)['estado'], 'sin_autorizacion')
        with mock.patch.dict(cs.ROLES_CONSULTAS, {'comparar_periodos': ('Propietario', 'Administrador'),
                                                   'resumen_ventas': ('Propietario', 'Administrador'),
                                                   'resumen_financiero': ('Propietario', 'Administrador')}):
            self.assertEqual(cs.comparar_periodos('Administrador', ini, fin)['estado'], 'ok')

    def test_error_temporal_de_la_base(self):
        ini, fin = self.armar(cerrar_hoy=True)
        fallo = OperationalError('SELECT', {}, Exception('database is locked'))
        with mock.patch.object(cs, '_leer_jornadas', side_effect=fallo):
            r = cs.comparar_periodos('Propietario', ini, fin)
        self.assertEqual(r['estado'], 'error_temporal')
        self.assertIsNone(r['cifras'])
        self.assertIn('COMPARACIÓN', r['metodo'])
        self.assertEqual(cs.comparar_periodos('Propietario', ini, fin)['estado'], 'ok')

    def test_un_error_de_programacion_no_se_disfraza(self):
        ini, fin = self.armar(cerrar_hoy=True)
        with mock.patch.object(cs, 'resumen_ventas', side_effect=KeyError('bug')):
            with self.assertRaises(KeyError):
                cs.comparar_periodos('Propietario', ini, fin)


class PeriodoYSeguridadTests(ComparacionBase):
    def test_fechas_invalidas_lanzan_parametro_invalido(self):
        for ini, fin in (('2026-13-40', self.hoy), (self.hoy, dias_atras(1)), ('hoy', self.hoy), (None, None),
                         (dias_atras(cs.MAX_DIAS_PERIODO), self.hoy)):
            with self.subTest(ini=ini, fin=fin), self.assertRaises(cs.ParametroInvalido):
                cs.comparar_periodos('Propietario', ini, fin)

    def test_un_periodo_futuro_completo_se_rechaza_y_un_fin_futuro_se_recorta(self):
        manana = (date.fromisoformat(self.hoy) + timedelta(days=1)).isoformat()
        with self.assertRaises(cs.ParametroInvalido):
            cs.comparar_periodos('Propietario', manana, manana)
        ini, _ = self.armar(cerrar_hoy=True)
        r = cs.comparar_periodos('Propietario', ini, '2999-01-01')
        self.assertEqual(r['periodo']['fin'], self.hoy)
        self.assertTrue(any('futura' in a for a in r['advertencias']))

    def test_el_periodo_mas_largo_permitido_funciona(self):
        r = cs.comparar_periodos('Propietario', dias_atras(cs.MAX_DIAS_PERIODO - 1), self.hoy)
        self.assertIn(r['estado'], ('sin_datos', 'parcial'))

    def test_es_solo_lectura_y_no_abre_jornadas(self):
        ini, fin = self.armar(cerrar_hoy=True)
        antes = (db.session.query(Jornada).count(), [(o.id, o.amount) for o in db.session.scalars(db.select(Op))])
        with mock.patch('app.services.finanzas_service.open_day', side_effect=AssertionError('open_day no se debe llamar')):
            self.comparar(ini, fin)
            cs.comparar_periodos('Propietario', dias_atras(30), dias_atras(20))
        self.assertFalse(db.session.new or db.session.dirty or db.session.deleted)
        self.assertEqual(antes, (db.session.query(Jornada).count(), [(o.id, o.amount) for o in db.session.scalars(db.select(Op))]))

    def test_no_devuelve_personas_descripciones_ni_imei(self):
        ini, fin = self.armar(cerrar_hoy=True)
        self.sin_incorporar()
        texto = json.dumps(self.comparar(ini, fin), ensure_ascii=False)
        for privado in ('ANA', 'VENDEDOR', 'CLIENTE', 'VENTA PRUEBA', 'imei', '49015420', 'seller', 'password'):
            self.assertNotIn(privado, texto)

    def test_la_consulta_figura_solo_para_el_propietario_en_la_configuracion(self):
        self.assertEqual(cs.ROLES_CONSULTAS['comparar_periodos'], ('Propietario',))


if __name__ == '__main__':
    unittest.main()
