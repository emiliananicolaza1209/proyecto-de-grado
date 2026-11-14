# Revisión V19.2.1 sobre 8a17bad

La ejecución 43508658426 de GitHub aprobó el trabajo `funcionales`, incluido
PostgreSQL. La revisión visual cubrió las 561 combinaciones previstas y detectó
tres desbordamientos reales en Acceso con WebKit: anchos 375, 390 y 430 px.
También falló una captura contable por superar el límite de 32767 píxeles del
motor; la página ya había superado la comprobación de ancho.

## Correcciones

- Acceso: el ancho de la tarjeta y sus campos incluye ahora rellenos y bordes.
  Se elimina el margen implícito del cuerpo y se limita la pista grid al ancho
  disponible. Se conserva el foco visible; no se oculta el desbordamiento con CSS.
- Capturas: se registra el área visible para evitar el límite de páginas largas.
  La comprobación sigue midiendo todo `document.documentElement.scrollWidth`.
  Cada combinación registra un solo resultado. Las pruebas usan idioma es-CO
  y zona horaria America/Bogota.
- Permisos: la autorización de escrituras lee `request.form`, igual que los
  controladores. `request.values` priorizaba parámetros de URL y permitía que una
  acción autorizada en la URL ocultara otra acción enviada en el formulario.
  La regresión reprodujo una respuesta 302 indebida al cambiar reglas con un
  usuario limitado a compra POOL; después de corregir, responde 403 y conserva
  la configuración. Una venta autorizada sigue funcionando aunque la URL contenga
  parámetros de otra acción.

La regresión pasa en SQLite y PostgreSQL 17.11 de ensayo. No se modifican modelos,
cálculos financieros ni revisiones de esquema. Sigue pendiente la actualización
a PostgreSQL revisión 3 requerida por V19.2, si aún no se ha realizado.

## Publicación

Aplicar solamente este incremento sobre el commit `8a17bad`, subirlo y esperar
otra ejecución de `funcionales` y `responsive`. Esta revisión visual debe
repetirse para comprobar la corrección de WebKit. Después actualizar el esquema
si falta y desplegar el último commit en el servicio existente de Render.

No se ha presentado la emulación como una prueba de dispositivos físicos.
