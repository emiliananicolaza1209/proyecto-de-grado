"""Reporte por periodo: el mismo cálculo y la misma redacción que el chat, con selector de periodo y exportación.

No calcula nada propio: cada reporte llama a las consultas de ``consultas_service`` (ventas -> resumen_ventas; finanzas ->
resumen_financiero y creditos_pendientes; inventario -> estado_inventario) y da formato con ``chat_service``. Así la pantalla, el
reporte y el chat muestran las mismas cifras. No usa ``request`` ni ``session`` y no escribe datos del negocio; cada reporte deja una
fila en ``registro_gestion`` (usuario, fecha, herramienta, periodo, estado; nunca las cifras).
"""
import csv
import io
from datetime import date, timedelta

from . import chat_service as chat
from . import consultas_service as cs
from .operacion_service import today

TIPOS = ('semana', '15dias', 'mes', 'rango')
ETIQUETAS_TIPO = {'semana': 'Esta semana (de lunes a hoy)', '15dias': 'Últimos 15 días', 'mes': 'Este mes (del 1 a hoy)',
                  'rango': 'Rango de fechas'}
OPCIONES = (('semana', 'Semana'), ('15dias', '15 días'), ('mes', 'Mes'), ('rango', 'Rango de fechas'))
ETIQUETAS_ESTADO = {'ok': 'Completo', 'parcial': 'Parcial', 'sin_datos': 'Sin datos', 'sin_autorizacion': 'Sin autorización',
                    'error_temporal': 'Error temporal'}
MODULOS = {
    # 'comparar': el reporte admite el botón "Comparar con el periodo anterior" (una comparación, no una predicción).
    'ventas': {'titulo': 'Reporte de ventas', 'consultas': ('resumen_ventas',), 'periodo': True, 'comparar': True},
    'finanzas': {'titulo': 'Reporte financiero', 'consultas': ('resumen_financiero', 'creditos_pendientes'), 'periodo': True,
                 'comparar': True},
    # El inventario es una foto de hoy; además del estado trae la lista de equipos de baja rotación sobre un umbral de días.
    'inventario': {'titulo': 'Reporte de inventario', 'consultas': ('estado_inventario', 'permanencia_inventario'), 'periodo': False,
                   'comparar': False},
}


class ReporteInvalido(ValueError):
    """Módulo, tipo de periodo o fechas que no se pueden usar; la ruta lo convierte en un 400 con el motivo."""


def resolver_periodo(tipo, ini=None, fin=None, hoy=None):
    """Convierte la elección del selector en fechas inclusivas (hora de Colombia)."""
    hoy_d = date.fromisoformat(hoy or today())
    if tipo == 'semana':
        ini_d, fin_d = hoy_d - timedelta(days=hoy_d.weekday()), hoy_d
    elif tipo == '15dias':
        ini_d, fin_d = hoy_d - timedelta(days=14), hoy_d
    elif tipo == 'mes':
        ini_d, fin_d = hoy_d.replace(day=1), hoy_d
    elif tipo == 'rango':
        try:
            ini_d, fin_d = date.fromisoformat((ini or '').strip()), date.fromisoformat((fin or '').strip())
        except ValueError:
            raise ReporteInvalido('Indica las dos fechas del rango con el formato AAAA-MM-DD.')
        if ini_d > fin_d:
            raise ReporteInvalido('La fecha inicial no puede ser posterior a la final.')
        if ini_d > hoy_d:
            raise ReporteInvalido('El rango está completamente en el futuro.')
        fin_d = min(fin_d, hoy_d)
    else:
        raise ReporteInvalido('Elige semana, 15 días, mes o un rango de fechas.')
    return {'tipo': tipo, 'ini': ini_d.isoformat(), 'fin': fin_d.isoformat(),
            'etiqueta': f'{ETIQUETAS_TIPO[tipo]}: {ini_d.isoformat()} a {fin_d.isoformat()}' if tipo != 'rango'
            else f'{ini_d.isoformat()} a {fin_d.isoformat()}'}


