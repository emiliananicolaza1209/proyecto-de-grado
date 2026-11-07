# Reglas operativas de CP Store · V16

Se conservan los nombres de los módulos. La jornada financiera concentra los cálculos y créditos; Ventas y pagos conserva la consulta del equipo, pasamano, cobros y su estado. Un registro financiero ligado a un equipo actualiza ese mismo equipo; no crea una copia del inventario.

## Compras, lotes y artículos

- Un lote nuevo empieza como borrador. Agregar filas o importar Excel no aumenta todavía el inventario disponible.
- La confirmación valida la cantidad completa, las referencias y los identificadores. Si hay un error, no ingresa parcialmente el lote.
- La plantilla Excel se descarga dentro de Compras y lotes. Usa las columnas y los ID que muestra la pantalla; la importación no intenta adivinar un modelo a partir de un IMEI desconocido.
- La compra por lote puede expresarse en COP o USD. En USD se aplica la tasa del lote y se suma el envío asignado a cada unidad. En COP no se aplica conversión.
- Accesorios: cantidades sin IMEI. Repuestos: serial opcional por unidad, sin imponer el formato de un IMEI.
- El costo administrativo del artículo se guarda para las ventas futuras. Cada venta conserva el costo que utilizó; no se recalculan ventas anteriores al editar el catálogo.
- Los fondos CP VARIOS, CP HIDROGELES, BATERÍAS y MEMORIAS reducen el margen como costo, pero no generan automáticamente una salida de caja. Se mantiene el control diario de esos fondos.
- Proveedores, categorías, artículos, aliados y socios con historia se desactivan; no se borran sus vínculos históricos.
- Las facturas de compra admiten PDF, PNG o JPG, hasta 8 MB. Se guardan dentro de `instance/facturas` y deben incluirse en los respaldos.
- Un lote nuevo confirmado puede reabrirse con motivo si no tiene movimientos dependientes. La reversión conserva historia. Los lotes anteriores a V16 se mantienen como históricos confirmados; se corrigen mediante los controles individuales existentes.

## Compra del POOL y utilidad al vender

Retoma y POOL son el mismo origen: celular usado comprado a un cliente, sin lote, proveedor CP CELULARES y compra en COP. El equipo queda disponible al registrarlo. Puede incluir hasta cinco costos adicionales de comisión o reparación.

Ejemplo confirmado de compra directa:

| Concepto | COP |
|---|---:|
| Dinero entregado por administración | 600.000 |
| Precio pagado al cliente | 500.000 |
| Otros costos pagados | 0 |
| Ganancia de compra de la jornada | 100.000 |
| Capital que se conserva en el POOL | 600.000 |

Los $100.000 quedan en caja y en el resultado del día. La operación se identifica como **Compra POOL**, no incrementa el conteo de ventas. Al revender el equipo se utiliza una base de capital de $600.000, de modo que los mismos $100.000 no se vuelvan a reconocer como ganancia.

Si hubo $50.000 de reparaciones pagadas y el aporte fue $600.000, la ganancia de compra sería $50.000. Para confirmar se exige que el aporte cubra compra y costos registrados, y se confirma que esos pagos ocurrieron.

Administración determina el valor asignado para la venta. No puede ser inferior al capital invertido. Por ejemplo, con capital de $600.000, valor asignado de $700.000 y venta neta de $800.000:

- $100.000 son el adicional del POOL para administración/socios.
- El margen de la operación diaria es $100.000 antes de otros costos y comisión extra.
- Se descuentan $20.000 de comisión extra POOL: quedan $80.000 antes de los demás conceptos de la jornada.

La comisión extra no sustituye la comisión habitual. Se reparte entre el personal con asistencia confirmada al registrar la venta. Con tres personas, el reparto exacto es $6.666,67, $6.666,67 y $6.666,66. Cambiar después la asistencia no modifica ese reparto histórico. Al confirmar su entrega se retira dinero de caja; no se vuelve a descontar de la utilidad.

### Retoma como parte de pago

Primero se ingresa el equipo recibido al POOL. En la venta se selecciona el medio **RETOMA**, ese equipo y exactamente su valor de compra. No es una transferencia ni efectivo; aparece como valor recibido en equipos. No se permite utilizar la misma retoma dos veces, ni vender y recibir el mismo equipo en la misma operación.

Después, si administración entrega un aporte para financiar esa retoma, se registra en Compras y comisiones POOL con origen **Parte de pago** y se vincula la venta. No se registra un pago ficticio al cliente: el valor ya se le reconoció en la venta. Solo se confirma un aporte si el dinero fue realmente entregado.

## Créditos y medios combinados

