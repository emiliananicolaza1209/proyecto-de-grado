# Seguridad de CP Store: decisiones, limitaciones y pendientes

Documento vivo. Lo que sigue describe lo que la aplicación hace hoy y lo que **no** hace.

## Sesión
- Cookie de sesión: `HttpOnly`, `SameSite=Lax`. `Secure` se activa con la variable de entorno
  `SESSION_COOKIE_SECURE=1` (o la clave de configuración del mismo nombre); debe activarse al desplegar tras HTTPS.
- Expiración por inactividad: `SESSION_IDLE_MINUTES` (30 por defecto). Cada petición autenticada renueva el reloj,
  salvo los archivos estáticos. Al vencer se vuelve a la pantalla de acceso con un aviso.
- **Limitación conocida (sin invalidación en servidor):** la sesión es una cookie firmada sin estado en el servidor.
  - "Cerrar sesión" borra la cookie del navegador, pero una copia de esa cookie sigue siendo válida hasta que venza
    por inactividad.
  - Editar o desactivar a un usuario sí invalida sus sesiones de inmediato (`session_version`).
  - Resolverlo exigiría una tabla de sesiones (cambio de esquema), que por ahora queda fuera de alcance.
