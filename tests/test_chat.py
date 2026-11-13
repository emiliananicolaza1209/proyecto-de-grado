"""Chat básico por reglas (commit A): intenciones, periodos, redacción, registro, ruta y permisos."""
import inspect
import json
import re
import secrets
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from sqlalchemy.exc import OperationalError
from werkzeug.datastructures import MultiDict
from werkzeug.security import generate_password_hash

from test_consulta_resumen_ventas import VentasBase, data, dias_atras
from app.extensions import db
from app.models import Producto
from app.models.gestion import RegistroGestion, Usuario
from app.services import chat_service as chat
from app.services import consultas_service as cs
from app.services import finanzas_service as f

HOY = '2026-11-10'  # martes
D = date.fromisoformat


class ChatBase(VentasBase):
    def preguntar(self, pregunta, rol='Propietario', **kw):
        return chat.responder(rol, pregunta, usuario='PROPIETARIO PRUEBA', usuario_id=7, **kw)

    def registros(self):
        db.session.expire_all()
        return [(r.entidad_id, r.actor, r.accion, r.motivo, dict(r.datos))
                for r in db.session.scalars(db.select(RegistroGestion).where(RegistroGestion.entidad == 'chat').order_by(RegistroGestion.id))]


class IntencionesTests(unittest.TestCase):
    CASOS = {
        'resumen_ventas': ('ventas de hoy', 'cuánto vendimos hoy', 'Ventas de esta semana', 'qué se vendió ayer', 'total de ventas'),
        'resumen_financiero': ('resultado de esta semana', 'cuál es la utilidad de hoy', 'resultado financiero', 'cuánto ganamos ayer',
                               'liquidación del mes'),
        'estado_inventario': ('inventario disponible', 'cuántos equipos hay', 'equipos disponibles', 'stock', 'existencias'),
        'creditos_pendientes': ('créditos pendientes', 'cuánto nos deben los aliados', 'saldo de ADDI', 'cartera de crédito'),
    }

    def test_cada_intencion_se_reconoce(self):
        for herramienta, preguntas in self.CASOS.items():
            for p in preguntas:
                with self.subTest(pregunta=p):
                    self.assertEqual(chat.detectar_intenciones(p)[0], herramienta)

    def test_mayusculas_y_tildes_no_importan(self):
        self.assertEqual(chat.detectar_intenciones('CRÉDITOS PENDIENTES')[0], 'creditos_pendientes')
        self.assertEqual(chat.detectar_intenciones('Inventario DISPONIBLE?')[0], 'estado_inventario')

    def test_sin_intencion(self):
        for p in ('hola', 'cuál es la capital de Francia', 'cuéntame un chiste', '???'):
            self.assertEqual(chat.detectar_intenciones(p), [], p)

    def test_una_palabra_dentro_de_otra_no_cuenta(self):
        self.assertEqual(chat.detectar_intenciones('inventario disponible'), ['estado_inventario'])  # "inventario" contiene "venta"
        self.assertEqual(chat.detectar_intenciones('ventas e inventario'), ['estado_inventario', 'resumen_ventas'])

    def test_con_varias_menciones_responde_la_de_mayor_prioridad_y_lo_avisa(self):
        self.assertEqual(chat.detectar_intenciones('ventas y créditos pendientes'), ['creditos_pendientes', 'resumen_ventas'])


