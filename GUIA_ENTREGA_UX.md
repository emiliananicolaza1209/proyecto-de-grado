# CP Store · actualización de experiencia de uso

Esta entrega contiene el código completo de los módulos presentes en esta copia del proyecto. No incluye la base de datos `instance/`, credenciales, entornos virtuales ni archivos de respaldo.

## Qué se implementó

- Inicio operativo con existencias, pasamano, devoluciones vencidas, ventas con saldo, accesos y equipos recientes; consultas paginadas a seis elementos para las listas.
- Barra superior con búsqueda global de equipos (IMEI o referencia), atajo Ctrl/Cmd+K y navegación móvil plegable.
- Ventas con indicadores de la búsqueda y filtro instantáneo de la tabla; los filtros originales del servidor siguen disponibles.
- Inventario con indicadores destacados y detalles del POOL plegables; conserva el listado, costos, lotes y las acciones existentes.
- Finanzas con secuencia orientativa por pestaña, avisos agrupados y comparación de hasta 14 jornadas cerradas basada en los snapshots originales.
- Información contable con búsqueda instantánea entre personas mostradas.
- Acciones comerciales desplegables como acordeón y protección del lado del cliente contra el doble clic en formularios; la validación y transacciones del servidor siguen vigentes.
- Estilos compartidos, responsive y estados de foco para teclado.

## Aplicación en Windows

1. Respalda `instance/` y tus cambios locales. Comprueba que trabajas en la rama `desarrollo`.
2. Extrae este ZIP en otra carpeta y copia las carpetas de código (`app/`, `migrations/`, `tests/`) y archivos raíz necesarios sobre tu proyecto. **No borres ni sustituyas `instance/`.**
3. Ejecuta `python -m unittest discover -s tests -p "test_*.py" -q` y después `python run.py`.
4. Revisa en escritorio y móvil Inicio, Inventario, Ventas, Finanzas e Información contable con datos de prueba antes de registrar operaciones reales.

## Próximas mejoras importantes

- Implementar autenticación y autorizaciones reales en servidor: vendedoras con panel operativo y operaciones asignadas; Sandra con caja y supervisión; Jonatan con analítica administrativa y datos sensibles. Actualmente el prototipo local **no restringe** el acceso a Finanzas ni a costos de Inventario. Una pantalla distinta no equivale a seguridad.
- Separar el panel administrativo de Finanzas con filtros temporales y vínculos desde cada indicador a sus movimientos; documentar definición de venta, utilidad, recaudo y monto bancario bruto/neto para evitar discrepancias.
- Optimizar consultas de listas grandes con paginación en servidor y mejorar exportaciones según roles.
- Definir migraciones versionadas para PostgreSQL, respaldo/restauración y pruebas de concurrencia de ventas, cobros y caja antes del uso multiusuario.
- Pruebas de accesibilidad y visuales en navegadores de escritorio/móvil; revisión con personal real en escenarios de pasamano, lote, cobro y cierre.
- Diseño de analítica y agente (módulo 05) y de usuarios (módulo 07): en este código aún son secciones pendientes, no funcionalidades terminadas.

Validación en este entorno: 69 pruebas automatizadas y sintaxis de los scripts JavaScript correctas. No se pudo ejecutar la inspección visual automatizada porque el navegador de Playwright no estaba instalado.
