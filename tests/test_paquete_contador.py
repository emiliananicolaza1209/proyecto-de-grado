"""Paquete consolidado para el contador: el Excel sale de los mismos datos que la pantalla y el CSV."""
import csv
import io
import re
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from _cleanup import release
from app import create_app
from app.extensions import db
from app.models import Producto
from app.models.contabilidad import BancoDestino, ConsignacionBancaria, PersonaBanco, PersonaContable
from app.services import paquete_contador_service as paquete
from app.services.contabilidad_service import (
    alertas_uvt, consolidar_periodo, datos_paquete, evaluar_estado_renta, generar_csv, registrar_ingreso_gasto,
)
from app.services.operacion_service import today

CEDULA = '900123456'
INI = '2025-01-01'


class PaqueteBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'DATABASE': str(Path(self.tmp.name) / 'db.sqlite'), 'SECRET_KEY': 'test'})
        self.client = self.app.test_client()
        self.hoy = today()
        with self.app.app_context():
            self._sembrar()

    def tearDown(self):
        release(self.app)
        self.tmp.cleanup()

    def _producto(self, imei, estado='Disponible', **extra):
        base = dict(imei=imei, model='IPHONE PRUEBA 128', capacity=128, color='NEGRO', condition='Nuevo',
                    cost_cents=300000000, location='LOCAL', supplier='CP CELULARES', status=estado,
                    created_at=self.hoy + ' 10:00:00')
        base.update(extra)
        db.session.add(Producto(**base))

    def _sembrar(self):
        persona = PersonaContable(nombre='ANA PRUEBA', identificacion=CEDULA, tipo='Natural')
        banco = BancoDestino(nombre='BANCO PRUEBA')
        db.session.add_all([persona, banco]); db.session.flush()
        db.session.add(PersonaBanco(persona_id=persona.id, banco_id=banco.id))
        self._producto('490154203237518', 'Vendido', sale_value_cents=500000000, paid_cents=200000000,
                       payment_status='Parcial', sale_date=self.hoy + ' 11:00:00',
                       seller='VENDEDOR PRUEBA', responsible='CLIENTE PRUEBA')
        self._producto('490154203237526', cost_cents=250000000)
        for tipo, concepto, categoria, valor, resp in (('GASTO', 'Arriendo local', 'ARRIENDO', '800000', 'Jonatan Responsable'),
                                                       ('INGRESO', 'Servicio técnico', 'SERVICIOS', '250000', 'Otra Persona')):
            registrar_ingreso_gasto({'tipo': tipo, 'concepto': concepto, 'categoria': categoria, 'valor': valor,
                                     'fecha': self.hoy, 'relacion': '', 'soporte_ref': 'FAC-1', 'responsable': resp})
        hoy = datetime.strptime(self.hoy, '%Y-%m-%d')
        for monto, ref, activa, fecha in ((Decimal('1500000.00'), 'ACTIVA-1', True, hoy),
                                          (Decimal('700000.00'), 'ANULADA-1', False, hoy),
                                          (Decimal('400000.00'), 'ANIO-ANTERIOR', True, datetime(2025, 6, 10))):
            db.session.add(ConsignacionBancaria(persona_id=persona.id, banco_id=banco.id, monto=monto,
                                                fecha=fecha, referencia=ref, activa=activa))
        db.session.commit()
        self.persona_id = persona.id

    def libro(self, ini=INI, fin=None):
        with self.app.app_context():
            datos = datos_paquete(ini, fin or self.hoy)
            modelo = paquete.construir_modelo(datos, 'prueba@cp', self.hoy + ' 12:00')
        return load_workbook(io.BytesIO(paquete.generar_excel(modelo))), datos

    @staticmethod
    def filas(ws):
        return [[c.value for c in fila] for fila in ws.iter_rows()]

    @staticmethod
    def tabla(ws, titulo_primera_col):
        """Filas de datos de la tabla que empieza en el encabezado dado, hasta la fila 'Total' o el vacío."""
        todas = PaqueteBase.filas(ws)
        inicio = next(i for i, f in enumerate(todas) if f[0] == titulo_primera_col)
        datos, total = [], None
        for f in todas[inicio + 1:]:
            if f[0] is None:
                break
            if f[0] == 'Total':
                total = f
                break
            datos.append(f)
        return datos, total


