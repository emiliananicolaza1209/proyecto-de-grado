"""Chat básico por reglas: intenciones fijas, periodos en español y respuestas deterministas.

No usa modelo de lenguaje, no usa ``request`` ni ``session`` y no escribe datos del negocio. Cada pregunta se traduce a una de las
cuatro consultas de ``consultas_service`` (la misma fuente de cálculo que pantallas y reportes) y la respuesta la redacta
:func:`redactar_respuesta`, que es el punto de extensión: un modelo de lenguaje podría reemplazarla después para mejorar la
redacción, pero NUNCA para calcular ni corregir registros (desactivado: aquí no hay dependencias ni claves).

Cada consulta queda en ``registro_gestion`` (tabla existente): usuario, fecha, herramienta, periodo y estado. No se guarda el
texto de la pregunta ni las cifras de la respuesta.
"""
import re
import unicodedata
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models.gestion import RegistroGestion
from . import consultas_service as cs
from ..models.contabilidad import ahora_colombia
from .operacion_service import today

MAX_PREGUNTA = 300
MESES = {'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8, 'septiembre': 9,
         'setiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12}
NOMBRE_MES = {1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril', 5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
              9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'}

# Orden de prioridad cuando una pregunta menciona varias cosas: se responde la primera y se avisa de las demás.
INTENCIONES = (
    ('resumen_financiero', ('resultado', 'utilidad', 'ganancia', 'ganamos', 'financier', 'balance', 'liquidacion', 'comision',
                            'cierre')),
    ('creditos_pendientes', ('credito', 'cartera', 'aliado', 'addi', 'sistecredito', 'su pay', 'sufi')),
    ('estado_inventario', ('inventario', 'disponible', 'existencia', 'stock', 'cuantos equipos', 'cuantos celulares',
                           'equipos hay', 'celulares hay')),
    ('resumen_ventas', ('venta', 'vend', 'facturamos')),
)
TITULOS = {'resumen_ventas': 'Ventas', 'resumen_financiero': 'Resultado financiero', 'estado_inventario': 'Inventario disponible',
           'creditos_pendientes': 'Créditos pendientes'}
FUENTES = {
    'resumen_ventas': 'Finanzas: operaciones Venta no anuladas por fecha de jornada (cierre de las jornadas cerradas)',
    'resumen_financiero': 'Finanzas: cierre de las jornadas cerradas y reporte de las abiertas (provisional)',
    'estado_inventario': 'Inventario: equipos disponibles no archivados, al momento de la consulta',
    'creditos_pendientes': 'Finanzas: créditos de aliados, saldo = neto - recibido, al momento de la consulta',
}
TIENEN_PERIODO = ('resumen_ventas', 'resumen_financiero')
# Datos que el chat nunca entrega, aunque se pidan: se responde que no se puede, sin intentar nada.
TEMAS_PRIVADOS = ('vendedor', 'cliente', 'imei', 'cedula', 'sueldo', 'salario', 'nomina', 'proveedor', 'margen', 'consignacion',
                  'banco', 'contrasena', 'password', 'usuario')
VERBOS_DE_ESCRITURA = ('borra', 'borrar', 'elimina', 'eliminar', 'crea', 'crear', 'registra', 'registrar', 'anula', 'anular', 'cambia',
                       'cambiar', 'modifica', 'modificar', 'actualiza', 'actualizar', 'cierra', 'cerrar', 'abre', 'abrir', 'edita',
                       'editar', 'agrega', 'agregar')
CAPACIDADES = ('ventas de un periodo (ej. "ventas de hoy", "ventas del 1 al 15 de octubre")',
               'resultado financiero de un periodo (ej. "resultado de esta semana")',
               'inventario disponible (ej. "inventario disponible")',
               'créditos pendientes por aliado (ej. "créditos pendientes")')
PERIODOS_ENTENDIDOS = 'hoy, ayer, esta semana, semana pasada, este mes, mes pasado, un mes por su nombre, "del 1 al 15 de octubre"'


def normalizar(texto):
    sin_tildes = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', sin_tildes.lower()).strip()


# --- periodos ---------------------------------------------------------------------------------------------------------
class PeriodoInvalido(ValueError):
    pass


_MES = r'(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)'
_ANIO = r'(?: de (\d{4}))?'


def _fecha(anio, mes, dia):
    try:
        return date(anio, mes, dia)
    except ValueError:
        raise PeriodoInvalido(f'La fecha {dia} de {NOMBRE_MES[mes]} de {anio} no existe.')


def _ultimo_dia(anio, mes):
    siguiente = date(anio + (mes == 12), mes % 12 + 1, 1)
    return siguiente - timedelta(days=1)


def _p(ini, fin, etiqueta, supuesto=False):
    return {'ini': ini.isoformat(), 'fin': fin.isoformat(), 'etiqueta': etiqueta, 'supuesto': supuesto}


def interpretar_periodo(pregunta, hoy=None):
    """Devuelve el periodo pedido en la pregunta, o ``None`` si no menciona ninguno. Las fechas son inclusivas."""
    hoy = date.fromisoformat(hoy or today())
    t = normalizar(pregunta)

    m = re.search(r'(\d{4}-\d{2}-\d{2}) (?:al?|hasta|y) (\d{4}-\d{2}-\d{2})', t)
    if m:
        try:
            ini, fin = date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))
        except ValueError:
            raise PeriodoInvalido('Una de las fechas no existe.')
        return _p(ini, fin, f'del {ini.isoformat()} al {fin.isoformat()}')
    m = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', t)
    if m:
        try:
            dia = date.fromisoformat(m.group(1))
        except ValueError:
            raise PeriodoInvalido('La fecha pedida no existe.')
        return _p(dia, dia, dia.isoformat())

    m = re.search(rf'\bdel? (\d{{1,2}})(?: de {_MES})? (?:al?|hasta el|hasta) (?:el )?(\d{{1,2}}) de {_MES}{_ANIO}', t) or \
        re.search(rf'\bentre (?:el )?(\d{{1,2}})() y (?:el )?(\d{{1,2}}) de {_MES}{_ANIO}', t)
    if m:
        d1, mes1, d2, mes2, anio = m.groups()
        anio = int(anio) if anio else hoy.year
        mes2 = MESES[mes2]
        mes1 = MESES[mes1] if mes1 else mes2
        ini, fin = _fecha(anio, mes1, int(d1)), _fecha(anio, mes2, int(d2))
        return _p(ini, fin, f'del {ini.day} de {NOMBRE_MES[ini.month]} al {fin.day} de {NOMBRE_MES[fin.month]} de {anio}')

    m = re.search(r'ultimos? (\d{1,3}) dias', t)
    if m and int(m.group(1)) >= 1:
        n = int(m.group(1))
        return _p(hoy - timedelta(days=n - 1), hoy, f'los últimos {n} días')

    m = re.search(rf'\b(?:el )?(\d{{1,2}}) de {_MES}{_ANIO}', t)
    if m:
        dia = _fecha(int(m.group(3)) if m.group(3) else hoy.year, MESES[m.group(2)], int(m.group(1)))
        return _p(dia, dia, f'el {dia.day} de {NOMBRE_MES[dia.month]} de {dia.year}')

    if re.search(r'\bayer\b', t):
        ayer = hoy - timedelta(days=1)
        return _p(ayer, ayer, 'ayer')
    if re.search(r'\bhoy\b', t):
        return _p(hoy, hoy, 'hoy')
    if re.search(r'semana (pasada|anterior)', t):
        lunes = hoy - timedelta(days=hoy.weekday() + 7)
        return _p(lunes, lunes + timedelta(days=6), 'la semana pasada')
    if re.search(r'(esta|la) semana\b|\bsemana actual', t):
        return _p(hoy - timedelta(days=hoy.weekday()), hoy, 'esta semana (de lunes a hoy)')
    if re.search(r'mes (pasado|anterior)', t):
        ultimo_anterior = hoy.replace(day=1) - timedelta(days=1)
        return _p(ultimo_anterior.replace(day=1), ultimo_anterior, f'el mes pasado ({NOMBRE_MES[ultimo_anterior.month]})')
    if re.search(r'\beste mes\b|\bmes actual', t):
        return _p(hoy.replace(day=1), hoy, f'este mes ({NOMBRE_MES[hoy.month]}, hasta hoy)')

    m = re.search(rf'\b{_MES}{_ANIO}\b', t)
    if m:
        mes, anio = MESES[m.group(1)], int(m.group(2)) if m.group(2) else hoy.year
        ini, fin = _fecha(anio, mes, 1), _ultimo_dia(anio, mes)
        etiqueta = f'{NOMBRE_MES[mes]} de {anio}'
        if fin > hoy >= ini:
            fin, etiqueta = hoy, etiqueta + ' (hasta hoy)'
        return _p(ini, fin, etiqueta)
    if re.search(r'\bdel mes\b|\bel mes\b', t):
        return _p(hoy.replace(day=1), hoy, f'este mes ({NOMBRE_MES[hoy.month]}, hasta hoy)')
    return None


