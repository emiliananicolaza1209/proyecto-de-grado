from ..database import begin_write
"""Flujos v16 complementarios a los módulos existentes."""
import secrets
from io import BytesIO
from pathlib import Path
from flask import Blueprint,render_template,request,redirect,url_for,flash,send_file,abort,g,current_app
from sqlalchemy import text as sql_text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from ..extensions import db
from ..auth import require,can,ROLES
from ..passwords import validar_clave
from ..models import Catalogo,Lote,Producto,PersonaContable,BancoDestino,PersonaBanco
from ..models.finanzas import Jornada,OperacionFinanciera as Op
from ..models.gestion import *
from ..services import compras_service as compras,stock_service as stock,sociedad_service as sociedad,credito_service as credito
from ..services.gestion_comun import audit,get_id,bp
from ..services.finanzas_service import today,money,text,find_day
from ..services.catalogo_service import normalize,clean,CONDITIONS

gestion=Blueprint('gestion',__name__)

def save(handler):
    if request.method!='POST':return None
    try:
        begin_write()
        handler();db.session.commit();flash('Cambios guardados con historial.','success')
        return redirect(request.url)
    except (ValueError,TypeError,KeyError,ArithmeticError) as e:
        db.session.rollback();flash(str(e) or 'Revisa los datos ingresados.','danger')
    except (IntegrityError,StaleDataError):
        db.session.rollback();flash('Registro duplicado o modificado en otra ventana. Recarga antes de continuar.','danger')
    return None

def context():
    return dict(token=secrets.token_hex(16),now=today(),form=request.form,
        people=db.session.scalars(db.select(PersonaContable).order_by(PersonaContable.nombre)).all(),
        banks=db.session.scalars(db.select(BancoDestino).order_by(BancoDestino.nombre)).all(),
        societies=db.session.scalars(db.select(Sociedad).where(Sociedad.activa==True)).all(),
        partners=db.session.scalars(db.select(Socio).order_by(Socio.nombre)).all())

@gestion.route('/inventario/proveedores',methods=['GET','POST'])
@require('catalogos')
def proveedores():
    def write():
        f=request.form
        p=get_id(Catalogo,f['id']) if f.get('id') else Catalogo(kind='supplier',parent_id=0)
        if p.kind!='supplier':raise ValueError('Proveedor inválido.')
        before=p.name;p.name=text(f.get('name'));p.normal_key=normalize(p.name,'supplier')
        p.active=int(f.get('active','1')=='1');p.supplier_category=f.get('category')
        if p.supplier_category not in ('Celulares','Accesorios','Ambos'):raise ValueError('Categoría inválida.')
        db.session.add(p);db.session.flush()
        extra=db.session.get(DatosProveedor,p.id) or DatosProveedor(proveedor_id=p.id)
        for k,n in [('identificacion',40),('telefono',40),('correo',120),('direccion',200)]:setattr(extra,k,text(f.get(k),False,n))
        db.session.add(extra);audit('proveedor',p.id,'Actualizar proveedor',{'antes':before,'nombre':p.name,'activo':p.active})
    response=save(write)
    if response:return response
    return render_template('gestion/proveedores.html',active='inventario',items=db.session.scalars(db.select(Catalogo).where(Catalogo.kind=='supplier').order_by(Catalogo.name)).all(),
        extras={x.proveedor_id:x for x in db.session.scalars(db.select(DatosProveedor))},**context())

