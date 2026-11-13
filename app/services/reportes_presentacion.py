"""Vista de negocio. Las consultas y contratos en centavos no se modifican."""
from decimal import Decimal
from datetime import datetime
from .operacion_service import COLOMBIA
from ..extensions import db
from ..models import Producto, Lote
from ..models.contabilidad import PersonaContable, BancoDestino, ConsignacionBancaria
from ..models.finanzas import OperacionFinanciera
from ..models.gestion import AliadoCredito, Sociedad

TITLES = {
    'inventario': 'Inventario actual', 'ventas': 'Ventas del periodo',
    'creditos': 'Créditos y saldos', 'finanzas': 'Utilidad por jornada',
    'compras': 'Compras y lotes', 'contable': 'Consignaciones por persona y banco',
    'auditoria': 'Historial de gestión', 'consolidado_adicional': 'Fondos y sueldos',
}
# (campo del contrato, etiqueta visible, formato). Se conserva el contrato original.
COLUMNS = {
    'ventas': [('id', 'Operación', 'reference'), ('fecha', 'Fecha', 'text'),
        ('descripcion', 'Descripción', 'text'), ('vendedor', 'Vendedor', 'text'),
        ('equipo', 'Equipo / IMEI', 'text'), ('anulada', 'Estado', 'void'),
        ('venta_neta', 'Venta neta · COP', 'money'), ('costos', 'Costos · COP', 'money'),
        ('costos_menores', 'Costos menores · COP', 'money')],
    'inventario': [('imei', 'IMEI', 'text'), ('referencia', 'Referencia', 'text'),
        ('capacidad', 'Capacidad · GB', 'text'), ('color', 'Color', 'text'),
        ('condicion', 'Condición', 'text'), ('ubicacion', 'Ubicación', 'text'),
        ('estado', 'Estado', 'status'), ('lote', 'Lote', 'text'),
        ('costo', 'Costo · COP', 'money'), ('sociedad', 'Sociedad', 'text')],
    'creditos': [('id', 'Crédito', 'reference'), ('fecha', 'Fecha de venta', 'text'),
        ('aliado', 'Aliado', 'text'), ('bruto', 'Valor financiado · COP', 'money'),
        ('costo', 'Costo del aliado · COP', 'money'), ('neto', 'Neto pactado · COP', 'money'),
        ('recibido', 'Desembolsado · COP', 'money'), ('pendiente', 'Pendiente · COP', 'money'),
        ('estado', 'Estado', 'status')],
    'finanzas': [('fecha', 'Jornada', 'text'), ('fuente', 'Estado de la jornada', 'status'),
        ('debe', 'Margen antes de costos menores · COP', 'money'),
        ('haber', 'Costos menores · COP', 'money'), ('service', 'Gastos de servicio · COP', 'money'),
        ('pd', 'Gastos PD · COP', 'money'), ('liquidation', 'Sueldos y cargos · COP', 'money'),
        ('commission', 'Comisiones · COP', 'money'), ('owner_result', 'Utilidad del día · COP', 'money')],
    'compras': [('codigo', 'Lote', 'text'), ('fecha', 'Fecha de ingreso', 'text'),
        ('proveedor', 'Proveedor', 'text'), ('estado', 'Estado', 'status'),
        ('esperados', 'Equipos esperados', 'number'), ('equipos', 'Equipos activos', 'number'),
        ('capital_equipos', 'Capital de equipos · COP', 'money')],
    'contable': [('fecha', 'Fecha', 'text'), ('persona', 'Persona titular', 'text'),
        ('identificacion', 'Identificación', 'text'), ('banco', 'Banco destino', 'text'),
        ('monto', 'Valor consignado · COP', 'money'), ('origen', 'Origen / referencia', 'text')],
    'auditoria': [('fecha', 'Fecha', 'text'), ('entidad', 'Área', 'text'),
        ('registro', 'Registro', 'reference'), ('accion', 'Acción', 'text'),
        ('actor', 'Responsable', 'text'), ('motivo', 'Motivo', 'text')],
}
SALARIES = [('persona', 'Persona', 'text'), ('causado', 'Sueldo causado · COP', 'money'),
    ('pagado_misma_jornada', 'Pagado en la misma jornada · COP', 'money'),
    ('pendiente', 'Pendiente · COP', 'money')]
FUNDS = [('concepto', 'Fondo', 'text'), ('capital_reservado', 'Capital reservado · COP', 'money')]


def cop(cents):
    if cents is None:
        return 'Por revisar'
    value = Decimal(str(cents)) / 100
    return '$ ' + format(value, ',.2f').replace(',', 'X').replace('.', ',').replace('X', '.')


def _lookup(model, ids):
    ids = {i for i in ids if i is not None}
    return {obj.id: obj for obj in db.session.scalars(db.select(model).where(model.id.in_(ids)))} if ids else {}


