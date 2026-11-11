# Acceso, versión compartida y aceptación

## Acceso de desarrollo y acceso del chatbot
Separar la credencial de administración/migraciones de la credencial usada por consultas. Para el chatbot, limitar a tablas/vistas y columnas necesarias; no conceder lectura general de usuarios ni de todo el esquema. El servidor sigue comprobando usuario, rol y alcance: un rol SQL de lectura no implementa por sí solo los permisos comerciales.

No se incluye GRANT masivo porque no se ha inspeccionado qué roles existen en Render ni sus privilegios heredados. Revisar privilegios efectivos, PUBLIC, propiedad y membresías antes de afirmar que una cuenta solo puede leer. Probar consultas permitidas y rechazos en el entorno de desarrollo. La herramienta nunca recibe credenciales ni el usuario decide su rol mediante el prompt.

Para el computador de Andrés: configuración privada de desarrollo con URL externa y TLS. Para una aplicación Render en la misma región: URL interna. No comprar una IP ni exponer el PostgreSQL del computador para este flujo. Validar accesos de red en el panel de Render.

## Matriz pendiente de aprobación
El código actual `app/auth.py` contiene Propietario, Administrador, Vendedora, Inventario y Socio. El Administrador tiene permisos amplios y el rol Inventario incluye costos. No se debe asumir que estas autorizaciones coinciden con todas las reglas históricas del negocio.

Primera versión propuesta: chatbot habilitado al Propietario. Para ampliar: decidir por herramienta y campo qué ve cada perfil; restringir Socio a su participación e Inventario/Vendedora a lo autorizado. Probar enlace directo y llamada de herramienta, no solo visibilidad del menú. El filtro se aplica antes de enviar datos al modelo.

## Publicar el código revisado
Ejecutar primero las comprobaciones del LEEME. No usar git add . a ciegas con todos los cambios acumulados. En VS Code, revisar diferencias y preparar solo archivos de código/documentación deseados.

Si `.env` está rastreado, añadir a `.gitignore` de la raíz (no al de `.venv`):
```gitignore
.env
.env.*
!.env.example
```
Después, solo si está rastreado:
```powershell
git rm --cached -- .env
```
Esto conserva el archivo local; no lo elimina de commits anteriores. Si alguna credencial real se publicó, cambiarla en su servicio y actualizar la configuración. `.env.example` debe tener campos de ejemplo vacíos, nunca credenciales reales.

Tras revisar y preparar los archivos:
```powershell
git diff --cached --stat
git diff --cached --name-only
git commit -m "Prepara PostgreSQL y documenta integracion de consultas"
git push -u origin migracion/postgresql
git rev-parse HEAD
```
Usar esa rama únicamente si `git branch --show-current` la confirma. Guardar el SHA que devuelve el último comando. El commit y push los ejecuta Emily en su proyecto actualizado; no se han ejecutado desde este paquete.

Andrés descarga la rama, crea su rama de trabajo desde ese commit e instala las dependencias del proyecto. Cada integrante conserva su propio `.env`; no se sube. Para datos sintéticos locales puede usar su PostgreSQL de desarrollo; no compartir indiscriminadamente la base de operación real.

## Cambios de esquema
Proponer una migración numerada con motivo, cambios, validaciones y recuperación; probarla sobre copia. Guardar versión y revisar antes de aplicarla al entorno compartido. El `.gitignore` de la preparación puede ignorar `*.sql`: si se adopta SQL versionado, permitir específicamente los scripts de migración, manteniendo ignorados los dumps y secretos.

## Pruebas existentes y nuevas
Las cuatro pruebas PostgreSQL existentes fueron reportadas en OK por Emily; no se repitieron aquí. `tests/test_postgres_integration.py` usa un esquema temporal con CPSTORE_TEST_PG_URL y borra solo ese esquema; ejecutarlo solo en desarrollo, con permisos y datos de prueba. No es un procedimiento de backup ni una prueba del chatbot.

Casos del chatbot a implementar con `tecnico/casos_aceptacion.json`: comparar las cifras estructuradas del servicio con la respuesta; validar mismo rango, anulado, sin datos, acceso rechazado, crédito parcial, no duplicación y datos insuficientes. Cada prueba debe registrar commit, entorno, fecha, ejecutor y resultado.

## Antes de operar en la empresa
- Cerrar una jornada y verificar su snapshot tras reiniciar; ejecutar flujo venta/cobro/recepción/cierre con dos usuarios sin doble cobro ni pérdida de actualización.
- Guardar respaldo PostgreSQL y soportes; restaurar en un entorno diferente y comprobar registros, totales y archivos. Un archivo de respaldo sin restauración probada no acredita recuperación.
- Revisar fecha exacta de expiración del plan gratuito en Render; pasar al plan apropiado antes del uso operativo o vencimiento. Este documento no contrata servicios ni fija precios.
- HTTPS, sin debug, secretos en configuración, sesiones y CSRF, límites de intentos/peticiones y logs sin secretos. Verificar almacenamiento persistente de adjuntos.
- No mantener la llamada al modelo dentro de una transacción de escritura: la base actual serializa escrituras web con bloqueo transaccional global y debe comprobarse su comportamiento concurrente.

Referencias técnicas para implementación: https://render.com/docs/postgresql-creating-connecting ; https://www.postgresql.org/docs/current/sql-grant.html . Confirmar configuración y capacidades vigentes en el entorno elegido.
