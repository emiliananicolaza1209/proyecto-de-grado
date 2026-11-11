"""Reporte por periodo: selector, cifras de las consultas, exportaciones, permisos y política de contenido."""
import io
import re
import shutil
import subprocess
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from test_chat_pantalla import PantallaBase
from test_consulta_resumen_ventas import VentasBase, dias_atras
from app.extensions import db
from app.models.gestion import RegistroGestion
from app.models.finanzas import Jornada, OperacionFinanciera as Op
from app.security import CSP
from app.services import chat_service as chat
from app.services import consultas_service as cs
from app.services import reporte_service as rs

RAIZ = Path(__file__).resolve().parent.parent
HOY = '2026-11-11'  # miércoles


def texto_de(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style).*?</\1>', ' ', html, flags=re.S)))


class PeriodoTests(unittest.TestCase):
    def test_semana_es_de_lunes_a_hoy(self):
        p = rs.resolver_periodo('semana', hoy=HOY)
        self.assertEqual((p['ini'], p['fin']), ('2026-11-09', HOY))
        self.assertIn('2026-11-09 a 2026-11-11', p['etiqueta'])

    def test_quince_dias_incluye_hoy(self):
        p = rs.resolver_periodo('15dias', hoy=HOY)
        self.assertEqual((p['ini'], p['fin']), ('2026-10-28', HOY))
        self.assertEqual((date.fromisoformat(p['fin']) - date.fromisoformat(p['ini'])).days + 1, 15)

    def test_mes_va_del_primero_a_hoy(self):
        self.assertEqual((rs.resolver_periodo('mes', hoy=HOY)['ini'], rs.resolver_periodo('mes', hoy=HOY)['fin']), ('2026-11-01', HOY))

    def test_rango(self):
        p = rs.resolver_periodo('rango', '2026-10-01', '2026-10-15', hoy=HOY)
        self.assertEqual((p['ini'], p['fin'], p['etiqueta']), ('2026-10-01', '2026-10-15', '2026-10-01 a 2026-10-15'))

    def test_rango_con_fin_futuro_se_recorta_a_hoy(self):
        self.assertEqual(rs.resolver_periodo('rango', '2026-11-05', '2999-01-01', hoy=HOY)['fin'], HOY)

    def test_entradas_que_no_sirven(self):
        casos = (('rango', '2026-11-10', '2026-11-01'), ('rango', '', ''), ('rango', 'hoy', 'mañana'), ('rango', '2026-13-40', HOY),
                 ('rango', '2999-01-01', '2999-02-01'), ('trimestre', None, None), (None, None, None), ('', None, None))
        for tipo, ini, fin in casos:
            with self.subTest(tipo=tipo, ini=ini, fin=fin), self.assertRaises(rs.ReporteInvalido):
                rs.resolver_periodo(tipo, ini, fin, hoy=HOY)

    def test_las_opciones_del_selector_son_las_pedidas(self):
        self.assertEqual([c for c, _ in rs.OPCIONES], ['semana', '15dias', 'mes', 'rango'])
        self.assertEqual([e for _, e in rs.OPCIONES], ['Semana', '15 días', 'Mes', 'Rango de fechas'])