@gestion.route('/inventario/alias',methods=['GET','POST'])
@require('catalogos')
def alias():
    def write():
        f=request.form;ref=get_id(Catalogo,f.get('reference_id'))
        if ref.kind!='reference' or not ref.active:raise ValueError('Selecciona una referencia activa.')
        a=get_id(AliasReferencia,f['id']) if f.get('id') else AliasReferencia()
        before=dict(descripcion=a.descripcion,referencia_id=a.referencia_id)
        a.descripcion=text(f.get('description'),True,200);a.clave=clean(a.descripcion);a.referencia_id=ref.id;a.activo=f.get('active','1')=='1'
        if not a.clave:raise ValueError('Alias vacío.')
        db.session.add(a);db.session.flush();audit('alias',a.id,'Guardar alias',{'antes':before,'referencia':ref.id,'descripcion':a.descripcion})
    response=save(write)
    if response:return response
    return render_template('gestion/alias.html',active='inventario',items=db.session.scalars(db.select(AliasReferencia)).all(),
        references=db.session.scalars(db.select(Catalogo).where(Catalogo.kind=='reference',Catalogo.active==1)).all(),**context())

@gestion.route('/inventario/compras',methods=['GET','POST'])
@require('inventario')
def lotes():
    result={}
    def write():result['lot']=compras.create(request.form)
    response=save(write)
    if response:return redirect(url_for('gestion.lote',lot_id=result['lot'].id))
    rows=db.session.execute(db.select(Lote,ControlLote).join(ControlLote,ControlLote.lote_id==Lote.id).order_by(Lote.id.desc())).all()
    return render_template('gestion/lotes.html',active='inventario',rows=rows,suppliers=db.session.scalars(db.select(Catalogo).where(Catalogo.kind=='supplier',Catalogo.active==1)).all(),**context())

@gestion.route('/inventario/compras/<int:lot_id>',methods=['GET','POST'])
@require('inventario')
def lote(lot_id):
    if not db.session.get(Lote,lot_id):abort(404)
    def write():
        lot=get_id(Lote,lot_id);c=compras.control(lot_id,request.form.get('revision'));action=request.form.get('action')
        if action=='add':
            f=request.form.to_dict();imeis=f.get('imei','').splitlines() or ['']
            if len(imeis)>200:raise ValueError('Máximo 200 IMEI por entrada.')
            compras.add_lines(lot,c,[dict(f,imei=i.strip()) for i in imeis if i.strip()] if f.get('tipo')=='Equipo' else [f])
        elif action=='import':compras.add_lines(lot,c,compras.read_excel(request.files['excel']))
        elif action=='remove':
            if c.estado!='Borrador':raise ValueError('Reabre el lote antes de corregir sus líneas.')
            row=get_id(LineaLote,request.form.get('line_id'))
            if row.lote_id!=lot_id:raise ValueError('Línea ajena al lote.')
            audit('lote',lot_id,'Retirar línea del borrador',row.datos);db.session.delete(row);c.revision+=1
        elif action=='quantity':
            if c.estado!='Borrador':raise ValueError('Reabre el lote para corregir la cantidad.')
            count=int(request.form.get('expected_count') or 0)
            if not 1<=count<=10000:raise ValueError('Cantidad fuera de rango.')
            audit('lote',lot_id,'Corregir cantidad esperada',{'antes':lot.expected_count,'despues':count},request.form.get('reason'))
            lot.expected_count=count;c.revision+=1
        elif action=='confirm':
            if not can('admin'):abort(403)
            compras.confirm(lot,c)
        elif action=='reopen':
            if not can('admin'):abort(403)
            compras.reopen(lot,c,request.form.get('reason',''))
        elif action=='invoice':compras.attach(lot,request.files['invoice'])
        else:raise ValueError('Acción desconocida.')
    response=save(write)
    if response:return response
    lot=get_id(Lote,lot_id);c=get_id(ControlLote,lot_id)
    return render_template('gestion/lote.html',active='inventario',lot=lot,c=c,
        lines=db.session.scalars(db.select(LineaLote).where(LineaLote.lote_id==lot_id)).all(),
        products=db.session.scalars(db.select(Producto).where(Producto.lot_id==lot_id)).all(),
        invoices=db.session.scalars(db.select(FacturaLote).where(FacturaLote.lote_id==lot_id)).all(),
        catalog=db.session.scalars(db.select(Catalogo).where(Catalogo.active==1)).all(),conditions=CONDITIONS,
        articles=db.session.scalars(db.select(ArticuloStock).where(ArticuloStock.activo==True)).all(),**context())

