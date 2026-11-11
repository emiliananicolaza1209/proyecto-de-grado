"""Consultas de solo lectura para el chatbot, los reportes y la analítica.

Contrato común (PDF de entrega, 9-nov-2026): fechas inclusivas, zona comercial de Bogotá (UTC-5), importes en
centavos de COP, fuentes, advertencias y cobertura. Toda respuesta distingue cinco estados:

* ``ok``               datos completos para lo pedido (un 0 real es una cifra válida).
* ``sin_datos``        no existe la fuente para responder; las cifras son ``None``, nunca 0.
* ``parcial``          hay datos pero faltan partes (días sin jornada, abiertas, pendientes); lo no calculable es ``None``.
* ``sin_autorizacion`` el perfil no puede usar la consulta; no se devuelven cifras ni se confirma si hay datos.
* ``error_temporal``   falló la base de datos de forma recuperable; se puede reintentar.

Un parámetro mal formado no es un estado: lanza :class:`ParametroInvalido` (la capa de rutas lo convierte en 400).

Este módulo no usa ``request`` ni ``session`` (recibe el perfil como texto), no escribe y no llama a ``open_day``.
Las cifras las calcula la aplicación; un modelo de lenguaje, si se usa, solo redacta (``redactar_respuesta``).
"""
import functools
import statistics
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.exc import DBAPIError, OperationalError, TimeoutError as SATimeoutError

from ..extensions import db
from . import finanzas_service
from ..models import Catalogo, Producto
from ..models.finanzas import Jornada, OperacionFinanciera as Op
from ..models.gestion import AliadoCredito, CreditoVenta
from .contabilidad_service import _compra_fecha  # misma regla de "fecha de ingreso" que el consolidado: fecha del lote o, sin lote, de creación
from .operacion_service import today

ZONA = 'America/Bogota (UTC-5)'
ESTADOS = ('ok', 'sin_datos', 'parcial', 'sin_autorizacion', 'error_temporal')

# --- Reglas por defecto: constantes fáciles de cambiar --------------------------------------------------------------
# Quién puede usar cada consulta. El chat arranca habilitado solo para el Propietario mientras Emily valida la matriz.
ROLES_CONSULTAS = {
    'estado_inventario': ('Propietario',),
    'creditos_pendientes': ('Propietario',),
    'resumen_ventas': ('Propietario',),
    'resumen_financiero': ('Propietario',),
    'comparar_periodos': ('Propietario',),
    'permanencia_inventario': ('Propietario',),
}
# Quién ve el costo inmovilizado del inventario (la matriz actual del código también se lo da a Inventario: no se traslada).
ROLES_CON_COSTO = ('Propietario',)
# Créditos que cuentan como saldo pendiente. Los 'Anulado' y 'Pagado' nunca cuentan.
ESTADOS_CREDITO_PENDIENTE = ('Pendiente', 'Parcial')
# Jornadas abiertas: True = se incluyen como "provisional", separadas del definitivo (cerradas); False = se excluyen y
# cuentan como cobertura incompleta.
JORNADAS_ABIERTAS_COMO_PROVISIONAL = True
# resumen_financiero: solo estos totales de Finanzas son flujos sumables entre días. Nunca se suman bases de caja ni saldos
# (control_total, control_cash, cash_expected, banks, funds, opening...). Se pueden cambiar sin tocar la lógica.
FLUJOS_SUMABLES = ('gross', 'sales_count', 'debe', 'haber', 'service', 'liquidation', 'result', 'commission', 'profit',
                   'owner_result')
ETIQUETAS_FLUJOS = {
    'gross': 'Ventas netas', 'sales_count': 'Ventas registradas', 'debe': 'DEBE (margen antes de costos menores)',
    'haber': 'HABER (costos menores)', 'service': 'Servicios', 'liquidation': 'Liquidación del día',
    'result': 'Resultado antes de comisiones', 'commission': 'Comisiones', 'profit': 'Resultado después de comisiones',
    'owner_result': 'Resultado final del día',
}
# True: con jornadas abiertas (resultado provisional) la respuesta es "parcial", aunque la cobertura esté completa.
ABIERTAS_DEGRADAN_A_PARCIAL = True
# permanencia_inventario: a partir de cuántos días en inventario un equipo disponible se considera de baja rotación (se puede
# cambiar aquí o pasar otro valor en cada consulta), tope aceptado, y cuántos equipos se listan como máximo.
UMBRAL_PERMANENCIA_DIAS = 60
MAX_UMBRAL_DIAS = 3650
MAX_EQUIPOS_LISTADOS = 200
RANGOS_PERMANENCIA = ((0, 30, '0 a 30 días'), (31, 60, '31 a 60 días'), (61, 90, '61 a 90 días'), (91, 180, '91 a 180 días'),
                      (181, None, 'más de 180 días'))
# Largo máximo de un periodo, en días (evita consultas que recorran años enteros desde el chat).
MAX_DIAS_PERIODO = 366
# Cuántas fechas sin jornada se listan en la respuesta (el total siempre se informa completo).
MAX_FECHAS_LISTADAS = 60
# Clave de CreditoVenta.condiciones que marcaría un crédito como NO aprobado. Hoy la aprobación se exige al registrar la venta
# (credito_service.credit_payment) pero no se guarda como dato: sin la clave, el crédito se considera aprobado.
CLAVE_APROBACION = 'aprobado'
# estado_inventario nunca devuelve IMEI: la pregunta se responde con conteos por ubicación y referencia.


class ParametroInvalido(ValueError):
    """Entrada mal formada o inexistente (fecha inválida, ID que no corresponde)."""


def respuesta(consulta, estado, *, mensaje='', periodo=None, fuentes=(), metodo='', cobertura=None,
              advertencias=(), cifras=None, detalle=None):
    if estado not in ESTADOS:
        raise ValueError(f'Estado desconocido: {estado}')
    return {'consulta': consulta, 'estado': estado, 'mensaje': mensaje, 'periodo': periodo, 'zona': ZONA,
            'fuentes': list(fuentes), 'metodo': metodo, 'cobertura': cobertura, 'advertencias': list(advertencias),
            'cifras': cifras, 'detalle': detalle, 'es_estimacion': False, 'generado_en': today()}


