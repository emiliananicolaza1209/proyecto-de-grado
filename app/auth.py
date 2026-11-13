"""Sesiones y permisos en servidor; sin contraseñas predeterminadas."""
import functools
import os
import secrets
import time
from collections import defaultdict, deque
from flask import Blueprint,request,session,g,current_app,redirect,url_for,abort,render_template,flash
from werkzeug.security import generate_password_hash, check_password_hash
import click
from .extensions import db
from .models.gestion import Usuario, PermisosUsuario
from .services.permisos_service import profile_can, user_keys, route_keys, READ_KEYS, KIND_KEYS
from .services.gestion_comun import audit
from .passwords import validar_clave

auth=Blueprint('auth',__name__)
ROLES=('Propietario','Administrador','Vendedora','Inventario','Socio')
_attempts=defaultdict(deque)      # (ip, usuario) -> instantes de intentos fallidos
_attempts_ip=defaultdict(deque)   # ip -> instantes de intentos fallidos con cualquier usuario
VENTANA=300          # segundos
LIMITE_USUARIO=5     # fallos por usuario y red en la ventana
LIMITE_IP=20         # fallos por red (cualquier usuario) en la ventana; frena probar claves contra muchos usuarios
# LIMITACIÓN CONOCIDA: los contadores viven en memoria del proceso. Se pierden al reiniciar el servidor y no se
# comparten entre procesos; con varios procesos el límite real es el de cada uno. Los fallos sí quedan en la
# auditoría (registro_gestion), que es persistente. Ver docs/SEGURIDAD.md.

_ficticio=[]
def _hash_ficticio():
    """Hash de una clave que nadie conoce, con el mismo método y costo que los reales; se calcula una sola vez por proceso."""
    if not _ficticio:_ficticio.append(generate_password_hash(secrets.token_hex(16)))
    return _ficticio[0]

def _vigentes(cola,ahora):
    while cola and cola[0]<ahora-VENTANA:cola.popleft()
    return cola

def _podar(ahora):
    """Evita que claves inventadas por un atacante hagan crecer la memoria sin límite."""
    for tabla in (_attempts,_attempts_ip):
        if len(tabla)>1000:
            for clave in [k for k,c in tabla.items() if not _vigentes(c,ahora)]:tabla.pop(clave,None)

def _registrar_acceso(accion,usuario,login,ip,motivo,**datos):
    from .models.gestion import RegistroGestion
    db.session.add(RegistroGestion(entidad='acceso',entidad_id=usuario.id if usuario else 0,accion=accion,motivo=motivo,
        actor='Acceso (sin sesión)',datos=dict(datos,login=login[:120],ip=ip[:64])))
    db.session.commit()

def enabled():return current_app.config.get('AUTH_REQUIRED',not current_app.testing)
def idle_seconds():return max(1,int(current_app.config.get('SESSION_IDLE_MINUTES',30)*60))
def role():return getattr(g,'usuario',None).rol if getattr(g,'usuario',None) else ('Propietario' if not enabled() else '')
def can(capability):
    if capability=='costos' and getattr(g,'usuario',None) and hasattr(g,'permisos_efectivos'):
        return 'inventario.costos' in g.permisos_efectivos
    return profile_can(role(),capability)

def allowed(key):
    if role()=='Propietario':return True
    if hasattr(g,'permisos_efectivos'):return key in g.permisos_efectivos
    from .services.permisos_service import profile_keys
    return key in profile_keys(role())

def module_allowed(module):return allowed(READ_KEYS.get(module,''))

def require(capability):
    def wrap(fn):
        @functools.wraps(fn)
        def decorated(*args,**kwargs):
            if not can(capability):abort(403,'Tu perfil no permite esta operación.')
            return fn(*args,**kwargs)
        return decorated
    return wrap

