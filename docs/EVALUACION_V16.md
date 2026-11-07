# Evaluación del alcance · V16

Fecha: 28 de octubre de 2026. Esta revisión utiliza el código de entrega, las pruebas y las reglas acordadas en la conversación. No modifica el documento original de requisitos ni declara aceptación del 100 % de una historia sin su validación funcional con CP Store.

“Implementado para validación” significa que existe el flujo en esta entrega. “Parcial” identifica expresamente una limitación. Las reglas posteriores del negocio prevalecen para esta implementación; deben incorporarse también al documento de requisitos.

| Historia | Situación y evidencia |
|---|---|
| HU-LOT-001 · Gestionar proveedores | Implementado para validación: alta, edición, categoría, identificación y contacto, desactivación e historial. Los datos de contacto son opcionales; cotejar los mínimos obligatorios del documento con el negocio. |
| HU-LOT-002 · Crear lote manual | Implementado: borrador COP/USD, fecha, proveedor, cantidad y equipos/artículos. |
| HU-LOT-003 · Factura de compra | Implementado: PDF/JPG/PNG, descarga protegida y registro de archivo. No es el comprobante de una venta. |
| HU-LOT-004 · Guardar borrador | Implementado: las líneas no pasan a disponibles hasta confirmar. |
| HU-LOT-005 · Continuar revisión | Implementado: consultar borrador, agregar/retirar líneas, ajustar cantidad e importar Excel. |
| HU-LOT-006 · Confirmar lote | Implementado: confirmación completa y transaccional; no se habilitan entregas parciales. |
| HU-LOT-007 · Corregir/revertir lote | Implementado con límites: reabrir lotes V16 sin operaciones posteriores y guardar historial. Los lotes históricos y los dependientes requieren correcciones individuales/conciliación. |
| HU-LOT-008 · Importar Excel | Implementado: plantilla descargable, validación previa y carga al borrador. No importa cualquier Excel arbitrario sin adaptación. |
| HU-ESC-001 · DIG-1202 | Se conserva captura por campo IMEI. Prueba física específica fuera del alcance solicitado. |
| HU-ESC-002 · Etiquetas | Diferido por instrucción del usuario. No se declara probado. |
| HU-ESC-003 · Buscar por escaneo | Flujo disponible en software; falta aceptación con el lector físico en los puestos reales. |
| HU-ESC-004 · Cámara web | Diferido. |
| HU-ESC-005 · Completar desde catálogo | Parcial: catálogo, alias y recuperación de equipos ya registrados. Un IMEI desconocido no identifica automáticamente la referencia sin una fuente externa. |
| HU-ESC-006 · Visión de pantalla | Diferido. |
| HU-INV-001 · Equipo serializado | Se conserva registro, validación/duplicado de IMEI, condición, ubicación e historial. |
| HU-INV-002 · Artículo por cantidad | Implementado: categorías, productos, costos administrativos, cantidades, movimientos, desactivación y serial opcional para repuestos. Venta conectada con stock. |
| HU-INV-003 · Consulta | Estados, búsqueda y ubicación conservados; se añade condición y se restringe información según perfil. |
| HU-INV-004 · Referencias | Alias explícitos, normalización, edición/desactivación e historial. |
| HU-INV-005 · Editar equipo | Conservado con responsable autenticado. Se impide alterar costos de una compra POOL financiada sin conciliarla. |
| HU-INV-006 · Retiro de error | Retiro lógico/restauración con historial; una entrega a socio o reversión de lote no puede restaurarse por fuera de su proceso. Falta aceptación exhaustiva de todos los casos históricos. |
| HU-INV-007 · Participación | Implementado: sociedades, porcentajes de capital/utilidad separados, valores aportados y condiciones por equipo. |
| HU-INV-008 · Inversión | Implementado: capital pendiente por ubicación y propietario; el socio consulta su parte. |
| HU-INV-009 · Exhibición/etiqueta | Se conserva la condición Exhibición. La etiqueta queda diferida. |
| HU-TRA-001 · Trasladar | Flujo existente conservado, ahora con usuario autenticado y permisos. |
| HU-TRA-002 · Historial de traslado | Conserva origen/destino, motivo y responsable. |
| HU-TRA-003 · Ubicaciones | Catálogo con edición/desactivación; los movimientos históricos no se borran. |
| HU-VEN-001 · Venta | Conexión entre Finanzas y equipo existente; los equipos vendidos cambian de estado en Inventario y Ventas y pagos. Se conserva el flujo de venta de un pasamano en módulo 03. |
| HU-VEN-002 · Fecha automática | Parcial frente a una exigencia de hora comercial editable: hay fecha del negocio, motivo de corrección, control por rol y fecha/hora de auditoría; no se añadió un campo separado para editar la hora de venta. |
| HU-VEN-003 · Pagos combinados | Implementado según aclaración: hasta cinco medios dinámicos, créditos combinables, datáfono y retoma. No se limita a las tres modalidades del borrador antiguo. |
| HU-VEN-004 · Comprobante de venta | Diferido por instrucción del usuario. |
| HU-CRE-001 · Aliados | Alta/edición/desactivación, cinco aliados iniciales, porcentaje y destino habitual. Configuración inicial 0 %; requiere valores reales. |
| HU-CRE-002 · Venta financiada | Registro en Finanzas con aprobación confirmada, medios combinados y vínculo al equipo cuando corresponde. |
| HU-CRE-003 · Costo/neto | Porcentaje sobre crédito bruto o neto pactado. Condiciones históricas conservadas. |
| HU-CRE-004 · Estado del crédito | Pendiente, parcial, pagado y anulado cuando procede. Desembolsos parciales/agrupados y consignación única. Confirmación manual; no hay integración API bancaria. |
| HU-RET-001 · Retoma | Compra directa y parte de pago, COP, costos adicionales y vínculo a la venta en parte de pago. |
| HU-RET-002 · Incorporación | Disponibilidad inmediata por decisión expresa del negocio. Se elimina como condición funcional la aprobación previa del borrador antiguo. |
| HU-RET-003 · Utilidad | Compra con ganancia diaria, base del POOL, adicional administrativo, comisión extra y liquidación por socio. |

