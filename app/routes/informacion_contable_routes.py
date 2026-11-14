from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response, g
from sqlalchemy.exc import IntegrityError
from decimal import Decimal, InvalidOperation
from app.extensions import db
from app.models.contabilidad import PersonaContable, BancoDestino, PersonaBanco, ConsignacionBancaria, HistorialConsignacion
from app.models.finanzas import OperacionFinanciera
from app.services.contabilidad_service import (
    evaluar_estado_renta, resumir_por_banco, consolidar_periodo,
    generar_csv, registrar_reporte, ultimos_reportes, parse_period,
    registrar_ingreso_gasto, corregir_clasificacion, movimientos_periodo, datos_paquete,
    ultimas_correcciones, CATEGORIAS_INGRESO_GASTO, ACTOR_ANONIMO,
)
from app.services.operacion_service import today
from app.services.paquete_contador_service import construir_modelo, generar_excel, generar_pdf
from app.auth import require
from app.models.contabilidad import ahora_colombia
from app.services.personas_contables import (nueva_persona, coincidencias, banco_por_nombre,
    asociar_banco, banco_de_persona)


def _actor():
    """Usuario autenticado para la auditoría contable; sin login (modo local) queda anónimo."""
    user = getattr(g, 'usuario', None)
    return user.login if user is not None else ACTOR_ANONIMO

# Definición del Blueprint con su prefijo
contabilidad_bp = Blueprint('contabilidad', __name__, url_prefix='/modulos/tributario')



@contabilidad_bp.app_template_filter('destino_consignacion')
def destino_consignacion(c):
    if c.banco:return c.banco.nombre
    # One read per source in a request; no inferred financial destination.
    if c.finance_operation_id:
        op=db.session.get(OperacionFinanciera,c.finance_operation_id)
        if op and c.payment_index is not None and 0<=c.payment_index<len(op.payments) and op.payments[c.payment_index].get('account')=='DATÁFONO':return 'DATÁFONO'
    if c.supplier_payment_id:
        from ..models.finanzas import PagoProveedor
        payment=db.session.get(PagoProveedor,c.supplier_payment_id)
        if payment and payment.account=='DATÁFONO':return 'DATÁFONO'
    return 'Sin banco identificado'

@contabilidad_bp.route('/', strict_slashes=False)
def index(form_error=None,matched_person=None):
    error = None
    try:
        ini, fin = parse_period(request.args.get('ini'), request.args.get('fin'))
    except ValueError as exc:
        error = str(exc)
        ini, fin = parse_period(None, None)
    try:
        consolidado = consolidar_periodo(ini, fin)
        movimientos = movimientos_periodo(ini, fin)
    except ValueError as exc:
        consolidado, movimientos, error = None, [], str(exc)
    personas = PersonaContable.query.order_by(PersonaContable.nombre).all()
    bancos = BancoDestino.query.order_by(BancoDestino.nombre).all()
    try: anio=int(request.args.get('anio',date.today().year))
    except ValueError: anio=date.today().year
    if not 2025<=anio<=date.today().year: anio=date.today().year
    
    desglose = resumir_por_banco(personas, anio)
    detalle_bancos = request.args.get('detalle_bancos', type=int)
    persona_bancos = detalle_bancos or request.args.get('persona', type=int)
    if persona_bancos not in desglose:
        persona_bancos = personas[0].id if personas else None
    reporte_personal = []
    for p in personas:
        estado = evaluar_estado_renta(p.id,anio)
        reporte_personal.append({
            "persona": p,
            "estado": estado,
            "desglose": desglose[p.id]
        })

    return render_template(
        'contabilidad/index.html',
        reporte_personal=reporte_personal,
        destinatarios=personas, # Pasamos esto para el selector del formulario
        bancos=bancos,
        persona_bancos=persona_bancos,abrir_bancos=detalle_bancos in desglose,
        bank_names={b.id:b.nombre for b in bancos},
        bancos_por_persona={p.id:[link.banco.id for link in p.bancos_asociados] for p in personas},
        form_error=form_error,matched_person=matched_person,person_form=request.form if form_error else {},
        anio=anio,hoy=today(), tope_limite=(reporte_personal[0]['estado']['tope_limite'] if reporte_personal else evaluar_estado_renta(0,anio)['tope_limite']),
        consignaciones=ConsignacionBancaria.query.order_by(ConsignacionBancaria.fecha.desc(),ConsignacionBancaria.id.desc()).limit(150).all(),
        historial=HistorialConsignacion.query.order_by(HistorialConsignacion.id.desc()).limit(100).all(),
        ventas=OperacionFinanciera.query.filter(OperacionFinanciera.person_id.isnot(None),OperacionFinanciera.voided==False).order_by(OperacionFinanciera.id.desc()).limit(50).all(),
        consolidado=consolidado, ini=ini, fin=fin, error=error,
        movimientos=movimientos,
        correcciones=ultimas_correcciones(),
        categorias=CATEGORIAS_INGRESO_GASTO,
        reportes=ultimos_reportes(),
        active='tributario'  # Ilumina la opción en el sidebar
    )