class PeriodosTests(unittest.TestCase):
    def p(self, texto):
        r = chat.interpretar_periodo(texto, HOY)
        return None if r is None else (r['ini'], r['fin'])

    def test_hoy_y_ayer(self):
        self.assertEqual(self.p('ventas de hoy'), (HOY, HOY))
        self.assertEqual(self.p('ventas de AYER'), ('2026-11-09', '2026-11-09'))

    def test_esta_semana_va_de_lunes_a_hoy(self):
        self.assertEqual(D(HOY).weekday(), 1)
        self.assertEqual(self.p('resultado de esta semana'), ('2026-11-09', HOY))

    def test_semana_pasada_es_lunes_a_domingo_anteriores(self):
        self.assertEqual(self.p('ventas de la semana pasada'), ('2026-11-02', '2026-11-08'))
        self.assertEqual(self.p('Semana Pasada'), ('2026-11-02', '2026-11-08'))

    def test_este_mes_y_mes_pasado(self):
        self.assertEqual(self.p('ventas de este mes'), ('2026-11-01', HOY))
        self.assertEqual(self.p('ventas del mes'), ('2026-11-01', HOY))
        self.assertEqual(self.p('ventas del mes pasado'), ('2026-10-01', '2026-10-31'))

    def test_mes_pasado_cruza_el_cambio_de_anio(self):
        r = chat.interpretar_periodo('mes pasado', '2027-01-15')
        self.assertEqual((r['ini'], r['fin']), ('2026-12-01', '2026-12-31'))

    def test_nombre_de_mes_usa_el_anio_actual(self):
        self.assertEqual(self.p('ventas de octubre'), ('2026-10-01', '2026-10-31'))
        self.assertEqual(self.p('ventas en el mes de septiembre'), ('2026-09-01', '2026-09-30'))
        self.assertEqual(self.p('ventas de febrero'), ('2026-02-01', '2026-02-28'))

    def test_el_mes_en_curso_por_nombre_llega_hasta_hoy(self):
        r = chat.interpretar_periodo('ventas de noviembre', HOY)
        self.assertEqual((r['ini'], r['fin']), ('2026-11-01', HOY))
        self.assertIn('hasta hoy', r['etiqueta'])

    def test_mes_con_anio_explicito(self):
        self.assertEqual(self.p('ventas de octubre de 2025'), ('2025-10-01', '2025-10-31'))

    def test_un_mes_futuro_se_interpreta_pero_queda_en_el_futuro(self):
        r = chat.interpretar_periodo('ventas de diciembre', HOY)
        self.assertEqual(r['ini'], '2026-12-01')
        self.assertGreater(r['ini'], HOY)

    def test_rango_del_1_al_15_de_octubre(self):
        self.assertEqual(self.p('ventas del 1 al 15 de octubre'), ('2026-10-01', '2026-10-15'))
        self.assertEqual(self.p('ventas del 1 al 15 de Octubre de 2025'), ('2025-10-01', '2025-10-15'))

    def test_rango_entre_dos_meses_y_otras_formas(self):
        self.assertEqual(self.p('del 25 de septiembre al 5 de octubre'), ('2026-09-25', '2026-10-05'))
        self.assertEqual(self.p('del 1 de octubre al 15 de octubre'), ('2026-10-01', '2026-10-15'))
        self.assertEqual(self.p('entre el 3 y el 10 de noviembre'), ('2026-11-03', '2026-11-10'))
        self.assertEqual(self.p('de 2026-10-01 a 2026-10-15'), ('2026-10-01', '2026-10-15'))

    def test_un_dia_suelto_y_los_ultimos_dias(self):
        self.assertEqual(self.p('ventas del 5 de octubre'), ('2026-10-05', '2026-10-05'))
        self.assertEqual(self.p('ventas del 2026-10-05'), ('2026-10-05', '2026-10-05'))
        self.assertEqual(self.p('ventas de los últimos 7 días'), ('2026-11-04', HOY))

    def test_sin_periodo_devuelve_none(self):
        for texto in ('ventas', 'inventario disponible', 'créditos pendientes', 'resultado financiero'):
            self.assertIsNone(self.p(texto), texto)

    def test_fechas_que_no_existen(self):
        for texto in ('ventas del 31 de febrero', 'del 1 al 32 de octubre', 'del 2026-02-30 al 2026-03-01', 'el 30 de febrero'):
            with self.subTest(texto=texto), self.assertRaises(chat.PeriodoInvalido):
                chat.interpretar_periodo(texto, HOY)

    def test_las_etiquetas_describen_el_periodo(self):
        self.assertEqual(chat.interpretar_periodo('del 1 al 15 de octubre', HOY)['etiqueta'], 'del 1 de octubre al 15 de octubre de 2026')
        self.assertEqual(chat.interpretar_periodo('ayer', HOY)['etiqueta'], 'ayer')


