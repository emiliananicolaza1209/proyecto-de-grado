"""Consolidado contable (TRI-001/002/003) y alertas de consignaciones por año gravable.
Las alertas no son dictámenes tributarios."""
from sqlalchemy import func
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import csv
import io
import json
from app.models.contabilidad import (
    ConsignacionBancaria, BancoDestino, PersonaContable, ReporteGenerado, IngresoGasto, CorreccionClasificacion,
)
from app.models import Producto
from app.extensions import db

# Tope de consignaciones bancarias fijado por la DIAN en 1.400 UVT
# (Para vigencia actual aprox. $69.719.000 COP, ajustable según la resolución de la vigencia)
TOPE_UVT_CONSIGNACIONES = 1400
VALOR_UVT_REF = 49799  # O el valor correspondiente al año gravable
TOPE_LIMITE_COP = TOPE_UVT_CONSIGNACIONES * VALOR_UVT_REF # ~$69.718.600 (referencia; la alerta usa UVT_POR_ANIO)
UVT_POR_ANIO = {2025: 49799, 2026: 52374}

COLOMBIA = timezone(timedelta(hours=-5))
ACTOR_ANONIMO = 'Sesión local sin autenticación'
SIN_BANCO = 'Sin banco asociado'  # consignaciones sin banco destino (p. ej. datáfono)

TIPOS_MOVIMIENTO = ('INGRESO', 'GASTO')
CATEGORIAS_INGRESO_GASTO = ('VENTA', 'COMPRA', 'ARRIENDO', 'NOMINA', 'SERVICIOS',
                            'TRANSPORTE', 'COMISION', 'INTERES', 'IMPUESTO', 'OTRO')


def _today_co():
    return datetime.now(COLOMBIA).date().isoformat()


def _check_day(raw, label):
    try:
        value = datetime.strptime(raw, '%Y-%m-%d').date()
        if value.isoformat() != raw:
            raise ValueError()
        return raw
    except (TypeError, ValueError):
        raise ValueError(f'{label}: usa formato año-mes-día válido.')


def parse_period(ini=None, fin=None):
    """Rango por defecto: mes actual hasta hoy. Nunca futuro ni ini>fin."""
    today = _today_co()
    ini = (ini or '').strip() or today[:8] + '01'
    fin = (fin or '').strip() or today
    ini = _check_day(ini, 'Fecha inicial')
    fin = _check_day(fin, 'Fecha final')
    if ini > fin:
        raise ValueError('La fecha inicial no puede ser posterior a la final.')
    if fin > today:
        raise ValueError('La fecha final no puede estar en el futuro.')
    return ini, fin


def _cop_to_cents(raw, label='Valor'):
    try:
        value = Decimal(str(raw or '').strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f'{label}: ingresa un valor válido con máximo dos decimales.')
    if not value.is_finite() or not 0 < value <= 999999999 or value != value.quantize(Decimal('0.01')):
        raise ValueError(f'{label}: ingresa un valor entre $0.01 y $999.999.999 con máximo dos decimales.')
    return int(value * 100)


def registrar_ingreso_gasto(data, actor=ACTOR_ANONIMO):
    """HU-FIN-001/002: valida y guarda un ingreso o gasto. No toca ventas."""
    tipo = (data.get('tipo') or '').strip().upper()
    if tipo not in TIPOS_MOVIMIENTO:
        raise ValueError('Tipo: debe ser INGRESO o GASTO.')
    concepto = (data.get('concepto') or '').strip()
    if not 3 <= len(concepto) <= 120:
        raise ValueError('Concepto: entre 3 y 120 caracteres.')
    categoria = (data.get('categoria') or 'OTRO').strip().upper()
    if categoria not in CATEGORIAS_INGRESO_GASTO:
        raise ValueError('Categoría: selecciona una opción válida.')
    cents = _cop_to_cents(data.get('valor'), 'Valor')
    fecha = _check_day((data.get('fecha') or '').strip(), 'Fecha')
    if fecha > _today_co():
        raise ValueError('Fecha: no puede estar en el futuro.')
    relacion = (data.get('relacion') or '').strip()[:120]
    soporte = (data.get('soporte_ref') or '').strip()[:100]
    responsable = (data.get('responsable') or '').strip()[:120]
    row = IngresoGasto(tipo=tipo, concepto=concepto, categoria=categoria,
                       valor_cents=cents, fecha=fecha, relacion=relacion,
                       soporte_ref=soporte, responsable=responsable)
    db.session.add(row)
    db.session.commit()
    return row