## Ajustes que debe recoger el documento de requisitos

1. Los créditos y su liquidación operativa se gestionan en Finanzas; Ventas y pagos muestra el equipo, sus cobros y estado.
2. Retoma equivale a POOL y admite compra directa sin venta de origen; parte de pago sí vincula una venta.
3. El ingreso al POOL es inmediato; no se exige la aprobación previa que figuraba en otra versión del requisito.
4. Un lote nuevo se confirma completo. Los históricos no se convierten retroactivamente en borradores.
5. Los pagos admiten hasta cinco medios; pueden combinar aliados.
6. La ganancia de compra POOL y la comisión extra de $20.000 son hechos distintos de una venta y de la comisión habitual.
7. Los nombres de los módulos se conservan.

## Pendientes y mejoras posteriores

- Aceptación con las vendedoras y administración usando sus jornadas reales, incluidos cierres de domingo, festivo y día ordinario.
- Recuperación integral de acuerdos pagados: devolución de desembolsos, reversión de anticipos/liquidaciones y corrección de compras POOL ya financiadas. Los bloqueos actuales evitan borrar sus efectos por separado.
- Manejo de disoluciones que compensen automáticamente varios equipos y saldos entre sí.
- Hora comercial editable si se mantiene ese criterio de HU-VEN-002; búsqueda externa por IMEI si se mantiene el de HU-ESC-005.
- Impresoras/etiquetas, cámara, visión y comprobante de venta desde móvil, expresamente diferidos.
- PostgreSQL, despliegue multiusuario, recuperación probada de respaldos, pruebas de concurrencia/carga, HTTPS y revisión de seguridad antes de publicación. La aplicación se ejecuta localmente con `run.py`.
- Evaluación de los demás módulos e historias fuera del intervalo solicitado. Esta entrega no certifica el módulo de IA ni todos los requisitos tributarios o no funcionales.

No se certifica equivalencia con cualquier Excel o una jornada todavía no aportada. Se mantienen los casos de comparación del Excel que ya formaban parte de las pruebas de la base recibida.