class FueraDeAlcanceTests(ChatBase):
    def test_pregunta_ajena_no_inventa_y_lista_lo_que_si_puede(self):
        with mock.patch.object(cs, 'resumen_ventas', side_effect=AssertionError), mock.patch.object(cs, 'estado_inventario', side_effect=AssertionError):
            r = self.preguntar('cuál es la capital de Francia')
        self.assertEqual(r['estado'], 'fuera_de_alcance')
        self.assertIsNone(r['herramienta'])
        self.assertIsNone(r['tarjeta'])
        self.assertIn('No puedo responder eso.', r['respuesta'])
        for capacidad in chat.CAPACIDADES:
            self.assertIn(capacidad, r['respuesta'])
        self.assertIn('Periodos que entiendo', r['respuesta'])

    def test_no_escribe_ni_corrige(self):
        for p in ('borra las ventas de hoy', 'crea una venta', 'anula la última venta', 'cambia el precio del inventario',
                  'registra un gasto', 'cierra la jornada'):
            with self.subTest(p=p):
                r = self.preguntar(p)
                self.assertEqual(r['estado'], 'fuera_de_alcance')
                self.assertIn('No hago cambios', r['respuesta'])

    def test_verbos_de_escritura_no_bloquean_preguntas_de_lectura(self):
        r = self.preguntar('ventas registradas hoy')
        self.assertEqual(r['herramienta'], 'resumen_ventas')

    def test_no_entrega_datos_privados_aunque_se_pidan(self):
        for p in ('ventas por vendedora', 'dame el IMEI del iphone', 'sueldo de Sandra', 'clientes que más compran',
                  'cédula del cliente', 'ventas de hoy por proveedor', 'margen de ventas'):
            with self.subTest(p=p):
                r = self.preguntar(p)
                self.assertEqual(r['estado'], 'fuera_de_alcance', p)
                self.assertIn('No entrego datos por persona', r['respuesta'])
                self.assertIsNone(r['tarjeta'])

    def test_pregunta_vacia_o_demasiado_larga(self):
        for p in ('', '   ', 'a' * (chat.MAX_PREGUNTA + 1)):
            with self.subTest(largo=len(p)), self.assertRaises(ValueError):
                self.preguntar(p)


class PeriodoEnLaPreguntaTests(ChatBase):
    def llamada(self, pregunta, herramienta='resumen_ventas', hoy=None):
        with mock.patch.object(cs, herramienta, wraps=getattr(cs, herramienta)) as espia:
            r = self.preguntar(pregunta, hoy=hoy or self.hoy)
        return r, espia

    def test_sin_periodo_usa_hoy_y_lo_dice(self):
        r, espia = self.llamada('ventas')
        espia.assert_called_once_with('Propietario', self.hoy, self.hoy)
        self.assertIn(f'No indicaste un periodo; usé hoy ({self.hoy}).', r['respuesta'])
        self.assertTrue(r['periodo']['supuesto'])

    def test_el_periodo_pedido_llega_a_la_consulta(self):
        r, espia = self.llamada('ventas del 1 al 15 de octubre')
        espia.assert_called_once_with('Propietario', f'{D(self.hoy).year}-10-01', f'{D(self.hoy).year}-10-15')
        self.assertFalse(r['periodo']['supuesto'])
        self.assertNotIn('No indicaste un periodo', r['respuesta'])

    def test_financiero_tambien_interpreta_periodo(self):
        _, espia = self.llamada('resultado de ayer', 'resumen_financiero')
        ayer = dias_atras(1)
        espia.assert_called_once_with('Propietario', ayer, ayer)

    def test_fin_futuro_se_recorta_a_hoy_con_nota(self):
        r, espia = self.llamada('ventas de noviembre', hoy=self.hoy)
        self.assertEqual(espia.call_args.args[2], self.hoy)

    def test_periodo_futuro_no_consulta_nada(self):
        with mock.patch.object(cs, 'resumen_ventas', side_effect=AssertionError('no debe consultar')):
            r = self.preguntar('ventas de diciembre de 2999', hoy=self.hoy)
        self.assertEqual(r['estado'], 'periodo_invalido')
        self.assertIn('todavía no ha ocurrido', r['respuesta'])

    def test_fecha_inexistente_se_explica(self):
        r = self.preguntar('ventas del 31 de febrero')
        self.assertEqual(r['estado'], 'periodo_invalido')
        self.assertIn('No pude usar ese periodo', r['respuesta'])

    def test_periodo_demasiado_largo_se_explica(self):
        r = self.preguntar('ventas del 2024-01-01 al 2026-01-01')
        self.assertEqual(r['estado'], 'periodo_invalido')

    def test_inventario_y_creditos_ignoran_el_periodo_y_lo_dicen(self):
        for pregunta, herramienta in (('inventario disponible de octubre', 'estado_inventario'), ('créditos pendientes de ayer', 'creditos_pendientes')):
            with self.subTest(p=pregunta):
                r, espia = self.llamada(pregunta, herramienta)
                espia.assert_called_once_with('Propietario')
                self.assertIn('ignoré el periodo', r['respuesta'])
                self.assertIsNone(r['periodo'])

    def test_varias_menciones_agregan_la_nota(self):
        r = self.preguntar('ventas y créditos pendientes')
        self.assertEqual(r['herramienta'], 'creditos_pendientes')
        self.assertIn('también mencionaba ventas', r['respuesta'])