@gestion.get('/inventario/compras/plantilla.xlsx')
@require('inventario')
def plantilla():
    from openpyxl import Workbook
    w=Workbook();sh=w.active;sh.title='Ingreso';sh.append(compras.HEADERS)
    sh.freeze_panes='A2';sh.auto_filter.ref='A1:M1'
    guide=w.create_sheet('Catálogos');guide.append(['ID','TIPO','NOMBRE','ID PADRE'])
    for item in db.session.scalars(db.select(Catalogo).where(Catalogo.active==1)):guide.append([item.id,item.kind,item.display_name,item.parent_id])
    stock_sheet=w.create_sheet('Artículos');stock_sheet.append(['ID','NOMBRE','SERIALIZADO'])
    for a in db.session.scalars(db.select(ArticuloStock).where(ArticuloStock.activo==True)):stock_sheet.append([a.id,a.nombre,'Sí' if a.serializado else 'No'])
    guide=w.create_sheet('Instrucciones');guide.append(['Equipos: tipo=Equipo, una fila por IMEI; use IDs de referencia, color, capacidad y ubicación.'])
    guide.append(['Artículos: tipo=Artículo, articulo_id y cantidad. Serial libre solo si el artículo es serializado.'])
    guide.append(['purchase_price: precio unitario en la moneda del lote. shipping_cop: envío unitario en COP. Sin separadores de miles.'])
    guide.append(['La carga solo agrega filas al borrador. Revise y confirme el lote para crear existencias.'])
    for sheet in w:
        for col in sheet.columns:sheet.column_dimensions[col[0].column_letter].width=24
    out=BytesIO();w.save(out);out.seek(0)
    return send_file(out,as_attachment=True,download_name='Plantilla_lote_CP_Store.xlsx')

def _factura_valida(nombre):
    """Las facturas se guardan con 48 caracteres hexadecimales y una extensión conocida; cualquier otra cosa no se sirve."""
    nombre=nombre or '';base=nombre[:-4] if nombre[-4:] in ('.pdf','.png','.jpg') else ''
    return len(base)==48 and all(c in '0123456789abcdef' for c in base)

@gestion.get('/inventario/facturas/<int:invoice_id>')
@require('inventario')
def factura(invoice_id):
    row=db.session.get(FacturaLote,invoice_id)
    if not row or not _factura_valida(row.archivo):abort(404)
    carpeta=(Path(current_app.instance_path)/'facturas').resolve();path=(carpeta/row.archivo).resolve()
    if path.parent!=carpeta or not path.is_file():abort(404)  # nunca fuera de instance/facturas (tampoco por un enlace simbólico)
    respuesta=send_file(path,mimetype=row.mime,as_attachment=True,download_name=secure_filename(row.nombre or '') or 'factura'+path.suffix)
    respuesta.headers['Cache-Control']='private, no-store'
    return respuesta

