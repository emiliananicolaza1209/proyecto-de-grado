#!/usr/bin/env python3
"""Respaldo y restauración de CP Store con PostgreSQL (pg_dump y pg_restore).

*** SIN PROBAR ***  Esta variante se escribió siguiendo la misma lógica del respaldo de SQLite (que sí está probado), pero NO se ha
ejecutado contra una base PostgreSQL real: en el equipo donde se escribió no hay PostgreSQL ni sus herramientas. Pruébala primero
en una base de ensayo, en un entorno separado, y revisa el resultado antes de confiar en ella. Solo la lectura de la variable de
entorno, el armado de las órdenes y las protecciones están cubiertos por pruebas automáticas (con las herramientas simuladas).

La URL de conexión se lee de una variable de entorno (por defecto CPSTORE_PG_URL, formato postgresql://usuario:clave@servidor:5432/base).
Nunca se escribe en un archivo, ni en la línea de órdenes, ni en pantalla: se reparte en las variables PGHOST, PGPORT, PGUSER,
PGPASSWORD y PGDATABASE solo para los procesos hijos.

    python scripts/respaldo_postgres.py copiar    --destino D:\\Respaldos\\CPStore
    python scripts/respaldo_postgres.py verificar --copia   D:\\Respaldos\\CPStore\\cpstore_20261112_180000
    python scripts/respaldo_postgres.py restaurar --copia   ...cpstore_20261112_180000 --base-nueva cpstore_prueba --soportes-destino D:\\Prueba\\soportes

Requiere las herramientas cliente de PostgreSQL en el PATH: pg_dump, pg_restore, psql, createdb y dropdb.
Igual que en SQLite: no copia .env, claves ni SECRET_KEY; la restauración nunca sobrescribe (crea una base NUEVA y se niega si ya existe).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import unquote, urlsplit, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent))
import respaldo as base_comun  # noqa: E402  (mismas funciones de huellas, soportes y avisos que el respaldo de SQLite)
from respaldo import ErrorRespaldo  # noqa: E402

VARIABLE_POR_DEFECTO = 'CPSTORE_PG_URL'
NOMBRE_DUMP = 'base.dump'
AVISO_SIN_PROBAR = ('ATENCIÓN: la variante de PostgreSQL está SIN PROBAR. Pruébala en una base de ensayo antes de usarla '
                    'con datos reales.')
NOMBRE_VALIDO = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,62}$')
HERRAMIENTAS = ('pg_dump', 'pg_restore', 'psql', 'createdb', 'dropdb')


def entorno_desde_url(variable=VARIABLE_POR_DEFECTO, entorno=None):
    """Devuelve (entorno para los procesos hijos, nombre de la base). La clave solo viaja en PGPASSWORD."""
    entorno = os.environ if entorno is None else entorno
    url = entorno.get(variable)
    if not url:
        raise ErrorRespaldo(f'Falta la variable de entorno {variable} con la URL de PostgreSQL '
                            '(postgresql://usuario:clave@servidor:5432/base). No la escribas en archivos.')
    partes = urlsplit(url)
    if not partes.scheme.startswith('postgres') or not partes.hostname or not partes.path.strip('/'):
        raise ErrorRespaldo(f'La variable {variable} no tiene el formato postgresql://usuario:clave@servidor:puerto/base.')
    hijo = {k: v for k, v in os.environ.items() if not k.startswith('PG')}
    hijo.update(PGHOST=partes.hostname, PGPORT=str(partes.port or 5432), PGDATABASE=unquote(partes.path.strip('/')))
    if partes.username:
        hijo['PGUSER'] = unquote(partes.username)
    if partes.password:
        hijo['PGPASSWORD'] = unquote(partes.password)
    modo = parse_qs(partes.query).get('sslmode')
    if modo:
        hijo['PGSSLMODE'] = modo[0]
    return hijo, hijo['PGDATABASE']


def ejecutar(orden, entorno, entrada=None):
    """Corre una herramienta de PostgreSQL. La orden nunca lleva la URL ni la clave."""
    try:
        r = subprocess.run(orden, env=entorno, capture_output=True, text=True, input=entrada, check=False)
    except FileNotFoundError:
        raise ErrorRespaldo(f'No se encontró {orden[0]}. Instala las herramientas cliente de PostgreSQL ({", ".join(HERRAMIENTAS)}) '
                            'y agrégalas al PATH.')
    if r.returncode != 0:
        detalle = (r.stderr or r.stdout or '').strip().splitlines()[-3:]
        raise ErrorRespaldo(f'{orden[0]} terminó con error ({r.returncode}): ' + ' | '.join(detalle), 5)
    return r.stdout


def _consulta(sql, entorno, **variables):
    orden = ['psql', '--no-psqlrc', '-At', '-v', 'ON_ERROR_STOP=1']
    for k, v in variables.items():
        orden += ['-v', f'{k}={v}']
    return ejecutar(orden + ['-f', '-'], entorno, entrada=sql + ';\n').strip()  # por stdin: así psql sí interpola :'variable'


def medir(entorno):
    """Conteos por tabla y totales de control, equivalentes a los del respaldo de SQLite."""
    tablas = [t for t in _consulta("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1", entorno).splitlines() if t]
    conteos = {t: int(_consulta(f'SELECT COUNT(*) FROM "{t}"', entorno)) for t in tablas}
    control = {'ventas_netas': None, 'inventario_disponible': None}
    version = None
    if 'finance_operation' in tablas:
        n, total = _consulta("SELECT COUNT(*) || ',' || COALESCE(SUM(amount), 0) FROM finance_operation "
                             "WHERE kind = 'Venta' AND NOT voided", entorno).split(',')
        control['ventas_netas'] = {'operaciones': int(n), 'total_cents': int(total)}
    if 'equipment' in tablas:
        n, costo = _consulta("SELECT COUNT(*) || ',' || COALESCE(SUM(cost_cents), 0) FROM equipment "
                             "WHERE status = 'Disponible' AND archived = 0", entorno).split(',')
        control['inventario_disponible'] = {'equipos': int(n), 'costo_cents': int(costo)}
    if 'schema_version' in tablas:
        versiones = [int(v) for v in _consulta('SELECT version FROM schema_version ORDER BY 1', entorno).splitlines() if v]
        version = {'version': max(versiones) if versiones else None, 'versiones': versiones}
    return {'tablas': conteos, 'control': control, 'version_esquema': version}


def copiar(soportes, destino, variable=VARIABLE_POR_DEFECTO, salida=print):
    salida(AVISO_SIN_PROBAR)
    entorno, nombre_db = entorno_desde_url(variable)
    destino, soportes = Path(destino).resolve(), Path(soportes).resolve()
    if destino == soportes or soportes in destino.parents:
        raise ErrorRespaldo('La carpeta de copias no puede estar dentro de la de soportes.')
    destino.mkdir(parents=True, exist_ok=True)
    nombre = base_comun.nombre_de_copia()
    final = destino / nombre
    if final.exists():
        raise ErrorRespaldo(f'Ya existe una copia con ese nombre ({nombre}). No se sobrescribe.')
    temporal = destino / f'.en_curso_{nombre}_{uuid.uuid4().hex[:8]}'
    try:
        temporal.mkdir()
        volcado = temporal / NOMBRE_DUMP
        ejecutar(['pg_dump', '--format=custom', '--no-owner', '--no-privileges', '--file', str(volcado)], entorno)
        ejecutar(['pg_restore', '--list', str(volcado)], entorno)  # comprueba que el volcado se puede leer
        medidas = medir(entorno)
        excluidos = []
        base_comun._copiar_soportes(soportes, temporal / base_comun.CARPETA_SOPORTES, excluidos)
        archivos, _ = base_comun.inspeccionar_soportes(temporal / base_comun.CARPETA_SOPORTES)
        verificacion = {'formato': base_comun.FORMATO, 'motor': 'postgresql', 'sin_probar': True, 'nombre': nombre,
                        'creada_en': base_comun.ahora().isoformat(timespec='seconds'), 'base_origen': nombre_db,
                        'version_esquema': medidas['version_esquema'], 'tablas': medidas['tablas'], 'control': medidas['control'],
                        'base': {'archivo': NOMBRE_DUMP, 'bytes': volcado.stat().st_size, 'sha256': base_comun.sha256_de(volcado)},
                        'soportes': archivos, 'excluidos': sorted(set(excluidos)), 'avisos': [AVISO_SIN_PROBAR],
                        'no_incluye': ['.env', 'claves', 'SECRET_KEY', 'la URL de conexión']}
        (temporal / base_comun.ARCHIVO_VERIFICACION).write_text(json.dumps(verificacion, ensure_ascii=False, indent=2), encoding='utf-8')
        temporal.rename(final)
    except BaseException:
        base_comun.quitar(temporal)
        raise
    salida(f'Copia creada: {final}')
    salida(base_comun.AVISO_SECRETOS)
    salida(base_comun.AVISO_DATOS)
    return {'copia': final, 'verificacion': verificacion}


def verificar_copia(copia, entorno=None):
    """Huellas del volcado y de los soportes; con ``entorno`` también comprueba que pg_restore pueda listarlo."""
    copia = Path(copia)
    datos = base_comun.leer_verificacion(copia)
    if datos.get('motor') != 'postgresql':
        raise ErrorRespaldo('Esta copia no es de PostgreSQL; usa scripts/respaldo.py.', 3)
    problemas = []
    volcado = copia / datos['base']['archivo']
    if not volcado.is_file():
        problemas.append('falta el volcado de la base')
    elif base_comun.sha256_de(volcado) != datos['base']['sha256']:
        problemas.append('el volcado no coincide con su huella')
    carpeta = copia / base_comun.CARPETA_SOPORTES
    for s in datos['soportes']:
        ruta = carpeta / s['archivo']
        if not ruta.is_file():
            problemas.append(f"falta el soporte {s['archivo']}")
        elif base_comun.sha256_de(ruta) != s['sha256']:
            problemas.append(f"el soporte {s['archivo']} no coincide con su huella")
    if problemas:
        raise ErrorRespaldo('La copia está dañada o fue modificada:\n  - ' + '\n  - '.join(problemas), 3)
    if entorno is not None:
        ejecutar(['pg_restore', '--list', str(volcado)], entorno)
    return datos


def restaurar(copia, base_nueva, soportes_destino, variable=VARIABLE_POR_DEFECTO, salida=print):
    salida(AVISO_SIN_PROBAR)
    entorno, base_actual = entorno_desde_url(variable)
    if not NOMBRE_VALIDO.match(base_nueva or ''):
        raise ErrorRespaldo('El nombre de la base nueva solo puede tener letras, números y guion bajo (máximo 63).')
    if base_nueva == base_actual:
        raise ErrorRespaldo('La base nueva no puede ser la base actual: la restauración nunca sobrescribe.')
    soportes_destino = Path(soportes_destino).resolve()
    if soportes_destino.exists():
        raise ErrorRespaldo(f'El destino de los soportes ya existe: {soportes_destino}. No se sobrescribe.')
    if not soportes_destino.parent.is_dir():
        raise ErrorRespaldo(f'La carpeta superior del destino no existe: {soportes_destino.parent}')
    existe = _consulta("SELECT 1 FROM pg_database WHERE datname = :'n'", entorno, n=base_nueva)
    if existe:
        raise ErrorRespaldo(f'Ya existe una base llamada {base_nueva}. La restauración nunca sobrescribe; elige otro nombre.')
    datos = verificar_copia(copia, entorno)  # si la copia está dañada, se corta antes de crear nada
    copia = Path(copia).resolve()
    temporal = soportes_destino.parent / f'.restaurando_{soportes_destino.name}_{uuid.uuid4().hex[:8]}'
    creada = False
    try:
        ejecutar(['createdb', '--maintenance-db=postgres', base_nueva], entorno)
        creada = True
        nuevo = dict(entorno, PGDATABASE=base_nueva)
        ejecutar(['pg_restore', '--no-owner', '--no-privileges', '--dbname', base_nueva, str(copia / datos['base']['archivo'])], nuevo)
        import shutil
        if (copia / base_comun.CARPETA_SOPORTES).is_dir():
            shutil.copytree(copia / base_comun.CARPETA_SOPORTES, temporal)
        else:
            temporal.mkdir()
        real = medir(nuevo)
        archivos, _ = base_comun.inspeccionar_soportes(temporal)
        pruebas = [base_comun._comparar(datos['version_esquema'], real['version_esquema'], 'Versión del esquema'),
                   base_comun._comparar(datos['tablas'], real['tablas'], 'Conteos por tabla'),
                   base_comun._comparar(datos['control']['ventas_netas'], real['control']['ventas_netas'], 'Control: ventas netas'),
                   base_comun._comparar(datos['control']['inventario_disponible'], real['control']['inventario_disponible'],
                                        'Control: inventario disponible'),
                   base_comun._comparar([(s['archivo'], s['sha256']) for s in datos['soportes']],
                                        [(s['archivo'], s['sha256']) for s in archivos], 'Huellas de los soportes')]
        fallos = base_comun._detalle_de_fallos(pruebas)
        if fallos:
            raise ErrorRespaldo('La restauración no coincide con la copia; se deshizo:\n  - ' + '\n  - '.join(fallos), 4)
        temporal.rename(soportes_destino)
    except BaseException:
        base_comun.quitar(temporal)
        if creada:
            try:
                ejecutar(['dropdb', '--maintenance-db=postgres', '--if-exists', base_nueva], entorno)
            except ErrorRespaldo:
                salida(f'No se pudo borrar la base {base_nueva} creada a medias; bórrala a mano.')
        raise
    salida(f'Restauración verificada en la base nueva {base_nueva} y los soportes en {soportes_destino}.')
    for p in pruebas:
        salida(f"  [{'OK' if p['ok'] else 'FALLA'}] {p['prueba']}")
    return {'base': base_nueva, 'soportes': soportes_destino, 'pruebas': pruebas}


def main(argv=None):
    p = argparse.ArgumentParser(prog='respaldo_postgres.py', description='Respaldo y restauración con PostgreSQL (SIN PROBAR).')
    p.add_argument('--variable', default=VARIABLE_POR_DEFECTO, help='variable de entorno con la URL (por defecto CPSTORE_PG_URL)')
    sub = p.add_subparsers(dest='orden', required=True)
    c = sub.add_parser('copiar')
    c.add_argument('--destino', required=True)
    c.add_argument('--soportes', default=None)
    v = sub.add_parser('verificar')
    v.add_argument('--copia', required=True)
    r = sub.add_parser('restaurar')
    r.add_argument('--copia', required=True)
    r.add_argument('--base-nueva', required=True)
    r.add_argument('--soportes-destino', required=True)
    a = p.parse_args(argv)
    try:
        if a.orden == 'copiar':
            copiar(a.soportes or base_comun.RAIZ / 'instance' / 'facturas', a.destino, a.variable)
        elif a.orden == 'verificar':
            print(AVISO_SIN_PROBAR)
            entorno, _ = entorno_desde_url(a.variable)
            verificar_copia(a.copia, entorno)
            print('La copia está íntegra.')
        else:
            restaurar(a.copia, a.base_nueva, a.soportes_destino, a.variable)
    except ErrorRespaldo as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return exc.codigo
    except OSError as exc:
        print(f'ERROR: no se pudo completar la operación ({exc}).', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
