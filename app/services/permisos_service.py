"""Accesos por módulo/acción. Un perfil conserva su límite de privilegios.

Sin personalización se mantienen exactamente los permisos anteriores. Las listas
personalizadas son una restricción del perfil, nunca una elevación de privilegios.
"""
from ..extensions import db
from ..models.gestion import PermisosUsuario

# clave, etiqueta, capacidad del perfil. La primera opción es la consulta del módulo.
MODULES = (
    ('resumen', 'Resumen', (('ver', 'Consultar resumen', 'consulta'),)),
    ('inventario', 'Inventario', (
        ('ver', 'Consultar equipos', 'consulta'), ('editar', 'Registrar y editar inventario y lotes', 'inventario'),
        ('trasladar', 'Trasladar equipos', 'traslado'), ('costos', 'Ver costos e inversión', 'costos'),
        ('catalogos', 'Administrar catálogos y proveedores', 'catalogos'))),
    ('ventas', 'Ventas y pagos', (
        ('ver', 'Consultar ventas', 'consulta'), ('registrar', 'Vender, reservar y devolver', 'venta'),
        ('cobrar', 'Registrar pagos de clientes', 'cobro'), ('corregir', 'Anular pagos y corregir fechas', 'admin'),
        ('recepciones', 'Recibir dinero en administración', 'admin'))),
    ('finanzas', 'Finanzas', (
        ('ver', 'Consultar movimientos', 'finanzas_venta'), ('venta', 'Registrar ventas de la jornada', 'finanzas_venta'),
        ('compra_pool', 'Registrar compras POOL', 'finanzas_pool'), ('movimientos', 'Registrar otros movimientos e incorporar ventas', 'admin'),
        ('corregir', 'Corregir o anular operaciones', 'admin'), ('proveedores', 'Consultar y pagar proveedores y comisiones', 'admin'),
        ('personal', 'Consultar y modificar personal y reglas', 'admin'), ('cierre', 'Abrir, cerrar y reabrir jornadas', 'admin'))),
    ('creditos', 'Créditos y desembolsos', (
        ('ver', 'Consultar créditos', 'admin'), ('desembolsar', 'Registrar desembolsos', 'admin'),
        ('aliados', 'Configurar aliados', 'admin'))),
    ('sociedades', 'Sociedades', (('ver', 'Consultar sociedades', 'sociedades_consulta'),
        ('gestionar', 'Gestionar aportes y liquidaciones', 'admin'), ('configurar', 'Configurar socios y sociedades', 'sociedades_config'))),
    ('reportes', 'Reportes', (('ver', 'Consultar reportes', 'consulta'), ('exportar', 'Descargar reportes', 'consulta'))),
    ('analitica', 'Analítica', (('ver', 'Consultar analítica', 'reportes'),)),
    ('chat', 'Chat de consultas', (('ver', 'Consultar chat', 'chat'),)),
    ('contabilidad', 'Información contable', (
        ('ver', 'Consultar información contable', 'contabilidad'), ('registrar', 'Registrar personas, bancos e ingresos y gastos', 'contabilidad'),
        ('corregir', 'Corregir consignaciones y clasificación', 'contabilidad'), ('exportar', 'Descargar paquete del contador', 'contabilidad'))),
    ('historial', 'Historial de gestión', (('ver', 'Consultar auditoría', 'admin'),)),
    ('usuarios', 'Usuarios', (('administrar', 'Administrar usuarios y permisos', 'usuarios'),)),
)
KEYS = {f'{module}.{action}': capability for module, _, actions in MODULES for action, _, capability in actions}
READ_KEYS = {module: f'{module}.{actions[0][0]}' for module, _, actions in MODULES}
KIND_KEYS={'Venta':'finanzas.venta','Servicio':'finanzas.proveedores','PD':'finanzas.proveedores',
           'Pago sueldo':'finanzas.personal','Pago comisión':'finanzas.personal',
           'Entrada caja':'finanzas.movimientos','Salida caja':'finanzas.movimientos'}


def profile_can(role, capability):
    if capability in ('chat', 'reportes'):
        from .consultas_service import ROLES_CONSULTAS
        return any(role in roles for roles in ROLES_CONSULTAS.values())
    if role == 'Propietario': return True
    if role == 'Administrador': return capability not in ('usuarios', 'sociedades_config')
    if role == 'Inventario': return capability in ('inventario', 'catalogos', 'consulta', 'traslado', 'costos')
    if role == 'Vendedora': return capability in ('consulta', 'venta', 'cobro', 'finanzas_venta', 'finanzas_pool', 'traslado')
    if role == 'Socio': return capability == 'sociedades_consulta'
    return False


def profile_keys(role):
    return {key for key, capability in KEYS.items() if profile_can(role, capability)}


def validate_permissions(role, mode, keys):
    if mode not in ('perfil', 'personalizado'): raise ValueError('Modo de permisos inválido.')
    if mode == 'perfil' or role == 'Propietario': return None
    selected = set(keys)
    if not selected.issubset(KEYS): raise ValueError('Hay permisos desconocidos. Recarga el formulario.')
    if not selected.issubset(profile_keys(role)): raise ValueError('Un permiso supera el perfil elegido. Revisa el perfil y sus módulos.')
    for module, _, actions in MODULES:
        module_keys = {f'{module}.{action}' for action, _, _ in actions}
        if selected & module_keys and READ_KEYS[module] not in selected:
            raise ValueError('Activa también la consulta del módulo para habilitar sus acciones.')
    if 'inventario.editar' in selected and 'inventario.costos' not in selected:
        raise ValueError('Registrar y editar compras requiere también el permiso de costos de inventario.')
    return sorted(selected)