@gestion.route('/inventario/articulos',methods=['GET','POST'])
@require('inventario')
def articulos():
    def write():
        f=request.form;action=f.get('action')
        if not can('admin'):abort(403)
        if action=='category':
            c=get_id(CategoriaStock,f.get('id')) if f.get('id') else CategoriaStock()
            c.nombre=text(f.get('name'));c.activa=f.get('active','1')=='1';db.session.add(c);db.session.flush();audit('categoria',c.id,'Guardar categoría',{'nombre':c.nombre,'activa':c.activa})
        elif action=='article':
            a=get_id(ArticuloStock,f.get('id')) if f.get('id') else ArticuloStock()
            cat=get_id(CategoriaStock,f.get('category_id'))
            if not cat.activa:raise ValueError('La categoría está inactiva.')
            serialized=f.get('serialized')=='1'
            if a.id and serialized!=a.serializado and db.session.scalar(db.select(MovimientoStock.id).where(MovimientoStock.articulo_id==a.id)):
                raise ValueError('Un artículo con movimientos conserva su modalidad de serial.')
            a.nombre=text(f.get('name'));a.categoria_id=cat.id;a.serializado=serialized;a.minimo=int(f.get('minimum') or 0)
            a.costo_administracion=money(f.get('cost'));a.fondo=f.get('fund');a.activo=f.get('active','1')=='1'
            if a.minimo<0 or a.fondo not in ('CP VARIOS','CP HIDROGELES','BATERÍAS','MEMORIAS'):raise ValueError('Mínimo o fondo inválido.')
            db.session.add(a);db.session.flush();audit('articulo',a.id,'Guardar producto y costo administrativo',{'costo':a.costo_administracion,'activo':a.activo})
        elif action=='adjust':
            a=get_id(ArticuloStock,f.get('article_id'));reason=text(f.get('reason'),True,500)
            stock.movement(a,int(f.get('quantity')),a.costo_administracion,'Ajuste: '+reason,serial=f.get('serial') or None)
        else:raise ValueError('Acción desconocida.')
    response=save(write)
    if response:return response
    arts=db.session.scalars(db.select(ArticuloStock).order_by(ArticuloStock.nombre)).all()
    return render_template('gestion/articulos.html',active='inventario',articles=arts,balances={a.id:stock.balance(a.id) for a in arts},
        categories=db.session.scalars(db.select(CategoriaStock)).all(),movements=db.session.scalars(db.select(MovimientoStock).order_by(MovimientoStock.id.desc()).limit(100)).all(),**context())

@gestion.route('/finanzas/creditos',methods=['GET','POST'])
@require('admin')  # la lista trae comisiones y montos de todas las ventas: solo administración (pendiente 7, opción 1)
def creditos():
    def write():
        if not can('admin'):abort(403)
        if request.form.get('action')=='settle':credito.settle(request.form)
        elif request.form.get('action')=='ally':
            f=request.form;a=get_id(AliadoCredito,f['id']) if f.get('id') else AliadoCredito()
            a.nombre=text(f.get('name'));a.porcentaje_bp=bp(f.get('rate'));a.activo=f.get('active','1')=='1'
            if f.get('person_id') or f.get('bank_id'):a.persona_id,a.banco_id=credito.destino(f.get('person_id'),f.get('bank_id'))
            else:a.persona_id=None;a.banco_id=None
            db.session.add(a);db.session.flush();audit('aliado',a.id,'Guardar condiciones futuras',{'nombre':a.nombre,'porcentaje_bp':a.porcentaje_bp,'persona_id':a.persona_id,'banco_id':a.banco_id})
        else:raise ValueError('Acción desconocida.')
    response=save(write)
    if response:return response
    rows=db.session.execute(db.select(CreditoVenta,Op,Jornada).join(Op,Op.id==CreditoVenta.operacion_id).join(Jornada,Jornada.id==Op.day_id).order_by(CreditoVenta.id.desc())).all()
    return render_template('gestion/creditos.html',active='finanzas',rows=rows,allies=db.session.scalars(db.select(AliadoCredito)).all(),
        batches=db.session.scalars(db.select(DesembolsoCredito).order_by(DesembolsoCredito.id.desc())).all(),**context())

