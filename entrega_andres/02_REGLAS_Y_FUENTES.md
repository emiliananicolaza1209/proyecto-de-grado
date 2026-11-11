# Reglas de negocio y fuentes verificadas

Este documento describe el comportamiento observado en el ZIP. Emily debe aceptar su significado antes de presentarlo como regla definitiva de la empresa.

## Unidades
- Campos `*_cents`: centavos de COP; 120.000 COP = 12.000.000 centavos.
- `finance_operation.amount`, `minor_cost`, `finance_supplier_payment.amount` y valores financieros en sus JSON: centavos, aunque no terminen en `_cents`.
- Créditos `bruto`, `costo`, `neto`, `recibido`, desembolsos y aplicaciones: centavos.
- `consignaciones_bancarias.monto`: **pesos COP decimales**. Los servicios convierten con Decimal(centavos)/100. No sumarlo directamente con centavos.
- `*_bp`: puntos básicos; 1.800 equivale al 18 %, 5.000 al 50 %.
- Mantener enteros/Decimal para calcular; convertir a pesos solo en presentación. Números de JSON deben tener unidad explícita.
- El CSV documenta declaraciones estructurales, no certifica la semántica de todos los JSON. Consultar el servicio que escribe cada campo antes de reutilizarlo.

## Reglas prioritarias
| ID local | Regla | Fuente principal |
|---|---|---|
| RN-01 | Venta, cobro al cliente y recepción por administración son eventos diferentes; no sumar como ingresos nuevos | `pago_service.summary`, `finanzas_service.sources/report` |
| RN-02 | Excluir `voided=True` y registros bancarios inactivos según el indicador; preservar historia | `finanzas_service.report`, `consignaciones_finanzas.sincronizar_operacion` |
| RN-03 | Operación financiera de Venta usa importe neto según pagos; bruto cobrado puede diferir por crédito o recargo de datáfono | `finanzas_service.sale_net_amount/net_payment` |
| RN-04 | Crédito: neto menos recibido determina saldo actual; utilidad se reconoce en la fecha de venta; el desembolso no repite venta ni utilidad | `credito_service.credit_payment/settle/operation_collected` |
| RN-05 | Desembolso agrupado: aplicaciones suman exactamente el monto; no exceder saldo ni mezclar aliados | `credito_service.settle` |
| RN-06 | Datáfono con `surcharge_5`: neto = importe / 1,05, redondeado al centavo; no aplicar esa división a todos los cobros con tarjeta | `finanzas_service.net_payment` |
| RN-07 | Margen de cada venta financiera = amount - suma(costs[].amount); `minor_cost` se descuenta en el paso posterior del resultado | `finanzas_service.report/calculate` |
| RN-08 | Resultado del negocio, control Excel y caja son indicadores distintos | `finanzas_service.calculate/report` |
| RN-09 | Fondos propios de accesorios se reservan para reinversión; no son automáticamente deuda externa ni salida de caja | `finanzas_service.report`, `stock_service.parse_cost` |
| RN-10 | Comisión extra POOL se reconoce al vender; pagarla reduce caja, sin volver a reducir utilidad | `sociedad_service.on_sale/pay_pool_commission`, pruebas POOL |
| RN-11 | Porcentajes y participación histórica se conservan en las condiciones de la operación, no se sustituyen por el catálogo actual | `credito_service.attach`, `sociedad_service.assign_ownership/on_sale` |
| RN-12 | Cierre conserva totales y configuración en snapshot; pantalla usa snapshot cuando la jornada está cerrada | `finanzas_routes.index`, `finance_day.snapshot` |
| RN-13 | Pago de sueldo pertenece hoy a una persona por nombre y a la misma jornada; no excede salario configurado con asistencia | `finanzas_service.add_operation` |
| RN-14 | Parámetros `sandra_control_*`, `normal_return`, etc. forman parte del modelo diario y no equivalen por sí solos a salario pagado | `finanzas_service.calculate` |
| RN-15 | Stock de artículos se obtiene por suma de movimientos, incluidas compensaciones; equipos disponibles requieren archived=0 y status=Disponible | `stock_service.balance`, `inventario_service.stats` |

Los códigos RN de este paquete identifican reglas de integración; **no son nuevas historias de usuario**.

## Contrato del JSON financiero
`finance_day.config.staff[]`: name, role, salary (centavos), attended. `config` también guarda parámetros del cierre y cuentas.

`finance_operation.costs[]`: type, name, quantity, unit, amount; pueden aparecer stock_id, serial, detail, category y external_imei según el tipo. Reutilizar `parse_costs` y `stock_service.parse_cost` como referencia; no asumir que todos los elementos tienen todas las claves.

`finance_operation.payments[]`: account y amount; variantes: CRÉDITO tiene net, fee, ally_id, mode, rate_bp; TRANSFERENCIA tiene person_id/bank_id; DATÁFONO puede tener surcharge_5; RETOMA requiere su tratamiento propio. Nunca enviar estos objetos completos al modelo sin una lista de campos autorizados.

`finance_day.snapshot`: totals, counted, difference y config. Es el corte almacenado del cierre; un reporte actual y un snapshot pueden divergir si luego hay correcciones. Mostrar qué fuente se utilizó.

## Ejemplos en pesos COP
1. Crédito bruto 650.000, costo 18 % = 117.000, neto 533.000. Antes del desembolso: ingreso bancario 0. Después de abonos de 200.000 y 333.000: recibido 533.000, saldo 0; no se repite la utilidad. Caso existente en `tests/test_gestion_v16.py`.
2. Inicial efectiva 500.000 + crédito neto pactado 900.000 = venta neta 1.400.000. Con base de caja 200.000, efectivo esperado 700.000 antes del desembolso. No crear descuentos adicionales ficticios.
3. Comisión POOL 20.000 pagada: caja disminuye 20.000; el margen calculado antes del pago no disminuye otra vez. Caso existente en pruebas POOL.
4. Sueldo de prueba 80.000, pago del mismo día a la misma persona 30.000: pendiente 50.000. Si el pago corresponde a otra jornada, la versión actual no permite generalizar ese vínculo sin desarrollo adicional.
5. Una consignación de 120.000 se cambia de banco: total activo sigue siendo 120.000, no 240.000. Hay historial de corrección.

## No deducir reglas del nombre
No equiparar “productos originales”, CP Varios, equipos, capital y utilidad. No aplicar un descuento administrativo fijo global solo por aparecer en conversaciones antiguas: usar la regla implementada y validada para la operación concreta. No tratar DEBE/HABER del control interno como un libro contable universal.