def corregir_clasificacion(ig_id, nueva, motivo, actor=ACTOR_ANONIMO):
    """HU-TRI-003: solo cambia la categoría; el resto del documento no se toca."""
    row = db.session.get(IngresoGasto, ig_id)
    if row is None:
        raise ValueError('Registro no encontrado.')
    nueva = (nueva or '').strip().upper()
    if nueva not in CATEGORIAS_INGRESO_GASTO:
        raise ValueError('Categoría: selecciona una opción válida.')
    if nueva == row.categoria:
        raise ValueError('La categoría nueva debe ser diferente a la actual.')
    motivo = (motivo or '').strip()
    if not 3 <= len(motivo) <= 500:
        raise ValueError('Motivo: entre 3 y 500 caracteres.')
    anterior = row.categoria
    row.categoria = nueva
    db.session.add(CorreccionClasificacion(
        entidad='ingreso_gasto', entidad_id=row.id, anterior=anterior,
        nueva=nueva, motivo=motivo, actor=actor))
    db.session.commit()
    return row


def movimientos_periodo(ini, fin):
    return db.session.scalars(
        db.select(IngresoGasto)
        .where(IngresoGasto.fecha >= ini, IngresoGasto.fecha <= fin)
        .order_by(IngresoGasto.fecha, IngresoGasto.id)).all()


def ultimas_correcciones(limit=10):
    return db.session.scalars(
        db.select(CorreccionClasificacion)
        .order_by(CorreccionClasificacion.id.desc()).limit(limit)).all()


def _compra_fecha(p):
    if p.lot and p.lot.entry_date:
        return p.lot.entry_date[:10]
    return (p.created_at or '')[:10]