@gestion.route('/finanzas/sociedades',methods=['GET','POST'])
@gestion.route('/ventas/sociedades',methods=['GET','POST'])
def sociedades():
    if not can('sociedades_consulta') and not can('admin'):abort(403)
    def write():
        if not can('admin'):abort(403)
        f=request.form;action=f.get('action')
        if action in ('partner','society') and not can('sociedades_config'):abort(403)
        if action=='partner':
            p=get_id(Socio,f['id']) if f.get('id') else Socio()
            if p.id and p.id==db.session.scalar(db.select(Socio.id).order_by(Socio.id).limit(1)) and f.get('active')=='0':raise ValueError('Conserva activo el propietario principal.')
            p.nombre=text(f.get('name'));p.activo=f.get('active','1')=='1';db.session.add(p);db.session.flush();audit('socio',p.id,'Guardar socio',{'nombre':p.nombre,'activo':p.activo})
        elif action=='society':sociedad.save_society(f)
        elif action=='ownership':sociedad.assign_ownership(get_id(Producto,f.get('product_id')),f.get('society_id') or None)
        elif action=='liquidate':sociedad.liquidate(f)
        elif action=='dissolve':sociedad.dissolve(f)
        else:raise ValueError('Acción desconocida.')
    response=save(write)
    if response:return response
    user=getattr(g,'usuario',None);sid=user.socio_id if user and user.rol=='Socio' else None
    if user and user.rol=='Socio' and not sid:abort(403)
    start=request.args.get('start') or None;end=request.args.get('end') or None
    rows=sociedad.balances(sid,start,end)
    liquidations=db.select(LiquidacionSocio).order_by(LiquidacionSocio.id.desc())
    if sid:liquidations=liquidations.where(LiquidacionSocio.socio_id==sid)
    ownership=[]
    for p,own in db.session.execute(db.select(Producto,PropiedadEquipo).join(PropiedadEquipo,Producto.id==PropiedadEquipo.producto_id)):
        if not sid or any(x['socio_id']==sid for x in own.participaciones):
            parts=own.participaciones if not sid else [x for x in own.participaciones if x['socio_id']==sid]
            ownership.append(dict(product=p,own=own,parts=parts))
    return render_template('gestion/sociedades.html',active='ventas',rows=rows,ownership=ownership,
        liquidations=db.session.scalars(liquidations).all(),restricted=bool(sid),
        society_rows=db.session.scalars(db.select(Sociedad)).all() if not sid else [],
        shares=db.session.scalars(db.select(Participacion)).all() if not sid else [],
        products=db.session.scalars(db.select(Producto).where(Producto.status=='Disponible',Producto.archived==0)).all() if not sid else [],**context())

@gestion.route('/finanzas/pool',methods=['GET','POST'])
@require('admin')
def pool():
    # Compatibilidad con enlaces y formularios de V16; el acceso actual es Jornada.
    def write():
        if request.form.get('action')=='purchase':sociedad.register_purchase(get_id(Producto,request.form.get('product_id')),request.form)
        elif request.form.get('action')=='commission':sociedad.pay_pool_commission(request.form)
        else:raise ValueError('Acción desconocida.')
    save(write)
    commission=request.form.get('action')=='commission'
    return redirect(url_for('finanzas.index',date=request.values.get('date') or today(),
                            tab='proveedores' if commission else 'movimientos',
                            _anchor='comisiones-pool' if commission else 'compra-pool'))

