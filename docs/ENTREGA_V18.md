# CP Store V18 — interfaz y preparación de despliegue
Fecha: 11 de noviembre de 2026. Entrega prevista: 12 de noviembre.

## Implementación
- Menú global lateral en escritorio. En móvil se abre como panel lateral con fondo, cierre, Escape y control del foco; no se transforma en navegación horizontal arriba.
- Apariencia azul/blanco/gris, formularios consistentes y tablas de consulta apiladas en móvil. Las matrices complejas se desplazan dentro de su contenedor.
- Estados con etiquetas de texto y color, sin iconos. Se conservan iconos en navegación y temas que requieren atención.
- Regreso contextual con destino local validado. Conserva filtros de URL, filtros locales y desplazamiento en la misma pestaña. Los formularios POST no se reenvían al regresar. No se guardan contraseñas ni datos de formularios comerciales en el navegador.
- Acciones comerciales mediante selector visible; acceso directo a vender o registrar abono desde el listado. El detalle de un movimiento de Finanzas se consulta en una sola vista con regreso al mismo renglón.
- Dashboard de lectura conectado a las tablas actuales; no contiene datos de ejemplo. El selector admite 7/15/30 días y fechas personalizadas históricas de hasta 366 días.
- Errores 400/403/404/413/500 legibles con regreso, acceso de usuario renovado y aviso de cambios sin guardar.

## Definiciones del dashboard
Todos los importes internos permanecen en centavos COP.

| Elemento | Fuente y significado |
| --- | --- |
| Ventas netas del período | `finance_operation` de tipo Venta, no anuladas, por `finance_day.date`. No se multiplican por costos o pagos. |
| Cobros registrados | Medios cobrados de ventas financieras, cobros manuales vigentes y desembolsos efectivos. Incluye recargo de datáfono; no incluye retomas ni créditos por desembolsar. |
| Sin duplicar | Un Cobro generado por Finanzas representa el mismo pago; no se vuelve a sumar. Aplicaciones de un desembolso se excluyen porque el lote de desembolso se cuenta una vez. Las recepciones de administración nunca son un nuevo cobro. |
| Equipos disponibles / composición | Equipos no archivados, situación actual; los vendidos se muestran como registros, no como stock físico disponible. No se pretende reconstruir inventario histórico. |
| Saldo actual de ventas | Precio menos cobros vigentes en vendidos y garantías de ventas; excluye importes por verificar y separados. No equivale a mora ni a la diferencia ventas-cobros del período. |
| Modelos | Equipos vendidos por fecha comercial, Top 5. No equivale a todas las ventas complementarias. |
| Ventas históricas sin incorporar | Se advierte que el total financiero es parcial. No se crean operaciones automáticamente desde el dashboard. |

Las cifras monetarias agregadas solo se entregan al Propietario y Administrador conforme a los permisos actuales. Los perfiles operativos reciben indicadores de equipos; los importes agregados no se esconden únicamente con CSS, se excluyen de la respuesta del servidor.

## Base de datos y trabajo de Andrés
No hay cambios al esquema (40 tablas de aplicación / 315 columnas de modelos), ni reinicialización, limpieza o migración de datos. Se agrega un servicio de lectura para el dashboard de Emily. Los servicios y contratos de analítica/chatbot existentes siguen disponibles para el trabajo de Andrés.
El comparador de código de `entrega_andres` conserva la referencia de la entrega anterior: sus hashes de código cambiarán con V18; el contrato de la estructura de PostgreSQL continúa vigente.

## Seguridad de despliegue
- El entorno `production` (o Render) requiere PostgreSQL y una clave privada configurada de al menos 32 caracteres. Falla si se olvida alguno: no crea SQLite por accidente.
- Autenticación obligatoria, DEBUG desactivado, cookies Secure/HttpOnly/SameSite y duración máxima de sesión configurada en 8 horas.
- Host permitido explícito o el dominio que Render proporciona. ProxyFix solo cuando se habilita detrás del proxy; no confía en X-Forwarded-Host.
- CSRF conservado, política CSP sin JavaScript inline ejecutable, anti-incrustación, HSTS y permisos de cámara solo para el propio sitio.
- `/healthz` comprueba una lectura de la base de datos y devuelve únicamente un estado; no exige login ni genera cookie.
- Gunicorn: un proceso, cuatro hilos, serialización transaccional PostgreSQL existente. No se arranca el servidor de desarrollo en Render.

Estos controles son una base para entregar el prototipo. No constituyen una auditoría o certificación de seguridad de producción.

## Adjuntos y servicio gratuito
La propuesta `render.yaml` utiliza un servicio web Free para las pruebas de entrega. En ese plan el disco es efímero: se deshabilita explícitamente la carga de nuevas facturas para no afirmar que un archivo está guardado y perderlo en un reinicio. Las compras y sus líneas continúan funcionando.
Para probar adjuntos persistentes: servicio con disco real montado en `/var/data`, `INSTANCE_PATH=/var/data/cpstore`, `PERSISTENT_INSTANCE=true` y `UPLOADS_ENABLED=true`. Esto requiere elegir un plan compatible; no se contrata desde el paquete.
La base PostgreSQL existente no se reemplaza ni se recrea. La modalidad gratuita tiene vencimiento: verificar su fecha en Render antes de usar datos reales.

## Pruebas
- Python 3.13.5 local: 169 pruebas descubiertas, 156 aprobadas y 13 optativas de PostgreSQL omitidas por falta de conexión privada.
- Dos comprobaciones Node del destino local de regreso, filtros, contexto vencido y regreso tras formularios.
- Las tres expectativas visuales antiguas se actualizan por el nuevo título/clases de estado. Se mantienen las comprobaciones de flujos y se conserva la lista de IMEI con devoluciones vencidas.
- La configuración de CI ejecuta SQLite y PostgreSQL 17 en un contenedor temporal, además de una prueba de navegador contra `scripts/preview_ui.py`. El servidor UI está ligado a loopback, crea una base temporal y nunca es el arranque de Render.
- No se ejecutó aquí un navegador para certificar tamaños, ni se ejecutaron aquí las pruebas de PostgreSQL real o las de la URL pública. Deben aprobarse en CI y en el servicio desplegado. No presentar las pruebas omitidas como aprobadas.

## Reglas pendientes de confirmar
La devolución con dinero recibido requiere autorización del propietario y revisión física antes de disponibilidad. Falta precisar el importe que se lleva a Gastos de servicio frente al reembolso del capital, y el tratamiento de créditos desembolsados y comisiones ya pagadas. V18 no habilita una devolución monetaria inventando estas reglas; conserva los bloqueos de conciliación existentes.
