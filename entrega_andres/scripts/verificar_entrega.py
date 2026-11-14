"""Compara archivos o metadatos PostgreSQL. No importa ni inicia la aplicación.

Conexión en READ ONLY; no lee filas comerciales. La única fila de aplicación
consultada es la revisión técnica cp_schema_revision.version.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


def compare_source(root, manifest):
    missing, different, matched = [], [], 0
    for relative, expected in manifest['files'].items():
        path = root / relative
        if not path.is_file():
            missing.append(relative)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            different.append(relative)
        else:
            matched += 1
    extras = sorted(str(p.relative_to(root)).replace('\\', '/')
                    for p in (root / 'app').rglob('*.py')
                    if str(p.relative_to(root)).replace('\\', '/') not in manifest['files'])
    return {'mode': 'codigo', 'status': 'diferencias' if missing or different or extras else 'coincide_base',
            'matched_files': matched, 'missing_files': missing,
            'different_files': different, 'additional_python_files': extras,
            'note': 'Comparación de bytes, no de equivalencia funcional. Cambios CRLF/LF también difieren. No certifica que sea el commit más reciente.'}


def compare_columns(expected, actual):
    lookup = {(r['table_name'], r['column_name']): r for r in actual}
    actual_tables = {r['table_name'] for r in actual}
    expected_tables = {t['table'] for t in expected}
    missing_columns, type_changes, nullable_changes, extra_columns = [], [], [], []
    pgtypes = {'db.Integer': 'integer', 'db.BigInteger': 'bigint', 'db.String': 'character varying',
               'db.Boolean': 'boolean', 'db.JSON': 'json', 'db.Numeric': 'numeric',
               'db.DateTime': 'timestamp without time zone', 'db.Date': 'date', 'db.Text': 'text'}
    for t in expected:
        for c in t['columns']:
            key = (t['table'], c['name'])
            if key not in lookup:
                missing_columns.append('.'.join(key))
                continue
            a = lookup[key]
            decl = c['type_declaration'].split('(')[0]
            target = pgtypes.get(decl)
            if target and a['data_type'] != target:
                type_changes.append({'field': '.'.join(key), 'declared_type': target, 'database_type': a['data_type']})
            if (a['is_nullable'] == 'YES') != c['nullable']:
                nullable_changes.append('.'.join(key))
        names = {c['name'] for c in t['columns']}
        extra_columns.extend(t['table']+'.'+r['column_name'] for r in actual
                             if r['table_name'] == t['table'] and r['column_name'] not in names)
    return {'missing_tables': sorted(expected_tables - actual_tables),
            'additional_tables': sorted(actual_tables - expected_tables - {'cp_schema_revision'}),
            'missing_columns': missing_columns, 'additional_columns': extra_columns,
            'different_types': type_changes, 'different_nullability': nullable_changes,
            'expected_app_tables': len(expected_tables),
            'visible_expected_app_tables': len(expected_tables & actual_tables)}


def inspect_database(env_file, schema, expected):
    # These imports are deliberately absent in source-comparison mode.
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row
    from dotenv import dotenv_values
    from urllib.parse import urlsplit, parse_qsl, urlencode, urlunsplit

    raw = dotenv_values(env_file).get('DATABASE_URL')
    if not raw:
        raise ValueError('DATABASE_URL ausente')
    raw = raw.replace('postgresql+psycopg://', 'postgresql://', 1)
    parsed = urlsplit(raw)
    if parsed.scheme not in ('postgresql', 'postgres'):
        raise ValueError('No es PostgreSQL')
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if (parsed.hostname or '').endswith('.render.com') and not query.get('sslmode'):
        query['sslmode'] = 'require'
    raw = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
    # libpq startup settings apply BEFORE any SQL transaction. The connection
    # is short-lived and only SELECT statements below are issued.
    with psycopg.connect(raw, connect_timeout=10, row_factory=dict_row,
                         options='-c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=5000 -c timezone=UTC') as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute("SELECT current_setting('transaction_read_only') AS read_only")
            if cur.fetchone()['read_only'] != 'on':
                raise RuntimeError('Read only no confirmado')
            cur.execute('''SELECT table_name, column_name, data_type, is_nullable,
                                  character_maximum_length, numeric_precision, numeric_scale
                             FROM information_schema.columns
                            WHERE table_schema = %s
                            ORDER BY table_name, ordinal_position''', (schema,))
            columns = cur.fetchall()
            cur.execute('''SELECT t.relname AS table_name, c.conname AS constraint_name,
                                  c.contype AS constraint_type,
                                  CASE WHEN c.confrelid <> 0 THEN c.confrelid::regclass::text ELSE NULL END AS target_table,
                                  ARRAY(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY k(num, pos)
                                        JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.num
                                        ORDER BY k.pos) AS columns,
                                  ARRAY(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY k(num, pos)
                                        JOIN pg_attribute a ON a.attrelid=c.confrelid AND a.attnum=k.num
                                        ORDER BY k.pos) AS target_columns
                             FROM pg_constraint c
                             JOIN pg_class t ON t.oid=c.conrelid
                             JOIN pg_namespace n ON n.oid=t.relnamespace
                            WHERE n.nspname=%s ORDER BY t.relname,c.conname''', (schema,))
            constraints = cur.fetchall()
            cur.execute('''SELECT t.relname AS table_name, ix.relname AS index_name,
                                  i.indisunique AS unique_index, i.indisvalid AS valid_index
                             FROM pg_index i JOIN pg_class t ON t.oid=i.indrelid
                             JOIN pg_class ix ON ix.oid=i.indexrelid
                             JOIN pg_namespace n ON n.oid=t.relnamespace
                            WHERE n.nspname=%s ORDER BY t.relname,ix.relname''', (schema,))
            indexes = cur.fetchall()
            revisions = []
            if any(r['table_name'] == 'cp_schema_revision' and r['column_name'] == 'version' for r in columns):
                cur.execute(sql.SQL('SELECT version FROM {}.{} LIMIT 10').format(
                    sql.Identifier(schema), sql.Identifier('cp_schema_revision')))
                revisions = [r['version'] for r in cur.fetchall()]
        conn.rollback()
    diff = compare_columns(expected, columns)
    changes = any(diff[k] for k in ('missing_tables', 'additional_tables', 'missing_columns',
                                   'additional_columns', 'different_types', 'different_nullability'))
    return {'mode': 'postgresql_metadatos', 'status': 'requiere_revision' if changes or revisions != [1] else 'estructura_basica_coincide',
            'schema': schema, 'read_only_confirmed': True, 'schema_revisions': revisions,
            'comparison': diff, 'columns': columns, 'constraints': constraints, 'indexes': indexes,
            'limitations': ['No inspecciona filas comerciales ni datos JSON.',
                            'Permisos insuficientes pueden ocultar tablas o columnas.',
                            'Restricciones e índices se listan para revisión; no se comparan automáticamente con todos los modelos.',
                            'Longitudes y precisión se listan; no se validan automáticamente.',
                            'No comprueba reglas, rendimiento, integridad de datos, privilegios de roles ni disponibilidad de respaldos.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--source-root', type=Path)
    mode.add_argument('--env-file', type=Path)
    parser.add_argument('--schema', default='public')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.source_root:
            manifest = json.loads((BASE/'tecnico/version_base.json').read_text(encoding='utf-8'))
            report = compare_source(args.source_root.resolve(), manifest)
        else:
            if not args.env_file.is_file():
                raise FileNotFoundError('Archivo de configuración ausente')
            if args.out.resolve() == args.env_file.resolve():
                raise ValueError('El reporte no puede reemplazar la configuración')
            expected = json.loads((BASE/'tecnico/esquema_modelos.json').read_text(encoding='utf-8'))['tables']
            report = inspect_database(args.env_file, args.schema, expected)
        report['generated_at_utc'] = datetime.now(timezone.utc).isoformat()
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str)+'\n', encoding='utf-8')
        print('Informe guardado. Estado: '+report['status'])
        return 0 if report['status'] in ('coincide_base','estructura_basica_coincide') else 2
    except ImportError:
        print('Falta una dependencia. Usa el Python del entorno .venv con psycopg y python-dotenv instalados.', file=sys.stderr)
        return 3
    except Exception as exc:
        # Do not print the exception: connection errors may expose host/user or URL.
        print('No se completó la revisión ('+type(exc).__name__+'). Comprueba ruta, dependencias, conexión y permisos. No compartas DATABASE_URL.', file=sys.stderr)
        return 4


if __name__ == '__main__':
    raise SystemExit(main())
