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

from sqlalchemy.exc import DBAPIError, OperationalError, TimeoutError as SATimeoutError

from ..extensions import db
from ..models import Catalogo, Producto
from ..models.finanzas import OperacionFinanciera as Op
from ..models.gestion import AliadoCredito, CreditoVenta
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
}
# Quién ve el costo inmovilizado del inventario (la matriz actual del código también se lo da a Inventario: no se traslada).
ROLES_CON_COSTO = ('Propietario',)
# Créditos que cuentan como saldo pendiente. Los 'Anulado' y 'Pagado' nunca cuentan.
ESTADOS_CREDITO_PENDIENTE = ('Pendiente', 'Parcial')
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


def consulta(nombre):
    """Aplica autorización (antes de leer nada) y convierte los fallos temporales de la base en un estado."""
    def decorador(funcion):
        @functools.wraps(funcion)
        def envuelta(rol, *args, **kwargs):
            if rol not in ROLES_CONSULTAS.get(nombre, ()):
                return respuesta(nombre, 'sin_autorizacion', mensaje='Tu perfil no puede usar esta consulta.')
            try:
                return funcion(rol, *args, **kwargs)
            except (OperationalError, SATimeoutError, DBAPIError):
                db.session.rollback()
                return respuesta(nombre, 'error_temporal',
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
