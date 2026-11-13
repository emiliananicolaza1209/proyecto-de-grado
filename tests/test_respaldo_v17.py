import unittest,tempfile,zipfile,json
from pathlib import Path
from app import create_app
from app.extensions import db
from app.respaldo import backup,verify,restore
from app.models.gestion import RegistroGestion


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.app=create_app({'TESTING':True,'DATABASE':str(self.root/'live.sqlite'),'SECRET_KEY':'test'})
        self.app.instance_path=str(self.root/'instance')
        self.ctx=self.app.app_context();self.ctx.push()
        files=self.root/'instance/facturas';files.mkdir(parents=True);(files/'invoice.pdf').write_bytes(b'example')
    def tearDown(self):
        db.session.remove();db.engine.dispose();self.ctx.pop();self.tmp.cleanup()
    def test_backup_hash_restore_separate_and_attachment(self):
        path=self.root/'copy.zip';backup(path)
        manifest=verify(path);self.assertIn('facturas/invoice.pdf',manifest['files'])
        restore(path,self.root/'recovered')
        self.assertEqual((self.root/'recovered/facturas/invoice.pdf').read_bytes(),b'example')
        self.assertTrue((self.root/'recovered/database.sqlite').exists())
        self.assertEqual(db.session.query(RegistroGestion).filter_by(entidad='respaldo').count(),2)
        with self.assertRaises(ValueError):restore(path,self.root/'instance')
        with self.assertRaises(ValueError):backup(path)
    def test_tampered_archive_rejected(self):
        original=self.root/'copy.zip';backup(original)
        changed=self.root/'corrupt.zip'
        with zipfile.ZipFile(original) as source,zipfile.ZipFile(changed,'w') as target:
            for name in source.namelist():target.writestr(name,b'corrupted' if name=='database.sqlite' else source.read(name))
        with self.assertRaises(ValueError):verify(changed)


if __name__=='__main__':unittest.main()