class RedaccionTests(ChatBase):
    def test_formato_de_pesos_con_separador_de_miles(self):
        for centavos, esperado in ((1529504762, '$15.295.047,62'), (0, '$0'), (100, '$1'), (5, '$0,05'), (123456789012, '$1.234.567.890,12'),
                                   (-50000, '-$500'), (99999900, '$999.999'), (None, 'no calculable')):
            self.assertEqual(chat.formatear_pesos(centavos), esperado, centavos)

    def test_ventas_muestra_importes_en_pesos_fuente_y_periodo(self):
        self.vender(monto='1200000', con_equipo=False)
        self.cerrar(self.d)
        r = self.preguntar('ventas de hoy')
        t = r['respuesta']
        self.assertIn('$1.200.000', t)
        self.assertIn(f'Ventas — {self.hoy}:', t)
        self.assertIn('Fuente: Finanzas', t)
        self.assertNotIn('1200000', t.replace('$1.200.000', ''))
        self.assertNotIn('provisional', t.lower())  # jornada cerrada: nada provisional

    def test_dice_provisional_cuando_hay_jornadas_abiertas(self):
        self.vender(monto='1200000', con_equipo=False)
        for pregunta in ('ventas de hoy', 'resultado de hoy'):
            with self.subTest(p=pregunta):
                t = self.preguntar(pregunta)['respuesta']
                self.assertIn('provisional', t.lower())
                self.assertIn('jornadas abiertas', t)

    def test_financiero_usa_el_rotulo_resultado_final_del_dia(self):
        self.vender(monto='1200000', con_equipo=False)
        t = self.preguntar('resultado de hoy')['respuesta']
        self.assertIn('Utilidad del día', t)
        self.assertIn(f"Utilidad del día: {chat.formatear_pesos(self.totales_hoy()['owner_result'])}", t)

    def totales_hoy(self):
        return f.report(self.d)['totals']

    def test_lista_las_advertencias(self):
        self.vender(monto='1200000', con_equipo=False)
        r = self.preguntar('ventas de esta semana', hoy=self.hoy)
        t = r['respuesta']
        if D(self.hoy).weekday() > 0:
            self.assertIn('Advertencias:', t)
            self.assertIn('cobertura incompleta', t)
            self.assertEqual(len(r['tarjeta']['advertencias']), len(set(r['tarjeta']['advertencias'])))

    def test_avisa_de_equipos_por_incorporar(self):
        self.sin_incorporar(valor=90000000)
        self.vender(monto='650000')
        t = self.preguntar('ventas de hoy')['respuesta']
        self.assertIn('Equipos por incorporar a Finanzas', t)
        self.assertIn('$900.000', t)

    def test_la_redaccion_es_determinista(self):
        self.vender(monto='1200000', con_equipo=False)
        a = self.preguntar('ventas de hoy')
        b = self.preguntar('ventas de hoy')
        self.assertEqual(a['respuesta'], b['respuesta'])
        resultado = cs.resumen_ventas('Propietario', self.hoy, self.hoy)
        self.assertEqual(chat.redactar_respuesta(resultado), chat.redactar_respuesta(resultado))

    def test_valor_no_calculable_se_dice_asi_no_se_inventa(self):
        self.vender(monto='1200000', con_equipo=False)
        self.cerrar(self.d)
        snap = json.loads(json.dumps(self.d.snapshot))
        snap['totals'].pop('owner_result')
        self.d.snapshot = snap
        db.session.commit()
        t = self.preguntar('resultado de hoy')['respuesta']
        self.assertIn('Utilidad del día: no calculable', t)
        self.assertIn('Resultado parcial', t)

    def test_inventario_y_creditos_se_redactan_con_sus_cifras(self):
        self.equipo(costo=250000000)
        t = self.preguntar('inventario disponible')['respuesta']
        self.assertIn('Equipos disponibles: 1', t)
        self.assertIn('Costo inmovilizado: $2.500.000', t)
        self.assertIn('Fuente: Inventario', t)
        t = self.preguntar('créditos pendientes')['respuesta']
        self.assertIn('no hay datos', t.lower())  # nunca se registró un crédito


