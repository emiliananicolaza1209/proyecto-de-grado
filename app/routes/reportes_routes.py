import csv
import io
import json
from flask import Blueprint, request, render_template, jsonify, send_file, abort, redirect, url_for, flash, g, Response
from openpyxl import Workbook
from ..extensions import db
from ..auth import require, can, role
from ..services import reportes_service as svc, alertas_service as alerts
from ..services import consultas_service as cs, reporte_service
from ..services.operacion_service import today
from ..services import reportes_presentacion as presentation
from ..services.gestion_comun import audit

reportes=Blueprint('reportes',__name__)


@reportes.get('/api/consultas/<tool>')
@require('admin')
def query_api(tool):
    try:
        data=alerts.consult(tool,request.args)
        if 'filas' in data:
            data['cantidad_filas']=len(data['filas']);data['detalle_limitado']=len(data['filas'])>100
            data['filas']=data['filas'][:100]
        return jsonify(data)
    except ValueError as e:return jsonify(error=str(e)),400


def result(kind):
    if kind not in svc.REPORTS:abort(404)
    if kind=='inventario':
        if not can('consulta'):abort(403)
        return svc.inventory(request.args,can('costos'),can('admin'))
    if not can('admin'):abort(403)
    return svc.REPORTS[kind](request.args)


@reportes.get('/reportes')
@require('consulta')
def index():
    kind=request.args.get('tipo','inventario')
    try:r=result(kind);error=None
    except ValueError as e:r=None;error=str(e)
    export_args=request.args.to_dict()
    for key in ('kind','fmt'):export_args.pop(key,None)
    export_args['presentacion']='usuario'
    return render_template('reportes/index.html',r=r,error=error,kind=kind,args=request.args,
        kinds=presentation.TITLES,view=presentation.present(kind,r,request.args) if r else None,
        filters=presentation.filter_options(can('admin')),
        export_urls={fmt:url_for('reportes.export',kind=kind,fmt=fmt,**export_args) for fmt in ('xlsx','csv')},
        active='analitica')


def cell(v):
    if isinstance(v,(dict,list)):return json.dumps(v,ensure_ascii=False)
    # Prevent spreadsheet formulas from untrusted names/descriptions.
    if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')):return "'"+v
    return v


@reportes.get('/reportes/exportar/<kind>/<fmt>')
@require('consulta')
def export(kind,fmt):
    try:r=result(kind)
    except ValueError as e:abort(400,str(e))
    if fmt not in ('xlsx','csv'):abort(404)
    if request.args.get('presentacion')=='usuario':
        return user_export(kind,fmt,r)
    rows=r['filas'];headers=list(rows[0]) if rows else ['sin_registros']
    metadata={k:v for k,v in r.items() if k!='filas'}
    if fmt=='xlsx':
        wb=Workbook();ws=wb.active;ws.title='Datos';ws.append(headers)
        for row in rows:ws.append([cell(row.get(k)) for k in headers])
        ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
        for col in ws.columns:ws.column_dimensions[col[0].column_letter].width=24
        meta=wb.create_sheet('Metadatos')
        for k,v in metadata.items():meta.append([k,cell(v)])
        out=io.BytesIO();wb.save(out);out.seek(0)
        return send_file(out,as_attachment=True,download_name=f'cpstore_{kind}.xlsx',mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    out=io.StringIO();w=csv.writer(out,delimiter=';')
    for k,v in metadata.items():w.writerow(['# '+k,cell(v)])
    w.writerow(headers)
    for row in rows:w.writerow([cell(row.get(k)) for k in headers])
    return send_file(io.BytesIO(out.getvalue().encode('utf-8-sig')),as_attachment=True,download_name=f'cpstore_{kind}.csv',mimetype='text/csv')


def user_export(kind,fmt,data):
    """Descarga visible en pesos y nombres; el contrato técnico sigue disponible."""
    view=presentation.present(kind,data,request.args)
    if fmt=='xlsx':
        wb=Workbook();ws=wb.active;ws.title='Datos'
        def fill(sheet,table):
            sheet.append([c['label'] for c in table['columns']])
            for row in table['rows']:
                sheet.append([cell(c['value']) for c in row])
                for index,c in enumerate(row,1):
                    if c['kind']=='money' and not isinstance(c['value'],str):
                        sheet.cell(sheet.max_row,index).number_format='#,##0.00" COP"'
            sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
            for column in sheet.columns:sheet.column_dimensions[column[0].column_letter].width=26
        fill(ws,view)
        for table in view['additional']:fill(wb.create_sheet(table['title'][:31]),table)
        meta=wb.create_sheet('Metadatos')
        for key,value in view['metadata']:meta.append([key,cell(value)])
        out=io.BytesIO();wb.save(out);out.seek(0)
        return send_file(out,as_attachment=True,download_name=f'cpstore_{kind}.xlsx',mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    out=io.StringIO();writer=csv.writer(out,delimiter=';')
    for key,value in view['metadata']:writer.writerow(['# '+key,cell(value)])
    for table in [view]+view['additional']:
        if table is not view:writer.writerow([]);writer.writerow(['# '+table['title']])
        writer.writerow([c['label'] for c in table['columns']])
        for row in table['rows']:
            writer.writerow([format(c['value'],'.2f').replace('.',',') if c['kind']=='money' and not isinstance(c['value'],str) else cell(c['value']) for c in row])
    return send_file(io.BytesIO(out.getvalue().encode('utf-8-sig')),as_attachment=True,download_name=f'cpstore_{kind}.csv',mimetype='text/csv')


@reportes.route('/analitica/alertas',methods=['GET','POST'])
@require('admin')
def alerts_page():
    error=None
    if request.method=='POST':
        try:
            if request.form.get('action')=='config':alerts.settings(request.form.get('days'),request.form.get('reason',''))
            elif request.form.get('action')=='estado':alerts.transition(request.form.get('key'),request.form.get('state'),request.form.get('reason',''))
            else:raise ValueError('Acción inválida.')
            db.session.commit();return redirect(url_for('reportes.alerts_page',**request.args))
        except ValueError as e:db.session.rollback();error=str(e)
    try:data=svc.comparison(request.args)
    except ValueError as e:data=None;error=str(e)
    return render_template('reportes/analitica.html',data=data,error=error,alerts=alerts.alerts(),config=alerts.config(),args=request.args,active='analitica')


@reportes.post('/analitica/consultar')
@require('admin')
def consult():
    try:
        tool=request.form.get('consulta');args={k:request.form[k] for k in ('desde','hasta','abiertas','aliado') if k in request.form}
        data=alerts.consult(tool,args)
        audit('consulta_agente',0,'Consulta basada en reglas',{'herramienta':tool,'filtros':args})
        db.session.commit()
        return render_template('reportes/consulta.html',data=data,tool=tool,active='analitica')
    except ValueError as e:db.session.rollback();abort(400,str(e))


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


@reportes.get('/analitica')
@require('reportes')
def analytics():
    datos=reporte_service.resumen_tarjetas(role(),request.args.get('periodo','semana'))
    for t in datos['tarjetas']:
        modulo,tipo,ini,fin=t['enlace']
        t['url']=url_for('reportes.ver',modulo=modulo,**{k:v for k,v in (('periodo',tipo),('ini',ini),('fin',fin)) if v})
    return render_template('reportes/resumen_analitico.html',active='analitica',analitica=datos,analitica_tipos=reporte_service.RESUMEN_TIPOS)
