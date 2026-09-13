from flask import Blueprint, abort, render_template, redirect, url_for
from ..services.inventario_service import stats

main = Blueprint('main', __name__)


@main.get('/')
def home():
    return render_template('home.html', stats=stats(), active='inicio')


@main.get('/modulos/<name>')
def module(name):
    if name == 'ventas':
        return redirect(url_for('ventas.index'))
    modules = {'ventas':'Ventas y pagos', 'finanzas':'Finanzas y liquidaciones',
               'analitica':'Analítica y agente', 'tributario':'Información contable y tributaria',
               'usuarios':'Usuarios y permisos'}
    if name not in modules:
        abort(404)
    return render_template('module.html', title=modules[name], active=name)