def consulta(nombre, metodo=''):
    """Aplica autorización (antes de leer nada) y convierte los fallos temporales de la base en un estado.

    ``metodo`` se repite en las respuestas de sin_autorizacion y error_temporal (no lleva cifras) para que ciertas consultas
    puedan decir siempre qué son, por ejemplo "esto es una comparación, no una predicción"."""
    def decorador(funcion):
        @functools.wraps(funcion)
        def envuelta(rol, *args, **kwargs):
            if rol not in ROLES_CONSULTAS.get(nombre, ()):
                return respuesta(nombre, 'sin_autorizacion', mensaje='Tu perfil no puede usar esta consulta.', metodo=metodo)
            try:
                return funcion(rol, *args, **kwargs)
            except (OperationalError, SATimeoutError, DBAPIError):
                db.session.rollback()
                return respuesta(nombre, 'error_temporal', metodo=metodo,
                                 mensaje='No se pudo leer la información en este momento. Intenta de nuevo en unos segundos.')
        return envuelta
    return decorador


def _id_catalogo(valor, tipo, etiqueta):
    """Valida un filtro por ID de catálogo: entero positivo que exista y sea del tipo pedido."""
    if valor in (None, ''):
        return None
    try:
        numero = int(str(valor).strip())
    except ValueError:
        raise ParametroInvalido(f'{etiqueta}: el filtro debe ser un ID numérico.')
    item = db.session.get(Catalogo, numero) if numero > 0 else None
    if item is None or item.kind != tipo:
        raise ParametroInvalido(f'{etiqueta}: no existe ese ID.')
    return numero


def _nombre_ubicacion(p):
    return p.location_item.name if p.location_item else (p.location or None)


def _nombre_referencia(p):
    return p.reference_item.display_name if p.reference_item else (p.model or None)


# --- estado_inventario ----------------------------------------------------------------------------------------------
def _hay_equipos():
    return db.session.scalar(db.select(Producto.id).where(Producto.archived == 0).limit(1)) is not None


def _leer_disponibles(ubicacion_id, referencia_id):
    q = db.select(Producto).where(Producto.archived == 0, Producto.status == 'Disponible')
    if ubicacion_id:
        q = q.where(Producto.location_id == ubicacion_id)
    if referencia_id:
        q = q.where(Producto.reference_id == referencia_id)
    return db.session.scalars(q).all()


@consulta('estado_inventario')
def estado_inventario(rol, ubicacion_id=None, referencia_id=None):
    """Equipos disponibles hoy (no archivados), por ubicación y referencia. Describe el estado actual, no el histórico."""
    fuentes = ['Producto (tabla equipment): status = Disponible y archived = 0 — misma definición de disponible que '
               'inventario_service.stats() y el Resumen', 'Catalogo: nombres de ubicación y referencia']
    metodo = 'Conteo directo de equipos disponibles al momento de la consulta; sin estimaciones.'
    ubicacion_id = _id_catalogo(ubicacion_id, 'location', 'Ubicación')
    referencia_id = _id_catalogo(referencia_id, 'reference', 'Referencia')
    periodo = {'fecha_corte': today(), 'nota': 'Foto del inventario actual; no hay inventario histórico.'}
    if not _hay_equipos():
        return respuesta('estado_inventario', 'sin_datos', mensaje='No hay equipos registrados en el inventario.',
                         periodo=periodo, fuentes=fuentes, metodo=metodo)

    equipos = _leer_disponibles(ubicacion_id, referencia_id)
    ver_costo = rol in ROLES_CON_COSTO
    advertencias, por_ubicacion, por_referencia = [], {}, {}
    sin_clasificar = 0
    for p in equipos:
        u = (p.location_id, _nombre_ubicacion(p) if p.location_id else None)
        r = (p.reference_id, _nombre_referencia(p) if p.reference_id else None)
        if u[1] is None or r[1] is None:
            sin_clasificar += 1
        for tabla, clave in ((por_ubicacion, u), (por_referencia, r)):
            fila = tabla.setdefault(clave, {'disponibles': 0, 'costo': 0})
            fila['disponibles'] += 1
            fila['costo'] += p.cost_cents

    def salida(tabla, idc, nombre, vacio):
        filas = []
        for (ident, texto), v in sorted(tabla.items(), key=lambda kv: (-kv[1]['disponibles'], str(kv[0][1]))):
            fila = {idc: ident, nombre: texto or vacio, 'disponibles': v['disponibles']}
            if ver_costo:
                fila['costo_inmovilizado_cents'] = v['costo']
            filas.append(fila)
        return filas

    cifras = {'disponibles': len(equipos), 'retomas_pool': sum(1 for p in equipos if p.source_type == 'Retoma')}
    if ver_costo:
        cifras['costo_inmovilizado_cents'] = sum(p.cost_cents for p in equipos)
    detalle = {'por_ubicacion': salida(por_ubicacion, 'ubicacion_id', 'ubicacion', 'Sin ubicación'),
               'por_referencia': salida(por_referencia, 'referencia_id', 'referencia', 'Sin referencia')}
    filtros = {k: v for k, v in (('ubicacion_id', ubicacion_id), ('referencia_id', referencia_id)) if v}
    if filtros:
        periodo['filtros'] = filtros
        if not equipos:
            advertencias.append('Ningún equipo disponible coincide con el filtro pedido.')
    estado = 'ok'
    if sin_clasificar:
        estado = 'parcial'
        advertencias.append(f'{sin_clasificar} equipo(s) disponible(s) no tienen ubicación o referencia del catálogo; '
                            'se agrupan como "Sin ubicación" o "Sin referencia".')
    return respuesta('estado_inventario', estado, periodo=periodo, fuentes=fuentes, metodo=metodo,
                     cobertura={'completa': estado == 'ok', 'equipos_sin_clasificar': sin_clasificar},
                     advertencias=advertencias, cifras=cifras, detalle=detalle)