@contabilidad_bp.get('/personas/verificar')
def verificar_persona():
    name=request.args.get('nombre','')[:120]
    document=request.args.get('identificacion','')[:30]
    if len(name)<3 and len(document)<3:return jsonify(exact=[],similar=[])
    exact,similar=coincidencias(name,document)
    def item(person):
        return {'id':person.id,'nombre':person.nombre,'identificacion':person.identificacion,
                'bancos':[link.banco.nombre for link in person.bancos_asociados]}
    return jsonify(exact=[item(p) for p in exact],similar=[item(p) for p in similar])


@contabilidad_bp.get('/export.csv')
def exportar_csv():
    """HU-TRI-002: exporta el consolidado del periodo y registra quién/cuándo."""
    try:
        ini, fin = parse_period(request.args.get('ini'), request.args.get('fin'))
        consolidado = consolidar_periodo(ini, fin)
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('contabilidad.index'))
    registrar_reporte(ini, fin, consolidado, _actor(), formato='csv')
    data = generar_csv(consolidado, _actor())
    return Response(
        data,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename=consolidado_{ini}_{fin}.csv'},
    )


_PAQUETE_TIPOS = {
    'xlsx': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', generar_excel),
    'pdf': ('application/pdf', generar_pdf),
}


def _descargar_paquete(formato):
    """Paquete para el contador (Excel o PDF): mismos datos que la pantalla y el CSV, en memoria.

    Solo Propietario y Administrador (capacidad 'contabilidad'); queda registrado quién, cuándo y qué formato.
    """
    mimetype, generador = _PAQUETE_TIPOS[formato]
    try:
        datos = datos_paquete(request.args.get('ini'), request.args.get('fin'))
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('contabilidad.index'))
    actor = _actor()
    modelo = construir_modelo(datos, actor, ahora_colombia().strftime('%Y-%m-%d %H:%M'))
    contenido = generador(modelo)
    registrar_reporte(datos['ini'], datos['fin'], datos['consolidado'], actor, formato=formato)
    respuesta = Response(contenido, mimetype=mimetype, headers={
        'Content-Disposition': f"attachment; filename=paquete_contador_{datos['ini']}_{datos['fin']}.{formato}",
        'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff',
    })
    return respuesta


@contabilidad_bp.get('/paquete.xlsx')
@require('contabilidad')
def paquete_excel():
    return _descargar_paquete('xlsx')


@contabilidad_bp.get('/paquete.pdf')
@require('contabilidad')
def paquete_pdf():
    return _descargar_paquete('pdf')


