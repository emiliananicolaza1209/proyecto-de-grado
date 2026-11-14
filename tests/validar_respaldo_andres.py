"""Validación opcional del respaldo privado exacto, fuera de la suite reproducible.

En PowerShell, con el archivo original disponible:
  $env:CPSTORE_RESPALDO_ANDRES = 'C:\\ruta\\cpstore.sqlite'
  python -m unittest discover -s tests -p validar_respaldo_andres.py -v

Nunca sustituirlo por el fixture de ensayo ni desactivar la comprobación SHA-256.
"""
import hashlib
import os
import shutil
import unittest
from pathlib import Path

import test_migracion_union as union

RESPALDO = Path(os.getenv('CPSTORE_RESPALDO_ANDRES') or
                Path(__file__).resolve().parents[2] / 'respaldo_instance_20261108_163211' / 'cpstore.sqlite')
SHA256_RESPALDO = '11c990140b809d5dc6a8f104b9c41e6f1ab0f2faad6ce6515a1672249d141723'


@unittest.skipUnless(RESPALDO.is_file(), f'Validación histórica no realizada: falta el respaldo original {RESPALDO}')
class RespaldoHistoricoAndres(union.BaseConEsquemaDeAndres):
    def preparar_base(self):
        self.assertEqual(hashlib.sha256(RESPALDO.read_bytes()).hexdigest(), SHA256_RESPALDO,
                         'El archivo no es el respaldo histórico verificado; no se modifica')
        shutil.copyfile(RESPALDO, self.path)


if __name__ == '__main__':
    unittest.main()