class EstadosSinFiltrarCifrasTests(ChatBase):
    def setUp(self):
        super().setUp()
        self.vender(monto='1234500', con_equipo=False)

    def test_sin_autorizacion_tiene_su_mensaje_y_no_filtra_cifras(self):
        for rol in ('Administrador', 'Vendedora', 'Inventario', 'Socio'):
            for pregunta in ('ventas de hoy', 'resultado de hoy', 'inventario disponible', 'créditos pendientes'):
                with self.subTest(rol=rol, p=pregunta):
                    r = self.preguntar(pregunta, rol=rol)
                    self.assertEqual(r['estado'], 'sin_autorizacion')
                    self.assertEqual(r['respuesta'], 'Tu perfil no tiene permiso para esta consulta.')
                    self.assertEqual(r['tarjeta']['cifras'], [])
                    texto = json.dumps(r, ensure_ascii=False)
                    for cifra in ('1.234.500', '1234500', '123450000'):
                        self.assertNotIn(cifra, texto)

    def test_sin_datos_tiene_su_mensaje(self):
        dia = dias_atras(25)
        r = self.preguntar(f'ventas del {dia}')
        self.assertEqual(r['estado'], 'sin_datos')
        t = r['respuesta']
        self.assertIn('no hay datos', t.lower())
        self.assertIn('no significa cero', t)
        self.assertEqual(r['tarjeta']['cifras'], [])
        self.assertNotIn('$0', t)

    def test_error_temporal_tiene_su_mensaje_y_no_filtra_cifras(self):
        fallo = OperationalError('SELECT', {}, Exception('database is locked'))
        with mock.patch.object(cs, '_leer_operaciones_venta', side_effect=fallo):
            r = self.preguntar('ventas de hoy')
        self.assertEqual(r['estado'], 'error_temporal')
        self.assertEqual(r['respuesta'], 'No pude leer la información en este momento. Intenta de nuevo en unos segundos.')
        self.assertEqual(r['tarjeta']['cifras'], [])
        self.assertNotIn('1.234.500', json.dumps(r, ensure_ascii=False))

    def test_parcial_lo_dice(self):
        t = self.preguntar('ventas de esta semana', hoy=self.hoy)
        if D(self.hoy).weekday() > 0:
            self.assertEqual(t['estado'], 'parcial')
            self.assertIn('Resultado parcial', t['respuesta'])


