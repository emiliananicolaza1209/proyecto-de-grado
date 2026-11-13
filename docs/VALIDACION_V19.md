# Validación de la entrega integrada V19

## Código revisado

Finanzas V18.3.1 + rama de Andrés `ia-analitica-contable` en
`348a073bd763f2cbb7fdace516798e89690f41fb`.
Base común real verificada: `cd7fe8da08bc06b04dc184421e89b7127af5dde6`.
Los archivos de aplicación, pruebas y migraciones de la referencia utilizada
coinciden con esa base; la integración se contrastó con el historial Git.

## Resultados ejecutados

| Verificación | Resultado |
| --- | --- |
| `python -m unittest discover -s tests -v` | 815 casos: 760 aprobados, 55 omitidos; sin fallos/errores. Duración local: 370,869 s. |
| Pruebas Node de navegación, formularios de pago y lateral | 5 aprobadas; sin fallos. |
| Sintaxis JavaScript de reportes, contabilidad y chat | Correcta. |
| Escenario integrado festivo POOL/crédito/proveedores/sueldos/PD/servicio | Tres variantes aprobadas en SQLite temporal; mismas cifras en Finanzas, chat y reporte. |
| Permisos y rutas combinadas | Matriz y accesos directos incluidos en la suite aprobada. |
| Generación contable XLSX/PDF y migración/reconciliación SQLite | Cubiertas por la suite aprobada. |

Se corrigieron incompatibilidades de la unión: formularios que ahora se abren
en una acción dedicada, nueva ubicación del resumen analítico, etiquetas
«Utilidad», selección de año sin script en línea y descarga que conserva
`private, no-store`. Las comprobaciones financieras y de permisos se conservan;
no se retiraron fallos de negocio para obtener un resultado aprobado.

## Lo que no demuestra esta ejecución

Las **55 pruebas omitidas requieren PostgreSQL real**. No se configuró una
conexión de ensayo en este entorno. Los contratos y DDL se probaron sin servidor,
pero eso no demuestra la actualización 1→2, transacciones o recorridos en una
PostgreSQL real. Tampoco se modificó la base del usuario.

No se pudo ejecutar un navegador gráfico en el entorno de revisión. Las rutas
y plantillas se ejercitaron con el cliente Flask y los scripts de navegación con
Node, pero falta la revisión visual en computador/celular. No se midió latencia
de Render ni de la conexión del usuario; no se promete una aceleración global.

La entrega no acredita prueba completa con datos reales, aprobación conjunta
de ambos autores, restauración PostgreSQL real ni despliegue público. Seguir
`PRUEBAS_INTEGRADAS_V19.md` y registrar esa evidencia antes de producción.

Los logs finales sin datos del negocio se incluyen en `evidencia` del paquete.
El instalador se verifica por separado sobre copias V18.2/V18.3/V18.3.1,
incluyendo repetición, reversión y rechazo de archivos con cambios desconocidos.


## Corrección del cierre de la conexión de la prueba de migración (13/11/2026)

Se identificó un fallo al limpiar `data.sqlite` en Windows: en
`DistributionTests.test_migration_preserves_existing_accounting_records`, leer
`row.id` después del commit reactiva la sesión. Descartar el motor con esa sesión
activa deja una conexión en el pool anterior, que el cierre del nuevo pool no
recupera. Se corrige llamando `db.session.remove()` antes de `db.engine.dispose()`
en esa prueba. No se omiten excepciones, no se añaden reintentos y no se cambian
los cálculos, las migraciones ni sus verificaciones de conservación de datos.

Una comprobación con conexiones SQLite reales retenidas reproduce una conexión
abierta antes del cambio y cero después. La nueva regresión
`test_migration_connections_v19.MigrationConnectionTests.test_migration_releases_every_real_connection`
comprueba el ciclo completo de esa prueba, manteniendo referencias a las
conexiones para que el recolector no oculte la fuga.

Verificación posterior: 10 pruebas dirigidas aprobadas (distribución/migración,
conexiones y recursos SQLite). En una copia V18.3 con solo la línea corregida:
227 casos, 190 aprobados y 37 PostgreSQL omitidos. La suite completa de 815 casos
de la tabla anterior corresponde al estado previo a esta corrección de pruebas;
no se presenta como una nueva ejecución integral posterior. No se dispuso de
Windows para validación nativa: repetir la prueba y la suite en el equipo donde
apareció WinError 32. PostgreSQL real sigue pendiente.

El instalador acepta tanto la prueba original V18.2/V18.3/V18.3.1 como su variante
con esa única línea corregida. El bundle Git incorpora la corrección y su
regresión. El registro detallado posterior se incluye en la evidencia del paquete.
