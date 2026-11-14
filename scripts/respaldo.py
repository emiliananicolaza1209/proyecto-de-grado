#!/usr/bin/env python3
"""Respaldo y restauración de CP Store con SQLite. Solo biblioteca estándar; no importa la aplicación.

    python scripts/respaldo.py copiar    --destino D:\\Respaldos\\CPStore
    python scripts/respaldo.py verificar --copia   D:\\Respaldos\\CPStore\\cpstore_20261112_180000
    python scripts/respaldo.py restaurar --copia   D:\\Respaldos\\CPStore\\cpstore_20261112_180000 --destino D:\\Prueba\\restaurado

Qué copia: la base de datos (copia consistente con la API de respaldo de SQLite, aunque la aplicación esté encendida) y la carpeta
de soportes (facturas adjuntas). Cada copia es una carpeta ``cpstore_AAAAMMDD_HHMMSS`` con ``cpstore.sqlite``, ``soportes/`` y
``verificacion.json`` (versión del esquema, conteos por tabla, totales de control y huella SHA-256 de cada archivo).

Qué NO copia, a propósito: ``.env``, ``.session-secret``, claves (``*.pem``, ``*.key``...) ni ``SECRET_KEY``. Guárdalos aparte.

La restauración nunca sobrescribe: se niega a seguir si el destino ya existe y trabaja en una carpeta temporal que solo se
renombra al final si todo se verificó. Si algo falla, no queda nada a medias.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
COLOMBIA = timezone(timedelta(hours=-5))
FORMATO = 1
NOMBRE_BASE = 'cpstore.sqlite'
CARPETA_SOPORTES = 'soportes'
ARCHIVO_VERIFICACION = 'verificacion.json'
PATRON_COPIA = re.compile(r'^cpstore_\d{8}_\d{6}$')
EXTENSIONES_SECRETAS = ('.pem', '.key', '.p12', '.pfx')
AVISO_SECRETOS = ('AVISO: esta copia NO incluye el archivo .env, las claves ni SECRET_KEY (ni .session-secret). '
                  'Guárdalos por separado, en un lugar seguro, o no podrás volver a poner la aplicación en marcha con las mismas sesiones.')
AVISO_DATOS = ('AVISO: la copia contiene datos personales y los hashes de las contraseñas. Protégela como si fuera la base original '
               '(Ley 1581).')


class ErrorRespaldo(Exception):
    """Error esperado, con un mensaje claro para la persona que usa el script. ``codigo`` es el código de salida."""

    def __init__(self, mensaje, codigo=2):
        super().__init__(mensaje)
        self.codigo = codigo


# --- utilidades --------------------------------------------------------------------------------------------------------
def es_secreto(nombre):
    n = nombre.lower()
    return n.startswith('.env') or 'secret' in n or 'password' in n or n.endswith(EXTENSIONES_SECRETAS)


def sha256_de(ruta):
    h = hashlib.sha256()
    with open(ruta, 'rb') as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b''):
            h.update(bloque)
    return h.hexdigest()


def ahora():
    return datetime.now(COLOMBIA)


def nombre_de_copia(momento=None):
    return 'cpstore_' + (momento or ahora()).strftime('%Y%m%d_%H%M%S')


def quitar(ruta):
    """Borra una carpeta temporal sin fallar si ya no existe."""
    shutil.rmtree(ruta, ignore_errors=True)


def _abrir_solo_lectura(ruta):
    return sqlite3.connect(Path(ruta).resolve().as_uri() + '?mode=ro', uri=True, timeout=30)


def _tablas(con):
    return [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def _comillas(nombre):
    return '"' + nombre.replace('"', '""') + '"'


# --- lo que se mide de una base ----------------------------------------------------------------------------------------
def integridad(ruta):
    """PRAGMA integrity_check. Devuelve None si está bien o el texto del problema."""
    try:
        con = _abrir_solo_lectura(ruta)
        try:
            resultado = [r[0] for r in con.execute('PRAGMA integrity_check')]
        finally:
            con.close()
    except sqlite3.DatabaseError as exc:
        return f'no se puede leer como base de datos SQLite ({exc})'
    return None if resultado == ['ok'] else '; '.join(resultado[:5])


def inspeccionar_base(ruta):
    """Versión del esquema, conteos por tabla y totales de control (ventas netas e inventario disponible)."""
    try:
        con = _abrir_solo_lectura(ruta)
    except sqlite3.DatabaseError as exc:
        raise ErrorRespaldo(f'No se pudo abrir la base: {exc}', 3)
    try:
        tablas = _tablas(con)
        conteos = {t: con.execute(f'SELECT COUNT(*) FROM {_comillas(t)}').fetchone()[0] for t in tablas}
        version = None
        if 'schema_version' in tablas:
            versiones = [r[0] for r in con.execute('SELECT version FROM schema_version ORDER BY version')]
            version = {'version': max(versiones) if versiones else None, 'versiones': versiones}
        control = {'ventas_netas': None, 'inventario_disponible': None}
        if 'finance_operation' in tablas:
            n, total = con.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM finance_operation WHERE kind = 'Venta' AND voided = 0").fetchone()
            control['ventas_netas'] = {'operaciones': n, 'total_cents': total}
        if 'equipment' in tablas:
            n, costo = con.execute("SELECT COUNT(*), COALESCE(SUM(cost_cents), 0) FROM equipment WHERE status = 'Disponible' AND archived = 0").fetchone()
            control['inventario_disponible'] = {'equipos': n, 'costo_cents': costo}
        referencias = []
        if 'facturas_lote' in tablas:
            referencias = [{'archivo': a, 'sha256': h} for a, h in con.execute('SELECT archivo, sha256 FROM facturas_lote ORDER BY archivo')]
    except sqlite3.DatabaseError as exc:
        raise ErrorRespaldo(f'La base no se pudo leer: {exc}', 3)
    finally:
        con.close()
    return {'version_esquema': version, 'tablas': conteos, 'control': control, '_facturas': referencias}


def inspeccionar_soportes(carpeta):
    """Archivos de soporte con su huella. Nunca incluye secretos (se listan como excluidos)."""
    archivos, excluidos = [], []
    carpeta = Path(carpeta)
    if carpeta.is_dir():
        for ruta in sorted(p for p in carpeta.rglob('*') if p.is_file()):
            relativa = ruta.relative_to(carpeta).as_posix()
            if es_secreto(ruta.name):
                excluidos.append(relativa)
                continue
            archivos.append({'archivo': relativa, 'bytes': ruta.stat().st_size, 'sha256': sha256_de(ruta)})
    return archivos, excluidos


def coherencia(referencias, soportes):
    """La base dice qué facturas existen y su huella; el disco debe coincidir. Devuelve avisos (puede no haber ninguno)."""
    en_disco = {s['archivo']: s['sha256'] for s in soportes}
    avisos = []
    for r in referencias:
        if r['archivo'] not in en_disco:
            avisos.append(f"La base cita la factura {r['archivo']} pero el archivo no está en la carpeta de soportes.")
        elif en_disco[r['archivo']] != r['sha256']:
            avisos.append(f"La factura {r['archivo']} no coincide con la huella guardada en la base.")
    citados = {r['archivo'] for r in referencias}
    avisos += [f'El archivo {a} está en soportes pero ninguna factura de la base lo cita.' for a in sorted(set(en_disco) - citados)]
    return avisos


# --- copiar ------------------------------------------------------------------------------------------------------------
def _copiar_base_consistente(base, destino):
    """Copia con la API de respaldo de SQLite: consistente aunque otra persona o la aplicación estén usando la base."""
    origen = sqlite3.connect(str(base), timeout=30)
    try:
        copia = sqlite3.connect(str(destino))
        try:
            origen.backup(copia, pages=200, sleep=0.05)
        finally:
            copia.close()
    except sqlite3.OperationalError as exc:
        raise ErrorRespaldo(f'La base está ocupada o no se pudo copiar ({exc}). Inténtalo de nuevo en unos minutos.', 5)
    finally:
        origen.close()


def _copiar_soportes(origen, destino, excluidos_vistos):
    destino.mkdir()
    origen = Path(origen)
    if not origen.is_dir():
        return
    for ruta in sorted(p for p in origen.rglob('*') if p.is_file()):
        if es_secreto(ruta.name):
            excluidos_vistos.append(ruta.relative_to(origen).as_posix())
            continue
        salida = destino / ruta.relative_to(origen)
        salida.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ruta, salida)
        if sha256_de(salida) != sha256_de(ruta):
            raise ErrorRespaldo(f'El archivo {ruta.name} cambió mientras se copiaba. Inténtalo de nuevo.', 5)


def copiar(base, soportes, destino, salida=print, momento=None):
    base, soportes, destino = Path(base).resolve(), Path(soportes).resolve(), Path(destino).resolve()
    if not base.is_file():
        raise ErrorRespaldo(f'No existe la base de datos: {base}')
    if destino == base.parent or destino == soportes or soportes in destino.parents:
        raise ErrorRespaldo('La carpeta de copias no puede ser la carpeta de la base ni estar dentro de la de soportes. '
                            'Elige otra, de preferencia en otro disco.')
    destino.mkdir(parents=True, exist_ok=True)
    avisos = []
    if os.stat(base).st_dev == os.stat(destino).st_dev:
        avisos.append('Las copias están en el mismo disco que la base: si el disco falla, se pierde todo. '
                      'Copia luego la carpeta a otro disco o a un lugar externo.')
    nombre = nombre_de_copia(momento)
    final = destino / nombre
    if final.exists():
        raise ErrorRespaldo(f'Ya existe una copia con ese nombre ({nombre}); espera un segundo y repite. No se sobrescribe.')
    temporal = destino / f'.en_curso_{nombre}_{uuid.uuid4().hex[:8]}'
    try:
        temporal.mkdir()
        copia_base = temporal / NOMBRE_BASE
        _copiar_base_consistente(base, copia_base)
        problema = integridad(copia_base)
        if problema:
            raise ErrorRespaldo(f'La copia de la base no pasó la revisión de integridad: {problema}', 3)
        excluidos = []
        _copiar_soportes(soportes, temporal / CARPETA_SOPORTES, excluidos)
        medidas = inspeccionar_base(copia_base)
        archivos, _ = inspeccionar_soportes(temporal / CARPETA_SOPORTES)
        avisos += coherencia(medidas.pop('_facturas'), archivos)
        verificacion = {'formato': FORMATO, 'motor': 'sqlite', 'creada_en': (momento or ahora()).isoformat(timespec='seconds'),
                        'nombre': nombre, 'version_esquema': medidas['version_esquema'], 'tablas': medidas['tablas'],
                        'control': medidas['control'],
                        'base': {'archivo': NOMBRE_BASE, 'bytes': copia_base.stat().st_size, 'sha256': sha256_de(copia_base)},
                        'soportes': archivos, 'excluidos': sorted(set(excluidos)), 'avisos': avisos,
                        'no_incluye': ['.env', '.session-secret', 'claves (*.pem, *.key...)', 'SECRET_KEY']}
        (temporal / ARCHIVO_VERIFICACION).write_text(json.dumps(verificacion, ensure_ascii=False, indent=2), encoding='utf-8')
        temporal.rename(final)
    except BaseException:
        quitar(temporal)
        raise
    salida(f'Copia creada: {final}')
    salida(f"  Esquema: versión {(verificacion['version_esquema'] or {}).get('version')} · {len(verificacion['tablas'])} tablas · "
           f"{len(archivos)} soporte(s)")
    for texto in (AVISO_SECRETOS, AVISO_DATOS, *avisos):
        salida(texto)
    if excluidos:
        salida(f'  Se omitieron {len(set(excluidos))} archivo(s) con aspecto de clave o secreto: {", ".join(sorted(set(excluidos)))}')
    return {'copia': final, 'verificacion': verificacion}


# --- verificar y restaurar ---------------------------------------------------------------------------------------------
def leer_verificacion(copia):
    copia = Path(copia)
    if not copia.is_dir():
        raise ErrorRespaldo(f'No existe la carpeta de la copia: {copia}')
    ruta = copia / ARCHIVO_VERIFICACION
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise ErrorRespaldo(f'La copia no tiene {ARCHIVO_VERIFICACION}: está incompleta o no es una copia de este programa.', 3)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ErrorRespaldo(f'El archivo {ARCHIVO_VERIFICACION} de la copia está dañado.', 3)
    for clave in ('formato', 'base', 'tablas', 'control', 'soportes', 'version_esquema'):
        if not isinstance(datos, dict) or clave not in datos:
            raise ErrorRespaldo(f'El archivo {ARCHIVO_VERIFICACION} no tiene la sección "{clave}".', 3)
    if datos['formato'] != FORMATO:
        raise ErrorRespaldo(f"Formato de copia {datos['formato']} no reconocido (se esperaba {FORMATO}).", 3)
    return datos


def verificar_copia(copia):
    """Revisa una copia sin restaurarla: huellas, integridad y archivos que sobran o faltan. Lanza ErrorRespaldo si está dañada."""
    copia = Path(copia)
    datos = leer_verificacion(copia)
    problemas = []
    base = copia / datos['base']['archivo']
    if not base.is_file():
        problemas.append('falta el archivo de la base de datos')
    else:
        if sha256_de(base) != datos['base']['sha256']:
            problemas.append('la base de datos no coincide con su huella (el archivo cambió o está dañado)')
        else:
            problema = integridad(base)
            if problema:
                problemas.append(f'la base no pasa la revisión de integridad: {problema}')
    carpeta = copia / CARPETA_SOPORTES
    esperados = {s['archivo']: s for s in datos['soportes']}
    for nombre, s in sorted(esperados.items()):
        ruta = carpeta / nombre
        if not ruta.is_file():
            problemas.append(f'falta el soporte {nombre}')
        elif sha256_de(ruta) != s['sha256']:
            problemas.append(f'el soporte {nombre} no coincide con su huella')
    en_disco = {p.relative_to(carpeta).as_posix() for p in carpeta.rglob('*') if p.is_file()} if carpeta.is_dir() else set()
    for sobra in sorted(en_disco - set(esperados)):
        problemas.append(f'hay un archivo que no figura en la verificación: {sobra}')
    if problemas:
        raise ErrorRespaldo('La copia está dañada o fue modificada:\n  - ' + '\n  - '.join(problemas), 3)
    return datos


def _comparar(esperado, real, etiqueta):
    return {'prueba': etiqueta, 'ok': esperado == real, 'esperado': esperado, 'real': real}


def verificar_restauracion(restaurado, datos):
    """Compara lo restaurado con lo que decía la copia. Devuelve la lista de pruebas (cada una con ok verdadero o falso)."""
    base = Path(restaurado) / datos['base']['archivo']
    problema = integridad(base)
    medidas = inspeccionar_base(base)
    archivos, _ = inspeccionar_soportes(Path(restaurado) / CARPETA_SOPORTES)
    pruebas = [
        {'prueba': 'PRAGMA integrity_check', 'ok': problema is None, 'esperado': 'ok', 'real': problema or 'ok'},
        _comparar(datos['version_esquema'], medidas['version_esquema'], 'Versión del esquema (schema_version)'),
        _comparar(datos['tablas'], medidas['tablas'], 'Conteos por tabla'),
        _comparar(datos['control']['ventas_netas'], medidas['control']['ventas_netas'], 'Total de control: ventas netas'),
        _comparar(datos['control']['inventario_disponible'], medidas['control']['inventario_disponible'],
                  'Total de control: inventario disponible'),
        _comparar([(s['archivo'], s['sha256']) for s in datos['soportes']], [(s['archivo'], s['sha256']) for s in archivos],
                  'Huellas de los soportes'),
        _comparar(datos['base']['sha256'], sha256_de(base), 'Huella de la base'),
    ]
    return pruebas


def _detalle_de_fallos(pruebas):
    lineas = []
    for p in pruebas:
        if not p['ok']:
            lineas.append(f"{p['prueba']}: esperado {json.dumps(p['esperado'], ensure_ascii=False)[:300]}, "
                          f"obtenido {json.dumps(p['real'], ensure_ascii=False)[:300]}")
    return lineas


def restaurar(copia, destino, salida=print):
    copia, destino = Path(copia).resolve(), Path(destino).resolve()
    if destino.exists():
        raise ErrorRespaldo(f'El destino ya existe: {destino}\nLa restauración nunca sobrescribe. Elige una ruta nueva que no exista.')
    if copia in destino.parents or destino == copia:
        raise ErrorRespaldo('El destino no puede estar dentro de la copia.')
    if not destino.parent.is_dir():
        raise ErrorRespaldo(f'La carpeta superior del destino no existe: {destino.parent}')
    datos = verificar_copia(copia)  # si la copia está dañada, se corta aquí: todavía no se creó nada
    temporal = destino.parent / f'.restaurando_{destino.name}_{uuid.uuid4().hex[:8]}'
    try:
        temporal.mkdir()
        shutil.copy2(copia / datos['base']['archivo'], temporal / datos['base']['archivo'])
        if (copia / CARPETA_SOPORTES).is_dir():
            shutil.copytree(copia / CARPETA_SOPORTES, temporal / CARPETA_SOPORTES)
        else:
            (temporal / CARPETA_SOPORTES).mkdir()
        pruebas = verificar_restauracion(temporal, datos)
        fallos = _detalle_de_fallos(pruebas)
        if fallos:
            raise ErrorRespaldo('La restauración no coincide con la copia; no se dejó nada:\n  - ' + '\n  - '.join(fallos), 4)
        temporal.rename(destino)
    except BaseException:
        quitar(temporal)
        raise
    salida(f'Restauración lista y verificada en: {destino}')
    for p in pruebas:
        salida(f"  [{'OK' if p['ok'] else 'FALLA'}] {p['prueba']}")
    c = datos['control']
    if c['ventas_netas']:
        salida(f"  Ventas netas: {c['ventas_netas']['operaciones']} operaciones, {c['ventas_netas']['total_cents']} centavos")
    if c['inventario_disponible']:
        salida(f"  Inventario disponible: {c['inventario_disponible']['equipos']} equipos, {c['inventario_disponible']['costo_cents']} centavos")
    salida('Esta restauración está en una carpeta aparte: no reemplazó nada. Para usarla, sigue docs/RECUPERACION.md.')
    return {'destino': destino, 'pruebas': pruebas, 'verificacion': datos}


# --- línea de comandos -------------------------------------------------------------------------------------------------
def _ruta_base_por_defecto():
    valor = os.environ.get('DATABASE_PATH')
    return (RAIZ / valor) if valor else RAIZ / 'instance' / 'cpstore.sqlite'


def main(argv=None):
    p = argparse.ArgumentParser(prog='respaldo.py', description='Respaldo y restauración de CP Store (SQLite).')
    sub = p.add_subparsers(dest='orden', required=True)
    c = sub.add_parser('copiar', help='crea una copia nueva con fecha y hora')
    c.add_argument('--destino', required=True, help='carpeta donde se guardan las copias (de preferencia en otro disco)')
    c.add_argument('--base', default=None, help='base SQLite (por defecto DATABASE_PATH o instance/cpstore.sqlite)')
    c.add_argument('--soportes', default=None, help='carpeta de soportes (por defecto instance/facturas)')
    v = sub.add_parser('verificar', help='revisa una copia sin restaurarla')
    v.add_argument('--copia', required=True)
    r = sub.add_parser('restaurar', help='restaura una copia en una ruta NUEVA y la verifica')
    r.add_argument('--copia', required=True)
    r.add_argument('--destino', required=True, help='ruta nueva; si ya existe, el programa se niega a seguir')
    a = p.parse_args(argv)
    try:
        if a.orden == 'copiar':
            copiar(a.base or _ruta_base_por_defecto(), a.soportes or RAIZ / 'instance' / 'facturas', a.destino)
        elif a.orden == 'verificar':
            datos = verificar_copia(a.copia)
            print(f"La copia está íntegra: {datos['nombre'] if 'nombre' in datos else Path(a.copia).name} · "
                  f"{len(datos['tablas'])} tablas · {len(datos['soportes'])} soporte(s).")
        else:
            restaurar(a.copia, a.destino)
    except ErrorRespaldo as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return exc.codigo
    except OSError as exc:
        print(f'ERROR: no se pudo completar la operación ({exc}). No se dejaron archivos a medias.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
