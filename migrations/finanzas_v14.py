"""Categoría de proveedores y datáfono identificado por persona sin banco ficticio."""
import sqlite3
from app.sqlite_resources import sqlite_connection
import re
import unicodedata
from pathlib import Path

CELULARES = '''CURI|COSTEÑOS|ESMERALDA|MOLL|TATIANA|ALEJA|SOFÍA|DIGITAL|JUAN MANUEL|CARLOS|WILFRIDO BUCACENTRO|J MAX|TECNO SÚPER|MOMPIS ELECTROWORD|YESICA-ÉDGAR|GABRIEL|CP CELULARES|OTROS|VIRTUAL THES|DAVID|CAMILO|SEÑOR CARLOS|LA DIGITAL|MEGACELL SELENE|MEGACELL MONA|JEFE JONATAN'''.split('|')
ACCESORIOS = '''CP VARIOS|CP HIDRÓGEL|FLACO|GABRIEL|CRIS|CRIS GRATAMIRA|TOCAYO|JANDEL|CARLOS|GRATAMIRA ACCESORIOS|CP MEMORIAS|REPUESTOS JMAX|REPUESTOS TECNOPARK|REPUESTOS CAKU|REPUESTOS MUNDO|REPUESTOS OTROS|ROXON|CP BATERÍAS|JEFE JON|ELÍAS SOFWARE|MOLL|YESICA-ÉDGAR|SEÑORA MARTHA|DIGITAL|FUDI|OTROS|DAVID|PUNTAZO DE LA 15'''.split('|')


def key(name):
    plain=''.join(c for c in unicodedata.normalize('NFKD',name.casefold()) if not unicodedata.combining(c))
    return re.sub('[^a-z0-9]','',plain)


def upgrade(path):
    with sqlite_connection(path) as conn:
        if conn.execute('SELECT 1 FROM schema_version WHERE version=14').fetchone():return
        backup=Path(str(path)+'.antes_finanzas_v14.bak')
        if not backup.exists():
            with sqlite_connection(backup) as copy:conn.backup(copy)
        conn.execute('PRAGMA foreign_keys=OFF')
        conn.execute('BEGIN')
        if 'supplier_category' not in {r[1] for r in conn.execute('PRAGMA table_info(catalog)')}:
            conn.execute('ALTER TABLE catalog ADD COLUMN supplier_category VARCHAR(20)')
        for name in dict.fromkeys(CELULARES+ACCESORIOS+['CP HIDROGELES','BATERÍAS','MEMORIAS']):
            norm=key(name)
            category='Ambos' if name in CELULARES and name in ACCESORIOS else 'Celulares' if name in CELULARES else 'Accesorios'
            conn.execute("INSERT OR IGNORE INTO catalog(kind,name,normal_key,parent_id,active,supplier_category) VALUES('supplier',?,?,0,1,?)",(name,norm,category))
            conn.execute("UPDATE catalog SET supplier_category=? WHERE kind='supplier' AND normal_key=? AND parent_id=0",(category,norm))
        for row_id,name in conn.execute("SELECT id,name FROM catalog WHERE kind='supplier' AND supplier_category IS NULL"):
            conn.execute('UPDATE catalog SET supplier_category=? WHERE id=?',('Accesorios',row_id))
        if conn.execute("SELECT [notnull] FROM pragma_table_info('consignaciones_bancarias') WHERE name='banco_id'").fetchone()[0]:
            conn.execute('''CREATE TABLE consignaciones_bancarias_v14 (
                id INTEGER PRIMARY KEY,persona_id INTEGER NOT NULL REFERENCES personas_contables(id),
                banco_id INTEGER REFERENCES bancos_destino(id),monto NUMERIC(14,2) NOT NULL,
                fecha DATETIME NOT NULL,referencia VARCHAR(100),
                finance_operation_id INTEGER REFERENCES finance_operation(id),payment_index INTEGER,
                supplier_payment_id INTEGER UNIQUE REFERENCES finance_supplier_payment(id),
                activa BOOLEAN NOT NULL DEFAULT 1,
                CONSTRAINT uq_consignacion_operacion_medio UNIQUE(finance_operation_id,payment_index))''')
            columns='id,persona_id,banco_id,monto,fecha,referencia,finance_operation_id,payment_index,supplier_payment_id,activa'
            conn.execute(f'INSERT INTO consignaciones_bancarias_v14({columns}) SELECT {columns} FROM consignaciones_bancarias')
            conn.execute('DROP TABLE consignaciones_bancarias')
            conn.execute('ALTER TABLE consignaciones_bancarias_v14 RENAME TO consignaciones_bancarias')
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS ux_consignacion_finance_payment ON consignaciones_bancarias(finance_operation_id,payment_index)')
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS ux_consignacion_supplier_payment ON consignaciones_bancarias(supplier_payment_id)')
        conn.execute('INSERT INTO schema_version(version) VALUES(14)')
        conn.commit()
        conn.execute('PRAGMA foreign_keys=ON')
        if conn.execute('PRAGMA foreign_key_check').fetchall():raise RuntimeError('Revisa la integridad de la migración 14; existe un respaldo previo.')
