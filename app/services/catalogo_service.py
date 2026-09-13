"""Catálogos y alertas de calidad de datos, sin dependencias de HTTP."""
import re
import unicodedata
from difflib import SequenceMatcher
from sqlalchemy.exc import IntegrityError
from ..extensions import db
from ..models import Catalogo

KINDS = {'brand': 'Marcas', 'reference': 'Modelos', 'color': 'Colores por modelo',
         'capacity': 'Capacidades por modelo', 'supplier': 'Proveedores', 'location': 'Ubicaciones'}
CONDITIONS = ('Nuevo', 'Usado', 'Exhibición', 'Open box', '0 ciclos')
CAPACITY_OPTIONS = (64, 128, 256, 512, 1024, 2048)
PARENT_KIND = {'reference': 'brand', 'color': 'reference', 'capacity': 'reference'}


class SimilarReferenceError(ValueError):
    def __init__(self, suggestions):
        super().__init__('Encontramos modelos parecidos. Revisa la alerta antes de crear otro.')
        self.suggestions = suggestions


def clean(value):
    value = ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]', '', value)


def normalize(value, kind=''):
    value = clean(value)
    return re.sub(r'^(apple)?iphone', '', value) if kind == 'reference' else value


def format_capacity(value):
    value = int(value)
    return f'{value // 1024} TB' if value >= 1024 else f'{value} GB'


def canonical_name(value, kind):
    value = ' '.join(value.split())
    return value.upper() if kind != 'capacity' else value


def get_item(item_id, kind=None):
    try:
        item = db.session.get(Catalogo, int(item_id))
    except (ValueError, TypeError):
        return None
    return item if item and (kind is None or item.kind == kind) else None


def list_items(kind=None, active_only=False):
    query = db.select(Catalogo).order_by(Catalogo.name)
    if kind:
        query = query.where(Catalogo.kind == kind)
    if active_only:
        query = query.where(Catalogo.active == 1)
    items = db.session.scalars(query).all()
    parents = {row.id: row.name for row in db.session.scalars(db.select(Catalogo))}
    return [{**item.to_dict(), 'parent_name': parents.get(item.parent_id),
             'display_name': item.display_name} for item in items]


def selected(data):
    result = {}
    brand = get_item(data.get('brand_id'), 'brand')
    if not brand or not brand.active:
        raise ValueError('Selecciona una marca activa.')
    for kind in ('reference', 'color', 'capacity', 'supplier', 'location'):
        item = get_item(data.get(kind + '_id'), kind)
        if not item or not item.active:
            raise ValueError('Selecciona una opción activa de cada catálogo.')
        result[kind] = item
    if result['reference'].parent_id != brand.id:
        raise ValueError('El modelo debe pertenecer a la marca seleccionada.')
    if any(result[k].parent_id != result['reference'].id for k in ('color', 'capacity')):
        raise ValueError('El color y la capacidad deben pertenecer al modelo seleccionado.')
    result['brand'] = brand
    return result


def reference_suggestions(name, brand_id, exclude_id=None):
    incoming = clean(name)
    if not incoming:
        return []
    candidates = db.session.scalars(db.select(Catalogo).where(Catalogo.kind == 'reference', Catalogo.parent_id == brand_id)).all()
    suggestions = []
    for item in candidates:
        if item.id == exclude_id:
            continue
        score = SequenceMatcher(None, incoming, clean(item.name)).ratio()
        if score >= .74:
            suggestions.append({'id': item.id, 'name': item.display_name, 'score': round(score * 100)})
    return sorted(suggestions, key=lambda result: -result['score'])[:3]



def catalog_alerts():
    """Encuentra referencias existentes que posiblemente sean el mismo modelo."""
    references = db.session.scalars(db.select(Catalogo).where(Catalogo.kind == 'reference').order_by(Catalogo.parent_id, Catalogo.name)).all()
    alerts = []
    for index, first in enumerate(references):
        for second in references[index + 1:]:
            score = SequenceMatcher(None, clean(first.name), clean(second.name)).ratio()
            # Dentro de una misma marca basta una coincidencia alta. Entre marcas
            # solo se avisa cuando es casi idéntica: cubre errores como IPHXONE.
            threshold = .78 if first.parent_id == second.parent_id else .88
            if score >= threshold and first.normal_key != second.normal_key:
                alerts.append({'first': {'id': first.id, 'name': first.display_name},
                               'second': {'id': second.id, 'name': second.display_name},
                               'score': round(score * 100)})
    return sorted(alerts, key=lambda item: -item['score'])[:20]

def save_item(kind, data):
    if kind not in KINDS:
        raise ValueError('Catálogo desconocido.')
    name = canonical_name(data.get('name', ''), kind)
    if not name or len(name) > 120 or not normalize(name, kind):
        raise ValueError('Escribe un nombre válido de máximo 120 caracteres.')
    item = get_item(data.get('id'), kind) if data.get('id') else None
    if data.get('id') and item is None:
        raise ValueError('La opción que intentas editar no existe.')
    parent = 0
    if kind in PARENT_KIND:
        if item and not data.get('parent_id'):
            parent = item.parent_id
        else:
            parent_item = get_item(data.get('parent_id'), PARENT_KIND[kind])
            if not parent_item:
                raise ValueError(f'Selecciona {"la marca" if kind == "reference" else "el modelo"} correspondiente.')
            parent = parent_item.id
    if item and parent != item.parent_id:
        raise ValueError('No se puede cambiar la relación de una opción existente. Crea otra opción.')
    if kind == 'capacity':
        if not name.isascii() or not name.isdigit() or int(name) not in CAPACITY_OPTIONS:
            raise ValueError('Selecciona una capacidad predeterminada válida.')
        name = str(int(name))
    if kind == 'reference' and item is None and data.get('confirm_similar') != '1':
        suggestions = reference_suggestions(name, parent)
        if suggestions:
            raise SimilarReferenceError(suggestions)
    if item and kind == 'capacity' and name != item.name:
        raise ValueError('Para otra capacidad crea una opción nueva; puedes desactivar la anterior.')
    if item is None:
        item = Catalogo(kind=kind, parent_id=parent)
    item.name = name
    item.normal_key = normalize(name, kind)
    item.active = int(data.get('active') == '1')
    try:
        db.session.add(item)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ValueError('Ya existe esta opción. Revisa la lista y usa o edita la referencia existente.')
    return item