class RegistroTests(ChatBase):
    def test_cada_consulta_queda_en_registro_gestion(self):
        self.vender(monto='1200000', con_equipo=False)
        self.preguntar('ventas de hoy')
        filas = self.registros()
        self.assertEqual(len(filas), 1)
        entidad_id, actor, accion, motivo, datos = filas[0]
        self.assertEqual((entidad_id, actor, accion), (7, 'PROPIETARIO PRUEBA', 'Consulta del chat'))
        self.assertEqual(datos['herramienta'], 'resumen_ventas')
        self.assertEqual(datos['periodo'], {'ini': self.hoy, 'fin': self.hoy})
        self.assertEqual(datos['estado'], 'parcial' if False else datos['estado'])
        self.assertEqual(datos['rol'], 'Propietario')
        self.assertRegex(datos['fecha'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}')

    def test_el_registro_no_guarda_la_pregunta_ni_cifras(self):
        self.vender(monto='1234500', con_equipo=False)
        self.preguntar('ventas de hoy, por favor, de la señora Marta')
        volcado = json.dumps(self.registros(), ensure_ascii=False)
        for secreto in ('Marta', 'señora', 'por favor', '1234500', '1.234.500', '123450000', 'pregunta', 'respuesta'):
            self.assertNotIn(secreto, volcado)

    def test_queda_registrado_el_estado_de_cada_resultado(self):
        self.preguntar('ventas de hoy')
        self.preguntar('capital de Francia')
        self.preguntar('ventas de hoy', rol='Vendedora')
        self.preguntar('ventas de diciembre de 2999')
        estados = [(d['herramienta'], d['estado']) for *_, d in self.registros()]
        self.assertEqual(estados[1:], [('ninguna', 'fuera_de_alcance'), ('resumen_ventas', 'sin_autorizacion'),
                                       ('resumen_ventas', 'periodo_invalido')])
        self.assertIn(estados[0][1], ('ok', 'parcial'))

    def test_inventario_no_tiene_periodo_en_el_registro(self):
        self.equipo()
        self.preguntar('inventario disponible')
        self.assertIsNone(self.registros()[0][4]['periodo'])

    def test_un_fallo_al_registrar_no_rompe_la_respuesta(self):
        self.vender(monto='1200000', con_equipo=False)
        with mock.patch.object(chat.db.session, 'commit', side_effect=OperationalError('INSERT', {}, Exception('locked'))):
            r = self.preguntar('ventas de hoy')
        self.assertIn('$1.200.000', r['respuesta'])
        self.assertEqual(self.registros(), [])

    def test_un_error_de_programacion_al_registrar_no_se_oculta(self):
        with mock.patch.object(chat.db.session, 'commit', side_effect=KeyError('bug')):
            with self.assertRaises(KeyError):
                self.preguntar('ventas de hoy')


class MismosTotalesTests(ChatBase):
    def test_ventas(self):
        self.vender(monto='650000')
        self.vender(monto='1200000', con_equipo=False)
        c = cs.resumen_ventas('Propietario', self.hoy, self.hoy)['cifras']
        t = self.preguntar('ventas de hoy')['respuesta']
        self.assertIn(f"Venta neta: {chat.formatear_pesos(c['venta_neta_cents'])}", t)
        self.assertIn(f"Operaciones de venta: {c['operaciones']}", t)
        self.assertIn(chat.formatear_pesos(c['equipos']['venta_neta_cents']), t)
        self.assertIn(chat.formatear_pesos(c['complementarias']['venta_neta_cents']), t)

    def test_financiero_coincide_con_finanzas_y_la_consulta(self):
        self.vender(monto='650000')
        self.vender(monto='1200000', con_equipo=False)
        prov = cs.resumen_financiero('Propietario', self.hoy, self.hoy)['cifras']['provisional']
        totales = f.report(self.d)['totals']
        t = self.preguntar('resultado de hoy')['respuesta']
        for clave in ('gross', 'debe', 'liquidation', 'commission', 'owner_result'):
            self.assertEqual(prov[clave], totales[clave])
            self.assertIn(f"{cs.ETIQUETAS_FLUJOS[clave]}: {chat.formatear_pesos(prov[clave])}", t)

    def test_inventario(self):
        self.equipo(costo=100000000)
        self.equipo(costo=300000000)
        c = cs.estado_inventario('Propietario')['cifras']
        t = self.preguntar('cuántos equipos hay')['respuesta']
        self.assertIn(f"Equipos disponibles: {c['disponibles']}", t)
        self.assertIn(f"Costo inmovilizado: {chat.formatear_pesos(c['costo_inmovilizado_cents'])}", t)

    def test_creditos(self):
        from test_consulta_creditos_pendientes import CreditosBase  # noqa: F401  (reutiliza el mismo flujo de venta a crédito)
        persona, banco = self.persona_banco()
        aliado = db.session.scalar(db.select(cs.AliadoCredito).where(cs.AliadoCredito.nombre == 'SU+PAY'))
        aliado.porcentaje_bp, aliado.persona_id, aliado.banco_id = 1800, persona.id, banco.id
        f.add_operation(self.d, data(kind='Venta', description='X', seller='ANA', token=secrets.token_hex(16), amount='650000',
                                     minor_cost='', payment_account=['CRÉDITO'], payment_amount=['650000'],
                                     payment_ally_id=[str(aliado.id)], payment_person_id=[str(persona.id)],
                                     payment_bank_id=[str(banco.id)], credit_approved='1', payment_credit_mode=['Porcentaje'],
                                     payment_credit_rate=['18']))
        db.session.commit()
        c = cs.creditos_pendientes('Propietario')['cifras']
        t = self.preguntar('créditos pendientes')['respuesta']
        self.assertEqual(c['saldo_cents'], 53300000)
        self.assertIn('Saldo pendiente: $533.000', t)
        self.assertIn('Aliado: SU+PAY: $533.000 (1)', t)


class PrivacidadTests(ChatBase):
    def setUp(self):
        super().setUp()
        self.p = self.equipo(costo=777700000)
        self.vender(monto='650000')
        self.sin_incorporar(valor=90000000)

    def test_ninguna_respuesta_filtra_imei_personas_ni_costos_de_lote(self):
        vistos = []
        for pregunta in ('ventas de hoy', 'resultado de hoy', 'inventario disponible', 'créditos pendientes'):
            r = self.preguntar(pregunta)
            vistos.append(json.dumps(r, ensure_ascii=False))
        texto = ' '.join(vistos)
        for privado in ('490154203', 'IMEI', 'imei', 'ANA', 'VENDEDOR X', 'CLIENTE X', 'seller', 'responsible', 'password'):
            self.assertNotIn(privado, texto)
        for linea in vistos[:2]:  # ventas y resultado: sin costo ni margen
            self.assertNotIn('Costo', linea)
            self.assertNotIn('Margen bruto', linea)
            self.assertNotIn('costo del equipo', linea.lower())

    def test_quien_no_ve_costos_no_los_recibe_aunque_se_habilite_la_consulta(self):
        with mock.patch.dict(cs.ROLES_CONSULTAS, {'estado_inventario': ('Propietario', 'Administrador')}):
            r = self.preguntar('inventario disponible', rol='Administrador')
        self.assertIn(r['estado'], ('ok', 'parcial'))  # parcial: el equipo de prueba no tiene ubicación de catálogo
        self.assertIn('Equipos disponibles: 1', r['respuesta'])  # el otro equipo está vendido
        self.assertNotIn('Costo inmovilizado', r['respuesta'])
        self.assertNotIn('7.777.000', json.dumps(r, ensure_ascii=False))
        self.assertNotIn('costo', json.dumps(r['tarjeta']).lower())


class RutaTests(VentasBase):
    def setUp(self):
        super().setUp()
        self.app.config['AUTH_REQUIRED'] = True

    def cliente(self, rol, **extra):
        u = Usuario(nombre=f'{rol.upper()} PRUEBA', login=rol.lower(), rol=rol, password_hash=generate_password_hash('clave_prueba_123'), **extra)
        db.session.add(u)
        db.session.commit()
        c = self.app.test_client()
        with c.session_transaction() as s:
            s.update(usuario_id=u.id, usuario_version=u.session_version, csrf='test')
        return c, u

    def post(self, c, pregunta='ventas de hoy', csrf='test'):
        return c.post('/chat/consultar', data=MultiDict({'csrf': csrf, 'pregunta': pregunta}))

    def test_el_propietario_recibe_respuesta_json(self):
        self.vender(monto='1200000', con_equipo=False)
        c, _ = self.cliente('Propietario')
        r = self.post(c)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, 'application/json')
        self.assertEqual(r.headers['Cache-Control'], 'no-store')
        j = r.get_json()
        self.assertEqual(j['herramienta'], 'resumen_ventas')
        self.assertIn('$1.200.000', j['respuesta'])
        self.assertEqual(j['tarjeta']['consulta'], 'resumen_ventas')
        self.assertIn('Fuente', j['respuesta'])

    def test_sin_csrf_es_400(self):
        c, _ = self.cliente('Propietario')
        self.assertEqual(self.post(c, csrf='mala').status_code, 400)
        self.assertEqual(c.post('/chat/consultar', data={'pregunta': 'ventas'}).status_code, 400)

    def test_solo_el_propietario_entra(self):
        for rol, esperado in (('Administrador', 403), ('Vendedora', 403), ('Inventario', 403)):
            with self.subTest(rol=rol):
                c, _ = self.cliente(rol)
                self.assertEqual(self.post(c).status_code, esperado)
        c, _ = self.cliente('Socio', socio_id=None)
        self.assertEqual(self.post(c).status_code, 302)  # el Socio vuelve a su página

    def test_sin_sesion_va_al_acceso(self):
        r = self.app.test_client().post('/chat/consultar', data={'pregunta': 'ventas'})
        self.assertIn(r.status_code, (302, 400))  # sin sesión ni token CSRF: nunca una respuesta
        if r.status_code == 302:
            self.assertIn('iniciar-sesion', r.headers['Location'])
        self.assertNotIn('Fuente', r.get_data(as_text=True))

    def test_pregunta_vacia_o_larga_es_400(self):
        c, _ = self.cliente('Propietario')
        for pregunta in ('', '   ', 'x' * 400):
            r = self.post(c, pregunta)
            self.assertEqual(r.status_code, 400, len(pregunta))
            self.assertIn('error', r.get_json())

    def test_solo_acepta_post(self):
        c, _ = self.cliente('Propietario')
        self.assertEqual(c.get('/chat/consultar').status_code, 405)

    def test_la_capacidad_sigue_a_roles_consultas(self):
        c, _ = self.cliente('Administrador')
        with mock.patch.dict(cs.ROLES_CONSULTAS, {'resumen_ventas': ('Propietario', 'Administrador')}):
            self.assertEqual(self.post(c, 'ventas de hoy').status_code, 200)
            r = self.post(c, 'inventario disponible')  # entra al chat, pero esa consulta sigue cerrada para él
            self.assertEqual(r.get_json()['estado'], 'sin_autorizacion')

    def test_la_ruta_deja_el_registro_con_el_usuario(self):
        c, u = self.cliente('Propietario')
        self.post(c)
        fila = db.session.scalar(db.select(RegistroGestion).where(RegistroGestion.entidad == 'chat'))
        self.assertEqual((fila.entidad_id, fila.actor), (u.id, 'PROPIETARIO PRUEBA'))
        self.assertEqual(fila.datos['herramienta'], 'resumen_ventas')

    def test_la_ruta_no_tiene_sql_y_el_servicio_no_usa_request(self):
        raiz = Path(__file__).resolve().parent.parent / 'app'
        ruta = (raiz / 'routes' / 'chat_routes.py').read_text(encoding='utf-8')
        servicio = (raiz / 'services' / 'chat_service.py').read_text(encoding='utf-8')
        for prohibido in ('db.', 'select(', '.execute', 'text(', 'session'):
            self.assertNotIn(prohibido, ruta)
        self.assertIsNone(re.search(r'from flask import[^\n]*\b(request|session|g)\b', servicio))
        for prohibido in ('openai', 'anthropic', 'requests', 'httpx', 'urllib', 'strftime', 'func.date', 'open_day('):
            self.assertNotIn(prohibido, servicio.lower())

    def test_ruta_clasificada_en_la_matriz(self):
        matriz = (Path(__file__).resolve().parent / 'test_matriz_permisos.py').read_text(encoding='utf-8')
        self.assertIn("'/chat/consultar'", matriz)


if __name__ == '__main__':
    unittest.main()
