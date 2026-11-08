"""Paquete consolidado para el contador (Excel y PDF).

No calcula nada nuevo: recibe `datos_paquete()` (el mismo consolidado y las mismas alertas UVT que
muestra Información contable) y los acomoda en un modelo de tablas que consumen el Excel y el PDF.
Sin `request` ni `session`: el usuario y la hora llegan como argumentos.

Datos personales (Ley 1581): solo los necesarios. Sin vendedores, responsables ni clientes.
Nombre de quien recibe consignaciones en el detalle; la identificación completa únicamente en la
hoja/sección "Alerta UVT" (finalidad: control del tope de 1.400 UVT).
"""
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

AVISO_RN = 'Apoyo informativo para el contador: no determina impuestos ni reemplaza su criterio (RN-TRI-001).'
AVISO_PRIVACIDAD = ('Documento confidencial. Contiene datos personales tratados con finalidad contable y '
                    'tributaria (Ley 1581 de 2012). Uso restringido al contador; no lo reenvíes ni lo publiques.')
AVISO_UVT = ('El tope de 1.400 UVT se mide por año calendario completo (consignaciones activas), no solo por el '
             'periodo elegido. Esta alerta no determina por sí sola la obligación de declarar.')
HOJAS = ('Resumen', 'Compras', 'Ventas', 'Ingresos', 'Gastos', 'Consignaciones', 'Alerta UVT', 'Pendientes')

TEXTO, DINERO, PORCENTAJE, ENTERO = 'texto', 'dinero', 'porcentaje', 'entero'


def cop(cents):
    """Centavos enteros -> Decimal con dos decimales (nunca float)."""
    return (Decimal(int(cents)) / 100).quantize(Decimal('0.01'))


def _tabla(hoja, titulo, columnas, filas, totales=None, subtotales=None):
    return {'hoja': hoja, 'titulo': titulo, 'columnas': columnas, 'filas': filas,
            'totales': totales, 'subtotales': subtotales}


def _subtotal(titulo, encabezado, agrupado):
    filas = [[nombre, datos['count'], datos['total_cents']] for nombre, datos in sorted(agrupado.items())]
    return {'titulo': titulo, 'columnas': [(encabezado, TEXTO), ('Cantidad', ENTERO), ('Total COP', DINERO)],
            'filas': filas}


