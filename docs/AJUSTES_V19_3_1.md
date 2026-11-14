# CP Store V19.3.1: revisión de CI y presentación

Base: `4577d276f98248163cf36d1b1fd83b6b05df0af0`, ya subida a
`integracion/cp-store-v19`. Fecha de preparación: 13/11/2026, hora Colombia.

## Lo observado en la revisión

La ejecución GitHub 43538347537 aprobó Responsive: 612 combinaciones, sin
fallos de ancho o JavaScript, en Chromium y WebKit. Se descargó el artefacto
público y se comprobó su SHA-256 contra la metadata de GitHub antes de revisarlo.

La inspección visual de las capturas mostró que la ayuda y el acceso al último
cierre del chat quedaban detrás del menú de escritorio. El elemento aside heredaba
la regla global del menú (posición fija, ancho y fondo), aunque no producía un
desbordamiento. Se sustituye por un contenedor con role=complementary que ocupa
su columna normal. El recorrido de navegador ahora exige visibilidad, límites
del contenedor y ausencia de superposición, en escritorio y móvil.

Las pestañas contables conservan la entrada del historial y su estado con
replaceState. Cambiar pestañas no añade pasos al botón Volver. Se añade el
recorrido Ventas → Información contable → pestaña → Volver a Ventas, con esperas
registradas antes de cada navegación. El recurso JavaScript usa versión 21.1.

## Fecha usada por las pruebas

El trabajo funcional de esa ejecución falló durante Python y no llegó al paso
de navegador. El acceso conectado no permitió descargar el log completo. Se
reprodujo una causa concreta en las 12 pruebas de test_reportes_v17.py: la fixture
usaba date.today() del servidor. A las 01:04 UTC del 14 de noviembre el negocio en
Colombia aún estaba en 13 de noviembre; preparar la jornada del 14 daba
«No se puede registrar una jornada futura».

La fixture ahora usa finance.today(), la misma fecha colombiana de la aplicación.
Las12 pruebas fallaban con TZ=UTC y aprobaron con la corrección tanto en UTC como
en la zona local, con Python 3.13. No cambia la regla del negocio ni la validación
de jornadas futuras. El workflow conserva el resultado del proceso Python y
guarda su log de ensayo como artefacto para diagnosticar cualquier otro fallo.

## Validación y publicación

Se ejecuta la suite completa con Python 3.13, TZ=UTC y PostgreSQL 17 temporal en
un único proceso, igual que el descubrimiento del workflow. VALIDACION.json
recoge el resultado final: 887 pruebas aprobadas, sin fallos, errores ni omitidas. También se comprobaron las 21 pruebas
de pantalla de Chat, las 12 de Reportes en ambas zonas, la navegación y los
controles DOM. El cambio de estructura del chat se contrastó con la regla global
que causaba la posición fija anterior.

El nuevo código de navegador debe ejecutar nuevamente funcionales y responsive
en GitHub antes del despliegue. Las capturas y el artefacto verde de 4577d27
corresponden a la versión anterior, no a esta revisión. La emulación no sustituye
la revisión en dispositivos físicos.

No hay migraciones ni cambios de modelos, datos comerciales o fórmulas de venta,
POOL, crédito, comisiones y cierre. Se utiliza la base ya actualizada a revisión 3.