def guard():
    g.usuario=None
    g.acceso_personalizado=False
    g.pop('permisos_efectivos',None)
    if not enabled():return
    uid=session.get('usuario_id')
    expirada=False
    if uid:
        u=db.session.get(Usuario,uid)
        if u and u.activo and session.get('usuario_version')==u.session_version:
            ahora=int(time.time());ultimo=session.get('ultimo_acceso')
            if ultimo is not None and ahora-ultimo>idle_seconds():session.clear();expirada=True
            else:
                g.usuario=u
                if request.endpoint!='static':session['ultimo_acceso']=ahora
        else:session.clear()
    if request.endpoint in ('static','auth.login','main.health') or request.endpoint is None:return
    if not g.usuario:return redirect(url_for('auth.login',expirada=1 if expirada else None))
    if request.endpoint=='auth.logout':return
    from sqlalchemy import inspect
    # No DDL web ni permisos inferidos si falta la nueva tabla. La actualización
    # es explícita y transaccional mediante actualizar-postgres.
    if not inspect(db.session.connection()).has_table('permisos_usuario'):
        return render_template('error.html',title='Actualización de accesos pendiente',
            message='El administrador debe actualizar el esquema antes de continuar.'),503
    g.permisos_efectivos=user_keys(g.usuario)
    g.acceso_personalizado=role()!='Propietario' and db.session.get(PermisosUsuario,g.usuario.id) is not None
    endpoint=request.endpoint
    if role()=='Socio' and endpoint not in ('gestion.sociedades','gestion.inversion'):
        return redirect(url_for('gestion.sociedades'))
    # La autorización debe leer la misma fuente que procesa cada escritura.
    # request.values prioriza la URL y permitiría ocultar el action/kind del POST.
    params=dict(request.args if request.method in ('GET','HEAD','OPTIONS') else request.form)
    route_args=dict(request.view_args or {})
    if role()=='Socio':route_args['_socio']=True
    keys=route_keys(endpoint,request.method,params,route_args)
    if g.acceso_personalizado and any(not allowed(key) for key in keys):
        if endpoint=='main.home':
            for module,target in [('inventario','inventory.index'),('ventas','ventas.index'),('finanzas','finanzas.index'),
                    ('creditos','gestion.creditos'),('contabilidad','contabilidad.index'),('reportes','reportes.index'),('sociedades','gestion.sociedades')]:
                if module_allowed(module):return redirect(url_for(target))
        abort(403,'No tienes habilitada esta función. Solicita al propietario que revise tus permisos.')
    if request.method=='GET':
        if endpoint in ('ventas.receipts','ventas.receipt_detail') and not can('admin'):abort(403)
        if endpoint.startswith('finanzas.') and not can('finanzas_venta'):abort(403)
        if endpoint.startswith('contabilidad.') and not can('contabilidad'):abort(403)
        if endpoint.startswith('chat.') and not can('chat'):abort(403)
        if endpoint in ('reportes.ver','reportes.analytics') and not can('reportes'):abort(403)
        if endpoint=='inventory.new' and not can('inventario'):abort(403)
        if endpoint.startswith('lotes.') and not can('inventario'):abort(403)
        return
    action=request.form.get('action','')
    if endpoint.startswith('gestion.') or endpoint.startswith('auth.'):return # decoradores locales
    capability='admin'
    if endpoint=='finanzas.index':
        capability='finanzas_venta' if action=='operation' and request.form.get('kind')=='Venta' else 'admin'
        if action=='pool_purchase' and not request.form.get('product_id'):capability='finanzas_pool'
    elif endpoint.startswith('ventas.'):
        capability='venta' if action in ('handoff','return','reserve','sell','payment','cancel') else 'admin'
        if request.form.get('movement_date'):
            from .services.operacion_service import today
            if request.form['movement_date']!=today():capability='admin'
    elif endpoint=='inventory.detail':capability='traslado' if action=='transfer' else 'inventario'
    elif endpoint.startswith('inventory.') or endpoint.startswith('lotes.'):capability='inventario'
    elif endpoint.startswith('catalogos.'):capability='catalogos'
    elif endpoint.startswith('contabilidad.'):capability='contabilidad'
    elif endpoint.startswith('chat.'):capability='chat'
    elif endpoint=='reportes.ver':capability='reportes'
    elif endpoint.startswith('reportes.'):capability='admin'
    if not can(capability):abort(403,'Tu perfil no permite esta operación.')

