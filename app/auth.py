"""Sesiones y permisos en servidor; sin contraseñas predeterminadas."""
import functools
import os
import time
from collections import defaultdict, deque
from flask import Blueprint,request,session,g,current_app,redirect,url_for,abort,render_template,flash
from werkzeug.security import generate_password_hash, check_password_hash
import click
from .extensions import db
from .models.gestion import Usuario
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
    r=role()
    if capability in ('chat','reportes'):  # entra quien tenga habilitada al menos una consulta del chat (ROLES_CONSULTAS: hoy solo el Propietario)
        from .services.consultas_service import ROLES_CONSULTAS
        return any(r in roles for roles in ROLES_CONSULTAS.values())
    if r=='Propietario':return True
    if r=='Administrador':return capability not in ('usuarios','sociedades_config')
    if r=='Inventario':return capability in ('inventario','catalogos','consulta','traslado','costos')
    if r=='Vendedora':return capability in ('consulta','venta','cobro','finanzas_venta','traslado')
    if r=='Socio':return capability=='sociedades_consulta'
    return False

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
    if request.endpoint in ('static','auth.login') or request.endpoint is None:return
    if not g.usuario:return redirect(url_for('auth.login',expirada=1 if expirada else None))
    if request.endpoint=='auth.logout':return
    endpoint=request.endpoint
    if role()=='Socio' and endpoint not in ('gestion.sociedades','gestion.inversion'):
        return redirect(url_for('gestion.sociedades'))
    if request.method=='GET':
        if endpoint in ('ventas.receipts','ventas.receipt_detail') and not can('admin'):abort(403)
        if endpoint.startswith('finanzas.') and not can('finanzas_venta'):abort(403)
        if endpoint.startswith('contabilidad.') and not can('contabilidad'):abort(403)
        if endpoint.startswith('chat.') and not can('chat'):abort(403)
        if endpoint.startswith('reportes.') and not can('reportes'):abort(403)
        if endpoint=='inventory.new' and not can('inventario'):abort(403)
        if endpoint.startswith('lotes.') and not can('inventario'):abort(403)
        return
    action=request.form.get('action','')
    if endpoint.startswith('gestion.') or endpoint.startswith('auth.'):return # decoradores locales
    capability='admin'
    if endpoint=='finanzas.index':
        capability='finanzas_venta' if action=='operation' and request.form.get('kind')=='Venta' else 'admin'
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
    elif endpoint.startswith('reportes.'):capability='reportes'
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
            if u and u.activo and check_password_hash(u.password_hash,request.form.get('password','')):
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
    app.context_processor(lambda:dict(can=can,usuario=getattr(g,'usuario',None)))
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
