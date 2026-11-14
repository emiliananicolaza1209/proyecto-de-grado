"""El consolidado solo cuenta consignaciones activas: pantalla, consolidado y alerta UVT deben coincidir."""
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from _cleanup import release
from app import create_app
from app.extensions import db
from app.models.contabilidad import BancoDestino, ConsignacionBancaria, PersonaBanco, PersonaContable
from app.services.contabilidad_service import consolidar_periodo, evaluar_estado_renta
from app.services.operacion_service import today
from app.services.reportes_presentacion import cop as cop_pantalla


class ConsolidadoSoloActivasTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'DATABASE': str(Path(self.tmp.name) / 'db.sqlite'), 'SECRET_KEY': 'test'})
        self.client = self.app.test_client()
        with self.app.app_context():
            persona = PersonaContable(nombre='ANA PRUEBA', identificacion='1001', tipo='Natural')
            banco = BancoDestino(nombre='BANCO PRUEBA')
            db.session.add_all([persona, banco]); db.session.flush()
            db.session.add(PersonaBanco(persona_id=persona.id, banco_id=banco.id))
            fecha = datetime.strptime(today(), '%Y-%m-%d')
            for monto, ref, activa in ((Decimal('1500000.00'), 'ACTIVA-1', True), (Decimal('700000.00'), 'ANULADA-1', False)):
                db.session.add(ConsignacionBancaria(persona_id=persona.id, banco_id=banco.id, monto=monto,
                                                    fecha=fecha, referencia=ref, activa=activa))
            db.session.commit()
            self.persona_id = persona.id

    def tearDown(self):
        release(self.app)
        self.tmp.cleanup()

    def test_consolidado_excluye_la_anulada(self):
        with self.app.app_context():
            cons = consolidar_periodo('2000-01-01', today())['consignaciones']
        self.assertEqual((cons['count'], cons['total_cents']), (1, 150000000))
        self.assertEqual([r['fuente'] for r in cons['detalle']], ['ACTIVA-1'])

    def test_pantalla_consolidado_y_alerta_uvt_coinciden(self):
        with self.app.app_context():
            cons = consolidar_periodo('2000-01-01', today())['consignaciones']
            alerta = evaluar_estado_renta(self.persona_id)
        self.assertEqual(Decimal(cons['total_cents']) / 100, alerta['total_consignado'])  # consolidado == alerta UVT
        html = self.client.get('/modulos/tributario/?ini=2000-01-01&fin=' + today()).get_data(as_text=True)
        # Solo la sección del consolidado: el Historial sí lista la anulada, marcada "ANULADA — no suma".
        consolidado = html.split('<div id="consolidado"', 1)[1].split('<div id="personas"', 1)[0]
        self.assertIn('Consignaciones (1)', consolidado)
        self.assertIn(cop_pantalla(cons['total_cents']), consolidado)  # pantalla == consolidado
        self.assertIn('ACTIVA-1', consolidado)
        self.assertNotIn('ANULADA-1', consolidado)
        self.assertNotIn('2,200,000', consolidado)
        self.assertIn('ANULADA', html)  # sigue visible y marcada en el historial


if __name__ == '__main__':
    unittest.main()
