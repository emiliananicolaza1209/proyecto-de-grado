"""Identidad de personas y asociación explícita con sus bancos."""
from difflib import SequenceMatcher
import re
import unicodedata

from ..extensions import db
from ..models.contabilidad import PersonaContable, BancoDestino, PersonaBanco


def clave_nombre(value):
    plain=''.join(ch for ch in unicodedata.normalize('NFKD',str(value or '').casefold())
                  if not unicodedata.combining(ch))
    return ' '.join(re.findall(r'[a-z0-9]+',plain))


def clave_identificacion(value):
    return ''.join(ch for ch in str(value or '').upper() if ch.isalnum() and ch.isascii())


def coincidencias(nombre,identificacion):
    name=clave_nombre(nombre);document=clave_identificacion(identificacion)
    people=db.session.scalars(db.select(PersonaContable).order_by(PersonaContable.nombre)).all()
    exact=[p for p in people if document and clave_identificacion(p.identificacion)==document]
    similars=[p for p in people if name and p not in exact and
        (clave_nombre(p.nombre)==name or SequenceMatcher(None,clave_nombre(p.nombre),name).ratio()>=.87)]
    return exact,similars[:5]


def nueva_persona(form):
    name=' '.join((form.get('nombre') or '').upper().split())
    document=clave_identificacion(form.get('identificacion'))
    kind=form.get('tipo')
    if not 2<=len(name)<=120 or not 3<=len(document)<=20 or kind not in ('Natural','Juridica'):
        raise ValueError('Completa el nombre, la identificación y el tipo de persona.')
    exact,similars=coincidencias(name,document)
    if exact:
        person=exact[0]
        raise ValueError(f'La identificación {document} ya pertenece a {person.nombre}. No registres otra ficha: selecciona a esa persona y agrégale el banco.')
    if similars and form.get('confirm_same_name')!='1':
        names=', '.join(f'{p.nombre} ({p.identificacion})' for p in similars[:3])
        raise ValueError(f'Hay un nombre igual o parecido: {names}. Verifica la cédula; si es otra persona, marca la confirmación del formulario.')
    person=PersonaContable(nombre=name,identificacion=document,tipo=kind,
                           declaro_renta_antes=form.get('declaro_renta_antes')=='1')
    db.session.add(person)
    db.session.flush()
    return person


def banco_por_nombre(nombre):
    name=' '.join(str(nombre or '').upper().split())
    if not 2<=len(name)<=60:raise ValueError('Escribe el nombre del banco (2 a 60 caracteres).')
    key=clave_nombre(name)
    bank=next((b for b in db.session.scalars(db.select(BancoDestino))
               if clave_nombre(b.nombre)==key),None)
    if bank:return bank,False
    bank=BancoDestino(nombre=name)
    db.session.add(bank)
    db.session.flush()
    return bank,True


def asociar_banco(persona_id,banco_id='',nuevo_banco=''):
    try: person=db.session.get(PersonaContable,int(persona_id))
    except (ValueError,TypeError): person=None
    if not person:raise ValueError('Selecciona una persona registrada.')
    if str(banco_id or '').strip() and str(nuevo_banco or '').strip():
        raise ValueError('Selecciona un banco existente o escribe uno nuevo, no ambos.')
    if str(nuevo_banco or '').strip():
        bank,_=banco_por_nombre(nuevo_banco)
    else:
        try:bank=db.session.get(BancoDestino,int(banco_id))
        except (ValueError,TypeError):bank=None
        if not bank:raise ValueError('Selecciona un banco existente o escribe uno nuevo.')
    existing=db.session.scalar(db.select(PersonaBanco).where(
        PersonaBanco.persona_id==person.id,PersonaBanco.banco_id==bank.id))
    if existing:return person,bank,False
    db.session.add(PersonaBanco(persona_id=person.id,banco_id=bank.id))
    db.session.flush()
    return person,bank,True


def banco_de_persona(persona_id,banco_id):
    return db.session.scalar(db.select(PersonaBanco.id).where(
        PersonaBanco.persona_id==persona_id,PersonaBanco.banco_id==banco_id)) is not None