# --- intención --------------------------------------------------------------------------------------------------------
def detectar_intenciones(pregunta):
    t = normalizar(pregunta)
    return [nombre for nombre, palabras in INTENCIONES if any(re.search(r'\b' + re.escape(p), t) for p in palabras)]


def _pide_algo_privado(pregunta):
    t = normalizar(pregunta)
    return any(re.search(rf'\b{p}', t) for p in TEMAS_PRIVADOS)


def _quiere_escribir(pregunta):
    palabras = set(re.findall(r'[a-z]+', normalizar(pregunta)))
    return bool(palabras & set(VERBOS_DE_ESCRITURA))


# --- redacción determinista -------------------------------------------------------------------------------------------
def formatear_pesos(centavos):
    """Importe en pesos con punto de miles y coma decimal solo si hay centavos: $1.234.567 / $1.234.567,50."""
    if centavos is None:
        return 'no calculable'
    pesos = Decimal(int(centavos)) / 100
    signo = '-' if pesos < 0 else ''
    pesos = abs(pesos)
    entero, frac = divmod(pesos, 1)
    texto = f'{int(entero):,}'.replace(',', '.')
    if frac:
        texto += ',' + f'{int(frac * 100):02d}'
    return f'{signo}${texto}'


def _n(valor):
    return 'no calculable' if valor is None else f'{valor:,}'.replace(',', '.')


