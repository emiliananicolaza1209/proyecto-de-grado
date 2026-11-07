"""Catálogos y alertas de calidad de datos, sin dependencias de HTTP."""
import re
import unicodedata
from difflib import SequenceMatcher
from sqlalchemy import true
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
        super().__init__('Encontramos nombres parecidos. Revisa las opciones antes de guardar.')
        self.suggestions = suggestions
        self.exact = False


class DuplicateCatalogError(SimilarReferenceError):
    def __init__(self, item):
        super().__init__([{'id': item.id, 'name': item.display_name, 'active': bool(item.active), 'score': 100}])
        self.exact = True
        self.args = ('Ya existe esta opción. Usa el registro existente para evitar duplicados.',)


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


def name_similarity(first, second, model=False):
    """Parecido de texto; una generación o variante diferente no es un duplicado."""
    def words(value):
        value = ''.join(c for c in unicodedata.normalize('NFKD', value.casefold())
                        if not unicodedata.combining(c))
        return re.sub(r'[^a-z0-9]+', ' ', value).strip()

    left, right = words(first), words(second)
    if not left or not right:
        return 0
    # Incluye sufijos: 16/16E, S24/S25 y SE 2.ª/3.ª son referencias distintas.
    if re.findall(r'\d+[a-z]*', left) != re.findall(r'\d+[a-z]*', right):
        return 0
    if model:
        def variants(value):
            value = re.sub(r'(\d)([a-z])', r'\1 \2', value)
            value = re.sub(r'\bpromax\b', 'pro max', value)
            return set(re.findall(r'\b(?:pro|max|mini|plus|ultra|lite|fe|edge|fold|flip|x|xr|xs|se|air)\b', value))
        if variants(left) != variants(right):
            return 0
    return SequenceMatcher(None, clean(first), clean(second)).ratio()


def catalog_suggestions(name, kind, parent_id=0, exclude_id=None):
    if not clean(name) or kind == 'capacity':
        return []
    candidates = db.session.scalars(db.select(Catalogo).where(
        Catalogo.kind == kind, Catalogo.parent_id == parent_id)).all()
    suggestions = []
    for item in candidates:
        if item.id == exclude_id:
            continue
        score = name_similarity(name, item.name, model=kind == 'reference')
        if normalize(name, kind) == item.normal_key:
            score = 1
        if score >= .86:
            suggestions.append({'id': item.id, 'name': item.display_name,
                                'active': bool(item.active), 'score': round(score * 100)})
    return sorted(suggestions, key=lambda result: (-result['score'], result['name']))[:5]


def reference_suggestions(name, brand_id, exclude_id=None):
    return catalog_suggestions(name, 'reference', brand_id, exclude_id)



def catalog_alerts():
    """Encuentra referencias existentes que posiblemente sean el mismo modelo."""
    references = db.session.scalars(db.select(Catalogo).where(Catalogo.kind == 'reference').order_by(Catalogo.parent_id, Catalogo.name)).all()
    alerts = []
    for index, first in enumerate(references):
        for second in references[index + 1:]:
            score = name_similarity(first.name, second.name, model=True)
            # Dentro de una misma marca basta una coincidencia alta. Entre marcas
            # solo se avisa cuando es casi idéntica: cubre errores como IPHXONE.
            threshold = .86 if first.parent_id == second.parent_id else .90
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
    duplicate = db.session.scalar(db.select(Catalogo).where(
        Catalogo.kind == kind, Catalogo.parent_id == parent,
        Catalogo.normal_key == normalize(name, kind),
        Catalogo.id != item.id if item else true()))
    if duplicate:
        raise DuplicateCatalogError(duplicate)
    changed_name = item is None or normalize(name, kind) != item.normal_key
    if changed_name and data.get('confirm_similar') != '1':
        suggestions = catalog_suggestions(name, kind, parent, item.id if item else None)
        if suggestions:
            raise SimilarReferenceError(suggestions)
    if item and kind == 'capacity' and name != item.name:
        raise ValueError('Para otra capacidad crea una opción nueva; puedes desactivar la anterior.')
    if item is None:
        item = Catalogo(kind=kind, parent_id=parent)
    item.name = name
    item.normal_key = normalize(name, kind)
    item.active = int(data.get('active') == '1')
    if kind == 'supplier':
        category=data.get('supplier_category') or item.supplier_category or 'Accesorios'
        if category not in ('Celulares','Accesorios','Ambos'):
            raise ValueError('Selecciona el tipo de proveedor: celulares, accesorios o ambos.')
        item.supplier_category=category
    try:
        db.session.add(item)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ValueError('Ya existe esta opción. Revisa la lista y usa o edita la referencia existente.')
    return item
