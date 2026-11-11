from flask import Blueprint, abort, render_template, redirect, request, url_for
from ..auth import can, role
from ..services import reporte_service
from ..services.inventario_service import stats
from ..services.inicio_service import operational_summary

main = Blueprint('main', __name__)


def _tarjetas_del_resumen():
    """Tarjetas analíticas del Resumen: solo para quien puede usar los reportes (hoy el Propietario). Los demás perfiles no reciben nada."""
    if not can('reportes'):
        return None
    datos = reporte_service.resumen_tarjetas(role(), request.args.get('periodo', 'semana'))
    for t in datos['tarjetas']:
        modulo, tipo, ini, fin = t['enlace']
        t['url'] = url_for('reportes.ver', modulo=modulo, **{k: v for k, v in (('periodo', tipo), ('ini', ini), ('fin', fin)) if v})
    return datos


@main.get('/')
def home():
    return render_template('home.html', stats=stats(), dashboard=operational_summary(), active='inicio',
                           analitica=_tarjetas_del_resumen(), analitica_tipos=reporte_service.RESUMEN_TIPOS)


@main.get('/modulos/<name>')
def module(name):
    if name == 'usuarios':
        return redirect(url_for('gestion.usuarios'))
    if name == 'finanzas':
        return redirect(url_for('finanzas.index'))
    if name == 'ventas':
        return redirect(url_for('ventas.index'))
    if name == 'tributario':
        return redirect(url_for('contabilidad.index'))
    modules = {'ventas':'Ventas y pagos', 'finanzas':'Finanzas y liquidaciones',
               'analitica':'Analítica y agente', 'tributario':'Información contable y tributaria',
               'usuarios':'Usuarios y permisos'}
    if name not in modules:
        abort(404)
    return render_template('module.html', title=modules[name], active=name)
