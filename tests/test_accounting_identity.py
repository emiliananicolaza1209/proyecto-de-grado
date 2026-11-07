"""La identidad se registra una sola vez y admite varios bancos."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.extensions import db
from app.models import PersonaContable, BancoDestino, PersonaBanco, ConsignacionBancaria
from migrations.integracion import upgrade_v13


class AccountingIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'data.sqlite'
        self.app=create_app({'TESTING':True,'DATABASE':str(self.path),'SECRET_KEY':'tests'})
        self.client=self.app.test_client()
        self.client.get('/modulos/tributario/')
        with self.client.session_transaction() as session:self.csrf=session['csrf']

    def tearDown(self):self.tmp.cleanup()

    def post(self,url,**data):
        return self.client.post(url,data={'csrf':self.csrf,**data})

    def test_same_identification_warning_and_multiple_banks(self):
        url='/modulos/tributario/crear-destinatario'
        self.assertEqual(self.post(url,nombre='Emily David',identificacion='1.234-567',tipo='Natural').status_code,302)
        result=self.client.get('/modulos/tributario/personas/verificar?nombre=Emilia+David&identificacion=1234567').json
        self.assertEqual(result['exact'][0]['nombre'],'EMILY DAVID')
        duplicate=self.post(url,nombre='Emilia David',identificacion='1234567',tipo='Natural')
        self.assertEqual(duplicate.status_code,409)
        self.assertIn('Agregar banco',duplicate.get_data(as_text=True))
        with self.app.app_context():
            person=db.session.scalar(db.select(PersonaContable))
            self.assertEqual(db.session.scalar(db.select(db.func.count(PersonaContable.id))),1)
            person_id=person.id
        endpoint='/modulos/tributario/persona/bancos'
        self.assertEqual(self.post(endpoint,persona_id=person_id,nuevo_banco='Bancolombia').status_code,302)
        self.assertEqual(self.post(endpoint,persona_id=person_id,nuevo_banco='bancolombia').status_code,302)
        self.assertEqual(self.post(endpoint,persona_id=person_id,nuevo_banco='Nequi').status_code,302)
        with self.app.app_context():
            self.assertEqual(db.session.scalar(db.select(db.func.count(PersonaContable.id))),1)
            self.assertEqual(db.session.scalar(db.select(db.func.count(BancoDestino.id))),2)
            self.assertEqual(db.session.scalar(db.select(db.func.count(PersonaBanco.id))),2)
            bank=db.session.scalar(db.select(BancoDestino).where(BancoDestino.nombre=='BANCOLOMBIA'))
            bank_id=bank.id
        self.assertEqual(self.post('/modulos/tributario/consignacion/nueva',persona_id=person_id,
            banco_id=bank_id,monto='120000',fecha='2026-10-01').status_code,302)
        with self.app.app_context():self.assertEqual(db.session.scalar(db.select(db.func.count(ConsignacionBancaria.id))),1)

    def test_similar_name_with_different_id_requires_confirmation(self):
        url='/modulos/tributario/crear-destinatario'
        self.post(url,nombre='Emily David',identificacion='10001',tipo='Natural')
        result=self.client.get('/modulos/tributario/personas/verificar?nombre=EMILY+DAVID&identificacion=20002').json
        self.assertEqual(len(result['similar']),1)
        self.assertEqual(self.post(url,nombre='emily david',identificacion='20002',tipo='Natural').status_code,409)
        with self.app.app_context():self.assertEqual(db.session.scalar(db.select(db.func.count(PersonaContable.id))),1)
        self.assertEqual(self.post(url,nombre='emily david',identificacion='20002',tipo='Natural',confirm_same_name='1').status_code,302)
        with self.app.app_context():self.assertEqual(db.session.scalar(db.select(db.func.count(PersonaContable.id))),2)

    def test_existing_consignation_links_bank_on_upgrade(self):
        with self.app.app_context():
            p=PersonaContable(nombre='ANA',identificacion='999',tipo='Natural')
            b=BancoDestino(nombre='BANCO ANTERIOR')
            db.session.add_all([p,b]);db.session.flush()
            db.session.add(ConsignacionBancaria(persona_id=p.id,banco_id=b.id,monto=1000));db.session.commit()
            person_id,bank_id=p.id,b.id
            db.session.execute(db.delete(PersonaBanco));db.session.commit()
            db.engine.dispose()
        with sqlite3.connect(self.path) as conn:conn.execute('DELETE FROM schema_version WHERE version=13')
        upgrade_v13(self.path)
        upgrade_v13(self.path)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT persona_id,banco_id FROM persona_banco').fetchall(),[(person_id,bank_id)])


if __name__=='__main__':unittest.main()