def _filas_tarjeta(resultado):
    """Cifras principales ya formateadas, para la respuesta escrita y para la tarjeta de la pantalla."""
    c, e = resultado['cifras'], resultado['consulta']
    if not c:
        return []
    if e == 'resumen_ventas':
        filas = [('Operaciones de venta', _n(c['operaciones'])), ('Venta neta', formatear_pesos(c['venta_neta_cents']))]
        if c.get('equipos'):
            filas.append(('Equipos', f"{formatear_pesos(c['equipos']['venta_neta_cents'])} ({_n(c['equipos']['operaciones'])})"))
            filas.append(('Complementarias',
                          f"{formatear_pesos(c['complementarias']['venta_neta_cents'])} ({_n(c['complementarias']['operaciones'])})"))
        prov = c.get('provisional')
        if prov and prov['operaciones']:
            filas.append(('Provisional (jornadas abiertas)', f"{formatear_pesos(prov['venta_neta_cents'])} ({_n(prov['operaciones'])})"))
        defi = c.get('definitivo')
        if defi and defi['operaciones']:
            filas.append(('Definitivo (jornadas cerradas)', f"{formatear_pesos(defi['venta_neta_cents'])} ({_n(defi['operaciones'])})"))
        por = c.get('por_incorporar')
        if por and por['equipos']:
            filas.append(('Equipos por incorporar a Finanzas', f"{_n(por['equipos'])} ({formatear_pesos(por['venta_neta_cents'])})"))
        return filas
    if e == 'resumen_financiero':
        filas = []
        for bloque, nombre in (('definitivo', 'Definitivo (jornadas cerradas)'), ('provisional', 'Provisional (jornadas abiertas)')):
            b = c[bloque]
            if not b['jornadas']:
                continue
            filas.append((f'{nombre} — jornadas', _n(b['jornadas'])))
            for clave in ('gross', 'debe', 'liquidation', 'commission', 'owner_result'):
                filas.append((f'{nombre} — {cs.ETIQUETAS_FLUJOS[clave]}', formatear_pesos(b[clave])))
        return filas
    if e == 'estado_inventario':
        filas = [('Equipos disponibles', _n(c['disponibles'])), ('De ellos, retomas del POOL', _n(c['retomas_pool']))]
        if 'costo_inmovilizado_cents' in c:
            filas.append(('Costo inmovilizado', formatear_pesos(c['costo_inmovilizado_cents'])))
        for u in (resultado['detalle'] or {}).get('por_ubicacion', [])[:5]:
            filas.append((f"Ubicación: {u['ubicacion']}", _n(u['disponibles'])))
        return filas
    if e == 'creditos_pendientes':
        filas = [('Saldo pendiente', formatear_pesos(c['saldo_cents'])), ('Créditos pendientes', _n(c['creditos_pendientes']))]
        for a in (resultado['detalle'] or {}).get('por_aliado', [])[:8]:
            filas.append((f"Aliado: {a['aliado']}", f"{formatear_pesos(a['saldo_cents'])} ({_n(a['creditos'])})"))
        return filas
    return []


