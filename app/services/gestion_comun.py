from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from flask import g, has_request_context
from ..extensions import db
from ..models.gestion import RegistroGestion

def actor():
    user=getattr(g,'usuario',None) if has_request_context() else None
    return user.nombre if user else 'Proceso local / pruebas'

def audit(entidad, ident, accion, datos=None, motivo='Registro autorizado'):
    db.session.add(RegistroGestion(entidad=entidad,entidad_id=ident,accion=accion,
        motivo=str(motivo or 'Registro autorizado')[:500],actor=actor(),datos=datos or {}))

def bp(value):
    try:
        n=Decimal(str(value or 0).replace(',','.'))
        if not n.is_finite() or n<0 or n>100 or n*100!=int(n*100):raise ValueError()
        return int(n*100)
    except (InvalidOperation,ValueError,OverflowError):raise ValueError('Porcentaje entre 0 y 100, máximo dos decimales.')

def distribute(amount, weights):
    """Reparto exacto en centavos; resto determinista, admite pérdidas."""
    if sum(weights)!=10000:raise ValueError('Las participaciones deben sumar 100 %.')
    sign=-1 if amount<0 else 1
    parts=[abs(amount)*x//10000 for x in weights]
    rest=abs(amount)-sum(parts)
    order=sorted(range(len(weights)),key=lambda i:-(abs(amount)*weights[i]%10000))
    for i in order[:rest]:parts[i]+=1
    return [sign*x for x in parts]

def get_id(model,value):
    try:obj=db.session.get(model,int(value))
    except (TypeError,ValueError):obj=None
    if obj is None:raise ValueError('Registro no encontrado; recarga la página.')
    return obj
