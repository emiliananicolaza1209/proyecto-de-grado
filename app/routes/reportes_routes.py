"""Reporte por periodo (ventas, finanzas, inventario). La ruta recibe el periodo, delega en reporte_service y arma los enlaces."""
from flask import Blueprint, Response, abort, g, render_template, request, url_for

from ..auth import can, require, role
from ..services import consultas_service as cs
from ..services import reporte_service
from ..services.operacion_service import today

reportes = Blueprint('reportes', __name__)
ACTIVOS = {'ventas': 'ventas', 'finanzas': 'finanzas', 'inventario': 'inventario'}
# Páginas donde aparece el botón de reporte: endpoint -> módulo del reporte.
PAGINAS_CON_PANEL = {'ventas.index': 'ventas', 'inventory.index': 'inventario', 'finanzas.index': 'finanzas'}


@reportes.app_context_processor
def contexto_del_panel():
    modulo = PAGINAS_CON_PANEL.get(request.endpoint) if can('reportes') else None
    return {'reporte_panel_modulo': modulo, 'reporte_opciones': reporte_service.OPCIONES,
            'reporte_estados': reporte_service.ETIQUETAS_ESTADO, 'reporte_hoy': today(),
            'reporte_seleccion_inicial': {'tipo': 'semana', 'ini': '', 'fin': '', 'umbral': '', 'comparar': False},
            'reporte_umbral_defecto': cs.UMBRAL_PERMANENCIA_DIAS, 'reporte_umbral_maximo': cs.MAX_UMBRAL_DIAS,
            'reporte_modulos_que_comparan': [m for m, c in reporte_service.MODULOS.items() if c['comparar']]}


def _exportaciones(reporte):
    """Enlaces a las exportaciones que ya existen en la aplicación, para el mismo periodo (solo si el perfil puede usarlas)."""
    periodo, enlaces = reporte['periodo'], []
    if reporte['modulo'] == 'ventas' and periodo and can('contabilidad'):
        for etiqueta, endpoint in (('Paquete para el contador (Excel)', 'contabilidad.paquete_excel'),
                                   ('Paquete para el contador (PDF)', 'contabilidad.paquete_pdf'),
                                   ('Consolidado contable (CSV)', 'contabilidad.exportar_csv')):
            enlaces.append({'etiqueta': etiqueta, 'url': url_for(endpoint, ini=periodo['ini'], fin=periodo['fin'])})
    if reporte['modulo'] == 'finanzas' and can('admin'):
        resultado = next((r for r in reporte['resultados'] if r['consulta'] == 'resumen_financiero'), None)
        for fila in ((resultado or {}).get('detalle') or {}).get('por_jornada', [])[:62]:
            enlaces.append({'etiqueta': f"Jornada {fila['fecha']} (CSV de Finanzas)", 'url': url_for('finanzas.export', date=fila['fecha'])})
    return enlaces


@reportes.get('/reportes/<modulo>')
@require('reportes')
def ver(modulo):
    if modulo not in reporte_service.MODULOS:
        abort(404)
    usuario = getattr(g, 'usuario', None)
    seleccion = {'tipo': request.args.get('periodo', 'semana'), 'ini': request.args.get('ini', ''), 'fin': request.args.get('fin', ''),
                 'umbral': request.args.get('umbral', ''), 'comparar': request.args.get('comparar') == '1'}
    error, reporte = None, None
    try:
        reporte = reporte_service.generar(role(), modulo, seleccion['tipo'], seleccion['ini'], seleccion['fin'],
                                          usuario=usuario.nombre if usuario else None, usuario_id=usuario.id if usuario else 0,
                                          comparar=seleccion['comparar'], umbral=seleccion['umbral'])
    except reporte_service.ReporteInvalido as exc:
        error = str(exc)
    formato = request.args.get('formato', 'html')
    if reporte and formato == 'csv':
        periodo = reporte['periodo']
        nombre = f"reporte_{modulo}_{periodo['ini']}_{periodo['fin']}.csv" if periodo else f"reporte_{modulo}_{reporte['generado_en']}.csv"
        return Response('﻿' + reporte_service.a_csv(reporte), mimetype='text/csv; charset=utf-8',
                        headers={'Content-Disposition': f'attachment; filename={nombre}', 'Cache-Control': 'no-store'})
    return render_template('reportes/ver.html', active=ACTIVOS[modulo], modulo=modulo, reporte=reporte, error=error,
                           seleccion=seleccion, tipos=reporte_service.ETIQUETAS_TIPO, conf=reporte_service.MODULOS[modulo],
                           exportaciones=_exportaciones(reporte) if reporte else []), (400 if error else 200)
