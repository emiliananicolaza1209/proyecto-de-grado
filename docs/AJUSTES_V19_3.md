# CP Store V19.3: interfaz de consultas y fechas del chat

Base publicada: `86f43bb1a178b9afcb0f1349535be5eed93bf18c`, rama
`integracion/cp-store-v19`. Fecha: 13/11/2026.

## Información contable

La pantalla conserva sus servicios, formularios, validaciones y exportaciones.
Se organiza en tres tareas: Consolidado, Personas y bancos, y Consignaciones.
Las pestañas admiten teclado, enlaces directos y navegación Atrás. Sin JavaScript
se conservan las tres secciones. Al registrar o corregir una consignación, el
retorno abre su sección. Los errores de alta de personas abren Personas y bancos.

El consolidado muestra seis indicadores, fechas visibles y una sola acción para
descargar Excel, PDF o CSV. El detalle, los formularios complementarios y los
historiales se despliegan cuando se necesitan. La corrección de categoría pide
un motivo explícito. Los importes de pantalla usan el formato COP del aplicativo;
las pruebas siguen contrastando sus valores con Excel, PDF y CSV. Los enlaces de
registro y exportación respetan las acciones habilitadas del usuario; se conserva
la comprobación de permisos y CSRF del servidor.

## Analítica, reportes y chat

Analítica separa «Ventas del periodo» de «Estado actual del negocio». El selector
conserva su alcance: cambia ventas; el resultado es el de hoy y el inventario y los
créditos siguen siendo actuales. Las tarjetas y los reportes detallados utilizan
el mismo estilo, con la fuente disponible al desplegarla.

El chat incluye selector de fechas, ayuda breve y acceso a la última jornada
cerrada disponible. Muestra el periodo consultado incluso si no hay datos. Una
fecha escrita en la pregunta tiene prioridad sobre la selección del formulario;
sin fecha ni selección, sigue consultando hoy y lo explica.

Se reprodujo que `ventas del 12/10/2026` y `ventas del 12-10-2026` no reconocían el
periodo: devolvían `None` y la consulta usaba hoy. Ahora reconoce día/mes/año,
día-mes-año, fechas ISO, rangos y extremos abreviados como «del 1 al 12/10/2026».
Una fecha numérica inválida se explica; no se sustituye silenciosamente por hoy.
«Ventas del último cierre» se interpreta como ventas, en vez de cambiar a utilidad
por la palabra cierre. «Resultado del último cierre» conserva su intención.

No se recibió el texto exacto de la pregunta original del usuario. Esta entrega
corrige las limitaciones reproducidas y permite elegir explícitamente el cierre;
no afirma haber diagnosticado otras frases o datos no observados.

## Reglas conservadas

No agrega modelos ni migraciones. PostgreSQL sigue en revisión 3 y conserva las
44 tablas del aplicativo. No se modifican los servicios de ventas, créditos,
POOL, comisiones, personal o cierres. Los importes históricos de chat y reportes
siguen leyendo el snapshot del cierre; no se reconstruye ni se reabre la jornada.
El registro contable complementario mantiene su separación de caja y utilidad.

## Validación

- Suite completa: 887 ejecuciones, 804 aprobadas y 83 que requieren PostgreSQL.
- PostgreSQL 17.11 temporal: 92 aprobadas. Se comprobaron por identificador las
  83 omitidas de la ejecución local; todas están cubiertas en este recorrido.
  Contando los identificadores distintos de ambas ejecuciones: 885 casos aprobados
  (hay dos ejecuciones repetidas en la suite existente).
- 20 comprobaciones DOM de pestañas, teclado, enlaces, formulario de fechas,
  prioridad de periodos, CSRF, cifras del cierre y respuesta tratada como texto.
- Tres pruebas Node de navegación existentes y revisión de sintaxis aprobadas.
- El caso de regresión crea una jornada ficticia con 12 ventas y 853.000 COP,
  la cierra y cambia una operación después. El chat conserva las cifras guardadas.
- Reportes y exportaciones conservan sus comprobaciones de coincidencia numérica;
  solo se actualiza la expectativa del formato COP y la ubicación del panel HTML.

Pendiente tras subir este incremento: GitHub Actions ejecutará el nuevo recorrido
real de navegador y la matriz de 612 combinaciones (36 pantallas/secciones,
17 combinaciones de tamaño y motor, Chromium y WebKit). Esa revisión todavía no
se ejecutó para este código. El navegador local no puede iniciarse por una
restricción de sockets Unix; las pruebas DOM no sustituyen el cálculo de layout.
La emulación de tamaños tampoco equivale a dispositivos físicos.

La base de `scripts/preview_ui.py` es desechable, de loopback, con cabecera de
ensayo obligatoria. Las pruebas de este incremento nunca usan la base de Render.
