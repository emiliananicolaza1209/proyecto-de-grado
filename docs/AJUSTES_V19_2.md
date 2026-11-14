# CP Store V19.2: contabilidad, usuarios y diseño adaptable

Base publicada: `e68b126d2c2617fd8eabfd1440dfbaec1dcc28e6`, rama `integracion/cp-store-v19`.

## Corrección contable

El filtro anterior compilaba `date(fecha) >= parametro::VARCHAR` con el controlador
PostgreSQL. Esa comparación no tiene operador en PostgreSQL y puede causar el
error 500 al abrir Información contable, aunque SQLite la admite.
Ahora se comparan dos límites DateTime: inicio incluido y medianoche del día
siguiente excluida. Se conserva el día local de las consignaciones, su estado
activo y sus valores. También se corrige un atributo `value` de un campo de fecha
que contenía HTML en vez de una fecha ISO.

## Usuarios y permisos

Pantalla con búsqueda, tarjetas de usuario, estado y matriz por módulos.
Cada usuario puede conservar los permisos de su perfil o personalizarlos.
La personalización limita el perfil: no permite obtener funciones reservadas a
otro perfil. Para distribuir funciones administrativas en varios módulos, usar
Administrador y seleccionar solo las necesarias. Propietario mantiene el control
completo; Socio conserva la restricción a sus propios resultados.

Opciones: inventario y traslados; ventas, cobros y recepciones; movimientos,
compra POOL, proveedores, personal, correcciones y cierre; créditos y aliados;
sociedades; reportes, exportaciones, analítica, chat, contabilidad e historial.
Las acciones requieren consultar el módulo correspondiente. Editar compras
requiere acceso a sus costos. Abrir una jornada requiere Cierre y Personal,
porque la apertura también guarda su personal y reglas.

Las restricciones se comprueban en el servidor, incluyendo URL directa, POST,
consultas, API y exportaciones. Las exportaciones respetan el módulo de origen.
Los formularios sin ninguna acción permitida se muestran deshabilitados.
Se conservan CSRF, bloqueo del último propietario, auditoría y control de sesión.
Guardar accesos invalida las sesiones anteriores; una edición desactualizada se
rechaza. Un usuario sin costo de inventario recibe una ficha de consulta sin
importes privados; puede trasladar si tiene esa función habilitada.

No se modifican fórmulas de ventas, créditos, comisiones POOL ni cierres históricos.

## Actualización de base

PostgreSQL pasa de revisión 2 a 3 mediante `actualizar-postgres`. Solo agrega
`permisos_usuario`, sin alterar usuarios, sesiones guardadas ni registros del
negocio. Desde revisión 1 primero agrega las tres tablas contables de revisión 2.
La operación es transaccional, usa el bloqueo común y admite repetición.
Una base incompleta o de revisión desconocida se rechaza. Una base vacía no se
inicializa con este comando. No hay DDL automático en las rutas web.

SQLite registra la revisión nueva 20. Los usuarios existentes sin personalización
conservan su perfil. Si falta la tabla de permisos, las páginas autenticadas
quedan temporalmente no disponibles hasta actualizar el esquema; no se conceden
permisos por omisión.

## Revisión adaptable

`tests/check_responsive_v20.cjs` recorre 33 pantallas con datos temporales:
inventario y formularios, ventas, recepciones, cuatro secciones de Finanzas,
compras POOL, créditos, sociedades, reportes, analítica, chat, contabilidad,
historial, acceso y Usuarios.

Chromium: anchos 320, 360, 375, 390, 412, 430, 768, 810, 1024, 1366 y 1920 px.
WebKit: 375, 390, 430, 768, 810 y 1024 px. Incluye tableta horizontal,
entrada táctil emulada, menú móvil, matriz de permisos, desbordamientos de página
y errores JavaScript. Son 561 combinaciones de pantalla y tamaño.

El trabajo `responsive` de GitHub Actions genera resultado JSON y capturas de
datos ficticios en el artefacto `responsive-v20`. Ejecutarlo y revisar los fallos
antes de publicar. La batería no equivale a probar dispositivos físicos ni la
interfaz nativa de Safari, Chrome Android o los teclados de cada teléfono.
Durante la preparación local se comprobó la respuesta HTTP de las 33 pantallas
y el comportamiento DOM de Usuarios. La ejecución visual en navegadores está
pendiente de Actions: este entorno bloquea sockets Unix necesarios para iniciarlos.

## Secuencia de publicación

1. Aplicar el parche y ejecutar pruebas locales.
2. Subir únicamente su lista de archivos a la rama de integración.
3. Esperar los dos trabajos de Actions: `funcionales` y `responsive`.
4. Actualizar la base existente con el código nuevo, conservando el respaldo
   habitual. Usar la URL externa únicamente en el proceso local del comando.
5. Desplegar el último commit en Render y repetir la comprobación autenticada,
   especialmente Información contable y Usuarios. La URL interna configurada en
   Render permanece como está.

Aplicar el parche localmente no publica ni despliega la versión.

## Evidencia de preparación

- Suite completa con SQLite: 865 casos; 791 aprobados y 74 PostgreSQL omitidos.
- PostgreSQL 17.11 de ensayo: 83 pruebas aprobadas, incluidas las 74 anteriores
  y nueve comprobaciones repetidas. Se verificó que todas las omisiones de la
  primera ejecución están cubiertas en esta segunda ejecución; cero fallos.
- Se reprodujo la comparación anterior en PostgreSQL: SQLSTATE 42883.
- 33 pantallas de la fixture respondieron 200. Dieciocho comprobaciones DOM
  verificaron la matriz de permisos, dependencias, búsqueda y límites de perfiles.
- Pruebas Node de navegación aprobadas y sintaxis del nuevo JavaScript válida.
- Pendientes: 561 combinaciones visuales en Actions y comprobación autenticada
  de la nueva versión en Render. No se tocaron datos ni permisos de producción.