# --- creditos_pendientes --------------------------------------------------------------------------------------------
def _aprobado(credito):
    return (credito.condiciones or {}).get(CLAVE_APROBACION, True) is not False


def _filtro_aliado(aliado_id):
    if aliado_id in (None, ''):
        return None
    try:
        numero = int(str(aliado_id).strip())
    except ValueError:
        raise ParametroInvalido('Aliado: el filtro debe ser un ID numérico.')
    if numero <= 0 or db.session.get(AliadoCredito, numero) is None:
        raise ParametroInvalido('Aliado: no existe ese ID.')
    return numero


def _leer_creditos(aliado_id):
    q = db.select(CreditoVenta, AliadoCredito, Op.voided).join(AliadoCredito, AliadoCredito.id == CreditoVenta.aliado_id) \
        .join(Op, Op.id == CreditoVenta.operacion_id)
    if aliado_id:
        q = q.where(CreditoVenta.aliado_id == aliado_id)
    return db.session.execute(q).all()


@consulta('creditos_pendientes')
def creditos_pendientes(rol, aliado_id=None):
    """Saldo actual por aliado de crédito: neto - recibido. Sin mora, sin reconstrucción histórica, sin datos de clientes."""
    fuentes = ['CreditoVenta (creditos_venta): neto, recibido y estado', 'AliadoCredito (aliados_credito): nombre del aliado',
               'OperacionFinanciera (finance_operation): solo operaciones no anuladas',
               'credito_service.settle: el desembolso suma a recibido y fija el estado Parcial o Pagado']
    metodo = ('Saldo = neto - recibido de cada crédito pendiente (estado Pendiente o Parcial), de operaciones no anuladas, '
              'sumado por aliado. El desembolso no se cuenta otra vez como venta ni utilidad. Saldo actual: no hay vencimiento '
              'en los datos, por eso no se afirma mora ni se reconstruye el pasado.')
    periodo = {'fecha_corte': today(), 'nota': 'Saldo actual; no es histórico.'}
    aliado_id = _filtro_aliado(aliado_id)
    if aliado_id:
        periodo['filtros'] = {'aliado_id': aliado_id}
    if db.session.scalar(db.select(CreditoVenta.id).limit(1)) is None:
        return respuesta('creditos_pendientes', 'sin_datos', mensaje='No hay créditos registrados.', periodo=periodo,
                         fuentes=fuentes, metodo=metodo)

    grupos = {}
    sin_aprobar = {'creditos': 0, 'neto_cents': 0, 'recibido_cents': 0, 'saldo_cents': 0}
    excluidos = {'anulados': 0, 'operacion_anulada': 0, 'pagados': 0}
    inconsistentes = 0
    for credito, aliado, op_anulada in _leer_creditos(aliado_id):
        if credito.estado == 'Anulado':
            excluidos['anulados'] += 1
            continue
        if op_anulada:
            excluidos['operacion_anulada'] += 1
            continue
        if credito.estado not in ESTADOS_CREDITO_PENDIENTE:
            excluidos['pagados'] += 1
            continue
        saldo = credito.neto - credito.recibido
        if not _aprobado(credito):  # aparte y fuera del saldo
            if saldo > 0:
                sin_aprobar['creditos'] += 1
                sin_aprobar['neto_cents'] += credito.neto
                sin_aprobar['recibido_cents'] += credito.recibido
                sin_aprobar['saldo_cents'] += saldo
            continue
        g = grupos.setdefault(aliado.id, {'aliado_id': aliado.id, 'aliado': aliado.nombre, 'creditos': 0, 'bruto_cents': 0,
                                          'costo_cents': 0, 'neto_cents': 0, 'recibido_cents': 0, 'saldo_cents': 0,
                                          'calculable': True})
        if saldo < 0:  # recibido mayor que el neto: dato inconsistente, no se inventa un saldo
            g['calculable'] = False
            inconsistentes += 1
            continue
        if saldo == 0:  # estado pendiente pero sin saldo: no es un crédito pendiente
            inconsistentes += 1
            continue
        g['creditos'] += 1
        for clave, valor in (('bruto_cents', credito.bruto), ('costo_cents', credito.costo), ('neto_cents', credito.neto),
                             ('recibido_cents', credito.recibido), ('saldo_cents', saldo)):
            g[clave] += valor

    filas = []
    for g in sorted(grupos.values(), key=lambda x: (-x['saldo_cents'], x['aliado'])):
        if g['calculable'] and g['creditos'] == 0:
            continue
        if not g['calculable']:
            for clave in ('bruto_cents', 'costo_cents', 'neto_cents', 'recibido_cents', 'saldo_cents'):
                g[clave] = None
        g.pop('calculable')
        filas.append(g)
    advertencias = []
    if inconsistentes:
        advertencias.append(f'{inconsistentes} crédito(s) con estado pendiente tienen un saldo inconsistente (cero o negativo); '
                            'su saldo no se calcula y requiere revisión.')
    if sin_aprobar['creditos']:
        advertencias.append(f'{sin_aprobar["creditos"]} crédito(s) sin aprobación confirmada se informan aparte y no suman al saldo.')
    if aliado_id and not filas and not inconsistentes and not sin_aprobar['creditos']:
        advertencias.append('El aliado pedido no tiene créditos pendientes.')

    parcial = bool(inconsistentes or sin_aprobar['creditos'])
    calculable = all(f['saldo_cents'] is not None for f in filas)

    def suma(clave):
        return sum(f[clave] for f in filas) if calculable else None
    cifras = {'saldo_cents': suma('saldo_cents'), 'creditos_pendientes': sum(f['creditos'] for f in filas),
              'aliados_con_saldo': len(filas), 'bruto_cents': suma('bruto_cents'), 'costo_cents': suma('costo_cents'),
              'neto_cents': suma('neto_cents'), 'recibido_cents': suma('recibido_cents')}
    return respuesta('creditos_pendientes', 'parcial' if parcial else 'ok', periodo=periodo, fuentes=fuentes, metodo=metodo,
                     cobertura={'completa': not parcial, 'excluidos': excluidos, 'inconsistentes': inconsistentes,
                                'sin_aprobacion': sin_aprobar['creditos']},
                     advertencias=advertencias, cifras=cifras, detalle={'por_aliado': filas, 'sin_aprobacion': sin_aprobar})


