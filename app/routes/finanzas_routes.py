"""Controladores del módulo financiero; escrituras serializadas en SQLite."""
import secrets
from datetime import date
import csv
import io
from flask import Blueprint,render_template,request,redirect,url_for,flash,Response,abort
from sqlalchemy import text
from ..extensions import db
from ..models import Catalogo
from ..models.finanzas import Jornada, OperacionFinanciera as Op, PagoProveedor as Pago, AuditoriaFinanciera as Audit
from ..services import finanzas_service as svc

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
            db.session.execute(text('BEGIN IMMEDIATE'))
            d=svc.find_day(day)
            action=request.form.get('action')
            if action=='open':
                svc.open_day(day)
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
                    if action=='config':svc.save_config(d,request.form)
                    elif action=='operation':svc.add_operation(d,request.form)
                    elif action=='incorporate_all':
                        for p in svc.report(d)['pending_sales']:
                            svc.incorporate(d,p.id,secrets.token_hex(16))
                    elif action=='incorporate':svc.incorporate(d,request.form.get('product_id'),request.form['token'])
                    elif action=='equipment_costs':svc.update_equipment_costs(d,request.form)
                    elif action=='supplier_payment':svc.pay_supplier(d,request.form)
                    elif action=='void':
                        o=db.session.get(Op,int(request.form.get('operation_id')))
                        if not o or o.day_id!=d.id or o.voided:raise ValueError('Registro inexistente o anulado.')
                        if db.session.scalar(db.select(Pago.id).where(Pago.operation_id==o.id)):
                            raise ValueError('Hay pagos a proveedores asociados. Registra la devolución y concilia antes de corregir esta operación.')
                        o.voided=True
                        # Permite incorporar de nuevo el equipo; su identidad queda en auditoría.
                        svc.audit(d,'Anulación',svc.text(request.form.get('reason'),True,500),{'operation':o.id,'product_id':o.product_id})
                        o.product_id=None
                    elif action=='close':
                        if not d.config['reviewed'] or not d.config['actor']:
                            raise ValueError('Confirma personal y reglas en Configuración antes de cerrar.')
                        r=svc.report(d);t=r['totals']
                        if t['overflow']:raise ValueError('La comisión supera la tabla disponible. No se cerrará con un importe inventado.')
                        if r['pending_sales']:raise ValueError('Incorpora las ventas pendientes del módulo 03.')
                        if any('cambió en MOD03' in w for w in t['warnings']):raise ValueError('Revisa las ventas modificadas en MOD03.')
                        counted=svc.money(request.form.get('counted'))
                        reason=svc.text(request.form.get('reason'),counted!=t['cash_expected'],500)
                        if t['warnings'] and request.form.get('acknowledge')!='1':raise ValueError('Revisa y reconoce las advertencias antes del cierre.')
                        d.snapshot={'totals':t,'counted':counted,'difference':counted-t['cash_expected'],'config':d.config}
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
    history=db.session.scalars(db.select(Audit).where(Audit.day_id==d.id).order_by(Audit.id.desc())).all() if d else []
    tab=request.values.get('return_tab') or request.args.get('tab','movimientos')
    if tab not in ('movimientos','proveedores','personal','cierre'):tab='movimientos'
    return render_template('finanzas/index.html',active='finanzas',day=day,d=d,r=r,error=error,
        providers=db.session.scalars(db.select(Catalogo.name).where(Catalogo.kind=='supplier',Catalogo.active==1)).all(),
        tab=tab,day_weekday=date.fromisoformat(day).weekday(),token=secrets.token_hex(16),funds=svc.FUNDS,obligations=svc.obligations() if d else [],
        history=history,form=request.form if error else {},live_totals=live_totals,
        days=db.session.scalars(db.select(Jornada).order_by(Jornada.date.desc()).limit(60)).all())

@finanzas.get('/finanzas/exportar')
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