class GenerarTests(VentasBase):
    def test_ventas_usa_resumen_ventas_y_coincide_con_el_chat(self):
        self.vender(monto='650000')
        self.vender(monto='1200000', con_equipo=False)
        r = rs.generar('Propietario', 'ventas', 'mes', usuario='P', usuario_id=1)
        directo = cs.resumen_ventas('Propietario', r['periodo']['ini'], r['periodo']['fin'])['cifras']
        filas = dict((c['etiqueta'], c['valor']) for c in r['tarjetas'][0]['cifras'])
        self.assertEqual(filas['Venta neta'], chat.formatear_pesos(directo['venta_neta_cents']))
        self.assertEqual(filas['Operaciones de venta'], str(directo['operaciones']))
        respuesta_chat = chat.responder('Propietario', 'ventas de este mes', usuario='P', usuario_id=1)
        self.assertEqual(respuesta_chat['tarjeta']['cifras'], r['tarjetas'][0]['cifras'])  # misma cifra en el chat y en el reporte
        self.assertEqual(r['textos'][0], respuesta_chat['respuesta'].replace('\nNota: ', '\nNota: '))

    def test_finanzas_trae_resultado_y_creditos_pendientes(self):
        self.vender(monto='650000')
        r = rs.generar('Propietario', 'finanzas', 'semana', usuario='P', usuario_id=1)
        self.assertEqual([t['consulta'] for t in r['tarjetas']], ['resumen_financiero', 'creditos_pendientes'])
        prov = cs.resumen_financiero('Propietario', r['periodo']['ini'], r['periodo']['fin'])['cifras']['provisional']
        filas = dict((c['etiqueta'], c['valor']) for c in r['tarjetas'][0]['cifras'])
        self.assertEqual(filas['Provisional (jornadas abiertas) — Resultado final del día'], chat.formatear_pesos(prov['owner_result']))
        self.assertTrue(r['tarjetas'][0]['provisional'])
        self.assertEqual(r['tarjetas'][1]['estado'], 'sin_datos')  # nunca se registró un crédito

    def test_inventario_es_una_foto_de_hoy_sin_periodo(self):
        self.equipo(costo=250000000)
        r = rs.generar('Propietario', 'inventario', 'rango', 'basura', 'basura', usuario='P', usuario_id=1)  # el periodo no se usa
        self.assertIsNone(r['periodo'])
        self.assertTrue(r['foto_actual'])
        self.assertEqual([t['consulta'] for t in r['tarjetas']], ['estado_inventario', 'permanencia_inventario'])
        self.assertIn(('Costo inmovilizado', '$2.500.000'), [(c['etiqueta'], c['valor']) for c in r['tarjetas'][0]['cifras']])

    def test_sin_autorizacion_no_trae_cifras(self):
        self.vender(monto='1200000', con_equipo=False)
        for modulo in ('ventas', 'finanzas', 'inventario'):
            for rol in ('Administrador', 'Vendedora', 'Inventario', 'Socio'):
                with self.subTest(modulo=modulo, rol=rol):
                    r = rs.generar(rol, modulo, 'mes', usuario='X', usuario_id=2)
                    for t in r['tarjetas']:
                        self.assertEqual((t['estado'], t['cifras']), ('sin_autorizacion', []))
                    self.assertNotIn('1.200.000', ' '.join(r['textos']))

    def test_modulo_inexistente_y_fechas_invalidas_son_reporte_invalido(self):
        for args in (('compras', 'mes'), ('ventas', 'rango', '2026-01-01', '2026-01-02x'), ('ventas', 'trimestre')):
            with self.subTest(args=args), self.assertRaises(rs.ReporteInvalido):
                rs.generar('Propietario', *args)
        with self.assertRaises(rs.ReporteInvalido):  # más de 366 días: lo rechaza la consulta y se convierte en un error claro
            rs.generar('Propietario', 'ventas', 'rango', '2020-01-01', self.hoy)

    def test_cada_consulta_deja_una_fila_en_registro_sin_cifras(self):
        self.vender(monto='1234500', con_equipo=False)
        rs.generar('Propietario', 'finanzas', 'mes', usuario='PROPIETARIO PRUEBA', usuario_id=7)
        filas = db.session.scalars(db.select(RegistroGestion).where(RegistroGestion.entidad == 'reporte').order_by(RegistroGestion.id)).all()
        self.assertEqual([f.datos['herramienta'] for f in filas], ['resumen_financiero', 'creditos_pendientes'])
        self.assertEqual((filas[0].actor, filas[0].entidad_id, filas[0].accion), ('PROPIETARIO PRUEBA', 7, 'Reporte por periodo'))
        self.assertEqual(filas[0].datos['periodo'], {'ini': rs.resolver_periodo('mes')['ini'], 'fin': rs.resolver_periodo('mes')['fin']})
        self.assertIsNone(filas[1].datos['periodo'])  # los créditos son un saldo actual
        self.assertNotIn('1234500', str([f.datos for f in filas]))
        self.assertEqual(db.session.query(RegistroGestion).filter_by(entidad='chat').count(), 0)

    def test_es_solo_lectura_salvo_el_registro(self):
        self.vender(monto='650000')
        antes = (db.session.query(Jornada).count(), db.session.query(Op).count(), [(o.id, o.amount) for o in db.session.scalars(db.select(Op))])
        rs.generar('Propietario', 'finanzas', 'semana', usuario='P', usuario_id=1)
        rs.generar('Propietario', 'ventas', 'rango', dias_atras(5), self.hoy, usuario='P', usuario_id=1)
        despues = (db.session.query(Jornada).count(), db.session.query(Op).count(), [(o.id, o.amount) for o in db.session.scalars(db.select(Op))])
        self.assertEqual(antes, despues)  # tampoco abre jornadas de los días sin jornada

    def test_csv_trae_lo_mismo_que_las_tarjetas(self):
        self.vender(monto='650000')
        self.vender(monto='1200000', con_equipo=False)
        r = rs.generar('Propietario', 'ventas', 'mes', usuario='P', usuario_id=1)
        lineas = rs.a_csv(r).split('\r\n')
        self.assertEqual(lineas[0], 'Reporte;Reporte de ventas')
        self.assertTrue(lineas[2].startswith('Periodo;Este mes'))
        self.assertIn('Concepto;Valor', lineas)
        for c in r['tarjetas'][0]['cifras']:
            self.assertIn(f"{c['etiqueta']};{c['valor']}", lineas)
        self.assertTrue(any(l.startswith('Fuente;Finanzas') for l in lineas))
        self.assertTrue(any('provisional' in l.lower() for l in lineas if l.startswith('Estado;')))

    def test_csv_protege_los_textos_que_empiezan_como_formula(self):
        for malo in ('=HYPERLINK("http://x")', '+1+1', '-2+3', '@SUM(1)'):
            self.assertEqual(rs._segura(malo), "'" + malo)
        self.assertEqual(rs._segura('Aliado: ADDI'), 'Aliado: ADDI')
        self.assertEqual(rs._segura(None), '')

    def test_csv_de_inventario_dice_que_no_depende_del_periodo(self):
        self.equipo()
        r = rs.generar('Propietario', 'inventario', usuario='P', usuario_id=1)
        self.assertIn('no depende del periodo', rs.a_csv(r))


