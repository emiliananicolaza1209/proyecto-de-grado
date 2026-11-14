from flask import Blueprint, abort, render_template, redirect, url_for, request, jsonify

main = Blueprint('main', __name__)


@main.get('/')
def home():
    from ..auth import can
    from ..services.dashboard_service import summary
    try:
        data = summary(request.args, financial=can('admin'))
    except ValueError as exc:
        return render_template('error.html', title='Revisa las fechas', message=str(exc), active='inicio'), 400
    return render_template('home.html', d=data, active='inicio')


@main.get('/healthz')
def health():
    from ..extensions import db
    from ..models import Producto
    try:
        db.session.execute(db.select(Producto.id).limit(1)).first()
    except Exception:
        db.session.rollback()
        return jsonify(status='unavailable'), 503
    return jsonify(status='ok')


@main.get('/modulos/<name>')
def module(name):
    if name == 'usuarios':
        return redirect(url_for('gestion.usuarios'))
    if name == 'finanzas':
        return redirect(url_for('finanzas.index'))
    if name == 'ventas':
        return redirect(url_for('ventas.index'))
    if name == 'analitica':
        return redirect(url_for('reportes.analytics'))
    modules = {'ventas':'Ventas y pagos', 'finanzas':'Finanzas y liquidaciones',
               'analitica':'Analítica y agente', 'tributario':'Información contable y tributaria',
               'usuarios':'Usuarios y permisos'}
    if name not in modules:
        abort(404)
    return render_template('module.html', title=modules[name], active=name)