def construir_modelo(datos, actor, generado_en):
    """datos: resultado de contabilidad_service.datos_paquete(). generado_en: texto 'AAAA-MM-DD HH:MM'."""
    c = datos['consolidado']
    compras, ventas, ingresos, gastos, cons = (c[k] for k in ('compras', 'ventas', 'ingresos', 'gastos', 'consignaciones'))

    meta = {'ini': c['ini'], 'fin': c['fin'], 'actor': actor, 'generado': generado_en}
    # Mismas filas y orden que el CSV de Andres (generar_csv) más cobrado y saldo de ventas.
    resumen = [
        ('Compras', compras['count'], compras['total_cents']),
        ('Ventas', ventas['count'], ventas['total_cents']),
        ('Utilidad estimada (venta-costo)', None, ventas['utilidad_cents']),
        ('Ventas cobradas', None, ventas['cobrado_cents']),
        ('Saldo por cobrar de ventas', None, ventas['saldo_cents']),
        ('Ingresos adicionales', ingresos['count'], ingresos['total_cents']),
        ('Gastos', gastos['count'], gastos['total_cents']),
        ('Consignaciones', cons['count'], cons['total_cents']),
    ]

    tablas = [
        _tabla('Compras', 'Compras de inventario',
               [('Fecha', TEXTO), ('IMEI', TEXTO), ('Modelo', TEXTO), ('Lote', TEXTO), ('Proveedor', TEXTO), ('Costo COP', DINERO)],
               [[r['fecha'], r['imei'], r['modelo'], r['lote'], r['proveedor'], r['valor_cents']] for r in compras['detalle']],
               totales={5: compras['total_cents']},
               subtotales=_subtotal('Subtotal por proveedor', 'Proveedor', compras['por_proveedor'])),
        _tabla('Ventas', 'Ventas de equipos',
               [('Fecha', TEXTO), ('IMEI', TEXTO), ('Modelo', TEXTO), ('Valor venta COP', DINERO), ('Costo COP', DINERO),
                ('Utilidad COP', DINERO), ('Cobrado COP', DINERO), ('Saldo COP', DINERO)],
               [[r['fecha'], r['imei'], r['modelo'], r['valor_cents'], r['costo_cents'], r['valor_cents'] - r['costo_cents'],
                 r['cobrado_cents'], r['saldo_cents']] for r in ventas['detalle']],
               totales={3: ventas['total_cents'], 4: ventas['costo_cents'], 5: ventas['utilidad_cents'],
                        6: ventas['cobrado_cents'], 7: ventas['saldo_cents']}),
    ]
    for hoja, titulo, bloque in (('Ingresos', 'Ingresos adicionales', ingresos), ('Gastos', 'Gastos', gastos)):
        tablas.append(_tabla(
            hoja, titulo,
            [('Fecha', TEXTO), ('Concepto', TEXTO), ('Categoría', TEXTO), ('Relación', TEXTO), ('Soporte', TEXTO), ('Valor COP', DINERO)],
            [[r['fecha'], r['concepto'], r['categoria'], r['relacion'], r['soporte_ref'], r['valor_cents']] for r in bloque['detalle']],
            totales={5: bloque['total_cents']},
            subtotales=_subtotal('Subtotal por categoría', 'Categoría', bloque['por_categoria'])))
    tablas.append(_tabla(
        'Consignaciones', 'Consignaciones bancarias activas',
        [('Fecha', TEXTO), ('Persona', TEXTO), ('Banco', TEXTO), ('Referencia', TEXTO), ('Valor COP', DINERO)],
        [[r['fecha'], r['persona'], r['banco'], r['referencia'], r['valor_cents']] for r in cons['detalle']],
        totales={4: cons['total_cents']}))

    alertas = _tabla(
        'Alerta UVT', 'Alerta de consignaciones (1.400 UVT)',
        [('Año', ENTERO), ('Persona', TEXTO), ('Identificación', TEXTO), ('Tipo', TEXTO),
         ('Total consignado en el año COP', DINERO), ('Tope 1.400 UVT COP', DINERO), ('% del tope', PORCENTAJE), ('Estado', TEXTO)],
        [[a['anio'], a['persona'], a['identificacion'], a['tipo'], a['total_cents'],
          (a['tope_cop'] * 100 if a['tope_cop'] else None), a['porcentaje'], a['estado']] for a in datos['alertas_uvt']])

    return {'meta': meta, 'resumen': resumen, 'tablas': tablas, 'alertas': alertas,
            'pendientes': list(c['faltantes']), 'avisos': [AVISO_RN, AVISO_PRIVACIDAD]}


# ---------------------------------------------------------------- Excel
_ENCABEZADO = PatternFill('solid', fgColor='1F3A5F')
_MONEDA = '#,##0.00'


def _valor_celda(valor, tipo):
    if valor is None:
        return None
    if tipo == DINERO:
        return cop(valor)
    if tipo == PORCENTAJE:
        return Decimal(str(valor))
    return valor


