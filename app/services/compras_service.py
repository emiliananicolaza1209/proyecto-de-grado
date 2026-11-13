"""Borradores sin existencias, confirmación atómica e importación con vista previa."""
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
import hashlib,secrets,zipfile
from pathlib import Path
from flask import current_app
from werkzeug.utils import secure_filename
from ..extensions import db
from ..models import Producto,Lote,Movimiento,Catalogo
from ..models.gestion import ControlLote,LineaLote,FacturaLote,ArticuloStock,MovimientoStock
from .gestion_comun import get_id,audit,actor
from .catalogo_service import selected,CONDITIONS,normalize
from .costo_service import purchase_cost
from .finanzas_service import money,valid_date,text
from .inventario_service import valid_imei,warranty_date
from .stock_service import movement,balance
import json

HEADERS=['tipo','imei','reference_id','color_id','capacity_id','location_id','condition','purchase_price','shipping_cop','battery','articulo_id','cantidad','serial']

def control(lot_id,revision=None):
    c=get_id(ControlLote,lot_id)
    if revision is not None and str(c.revision)!=str(revision):raise ValueError('El lote cambió. Recarga antes de continuar.')
    return c

def create(f):
    supplier=get_id(Catalogo,f.get('supplier_id'))
    if supplier.kind!='supplier' or not supplier.active:raise ValueError('Selecciona un proveedor activo.')
    currency=f.get('currency','USD')
    if currency not in ('COP','USD'):raise ValueError('Moneda inválida.')
    rate=Decimal(str(f.get('exchange_rate') or '1')) if currency=='USD' else Decimal(1)
    if not rate.is_finite() or not 0<rate<=1000000 or rate.as_tuple().exponent < -2:raise ValueError('Tasa de cambio inválida.')
    count=int(f.get('expected_count') or 0)
    if not 1<=count<=10000:raise ValueError('La cantidad esperada debe estar entre 1 y 10.000.')
    lot=Lote(entry_date=valid_date(f.get('entry_date')),supplier_id=supplier.id,exchange_rate=str(rate),expected_count=count,note=text(f.get('note'),False,500))
    db.session.add(lot);db.session.flush()
    society=int(f.get('society_id')) if f.get('society_id') else None
    if society:
        from .sociedad_service import snapshot
        snapshot(society)
    db.session.add(ControlLote(lote_id=lot.id,moneda=currency,sociedad_id=society,heredado=False));db.session.flush()
    audit('lote',lot.id,'Crear borrador',{'moneda':currency,'cantidad':count})
    return lot

def validate(lot,c,data,exclude_product=None):
    data=dict(data);typ=data.get('tipo','Equipo')
    if typ not in ('Equipo','Artículo'):raise ValueError('Tipo: Equipo o Artículo.')
    qty=int(data.get('cantidad') or 1)
    price=money(data.get('purchase_price') or '0');shipping=money(data.get('shipping_cop') or '0')
    if price<=0 or qty<=0 or qty>10000:raise ValueError('Precio y cantidad deben ser positivos.')
    cost=int((Decimal(price)*Decimal(lot.exchange_rate)).quantize(Decimal('1'),rounding=ROUND_HALF_UP)) + shipping if c.moneda=='USD' else price+shipping
    if typ=='Artículo':
        a=get_id(ArticuloStock,data.get('articulo_id'))
        if not a.activo:raise ValueError('El artículo está inactivo.')
        serial=str(data.get('serial') or '').strip()
        if a.serializado and (qty!=1 or not serial or len(serial)>100):raise ValueError('Cada repuesto con serial requiere una línea de una unidad.')
        return dict(tipo=typ,articulo_id=a.id,cantidad=qty,serial=serial,purchase_price=str(Decimal(price)/100),shipping_cop=str(Decimal(shipping)/100),cost=cost)
    if qty!=1:raise ValueError('Cada IMEI corresponde a un solo equipo.')
    imei=str(data.get('imei') or '').strip()
    if not valid_imei(imei):raise ValueError('IMEI inválido: se necesitan 15 dígitos con control válido.')
    existing=db.session.scalar(db.select(Producto).where(Producto.imei==imei))
    if existing and existing.id!=exclude_product:raise ValueError('El IMEI ya existe en inventario: '+imei)
    data['supplier_id']=lot.supplier_id
    ref=get_id(Catalogo,data.get('reference_id'))
    data['brand_id']=ref.parent_id
    items=selected(data)
    condition=data.get('condition')
    if condition not in CONDITIONS:raise ValueError('Condición inválida.')
    battery=data.get('battery')
    battery=int(battery) if str(battery or '').strip() else None
    if battery is not None and not 0<=battery<=100:raise ValueError('La batería debe estar entre 0 y 100.')
    return dict(tipo=typ,imei=imei,condition=condition,battery=battery,cantidad=1,
        purchase_price=str(Decimal(price)/100),shipping_cop=str(Decimal(shipping)/100),cost=cost,
        model=items['reference'].display_name,color=items['color'].name,capacity=int(items['capacity'].name),
        location=items['location'].name,supplier=items['supplier'].name,
        **{k+'_id':v.id for k,v in items.items() if k in ('reference','color','capacity','supplier','location')})