Una venta admite hasta cinco medios añadidos según se necesiten. Puede mezclar efectivo, transferencias, datáfono, uno o varios aliados y retoma.

| Caso | Operación | Neto COP |
|---|---|---:|
| Datáfono con recargo de 5 % sobre el precio | 1.155.000 / 1,05 | 1.100.000 |
| Crédito SU+PAY con descuento de 18 % | 650.000 × (1 − 0,18) | 533.000 |
| Inicial efectivamente recibida + neto pactado del aliado | 500.000 + 900.000 | 1.400.000 |

En el último caso, los $100.000 de inicial que el negocio asumió no se registran como dinero recibido ni se descuentan una segunda vez. Los costos del equipo y accesorios sí se restan de los $1.400.000.

La utilidad y la comisión de la jornada se calculan en la fecha de la venta aprobada. El crédito pendiente se muestra separado del dinero recibido en bancos. El porcentaje, neto y cuenta pactados se conservan en cada crédito. Editar el aliado afecta nuevas ventas.

Los desembolsos pueden ser parciales o cubrir varias ventas del mismo aliado. La suma aplicada debe coincidir exactamente con lo recibido. Se confirma la cuenta real de recepción, que puede diferir de la cuenta prevista si se acordó otro destino. El registro crea una sola consignación contable por desembolso y actualiza los equipos asociados. No crea una segunda venta ni una segunda utilidad.

No se hace conexión automática con ADDI, Sistecrédito u otras plataformas, ni se consulta el banco. El personal registra la aprobación y administración confirma el ingreso real.

## Sociedades y liquidaciones

Cada sociedad tiene participantes y dos distribuciones independientes: capital y utilidad. Cada distribución debe sumar 100 %. El capital puede ingresarse como porcentajes o como valores aportados, de los que se calculan las participaciones. Los equipos conservan las condiciones que se les asignaron; cambiar la configuración sirve para nuevas asignaciones.

- En equipos POOL, la utilidad de los socios es el adicional entre el valor asignado y el capital del POOL.
- En los demás equipos, se reparte el margen de esa venta después de sus costos y costos menores. La liquidación de socios queda separada del cierre y de las comisiones del personal.
- Se puede consultar un período de cualquier duración: 7, 13, 15 días u otro intervalo.
- Se separan utilidad pendiente, utilidad ya pagada y capital pendiente. Una liquidación pagada no vuelve a aparecer como deuda.
- Normalmente se confirma el pago después del recaudo. Si se paga antes, exige confirmar que es un anticipo y registrar fuente y referencia.
- Por defecto se paga la utilidad y el capital queda identificado para reinversión. La opción de incluir capital permite devolverlo expresamente. El sistema no reinvierte automáticamente el capital en otro equipo.
- Las pérdidas del período se incluyen al calcular su liquidación. Si el neto no es positivo, no se registra un pago positivo ficticio.

### Salida de un socio con equipos sin vender

El acuerdo se registra por equipo y puede usar el costo completo registrado —incluidos costos incorporados— o una valoración acordada.

**Dinero:** otro socio compra la participación. El importe debe coincidir con la participación sobre la valoración elegida. Se reasignan las participaciones y se conserva el costo histórico del equipo. La valoración de salida queda en el acuerdo; no se registra como una venta a cliente.

**Equipo:** se entrega la unidad completa. Si quien la recibe solo posee una parte, se confirma la compensación de la participación de los demás socios. Ejemplo: equipo valorado en $600.000, participación del 50 %: recibe la unidad y compensa $300.000. El equipo queda como **Entregado a socio**, fuera de disponibles, y no puede restaurarse con el botón genérico del inventario.

Si el acuerdo se resuelve con un conjunto de varios equipos, se registra cada unidad y su compensación. El sistema no compensa automáticamente diferencias entre varios equipos o varios acuerdos. Tampoco ejecuta transferencias bancarias.

## Correcciones e historial

Los cambios nuevos guardan usuario, fecha y motivo. Las ventas conservan los controles de revisión para evitar sobrescribir cambios de otra ventana.

Las correcciones habituales de medios bancarios permanecen disponibles en ventas complementarias sin contratos nuevos. No se puede convertir una operación antigua en crédito o salida de stock mediante una edición que omita los registros asociados: se concilia/anula la anterior cuando procede y se registra la venta correcta.

Las compras financiadas POOL, comisiones ya entregadas, liquidaciones pagadas y acuerdos de disolución no pueden editarse o anularse desde el movimiento de caja aislado. Las ventas con dinero ya cobrado o liquidado requieren conciliación. Esta entrega no automatiza reembolsos ni la reversión integral de esos acuerdos pagados.