def _escribir_tabla(ws, fila, columnas, filas, totales=None, etiqueta_total='Total'):
    """Escribe encabezado, filas y fila de total; devuelve (fila_encabezado, fila_siguiente)."""
    cabecera = fila
    for i, (nombre, _tipo) in enumerate(columnas, 1):
        celda = ws.cell(row=fila, column=i, value=nombre)
        celda.font = Font(bold=True, color='FFFFFF')
        celda.fill = _ENCABEZADO
        celda.alignment = Alignment(wrap_text=True, vertical='center')
    for datos_fila in filas:
        fila += 1
        for i, ((_n, tipo), valor) in enumerate(zip(columnas, datos_fila), 1):
            celda = ws.cell(row=fila, column=i, value=_valor_celda(valor, tipo))
            if tipo == DINERO:
                celda.number_format = _MONEDA
            elif tipo == PORCENTAJE:
                celda.number_format = '0.00'
            elif valor is not None and tipo == TEXTO:
                celda.number_format = '@'  # IMEI y cédulas siempre como texto
    if totales:
        fila += 1
        ws.cell(row=fila, column=1, value=etiqueta_total).font = Font(bold=True)
        for indice, cents in totales.items():
            celda = ws.cell(row=fila, column=indice + 1, value=cop(cents))
            celda.number_format = _MONEDA
            celda.font = Font(bold=True)
    return cabecera, fila + 1


def _ajustar_anchos(ws, minimo=12, maximo=60):
    for columna in ws.columns:
        ancho = max((len(str(c.value)) for c in columna if c.value is not None), default=0)
        ws.column_dimensions[get_column_letter(columna[0].column)].width = max(minimo, min(maximo, ancho + 2))


def generar_excel(modelo):
    """Libro .xlsx en bytes, una hoja por tema. Importes numéricos (no texto, no fórmulas)."""
    meta = modelo['meta']
    wb = Workbook()
    ws = wb.active
    ws.title = 'Resumen'
    ws['A1'] = 'CP STORE · Consolidado contable-tributario'
    ws['A1'].font = Font(bold=True, size=14)
    ws['A2'] = 'Periodo'
    ws['B2'] = meta['ini']
    ws['C2'] = meta['fin']
    ws['A3'] = 'Generado por'
    ws['B3'] = meta['actor']
    ws['A4'] = 'Fecha de generación'
    ws['B4'] = meta['generado']
    for r in (2, 3, 4):
        ws.cell(row=r, column=1).font = Font(bold=True)
    _escribir_tabla(ws, 6, [('Sección', TEXTO), ('Cantidad', ENTERO), ('Total COP', DINERO)],
                    [list(f) for f in modelo['resumen']])
    fila = 6 + len(modelo['resumen']) + 2
    ws.cell(row=fila, column=1, value=f"Alertas UVT: {len(modelo['alertas']['filas'])} · "
                                      f"Registros por revisar: {len(modelo['pendientes'])}")
    for texto in modelo['avisos']:
        fila += 1
        ws.cell(row=fila, column=1, value=texto).alignment = Alignment(wrap_text=False)
    _ajustar_anchos(ws)

    for tabla in modelo['tablas']:
        ws = wb.create_sheet(tabla['hoja'])
        ws['A1'] = tabla['titulo']
        ws['A1'].font = Font(bold=True, size=13)
        ws['A2'] = f"Periodo {meta['ini']} a {meta['fin']}"
        cabecera, siguiente = _escribir_tabla(ws, 4, tabla['columnas'], tabla['filas'], tabla['totales'])
        ws.freeze_panes = ws.cell(row=cabecera + 1, column=1)
        ultima = cabecera + len(tabla['filas'])
        if tabla['filas']:
            ws.auto_filter.ref = f"A{cabecera}:{get_column_letter(len(tabla['columnas']))}{ultima}"
        sub = tabla['subtotales']
        if sub and sub['filas']:
            ws.cell(row=siguiente + 1, column=1, value=sub['titulo']).font = Font(bold=True)
            _escribir_tabla(ws, siguiente + 2, sub['columnas'], sub['filas'])
        _ajustar_anchos(ws)

    alertas = modelo['alertas']
    ws = wb.create_sheet('Alerta UVT')
    ws['A1'] = alertas['titulo']
    ws['A1'].font = Font(bold=True, size=13)
    ws['A2'] = AVISO_UVT
    cabecera, _ = _escribir_tabla(ws, 4, alertas['columnas'], alertas['filas'])
    if not alertas['filas']:
        ws.cell(row=5, column=1, value='Sin consignaciones activas en los años del periodo.')
    ws.freeze_panes = ws.cell(row=cabecera + 1, column=1)
    _ajustar_anchos(ws)

    ws = wb.create_sheet('Pendientes')
    ws['A1'] = 'Registros por revisar (datos faltantes o sin clasificar)'
    ws['A1'].font = Font(bold=True, size=13)
    for i, texto in enumerate(modelo['pendientes'] or ['Sin pendientes en el periodo.'], start=3):
        ws.cell(row=i, column=1, value=texto)
    _ajustar_anchos(ws, maximo=120)

    salida = BytesIO()
    wb.save(salida)
    return salida.getvalue()


