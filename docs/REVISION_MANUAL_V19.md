# Revisión manual de la integración V19

Actualización: el usuario autorizó implementar el conjunto después de estas
notas. Los apartados siguientes conservan la secuencia de la prueba anterior.
La implementación y sus comprobaciones están en `AJUSTES_V19_1.md`.

Fecha: 13/11/2026. Rama publicada: `integracion/cp-store-v19`, commit `eb99ae3`.
Entorno manual: `scripts/preview_ui.py`, SQLite temporal local, puerto 5018.
Los resultados de este entorno no son operaciones ni datos de producción.

## Evidencia funcional observada

1. Resumen inicial: 24 equipos ficticios; 12 disponibles y 12 vendidos.
2. Alta de retoma POOL, IMEI ficticio `990000000001232`, APPLE IPHONE 13,
   128 GB, AZUL, Usado, LOCAL CP STORE.
3. Compra al cliente: 500.000 COP. Costo adicional «COMISIÓN»: 20.000 COP.
4. La vista previa mostró 520.000 COP y el registro guardado en Inventario
   conservó ese costo. Estado Disponible; contador POOL disponible: 1.

Resultado del primer caso: aprobado en la interfaz de ensayo. Pendientes:
aporte de administración, venta POOL, pago posterior de comisión, crédito,
desembolsos y cierre/consultas del escenario integrado.

## Observaciones visuales aplazadas por el usuario

El usuario prioriza completar pruebas y desplegar para la entrega. No aplicar
ahora otro rediseño ni presentarlo como bloqueo financiero resuelto.

- El contorno de foco de los campos se superpone a etiquetas próximas.
  Separar etiquetas/campos y usar un contorno más fino con buen contraste;
  mantener una indicación de foco visible al navegar con teclado.
- La fila de costos adicionales desperdicia espacio y «Quitar» ocupa media
  fila. Proponer una fila compacta concepto/importe/acción con apilado móvil.
- El panel «POOL · retomas del local» es muy alto incluso cerrado, y el
  detalle abierto reúne demasiadas cifras en un párrafo. Proponer un resumen
  compacto de indicadores y un acceso al detalle, con etiquetas claras.
- La presentación monetaria de Inventario usa separadores distintos a los
  de Finanzas. Revisar uniformidad durante la misma revisión de presentación.

No se modificó CSS, plantillas ni lógica financiera por estas observaciones.
Conservar los datos de ensayo mientras se completa el recorrido: cerrar el
proceso de vista previa elimina la base temporal.

## Reglas y claridad adicionales indicadas por el usuario

- Solo puede existir una persona Principal por jornada; las demás deben ser
  Secundarias. La validación actual de `save_config` todavía no impone esa
  exclusividad: añadir control en servidor y orientación en el formulario,
  con una regresión que rechace dos principales. No tratarlo como implementado.
- Precisar en las tarjetas de Finanzas que los totales corresponden a la fecha
  seleccionada. Inventario muestra existencias actuales; no es un total diario.
- Distinguir compra POOL de venta: guardar la retoma en Inventario no registra
  el aporte administrativo en Finanzas. Una compra POOL financiera aporta su
  ganancia a la jornada, pero no incrementa ventas ni ventas netas.
- Revisar la etiqueta «Margen de ventas»: su cálculo incluye también la
  ganancia de compras POOL. Debe expresar ese alcance sin confundir con utilidad.
- Las capturas posteriores están en 13/11/2026, con las 13 operaciones de
  demostración. Volver al 12/10/2026 para el escenario aislado acordado.

Comprobación dirigida con otra base temporal: se reprodujeron los indicadores
del 13/11 (13 ventas, 7.920.000,25 COP netos, margen 4.320.000,25 COP y sueldos/
cargos 486.000 COP al configurar 50.000 + 25.000 de sueldos). «POR REVISAR» se
debe en ese caso al límite de la tabla de comisiones (`overflow=True`).
Registrar en 12/10 una compra POOL de costo 520.000 y aporte 620.000 generó
100.000 COP de ganancia de compra, 0 ventas y 0 ventas netas en esa jornada;
los indicadores del 13/11 permanecieron idénticos. Son resultados de ensayo,
no una confirmación de que el usuario ya haya registrado el aporte manualmente.

## Compra POOL: corrección del flujo solicitada

El usuario registró en la interfaz de ensayo la compra del equipo ya creado:
aporte 620.000 COP, cliente 500.000 COP, comisión/costos 20.000 COP y ganancia
100.000 COP. La captura está en la jornada 13/11/2026 y muestra el movimiento
«COMPRA POOL 990000000001232». Confirma el cálculo actual, pero **no aprueba
el flujo de negocio**, que el usuario rechazó durante esta prueba.

Requerimiento acordado: la vendedora inicia la compra en Movimientos cuando
ocurre la adquisición. Ese registro debe crear el equipo POOL y el movimiento
financiero asociados, conservar quién realizó la compra y causar la ganancia
en el DEBE de esa fecha. No puede exigir que administración haya creado antes
un equipo disponible que aún no se había comprado. Administración debe recibir
un aviso o pendiente para revisar/completar datos adicionales del mismo equipo,
sin crear otra compra, otro equipo ni otra ganancia.

Antes de implementar: definir campos mínimos verificables, revisión posterior,
permisos de vendedora, confirmación del aporte real, guardado atómico y protección
de IMEI/token repetidos. Mantener separados el precio al cliente, los costos
reales de compra, el aporte recibido y el capital asignado para su reventa.
Conservar soporte para operaciones previas ya registradas.

## Forma de entrega pedida por el usuario