@gestion.route('/usuarios',methods=['GET','POST'])
@require('usuarios')
def usuarios():
    from ..services.permisos_service import MODULES, profile_keys, validate_permissions
    def write():
        f=request.form;u=get_id(Usuario,f['id']) if f.get('id') else Usuario()
        rol=f.get('role')
        if rol not in ROLES:raise ValueError('Perfil inválido.')
        selected=validate_permissions(rol,f.get('permission_mode','perfil'),f.getlist('permission'))
        # Una página anterior a esta versión no borra una personalización existente.
        previous=db.session.get(PermisosUsuario,u.id) if u.id else None
        if previous and 'permission_mode' not in f:raise ValueError('Recarga Usuarios antes de cambiar este acceso.')
        if u.id and 'permission_mode' in f and f.get('access_version')!=str(u.session_version):
            raise ValueError('Este usuario cambió en otra ventana. Recarga antes de guardar.')
        before=dict(rol=u.rol,activo=u.activo,permisos=previous.permisos if previous else None)
        active=f.get('active','1')=='1'
        if u.id and u.rol=='Propietario' and (not active or rol!='Propietario'):
            if db.session.scalar(db.select(db.func.count(Usuario.id)).where(Usuario.rol=='Propietario',Usuario.activo==True,Usuario.id!=u.id))==0:
                raise ValueError('Debe permanecer un propietario activo.')
        password=f.get('password','')
        if password or not u.id:
            validar_clave(password,f.get('login'),f.get('name'))
            u.password_hash=generate_password_hash(password)
        u.nombre=text(f.get('name'));u.login=f.get('login','').strip().lower()
        if not u.login or len(u.login)>120:raise ValueError('Usuario inválido.')
        u.rol=rol;u.activo=active;u.socio_id=get_id(Socio,f.get('partner_id')).id if rol=='Socio' else None
        u.session_version=(u.session_version or 0)+1;db.session.add(u);db.session.flush()
        if selected is None:
            if previous:db.session.delete(previous)
        elif previous:previous.permisos=selected
        else:db.session.add(PermisosUsuario(usuario_id=u.id,permisos=selected))
        audit('usuario',u.id,'Actualizar acceso',{'antes':before,'rol':rol,'activo':active,'permisos':selected})
    response=save(write)
    if response:return response
    return render_template('gestion/usuarios.html',active='usuarios',users=db.session.scalars(db.select(Usuario).order_by(Usuario.nombre)).all(),
        roles=ROLES,permission_modules=MODULES,profile_permissions={r:sorted(profile_keys(r)) for r in ROLES},
        permissions_by_user={r.usuario_id:r.permisos for r in db.session.scalars(db.select(PermisosUsuario))},**context())

@gestion.get('/gestion/historial')
@require('admin')
def historial():
    rows=db.select(RegistroGestion).order_by(RegistroGestion.id.desc())
    if request.args.get('entidad'):rows=rows.where(RegistroGestion.entidad==request.args['entidad'])
    if request.args.get('id'):
        try:rows=rows.where(RegistroGestion.entidad_id==int(request.args['id']))
        except ValueError:abort(400,'El id debe ser un número.')
    return render_template('gestion/historial.html',active='finanzas',rows=db.session.scalars(rows.limit(300)).all())

@gestion.get('/inventario/inversion')
@gestion.get('/ventas/inversion')
def inversion():
    if not can('costos') and not can('sociedades_consulta'):abort(403)
    user=getattr(g,'usuario',None);sid=user.socio_id if user and user.rol=='Socio' else None
    if user and user.rol=='Socio' and not sid:abort(403)
    from ..services.gestion_comun import distribute
    totals={}
    # Inventario necesita saber cuántos equipos hay en cada ubicación, no cuánto capital tiene cada socio.
    solo_ubicacion=not sid and not can('admin')
    por_ubicacion={}
    for p in db.session.scalars(db.select(Producto).where(Producto.archived==0,Producto.status!='Vendido')):
        if p.status=='Garantía' and p.warranty_previous=='Vendido':continue
        if solo_ubicacion:
            nombre=p.location_item.name if p.location_item else p.location
            por_ubicacion[nombre]=por_ubicacion.get(nombre,0)+1
            continue
        own=db.session.get(PropiedadEquipo,p.id);parts=own.participaciones if own else sociedad.snapshot()
        amounts=distribute(own.capital if own else p.cost_cents,[x['capital_bp'] for x in parts])
        for part,amount in zip(parts,amounts):
            if sid and part['socio_id']!=sid:continue
            name=p.location_item.name if p.location_item else p.location
            key=(name,part['socio_id']);item=totals.setdefault(key,dict(location=name,partner=part['nombre'],capital=0,count=0))
            item['capital']+=amount;item['count']+=1
    if solo_ubicacion:
        return render_template('gestion/inversion.html',active='ventas',solo_ubicacion=True,
            rows=[dict(location=k,count=v) for k,v in sorted(por_ubicacion.items(),key=lambda x:str(x[0]))],total=None)
    return render_template('gestion/inversion.html',active='ventas',solo_ubicacion=False,rows=list(totals.values()),total=sum(x['capital'] for x in totals.values()))