# --- periodos y jornadas (compartido por resumen_ventas y resumen_financiero) --------------------------------------------
def _dia(valor, etiqueta):
    try:
        return date.fromisoformat(str(valor).strip()).isoformat()
    except (ValueError, TypeError):
        raise ParametroInvalido(f'{etiqueta}: usa el formato AAAA-MM-DD.')


def _periodo(ini, fin):
    """Fechas inclusivas. Un fin futuro se recorta a hoy (con aviso); un periodo entero en el futuro o demasiado largo se rechaza."""
    hoy = today()
    ini, fin = _dia(ini, 'Fecha inicial'), _dia(fin, 'Fecha final')
    if ini > fin:
        raise ParametroInvalido('La fecha inicial no puede ser posterior a la final.')
    if ini > hoy:
        raise ParametroInvalido('El periodo está completamente en el futuro.')
    avisos = []
    if fin > hoy:
        avisos.append(f'La fecha final {fin} es futura; se consultó hasta hoy ({hoy}).')
        fin = hoy
    if (date.fromisoformat(fin) - date.fromisoformat(ini)).days + 1 > MAX_DIAS_PERIODO:
        raise ParametroInvalido(f'El periodo no puede superar {MAX_DIAS_PERIODO} días.')
    return ini, fin, avisos


def _fechas(ini, fin):
    d, ultimo = date.fromisoformat(ini), date.fromisoformat(fin)
    while d <= ultimo:
        yield d.isoformat()
        d += timedelta(days=1)


def _leer_jornadas(ini, fin):
    return db.session.scalars(db.select(Jornada).where(Jornada.date >= ini, Jornada.date <= fin).order_by(Jornada.date)).all()


# --- resumen_ventas -------------------------------------------------------------------------------------------------
def _leer_operaciones_venta(ini, fin):
    q = db.select(Op, Jornada.date).join(Jornada, Jornada.id == Op.day_id) \
        .where(Op.kind == 'Venta', Op.voided == False, Jornada.date >= ini, Jornada.date <= fin)  # noqa: E712
    return db.session.execute(q).all()


def _equipos_por_incorporar(ini, fin):
    """Equipos vendidos en el periodo (Ventas y pagos) que no tienen operación en Finanzas: no están en la venta neta."""
    vendidos = db.session.scalars(db.select(Producto).where(
        Producto.archived == 0, Producto.status.in_(('Vendido', 'Garantía')), Producto.sale_date.is_not(None))).all()
    en_periodo = [p for p in vendidos if ini <= p.sale_date[:10] <= fin]
    if not en_periodo:
        return []
    con_operacion = set(db.session.scalars(db.select(Op.product_id).where(Op.product_id.is_not(None))).all())
    return [p for p in en_periodo if p.id not in con_operacion]