class PanelYRutaTests(PantallaBase):
    def reporte(self, modulo, query='', rol='Propietario'):
        return self.cliente(rol).get(f'/reportes/{modulo}{query}')

    def test_el_boton_aparece_en_ventas_inventario_y_finanzas_solo_para_el_propietario(self):
        c = self.cliente('Propietario')
        for ruta, modulo in (('/ventas', 'ventas'), ('/inventario', 'inventario'), ('/finanzas', 'finanzas')):
            html = c.get(ruta).get_data(as_text=True)
            self.assertIn('id="reporte-panel"', html, ruta)
            self.assertIn(f'action="/reportes/{modulo}"', html, ruta)
            self.assertIn('Generar reporte', html, ruta)
            self.assertIn('/static/js/reportes.js', html, ruta)
        for rol, ruta in (('Administrador', '/ventas'), ('Vendedora', '/ventas'), ('Vendedora', '/finanzas'), ('Inventario', '/inventario'),
                          ('Inventario', '/ventas')):
            html = self.cliente(rol).get(ruta).get_data(as_text=True)
            self.assertNotIn('reporte-panel', html, (rol, ruta))
            self.assertNotIn('/reportes/', html, (rol, ruta))
            self.assertNotIn('reportes.js', html, (rol, ruta))

    def test_el_selector_ofrece_semana_15_dias_mes_y_rango(self):
        html = self.cliente('Propietario').get('/ventas').get_data(as_text=True)
        selector = re.search(r'<select id="reporte-periodo-ventas" name="periodo".*?</select>', html, re.S).group(0)
        self.assertEqual(re.findall(r'<option value="([^"]+)"[^>]*>([^<]+)</option>', selector),
                         [('semana', 'Semana'), ('15dias', '15 días'), ('mes', 'Mes'), ('rango', 'Rango de fechas')])
        self.assertRegex(html, r'<div class="reporte-rango" hidden>')
        self.assertIn('type="date" name="ini"', html)
        self.assertIn('type="date" name="fin"', html)
        self.assertIn(f'max="{self.hoy}"', html)

    def test_en_inventario_el_periodo_esta_desactivado_y_se_explica(self):
        html = self.cliente('Propietario').get('/inventario').get_data(as_text=True)
        self.assertRegex(html, r'<select id="reporte-periodo-inventario" name="periodo" class="form-select" disabled>')
        self.assertIn('foto de hoy: no depende del periodo', html)

    def test_las_paginas_de_los_modulos_siguen_funcionando_con_el_panel(self):
        c = self.cliente('Propietario')
        for ruta in ('/ventas', '/inventario', '/finanzas'):
            self.assertEqual(c.get(ruta).status_code, 200, ruta)

    def test_ventas_para_cada_tipo_de_periodo(self):
        self.vender(monto='1200000', con_equipo=False)
        for query, texto in (('?periodo=semana', 'Esta semana'), ('?periodo=15dias', 'Últimos 15 días'), ('?periodo=mes', 'Este mes'),
                             (f'?periodo=rango&ini={dias_atras(3)}&fin={self.hoy}', f'{dias_atras(3)} a {self.hoy}'), ('', 'Esta semana')):
            with self.subTest(query=query):
                r = self.reporte('ventas', query)
                self.assertEqual(r.status_code, 200)
                t = texto_de(r.get_data(as_text=True))
                self.assertIn(texto, t)
                self.assertIn('$1.200.000', t)
                self.assertIn('Fuente: Finanzas', t)

    def test_la_pagina_conserva_la_seleccion_y_los_enlaces_de_exportacion_usan_el_mismo_periodo(self):
        self.vender(monto='1200000', con_equipo=False)
        ini = dias_atras(3)
        html = self.reporte('ventas', f'?periodo=rango&ini={ini}&fin={self.hoy}').get_data(as_text=True)
        self.assertRegex(html, r'<option value="rango" selected>')
        self.assertIn(f'value="{ini}"', html)
        self.assertNotRegex(html, r'<div class="reporte-rango" hidden>')  # con "rango" las fechas se ven
        self.assertIn(f'formato=csv', html)
        for ruta in ('/modulos/tributario/paquete.xlsx', '/modulos/tributario/paquete.pdf', '/modulos/tributario/export.csv'):
            self.assertRegex(html, rf'href="{ruta}\?ini={ini}&amp;fin={self.hoy}"')

    def test_los_enlaces_a_las_exportaciones_existentes_funcionan(self):
        self.vender(monto='1200000', con_equipo=False)
        c = self.cliente('Propietario')
        html = c.get(f'/reportes/ventas?periodo=rango&ini={dias_atras(3)}&fin={self.hoy}').get_data(as_text=True)
        xlsx = c.get(re.search(r'href="(/modulos/tributario/paquete\.xlsx[^"]+)"', html).group(1).replace('&amp;', '&'))
        self.assertEqual((xlsx.status_code, xlsx.data[:2]), (200, b'PK'))
        pdf = c.get(re.search(r'href="(/modulos/tributario/paquete\.pdf[^"]+)"', html).group(1).replace('&amp;', '&'))
        self.assertEqual((pdf.status_code, pdf.data[:5]), (200, b'%PDF-'))

    def test_finanzas_lista_el_csv_de_cada_jornada_del_periodo(self):
        self.vender(monto='1200000', con_equipo=False)
        c = self.cliente('Propietario')
        html = c.get('/reportes/finanzas?periodo=semana').get_data(as_text=True)
        enlace = re.search(rf'href="(/finanzas/exportar\?date={self.hoy})"', html)
        self.assertIsNotNone(enlace)
        csv = c.get(enlace.group(1))
        self.assertEqual(csv.status_code, 200)
        self.assertEqual(csv.mimetype, 'text/csv')

    def test_descarga_csv_del_reporte(self):
        self.vender(monto='1200000', con_equipo=False)
        r = self.reporte('ventas', f'?periodo=rango&ini={dias_atras(2)}&fin={self.hoy}&formato=csv')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, 'text/csv')
        self.assertEqual(r.headers['Content-Disposition'], f'attachment; filename=reporte_ventas_{dias_atras(2)}_{self.hoy}.csv')
        self.assertEqual(r.headers['Cache-Control'], 'no-store')
        cuerpo = r.get_data()
        self.assertTrue(cuerpo.startswith(b'\xef\xbb\xbf'))  # BOM para que Excel lea las tildes
        texto = cuerpo.decode('utf-8-sig')
        self.assertIn('Venta neta;$1.200.000', texto)
        self.assertIn('Reporte;Reporte de ventas', texto)

    def test_csv_de_inventario_no_necesita_periodo(self):
        self.equipo()
        r = self.reporte('inventario', '?formato=csv')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers['Content-Disposition'], f'attachment; filename=reporte_inventario_{self.hoy}.csv')

    def test_errores_claros_con_400_y_sin_trazas(self):
        for query in ('?periodo=rango', '?periodo=rango&ini=2026-11-10&fin=2026-11-01', '?periodo=rango&ini=a&fin=b', '?periodo=hola',
                      '?periodo=rango&ini=2020-01-01&fin=' + self.hoy):
            with self.subTest(query=query):
                r = self.reporte('ventas', query)
                self.assertEqual(r.status_code, 400)
                self.assertIn('role="alert"', r.get_data(as_text=True))
                self.assertNotIn('Traceback', r.get_data(as_text=True))
        r = self.reporte('ventas', '?periodo=hola&formato=csv')  # con error no hay CSV: se muestra el motivo
        self.assertEqual((r.status_code, r.mimetype), (400, 'text/html'))

    def test_modulo_desconocido_es_404(self):
        self.assertEqual(self.reporte('compras').status_code, 404)

    def test_provisional_y_sin_datos_se_dicen(self):
        self.vender(monto='1200000', con_equipo=False)
        t = texto_de(self.reporte('ventas', '?periodo=semana').get_data(as_text=True))
        self.assertIn('Provisional', t)
        dia = dias_atras(25)
        t = texto_de(self.reporte('ventas', f'?periodo=rango&ini={dia}&fin={dia}').get_data(as_text=True))
        self.assertIn('Sin datos', t)
        self.assertIn('no significa cero', t)

    def test_la_pantalla_dice_lo_mismo_que_el_chat(self):
        self.vender(monto='650000')
        self.vender(monto='1200000', con_equipo=False)
        c = self.cliente('Propietario')
        pantalla = texto_de(c.get('/reportes/ventas?periodo=semana').get_data(as_text=True))
        respuesta = chat.responder('Propietario', 'ventas de esta semana', usuario='P', usuario_id=1)
        for etiqueta, valor in [(x['etiqueta'], x['valor']) for x in respuesta['tarjeta']['cifras']]:
            self.assertIn(f'{etiqueta} {valor}', pantalla)


