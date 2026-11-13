from ..database import begin_write
"""Controladores del módulo financiero; escrituras serializadas en SQLite."""
import secrets
from datetime import date
import csv
import io
from flask import Blueprint,render_template,request,redirect,url_for,flash,Response,abort
from sqlalchemy import text
from sqlalchemy.orm import selectinload, load_only
from ..extensions import db
from ..models import Catalogo, Producto, PersonaContable
from ..models.contabilidad import BancoDestino, PersonaBanco
from ..models.finanzas import Jornada, OperacionFinanciera as Op, PagoProveedor as Pago, AuditoriaFinanciera as Audit
from ..services import finanzas_service as svc
from ..auth import can, require

finanzas=Blueprint('finanzas',__name__)

@finanzas.app_template_filter('cop')
def cop(value):
    if value is None:return 'POR REVISAR'
    return '$ '+format(value/100,',.2f').replace(',','X').replace('.',',').replace('X','.')

@finanzas.route('/finanzas',methods=['GET','POST'])
def index():
    day=request.values.get('date') or svc.today()
    error=None
    try:svc.valid_date(day)
    except ValueError as exc:abort(400,str(exc))
    if request.method=='POST':
        try:
            # Impide cierres/pagos simultáneos calculados sobre saldos ya modificados.
            begin_write()
            d=svc.find_day(day)
            action=request.form.get('action')
            if action=='open':
                svc.start_reviewed_day(day,request.form)
            else:
                if not d:raise ValueError('Primero abre la jornada.')
                if action=='reopen':
                    if d.status!='Cerrada' or str(d.revision)!=request.form.get('revision'):
                        raise ValueError('La jornada cambió. Recarga.')
                    reason=svc.text(request.form.get('reason'),True,500)
                    svc.audit(d,'Reapertura',reason,{'previous_snapshot':d.snapshot})
                    d.status='Abierta';d.snapshot=None
                else:
                    svc.editable(d,request.form.get('revision'))
                    if action!='config' and not d.config.get('reviewed'):raise ValueError('Confirma primero Personal y reglas antes de registrar movimientos.')
                    if action=='config':svc.save_config(d,request.form)
                    elif action=='operation':svc.add_operation(d,request.form)
                    elif action=='edit_operation':svc.edit_operation(d,request.form)
                    elif action=='pool_purchase':
                        from ..services.sociedad_service import register_purchase
                        from ..services.gestion_comun import get_id
                        register_purchase(get_id(Producto,request.form.get('product_id')),request.form)
                    elif action=='pool_commission':
                        from ..services.sociedad_service import pay_pool_commission
                        pay_pool_commission(request.form)
                    elif action=='void_pool_commission':
                        from ..services.sociedad_service import reverse_pool_commission
                        reverse_pool_commission(d,request.form)
                    elif action=='staff_payment':svc.pay_staff(d,request.form)
                    elif action=='contribution':svc.confirm_contribution(d,request.form)
                    elif action=='incorporate_all':
                        for p in svc.report(d)['pending_sales']:
                            svc.incorporate(d,p.id,secrets.token_hex(16))
                    elif action=='incorporate':svc.incorporate(d,request.form.get('product_id'),request.form['token'])
                    elif action=='equipment_costs':svc.update_equipment_costs(d,request.form)
                    elif action=='supplier_payment':svc.pay_supplier(d,request.form)
                    elif action=='edit_supplier_payment':svc.edit_supplier_payment(d,request.form)
                    elif action=='void':
                        o=db.session.get(Op,int(request.form.get('operation_id')))
                        if not o or o.day_id!=d.id or o.voided:raise ValueError('Registro inexistente o anulado.')
                        svc.protect_managed_operation(o)
                        if db.session.scalar(db.select(Pago.id).where(Pago.operation_id==o.id)):
                            raise ValueError('Hay pagos a proveedores asociados. Registra la devolución y concilia antes de corregir esta operación.')
                        if o.product_id and o.payments:
                            raise ValueError('Esta venta ya actualizó Inventario y Ventas y pagos. Corrige sus datos en el equipo; una devolución requiere registrar su reversión de dinero.')
                        from ..models.gestion import CompraPool, AplicacionLiquidacion, ResultadoSocio
                        if db.session.scalar(db.select(CompraPool.producto_id).where(CompraPool.operacion_id==o.id)):
                            raise ValueError('Una compra POOL ya incorporó capital al equipo. Corrige su operación y financiación con administración.')
                        if db.session.scalar(db.select(AplicacionLiquidacion.id).join(ResultadoSocio,ResultadoSocio.id==AplicacionLiquidacion.resultado_id).where(ResultadoSocio.operacion_id==o.id)):
                            raise ValueError('Hay liquidaciones pagadas asociadas a esta operación.')
                        from ..services.credito_service import cancel_unreceived
                        cancel_unreceived(o,request.form.get('reason'))
                        from ..services.stock_service import reverse_sale
                        reverse_sale(o,request.form.get('reason',''))
                        o.voided=True
                        from ..services.consignaciones_finanzas import sincronizar_operacion
                        sincronizar_operacion(d.date,o)
                        # Permite incorporar de nuevo el equipo; su identidad queda en auditoría.
                        svc.audit(d,'Anulación',svc.text(request.form.get('reason'),True,500),{'operation':o.id,'product_id':o.product_id})
                        o.product_id=None
                    elif action=='close':
                        if not d.config['reviewed'] or not d.config['actor'] or not any(
                            p.get('attended',True) for p in d.config.get('staff',[])):
                            raise ValueError('Confirma personal y reglas en Configuración antes de cerrar.')
                        r=svc.report(d);t=r['totals']
                        tasks=svc.closing_tasks(d,r)
                        if tasks:raise ValueError('No se puede cerrar: '+ '; '.join(x['label'] for x in tasks))
                        if t['overflow']:raise ValueError('La comisión supera la tabla disponible. No se cerrará con un importe inventado.')
                        if r['pending_sales']:raise ValueError('Incorpora las ventas pendientes del módulo 03.')
                        if any('cambió en MOD03' in w for w in t['warnings']):raise ValueError('Revisa las ventas modificadas en MOD03.')
                        counted=svc.money(request.form.get('counted'))
                        difference=counted-t['cash_to_deliver']
                        reason=svc.text(request.form.get('reason'),difference!=0 or t['base_shortfall']>0 or t['salary_due']>0,500)
                        if t['warnings'] and request.form.get('acknowledge')!='1':raise ValueError('Revisa y reconoce las advertencias antes del cierre.')
                        d.snapshot={'totals':t,'counted':counted,'difference':difference,'config':d.config}
                        d.status='Cerrada'
                        svc.audit(d,'Cierre',reason, d.snapshot)
                    else:raise ValueError('Acción desconocida.')
                svc.commit(d)
            flash('Jornada actualizada.')
            return redirect(url_for('finanzas.index',date=day,tab=request.form.get('return_tab','movimientos')))
        except (ValueError,KeyError,TypeError) as exc:
            db.session.rollback();error=str(exc) or 'Revisa los campos del formulario.'
    d=svc.find_day(day)
    r=svc.report(d) if d else None
    live_totals=r['totals'] if r else None
    if d and d.status=='Cerrada':r['totals']=d.snapshot['totals']
    history=db.session.scalars(db.select(Audit).where(Audit.day_id==d.id).order_by(Audit.id.desc()).limit(100)).all() if d and request.args.get('tab') in ('cierre','proveedores') else []
    payment_origins={}
    if r and r['supplier_payments']:
        ids={p.operation_id for p in r['supplier_payments']}
        sources={o.id:(o,date) for o,date in db.session.execute(db.select(Op,Jornada.date).join(Jornada,Jornada.id==Op.day_id).where(Op.id.in_(ids)))}
        for payment in r['supplier_payments']:
            source,origin_date=sources.get(payment.operation_id,(None,''))
            if source and 0<=payment.cost_index<len(source.costs):
                payment_origins[payment.id]={'name':source.costs[payment.cost_index].get('name','Sin detalle'),'date':origin_date}
    tab=request.values.get('return_tab') or request.args.get('tab','movimientos')
    if tab not in ('movimientos','proveedores','personal','cierre'):tab='movimientos'
    if not can('admin'):tab='movimientos'
    providers=db.session.scalars(db.select(Catalogo).where(Catalogo.kind=='supplier',Catalogo.active==1).order_by(Catalogo.supplier_category,Catalogo.name)).all() if d and tab in ('movimientos','proveedores') else []
    closed_days=db.session.scalars(db.select(Jornada).where(Jornada.status=='Cerrada',Jornada.snapshot.is_not(None))
                                    .order_by(Jornada.date.desc()).limit(14)).all() if tab=='cierre' else []
    trend=[dict(date=item.date,sales=(item.snapshot.get('totals') or {}).get('gross',0),
                count=(item.snapshot.get('totals') or {}).get('sales_count',0),
                result=(item.snapshot.get('totals') or {}).get('owner_result')) for item in reversed(closed_days)]
    trend_max=max((row['sales'] for row in trend),default=0)
    for row in trend:
        row['percentage']=round(row['sales']*100/trend_max,1) if trend_max else 0
    from ..models.gestion import AliadoCredito,ArticuloStock,UnidadStock,CompraPool
    from ..services.pool_jornada import context as pool_context
    warning_links=[]
    for warning in r['totals']['warnings'] if r else []:
        lower=warning.lower();target=url_for('finanzas.index',date=day,tab='movimientos',_anchor='movimientos-jornada')
        if 'sueldo' in lower:target=url_for('finanzas.index',date=day,tab='personal',_anchor='pagos-personal')
        elif 'base' in lower or 'aporte' in lower or 'rojo' in lower:target=url_for('finanzas.index',date=day,tab='cierre',_anchor='aporte-caja')
        elif 'vendedora' in lower:target=url_for('ventas.receipts')
        elif 'cuenta bancaria' in lower or 'titular' in lower:target=url_for('contabilidad.index')
        elif 'control excel' in lower:target=url_for('finanzas.index',date=day,tab='cierre',_anchor='resumen-cierre')
        warning_links.append(dict(label=warning,href=target))
    articles=db.session.scalars(db.select(ArticuloStock).where(ArticuloStock.activo==True)).all() if d and tab=='movimientos' else []
    people=db.session.scalars(db.select(PersonaContable).options(selectinload(PersonaContable.bancos_asociados)).order_by(PersonaContable.nombre)).all() if d and tab in ('movimientos','proveedores','personal') else []
    equipment=db.session.scalars(db.select(Producto).where(Producto.status=='Disponible',Producto.archived==0).order_by(Producto.model,Producto.imei)).all() if d and tab=='movimientos' else []
    pool_ids=[p.id for p in equipment if p.source_type=='Retoma']
    pool_gain={buy.producto_id:buy.ganancia for buy in db.session.scalars(db.select(CompraPool).where(CompraPool.producto_id.in_(pool_ids)))} if pool_ids else {}
    staff_rows=svc.staff_dues(d,r['totals']) if d and can('admin') and tab in ('personal','cierre') else []
    return render_template('finanzas/index.html',active='finanzas',day=day,d=d,r=r,error=error,
        allies=db.session.scalars(db.select(AliadoCredito).where(AliadoCredito.activo==True)).all() if d and tab=='movimientos' else [],
        articles=articles,stock_units=db.session.scalars(db.select(UnidadStock).where(UnidadStock.disponible==True)).all() if articles else [],
        stock_costs={str(a.id):a.costo_administracion for a in articles},
        retomas=[p for p in equipment if p.source_type=='Retoma'],
        providers=providers,provider_categories={p.name:p.supplier_category or 'Accesorios' for p in providers},drink_prices=svc.DRINK_PRICES,
        available_equipment=equipment,
        equipment_costs={p.imei:{'purchase':p.cost_cents+pool_gain.get(p.id,0),'pool':p.source_type=='Retoma'} for p in equipment},
        accounting_people=people,
        banks_destino=db.session.scalars(db.select(BancoDestino).order_by(BancoDestino.nombre)).all() if people else [],
        person_bank_map={p.id:[link.banco_id for link in p.bancos_asociados]
                         for p in people},
        warning_links=warning_links,draft=__import__('types').SimpleNamespace(config=svc.draft_config(day),status='Preparación',revision=0) if not d else None,
        calendar=__import__('app.services.calendario_co',fromlist=['day_info']).day_info(day),
        staff_dues=staff_rows,
        closing_tasks=svc.closing_tasks(d,r,staff_rows) if d and can('admin') and tab=='cierre' else [],
        tab=tab,day_weekday=date.fromisoformat(day).weekday(),token=secrets.token_hex(16),funds=svc.FUNDS,obligations=svc.obligations(day) if d and tab=='proveedores' else [],
        history=history,form=request.form if error else {},live_totals=live_totals,payment_origins=payment_origins,
        days=db.session.scalars(db.select(Jornada).options(load_only(Jornada.date,Jornada.status)).order_by(Jornada.date.desc()).limit(60)).all(),trend=trend,
        pool=pool_context(day,include_candidates=request.args.get('accion')=='compra_pool' or bool(error and request.form.get('action')=='pool_purchase')) if d and can('admin') and tab in ('movimientos','proveedores') else None)

@finanzas.get('/finanzas/exportar')
@require('admin')
def export():
    d=svc.find_day(request.args.get('date',''))
    if not d:abort(404)
    r=svc.report(d);out=io.StringIO();writer=csv.writer(out,delimiter=';')
    writer.writerow(['FECHA','TIPO','DESCRIPCIÓN','RESPONSABLE','VALOR COP','COSTOS MENORES COP','ANULADO'])
    for o in r['operations']:
        def safe(s):return "'"+s if s and s[0] in '=+-@\t\r' else s
        writer.writerow([d.date,o.kind,safe(o.description),safe(o.seller),f'{o.amount/100:.2f}',f'{o.minor_cost/100:.2f}',o.voided])
    t=d.snapshot['totals'] if d.status=='Cerrada' else r['totals']
    writer.writerow([]);writer.writerow(['RESUMEN',d.status])
    for key in ('gross','debe','haber','service','pd','liquidation','result','commission','profit','owner_result','cash_expected'):
        writer.writerow([key,'' if t[key] is None else f'{t[key]/100:.2f}'])
    return Response('\ufeff'+out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename="Finanzas_{d.date}.csv"'})