@consulta('resumen_ventas')
def resumen_ventas(rol, ini, fin):
    """Venta neta incorporada a Finanzas en el periodo: operaciones Venta no anuladas, por fecha de jornada.

    La venta, el cobro y la recepción son eventos distintos: aquí solo la venta (sin cobrado ni saldo)."""
    fuentes = ['OperacionFinanciera (finance_operation): kind = Venta y voided = False, por fecha de la jornada (Jornada.date)',
               'Jornada cerrada: snapshot[totals][gross] y [sales_count], los mismos de la pantalla de Finanzas',
               'Producto (equipment): equipos Vendido o en Garantía sin operación en Finanzas, solo como aviso']
    metodo = ('Venta neta = suma de Operacion.amount (ya descuenta el recargo de datáfono y la comisión del aliado). Equipos = '
              'operaciones con equipo propio del inventario; complementarias = el resto (accesorios, servicios, equipos de '
              'proveedores externos). Jornada cerrada: se usa su snapshot. Jornada abierta: provisional, separada del definitivo. '
              'No incluye cobros ni recepciones ni créditos desembolsados.')
    ini, fin, avisos = _periodo(ini, fin)
    periodo = {'ini': ini, 'fin': fin, 'inclusivo': True}
    por_incorporar_lista = _equipos_por_incorporar(ini, fin)
    por_incorporar = {'equipos': len(por_incorporar_lista), 'venta_neta_cents': sum(p.sale_value_cents or 0 for p in por_incorporar_lista)}

    jornadas = {j.date: j for j in _leer_jornadas(ini, fin)}
    if not jornadas and not por_incorporar_lista:
        return respuesta('resumen_ventas', 'sin_datos', mensaje='No hay jornadas de Finanzas en el periodo pedido.', periodo=periodo,
                         fuentes=fuentes, metodo=metodo, advertencias=avisos)

    cerradas = {d for d, j in jornadas.items() if j.status == 'Cerrada'}
    abiertas = {d for d, j in jornadas.items() if j.status != 'Cerrada'}
    excluidas = abiertas if not JORNADAS_ABIERTAS_COMO_PROVISIONAL else set()
    contadas = set(jornadas) - excluidas
    operaciones = [(op, dia) for op, dia in _leer_operaciones_venta(ini, fin) if dia in contadas]

    def vacio():
        return {'operaciones': 0, 'venta_neta_cents': 0}
    definitivo, provisional, equipos, complementarias = vacio(), vacio(), vacio(), vacio()
    suma_ops = {}
    for op, dia in operaciones:
        suma_ops.setdefault(dia, [0, 0])
        suma_ops[dia][0] += 1
        suma_ops[dia][1] += op.amount
        bloque = equipos if op.product_id else complementarias
        bloque['operaciones'] += 1
        bloque['venta_neta_cents'] += op.amount

    sin_cierre, no_cuadra = [], []
    for dia in sorted(contadas):
        if dia in cerradas:
            totales = ((jornadas[dia].snapshot or {}).get('totals') or {})
            if totales.get('gross') is None or totales.get('sales_count') is None:
                sin_cierre.append(dia)
                continue
            n, monto = totales['sales_count'], totales['gross']
            if [n, monto] != suma_ops.get(dia, [0, 0]):
                no_cuadra.append(dia)
            definitivo['operaciones'] += n
            definitivo['venta_neta_cents'] += monto
        else:
            n, monto = suma_ops.get(dia, [0, 0])
            provisional['operaciones'] += n
            provisional['venta_neta_cents'] += monto

    sin_jornada = [d for d in _fechas(ini, fin) if d not in contadas]
    advertencias = list(avisos)
    if sin_jornada:
        advertencias.append(f'{len(sin_jornada)} día(s) del periodo no tienen jornada de Finanzas o no se cuentan: cobertura incompleta, '
                            'no significa cero ventas.')
    if abiertas and JORNADAS_ABIERTAS_COMO_PROVISIONAL:
        advertencias.append(f'{len(abiertas)} jornada(s) abierta(s): sus ventas son provisionales y se informan aparte del definitivo.')
    if por_incorporar_lista:
        advertencias.append(f'{por_incorporar["equipos"]} equipo(s) vendido(s) en Ventas y pagos no están incorporados a Finanzas '
                            f'(${por_incorporar["venta_neta_cents"] // 100:,} COP); no están en la venta neta.')
    if sin_cierre:
        advertencias.append('El snapshot de cierre no trae la venta neta de: ' + ', '.join(sin_cierre) + '; no se calcula.')
    if no_cuadra:
        advertencias.append('El cierre de ' + ', '.join(no_cuadra) + ' no coincide con sus operaciones actuales; se usa el cierre.')

    cobertura = {'completa': not (sin_jornada or por_incorporar_lista or sin_cierre or no_cuadra),
                 'dias_periodo': len(list(_fechas(ini, fin))), 'con_jornada': len(jornadas), 'cerradas': len(cerradas),
                 'abiertas': len(abiertas), 'sin_jornada_total': len(sin_jornada),
                 'sin_jornada': sin_jornada[:MAX_FECHAS_LISTADAS], 'equipos_por_incorporar': len(por_incorporar_lista)}
    if not contadas or sin_cierre:
        # sin ninguna jornada contable, o con un cierre sin dato: no se inventa un 0
        cifras = {'operaciones': None, 'venta_neta_cents': None, 'definitivo': None if sin_cierre else definitivo,
                  'provisional': provisional, 'equipos': None, 'complementarias': None, 'por_incorporar': por_incorporar}
    else:
        cifras = {'operaciones': definitivo['operaciones'] + provisional['operaciones'],
                  'venta_neta_cents': definitivo['venta_neta_cents'] + provisional['venta_neta_cents'],
                  'definitivo': definitivo, 'provisional': provisional, 'equipos': equipos, 'complementarias': complementarias,
                  'por_incorporar': por_incorporar}
    estado = 'ok' if cobertura['completa'] else 'parcial'
    return respuesta('resumen_ventas', estado, periodo=periodo, fuentes=fuentes, metodo=metodo, cobertura=cobertura,
                     advertencias=advertencias, cifras=cifras)


# --- resumen_financiero ---------------------------------------------------------------------------------------------
def _totales_de_jornada(jornada):
    """Cerrada: el snapshot guardado al cerrar. Abierta: el reporte actual de Finanzas (que usa calculate). Nunca open_day."""
    if jornada.status == 'Cerrada':
        return 'snapshot', ((jornada.snapshot or {}).get('totals') or {})
    return 'report', finanzas_service.report(jornada)['totals']


def _leer_totales(jornadas):
    return [(j, *_totales_de_jornada(j)) for j in jornadas]


def _valor(totales, clave):
    v = totales.get(clave)
    return v if isinstance(v, int) and not isinstance(v, bool) else None  # falta, null o dato no numérico


def _bucket(filas):
    """Suma por flujo de las jornadas de un grupo. Si un día no trae la cifra, esa cifra del total es None."""
    sin_dato = {}
    suma = {}
    for clave in FLUJOS_SUMABLES:
        valores = [(f['fecha'], f[clave]) for f in filas]
        faltantes = [fecha for fecha, v in valores if v is None]
        if faltantes:
            sin_dato[clave] = faltantes
        suma[clave] = None if (faltantes or not filas) else sum(v for _, v in valores)
    return {'jornadas': len(filas), **suma}, sin_dato


