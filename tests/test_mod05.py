"""MOD-05 HU-TRI-001/002/003: consolidado, export CSV, ingresos/gastos y correcciones."""
import test_catalogs
from app.extensions import db
from app.models import Producto
from app.models.contabilidad import (
    ConsignacionBancaria, ReporteGenerado, IngresoGasto, CorreccionClasificacion,
)
from app.services.operacion_service import today


class Mod05Tests(test_catalogs.CatalogTests):
    def _persona_banco(self):
        self.client.post('/modulos/tributario/crear-destinatario', data={
            'csrf': self.csrf, 'nombre': 'Contador Prueba',
            'identificacion': '12345', 'tipo': 'Natural'})
        self.client.post('/modulos/tributario/crear-banco', data={
            'csrf': self.csrf, 'nombre_banco': 'Bancolombia'})
        with self.app.app_context():
            from app.models.contabilidad import PersonaContable, BancoDestino
            persona = db.session.scalars(db.select(PersonaContable)).first()
            banco = db.session.scalars(db.select(BancoDestino)).first()
            return persona.id, banco.id

    def _equipo_vendido(self):
        imei = self.imei(7)
        resp = self.client.post('/inventario/nuevo', data={
            **self.fields, 'imei': imei, 'condition': 'Nuevo'})
        self.assertEqual(resp.status_code, 302, resp.get_data(as_text=True)[-500:])
        with self.app.app_context():
            pid = db.session.scalar(db.select(Producto.id).where(Producto.imei == imei))
            rev = db.session.get(Producto, pid).revision
        payload = {'csrf': self.csrf, 'revision': str(rev), 'action': 'sell',
                   'reason': 'Venta de prueba MOD-05', 'seller': 'VENDEDOR',
                   'responsible': 'CLIENTE', 'sale_value': '5000000'}
        resp = self.client.post(f'/ventas/{pid}', data=payload)
        self.assertEqual(resp.status_code, 302, resp.get_data(as_text=True)[-500:])
        return pid

    def test_consolidado_y_export_registran_reporte(self):
        persona_id, banco_id = self._persona_banco()
        self._equipo_vendido()
        resp = self.client.post('/modulos/tributario/consignacion/nueva', data={
            'csrf': self.csrf, 'persona_id': persona_id, 'banco_id': banco_id,
            'monto': '1500000', 'referencia': 'SOP-001'})
        self.assertEqual(resp.status_code, 302)
        page = self.client.get('/modulos/tributario/?ini=2000-01-01&fin=' + today())
        html = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn('Consolidado por periodo', html)
        self.assertIn('Utilidad estimada', html)
        self.assertIn('SOP-001', html)
        csv_resp = self.client.get('/modulos/tributario/export.csv?ini=2000-01-01&fin=' + today())
        self.assertEqual(csv_resp.status_code, 200)
        self.assertIn('text/csv', csv_resp.content_type)
        body = csv_resp.get_data(as_text=True)
        self.assertIn('Consolidado contable-tributario', body)
        self.assertIn('no determina impuestos', body)
        with self.app.app_context():
            self.assertEqual(db.session.query(ReporteGenerado).count(), 1)
            rep = db.session.scalars(db.select(ReporteGenerado)).first()
            self.assertEqual(rep.fecha_ini, '2000-01-01')
        # El reporte queda visible en la tabla quién/cuándo.
        self.assertIn('Sesión local', self.client.get('/modulos/tributario/?ini=2000-01-01&fin=' + today()).get_data(as_text=True))

    def test_validaciones_no_exponen_detalle(self):
        persona_id, banco_id = self._persona_banco()
        bad = self.client.get('/modulos/tributario/?ini=2026-13-40&fin=' + today()).get_data(as_text=True)
        self.assertIn('año-mes-día', bad)
        resp = self.client.post('/modulos/tributario/consignacion/nueva', data={
            'csrf': self.csrf, 'persona_id': persona_id, 'banco_id': banco_id, 'monto': '-5', 'referencia': 'X'})
        self.assertEqual(resp.status_code, 302)
        with self.app.app_context():
            self.assertEqual(db.session.query(ConsignacionBancaria).count(), 0)
        resp = self.client.post('/modulos/tributario/consignacion/nueva', data={
            'csrf': self.csrf, 'persona_id': 9999, 'banco_id': banco_id, 'monto': '1000'})
        self.assertEqual(resp.status_code, 302)
        # Sin slash final también sirve el módulo (sin pasar por el placeholder).
        page = self.client.get('/modulos/tributario')
        self.assertEqual(page.status_code, 200)
        self.assertIn('Consolidado por periodo', page.get_data(as_text=True))

    def _movimiento(self, **kw):
        base = {'csrf': self.csrf, 'tipo': 'GASTO', 'concepto': 'Arriendo local',
                'categoria': 'ARRIENDO', 'valor': '800000', 'fecha': today(),
                'relacion': '', 'soporte_ref': 'FAC-1', 'responsable': 'Jonatan'}
        base.update(kw)
        return self.client.post('/modulos/tributario/ingreso-gasto/nuevo', data=base)

    def test_ingreso_gasto_entra_al_consolidado_y_csv(self):
        self.assertEqual(self._movimiento().status_code, 302)
        self.assertEqual(self._movimiento(
            tipo='INGRESO', concepto='Servicio técnico', categoria='SERVICIOS',
            valor='250000', soporte_ref='').status_code, 302)
        with self.app.app_context():
            self.assertEqual(db.session.query(IngresoGasto).count(), 2)
        html = self.client.get('/modulos/tributario/?ini=2000-01-01&fin=' + today()).get_data(as_text=True)
        self.assertIn('Arriendo local', html)
        self.assertIn('Servicio técnico', html)
        body = self.client.get('/modulos/tributario/export.csv?ini=2000-01-01&fin=' + today()).get_data(as_text=True)
        self.assertIn('Ingresos adicionales', body)
        self.assertIn('Gastos', body)
        self.assertIn('Arriendo local', body)

    def test_ingreso_gasto_invalido_no_se_guarda(self):
        for data in ({'valor': '-5'}, {'valor': '10', 'fecha': '2999-01-01'},
                     {'tipo': 'OTRO'}, {'concepto': 'x'}, {'categoria': 'INEXISTENTE'}):
            self.assertEqual(self._movimiento(**data).status_code, 302)
        with self.app.app_context():
            self.assertEqual(db.session.query(IngresoGasto).count(), 0)

    def test_corregir_clasificacion_audita_sin_borrar(self):
        self.assertEqual(self._movimiento().status_code, 302)
        with self.app.app_context():
            row = db.session.scalars(db.select(IngresoGasto)).first()
            gid, concepto, valor = row.id, row.concepto, row.valor_cents
        resp = self.client.post(f'/modulos/tributario/clasificacion/{gid}', data={
            'csrf': self.csrf, 'nueva_categoria': 'SERVICIOS', 'motivo': 'Era un servicio, no arriendo'})
        self.assertEqual(resp.status_code, 302)
        with self.app.app_context():
            row = db.session.get(IngresoGasto, gid)
            self.assertEqual(row.categoria, 'SERVICIOS')
            self.assertEqual(row.concepto, concepto)  # El documento original no se altera.
            self.assertEqual(row.valor_cents, valor)
            corr = db.session.scalars(db.select(CorreccionClasificacion)).first()
            self.assertEqual((corr.anterior, corr.nueva), ('ARRIENDO', 'SERVICIOS'))
        html = self.client.get('/modulos/tributario/?ini=2000-01-01&fin=' + today()).get_data(as_text=True)
        self.assertIn('Era un servicio, no arriendo', html)
        # Misma categoría o motivo corto se rechazan.
        self.assertEqual(self.client.post(f'/modulos/tributario/clasificacion/{gid}', data={
            'csrf': self.csrf, 'nueva_categoria': 'SERVICIOS', 'motivo': 'repetido'}).status_code, 302)
        self.assertEqual(self.client.post(f'/modulos/tributario/clasificacion/9999', data={
            'csrf': self.csrf, 'nueva_categoria': 'OTRO', 'motivo': 'inexistente'}).status_code, 302)
        with self.app.app_context():
            self.assertEqual(db.session.query(CorreccionClasificacion).count(), 1)