@contabilidad_bp.post('/ingreso-gasto/nuevo')
def registrar_movimiento():
    """HU-FIN-001/002: registra un ingreso o gasto para el consolidado."""
    try:
        registrar_ingreso_gasto({
            'tipo': request.form.get('tipo'),
            'concepto': request.form.get('concepto'),
            'categoria': request.form.get('categoria'),
            'valor': request.form.get('valor'),
            'fecha': request.form.get('fecha'),
            'relacion': request.form.get('relacion'),
            'soporte_ref': request.form.get('soporte_ref'),
            'responsable': request.form.get('responsable'),
        }, _actor())
        flash('Movimiento registrado exitosamente.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
    except Exception:
        db.session.rollback()
        flash('No fue posible registrar el movimiento. Revisa los datos e intenta de nuevo.', 'danger')
    return redirect(url_for('contabilidad.index'))


@contabilidad_bp.post('/clasificacion/<int:ig_id>')
def corregir(ig_id):
    """HU-TRI-003: corrige la categoría conservando anterior, nueva y motivo."""
    try:
        corregir_clasificacion(ig_id, request.form.get('nueva_categoria'),
                               request.form.get('motivo'), _actor())
        flash('Clasificación corregida y registrada en auditoría.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
    except Exception:
        db.session.rollback()
        flash('No fue posible corregir la clasificación.', 'danger')
    return redirect(url_for('contabilidad.index'))



@contabilidad_bp.route('/consignacion/nueva', methods=['POST'])
def registrar_consignacion():
    try:
        persona_id,banco_id,monto,fecha,referencia=campos_consignacion(request.form)
        nueva_cons = ConsignacionBancaria(
            persona_id=persona_id,banco_id=banco_id,monto=monto,fecha=fecha,referencia=referencia
        )
        db.session.add(nueva_cons)
        db.session.flush()
        db.session.add(HistorialConsignacion(consignacion_id=nueva_cons.id,accion='Registro',
            motivo='Registro inicial',despues=datos_consignacion(nueva_cons)))
        db.session.commit()
        flash("Consignación registrada exitosamente.", "success")
    except (ValueError, TypeError, InvalidOperation) as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    except Exception:
        db.session.rollback()
        flash("No fue posible registrar la consignación. Revisa los datos e intenta de nuevo.", "danger")

    return redirect(url_for('contabilidad.index',_anchor='consignaciones'))


def datos_consignacion(c):
    return dict(persona_id=c.persona_id,banco_id=c.banco_id,monto=str(c.monto),
                fecha=c.fecha.isoformat(),referencia=c.referencia or '')


def campos_consignacion(form):
    try:
        persona_id=int(form.get('persona_id',''));banco_id=int(form.get('banco_id',''))
        monto=Decimal(form.get('monto',''))
        fecha=datetime.strptime(form.get('fecha') or today(),'%Y-%m-%d')
    except (ValueError, TypeError, InvalidOperation): raise ValueError('Revisa persona, banco, fecha e importe.')
    if not db.session.get(PersonaContable,persona_id) or not db.session.get(BancoDestino,banco_id):
        raise ValueError('Selecciona una persona y un banco registrados.')
    if not banco_de_persona(persona_id,banco_id):
        raise ValueError('Primero asocia este banco a la persona en Información contable.')
    if not monto.is_finite() or monto<=0 or monto>Decimal('999999999999.99') or monto!=monto.quantize(Decimal('.01')):
        raise ValueError('Ingresa un monto positivo con máximo dos decimales.')
    if fecha.date()>date.fromisoformat(today()):raise ValueError('La fecha no puede ser futura.')
    referencia=(form.get('referencia') or '').strip()
    if len(referencia)>100:raise ValueError('Referencia demasiado larga.')
    return persona_id,banco_id,monto,fecha,referencia


@contabilidad_bp.post('/consignacion/<int:record_id>/editar')
def editar_consignacion(record_id):
    c=db.session.get(ConsignacionBancaria,record_id)
    if not c: return redirect(url_for('contabilidad.index'))
    try:
        motivo=(request.form.get('motivo') or '').strip()
        if not 3<=len(motivo)<=500:raise ValueError('Explica la corrección (3 a 500 caracteres).')
        before=datos_consignacion(c)
        c.persona_id,c.banco_id,c.monto,c.fecha,c.referencia=campos_consignacion(request.form)
        db.session.add(HistorialConsignacion(consignacion_id=c.id,accion='Edición',
            motivo=motivo,antes=before,despues=datos_consignacion(c)))
        db.session.commit()
        flash('Consignación corregida. Las ventas no se modificaron.','success')
    except (ValueError,TypeError,InvalidOperation) as exc:
        db.session.rollback();flash(str(exc),'danger')
    return redirect(url_for('contabilidad.index',anio=request.form.get('anio',date.today().year),_anchor='consignaciones'))

@contabilidad_bp.route('/crear-destinatario', methods=['POST'])
def crear_destinatario():
    try:
        person=nueva_persona(request.form)
        db.session.commit()
        flash(f'{person.nombre} registrada. Ahora puedes asociarle un banco.','success')
        return redirect(url_for('contabilidad.index',persona=person.id,_anchor='asociar-banco'))
    except (ValueError,IntegrityError) as exc:
        db.session.rollback()
        exact,_=coincidencias(request.form.get('nombre'),request.form.get('identificacion'))
        return index(form_error=str(exc),matched_person=exact[0] if exact else None),409


@contabilidad_bp.post('/persona/<int:person_id>/bancos')
def agregar_banco_persona(person_id):
    try:
        person,bank,created=asociar_banco(person_id,request.form.get('banco_id'),request.form.get('nuevo_banco'))
        db.session.commit()
        flash(f'{bank.nombre} {"asociado" if created else "ya estaba asociado"} a {person.nombre}.','success')
        return redirect(url_for('contabilidad.index',persona=person.id,_anchor='asociar-banco'))
    except (ValueError,IntegrityError) as exc:
        db.session.rollback()
        flash(str(exc),'danger')
        return redirect(url_for('contabilidad.index',persona=person_id,_anchor='asociar-banco'))


@contabilidad_bp.post('/persona/bancos')
def agregar_banco_persona_actual():
    try:person_id=int(request.form.get('persona_id',''))
    except (ValueError,TypeError):
        flash('Selecciona una persona registrada.','danger')
        return redirect(url_for('contabilidad.index',_anchor='asociar-banco'))
    return agregar_banco_persona(person_id)

@contabilidad_bp.route('/crear-banco', methods=['POST'])
def crear_banco():
    nombre_banco = (request.form.get('nombre_banco') or '').strip()
    if nombre_banco:
        if not 2 <= len(nombre_banco) <= 60:
            flash('El nombre del banco debe tener entre 2 y 60 caracteres.', 'warning')
            return redirect(url_for('contabilidad.index'))
        try:
            nuevo,created=banco_por_nombre(nombre_banco)
            db.session.commit()
            flash('Banco registrado con éxito' if created else 'El banco ya existe; selecciónalo para asociarlo a la persona.', 'success')
        except IntegrityError:
            db.session.rollback()
            flash('Este banco ya se encuentra registrado.', 'danger')
        except Exception:
            db.session.rollback()
            flash('No fue posible registrar el banco.', 'danger')
    else:
        flash('El nombre del banco es obligatorio.', 'warning')
        
    return redirect(url_for('contabilidad.index'))


@contabilidad_bp.post('/persona/<int:person_id>/antecedente')
def actualizar_antecedente(person_id):
    persona=db.session.get(PersonaContable,person_id)
    if persona:
        persona.declaro_renta_antes=request.form.get('declaro_renta_antes')=='1'
        db.session.commit()
        flash('Antecedente actualizado. El umbral de consignaciones no se altera automáticamente.','success')
    return redirect(url_for('contabilidad.index',_anchor='personas'))