@consulta('resumen_financiero')
def resumen_financiero(rol, ini, fin):
    """Resultado de las jornadas de Finanzas en el periodo: definitivo (cerradas) separado de provisional (abiertas)."""
    fuentes = ['Jornada (finance_day): fecha y estado', 'Jornada cerrada: snapshot[totals], guardado al cerrar el día',
               'Jornada abierta: finanzas_service.report(jornada), que calcula con finanzas_service.calculate',
               'No usa consignaciones, saldos de caja ni open_day']
    metodo = ('Suma, día por día, los flujos que Finanzas ya calcula: ' + ', '.join(FLUJOS_SUMABLES) + '. No se suman bases de caja '
              'ni saldos (control_total, cash_expected, banks). Jornada cerrada: snapshot (definitivo). Jornada abierta: reporte '
              'actual (provisional), siempre separado del definitivo. Un día sin jornada es cobertura incompleta, no cero. '
              '"Resultado final del día" (owner_result) es la utilidad después de comisiones y gastos PD; NO es lo mismo que el '
              '"Margen bruto de equipos" de Información contable (venta neta menos costo del equipo, sin sueldos ni gastos): el '
              'resultado del día descuenta liquidación, servicios y comisiones y suma la ganancia de compras POOL, por lo que '
              'ambas cifras difieren por definición.')
    ini, fin, avisos = _periodo(ini, fin)
    periodo = {'ini': ini, 'fin': fin, 'inclusivo': True}
    jornadas = _leer_jornadas(ini, fin)
    if not jornadas:
        return respuesta('resumen_financiero', 'sin_datos', mensaje='No hay jornadas de Finanzas en el periodo pedido.',
                         periodo=periodo, fuentes=fuentes, metodo=metodo, advertencias=avisos)

    cerradas = [j for j in jornadas if j.status == 'Cerrada']
    abiertas = [j for j in jornadas if j.status != 'Cerrada']
    contadas = cerradas + (abiertas if JORNADAS_ABIERTAS_COMO_PROVISIONAL else [])
    por_jornada = []
    for j, fuente, totales in _leer_totales(contadas):
        fila = {'fecha': j.date, 'estado': j.status, 'fuente': fuente}
        fila.update({clave: _valor(totales, clave) for clave in FLUJOS_SUMABLES})
        por_jornada.append(fila)
    definitivo, falta_def = _bucket([r for r in por_jornada if r['estado'] == 'Cerrada'])
    provisional, falta_prov = _bucket([r for r in por_jornada if r['estado'] != 'Cerrada'])

    fechas_contadas = {j.date for j in contadas}
    sin_jornada = [d for d in _fechas(ini, fin) if d not in fechas_contadas]
    advertencias = list(avisos)
    for etiqueta, faltantes in (('definitivo', falta_def), ('provisional', falta_prov)):
        for clave, fechas in faltantes.items():
            advertencias.append(f'{ETIQUETAS_FLUJOS[clave]} ({clave}) no se puede calcular en el bloque {etiqueta}: sin dato en '
                                + ', '.join(fechas[:10]) + (' …' if len(fechas) > 10 else '') + '.')
    if sin_jornada:
        advertencias.append(f'{len(sin_jornada)} día(s) del periodo no tienen jornada de Finanzas o no se cuentan: cobertura '
                            'incompleta, no significa resultado cero.')
    if abiertas and JORNADAS_ABIERTAS_COMO_PROVISIONAL:
        advertencias.append(f'{len(abiertas)} jornada(s) abierta(s): su resultado es provisional y está separado del definitivo.')
    hay_nulos = bool(falta_def or falta_prov)
    abiertas_pendientes = bool(abiertas and JORNADAS_ABIERTAS_COMO_PROVISIONAL and ABIERTAS_DEGRADAN_A_PARCIAL)
    completa = not (sin_jornada or hay_nulos or abiertas_pendientes)
    cobertura = {'completa': completa, 'dias_periodo': len(list(_fechas(ini, fin))), 'con_jornada': len(jornadas),
                 'cerradas': len(cerradas), 'abiertas': len(abiertas), 'sin_jornada_total': len(sin_jornada),
                 'sin_jornada': sin_jornada[:MAX_FECHAS_LISTADAS]}
    cifras = {'definitivo': definitivo, 'provisional': provisional}
    detalle = {'etiquetas': {clave: ETIQUETAS_FLUJOS[clave] for clave in FLUJOS_SUMABLES}, 'por_jornada': por_jornada}
    return respuesta('resumen_financiero', 'ok' if completa else 'parcial', periodo=periodo, fuentes=fuentes, metodo=metodo,
                     cobertura=cobertura, advertencias=advertencias, cifras=cifras, detalle=detalle)


# --- comparar_periodos ----------------------------------------------------------------------------------------------
AVISO_COMPARACION = ('Esto es una COMPARACIÓN de dos periodos que ya ocurrieron: no es una predicción ni una estimación del futuro.')
METODO_COMPARACION = (AVISO_COMPARACION + ' Se compara el periodo pedido con el periodo inmediatamente anterior de igual duración (mismo '
                      'número de días). Ventas netas viene de resumen_ventas y resultado final de resumen_financiero (suma del '
                      '"Resultado final del día"), las mismas consultas de las pantallas, el chat y los reportes. Solo se compara si '
                      'AMBOS periodos tienen cobertura completa (todos los días con jornada, sin equipos por incorporar y sin '
                      'cifras nulas); si falta cobertura en cualquiera de los dos, la comparación va como null con la razón, nunca '
                      'con una cifra o un porcentaje inventados. La variación porcentual solo se calcula si el periodo anterior es '
                      'positivo. Las jornadas abiertas cuentan como provisionales y se marcan.')


def _dias(ini, fin):
    return (date.fromisoformat(fin) - date.fromisoformat(ini)).days + 1


def _periodo_anterior(ini, fin):
    n = _dias(ini, fin)
    fin_anterior = date.fromisoformat(ini) - timedelta(days=1)
    return (fin_anterior - timedelta(days=n - 1)).isoformat(), fin_anterior.isoformat()


def _valor_ventas(r):
    """(valor en centavos o None, provisional, motivos por los que falta cobertura) de un resumen_ventas."""
    if r['estado'] == 'sin_datos':
        return None, False, ['no hay jornadas de Finanzas en el periodo']
    cob, motivos = r['cobertura'], []
    if cob['sin_jornada_total']:
        motivos.append(f"{cob['sin_jornada_total']} día(s) sin jornada")
    if cob['equipos_por_incorporar']:
        motivos.append(f"{cob['equipos_por_incorporar']} equipo(s) vendido(s) sin incorporar a Finanzas")
    if not motivos and not cob['completa']:
        motivos.append('el cierre de alguna jornada no trae o no coincide con la venta neta')
    if motivos or r['cifras'] is None or r['cifras']['venta_neta_cents'] is None:
        return None, False, motivos or ['la venta neta no se pudo calcular']
    return r['cifras']['venta_neta_cents'], bool(cob['abiertas']), []