def add_lines(lot,c,rows):
    if c.estado!='Borrador':raise ValueError('Solo se editan los lotes en borrador.')
    existing=db.session.scalars(db.select(LineaLote).where(LineaLote.lote_id==lot.id)).all()
    imeis={r.datos.get('imei') for r in existing if r.tipo=='Equipo'}
    serials={(r.datos.get('articulo_id'),r.datos.get('serial')) for r in existing if r.datos.get('serial')}
    checked=[];errors=[]
    for i,row in enumerate(rows,2):
        try:
            v=validate(lot,c,row)
            if v.get('imei'):
                if v['imei'] in imeis:raise ValueError('IMEI repetido en el borrador.')
                imeis.add(v['imei'])
            if v.get('serial'):
                key=(v['articulo_id'],v['serial'])
                if key in serials:raise ValueError('Serial repetido en el borrador.')
                serials.add(key)
            checked.append(v)
        except (ValueError,TypeError) as e:errors.append(f'Fila {i}: {e}')
    if errors:raise ValueError(' • '.join(errors[:15]))
    for v in checked:db.session.add(LineaLote(lote_id=lot.id,tipo=v['tipo'],datos=v,articulo_id=v.get('articulo_id')))
    c.revision+=1;audit('lote',lot.id,'Agregar líneas al borrador',{'filas':len(checked)})
    return checked

def read_excel(file):
    if not file.filename.lower().endswith('.xlsx'):raise ValueError('Usa la plantilla .xlsx.')
    raw=file.read()
    if len(raw)>8*1024*1024:raise ValueError('Máximo 8 MB.')
    try:
        with zipfile.ZipFile(BytesIO(raw)) as z:
            if sum(x.file_size for x in z.infolist())>40*1024*1024:raise ValueError('El Excel es demasiado grande.')
        from openpyxl import load_workbook
        w=load_workbook(BytesIO(raw),read_only=True,data_only=False)
        sh=w.worksheets[0];it=sh.iter_rows(values_only=True);headers=list(next(it))
        if headers!=HEADERS:raise ValueError('Los encabezados deben coincidir con la plantilla descargada.')
        rows=[]
        for vals in it:
            if not any(v is not None for v in vals):continue
            if any(isinstance(v,str) and v.startswith('=') for v in vals):raise ValueError('La importación recibe valores, no fórmulas.')
            if len(rows)>=5000:raise ValueError('Máximo 5.000 líneas por archivo.')
            rows.append({k:str(v) if v is not None else '' for k,v in zip(headers,vals)})
        w.close()
    except (zipfile.BadZipFile,KeyError,StopIteration):raise ValueError('Archivo Excel no válido.')
    if not rows:raise ValueError('La plantilla está vacía.')
    return rows