def _es_provisional(resultado):
    cob = resultado.get('cobertura') or {}
    return bool(resultado['consulta'] in TIENEN_PERIODO and cob.get('abiertas'))


def redactar_respuesta(resultado, notas=()):
    """Texto de la respuesta. Determinista: mismas entradas, misma salida. Nunca calcula; solo da formato a lo ya calculado."""
    estado, consulta = resultado['estado'], resultado['consulta']
    titulo = TITULOS.get(consulta, consulta)
    periodo = resultado.get('periodo') or {}
    if estado == 'sin_autorizacion':
        return 'Tu perfil no tiene permiso para esta consulta.'
    if estado == 'error_temporal':
        return 'No pude leer la información en este momento. Intenta de nuevo en unos segundos.'
    lineas = []
    if estado == 'sin_datos':
        lineas.append(f'{titulo}: no hay datos para responder esto.')
        if resultado.get('mensaje'):
            lineas.append(resultado['mensaje'])
        lineas.append('Eso no significa cero: significa que no hay registros que consultar.')
    else:
        if periodo.get('ini'):
            tramo = periodo['ini'] if periodo['ini'] == periodo['fin'] else f"{periodo['ini']} a {periodo['fin']}"
            lineas.append(f'{titulo} — {tramo}:')
        else:
            lineas.append(f"{titulo} — estado a {periodo.get('fecha_corte', 'hoy')}:")
        if estado == 'parcial':
            lineas.append('Resultado parcial: faltan datos o parte de las cifras son provisionales.')
        if _es_provisional(resultado):
            lineas.append('Incluye jornadas abiertas: esa parte es provisional y puede cambiar al cerrar el día.')
        for etiqueta, valor in _filas_tarjeta(resultado):
            lineas.append(f'- {etiqueta}: {valor}')
    for nota in notas:
        lineas.append(f'Nota: {nota}')
    if resultado.get('advertencias'):
        lineas.append('Advertencias:')
        lineas.extend(f'- {a}' for a in resultado['advertencias'])
    lineas.append(f'Fuente: {FUENTES.get(consulta, consulta)}.')
    return '\n'.join(lineas)


def tarjeta(resultado, periodo_etiqueta=None, notas=()):
    return {'consulta': resultado['consulta'], 'titulo': TITULOS.get(resultado['consulta'], resultado['consulta']),
            'estado': resultado['estado'], 'provisional': _es_provisional(resultado),
            'periodo': {**(resultado.get('periodo') or {}), 'etiqueta': periodo_etiqueta},
            'cifras': [{'etiqueta': e, 'valor': v} for e, v in _filas_tarjeta(resultado)] if resultado['estado'] in ('ok', 'parcial') else [],
            'fuente': FUENTES.get(resultado['consulta'], resultado['consulta']),
            'advertencias': list(resultado.get('advertencias') or []) if resultado['estado'] in ('ok', 'parcial', 'sin_datos') else [],
            'notas': list(notas)}


# --- registro ---------------------------------------------------------------------------------------------------------
def _registrar(usuario_id, usuario, rol, herramienta, periodo, estado):
    """Una fila por consulta en registro_gestion. Sin pregunta, sin cifras, sin secretos. Un fallo aquí no rompe la respuesta."""
    try:
        db.session.add(RegistroGestion(
            entidad='chat', entidad_id=int(usuario_id or 0), accion='Consulta del chat', motivo='Consulta de solo lectura',
            actor=str(usuario or 'Sin usuario')[:120],
            datos={'herramienta': herramienta, 'periodo': {'ini': periodo['ini'], 'fin': periodo['fin']} if periodo else None,
                   'estado': estado, 'rol': rol, 'fecha': ahora_colombia().isoformat(timespec='seconds')}))
        db.session.commit()
        return True
    except SQLAlchemyError:
        db.session.rollback()
        return False


