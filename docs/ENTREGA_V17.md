# V17: reportes, analítica, consultas y recuperación

## Implementación para validación

- `/reportes`: inventario actual con filtros y propiedad según permiso; ventas netas con periodo, vendedor, ubicación y anulaciones; compras/lotes; créditos; finanzas por rango; consignaciones contables y auditoría de gestión.
- `/reportes/exportar/<tipo>/xlsx` o `/csv`: mismos permisos y filtros, metadatos y advertencias. Excel incluye hoja de metadatos, filtros y protección de celdas de texto frente a fórmulas.
- `/analitica`: comparación con periodo anterior de igual duración, diferencia absoluta y porcentaje no calculable cuando el anterior es cero.
- Alertas automáticas al consultar: stock por mínimo del artículo, equipos disponibles con antigüedad configurable y créditos pendientes (no mora). Seguimiento Pendiente/En revisión/Cerrada con motivo, responsable y auditoría. Cerrar no elimina una condición que persiste.
- Agente consultivo basado en reglas con cuatro preguntas seleccionables: ventas, disponibilidad, resultado de jornadas y crédito pendiente. Usa servicios internos, sin proveedor externo ni SQL libre. No es chat generativo ni predicción.
- `/api/consultas/ventas`, `inventario`, `finanzas`, `creditos`: JSON autenticado con el mismo servicio. Detalle limitado a 100 filas, totales globales identificados. Disponible para integrar con un futuro cliente MCP.
- Consolidado adicional por rango: fondos propios como capital reservado y sueldos por nombre/jornada. No altera el catálogo original de historias.
- Respaldo CLI con base y facturas, huellas SHA256, verificación, restauración a entorno separado y auditoría; sin ruta pública para descargar datos sensibles.
- Encabezados de privacidad, protección contra incorporación en marcos y no caché de páginas privadas. INSTANCE_PATH configurable para soportes persistentes.

## Reglas conservadas

No se suman cobro, venta y recepción como tres ingresos. La utilidad de un crédito no se vuelve a generar con el desembolso. Las ventas anuladas se pueden listar pero no suman. Cierre usa snapshot; abierto solo si se solicita, marcado provisional. No se suman bases ni caja esperada como flujos del periodo. Jornadas faltantes se identifican; no se inventan ceros. Un periodo completo sin cierres útiles no certifica resultado financiero.

## Estado de los requisitos

Avanza la implementación de HU-FIN-004, HU-VEN-007, HU-REP-001 a 006, HU-DASH-001 y 002, HU-ANA-001 y 003, HU-IA-001 a 006, HU-TRI-001/002 y HU-AUD-002 a 004. Esto no convierte automáticamente todos sus criterios en completos. Cada fuente tiene límites explícitos:

| Bloque | Lo que aún falta para aceptar completamente |
|---|---|
| Reportes | Compras no reconstruye todos los artículos/pagos históricos; créditos muestra saldo actual de los originados en el rango; falta reporte formal de separados y conciliación de anulaciones históricas. |
| Analítica | Permanencia no equivale a rotación histórica completa. No hay predicción validada. El cierre global no se distribuye por vendedor/ubicación: el sistema rechaza ese filtro. |
| Alertas/agente | Detección al consultar, sin notificaciones externas ni tarea periódica instalada. El agente ofrece preguntas seleccionables; MCP y modelo generativo no se conectaron. |
| Contabilidad | Consignaciones por periodo, no clasificación fiscal integral ni declaración tributaria. El paquete completo para contador requiere validar compras, gastos y categorías. |
| Sueldos/adicional | Nombres no son identificadores estables. Pago de otra jornada no se aplica a deuda de un periodo previo. Originales necesita mapeo explícito de productos/categorías. |
| Respaldo | SQLite probado. PostgreSQL usa pg_dump/pg_restore: requiere herramientas compatibles y restauración real comprobada. No se instaló programación automática. Los soportes no se capturan atómicamente con la base: suspender cargas durante copia. |
| Otros parciales | Persisten reversión de lotes con dependencias, reembolsos de ventas/separados ya cobrados, compensaciones/disoluciones complejas, hora comercial independiente, fuente externa de IMEI y pruebas físicas de lector. Los bloqueos de integridad se mantienen. |
| Producción | Pendientes despliegue real, permisos aceptados por negocio, concurrencia/carga y prueba PostgreSQL de estos cambios. |

No se recalcula porcentaje de cumplimiento ni se declara terminado el proyecto con esta entrega.

## Aplicación local

Aplicar con el instalador del paquete, que verifica la base previa y conserva copia de los archivos reemplazados. No añade tablas ni modifica las 40 existentes; los estados/configuración de alertas y consultas auditadas usan registro_gestion.

Después de aplicar, desde la raíz del proyecto, con el servidor detenido:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*v17.py' -v
.\.venv\Scripts\python.exe run.py
```

Entrar con propietario. Revisar `/reportes` y `/analitica`. Las vendedoras solo acceden al reporte de inventario sin costos/propiedad; inventario ve costos según el permiso preexistente y no recibe participaciones. Socio mantiene su flujo restringido existente. Propietario/Administrador acceden a los reportes financieros nuevos, sujeto a validar la matriz de negocio.

## Copia y recuperación

No guardar respaldos en el repositorio. Crear el destino fuera del proyecto y conservarlo de forma privada:

```powershell
.\.venv\Scripts\python.exe -m flask --app run.py crear-respaldo --destino C:\RespaldosPrivados\cpstore_copia.zip
.\.venv\Scripts\python.exe -m flask --app run.py verificar-respaldo C:\RespaldosPrivados\cpstore_copia.zip
.\.venv\Scripts\python.exe -m flask --app run.py restaurar-respaldo C:\RespaldosPrivados\cpstore_copia.zip --destino-aislado C:\RecuperacionPrueba\cpstore
```

Destino debe ser nuevo. En PostgreSQL, definir CPSTORE_RESTORE_URL privadamente para una base distinta, vacía y con nombre terminado en `_restore`; nunca usar DATABASE_URL como destino de recuperación. El comando pide confirmación y no sustituye la base activa. Validar registros y soportes antes de considerar una conmutación operativa. pg_dump y pg_restore deben estar en PATH y ser compatibles con la versión del servidor.

Para automatizar: configurar posteriormente una tarea del sistema que ejecute crear-respaldo con destino único por fecha, revisar su salida y verificar restauraciones periódicamente; no hay automatización activa por instalar este paquete.

## Preparación del alojamiento

Build: `pip install -r requirements.txt`. Inicio Linux: `gunicorn run:app --bind 0.0.0.0:$PORT --workers 1 --threads 4`. Variables privadas: DATABASE_URL PostgreSQL, SECRET_KEY estable y SESSION_COOKIE_SECURE=true bajo HTTPS. INSTANCE_PATH debe apuntar a un directorio persistente del alojamiento para facturas; un disco efímero pierde soportes. No inicializar ni borrar la base desde cada arranque. Revisar vigencia del plan de prueba y configurar respaldo externo. No se contrataron ni desplegaron servicios en esta entrega.

## Verificación realizada

140 pruebas descubiertas: 136 ejecutadas y aprobadas, 4 PostgreSQL omitidas por no tener CPSTORE_TEST_PG_URL. Incluye 14 nuevas pruebas (12 reportes/seguridad/alertas/agente y 2 recuperación/integridad). Prueba de renderizado HTML mediante cliente Flask aprobada. Navegador visual no disponible por restricciones del entorno; revisar diseño en computador y móvil. Los cuatro tests PostgreSQL que Emily ejecutó previamente corresponden a la base anterior, no certifican estos cambios.
