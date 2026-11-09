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

## Intentos de acceso
- Límite por usuario y red: 5 fallos en 5 minutos. Límite por red: 20 fallos en 5 minutos con cualquier usuario
  (frena probar una clave contra muchos usuarios). Un acceso correcto reinicia solo el contador de ese usuario.
- Cada fallo queda en la auditoría (`registro_gestion`, entidad `acceso`) con el usuario escrito, la IP y el motivo
  (usuario inexistente, inactivo o contraseña incorrecta). Nunca se guarda la contraseña. El bloqueo queda registrado
  una sola vez por ventana, y los intentos bloqueados no escriben, para que nadie pueda inundar la tabla.
- **Limitación conocida (en memoria):** los contadores viven en la memoria del proceso. Se pierden al reiniciar el
  servidor y no se comparten entre procesos. Detrás de un proxy, `remote_addr` es la IP del proxy: configurar
  `ProxyFix` o equivalente al desplegar. Los registros de auditoría sí son persistentes.

## Contraseñas
- Mínimo 12 y máximo 128 caracteres. Se rechazan: claves de la lista de las más usadas, claves armadas solo con
  palabras muy comunes (aunque lleven números o símbolos, p. ej. `Password-2026!`), secuencias y repeticiones
  (`abcdefghijkl`, `123456789012`, `abababababab`) y claves que contienen el usuario o el nombre de la persona.
- Aplica al crear o editar usuarios y a `flask crear-propietario`. Se guardan solo con hash.
- Limitación: no se consulta una lista pública de claves filtradas (sería una dependencia nueva) y los usuarios no
  pueden cambiar su propia clave: la fija el Propietario.

## Pendientes de seguridad (anotados, sin tocar)
Estos puntos salieron del diagnóstico de usuarios y se dejan para una etapa posterior por decisión del equipo.
7. **Lectura de créditos para la Vendedora:** `/finanzas/creditos` (créditos, aliados y desembolsos) es visible para el
   perfil Vendedora aunque sus escrituras estén bloqueadas. Decidir si la lectura debe cerrarse.
8. **Errores 500 en vez de 400/404:** `/inventario/facturas/<id>` con un id inexistente, `/finanzas/exportar` sin fecha
   y `/gestion/historial?id=abc` terminan en error interno. No filtran datos, pero conviene responder 400 o 404.
9. **Enumeración de usuarios por tiempo de respuesta:** si el usuario no existe no se calcula el hash, así que la
   respuesta es más rápida que con un usuario existente. Mitigación posible: calcular siempre un hash ficticio.

## Cobertura automática
`tests/test_matriz_permisos.py` fija qué roles pueden usar cada ruta y cada acción de escritura. Falla si una ruta
cambia de permisos o si aparece una ruta nueva sin clasificar; al añadir una ruta hay que declararla allí.
