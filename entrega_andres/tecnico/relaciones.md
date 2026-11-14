# Relaciones declaradas en modelos

Flechas: tabla con clave foránea -> tabla referenciada. Diagramas parciales por dominio; no expresan todas las reglas de cardinalidad. Todas las FK están en esquema_modelos.json. Los JSON tienen relaciones lógicas adicionales no protegidas por FK.

## Operación y cobros

```mermaid
flowchart TD
  purchase_lot["purchase_lot"]
  equipment["equipment"]
  equipment_event["equipment_event"]
  customer_collection["customer_collection"]
  admin_receipt["admin_receipt"]
  finance_day["finance_day"]
  finance_operation["finance_operation"]
  finance_operation -->|day_id| finance_day
  finance_operation -->|product_id| equipment
  equipment_event -->|product_id| equipment
  customer_collection -->|product_id| equipment
  admin_receipt -->|collection_id| customer_collection
  equipment -->|lot_id| purchase_lot
```

## Créditos

```mermaid
flowchart TD
  finance_operation["finance_operation"]
  creditos_venta["creditos_venta"]
  aliados_credito["aliados_credito"]
  desembolsos_credito["desembolsos_credito"]
  aplicaciones_credito["aplicaciones_credito"]
  customer_collection["customer_collection"]
  consignaciones_bancarias["consignaciones_bancarias"]
  consignaciones_bancarias -->|finance_operation_id| finance_operation
  creditos_venta -->|operacion_id| finance_operation
  creditos_venta -->|aliado_id| aliados_credito
  desembolsos_credito -->|aliado_id| aliados_credito
  desembolsos_credito -->|consignacion_id| consignaciones_bancarias
  aplicaciones_credito -->|desembolso_id| desembolsos_credito
  aplicaciones_credito -->|credito_id| creditos_venta
  aplicaciones_credito -->|cobro_id| customer_collection
```

## Bancos y personas

```mermaid
flowchart TD
  personas_contables["personas_contables"]
  bancos_destino["bancos_destino"]
  persona_banco["persona_banco"]
  consignaciones_bancarias["consignaciones_bancarias"]
  historial_consignaciones["historial_consignaciones"]
  finance_operation["finance_operation"]
  finance_supplier_payment["finance_supplier_payment"]
  persona_banco -->|persona_id| personas_contables
  persona_banco -->|banco_id| bancos_destino
  consignaciones_bancarias -->|persona_id| personas_contables
  consignaciones_bancarias -->|banco_id| bancos_destino
  consignaciones_bancarias -->|finance_operation_id| finance_operation
  consignaciones_bancarias -->|supplier_payment_id| finance_supplier_payment
  historial_consignaciones -->|consignacion_id| consignaciones_bancarias
  finance_operation -->|person_id| personas_contables
  finance_supplier_payment -->|operation_id| finance_operation
  finance_supplier_payment -->|person_id| personas_contables
  finance_supplier_payment -->|bank_id| bancos_destino
```

## Artículos y compras

```mermaid
flowchart TD
  purchase_lot["purchase_lot"]
  control_lote["control_lote"]
  lineas_lote["lineas_lote"]
  facturas_lote["facturas_lote"]
  categorias_stock["categorias_stock"]
  articulos_stock["articulos_stock"]
  unidades_stock["unidades_stock"]
  movimientos_stock["movimientos_stock"]
  finance_operation["finance_operation"]
  control_lote -->|lote_id| purchase_lot
  lineas_lote -->|lote_id| purchase_lot
  lineas_lote -->|articulo_id| articulos_stock
  facturas_lote -->|lote_id| purchase_lot
  articulos_stock -->|categoria_id| categorias_stock
  unidades_stock -->|articulo_id| articulos_stock
  movimientos_stock -->|articulo_id| articulos_stock
  movimientos_stock -->|lote_id| purchase_lot
  movimientos_stock -->|operacion_id| finance_operation
  movimientos_stock -->|unidad_id| unidades_stock
```

## Sociedades y POOL

```mermaid
flowchart TD
  socios["socios"]
  sociedades["sociedades"]
  participaciones_sociedad["participaciones_sociedad"]
  propiedad_equipo["propiedad_equipo"]
  equipment["equipment"]
  compras_pool["compras_pool"]
  comisiones_pool["comisiones_pool"]
  finance_operation["finance_operation"]
  finance_operation -->|product_id| equipment
  participaciones_sociedad -->|sociedad_id| sociedades
  participaciones_sociedad -->|socio_id| socios
  propiedad_equipo -->|producto_id| equipment
  propiedad_equipo -->|sociedad_id| sociedades
  compras_pool -->|producto_id| equipment
  compras_pool -->|venta_origen_id| finance_operation
  compras_pool -->|operacion_id| finance_operation
  comisiones_pool -->|operacion_id| finance_operation
  comisiones_pool -->|pago_operacion_id| finance_operation
```

## Liquidaciones

```mermaid
flowchart TD
  socios["socios"]
  sociedades["sociedades"]
  resultados_socio["resultados_socio"]
  liquidaciones_socio["liquidaciones_socio"]
  aplicaciones_liquidacion["aplicaciones_liquidacion"]
  disoluciones_sociedad["disoluciones_sociedad"]
  finance_operation["finance_operation"]
  equipment["equipment"]
  finance_operation -->|product_id| equipment
  resultados_socio -->|producto_id| equipment
  resultados_socio -->|operacion_id| finance_operation
  resultados_socio -->|sociedad_id| sociedades
  resultados_socio -->|socio_id| socios
  liquidaciones_socio -->|socio_id| socios
  aplicaciones_liquidacion -->|liquidacion_id| liquidaciones_socio
  aplicaciones_liquidacion -->|resultado_id| resultados_socio
  disoluciones_sociedad -->|sociedad_id| sociedades
  disoluciones_sociedad -->|socio_id| socios
  disoluciones_sociedad -->|producto_id| equipment
```