def generar(rol, modulo, tipo=None, ini=None, fin=None, usuario=None, usuario_id=0, hoy=None, comparar=False, umbral=None):
    """Ejecuta las consultas del módulo y devuelve las tarjetas y los textos ya redactados.

    ``comparar`` agrega la comparación con el periodo anterior de igual duración (solo ventas y finanzas); ``umbral`` fija los días de
    baja rotación del reporte de inventario."""
    if modulo not in MODULOS:
        raise ReporteInvalido('Ese reporte no existe.')
    conf = MODULOS[modulo]
    periodo = None
    if conf['periodo']:
        periodo = resolver_periodo(tipo, ini, fin, hoy)
    comparado = bool(comparar and conf['comparar'])
    resultados, tarjetas, textos = [], [], []
    for nombre in (*conf['consultas'], *(('comparar_periodos',) if comparado else ())):
        consulta = getattr(cs, nombre)
        try:
            if nombre == 'permanencia_inventario':
                r = consulta(rol, umbral)
            elif periodo and nombre in chat.TIENEN_PERIODO:
                r = consulta(rol, periodo['ini'], periodo['fin'])
            else:
                r = consulta(rol)
        except cs.ParametroInvalido as exc:
            raise ReporteInvalido(str(exc))
        usa_periodo = bool(periodo and nombre in chat.TIENEN_PERIODO)
        chat._registrar(usuario_id, usuario, rol, nombre, periodo if usa_periodo else None, r['estado'],
                        entidad='reporte', accion='Reporte por periodo')
        resultados.append(r)
        tarjetas.append(chat.tarjeta(r, periodo['etiqueta'] if usa_periodo else None))
        textos.append(chat.redactar_respuesta(r))
    return {'modulo': modulo, 'titulo': conf['titulo'], 'periodo': periodo, 'resultados': resultados, 'tarjetas': tarjetas,
            'textos': textos, 'generado_en': today(), 'foto_actual': not conf['periodo'], 'comparado': comparado,
            'puede_comparar': conf['comparar']}


RESUMEN_TIPOS = ('semana', '15dias', 'mes')


def resumen_tarjetas(rol, tipo='semana', hoy=None):
    """Las cinco tarjetas del Resumen del Propietario, con las mismas consultas y la misma redacción que el chat y los reportes.

    Ventas netas usa el periodo elegido; el resultado final es el del día de hoy; inventario, créditos y baja rotación son una foto de hoy.
    No calcula nada propio y no escribe nada (ver la pantalla no deja filas en registro_gestion). ``enlace`` indica el reporte al que lleva
    cada tarjeta: (módulo, periodo, ini, fin)."""
    tipo = tipo if tipo in RESUMEN_TIPOS else 'semana'
    periodo = resolver_periodo(tipo, hoy=hoy)
    dia = periodo['fin']
    plan = (
        ('resumen_ventas', (periodo['ini'], periodo['fin']), periodo['etiqueta'], ('ventas', tipo, '', '')),
        ('resumen_financiero', (dia, dia), f'Hoy: {dia}', ('finanzas', 'rango', dia, dia)),
        ('estado_inventario', (), None, ('inventario', '', '', '')),
        ('creditos_pendientes', (), None, ('finanzas', tipo, '', '')),
        ('permanencia_inventario', (), None, ('inventario', '', '', '')),
    )
    salida = []
    for nombre, args, etiqueta, enlace in plan:
        r = getattr(cs, nombre)(rol, *args)
        salida.append({'tarjeta': chat.tarjeta(r, etiqueta), 'texto': chat.redactar_respuesta(r), 'enlace': enlace})
    return {'tipo': tipo, 'periodo': periodo, 'tarjetas': salida}


def _segura(texto):
    """Evita que Excel tome un texto como fórmula (los nombres de aliado o de ubicación vienen de la base)."""
    texto = '' if texto is None else str(texto)
    return "'" + texto if texto[:1] in ('=', '+', '-', '@', '\t', '\r') else texto


def a_csv(reporte):
    """El mismo contenido de las tarjetas, en CSV (separador ;). Los importes ya vienen en pesos con formato."""
    salida = io.StringIO()
    w = csv.writer(salida, delimiter=';', lineterminator='\r\n')
    w.writerow(['Reporte', reporte['titulo']])
    w.writerow(['Generado', reporte['generado_en']])
    w.writerow(['Periodo', reporte['periodo']['etiqueta'] if reporte['periodo'] else f"Estado a {reporte['generado_en']} (no depende del periodo)"])
    for t in reporte['tarjetas']:
        w.writerow([])
        w.writerow(['Consulta', t['titulo']])
        w.writerow(['Estado', t['estado'] + (' (incluye jornadas abiertas: provisional)' if t['provisional'] else '')])
        if t['cifras']:
            w.writerow(['Concepto', 'Valor'])
            for c in t['cifras']:
                w.writerow([_segura(c['etiqueta']), c['valor']])  # el valor lo arma el código (importes y conteos), no texto libre
        for nota in t['notas']:
            w.writerow(['Nota', _segura(nota)])
        for aviso in t['advertencias']:
            w.writerow(['Advertencia', _segura(aviso)])
        w.writerow(['Fuente', _segura(t['fuente'])])
    return salida.getvalue()
