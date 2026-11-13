import secrets
from flask import abort, request, session, current_app


def response_headers(response):
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='same-origin'
    if request.endpoint!='static':response.headers['Cache-Control']='no-store'
    response.headers['Content-Security-Policy']=(
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
        "media-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    response.headers['Permissions-Policy']='camera=(self), microphone=(), geolocation=()'
    if current_app.config.get('APP_ENV')=='production':
        response.headers['Strict-Transport-Security']='max-age=31536000'
    return response


def protect_forms():
    if request.endpoint in ('static','main.health'):return
    session.setdefault('csrf', secrets.token_hex(24))
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and not secrets.compare_digest(session['csrf'], request.form.get('csrf', '')):
        abort(400, 'El formulario venció. Recarga la página.')