# ---------------------------------------------------------------- PDF
_PESOS_COLUMNA = {
    'Fecha': 1.1, 'IMEI': 1.5, 'Modelo': 2.2, 'Lote': 1.0, 'Proveedor': 1.7, 'Concepto': 2.4, 'Categoría': 1.3,
    'Relación': 1.6, 'Soporte': 1.2, 'Persona': 2.3, 'Banco': 1.6, 'Referencia': 1.6, 'Identificación': 1.5,
    'Tipo': 0.9, 'Estado': 2.2, 'Año': 0.6, 'Cantidad': 0.9, 'Sección': 2.6,
}


def _t(valor):
    """Texto seguro para las fuentes estándar del PDF (cp1252); lo que no cabe sale como '?'."""
    return str(valor).encode('cp1252', 'replace').decode('cp1252')


def _fmt_pdf(valor, tipo):
    """Mismo formato que la pantalla Información contable: $ con separador de miles y sin decimales."""
    if valor is None:
        return ''
    if tipo == DINERO:
        return '${:,.0f}'.format(valor / 100)
    if tipo == PORCENTAJE:
        return f'{float(valor):.1f} %'
    return _t(valor)


def _esc(valor):
    """Escapa texto para usarlo dentro de un Paragraph de reportlab (que interpreta marcas tipo HTML)."""
    return _t(valor).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def generar_pdf(modelo, comprimir=True):
    """PDF A4 apaisado: portada-resumen, una sección por tema, pie con página y aviso de confidencialidad.

    comprimir=False deja el texto legible en los bytes (útil para pruebas); en producción va comprimido.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    meta = modelo['meta']
    pagina = landscape(A4)
    ancho_util = pagina[0] - 3 * cm
    estilos = getSampleStyleSheet()
    h1 = ParagraphStyle('h1', parent=estilos['Title'], fontSize=17, alignment=0, spaceAfter=4)
    h2 = ParagraphStyle('h2', parent=estilos['Heading2'], fontSize=12, spaceBefore=10, spaceAfter=4)
    normal = ParagraphStyle('n', parent=estilos['Normal'], fontSize=9, leading=11)
    nota = ParagraphStyle('nota', parent=normal, fontSize=8, leading=10, textColor=colors.HexColor('#444444'))
    celda = ParagraphStyle('c', parent=normal, fontSize=8, leading=9.5)
    celda_der = ParagraphStyle('cd', parent=celda, alignment=2)
    celda_enc = ParagraphStyle('ce', parent=celda, textColor=colors.white, fontName='Helvetica-Bold')
    azul = colors.HexColor('#1F3A5F')

    def tabla(columnas, filas, totales=None):
        pesos = [_PESOS_COLUMNA.get(n, 1.4 if tipo == DINERO else 1.0) for n, tipo in columnas]
        anchos = [ancho_util * p / sum(pesos) for p in pesos]
        derecha = {i for i, (_n, tipo) in enumerate(columnas) if tipo in (DINERO, PORCENTAJE, ENTERO)}
        datos = [[Paragraph(_esc(n), celda_enc) for n, _tipo in columnas]]
        for fila in filas:
            datos.append([Paragraph(_esc(_fmt_pdf(v, tipo)), celda_der if i in derecha else celda)
                          for i, ((_n, tipo), v) in enumerate(zip(columnas, fila))])
        estilo = [('BACKGROUND', (0, 0), (-1, 0), azul), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                  ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#BBBBBB')),
                  ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F3F6FA')]),
                  ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]
        if totales:
            fila_total = [Paragraph('<b>Total</b>', celda)] + [''] * (len(columnas) - 1)
            for indice, cents in totales.items():
                fila_total[indice] = Paragraph('<b>%s</b>' % _fmt_pdf(cents, DINERO), celda_der)
            datos.append(fila_total)
            estilo += [('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#DDE6F2')),
                       ('LINEABOVE', (0, -1), (-1, -1), 0.8, azul)]
        t = Table(datos, colWidths=anchos, repeatRows=1)
        t.setStyle(TableStyle(estilo))
        return t

    def pie(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(colors.HexColor('#555555'))
        canvas.drawString(1.5 * cm, 0.9 * cm,
                          _t(f"CP STORE · Periodo {meta['ini']} a {meta['fin']} · Documento confidencial (Ley 1581 de 2012)"))
        canvas.drawRightString(pagina[0] - 1.5 * cm, 0.9 * cm, f'Página {doc.page}')
        canvas.restoreState()

    historia = [Paragraph('CP STORE · Consolidado contable-tributario', h1),
                Paragraph(f"Periodo: <b>{_esc(meta['ini'])}</b> a <b>{_esc(meta['fin'])}</b> &nbsp;·&nbsp; "
                          f"Generado por: {_esc(meta['actor'])} &nbsp;·&nbsp; {_esc(meta['generado'])}", normal),
                Spacer(1, 6), Paragraph('Resumen', h2),
                tabla([('Sección', TEXTO), ('Cantidad', ENTERO), ('Total COP', DINERO)], [list(f) for f in modelo['resumen']]),
                Spacer(1, 6),
                Paragraph(f"Alertas UVT: {len(modelo['alertas']['filas'])} · Registros por revisar: {len(modelo['pendientes'])}", normal),
                Spacer(1, 4)]
    historia += [Paragraph(_esc(texto), nota) for texto in modelo['avisos']]

    for t in modelo['tablas']:
        historia += [PageBreak(), Paragraph(_esc(t['titulo']), h2)]
        if t['filas']:
            historia.append(tabla(t['columnas'], t['filas'], t['totales']))
        else:
            historia.append(Paragraph('Sin registros en el periodo.', normal))
        sub = t['subtotales']
        if sub and sub['filas']:
            historia += [Spacer(1, 8), Paragraph(_esc(sub['titulo']), h2), tabla(sub['columnas'], sub['filas'])]

    alertas = modelo['alertas']
    historia += [PageBreak(), Paragraph(_esc(alertas['titulo']), h2), Paragraph(_esc(AVISO_UVT), nota), Spacer(1, 4)]
    if alertas['filas']:
        historia.append(tabla(alertas['columnas'], alertas['filas']))
    else:
        historia.append(Paragraph('Sin consignaciones activas en los años del periodo.', normal))

    historia += [Spacer(1, 10), Paragraph('Registros por revisar (datos faltantes o sin clasificar)', h2)]
    historia += [Paragraph(_esc('• ' + texto), normal) for texto in (modelo['pendientes'] or ['Sin pendientes en el periodo.'])]

    salida = BytesIO()
    doc = SimpleDocTemplate(salida, pagesize=pagina, leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.4 * cm,
                            bottomMargin=1.6 * cm, title='CP Store - Consolidado contable', author='CP Store',
                            pageCompression=1 if comprimir else 0)
    doc.build(historia, onFirstPage=pie, onLaterPages=pie)
    return salida.getvalue()
