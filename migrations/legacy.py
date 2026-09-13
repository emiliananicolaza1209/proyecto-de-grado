import re
import unicodedata

def normalize(value, kind=''):
    value = ''.join(c for c in unicodedata.normalize('NFKD', value.casefold())
                    if not unicodedata.combining(c))
    value = re.sub(r'[^a-z0-9]', '', value)
    if kind == 'reference':
        value = re.sub(r'^(apple)?iphone', '', value)
    return value


def add_item(db, kind, name, parent=0):
    key = normalize(name, kind)
    db.execute('INSERT OR IGNORE INTO catalog(kind,name,normal_key,parent_id) VALUES(?,?,?,?)',
               (kind, name, key, parent))
    return db.execute('SELECT id FROM catalog WHERE kind=? AND normal_key=? AND parent_id=?',
                      (kind, key, parent)).fetchone()['id']


def migrate(db):
    db.execute('''CREATE TABLE IF NOT EXISTS catalog (
        id INTEGER PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
        normal_key TEXT NOT NULL, parent_id INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1, UNIQUE(kind,normal_key,parent_id))''')
    columns = {r['name'] for r in db.execute('PRAGMA table_info(equipment)')}
    for name in ('reference_id', 'color_id', 'capacity_id', 'supplier_id', 'location_id'):
        if name not in columns:
            db.execute(f'ALTER TABLE equipment ADD COLUMN {name} INTEGER REFERENCES catalog(id)')
    for row in db.execute('SELECT * FROM equipment WHERE reference_id IS NULL').fetchall():
        ref = add_item(db, 'reference', row['model'])
        color = add_item(db, 'color', row['color'], ref)
        capacity = add_item(db, 'capacity', str(row['capacity']), ref)
        supplier = add_item(db, 'supplier', row['supplier'])
        location = add_item(db, 'location', row['location'])
        db.execute('UPDATE equipment SET reference_id=?,color_id=?,capacity_id=?,supplier_id=?,location_id=? WHERE id=?',
                   (ref, color, capacity, supplier, location, row['id']))


