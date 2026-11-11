# Validación de esta entrega

- Se analizaron declaraciones Python sin iniciar Flask ni ejecutar inicializadores.
- Inventario: 40 tablas de modelos y 315 columnas. La tabla técnica cp_schema_revision se crea por separado.
- Las referencias a tablas/columnas declaradas en claves foráneas se comprobaron internamente.
- JSON de esquema, contratos, casos y versión: formato válido.
- Script: compilación Python correcta; comparación con la base idéntica; detección de archivos ausentes; detección de tipos y nulabilidad distintos; detección de tabla/columnas ausentes.
- PDF: seis páginas renderizadas e inspeccionadas visualmente.
- No se ejecutó conexión a Render ni se validó psycopg contra un servidor real en esta entrega. Esa comprobación corresponde al comando del LEEME en el entorno del proyecto.
- No se han implementado ni ejecutado las cuatro consultas de chatbot. Los 16 escenarios son especificaciones de aceptación; las pruebas existentes se identifican por su archivo y método.
- comparacion_base_revisada.json compara el ZIP revisado contra sí mismo como control del verificador. No representa el proyecto actual de Emily.