class PaqueteExcelTests(PaqueteBase):
    def test_una_hoja_por_tema_en_orden(self):
        wb, _ = self.libro()
        self.assertEqual(wb.sheetnames, list(paquete.HOJAS))

    def test_resumen_coincide_con_consolidado_csv_y_pantalla(self):
        wb, datos = self.libro()
        c = datos['consolidado']
        resumen = {f[0]: f for f in self.filas(wb['Resumen']) if f[0] and isinstance(f[2], (int, float, Decimal))}
        esperado = {'Compras': c['compras'], 'Ventas': c['ventas'], 'Ingresos adicionales': c['ingresos'],
                    'Gastos': c['gastos'], 'Consignaciones': c['consignaciones']}
        for nombre, bloque in esperado.items():
            self.assertEqual(resumen[nombre][2], Decimal(bloque['total_cents']) / 100, nombre)
            self.assertEqual(resumen[nombre][1], bloque['count'], nombre)
        self.assertEqual(resumen['Utilidad estimada (venta-costo)'][2], Decimal(c['ventas']['utilidad_cents']) / 100)
        # CSV de Andres: mismas cifras (sección, cantidad, total)
        filas_csv = list(csv.reader(io.StringIO(generar_csv(c).lstrip('﻿'))))
        csv_resumen = {f[0]: f for f in filas_csv[filas_csv.index(['Sección', 'Cantidad', 'Total COP']) + 1:] if len(f) == 3 and f[0]}
        for nombre in ('Compras', 'Ventas', 'Ingresos adicionales', 'Gastos', 'Consignaciones', 'Utilidad estimada (venta-costo)'):
            self.assertEqual(resumen[nombre][2], Decimal(csv_resumen[nombre][2]), nombre)
        # Pantalla Información contable: mismas cifras en la sección del consolidado
        html = self.client.get(f'/modulos/tributario/?ini={INI}&fin={self.hoy}').get_data(as_text=True)
        seccion = html[html.index('accounting-consolidado'):html.index('</section>', html.index('accounting-consolidado'))]
        for bloque in (c['compras'], c['ventas'], c['ingresos'], c['gastos'], c['consignaciones']):
            self.assertIn('${:,.0f}'.format(bloque['total_cents'] / 100), seccion)
        self.assertIn('${:,.0f}'.format(c['ventas']['utilidad_cents'] / 100), seccion)

    def test_suma_del_detalle_igual_al_total_en_cada_hoja(self):
        wb, datos = self.libro()
        columnas_dinero = {'Compras': [5], 'Ventas': [3, 4, 5, 6, 7], 'Ingresos': [5], 'Gastos': [5], 'Consignaciones': [4]}
        for hoja, indices in columnas_dinero.items():
            detalle, total = self.tabla(wb[hoja], 'Fecha')
            self.assertIsNotNone(total, hoja)
            self.assertTrue(detalle, hoja)
            for i in indices:
                self.assertEqual(sum(f[i] for f in detalle), total[i], f'{hoja} col {i}')
        ventas, total = self.tabla(wb['Ventas'], 'Fecha')
        self.assertEqual(ventas[0][7], Decimal('3000000.00'))  # saldo: 5.000.000 - 2.000.000 cobrados
        self.assertEqual(total[7], Decimal(datos['consolidado']['ventas']['saldo_cents']) / 100)

    def test_subtotales_por_proveedor_y_categoria(self):
        wb, datos = self.libro()
        filas = self.filas(wb['Compras'])
        i = next(k for k, f in enumerate(filas) if f[0] == 'Subtotal por proveedor')
        self.assertEqual(filas[i + 2][0], 'CP CELULARES')
        self.assertEqual(filas[i + 2][2], Decimal(datos['consolidado']['compras']['total_cents']) / 100)

    def test_alerta_uvt_coincide_con_la_pantalla_aun_con_consignacion_anulada(self):
        wb, datos = self.libro()
        filas, _ = self.tabla(wb['Alerta UVT'], 'Año')
        por_anio = {f[0]: f for f in filas}
        self.assertEqual(sorted(por_anio), [2025, 2026])  # periodo de dos años -> un bloque por año
        with self.app.app_context():
            e26 = evaluar_estado_renta(self.persona_id, 2026)
            e25 = evaluar_estado_renta(self.persona_id, 2025)
        self.assertEqual(por_anio[2026][4], Decimal(str(e26['total_consignado'])))
        self.assertEqual(por_anio[2026][4], Decimal('1500000.00'))  # la anulada (700.000) no suma
        self.assertEqual(por_anio[2025][4], Decimal(str(e25['total_consignado'])))
        self.assertEqual(por_anio[2026][5], Decimal(e26['tope_limite']))
        self.assertEqual(por_anio[2026][7], 'Dentro del umbral')
        # consolidado (hoja Consignaciones) == alerta del año actual + la del año anterior, y sin la anulada
        _, total_cons = self.tabla(wb['Consignaciones'], 'Fecha')
        self.assertEqual(total_cons[4], por_anio[2026][4] + por_anio[2025][4])
        textos = {c.value for ws in wb for fila in ws.iter_rows() for c in fila}
        self.assertNotIn('ANULADA-1', textos)
        # pantalla: la tarjeta de personas muestra el mismo total del año
        html = self.client.get(f'/modulos/tributario/?anio=2026&ini={INI}&fin={self.hoy}').get_data(as_text=True)
        self.assertIn('$1,500,000.00', html)

    def test_alerta_uvt_omite_personas_sin_consignaciones_en_el_anio(self):
        with self.app.app_context():
            db.session.add(PersonaContable(nombre='SIN MOVIMIENTO', identificacion='55555', tipo='Natural')); db.session.commit()
            nombres = {a['persona'] for a in alertas_uvt(INI, self.hoy)}
        self.assertEqual(nombres, {'ANA PRUEBA'})

    def test_no_incluye_datos_personales_innecesarios(self):
        wb, _ = self.libro()
        celdas = [(ws.title, str(c.value)) for ws in wb for fila in ws.iter_rows() for c in fila if c.value is not None]
        for prohibido in ('VENDEDOR PRUEBA', 'CLIENTE PRUEBA', 'Jonatan', 'Otra Persona', 'Responsable', 'declaro', 'password'):
            self.assertFalse([h for h, t in celdas if prohibido in t], prohibido)
        donde_cedula = {h for h, t in celdas if CEDULA in t}
        self.assertEqual(donde_cedula, {'Alerta UVT'})  # la identificación completa solo en la hoja Alerta UVT
        self.assertIn('ANA PRUEBA', {t for h, t in celdas if h == 'Consignaciones'})  # el nombre sí, para conciliar

    def test_importes_son_numeros_y_el_imei_texto(self):
        wb, _ = self.libro()
        compras, _ = self.tabla(wb['Compras'], 'Fecha')
        self.assertTrue(all(isinstance(f[5], (int, float)) for f in compras))  # importes: números, no texto
        self.assertEqual({f[1] for f in compras}, {'490154203237518', '490154203237526'})  # IMEI completo, como texto
        self.assertTrue(all(isinstance(f[1], str) for f in compras))
        self.assertEqual(wb['Compras'].cell(row=5, column=6).number_format, '#,##0.00')

    def test_incluye_avisos_y_pendientes(self):
        wb, datos = self.libro()
        resumen = {str(c.value) for fila in wb['Resumen'].iter_rows() for c in fila if c.value}
        self.assertIn(paquete.AVISO_RN, resumen)
        self.assertIn(paquete.AVISO_PRIVACIDAD, resumen)
        pendientes = [f[0] for f in self.filas(wb['Pendientes']) if f[0]][1:]
        self.assertEqual(pendientes, datos['consolidado']['faltantes'] or ['Sin pendientes en el periodo.'])
        self.assertTrue(any('saldo pendiente' in p for p in pendientes))

    def test_periodo_sin_movimientos_genera_libro_valido(self):
        wb, _ = self.libro(ini='2000-01-01', fin='2000-01-31')
        self.assertEqual(wb.sheetnames, list(paquete.HOJAS))
        self.assertEqual(self.tabla(wb['Compras'], 'Fecha')[0], [])
        self.assertTrue(any('Sin consignaciones' in str(f[0]) for f in self.filas(wb['Alerta UVT'])))

    def test_modelo_no_cambia_los_datos_de_origen(self):
        with self.app.app_context():
            antes = consolidar_periodo(INI, self.hoy)
            paquete.construir_modelo(datos_paquete(INI, self.hoy), 'x', 'y')
            self.assertEqual(consolidar_periodo(INI, self.hoy), antes)


