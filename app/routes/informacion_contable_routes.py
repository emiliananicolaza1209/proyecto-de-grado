from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models.contabilidad import PersonaContable, BancoDestino, ConsignacionBancaria
from app.services.contabilidad_service import evaluar_estado_renta, TOPE_LIMITE_COP

# Definición del Blueprint con su prefijo
contabilidad_bp = Blueprint('contabilidad', __name__, url_prefix='/modulos/tributario')

@contabilidad_bp.route('/')
def index():
    personas = PersonaContable.query.all()
    bancos = BancoDestino.query.all()
    
    reporte_personal = []
    for p in personas:
        estado = evaluar_estado_renta(p.id)
        reporte_personal.append({
            "persona": p,
            "estado": estado
        })
        
    return render_template(
        'contabilidad/index.html', 
        reporte_personal=reporte_personal, 
        destinatarios=personas, # Pasamos esto para el selector del formulario
        bancos=bancos,
        tope_limite=TOPE_LIMITE_COP,
        active='tributario'  # Ilumina la opción en el sidebar
    )

@contabilidad_bp.route('/consignacion/nueva', methods=['POST'])
def registrar_consignacion():
    try:
        persona_id = request.form.get('persona_id')
        banco_id = request.form.get('banco_id')
        monto = float(request.form.get('monto'))
        referencia = request.form.get('referencia')
        
        nueva_cons = ConsignacionBancaria(
            persona_id=persona_id,
            banco_id=banco_id,
            monto=monto,
            referencia=referencia
        )
        db.session.add(nueva_cons)
        db.session.commit()
        
        flash("Consignación registrada exitosamente.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error al registrar la consignación: {str(e)}", "danger")
        
    return redirect(url_for('contabilidad.index'))

@contabilidad_bp.route('/crear-destinatario', methods=['POST'])
def crear_destinatario():
    nombre = request.form.get('nombre')
    identificacion = request.form.get('identificacion')
    tipo = request.form.get('tipo')
    
    if nombre and tipo and identificacion:
        try:
            nuevo = PersonaContable(nombre=nombre, identificacion=identificacion, tipo=tipo)
            db.session.add(nuevo)
            db.session.commit()
            flash('Destinatario registrado con éxito', 'success')
        except IntegrityError:
            db.session.rollback()
            flash(f'El número de identificación "{identificacion}" ya se encuentra registrado en el sistema.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Ocurrió un error inesperado: {str(e)}', 'danger')
    else:
        flash('Debe completar todos los campos obligatorios, incluyendo el tipo y la identificación.', 'warning')
        
    return redirect(url_for('contabilidad.index'))

@contabilidad_bp.route('/crear-banco', methods=['POST'])
def crear_banco():
    nombre_banco = request.form.get('nombre_banco')
    if nombre_banco:
        try:
            nuevo = BancoDestino(nombre=nombre_banco)
            db.session.add(nuevo)
            db.session.commit()
            flash('Banco registrado con éxito', 'success')
        except IntegrityError:
            db.session.rollback()
            flash('Este banco ya se encuentra registrado.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar el banco: {str(e)}', 'danger')
    else:
        flash('El nombre del banco es obligatorio.', 'warning')
        
    return redirect(url_for('contabilidad.index'))