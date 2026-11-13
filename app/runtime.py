"""Configuración de despliegue y respuestas públicas sin información sensible."""
import os
from datetime import timedelta
from flask import render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.exceptions import SecurityError


def flag(value):
    return value is True or str(value).lower() in ('1', 'true', 'yes')


def configure_runtime(app):
    production = app.config.get('APP_ENV', os.getenv('APP_ENV', 'development')) == 'production' or os.getenv('RENDER') == 'true'
    app.config['APP_ENV'] = 'production' if production else 'development'
    persistent = flag(app.config.get('PERSISTENT_INSTANCE', os.getenv('PERSISTENT_INSTANCE', 'false')))
    uploads = flag(app.config.get('UPLOADS_ENABLED', os.getenv('UPLOADS_ENABLED', str(not production or persistent))))
    app.config.update(UPLOADS_ENABLED=uploads, PERSISTENT_INSTANCE=persistent,
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=8))
    if not production:
        return
    # Fallar antes de iniciar SQLAlchemy; nunca permitir SQLite o una clave
    # temporal por haber olvidado una variable del servicio web.
    secret = app.config.get('SECRET_KEY')
    configured_secret = secret if app.config.get('_SECRET_KEY_CONFIGURED') else None
    if not configured_secret or len(configured_secret) < 32:
        raise ValueError('Producción requiere una SECRET_KEY privada de al menos 32 caracteres.')
    raw = app.config.get('DATABASE_URL', os.getenv('DATABASE_URL', '')).strip()
    if not raw.startswith(('postgres://', 'postgresql://', 'postgresql+psycopg://')):
        raise ValueError('Producción requiere DATABASE_URL de PostgreSQL.')
    if uploads and not persistent:
        raise ValueError('Activa almacenamiento persistente antes de habilitar adjuntos en producción.')
    hosts = app.config.get('TRUSTED_HOSTS') or [x.strip() for x in os.getenv('APP_ALLOWED_HOSTS',
        os.getenv('RENDER_EXTERNAL_HOSTNAME', '')).split(',') if x.strip()]
    if not hosts:
        raise ValueError('Configura APP_ALLOWED_HOSTS o el dominio asignado por Render.')
    app.config.update(AUTH_REQUIRED=True, DEBUG=False, SESSION_COOKIE_SECURE=True,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      PREFERRED_URL_SCHEME='https', TRUSTED_HOSTS=hosts)
    if flag(app.config.get('TRUST_PROXY', os.getenv('TRUST_PROXY', 'false'))):
        # Solo habilitar detrás del proxy de Render. El Host se valida por
        # TRUSTED_HOSTS, no se toma de X-Forwarded-Host.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0, x_port=0, x_prefix=0)


def register_errors(app):
    messages = {
        400: ('Revisa la solicitud', 'El formulario venció o la solicitud no es válida. Recarga la página e inténtalo de nuevo.'),
        403: ('Acceso no permitido', 'Tu perfil no permite realizar esta operación.'),
        404: ('No encontramos este apartado', 'El registro o la página ya no está disponible en esta dirección.'),
        413: ('Archivo demasiado grande', 'El envío supera el tamaño permitido. Selecciona un archivo más pequeño.'),
        500: ('No pudimos completar la operación', 'Vuelve al apartado anterior. Si el problema continúa, informa al administrador.'),
    }
    def error_page(error):
        code = getattr(error, 'code', 500)
        if isinstance(error, SecurityError):
            return 'Dirección de servicio no permitida.', 400
        if request.path.startswith('/api/'):
            return {'error': messages[code][0]}, code
        title, message = messages[code]
        return render_template('error.html', title=title, message=message, active=''), code
    for code in messages:
        app.register_error_handler(code, error_page)
