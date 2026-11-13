# CP Store V18.1 — cierre de usabilidad y reportes

Fecha: 11 de noviembre de 2026. Base requerida: V18 instalada.

## Cambios incluidos

- Las secciones Movimientos, Proveedores y gastos, Personal y reglas y Cierre están en el lateral. Se conserva la fecha consultada y se identifica una sola sección activa.
- Movimientos empieza con el listado y acciones explícitas. Registrar movimiento y Registrar compra POOL llevan a una vista propia; los costos se muestran como una sección del formulario, sin acordeones encadenados.
- Volver a movimientos y Cancelar conservan la jornada. El regreso general sigue conservando filtros y desplazamiento. El filtro local de movimientos también se recuerda.
- El reporte contable presenta fecha, titular, identificación, nombre del banco, valor consignado en COP y origen/referencia. No muestra persona_id ni banco_id como columnas de negocio.
- Los importes de reportes, recepción de dinero y listados de ventas usan formato colombiano; no se muestran centavos como si fueran pesos. Un monto interno de 12.000.025 centavos se presenta como $120.000,25.
- Los filtros de reportes se muestran según el tipo seleccionado. El aliado se elige por nombre. Se reemplaza el bloque de JSON por totales y cobertura legibles; no se suman cierres físicos de caja entre jornadas.
- Los botones de exportación de la interfaz descargan nombres y valores en pesos. Excel conserva importes numéricos, incluidos negativos, y el formato COP. CSV conserva valores decimales y protección frente a fórmulas en textos.
- Se conserva el azul, blanco, gris y la semántica de estados de V18. Se ajustan los nuevos formularios y filtros para pantallas estrechas.

## Contratos, datos y responsabilidad

No se modifica el esquema de PostgreSQL, no se ejecutan migraciones y no se cambian las reglas de cálculo de ventas, créditos, liquidaciones o devoluciones. Se añade una capa de presentación de lectura.

Los servicios y consultas que consume Andrés mantienen centavos e identificadores internos. Las exportaciones técnicas sin el parámetro `presentacion=usuario` mantienen su contrato anterior. Los enlaces visibles de la interfaz añaden ese parámetro para obtener la versión legible. No se implementa un nuevo modelo predictivo ni un chatbot.

## Validación local

- Suite completa: 179 pruebas descubiertas; 166 aprobadas, 13 optativas de PostgreSQL omitidas. No se dispone aquí de la conexión privada de Render.
- Diez pruebas nuevas comprueban nombres, unidades, XLSX/CSV, negativos, protección de fórmulas, permisos, conservación de filtros y los POST de registro válido e inválido.
- Dos pruebas anteriores se dirigen a la nueva URL del formulario (`accion=registrar`): conservan todas sus comprobaciones de reglas y pagos.
- Tres pruebas Node verifican destinos de regreso y selección del lateral por sección. Validación de sintaxis de los archivos JS modificados.
- El recorrido Playwright existente se amplía con reportes y formulario financiero a 1440, 1024, 390 y 320 px. Está preparado para CI; NO se ejecutó aquí porque el entorno no permite iniciar Chromium. La revisión visual y accesibilidad en navegador sigue pendiente.
- La ejecución PostgreSQL comunicada por Emily tuvo 15 aprobadas y una desconexión; el caso aislado pasó sin cambios. Esa ejecución no se presenta como una suite PostgreSQL totalmente aprobada ni como una causa corregida. Revisar registros de Render y repetir la validación en CI y en el servicio público.

## Orden de cierre para la entrega del 12 de noviembre

1. Instalar esta corrección y ejecutar las pruebas indicadas en LEEME_PRIMERO.md.
2. Recorrido visual con datos de octubre, escritorio y celular: lateral, regreso, filtros, importes y exportación contable.
3. Recorrido por roles: ingreso de equipo, venta, abono, recepción, crédito, finanzas y cierre. Comparar resultados con operaciones de prueba conocidas; no crear movimientos de prueba en datos reales.
4. Verificar el estado de la integración de Andrés y los registros de la desconexión PostgreSQL.
5. Subir la versión completa, revisar CI y desplegar el servicio web en Render con la base existente. Seguir docs/DESPLIEGUE_RENDER_V18.md.
6. Ejecutar scripts/verificar_despliegue.py sobre la URL HTTPS y repetir los recorridos con autenticación, permisos y reinicio. Guardar evidencias de resultados y limitaciones.

### Pendientes que el rediseño no resuelve

- La URL pública, el despliegue y las pruebas desde otro dispositivo todavía deben completarse.
- Las facturas adjuntas necesitan una decisión de almacenamiento persistente. El perfil gratuito preparado deshabilita nuevas cargas en disco efímero; no afirmar que esta función está habilitada si no se configuró almacenamiento real.
- Las devoluciones con dinero recibido siguen requiriendo aclarar capital reembolsado frente al importe de Gastos de servicio, créditos desembolsados y comisiones pagadas. Se mantienen los bloqueos existentes.
- El consolidado “Originales” requiere definir cómo se clasifica ese inventario. No se inventa una categoría a partir del nombre de productos.
- La funcionalidad de analítica/chatbot de Andrés y las restantes historias de usuario deben evaluarse con sus evidencias. Instalar V18.1 no equivale a completar el 100 % de los requerimientos originales.