def user_keys(user):
    row = db.session.get(PermisosUsuario, user.id)
    if user.rol == 'Propietario' or row is None: return profile_keys(user.rol)
    return profile_keys(user.rol) & set(row.permisos)


def route_key(endpoint, method='GET', values=None, args=None):
    """Política central para rutas HTML, API, exportaciones y escrituras directas."""
    values = values or {}; args = args or {}; write = method not in ('GET', 'HEAD', 'OPTIONS')
    action = values.get('action', '')
    if endpoint in ('static', 'main.health', 'auth.login', 'auth.logout') or endpoint is None: return None
    if endpoint == 'main.home': return 'resumen.ver'
    if endpoint == 'main.module':
        module = args.get('name', '')
        return {'tributario': 'contabilidad.ver', 'usuarios': 'usuarios.administrar'}.get(module, f'{module}.ver')
    if endpoint.startswith('inventory.'):
        if not write: return 'inventario.editar' if endpoint=='inventory.new' else 'inventario.ver'
        return 'inventario.trasladar' if action == 'transfer' else 'inventario.editar'
    if endpoint.startswith(('lotes.', 'catalogos.')):
        return 'inventario.catalogos' if endpoint.startswith('catalogos.') else ('inventario.editar' if write else 'inventario.ver')
    if endpoint.startswith('ventas.'):
        if endpoint in ('ventas.receipts', 'ventas.receipt_detail'): return 'ventas.recepciones'
        if not write: return 'ventas.ver'
        if action == 'payment': return 'ventas.cobrar'
        if action in ('void_collection', 'correct_date'): return 'ventas.corregir'
        return 'ventas.registrar' if action in ('handoff','return','reserve','sell','cancel') else 'ventas.corregir'
    if endpoint.startswith('finanzas.'):
        if not write:
            if endpoint != 'finanzas.index': return 'reportes.exportar'
            if values.get('accion') == 'compra_pool': return 'finanzas.compra_pool'
            return {'personal': 'finanzas.personal', 'proveedores': 'finanzas.proveedores', 'cierre': 'finanzas.cierre'}.get(values.get('tab'), 'finanzas.ver')
        if action in ('open', 'close', 'reopen'): return 'finanzas.cierre'
        if action in ('config', 'staff_payment'): return 'finanzas.personal'
        if action == 'pool_purchase': return 'finanzas.compra_pool'
        if action in ('supplier_payment', 'edit_supplier_payment', 'pool_commission', 'void_pool_commission'): return 'finanzas.proveedores'
        if action in ('edit_operation', 'equipment_costs', 'void'): return 'finanzas.corregir'
        if action == 'operation': return KIND_KEYS.get(values.get('kind'),'__sin_permiso__')
        return 'finanzas.movimientos'
    if endpoint.startswith('contabilidad.'):
        if endpoint in ('contabilidad.exportar_csv', 'contabilidad.paquete_excel', 'contabilidad.paquete_pdf'): return 'contabilidad.exportar'
        if not write: return 'contabilidad.ver'
        return 'contabilidad.corregir' if endpoint in ('contabilidad.corregir', 'contabilidad.editar_consignacion', 'contabilidad.actualizar_antecedente') else 'contabilidad.registrar'
    if endpoint.startswith('chat.'): return 'chat.ver'
    if endpoint.startswith('reportes.'):
        if endpoint in ('reportes.analytics', 'reportes.alerts_page', 'reportes.consult', 'reportes.query_api'): return 'analitica.ver'
        return 'reportes.exportar' if endpoint == 'reportes.export' else 'reportes.ver'
    if endpoint == 'gestion.usuarios': return 'usuarios.administrar'
    if endpoint == 'gestion.historial': return 'historial.ver'
    if endpoint == 'gestion.creditos':
        return ('creditos.aliados' if action == 'ally' else 'creditos.desembolsar') if write else 'creditos.ver'
    if endpoint == 'gestion.pool': return 'finanzas.proveedores' if action == 'commission' else 'finanzas.compra_pool'
    if endpoint == 'gestion.sociedades':
        return ('sociedades.configurar' if action in ('partner', 'society') else 'sociedades.gestionar') if write else 'sociedades.ver'
    if endpoint == 'gestion.inversion': return 'sociedades.ver' if args.get('_socio') else 'inventario.costos'
    if endpoint in ('gestion.proveedores', 'gestion.alias'): return 'inventario.catalogos'
    if endpoint.startswith('gestion.'): return 'inventario.editar' if write else 'inventario.ver'
    return '__sin_permiso__'


def route_keys(endpoint, method='GET', values=None, args=None):
    values=values or {};args=args or {}
    key=route_key(endpoint,method,values,args)
    keys={key} if key else set()
    if endpoint=='finanzas.export':keys.add('finanzas.ver')
    if endpoint in ('gestion.lotes','gestion.lote','gestion.plantilla','gestion.factura','gestion.articulos','lotes.index','lotes.detail','inventory.new'):
        keys.add('inventario.costos')
    if endpoint in ('reportes.index','reportes.export','reportes.ver'):
        kind=args.get('kind') or args.get('modulo') or values.get('tipo','inventario')
        source={'inventario':'inventario.ver','ventas':'ventas.ver','creditos':'creditos.ver',
                'finanzas':'finanzas.ver','contable':'contabilidad.ver','auditoria':'historial.ver',
                'compras':'inventario.ver','consolidado_adicional':'contabilidad.ver'}.get(kind)
        if source:keys.add(source)
        if values.get('formato')=='csv':keys.add('reportes.exportar')
    if endpoint.startswith('ventas.') and method=='POST' and values.get('movement_date'):
        from .operacion_service import today
        if values['movement_date']!=today():keys.add('ventas.corregir')
    if endpoint=='finanzas.index' and method=='POST' and values.get('action')=='open':keys.add('finanzas.personal')
    return keys
