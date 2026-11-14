"""Permisos efectivos en servidor, revocación de sesiones y persistencia."""
import json
import secrets
import unittest
from html.parser import HTMLParser
from werkzeug.datastructures import MultiDict
from werkzeug.security import generate_password_hash
import test_gestion_v16 as fixture
from app.extensions import db
from app.models.gestion import Usuario, PermisosUsuario, RegistroGestion
from app.services.permisos_service import validate_permissions, profile_keys


class AccessTests(unittest.TestCase):
    setUp=fixture.GestionTests.setUp
    tearDown=fixture.GestionTests.tearDown
    product=fixture.GestionTests.product

    def user(self, role='Administrador', keys=None):
        user=Usuario(nombre='ACCESO PRUEBA',login=secrets.token_hex(6),password_hash=generate_password_hash('ClaveUnicaDePruebas!735'),rol=role)
        db.session.add(user);db.session.flush()
        if keys is not None:db.session.add(PermisosUsuario(usuario_id=user.id,permisos=keys))
        db.session.commit();return user

    def login(self,user):
        self.app.config['AUTH_REQUIRED']=True;client=self.app.test_client()
        with client.session_transaction() as session:session.update(usuario_id=user.id,usuario_version=user.session_version,csrf='test')
        return client

    def test_custom_multiple_modules_read_only_and_direct_post_denied(self):
        user=self.user(keys=['inventario.ver','ventas.ver','finanzas.ver'])
        client=self.login(user)
        for path in ('/inventario','/ventas','/finanzas'):
            with self.subTest(path=path):self.assertEqual(client.get(path).status_code,200)
        for path in ('/usuarios','/finanzas/creditos','/modulos/tributario/','/finanzas?tab=personal','/gestion/historial'):
            with self.subTest(path=path):self.assertEqual(client.get(path).status_code,403)
        old=self.d.config.copy()
        r=client.post('/finanzas',data=dict(csrf='test',date=self.day,revision=self.d.revision,action='config'))
        self.assertEqual(r.status_code,403);db.session.refresh(self.d);self.assertEqual(self.d.config,old)
        self.assertEqual(client.post('/inventario/nuevo',data=dict(csrf='test')).status_code,403)

    def test_payment_and_sale_are_separate_permissions(self):
        product=self.product();client=self.login(self.user('Vendedora',['ventas.ver','ventas.registrar']))
        response=client.post(f'/ventas/{product.id}',data=dict(csrf='test',action='payment'))
        self.assertEqual(response.status_code,403)
        response=client.get(f'/ventas/{product.id}')
        self.assertEqual(response.status_code,200)
        self.assertIn('Solo consulta',response.get_data(as_text=True))

    def test_costs_not_embedded_in_inventory_or_finance_json(self):
        product=self.product(cost=387654300)
        client=self.login(self.user(keys=['inventario.ver','finanzas.ver']))
        inventory=client.get('/inventario').get_data(as_text=True)
        self.assertNotIn('3.876.543',inventory)
        detail=client.get(f'/inventario/{product.id}')
        self.assertEqual(detail.status_code,200);self.assertNotIn('3.876.543',detail.get_data(as_text=True))
        for path in ('/inventario/compras','/inventario/articulos','/inventario/lotes'):
            self.assertEqual(client.get(path).status_code,403)
        finance=client.get('/finanzas?accion=registrar').get_data(as_text=True)
        self.assertNotIn('387654300',finance)
        self.assertIn('finance-equipment-costs',finance)
        self.assertNotIn('Personal y reglas</a>',finance)

    def test_profile_defaults_unchanged_and_no_unowned_module_can_be_granted(self):
        self.assertIsNone(validate_permissions('Vendedora','perfil',[]))
        self.assertIn('finanzas.compra_pool',profile_keys('Vendedora'))
        for keys in (['usuarios.administrar'],['finanzas.ver','finanzas.personal'],['desconocido.ver']):
            with self.subTest(keys=keys),self.assertRaises(ValueError):validate_permissions('Vendedora','personalizado',keys)
        with self.assertRaises(ValueError):validate_permissions('Administrador','personalizado',['ventas.cobrar'])

    def test_only_owner_can_change_permissions_and_update_invalidates_session(self):
        owner=self.user('Propietario');user=self.user();client=self.login(owner);old_client=self.login(user)
        response=client.post('/usuarios',data=MultiDict(dict(csrf='test',id=user.id,access_version=user.session_version,
            name=user.nombre,login=user.login,role=user.rol,active='1',permission_mode='personalizado',permission=['inventario.ver','ventas.ver'])))
        self.assertEqual(response.status_code,302)
        saved=db.session.get(PermisosUsuario,user.id);self.assertEqual(set(saved.permisos),{'inventario.ver','ventas.ver'})
        self.assertEqual(old_client.get('/inventario').status_code,302)
        audit=db.session.scalar(db.select(RegistroGestion).where(RegistroGestion.entidad=='usuario',RegistroGestion.entidad_id==user.id))
        self.assertEqual(audit.datos['permisos'],saved.permisos)
        self.assertIn('antes',audit.datos)
        self.assertEqual(self.login(user).post('/usuarios',data=dict(csrf='test')).status_code,403)

    def test_stale_editor_and_forged_permission_rejected_without_change(self):
        client=self.login(self.user('Propietario'));user=self.user('Vendedora')
        base=dict(csrf='test',id=user.id,access_version=user.session_version,name=user.nombre,login=user.login,role=user.rol,active='1',permission_mode='personalizado')
        response=client.post('/usuarios',data=MultiDict(base|{'permission':['usuarios.administrar']}))
        self.assertEqual(response.status_code,200);self.assertIsNone(db.session.get(PermisosUsuario,user.id))
        response=client.post('/usuarios',data=MultiDict(base|{'access_version':'9999','permission':['ventas.ver']}))
        self.assertEqual(response.status_code,200);self.assertIsNone(db.session.get(PermisosUsuario,user.id))

    def test_last_owner_protected_and_cannot_restrict_owner(self):
        owner=self.user('Propietario');client=self.login(owner)
        self.assertIsNone(validate_permissions('Propietario','personalizado',[]))
        r=client.post('/usuarios',data=dict(csrf='test',id=owner.id,name=owner.nombre,login=owner.login,role='Vendedora',active='1'))
        self.assertEqual(r.status_code,200);db.session.refresh(owner);self.assertEqual(owner.rol,'Propietario')

    def test_empty_access_and_restricted_home_do_not_loop_or_open_modules(self):
        client=self.login(self.user(keys=['ventas.ver']))
        self.assertEqual(client.get('/').location,'/ventas')
        self.assertEqual(client.get('/ventas').status_code,200)
        empty=self.login(self.user(keys=[]))
        self.assertEqual(empty.get('/').status_code,403)
        self.assertEqual(empty.get('/cerrar-sesion').status_code,405)
        self.assertEqual(empty.post('/cerrar-sesion',data=dict(csrf='test')).status_code,302)

    def test_custom_access_persists_and_sqlite_migration_is_idempotent(self):
        user=self.user(keys=['ventas.ver']);before=user.session_version
        if db.engine.name=='sqlite':
            from migrations.accesos_v20 import upgrade
            upgrade(self.app.config['DATABASE']);upgrade(self.app.config['DATABASE'])
        else:
            from app.database import initialize_postgres
            self.assertFalse(initialize_postgres());self.assertFalse(initialize_postgres())
        db.session.expire_all()
        self.assertEqual(db.session.get(PermisosUsuario,user.id).permisos,['ventas.ver'])
        self.assertEqual(db.session.get(Usuario,user.id).session_version,before)

    def test_users_page_is_structured_by_modules_without_password_hashes(self):
        owner=self.user('Propietario');html=self.login(owner).get('/usuarios').get_data(as_text=True)
        self.assertIn('data-module="creditos"',html);self.assertIn('name="permission_mode"',html)
        self.assertIn('css/usuarios.css',html);self.assertNotIn(owner.password_hash,html)

    def test_report_export_cannot_bypass_disabled_source_module(self):
        client=self.login(self.user(keys=['reportes.ver','reportes.exportar','inventario.ver']))
        self.assertEqual(client.get('/reportes?tipo=inventario').status_code,200)
        self.assertEqual(client.get('/reportes?tipo=finanzas').status_code,403)
        self.assertEqual(client.get('/reportes/exportar/finanzas/csv').status_code,403)
        self.assertEqual(client.get('/finanzas/exportar?date='+self.day).status_code,403)

    def test_salary_operation_cannot_bypass_disabled_personnel(self):
        client=self.login(self.user(keys=['finanzas.ver','finanzas.movimientos']))
        self.assertEqual(client.post('/finanzas',data=dict(csrf='test',date=self.day,action='operation',kind='Pago sueldo')).status_code,403)

    def test_query_parameters_cannot_override_post_permission(self):
        from jornada_fixtures import opening
        client=self.login(self.user(keys=['finanzas.ver','finanzas.compra_pool']))
        before=self.d.config.copy()
        form=opening(self.day)
        form.update(csrf='test',date=self.day,revision=self.d.revision,action='config',normal_base='90000')
        response=client.post('/finanzas?action=pool_purchase',data=form)
        self.assertEqual(response.status_code,403)
        db.session.refresh(self.d);self.assertEqual(self.d.config,before)
        sales=self.login(self.user(keys=['finanzas.ver','finanzas.venta']))
        response=sales.post('/finanzas?kind=Venta',data=dict(csrf='test',date=self.day,action='operation',kind='Pago sueldo'))
        self.assertEqual(response.status_code,403)
        response=sales.post('/finanzas?action=config&kind=Pago+sueldo',data=dict(csrf='test',date=self.day,
            revision=self.d.revision,action='operation',kind='Venta',description='VENTA PERMITIDA CON URL AJENA',
            seller='ANA',token=secrets.token_hex(16),amount='120000',minor_cost='0',
            payment_account='EFECTIVO',payment_amount='120000'))
        self.assertEqual(response.status_code,302)


if __name__=='__main__':unittest.main()
