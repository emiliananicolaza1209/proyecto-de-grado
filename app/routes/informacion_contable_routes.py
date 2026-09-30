from flask import Blueprint, render_template, request, redirect, url_for, flash, Response
from sqlalchemy.exc import IntegrityError
from decimal import Decimal, InvalidOperation
from app.extensions import db
from app.models.contabilidad import PersonaContable, BancoDestino, ConsignacionBancaria
from app.services.contabilidad_service import (
    evaluar_estado_renta, TOPE_LIMITE_COP, consolidar_periodo,
    generar_csv, registrar_reporte, ultimos_reportes, parse_period,
    registrar_ingreso_gasto, corregir_clasificacion, movimientos_periodo,
    ultimas_correcciones, CATEGORIAS_INGRESO_GASTO, ACTOR_ANONIMO,
)

ACTOR = ACTOR_ANONIMO

# Definición del Blueprint con su prefijo
contabilidad_bp = Blueprint('contabilidad', __name__, url_prefix='/modulos/tributario')


@contabilidad_bp.route('/', strict_slashes=False)
def index():
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
        consolidado=consolidado, ini=ini, fin=fin, error=error,
        movimientos=movimientos,
        correcciones=ultimas_correcciones(),
        categorias=CATEGORIAS_INGRESO_GASTO,
        reportes=ultimos_reportes(),
        active='tributario'  # Ilumina la opción en el sidebar
    )


@contabilidad_bp.get('/export.csv')
def exportar_csv():
    """HU-TRI-002: exporta el consolidado del periodo y registra quién/cuándo."""
    try:
        ini, fin = parse_period(request.args.get('ini'), request.args.get('fin'))
        consolidado = consolidar_periodo(ini, fin)
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('contabilidad.index'))
    registrar_reporte(ini, fin, consolidado, ACTOR)
    data = generar_csv(consolidado, ACTOR)
    return Response(
        data,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename=consolidado_{ini}_{fin}.csv'},
    )


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
        }, ACTOR)
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
                               request.form.get('motivo'), ACTOR)
        flash('Clasificación corregida y registrada en auditoría.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
    except Exception:
        db.session.rollback()
        flash('No fue posible corregir la clasificación.', 'danger')
    return redirect(url_for('contabilidad.index'))


def _monto_cop(raw):
    try:
        value = Decimal(str(raw or '').strip())
    except (InvalidOperation, ValueError):
        raise ValueError('Monto: ingresa un valor válido con máximo dos decimales.')
    if not value.is_finite() or not 0 < value <= 999999999 or value != value.quantize(Decimal('0.01')):
        raise ValueError('Monto: ingresa un valor entre $0.01 y $999.999.999 con máximo dos decimales.')
    return value


@contabilidad_bp.route('/consignacion/nueva', methods=['POST'])
def registrar_consignacion():
    try:
        try:
            persona = db.session.get(PersonaContable, int(request.form.get('persona_id') or 0))
            banco = db.session.get(BancoDestino, int(request.form.get('banco_id') or 0))
        except (ValueError, TypeError):
            persona, banco = None, None
        if persona is None or banco is None:
            raise ValueError('Selecciona un destinatario y un banco válidos.')
        monto = _monto_cop(request.form.get('monto'))
        referencia = (request.form.get('referencia') or '').strip()[:100]

        nueva_cons = ConsignacionBancaria(
            persona_id=persona.id,
            banco_id=banco.id,
            monto=monto,
            referencia=referencia or None,
        )
        db.session.add(nueva_cons)
        db.session.commit()

        flash("Consignación registrada exitosamente.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    except Exception:
        db.session.rollback()
        flash("No fue posible registrar la consignación. Revisa los datos e intenta de nuevo.", "danger")

    return redirect(url_for('contabilidad.index'))

@contabilidad_bp.route('/crear-destinatario', methods=['POST'])
def crear_destinatario():
    nombre = (request.form.get('nombre') or '').strip()
    identificacion = (request.form.get('identificacion') or '').strip()
    tipo = request.form.get('tipo')

    if nombre and tipo and identificacion:
        if not 2 <= len(nombre) <= 120 or not 2 <= len(identificacion) <= 20:
            flash('Nombre e identificación deben tener entre 2 y 120 / 20 caracteres.', 'warning')
            return redirect(url_for('contabilidad.index'))
        try:
            nuevo = PersonaContable(nombre=nombre, identificacion=identificacion, tipo=tipo)
            db.session.add(nuevo)
            db.session.commit()
            flash('Destinatario registrado con éxito', 'success')
        except IntegrityError:
            db.session.rollback()
            flash(f'El número de identificación "{identificacion}" ya se encuentra registrado en el sistema.', 'danger')
        except Exception:
            db.session.rollback()
            flash('Ocurrió un error inesperado al crear el destinatario.', 'danger')
    else:
        flash('Debe completar todos los campos obligatorios, incluyendo el tipo y la identificación.', 'warning')

    return redirect(url_for('contabilidad.index'))

@contabilidad_bp.route('/crear-banco', methods=['POST'])
def crear_banco():
    nombre_banco = (request.form.get('nombre_banco') or '').strip()
    if nombre_banco:
        if not 2 <= len(nombre_banco) <= 60:
            flash('El nombre del banco debe tener entre 2 y 60 caracteres.', 'warning')
            return redirect(url_for('contabilidad.index'))
        try:
            nuevo = BancoDestino(nombre=nombre_banco)
            db.session.add(nuevo)
            db.session.commit()
            flash('Banco registrado con éxito', 'success')
        except IntegrityError:
            db.session.rollback()
            flash('Este banco ya se encuentra registrado.', 'danger')
        except Exception:
            db.session.rollback()
            flash('No fue posible registrar el banco.', 'danger')
    else:
        flash('El nombre del banco es obligatorio.', 'warning')

    return redirect(url_for('contabilidad.index'))