class PermisosTests(PantallaBase):
    def test_solo_el_propietario_abre_los_reportes(self):
        for ruta in ('/reportes/ventas', '/reportes/finanzas', '/reportes/inventario', '/reportes/ventas?formato=csv'):
            self.assertEqual(self.cliente('Propietario').get(ruta).status_code, 200, ruta)
            for rol in ('Administrador', 'Vendedora', 'Inventario'):
                self.assertEqual(self.cliente(rol).get(ruta).status_code, 403, (rol, ruta))
            self.assertEqual(self.cliente('Socio').get(ruta).status_code, 302, ruta)
            self.assertEqual(self.app.test_client().get(ruta).status_code, 302, ruta)

    def test_un_perfil_habilitado_en_una_sola_consulta_ve_las_demas_como_sin_autorizacion(self):
        self.vender(monto='1200000', con_equipo=False)
        with mock.patch.dict(cs.ROLES_CONSULTAS, {'resumen_ventas': ('Propietario', 'Administrador')}):
            c = self.cliente('Administrador')
            ventas = texto_de(c.get('/reportes/ventas?periodo=semana').get_data(as_text=True))
            self.assertIn('$1.200.000', ventas)
            fin = texto_de(c.get('/reportes/finanzas?periodo=semana').get_data(as_text=True))
            self.assertIn('Sin autorización', fin)
            self.assertNotIn('$', fin.replace('$)', ''))  # ninguna cifra en pesos
            self.assertNotIn('Resultado final del día', fin.split('Fuente')[0].split('Generar reporte')[1])

    def test_los_enlaces_de_exportacion_dependen_de_los_permisos_de_cada_exportacion(self):
        with mock.patch.dict(cs.ROLES_CONSULTAS, {'resumen_ventas': ('Propietario', 'Vendedora')}):
            html = self.cliente('Vendedora').get('/reportes/ventas?periodo=semana').get_data(as_text=True)
        self.assertNotIn('/modulos/tributario/', html)  # la Vendedora no puede usar el paquete contable: no se le ofrece
        self.assertIn('formato=csv', html)

    def test_no_se_filtran_imei_personas_ni_costos_de_lote(self):
        self.vender(monto='650000')
        self.sin_incorporar()
        c = self.cliente('Propietario')
        for ruta in ('/reportes/ventas?periodo=mes', '/reportes/finanzas?periodo=mes', '/reportes/inventario?formato=csv',
                     '/reportes/ventas?periodo=mes&formato=csv'):
            cuerpo = c.get(ruta).get_data(as_text=True)
            for privado in ('490154203', 'VENDEDOR X', 'CLIENTE X', 'seller', 'password', 'ANA'):
                self.assertNotIn(privado, cuerpo, (ruta, privado))