Seguir primero con las pruebas manuales y registrar los demás hallazgos.
Al terminar, implementar y entregar **una sola carpeta de ajustes** que reúna
el flujo POOL, la exclusividad de Principal y las observaciones de presentación.
No instalar cambios intermedios ni presentar el flujo rechazado como aprobado.
Después ejecutar validación del conjunto antes de fusionar/desplegar.

## Costo comercial variable del POOL indicado durante la venta

El usuario aclara que el precio real de adquisición no es el costo comercial
que administración comunica a la vendedora. Ejemplo: cliente 500.000 COP y
comisión de compra 20.000 COP -> costo real 520.000 COP; administración puede
indicar 800.000 COP como costo comercial de venta. Ese importe varía y la
vendedora debe poder ingresarlo al registrar la venta, sin depender de que
administración haya actualizado previamente una lista de precios.

Guardar por separado costo real, aporte recibido, costo comercial usado en esa
venta, precio/neto de venta, comisión extra de venta y ganancia adicional de
administración. Conservar el importe aplicado en el historial de la operación;
los cambios posteriores de precios no deben reescribir ventas o cierres.
El ingreso del costo comercial por la vendedora no habilita editar el costo real
de compra ni consultar los costos privados de otros equipos.

Hallazgo actual: el servicio guarda un costo POOL asignado distinto del capital
para administración, pero la ruta de Vendedora elimina `cost_unit` y usa el
capital de Inventario. Ajustar ese permiso para POOL dentro del paquete único;
no extenderlo sin distinción a equipos de lote ni a artículos.

Evitar doble reconocimiento: si en la compra del ejemplo ya se registró aporte
620.000 y ganancia del local 100.000, la diferencia total comercial 800.000 -
520.000 = 280.000 incluye esos 100.000. El adicional todavía separado para
administración es 800.000 - 620.000 = 180.000, no otros 280.000 sobre los anteriores.
Si no se reconoció ganancia en la compra, el adicional sería 280.000.

Replantear el caso manual de venta: con costo comercial 800.000 y crédito al
18 %, una venta bruta de 800.000 no deja margen positivo. Se propone usar
1.100.000: neto 902.000; margen de venta tras comisión extra de 20.000 = 82.000,
antes de sueldos y otros gastos de jornada. Registrar por separado el adicional
de administración; no usar el total general del día precargado para validar
solo esta operación.

## Crédito: explicación solicitada y vista previa de las comisiones

«Neto pactado» es el importe final acordado a recibir del aliado, ingresado
directamente. No se vuelve a descontar el porcentaje y no implica que el
dinero ya haya sido desembolsado. El modo Porcentaje calcula ese neto a partir
del bruto. Proponer etiqueta «Valor final a recibir del aliado» y mostrar solo
los campos pertinentes al modo elegido.

El usuario reitera que hay dos comisiones POOL distintas: compra y venta.
La de compra del caso (20.000 COP) ya integra el costo real 520.000 COP. La
extra de venta (20.000 COP) reduce el margen de la operación de venta una vez,
en su fecha de origen; la fecha/medio de su entrega se controla por separado.
El descuento del aliado es un tercer concepto y no sustituye esas comisiones.

Las capturas siguientes todavía muestran crédito 800.000 y costo asignado
620.000: neto 656.000, costo del crédito 144.000 y vista previa de margen
36.000. Esa vista previa **no resta los 20.000 de comisión extra de venta**;
el cálculo guardado sí los agrega a los costos (margen resultante 16.000).
Corregir la vista previa para que muestre el efecto completo y ambas comisiones
sean distinguibles, evitando presentar esa estimación como ganancia final.

Las capturas siguen en el formulario de registro y sin banco seleccionado:
no acreditan todavía una venta guardada. Mantener la prueba como pendiente.
Al seleccionar IMEI se autocompleta el costo; al restaurar datos tras un error,
`costType` también vuelve a rellenarlo. Conservar el costo comercial ingresado
al restaurar el formulario; no atribuir sin evidencia las capturas a un reinicio
automático del campo por cualquier cambio de banco/aliado.

## Venta guardada y nuevas precisiones del usuario

La captura posterior muestra la venta «VENTA POOL PRUEBA», responsable ANA,
guardada en 13/11/2026 con crédito bruto 800.000 COP y venta neta 656.000 COP.
El detalle conserva el costo asignado 620.000 COP y añade la comisión extra
de venta 20.000 COP. Ese caso corresponde al ejemplo anterior: margen por
operación 16.000 COP, no al nuevo ejemplo de costo comercial 800.000 y venta
1.100.000. No registrar otra venta del mismo equipo para sustituir la evidencia.
Desembolso y entrega posterior de la comisión todavía pendientes de comprobar.

- Mover la aceptación de crédito aprobado al final del formulario, junto al
  botón Guardar. Debe ser visible cuando haya crédito y conservar su validación
  obligatoria en servidor; no quitar la confirmación para facilitar el guardado.
- El usuario precisa su denominación de compra: 500.000 pagados al cliente +
  100.000 de ganancia del local = 600.000 de valor de compra para administración.
  Ese importe integra el capital del equipo; no mostrar solo el pago al cliente
  como si fuera el importe completo de la operación.
- Mantener pendiente la precisión de si el importe total comunicado de 600.000
  excluye la comisión adicional de compra (20.000, total 620.000) o ya la incluye.
  Con precio al cliente 500.000 y comisión 20.000, un total final de 600.000
  dejaría 80.000, no 100.000, de ganancia neta de compra. No cambiar cálculos
  ni dar ambas cifras por compatibles hasta aclarar este desglose.
- El modal de detalle muestra la comisión automática POOL también dentro de
  «Completar costos del paquete» como una fila Proveedor. Revisar su edición
  para que una comisión automática no pueda cargarse otra vez como costo
  complementario ni requiera un proveedor ficticio para conservarse.
