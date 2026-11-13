"""Destinos de regreso locales. Nunca aceptar una redirección externa del cliente."""
from urllib.parse import unquote, urlsplit
from flask import request, url_for


def safe_path(value):
    if not isinstance(value, str) or len(value) > 4096:
        return None
    decoded = unquote(value)
    if not value.startswith('/') or decoded.startswith('//') or '\\' in decoded:
        return None
    if any(ord(c) < 32 or ord(c) == 127 for c in decoded):
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        return None
    if parsed.path.startswith(('/api/', '/static/', '/cerrar-sesion', '/healthz')):
        return None
    return value


def context():
    endpoint = request.endpoint or ''
    if endpoint.startswith(('inventory.', 'lotes.')) or endpoint in (
            'gestion.lotes', 'gestion.lote', 'gestion.articulos', 'gestion.proveedores', 'gestion.alias'):
        fallback = url_for('inventory.index')
        if endpoint == 'gestion.lote':
            fallback = url_for('gestion.lotes')
        elif endpoint == 'lotes.detail':
            fallback = url_for('lotes.index')
    elif endpoint.startswith('ventas.') or endpoint in ('gestion.sociedades', 'gestion.inversion'):
        fallback = url_for('ventas.index')
    elif endpoint.startswith('finanzas.') or endpoint in ('gestion.creditos', 'gestion.historial'):
        fallback = url_for('finanzas.index')
    elif endpoint.startswith('contabilidad.'):
        fallback = url_for('contabilidad.index')
    elif endpoint.startswith('reportes.'):
        fallback = url_for('reportes.index')
    else:
        fallback = url_for('main.home')
    explicit = safe_path(request.args.get('volver', ''))
    try:
        source = urlsplit(request.referrer or '')
    except ValueError:
        source = urlsplit('')
    referrer = None
    if source.netloc == request.host and source.scheme in ('http', 'https'):
        referrer = safe_path(source.path + ('?'+source.query if source.query else ''))
    current = request.full_path.rstrip('?')
    target = next((p for p in (explicit, referrer, fallback, '/') if p and p != current), '/')
    return dict(back_url=target, current_page=current,
                show_back=endpoint != 'main.home')
