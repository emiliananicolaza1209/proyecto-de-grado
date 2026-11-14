from ..extensions import db
from ..models import Producto
from ..models.finanzas import OperacionFinanciera as Op
from ..models.gestion import CompraPool
from .gestion_comun import get_id

def retoma_payment(f,index,amount):
    ids=f.getlist('payment_retoma_id');p=get_id(Producto,ids[index] if index<len(ids) else '')
    if p.source_type!='Retoma' or p.archived or p.status!='Disponible' or db.session.get(CompraPool,p.id):
        raise ValueError('Selecciona una retoma recién ingresada, sin compra ya pagada.')
    if amount!=p.purchase_cop_cents:raise ValueError('El valor de la parte de pago debe coincidir con la compra registrada de la retoma.')
    for op in db.session.scalars(db.select(Op).where(Op.voided==False)):
        if any(x.get('equipment_id')==p.id and x['account']=='RETOMA' for x in op.payments):
            raise ValueError('Este equipo ya fue utilizado como parte de pago de otra venta.')
    return dict(account='RETOMA',amount=amount,equipment_id=p.id,imei=p.imei)