def consolidar_periodo(ini, fin):
    """HU-TRI-001: consolida compras, ventas, ingresos, gastos y consignaciones.

    Compras por fecha de lote (o creación si no tiene lote).
    Ventas por sale_date. Ingresos/gastos/consignaciones por su fecha.
    No determina impuestos (RN-TRI-001): solo prepara información.
    """
    ini, fin = parse_period(ini, fin)
    productos = db.session.scalars(db.select(Producto)).all()

    compras = {'total_cents': 0, 'count': 0, 'por_proveedor': {}, 'detalle': []}
    ventas = {'total_cents': 0, 'cobrado_cents': 0, 'saldo_cents': 0,
              'costo_cents': 0, 'utilidad_cents': 0, 'count': 0, 'detalle': []}
    faltantes = []

    for p in productos:
        if p.archived:
            continue
        cf = _compra_fecha(p)
        if ini <= cf <= fin:
            costo = p.cost_cents or 0
            compras['total_cents'] += costo
            compras['count'] += 1
            prov = p.supplier or 'SIN PROVEEDOR'
            agg = compras['por_proveedor'].setdefault(prov, {'total_cents': 0, 'count': 0})
            agg['total_cents'] += costo
            agg['count'] += 1
            compras['detalle'].append({
                'fecha': cf, 'tipo': 'COMPRA', 'detalle': f"{p.imei} · {p.model}",
                'fuente': p.lot.code if p.lot else 'Sin lote',
                'valor_cents': costo, 'responsable': p.supplier or '',
                'imei': p.imei, 'modelo': p.model, 'lote': p.lot.code if p.lot else 'Sin lote',
                'proveedor': prov,
            })
            if not p.lot_id:
                faltantes.append(f"Equipo {p.imei} sin lote asociado (costo incluido por fecha de creación).")
        if p.sale_date and ini <= p.sale_date[:10] <= fin and p.status == 'Vendido':
            venta = p.sale_value_cents or 0
            cobrado = p.paid_cents or 0
            costo = p.cost_cents or 0
            ventas['total_cents'] += venta
            ventas['cobrado_cents'] += cobrado
            ventas['saldo_cents'] += max(venta - cobrado, 0)
            ventas['costo_cents'] += costo
            ventas['utilidad_cents'] += venta - costo
            ventas['count'] += 1
            ventas['detalle'].append({
                'fecha': p.sale_date[:10], 'tipo': 'VENTA',
                'detalle': f"{p.imei} · {p.model}",
                'fuente': f"Vendedor: {p.seller or p.responsible or 'Sin dato'}",
                'fuente_export': 'Venta de inventario',  # exportaciones (CSV/paquete): sin nombres de personas (Ley 1581)
                'valor_cents': venta, 'responsable': p.seller or p.responsible or '',
                'imei': p.imei, 'modelo': p.model, 'costo_cents': costo,
                'cobrado_cents': cobrado, 'saldo_cents': max(venta - cobrado, 0),
            })
            if not venta:
                faltantes.append(f"Equipo {p.imei} vendido sin valor de venta registrado.")
            if p.payment_status == 'Parcial':
                faltantes.append(f"Venta {p.imei} con saldo pendiente: ${venta - cobrado:,} COP.")

    ingresos = {'total_cents': 0, 'count': 0, 'por_categoria': {}, 'detalle': []}
    gastos = {'total_cents': 0, 'count': 0, 'por_categoria': {}, 'detalle': []}
    for m in movimientos_periodo(ini, fin):
        bucket = ingresos if m.tipo == 'INGRESO' else gastos
        bucket['total_cents'] += m.valor_cents
        bucket['count'] += 1
        agg = bucket['por_categoria'].setdefault(m.categoria, {'total_cents': 0, 'count': 0})
        agg['total_cents'] += m.valor_cents
        agg['count'] += 1
        bucket['detalle'].append({
            'fecha': m.fecha, 'tipo': m.tipo,
            'detalle': f"{m.concepto} [{m.categoria}]",
            'fuente': m.relacion or 'Registro directo',
            'valor_cents': m.valor_cents, 'responsable': m.responsable or '',
            'concepto': m.concepto, 'categoria': m.categoria, 'relacion': m.relacion or '',
            'soporte_ref': m.soporte_ref or '',
        })
        if m.categoria == 'OTRO':
            faltantes.append(f"{m.tipo} '{m.concepto}' sin clasificar (categoría OTRO).")

    # Solo consignaciones activas: las anuladas no suman (igual que la alerta UVT y el desglose por banco).
    cons_q = db.session.query(ConsignacionBancaria).filter(
        ConsignacionBancaria.activa == True,  # noqa: E712
        func.date(ConsignacionBancaria.fecha) >= ini,
        func.date(ConsignacionBancaria.fecha) <= fin,
    ).order_by(ConsignacionBancaria.fecha).all()
    cons_total = sum(int(Decimal(str(c.monto)) * 100) for c in cons_q)
    consignaciones = {'total_cents': cons_total, 'count': len(cons_q), 'detalle': [
        {'fecha': c.fecha.date().isoformat() if hasattr(c.fecha, 'date') else str(c.fecha)[:10],
         'tipo': 'CONSIGNACION',
         'detalle': f"{c.destinatario.nombre if c.destinatario else '?'} → {c.banco.nombre if c.banco else SIN_BANCO}",
         'fuente': c.referencia or 'Sin referencia',
         'valor_cents': int(Decimal(str(c.monto)) * 100),
         'responsable': c.destinatario.nombre if c.destinatario else '',
         'persona': c.destinatario.nombre if c.destinatario else '?',
         'banco': c.banco.nombre if c.banco else SIN_BANCO, 'referencia': c.referencia or ''}
        for c in cons_q]}
    for c in cons_q:
        if not c.referencia:
            ident = c.destinatario.nombre if c.destinatario else f'#{c.id}'
            faltantes.append(f"Consignación de {ident} sin referencia de soporte.")

    return {
        'ini': ini, 'fin': fin,
        'compras': compras, 'ventas': ventas,
        'ingresos': ingresos, 'gastos': gastos,
        'consignaciones': consignaciones,
        'faltantes': sorted(set(faltantes)),
    }


