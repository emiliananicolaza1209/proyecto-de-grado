"""Datos de identificación: https://support.apple.com/es-co/108044 (2026-09-09).
Solo atributos del catálogo; nunca crea existencias ni consulta internet al iniciar.
"""
import re
import unicodedata

# Variantes con las mismas opciones se agrupan para evitar inconsistencias.
GROUPS = [
 ('8|8 PLUS', [64,128,256], 'ORO|PLATA|GRIS ESPACIAL|ROJO'),
 ('X', [64,256], 'PLATA|GRIS ESPACIAL'),
 ('XR', [64,128,256], 'NEGRO|BLANCO|AZUL|AMARILLO|CORAL|ROJO'),
 ('XS|XS MAX', [64,256,512], 'PLATA|GRIS ESPACIAL|ORO'),
 ('11', [64,128,256], 'MORADO|VERDE|AMARILLO|NEGRO|BLANCO|ROJO'),
 ('11 PRO|11 PRO MAX', [64,256,512], 'PLATA|GRIS ESPACIAL|ORO|VERDE MEDIANOCHE'),
 ('SE (2.ª GENERACIÓN)', [64,128,256], 'BLANCO|NEGRO|ROJO'),
 ('12|12 MINI', [64,128,256], 'NEGRO|BLANCO|ROJO|VERDE|AZUL|MORADO'),
 ('12 PRO|12 PRO MAX', [128,256,512], 'PLATA|GRAFITO|ORO|AZUL PACÍFICO'),
 ('13|13 MINI', [128,256,512], 'ROJO|BLANCO ESTELAR|AZUL MEDIANOCHE|AZUL|ROSA|VERDE'),
 ('13 PRO|13 PRO MAX', [128,256,512,1024], 'GRAFITO|ORO|PLATA|AZUL SIERRA|VERDE ALPINO'),
 ('SE (3.ª GENERACIÓN)', [64,128,256], 'ROJO|BLANCO ESTELAR|AZUL MEDIANOCHE'),
 ('14|14 PLUS', [128,256,512], 'AZUL MEDIANOCHE|BLANCO ESTELAR|ROJO|AZUL|MORADO|AMARILLO'),
 ('14 PRO|14 PRO MAX', [128,256,512,1024], 'PLATA|ORO|NEGRO ESPACIAL|MORADO OSCURO'),
 ('15|15 PLUS', [128,256,512], 'NEGRO|AZUL|VERDE|AMARILLO|ROSA'),
 ('15 PRO', [128,256,512,1024], 'TITANIO NEGRO|TITANIO BLANCO|TITANIO AZUL|TITANIO NATURAL'),
 ('15 PRO MAX', [256,512,1024], 'TITANIO NEGRO|TITANIO BLANCO|TITANIO AZUL|TITANIO NATURAL'),
 ('16|16 PLUS', [128,256,512], 'NEGRO|BLANCO|ROSA|VERDE AZULADO|ULTRAMARINO'),
 ('16 PRO', [128,256,512,1024], 'TITANIO NEGRO|TITANIO BLANCO|TITANIO NATURAL|TITANIO DEL DESIERTO'),
 ('16 PRO MAX', [256,512,1024], 'TITANIO NEGRO|TITANIO BLANCO|TITANIO NATURAL|TITANIO DEL DESIERTO'),
 ('16E', [128,256,512], 'NEGRO|BLANCO'),
 ('AIR', [256,512,1024], 'NEGRO ESPACIAL|BLANCO NUBE|ORO CLARO|AZUL CIELO'),
 ('17', [256,512], 'NEGRO|BLANCO|AZUL NEBLINA|SALVIA|LAVANDA'),
 ('17 PRO', [256,512,1024], 'PLATA|NARANJA CÓSMICO|AZUL PROFUNDO'),
 ('17 PRO MAX', [256,512,1024,2048], 'PLATA|NARANJA CÓSMICO|AZUL PROFUNDO'),
 ('17E', [256,512], 'NEGRO|BLANCO|ROSA PÁLIDO'),
]


def seed(db):
    def item(kind, name, parent=0):
        key = ''.join(c for c in unicodedata.normalize('NFKD', name.casefold()) if not unicodedata.combining(c))
        key = re.sub('[^a-z0-9]', '', key)
        if kind == 'reference':
            key = re.sub(r'^(apple)?iphone', '', key)
        db.execute('INSERT OR IGNORE INTO catalog(kind,name,normal_key,parent_id,active) VALUES(?,?,?,?,1)', (kind,name,key,parent))
        return db.execute('SELECT id FROM catalog WHERE kind=? AND normal_key=? AND parent_id=?', (kind,key,parent)).fetchone()[0]
    apple = item('brand', 'APPLE')
    for names, capacities, colors in GROUPS:
        for name in names.split('|'):
            reference = item('reference', 'IPHONE '+name, apple)
            # Conservar identidad y opciones históricas; no borrar vínculos existentes.
            db.execute('UPDATE catalog SET name=? WHERE id=?', ('IPHONE '+name, reference))
            for capacity in capacities:
                item('capacity', str(capacity), reference)
            for color in colors.split('|'):
                item('color', color, reference)
