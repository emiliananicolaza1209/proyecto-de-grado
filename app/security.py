import secrets
from flask import abort, request, session


CSP = "; ".join((
    "default-src 'self'",
    "script-src 'self'",                               # sin scripts ni manejadores en línea
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",  # Bootstrap por CDN y estilos en línea de barras/medidores
    "img-src 'self' data:",
    "font-src 'self' https://cdn.jsdelivr.net data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
))
CABECERAS = {
    'Content-Security-Policy': CSP,
    'X-Frame-Options': 'DENY',
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'same-origin',
}


def add_security_headers(response):
    for nombre, valor in CABECERAS.items():
        response.headers.setdefault(nombre, valor)
    return response


def protect_forms():
    session.setdefault('csrf', secrets.token_hex(24))
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and not secrets.compare_digest(session['csrf'], request.form.get('csrf', '')):
        abort(400, 'El formulario venció. Recarga la página.')
