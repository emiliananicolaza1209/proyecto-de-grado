import secrets
from flask import abort, request, session


def protect_forms():
    session.setdefault('csrf', secrets.token_hex(24))
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and not secrets.compare_digest(session['csrf'], request.form.get('csrf', '')):
        abort(400, 'El formulario venció. Recarga la página.')