def _valor_resultado(r):
    """(resultado final en centavos o None, provisional, motivos) de un resumen_financiero: definitivo + provisional, ambos aditivos."""
    if r['estado'] == 'sin_datos':
        return None, False, ['no hay jornadas de Finanzas en el periodo']
    motivos = []
    if r['cobertura']['sin_jornada_total']:
        motivos.append(f"{r['cobertura']['sin_jornada_total']} día(s) sin jornada")
    partes = [b['owner_result'] for b in (r['cifras']['definitivo'], r['cifras']['provisional']) if b['jornadas']]
    if any(p is None for p in partes):
        motivos.append('el resultado final no se puede calcular en alguna jornada')
    if motivos or not partes:
        return None, False, motivos or ['el resultado final no se pudo calcular']
    return sum(partes), bool(r['cifras']['provisional']['jornadas']), []


def _variacion(actual, anterior, nombre):
    """Compara dos valores ya validados por _valor_*. Sin cobertura en alguno: todo en null, con la razón."""
    (v1, p1, m1), (v0, p0, m0) = actual, anterior
    salida = {'comparable': False, 'actual_cents': v1, 'anterior_cents': v0, 'diferencia_cents': None, 'variacion_bp': None,
              'variacion_pct': None, 'provisional': bool(p1 or p0), 'motivos_actual': m1, 'motivos_anterior': m0}
    avisos = []
    for etiqueta, motivos in (('actual', m1), ('anterior', m0)):
        if motivos:
            avisos.append(f'{nombre}: el periodo {etiqueta} no tiene cobertura completa ({"; ".join(motivos)}); no se compara.')
    if v1 is None or v0 is None:
        return salida, avisos
    salida['comparable'] = True
    salida['diferencia_cents'] = v1 - v0
    if v0 > 0:
        numerador = (v1 - v0) * 10000  # puntos básicos con enteros: sin decimales flotantes, redondeo al más cercano
        bp = (numerador + v0 // 2) // v0 if numerador >= 0 else -((-numerador + v0 // 2) // v0)
        salida['variacion_bp'], salida['variacion_pct'] = bp, bp / 100
    else:
        avisos.append(f'{nombre}: el periodo anterior es cero o negativo; se informa la diferencia pero no se calcula un porcentaje.')
    if salida['provisional']:
        avisos.append(f'{nombre}: incluye jornadas abiertas; la cifra es provisional y la comparación puede cambiar al cerrar el día.')
    return salida, avisos


@consulta('comparar_periodos', metodo=METODO_COMPARACION)
def comparar_periodos(rol, ini, fin):
    """Ventas netas y resultado final del periodo frente al periodo anterior de igual duración. Una comparación, no una predicción."""
    fuentes = ['resumen_ventas (periodo pedido y periodo anterior de igual duración)',
               'resumen_financiero (periodo pedido y periodo anterior de igual duración)']
    ini, fin, avisos = _periodo(ini, fin)
    ini_a, fin_a = _periodo_anterior(ini, fin)
    actual = {'ini': ini, 'fin': fin, 'dias': _dias(ini, fin)}
    anterior = {'ini': ini_a, 'fin': fin_a, 'dias': _dias(ini_a, fin_a)}
    periodo = {**actual, 'inclusivo': True, 'anterior': anterior, 'tipo': 'comparacion'}
    resultados = {'ventas': (resumen_ventas(rol, ini, fin), resumen_ventas(rol, ini_a, fin_a)),
                  'resultado': (resumen_financiero(rol, ini, fin), resumen_financiero(rol, ini_a, fin_a))}
    todos = [r for par in resultados.values() for r in par]
    for estado in ('sin_autorizacion', 'error_temporal'):  # si una consulta de base no pudo responder, esta tampoco
        if any(r['estado'] == estado for r in todos):
            return respuesta('comparar_periodos', estado, metodo=METODO_COMPARACION,
                             mensaje='Tu perfil no puede usar esta consulta.' if estado == 'sin_autorizacion'
                             else 'No se pudo leer la información en este momento. Intenta de nuevo en unos segundos.')
    if all(r['estado'] == 'sin_datos' for r in todos):
        return respuesta('comparar_periodos', 'sin_datos', mensaje='No hay jornadas de Finanzas en ninguno de los dos periodos.',
                         periodo=periodo, fuentes=fuentes, metodo=METODO_COMPARACION, advertencias=[AVISO_COMPARACION, *avisos])

    ventas, aviso_ventas = _variacion(_valor_ventas(resultados['ventas'][0]), _valor_ventas(resultados['ventas'][1]), 'Ventas netas')
    resultado, aviso_resultado = _variacion(_valor_resultado(resultados['resultado'][0]), _valor_resultado(resultados['resultado'][1]),
                                            'Resultado final')
    cifras = {'es_comparacion': True, 'es_prediccion': False, 'periodo_actual': actual, 'periodo_anterior': anterior,
              'ventas_netas': ventas, 'resultado_final': resultado}
    completa = ventas['comparable'] and resultado['comparable'] and not (ventas['provisional'] or resultado['provisional'])
    cobertura = {'completa': completa, 'ventas_netas': ventas['comparable'], 'resultado_final': resultado['comparable']}
    return respuesta('comparar_periodos', 'ok' if completa else 'parcial', periodo=periodo, fuentes=fuentes, metodo=METODO_COMPARACION,
                     cobertura=cobertura, advertencias=[AVISO_COMPARACION, *avisos, *aviso_ventas, *aviso_resultado], cifras=cifras)


# --- permanencia_inventario -----------------------------------------------------------------------------------------
METODO_PERMANENCIA = ('Cuenta los días que cada equipo disponible (no archivado) lleva en inventario: desde su fecha de ingreso (la '
                      'del lote o, si no tiene lote, la de creación del equipo, la misma regla del consolidado contable) hasta hoy. '
                      'Un equipo es de baja rotación cuando lleva MÁS días que el umbral. Es un conteo de lo que ya pasó: no es una '
                      'predicción de cuándo se venderá. Foto de hoy: no hay inventario histórico. Nunca devuelve el IMEI.')


def _umbral(valor):
    if valor is None or valor == '':
        return UMBRAL_PERMANENCIA_DIAS
    if isinstance(valor, bool) or isinstance(valor, float) and not valor.is_integer():
        raise ParametroInvalido('Umbral: debe ser un número entero de días.')
    try:
        dias = int(str(valor).strip())
    except ValueError:
        raise ParametroInvalido('Umbral: debe ser un número entero de días.')
    if not 1 <= dias <= MAX_UMBRAL_DIAS:
        raise ParametroInvalido(f'Umbral: debe estar entre 1 y {MAX_UMBRAL_DIAS} días.')
    return dias


def _ingreso(p, hoy):
    """Fecha de ingreso del equipo, o None si no existe, no es una fecha válida o está en el futuro."""
    try:
        ingreso = date.fromisoformat(_compra_fecha(p))
    except (ValueError, TypeError):
        return None
    return ingreso if ingreso <= hoy else None


def _redondeado(valor):
    return float(Decimal(str(valor)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))


@consulta('permanencia_inventario', metodo=METODO_PERMANENCIA)
def permanencia_inventario(rol, umbral_dias=None):
    """Días en inventario de cada equipo disponible y cuántos pasan del umbral (baja rotación). Sin IMEI; costo solo para quien lo ve."""
    fuentes = ['Producto (tabla equipment): status = Disponible y archived = 0',
               'Lote (purchase_lot): fecha de ingreso; sin lote, fecha de creación del equipo',
               'Catalogo: nombres de ubicación y referencia']
    umbral = _umbral(umbral_dias)
    hoy_texto = today()
    hoy = date.fromisoformat(hoy_texto)
    periodo = {'fecha_corte': hoy_texto, 'umbral_dias': umbral, 'nota': 'Foto del inventario de hoy; no es histórico.'}
    if not _hay_equipos():
        return respuesta('permanencia_inventario', 'sin_datos', mensaje='No hay equipos registrados en el inventario.',
                         periodo=periodo, fuentes=fuentes, metodo=METODO_PERMANENCIA)
    equipos = _leer_disponibles(None, None)
    ver_costo = rol in ROLES_CON_COSTO
    filas, sin_fecha = [], 0
    for p in equipos:
        ingreso = _ingreso(p, hoy)
        if ingreso is None:
            sin_fecha += 1
        else:
            filas.append({'p': p, 'ingreso': ingreso, 'dias': (hoy - ingreso).days})
    dias = [f['dias'] for f in filas]
    sobre = sorted((f for f in filas if f['dias'] > umbral), key=lambda f: (-f['dias'], f['p'].id))

    cifras = {'umbral_dias': umbral, 'disponibles': len(equipos), 'con_fecha_de_ingreso': len(filas), 'sin_fecha_de_ingreso': sin_fecha,
              'promedio_dias': _redondeado(sum(dias) / len(dias)) if dias else None,
              'mediana_dias': _redondeado(statistics.median(dias)) if dias else None, 'maximo_dias': max(dias) if dias else None,
              'sobre_umbral': {'equipos': len(sobre)}}
    if ver_costo:
        cifras['costo_inmovilizado_cents'] = sum(p.cost_cents for p in equipos)
        cifras['sobre_umbral']['costo_inmovilizado_cents'] = sum(f['p'].cost_cents for f in sobre)

    rangos = []
    for desde, hasta, nombre in RANGOS_PERMANENCIA:
        dentro = [f for f in filas if f['dias'] >= desde and (hasta is None or f['dias'] <= hasta)]
        fila = {'rango': nombre, 'equipos': len(dentro)}
        if ver_costo:
            fila['costo_inmovilizado_cents'] = sum(f['p'].cost_cents for f in dentro)
        rangos.append(fila)
    por_referencia = {}
    for f in sobre:
        clave = (f['p'].reference_id, _nombre_referencia(f['p']) if f['p'].reference_id else None)
        fila = por_referencia.setdefault(clave, {'referencia_id': clave[0], 'referencia': clave[1] or 'Sin referencia', 'equipos': 0,
                                                  'dias_maximo': 0, 'costo': 0})
        fila['equipos'] += 1
        fila['dias_maximo'] = max(fila['dias_maximo'], f['dias'])
        fila['costo'] += f['p'].cost_cents
    sobre_por_referencia = []
    for fila in sorted(por_referencia.values(), key=lambda x: (-x['equipos'], -x['dias_maximo'], x['referencia'])):
        costo = fila.pop('costo')
        if ver_costo:
            fila['costo_inmovilizado_cents'] = costo
        sobre_por_referencia.append(fila)
    listado = []
    for f in sobre[:MAX_EQUIPOS_LISTADOS]:
        p = f['p']
        fila = {'equipo_id': p.id, 'referencia': (_nombre_referencia(p) if p.reference_id else None) or 'Sin referencia',
                'ubicacion': (_nombre_ubicacion(p) if p.location_id else None) or 'Sin ubicación',
                'ingreso': f['ingreso'].isoformat(), 'dias': f['dias']}
        if ver_costo:
            fila['costo_inmovilizado_cents'] = p.cost_cents
        listado.append(fila)
    detalle = {'por_rango': rangos, 'sobre_umbral_por_referencia': sobre_por_referencia, 'equipos_sobre_umbral': listado,
               'equipos_sobre_umbral_truncado': len(sobre) > MAX_EQUIPOS_LISTADOS}

    advertencias = []
    if sin_fecha:
        advertencias.append(f'{sin_fecha} equipo(s) disponible(s) no tienen una fecha de ingreso válida (vacía, mal escrita o futura); '
                            'no cuentan en los días ni en el umbral.')
    if detalle['equipos_sobre_umbral_truncado']:
        advertencias.append(f'Se listan los {MAX_EQUIPOS_LISTADOS} equipos con más días; el total sobre el umbral es {len(sobre)}.')
    estado = 'parcial' if sin_fecha else 'ok'
    return respuesta('permanencia_inventario', estado, periodo=periodo, fuentes=fuentes, metodo=METODO_PERMANENCIA,
                     cobertura={'completa': not sin_fecha, 'equipos_sin_fecha_de_ingreso': sin_fecha},
                     advertencias=advertencias, cifras=cifras, detalle=detalle)