def fuera_de_alcance(motivo=None):
    lineas = [motivo or 'No puedo responder eso.', 'Solo respondo consultas de lectura sobre:']
    lineas.extend(f'- {c}' for c in CAPACIDADES)
    lineas.append(f'Periodos que entiendo: {PERIODOS_ENTENDIDOS}.')
    return '\n'.join(lineas)


def responder(rol, pregunta, usuario=None, usuario_id=0, hoy=None):
    """Interpreta la pregunta, ejecuta la consulta autorizada y devuelve la respuesta redactada y su tarjeta."""
    pregunta = (pregunta or '').strip()
    base = {'pregunta': pregunta, 'intencion': None, 'herramienta': None, 'periodo': None, 'estado': None, 'respuesta': '',
            'tarjeta': None}

    def cerrar(estado, texto, herramienta=None, periodo=None, tarjeta_=None, intencion=None):
        _registrar(usuario_id, usuario, rol, herramienta or 'ninguna', periodo, estado)
        return {**base, 'estado': estado, 'respuesta': texto, 'herramienta': herramienta, 'intencion': intencion,
                'periodo': periodo, 'tarjeta': tarjeta_}

    if not pregunta or len(pregunta) > MAX_PREGUNTA:
        raise ValueError(f'Escribe una pregunta de hasta {MAX_PREGUNTA} caracteres.')
    if _quiere_escribir(pregunta):
        return cerrar('fuera_de_alcance', fuera_de_alcance('No hago cambios: el chat solo consulta, no escribe ni corrige datos.'))
    if _pide_algo_privado(pregunta):
        return cerrar('fuera_de_alcance', fuera_de_alcance(
            'No entrego datos por persona (vendedoras, clientes, sueldos, cédulas), IMEI, bancos ni contraseñas.'))
    intenciones = detectar_intenciones(pregunta)
    if not intenciones:
        return cerrar('fuera_de_alcance', fuera_de_alcance())
    herramienta = intenciones[0]
    notas = []
    if len(intenciones) > 1:
        otras = ', '.join(TITULOS[i].lower() for i in intenciones[1:])
        notas.append(f'Tu pregunta también mencionaba {otras}; respondí {TITULOS[herramienta].lower()}. Pregunta lo otro por separado.')

    periodo = None
    try:
        pedido = interpretar_periodo(pregunta, hoy)
    except PeriodoInvalido as exc:
        return cerrar('periodo_invalido', f'No pude usar ese periodo: {exc}', herramienta, intencion=herramienta)
    if herramienta in TIENEN_PERIODO:
        if pedido is None:
            hoy_ = hoy or today()
            pedido = _p(date.fromisoformat(hoy_), date.fromisoformat(hoy_), 'hoy', supuesto=True)
            notas.append(f'No indicaste un periodo; usé hoy ({hoy_}).')
        periodo = pedido
        if periodo['ini'] > (hoy or today()):
            return cerrar('periodo_invalido', f"El periodo {periodo['etiqueta']} todavía no ha ocurrido: no hay nada que consultar.",
                          herramienta, periodo, intencion=herramienta)
        if periodo['fin'] > (hoy or today()):
            periodo = dict(periodo, fin=hoy or today())
            notas.append('El periodo llega hasta una fecha futura; consulté hasta hoy.')
        try:
            resultado = getattr(cs, herramienta)(rol, periodo['ini'], periodo['fin'])
        except cs.ParametroInvalido as exc:
            return cerrar('periodo_invalido', f'No pude usar ese periodo: {exc}', herramienta, periodo, intencion=herramienta)
    else:
        if pedido is not None:
            notas.append('Esta consulta muestra el estado de hoy; ignoré el periodo que indicaste.')
        resultado = getattr(cs, herramienta)(rol)
    texto = redactar_respuesta(resultado, notas)
    return cerrar(resultado['estado'], texto, herramienta, periodo,
                  tarjeta(resultado, periodo['etiqueta'] if periodo else None, notas), herramienta)