def registrar_reporte(ini, fin, consolidado, actor=ACTOR_ANONIMO, formato=None):
    """HU-TRI-002: deja quién/cuándo generó el reporte y sus totales."""
    totales = {
        'compras_cents': consolidado['compras']['total_cents'],
        'ventas_cents': consolidado['ventas']['total_cents'],
        'utilidad_cents': consolidado['ventas']['utilidad_cents'],
        'ingresos_cents': consolidado['ingresos']['total_cents'],
        'gastos_cents': consolidado['gastos']['total_cents'],
        'consignaciones_cents': consolidado['consignaciones']['total_cents'],
    }
    if formato:
        totales['formato'] = formato  # csv | xlsx | pdf, sin columna nueva (no hay migración)
    rep = ReporteGenerado(fecha_ini=ini, fecha_fin=fin, actor=actor,
                          totales_json=json.dumps(totales, ensure_ascii=False))
    db.session.add(rep)
    db.session.commit()
    return rep


def ultimos_reportes(limit=5):
    return db.session.scalars(
        db.select(ReporteGenerado).order_by(ReporteGenerado.id.desc()).limit(limit)).all()


def generar_csv(consolidado, actor=ACTOR_ANONIMO):
    """CSV con BOM para Excel ES. Conserva periodo y advierte RN-TRI-001."""
    out = io.StringIO()
    out.write('\ufeff')
    w = csv.writer(out)
    w.writerow(['CP STORE', 'Consolidado contable-tributario (apoyo, no determina impuestos)'])
    w.writerow(['Periodo', consolidado['ini'], consolidado['fin']])
    w.writerow(['Generado', datetime.now(COLOMBIA).isoformat(timespec='seconds'), actor])
    w.writerow([])
    w.writerow(['Sección', 'Cantidad', 'Total COP'])
    w.writerow(['Compras', consolidado['compras']['count'], f"{consolidado['compras']['total_cents']/100:.2f}"])
    w.writerow(['Ventas', consolidado['ventas']['count'], f"{consolidado['ventas']['total_cents']/100:.2f}"])
    w.writerow(['Margen bruto de equipos (venta-costo)', '', f"{consolidado['ventas']['utilidad_cents']/100:.2f}"])
    w.writerow(['Ingresos adicionales', consolidado['ingresos']['count'], f"{consolidado['ingresos']['total_cents']/100:.2f}"])
    w.writerow(['Gastos', consolidado['gastos']['count'], f"{consolidado['gastos']['total_cents']/100:.2f}"])
    w.writerow(['Consignaciones', consolidado['consignaciones']['count'], f"{consolidado['consignaciones']['total_cents']/100:.2f}"])
    w.writerow([])
    w.writerow(['Fecha', 'Tipo', 'Detalle', 'Fuente', 'Valor COP'])  # sin Responsable: datos de personas innecesarios (Ley 1581)
    for section in ('compras', 'ventas', 'ingresos', 'gastos', 'consignaciones'):
        for r in consolidado[section]['detalle']:
            w.writerow([r['fecha'], r['tipo'], r['detalle'], r.get('fuente_export', r['fuente']),
                        f"{r['valor_cents']/100:.2f}"])
    w.writerow([])
    w.writerow(['Registros por revisar'])
    for f in consolidado['faltantes'] or ['Sin pendientes en el periodo.']:
        w.writerow([f])
    return out.getvalue()


