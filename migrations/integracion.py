"""Campos aditivos para personas y operaciones; conserva registros y pagos."""
import sqlite3
import json
import unicodedata
from pathlib import Path


def upgrade(path):
    with sqlite3.connect(path) as conn:
        if conn.execute('SELECT 1 FROM schema_version WHERE version=11').fetchone():
            return
        backup=Path(str(path)+'.antes_integracion.bak')
        if not backup.exists():
            with sqlite3.connect(backup) as safe_copy:
                conn.backup(safe_copy)
        conn.execute('BEGIN')
        for table, name, definition in (
            ('personas_contables','declaro_renta_antes','BOOLEAN NOT NULL DEFAULT 0'),
            ('finance_operation','person_id','INTEGER REFERENCES personas_contables(id)'),
            ('equipment','person_id','INTEGER REFERENCES personas_contables(id)'),
        ):
            columns={row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
            if name not in columns:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
        for day_id, raw in conn.execute("SELECT id,config FROM finance_day WHERE status='Abierta'"):
            config=json.loads(raw)
            if config.get('opening')!=20000000:
                before=config.get('opening')
                config['opening']=20000000
                conn.execute('UPDATE finance_day SET config=?,revision=revision+1 WHERE id=?',
                             (json.dumps(config,ensure_ascii=False),day_id))
                conn.execute('INSERT INTO finance_audit(day_id,action,reason,detail) VALUES(?,?,?,?)',
                             (day_id,'Migración base fija','Base de caja establecida en $200.000',
                              json.dumps({'before':before,'after':20000000})))
        conn.execute('INSERT INTO schema_version(version) VALUES(11)')


def upgrade_v12(path):
    """Retomas y conciliación financiera individual sin modificar datos anteriores."""
    with sqlite3.connect(path) as conn:
        if conn.execute('SELECT 1 FROM schema_version WHERE version=12').fetchone():
            return
        backup=Path(str(path)+'.antes_pool_y_consignaciones.bak')
        if not backup.exists():
            with sqlite3.connect(backup) as safe_copy:
                conn.backup(safe_copy)
        conn.execute('BEGIN')
        for table,name,definition in (
            ('equipment','source_type',"TEXT NOT NULL DEFAULT 'Lote'"),
            ('equipment','purchase_cop_cents','INTEGER'),
            ('equipment','additional_costs','JSON'),
            ('consignaciones_bancarias','finance_operation_id','INTEGER REFERENCES finance_operation(id)'),
            ('consignaciones_bancarias','payment_index','INTEGER'),
            ('consignaciones_bancarias','supplier_payment_id','INTEGER REFERENCES finance_supplier_payment(id)'),
            ('consignaciones_bancarias','activa','BOOLEAN NOT NULL DEFAULT 1'),
            ('finance_supplier_payment','person_id','INTEGER REFERENCES personas_contables(id)'),
            ('finance_supplier_payment','bank_id','INTEGER REFERENCES bancos_destino(id)'),
        ):
            if name not in {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS ux_consignacion_finance_payment ON consignaciones_bancarias(finance_operation_id,payment_index)')
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS ux_consignacion_supplier_payment ON consignaciones_bancarias(supplier_payment_id)')
        for name in ('CP CELULARES','CP VARIOS','CP HIDROGELES','BATERÍAS','MEMORIAS'):
            key=''.join(c for c in unicodedata.normalize('NFKD',name.casefold()) if c.isascii() and c.isalnum())
            conn.execute("INSERT OR IGNORE INTO catalog(kind,name,normal_key,parent_id,active) VALUES('supplier',?,?,0,1)",(name,key))
        conn.execute("INSERT OR IGNORE INTO catalog(kind,name,normal_key,parent_id,active) VALUES('location','LOCAL CP STORE','localcpstore',0,1)")
        for day_id,raw in conn.execute("SELECT id,config FROM finance_day WHERE status='Abierta'"):
            cfg=json.loads(raw)
            before=cfg.get('accounts',[])
            cfg['accounts']=['EFECTIVO','TRANSFERENCIA','DATÁFONO']
            if before!=cfg['accounts']:
                conn.execute('UPDATE finance_day SET config=?,revision=revision+1 WHERE id=?',
                             (json.dumps(cfg,ensure_ascii=False),day_id))
                conn.execute('INSERT INTO finance_audit(day_id,action,reason,detail) VALUES(?,?,?,?)',
                             (day_id,'Actualización de medios','Medios nuevos identificados por persona y banco',
                              json.dumps({'before':before,'after':cfg['accounts']},ensure_ascii=False)))
        conn.execute('INSERT INTO schema_version(version) VALUES(12)')


def upgrade_v13(path):
    """Asocia los bancos de consignaciones existentes con cada persona."""
    with sqlite3.connect(path) as conn:
        if conn.execute('SELECT 1 FROM schema_version WHERE version=13').fetchone():
            return
        backup=Path(str(path)+'.antes_bancos_persona.bak')
        if not backup.exists():
            with sqlite3.connect(backup) as safe_copy:
                conn.backup(safe_copy)
        conn.execute('BEGIN')
        conn.execute('''CREATE TABLE IF NOT EXISTS persona_banco (
            id INTEGER PRIMARY KEY, persona_id INTEGER NOT NULL REFERENCES personas_contables(id),
            banco_id INTEGER NOT NULL REFERENCES bancos_destino(id),
            CONSTRAINT uq_persona_banco UNIQUE(persona_id,banco_id))''')
        conn.execute('CREATE INDEX IF NOT EXISTS ix_persona_banco_persona_id ON persona_banco(persona_id)')
        conn.execute('''INSERT OR IGNORE INTO persona_banco(persona_id,banco_id)
            SELECT DISTINCT persona_id,banco_id FROM consignaciones_bancarias
            WHERE persona_id IS NOT NULL AND banco_id IS NOT NULL''')
        conn.execute('''INSERT OR IGNORE INTO persona_banco(persona_id,banco_id)
            SELECT DISTINCT person_id,bank_id FROM finance_supplier_payment
            WHERE person_id IS NOT NULL AND bank_id IS NOT NULL''')
        conn.execute('INSERT INTO schema_version(version) VALUES(13)')