class PoliticaDeContenidoTests(PantallaBase):
    def test_las_paginas_nuevas_no_usan_nada_en_linea(self):
        c = self.cliente('Propietario')
        for ruta in ('/reportes/ventas', '/reportes/finanzas', '/reportes/inventario', '/ventas', '/inventario', '/finanzas'):
            r = c.get(ruta)
            html = r.get_data(as_text=True)
            self.assertEqual(r.headers['Content-Security-Policy'], CSP, ruta)
            for atributos in re.findall(r'<script\b([^>]*)>', html):
                self.assertTrue('src=' in atributos or 'application/json' in atributos, (ruta, atributos))
            self.assertIsNone(re.search(r'\son(click|change|submit|load|input|keyup|keydown)\s*=', html), ruta)
            self.assertNotIn('javascript:', html.lower(), ruta)
            if ruta.startswith('/reportes'):
                self.assertNotIn('style="', html, ruta)
                self.assertIn('/static/css/reportes.css', html)
                self.assertIn('/static/js/reportes.js', html)

    def test_la_politica_sigue_siendo_estricta(self):
        self.assertIn("script-src 'self'", CSP)
        self.assertNotIn("script-src 'self' 'unsafe-inline'", CSP)


class JavaScriptTests(unittest.TestCase):
    def setUp(self):
        self.js = (RAIZ / 'app' / 'static' / 'js' / 'reportes.js').read_text(encoding='utf-8')

    def test_es_propio_y_no_toca_nada_peligroso(self):
        self.assertIn("'use strict'", self.js)
        for peligroso in ('innerHTML', 'eval(', 'new Function', 'document.write', 'localStorage', 'sessionStorage', 'document.cookie', 'fetch('):
            self.assertNotIn(peligroso, self.js)

    def test_cubre_el_selector_de_rango(self):
        for pista in ("'rango'", 'rango.hidden', 'ini.required', 'setCustomValidity', 'preventDefault'):
            self.assertIn(pista, self.js)

    def test_tiene_sintaxis_valida(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node no está instalado')
        r = subprocess.run([node, '--check', str(RAIZ / 'app' / 'static' / 'js' / 'reportes.js')], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)


class MatrizTests(unittest.TestCase):
    def test_las_rutas_de_reporte_estan_clasificadas_en_la_matriz(self):
        matriz = (RAIZ / 'tests' / 'test_matriz_permisos.py').read_text(encoding='utf-8')
        for ruta in ('/reportes/ventas', '/reportes/finanzas', '/reportes/inventario'):
            self.assertIn(f"'{ruta}", matriz)


if __name__ == '__main__':
    unittest.main()