def resumir_por_banco(personas, anio):
    """Distribución anual de las mismas consignaciones activas del total personal.

    Conserva bancos asociados sin ingresos y bancos con movimientos históricos,
    aunque ya no estén asociados. Los movimientos sin banco forman un grupo
    separado: no se les asigna un banco ni se excluyen del total.
    """
    grupos = {
        p.id: {
            link.banco_id: dict(banco_id=link.banco_id, nombre=link.banco.nombre,
                                total=Decimal('0.00'), cantidad=0)
            for link in p.bancos_asociados
        } for p in personas
    }
    if not grupos:
        return {}
    inicio, fin = datetime(anio, 1, 1), datetime(anio + 1, 1, 1)
    from ..models.finanzas import OperacionFinanciera as Op, PagoProveedor as Pago
    registros=db.session.execute(db.select(ConsignacionBancaria,BancoDestino.nombre,Op.payments,Pago.account)
        .outerjoin(BancoDestino,BancoDestino.id==ConsignacionBancaria.banco_id)
        .outerjoin(Op,Op.id==ConsignacionBancaria.finance_operation_id)
        .outerjoin(Pago,Pago.id==ConsignacionBancaria.supplier_payment_id)
        .where(ConsignacionBancaria.persona_id.in_(grupos),ConsignacionBancaria.activa==True,
               ConsignacionBancaria.fecha>=inicio,ConsignacionBancaria.fecha<fin))
    for c,nombre,payments,payment_account in registros:
        method=payment_account
        if payments is not None and c.payment_index is not None and 0<=c.payment_index<len(payments):method=payments[c.payment_index].get('account')
        dataphone=method=='DATÁFONO' or (nombre or '').upper() in ('DATÁFONO','DATAFONO')
        key=c.banco_id
        if dataphone:
            key=next((key for key,v in grupos[c.persona_id].items() if v['nombre'].upper() in ('DATÁFONO','DATAFONO')), 'datafono')
        entry=grupos[c.persona_id].setdefault(key,dict(banco_id=c.banco_id,nombre='Datáfono' if dataphone else nombre or 'Ingresos sin banco asociado',total=Decimal('0.00'),cantidad=0))
        entry['total']+=c.monto;entry['cantidad']+=1
    resultado = {}
    for persona_id, bancos in grupos.items():
        total = sum((b['total'] for b in bancos.values()), Decimal('0.00'))
        for b in bancos.values():
            b['porcentaje'] = ((b['total'] * 100 / total).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP) if total else Decimal('0.00'))
            b['ancho'] = min(Decimal(100), max(Decimal(0), b['porcentaje']))
        resultado[persona_id] = dict(total=total, bancos=sorted(
            bancos.values(), key=lambda b: (b['banco_id'] is None, -b['total'], b['nombre'].casefold())))
    return resultado


def evaluar_estado_renta(persona_id, anio=None):
    anio = anio or datetime.now(COLOMBIA).year
    uvt = UVT_POR_ANIO.get(anio)
    inicio=datetime(anio,1,1);fin=datetime(anio+1,1,1)
    total = db.session.scalar(db.select(func.sum(ConsignacionBancaria.monto)).where(
        ConsignacionBancaria.persona_id==persona_id,
        ConsignacionBancaria.activa==True,
        ConsignacionBancaria.fecha>=inicio,ConsignacionBancaria.fecha<fin)) or Decimal(0)
    limite = int((Decimal(TOPE_UVT_CONSIGNACIONES * uvt)).quantize(
        Decimal('1E3'),rounding=ROUND_HALF_UP)) if uvt else None
    porcentaje = min(round(float(total / Decimal(limite)*100),2),100) if limite else 0
    return dict(total_consignado=total,tope_limite=limite,
                supera_tope=total>limite if limite else False,
                porcentaje=porcentaje,porcentaje_uso=porcentaje,
                pendiente_uvt=not bool(uvt),anio=anio)


def alertas_uvt(ini, fin):
    """Alerta de 1.400 UVT para cada año que toca el periodo.

    El tope es anual: cuenta el año calendario completo (consignaciones activas), no solo el
    periodo elegido. Solo salen las personas con consignaciones en ese año. Reutiliza
    evaluar_estado_renta, la misma función que usa la pantalla Información contable.
    """
    ini, fin = parse_period(ini, fin)
    personas = db.session.scalars(db.select(PersonaContable).order_by(PersonaContable.nombre)).all()
    filas = []
    for anio in range(int(ini[:4]), int(fin[:4]) + 1):
        for persona in personas:
            estado = evaluar_estado_renta(persona.id, anio)
            total = Decimal(str(estado['total_consignado']))
            if not total:
                continue
            if estado['pendiente_uvt']:
                texto = 'UVT del año pendiente de configurar'
            elif estado['supera_tope']:
                texto = 'Supera el tope'
            else:
                texto = 'Dentro del umbral'
            filas.append({
                'anio': anio, 'persona': persona.nombre, 'identificacion': persona.identificacion,
                'tipo': persona.tipo, 'total_cents': int((total * 100).to_integral_value()),
                'tope_cop': estado['tope_limite'], 'porcentaje': estado['porcentaje'],
                'supera_tope': estado['supera_tope'], 'pendiente_uvt': estado['pendiente_uvt'],
                'estado': texto,
            })
    return filas


def datos_paquete(ini, fin):
    """Una sola fuente para pantalla, CSV, Excel y PDF: el consolidado y las alertas UVT."""
    ini, fin = parse_period(ini, fin)
    return {'ini': ini, 'fin': fin, 'consolidado': consolidar_periodo(ini, fin),
            'alertas_uvt': alertas_uvt(ini, fin)}
