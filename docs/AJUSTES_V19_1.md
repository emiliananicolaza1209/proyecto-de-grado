# Ajustes de la revisión manual V19.1

Fecha: 13 de noviembre de 2026. Base publicada: `eb99ae35c7f782c28982f1ff28e5b3ada06d0ce6`, rama `integracion/cp-store-v19`.

## Compra POOL desde el local

Finanzas → Registrar compra POOL permite registrar una compra directa sin que
administración haya creado antes el equipo. Se solicitan IMEI válido, modelo,
color, capacidad y local; se usan Usado y CP CELULARES. Los catálogos siguen
siendo controlados: no se inventan características del equipo para guardarlo.

La vendedora queda identificada por su sesión. Administración puede registrar
en nombre de una persona de la jornada. Equipo, compra, ganancia, propiedad y
pendiente de revisión se guardan en la misma transacción. Un error revierte el
conjunto. IMEI único, token y revisión de jornada evitan repetir la compra.

Administración verá el pendiente en Finanzas y en Inventario. Desde el detalle
puede completar los datos y marcar la revisión con una observación. Esa acción
conserva el equipo, no vuelve a registrar dinero y no cambia cierres anteriores.
El registro pendiente usa el historial de gestión existente; no requiere crear
tablas ni actualizar de nuevo el esquema PostgreSQL.

Las retomas anteriores conservan sus registros. La conciliación de un equipo
ya ingresado queda en una sección aparte, solo para administración. Las partes
de pago anteriores mantienen su validación de venta de origen.

## Importes separados

| Concepto del ejemplo | COP |
|---|---:|
| Pago al cliente | 500.000 |
| Ganancia del local al comprar | 100.000 |
| Compra para administración, antes de costos adicionales | 600.000 |
| Comisión de compra | 20.000 |
| Aporte recibido y capital del equipo | 620.000 |
| Costo real de adquisición, cliente + comisión | 520.000 |

La comisión de compra es una entrada independiente: si no existe, se ingresa
cero y el total del ejemplo es 600.000. Si existe, integra el aporte requerido.
La suma se valida en servidor y requiere confirmar el dinero y pagos reales.
La ganancia de compra aporta 100.000 al DEBE de esa fecha; no aumenta ventas.

Al vender, la vendedora escribe el costo comercial comunicado por administración.
Se conserva en la operación, sin modificar el costo privado de adquisición ni
permitir cambiar los costos de equipos de lote o artículos. El formulario de
error conserva el costo comercial ya ingresado.

| Venta de ejemplo, distinta de la venta manual anterior | COP |
|---|---:|
| Costo comercial POOL indicado | 800.000 |
| Venta bruta financiada | 1.100.000 |
| Descuento del aliado, 18 % | 198.000 |
| Venta neta | 902.000 |
| Comisión extra de venta POOL | 20.000 |
| Margen de esa venta, antes de otros gastos y sueldos | 82.000 |
| Adicional de administración, 800.000 − 620.000 | 180.000 |

La compra ya había causado 100.000. El adicional administrativo es 180.000;
no se vuelven a sumar 280.000 sobre esa ganancia anterior. La comisión extra de
venta se causa una sola vez. Su entrega posterior y los desembolsos del crédito
no crean otra utilidad. La comisión automática ya no aparece como proveedor
editable dentro de «Completar costos del paquete».

La evidencia manual previa fue otra venta: bruto 800.000, neto 656.000, costo
asignado 620.000 y comisión extra 20.000; su margen era 16.000. Este ajuste no
reescribe esa venta ni crea una venta adicional del mismo equipo.

## Personal y presentación

- Un máximo de una Principal por jornada; las demás son Secundarias. Servidor
  rechaza duplicados y las personas nuevas se sugieren como Secundarias.
  Los escenarios de prueba se actualizaron a esa regla, conservando las
  comprobaciones de importes y agregando una regresión que exige el rechazo.
- Confirmación de crédito aprobado al final del formulario, junto a Guardar.
  Sigue siendo obligatoria tanto en interfaz como en servidor.
- «Valor final acordado» muestra el importe final a recibir del aliado; el
  modo Porcentaje muestra su porcentaje. Se oculta el campo que no corresponde.
  El importe pendiente no se presenta como un desembolso recibido.
- La vista previa de venta incluye la comisión extra POOL, con el mismo
  importe usado por el servicio. El margen estimado concuerda con el guardado.
- Foco visible más fino, separación de etiquetas, filas de costos y botones
  Quitar compactos; panel POOL con indicadores en lugar de un párrafo extenso.
- Importes de Inventario con el formato COP usado por Finanzas.
- Finanzas identifica la fecha seleccionada y el margen de ventas y compras
  POOL. Inventario identifica existencias actuales y cifras acumuladas.

## Comprobaciones realizadas

- Suite completa en Python 3.12, distribuida en cuatro procesos independientes:
  834 casos, **776 aprobados, 58 omitidos y cero fallos**. Los 58 omitidos
  requieren PostgreSQL de ensayo; no se usó la base de producción.
- Nueve regresiones nuevas cubren compra atómica, identidad de vendedora,
  duplicados, importes, revisión, costo comercial, comisiones y desembolso
  posterior. Se incorporaron también al recorrido PostgreSQL de CI.
- Cinco pruebas Node de navegación aprobadas; JavaScript nuevo sin errores de
  sintaxis. Once comprobaciones DOM con HTML real de Flask verifican costo
  restaurado, margen completo, campos del aliado, aceptación, compra y personal.
- Se comprobó que las versiones base de los archivos modificados coinciden
  con el commit publicado. El paquete no vuelve a instalar parches anteriores.

Pendiente en el entorno del usuario: probar visualmente en el navegador y
ejecutar el nuevo workflow en GitHub con PostgreSQL y Chromium. Chromium no
pudo iniciarse en el entorno local de preparación; las comprobaciones DOM no
sustituyen esa revisión visual. Se añadió `check_ajustes_pool_v19.cjs` al workflow
para recorrer compra y venta POOL y cuatro anchos de pantalla.

Quedan para la prueba manual posterior la entrega de comisiones, desembolsos,
el cierre de un escenario aislado y sus consultas. El día precargado de la vista
previa contiene ventas de estrés que pueden superar la tabla de comisiones;
no se modificaron esas reglas para forzar su cierre.