class PaquetePdfTests(PaqueteBase):
    def modelo(self, ini=INI, fin=None):
        with self.app.app_context():
            datos = datos_paquete(ini, fin or self.hoy)
            return paquete.construir_modelo(datos, 'prueba@cp', self.hoy + ' 12:00'), datos

    def pdf(self, comprimir=False, **kw):
        modelo, datos = self.modelo(**kw)
        return paquete.generar_pdf(modelo, comprimir=comprimir), modelo, datos

    @staticmethod
    def paginas(raw):
        return len(re.findall(rb'/Type\s*/Page(?![a-z])', raw))

    def test_es_un_pdf_valido(self):
        raw, _, _ = self.pdf(comprimir=True)  # tal como sale en producción
        self.assertTrue(raw.startswith(b'%PDF'))
        self.assertIn(b'%%EOF', raw[-32:])
        self.assertEqual(self.paginas(raw), 7)  # resumen + 5 temas + alerta UVT con pendientes

    def test_cifras_del_pdf_coinciden_con_el_consolidado_y_la_pantalla(self):
        raw, modelo, datos = self.pdf()
        c = datos['consolidado']
        for nombre, cantidad, cents in modelo['resumen']:
            self.assertIn('${:,.0f}'.format(cents / 100).encode('cp1252'), raw, nombre)
        for bloque in (c['compras'], c['ventas'], c['ingresos'], c['gastos'], c['consignaciones']):
            self.assertIn('${:,.0f}'.format(bloque['total_cents'] / 100).encode('cp1252'), raw)
        html = self.client.get(f'/modulos/tributario/?ini={INI}&fin={self.hoy}').get_data(as_text=True)
        seccion = html[html.index('accounting-consolidado'):html.index('</section>', html.index('accounting-consolidado'))]
        for bloque in (c['compras'], c['ventas'], c['ingresos'], c['gastos'], c['consignaciones']):
            cifra = '${:,.0f}'.format(bloque['total_cents'] / 100)
            self.assertIn(cifra, seccion)   # pantalla
            self.assertIn(cifra.encode('cp1252'), raw)  # PDF

    def test_secciones_periodo_y_avisos(self):
        raw, _, _ = self.pdf()
        for texto in (b'Consolidado contable-tributario', f'{INI}'.encode(), self.hoy.encode(), b'Compras de inventario',
                      b'Ventas de equipos', b'Ingresos adicionales', b'Consignaciones bancarias activas',
                      b'Alerta de consignaciones', b'Ley 1581', b'RN-TRI-001', b'P\\341gina 1'):
            self.assertIn(texto, raw, texto)

    def test_alerta_uvt_en_el_pdf_con_cedula_solo_en_esa_seccion(self):
        raw, modelo, _ = self.pdf()
        inicio_alerta = raw.index(b'Alerta de consignaciones')
        # una vez por fila de alerta (2025 y 2026) y nunca antes de la sección Alerta UVT
        self.assertEqual(raw.count(CEDULA.encode()), len(modelo['alertas']['filas']))
        self.assertGreater(raw.index(CEDULA.encode()), inicio_alerta)
        self.assertIn(b'Dentro del umbral', raw)

    def test_sin_datos_personales_innecesarios_ni_anuladas(self):
        raw, _, _ = self.pdf()
        for prohibido in (b'VENDEDOR PRUEBA', b'CLIENTE PRUEBA', b'Jonatan', b'Otra Persona', b'ANULADA-1'):
            self.assertNotIn(prohibido, raw, prohibido)
        self.assertIn(b'ACTIVA-1', raw)
        self.assertIn(b'ANA PRUEBA', raw)

    def test_tablas_largas_continuan_con_encabezado_repetido(self):
        modelo, _ = self.modelo()
        compras = modelo['tablas'][0]
        compras['filas'] = compras['filas'] * 60  # 120 filas: no caben en una página
        raw = paquete.generar_pdf(modelo, comprimir=False)
        paginas_compras = self.paginas(raw) - self.paginas(paquete.generar_pdf(self.modelo()[0], comprimir=False))
        self.assertGreaterEqual(paginas_compras, 2)
        self.assertGreaterEqual(raw.count(b'Costo COP'), 3)  # el encabezado se repite en cada página

    def test_caracteres_fuera_de_latin1_y_marcas_no_rompen_el_pdf(self):
        modelo, _ = self.modelo()
        modelo['tablas'][3]['filas'].append(['2026-01-01', 'Ñandú ✓ <b>&</b>', 'OTRO', '', '', 100])
        raw = paquete.generar_pdf(modelo, comprimir=True)
        self.assertTrue(raw.startswith(b'%PDF'))

    def test_periodo_sin_movimientos(self):
        raw, _, _ = self.pdf(ini='2000-01-01', fin='2000-01-31')
        self.assertTrue(raw.startswith(b'%PDF'))
        self.assertIn(b'Sin registros en el periodo.', raw)
        self.assertIn(b'Sin consignaciones activas', raw)

    def test_excel_y_pdf_usan_las_mismas_cifras(self):
        modelo, _ = self.modelo()
        wb = load_workbook(io.BytesIO(paquete.generar_excel(modelo)))
        raw = paquete.generar_pdf(modelo, comprimir=False)
        for fila in self.filas(wb['Resumen']):
            if fila[0] and isinstance(fila[2], (int, float, Decimal)) and fila[0] != 'Sección':
                self.assertIn('${:,.0f}'.format(float(fila[2])).encode('cp1252'), raw, fila[0])


if __name__ == '__main__':
    unittest.main()