def confirm(lot,c):
    if c.estado!='Borrador':raise ValueError('Este lote ya fue confirmado.')
    rows=db.session.scalars(db.select(LineaLote).where(LineaLote.lote_id==lot.id)).all()
    if sum(int(r.datos.get('cantidad',1)) for r in rows)!=lot.expected_count:raise ValueError('La cantidad del borrador debe coincidir con la esperada antes de confirmar.')
    from .sociedad_service import assign_ownership
    for r in rows:
        v=validate(lot,c,r.datos,r.producto_id)
        if r.tipo=='Equipo':
            p=db.session.get(Producto,r.producto_id) if r.producto_id else Producto()
            if p is not None and r.producto_id and p.status!='Anulado lote':raise ValueError('El equipo ya tiene un estado activo.')
            for k in ('imei','condition','battery','model','color','capacity','location','supplier','reference_id','color_id','capacity_id','location_id','supplier_id'):setattr(p,k,v[k])
            p.lot_id=lot.id;p.source_type='Lote';p.cost_cents=v['cost'];p.status='Disponible';p.archived=0
            p.purchase_usd=v['purchase_price'] if c.moneda=='USD' else None
            p.purchase_cop_cents=money(v['purchase_price']) if c.moneda=='COP' else None
            p.exchange_rate=lot.exchange_rate;p.shipping_cents=money(v['shipping_cop']);p.subtotal_cents=v['cost']-p.shipping_cents
            db.session.add(p);db.session.flush();r.producto_id=p.id
            assign_ownership(p,c.sociedad_id)
            db.session.add(Movimiento(product_id=p.id,action='Confirmar lote',reason=lot.code,actor=actor(),before_data='{}',after_data=json.dumps(p.to_dict(),ensure_ascii=False)))
        else:movement(get_id(ArticuloStock,v['articulo_id']),v['cantidad'],v['cost'],'Ingreso de lote confirmado',lot=lot.id,serial=v.get('serial'))
    c.estado='Confirmado';c.revision+=1;audit('lote',lot.id,'Confirmar lote',{'cantidad':lot.expected_count})

def reopen(lot,c,reason):
    from ..models import Cobro
    from ..models.finanzas import OperacionFinanciera as Op
    if c.heredado:raise ValueError('Lote histórico: conserva su ingreso y corrige cada equipo desde su ficha.')
    if c.estado!='Confirmado' or len(reason.strip())<5:raise ValueError('Indica el motivo de la reversión del lote confirmado.')
    rows=db.session.scalars(db.select(LineaLote).where(LineaLote.lote_id==lot.id)).all()
    for r in rows:
        if r.producto_id:
            p=get_id(Producto,r.producto_id)
            subsequent=db.session.scalar(db.select(Movimiento.id).where(Movimiento.product_id==p.id,Movimiento.action.not_in(('Confirmar lote','Revertir lote'))))
            if p.status!='Disponible' or p.archived or subsequent or db.session.scalar(db.select(Op.id).where(Op.product_id==p.id)) or db.session.scalar(db.select(Cobro.id).where(Cobro.product_id==p.id)):
                raise ValueError('No se puede revertir: hay equipos con operaciones dependientes.')
        else:
            later=db.session.scalar(db.select(MovimientoStock.id).where(MovimientoStock.articulo_id==r.articulo_id,MovimientoStock.cantidad<0,MovimientoStock.lote_id.is_(None)))
            if later:raise ValueError('Hay salidas del artículo. Corrige con un ajuste trazable, no revirtiendo el lote.')
    for r in rows:
        if r.producto_id:
            p=get_id(Producto,r.producto_id);before=p.to_dict();p.archived=1;p.status='Anulado lote'
            db.session.add(Movimiento(product_id=p.id,action='Revertir lote',reason=reason,actor=actor(),before_data=json.dumps(before),after_data=json.dumps(p.to_dict())))
        else:movement(get_id(ArticuloStock,r.articulo_id),-r.datos['cantidad'],r.datos['cost'],'Reversión de lote: '+reason,lot=lot.id,serial=r.datos.get('serial'))
    c.estado='Borrador';c.revision+=1;audit('lote',lot.id,'Reabrir lote',{},reason)

def attach(lot,file):
    if not current_app.config.get('UPLOADS_ENABLED', True):
        raise ValueError('La carga de facturas está deshabilitada en este entorno. Solicita al administrador habilitar almacenamiento persistente para conservar los archivos.')
    raw=file.read()
    if not raw or len(raw)>8*1024*1024:raise ValueError('La factura debe tener entre 1 byte y 8 MB.')
    if raw.startswith(b'%PDF-'):mime='application/pdf';ext='.pdf'
    elif raw.startswith(b'\x89PNG\r\n\x1a\n'):mime='image/png';ext='.png'
    elif raw.startswith(b'\xff\xd8\xff'):mime='image/jpeg';ext='.jpg'
    else:raise ValueError('Solo se reciben facturas PDF, PNG o JPG.')
    folder=Path(current_app.instance_path)/'facturas';folder.mkdir(parents=True,exist_ok=True)
    filename=secrets.token_hex(24)+ext;(folder/filename).write_bytes(raw)
    row=FacturaLote(lote_id=lot.id,nombre=secure_filename(file.filename)[:200] or 'factura'+ext,archivo=filename,mime=mime,sha256=hashlib.sha256(raw).hexdigest())
    db.session.add(row);audit('lote',lot.id,'Adjuntar factura',{'sha256':row.sha256})