@auth.route('/iniciar-sesion',methods=['GET','POST'])
def login():
    setup=db.session.scalar(db.select(Usuario.id).limit(1)) is None
    error='Tu sesión se cerró por inactividad. Inicia sesión de nuevo.' if request.method=='GET' and request.args.get('expirada') else None
    if request.method=='POST' and not setup:
        ip=request.remote_addr or '';key=(ip,request.form.get('login','').strip().lower())
        now=time.monotonic();_podar(now)
        q=_vigentes(_attempts[key],now);qi=_vigentes(_attempts_ip[ip],now)
        if len(q)>=LIMITE_USUARIO or len(qi)>=LIMITE_IP:error='Espera cinco minutos antes de volver a intentar.'
        else:
            u=db.session.scalar(db.select(Usuario).where(Usuario.login==key[1]))
            # Siempre se calcula UN hash, exista o no el usuario y esté activo o no: así el tiempo de respuesta no delata qué usuarios existen.
            clave_correcta=check_password_hash(u.password_hash if u else _hash_ficticio(),request.form.get('password','')) and bool(u)
            if u and u.activo and clave_correcta:
                session.clear();session['usuario_id']=u.id;session['usuario_version']=u.session_version;session['ultimo_acceso']=int(time.time())
                _attempts.pop(key,None)
                return redirect(url_for('main.home'))
            q.append(now);qi.append(now)
            motivo='Usuario inexistente' if not u else 'Usuario inactivo' if not u.activo else 'Contraseña incorrecta'
            _registrar_acceso('Inicio de sesión fallido',u,key[1],ip,motivo,intentos_usuario=len(q),intentos_red=len(qi))
            if len(q)>=LIMITE_USUARIO or len(qi)>=LIMITE_IP:
                _registrar_acceso('Bloqueo temporal de acceso',u,key[1],ip,'Límite de intentos alcanzado',
                    por='usuario' if len(q)>=LIMITE_USUARIO else 'red',minutos=VENTANA//60)
            error='Usuario o contraseña incorrectos.'
    return render_template('gestion/login.html',error=error,setup=setup)

@auth.post('/cerrar-sesion')
def logout():
    session.clear();return redirect(url_for('auth.login'))

def _verdadero(valor):return str(valor or '').strip().lower() in ('1','true','si','sí','yes','on')

def init_auth(app):
    # Sesión: la cookie es HttpOnly y SameSite=Lax (app/__init__.py). Secure se activa con SESSION_COOKIE_SECURE=1
    # al desplegar tras HTTPS; la inactividad máxima se fija con SESSION_IDLE_MINUTES (30 por defecto).
    # LIMITACIÓN CONOCIDA: la sesión es una cookie firmada sin estado en el servidor. Cerrar sesión la borra del
    # navegador, pero una copia de la cookie sigue valiendo hasta que expire por inactividad o hasta que se edite
    # o desactive al usuario (eso sí la invalida de inmediato). Ver docs/SEGURIDAD.md.
    if _verdadero(os.getenv('SESSION_COOKIE_SECURE')):app.config['SESSION_COOKIE_SECURE']=True
    try:minutos=float(os.getenv('SESSION_IDLE_MINUTES') or 30)
    except ValueError:minutos=30
    app.config.setdefault('SESSION_IDLE_MINUTES',minutos if minutos>0 else 30)
    app.before_request(guard)
    from .access_ui import restrict_forms
    app.after_request(restrict_forms)
    app.context_processor(lambda:dict(can=can,allowed=allowed,module_allowed=module_allowed,
        finance_kind_allowed=lambda kind:allowed(KIND_KEYS.get(kind,'')),
        access_keys=sorted(getattr(g,'permisos_efectivos',[])),access_custom=getattr(g,'acceso_personalizado',False),usuario=getattr(g,'usuario',None)))
    app.register_blueprint(auth)
    @app.cli.command('crear-propietario')
    @click.option('--usuario',prompt='Usuario')
    @click.option('--nombre',prompt='Nombre')
    @click.password_option(confirmation_prompt=True)
    def owner(usuario,nombre,password):
        try:validar_clave(password,usuario,nombre)
        except ValueError as e:raise click.ClickException(str(e))
        if db.session.scalar(db.select(Usuario.id).where(Usuario.login==usuario.lower().strip())):
            raise click.ClickException('Ese usuario ya existe. Usa Usuarios para editarlo.')
        u=Usuario(login=usuario.lower().strip(),nombre=nombre.strip(),password_hash=generate_password_hash(password),rol='Propietario')
        db.session.add(u);db.session.flush();audit('usuario',u.id,'Alta local de propietario');db.session.commit()
        click.echo('Propietario creado. Ya puedes iniciar sesión.')