def _display_rows(kind, rows):
    # Copias: ningún nombre o importe de presentación altera los datos del servicio.
    rows = [dict(row) for row in rows]
    if kind == 'contable':
        people = _lookup(PersonaContable, (r.get('persona_id') for r in rows))
        banks = _lookup(BancoDestino, (r.get('banco_id') for r in rows))
        operations = _lookup(OperacionFinanciera, (r.get('operacion') for r in rows))
        records = _lookup(ConsignacionBancaria, (r.get('id') for r in rows))
        for row in rows:
            person, bank, operation = people.get(row.get('persona_id')), banks.get(row.get('banco_id')), operations.get(row.get('operacion'))
            record=records.get(row.get('id'))
            row.update(persona=person.nombre if person else 'Titular por revisar',
                identificacion=person.identificacion if person else '—',
                banco=bank.nombre if bank else 'Sin banco asignado',
                origen=operation.description if operation else (record.referencia if record and record.referencia else 'Registro contable'))
    elif kind == 'ventas':
        equipment = _lookup(Producto, (r.get('equipo') for r in rows))
        for row in rows:
            p = equipment.get(row.get('equipo'))
            row['equipo'] = f'{p.model} · {p.imei}' if p else 'Venta complementaria'
    elif kind == 'inventario':
        lots = _lookup(Lote, (r.get('lote') for r in rows))
        societies = _lookup(Sociedad, (r.get('sociedad') for r in rows))
        for row in rows:
            lot, society = lots.get(row.get('lote')), societies.get(row.get('sociedad'))
            row['lote'] = lot.code if lot else 'Sin lote'
            if 'sociedad' in row:
                row['sociedad'] = society.nombre if society else 'Sin sociedad asignada'
    return rows


def table(columns, rows):
    def cell(value, kind):
        if kind == 'money':
            return dict(text=cop(value), value=Decimal(str(value))/100 if value is not None else 'Por revisar', kind=kind)
        if kind == 'void':
            value = 'Anulada' if value else 'Vigente'
            kind = 'status'
        elif kind == 'reference' and value is not None:
            value = '#' + str(value)
        text = '—' if value is None or value == '' else str(value)
        return dict(text=text, value=value if value is not None else '', kind=kind)
    return dict(columns=[dict(key=k, label=label, kind=kind) for k, label, kind in columns],
                rows=[[cell(row.get(k), kind) for k, _, kind in columns] for row in rows])


def present(kind, data, args):
    rows = _display_rows(kind, data['filas'])
    columns = COLUMNS.get(kind, [])
    if kind == 'inventario':
        columns = [c for c in columns if c[0] not in ('costo', 'sociedad') or any(c[0] in r for r in rows)]
    elif kind == 'consolidado_adicional':
        columns = SALARIES if args.get('concepto') == 'sueldos' else FUNDS
    view = dict(title=TITLES[kind], **table(columns, rows), metrics=[], additional=[])
    try:
        view['generated']=datetime.fromisoformat(data['generado']).astimezone(COLOMBIA).strftime('%d/%m/%Y · %H:%M')
    except (KeyError,ValueError,TypeError):
        view['generated']='Fecha no disponible'
    view['metrics'].append(dict(label='Registros encontrados', value=str(len(rows))))
    for key, label in [('venta_neta', 'Ventas netas'), ('total', 'Total consignado'), ('pendiente', 'Saldo pendiente actual')]:
        if key in data:
            view['metrics'].append(dict(label=label, value=cop(data[key])))
    if 'cantidad' in data and kind == 'ventas':
        view['metrics'].append(dict(label='Ventas vigentes', value=str(data['cantidad'])))
    for key, label in [('dias_incluidos', 'Jornadas incluidas'), ('dias_sin_jornada', 'Días sin jornada registrada')]:
        if key in data:
            view['metrics'].append(dict(label=label, value=str(data[key])))
    if kind == 'finanzas':
        for key, label in [('debe', 'Margen antes de costos menores'), ('commission', 'Comisiones'), ('owner_result', 'Utilidad del periodo')]:
            view['metrics'].append(dict(label=label, value=cop(data['totales'].get(key))))
        if data['sueldos']:
            view['additional'].append(dict(title='Sueldos del periodo', **table(SALARIES, data['sueldos'])))
        if data['fondos']:
            view['additional'].append(dict(title='Capital reservado por fondo', **table(FUNDS,
                [dict(concepto=k, capital_reservado=v) for k, v in sorted(data['fondos'].items())])))
    view['metadata'] = [('Reporte', view['title']), ('Moneda', 'COP'), ('Unidad de los importes', 'Pesos'),
        ('Generado', data.get('generado', '')), ('Zona horaria', data.get('zona', ''))]
    for key, label in [('desde', 'Desde'), ('hasta', 'Hasta'), ('dias_incluidos', 'Jornadas incluidas'),
                       ('dias_sin_jornada', 'Días sin jornada registrada')]:
        if key in data:
            view['metadata'].append((label, data[key]))
    view['metadata'].extend(('Advertencia', w) for w in data.get('advertencias', []))
    return view


def filter_options(administration=False):
    options = dict(locations=db.session.scalars(db.select(Producto.location).distinct().order_by(Producto.location)).all(),
                   sellers=[], allies=[])
    if administration:
        options.update(sellers=db.session.scalars(db.select(OperacionFinanciera.seller).distinct().order_by(OperacionFinanciera.seller)).all(),
                       allies=db.session.scalars(db.select(AliadoCredito).order_by(AliadoCredito.nombre)).all())
    return options
