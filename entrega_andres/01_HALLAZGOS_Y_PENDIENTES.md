# Hallazgos y pendientes reales

## Evidencia disponible
- Reportado por Emily: conexión PostgreSQL, 40 tablas de aplicación, persistencia tras reinicio, venta y correcciones de consignación; cuatro pruebas de integración terminaron en OK.
- Confirmado por lectura del ZIP: 40 modelos con tabla; inicialización PostgreSQL con `cp_schema_revision` versión 1; cálculos diarios, estados de crédito y control de acceso en servidor.
- No ejecutado aquí: conexión a Render, pruebas PostgreSQL actuales, respaldo/restauración, publicación Git, despliegue ni pruebas del chatbot.

## Bloques y decisiones
| Prioridad | Hallazgo en el código | Trabajo necesario | Responsable |
|---|---|---|---|
| Antes de integrar | La fuente es el ZIP, sin commit | Comparar archivos, revisar cambios locales y fijar commit compartido | Emily |
| Antes de integrar | `comprobar-db` verifica conexión y presencia de tablas | Ejecutar verificador adjunto; contrastar columnas, claves y restricciones | Emily ejecuta; Andrés revisa |
| Antes de nuevas tablas | Versión inicial 1 y `create_all`; no migraciones incrementales PostgreSQL comprobadas | Elegir scripts versionados o Alembic; probar actualización en copia, respaldar y registrar revisión | Andrés con aprobación técnica conjunta |
| Chatbot | No se encontró módulo MCP/chat en esta base | Implementar cuatro adaptadores con autorización por consulta y campo | Andrés |
| Chatbot | `auth.can()` da costos al rol Inventario y permisos amplios al Administrador | Validar matriz vigente con Emily; no trasladar al bot reglas antiguas por suposición | Ambos |
| Cierre | Existen cierre y snapshot | Confirmar guardado y consulta tras reiniciar; comparar abierto/cerrado | Emily |
| Sueldo por persona | Personal dentro de JSON; pagos por nombre y jornada | Límite inicial: misma jornada y nombre validado. Para pagos de otros periodos: identificador estable y aplicación a obligaciones | Emily define; Andrés apoya consulta |
| Vencimientos | `creditos_venta` no tiene columna de vencimiento | Mostrar pendiente, no vencido. Definir fecha esperada antes de generar mora | Ambos |
| Originales | Hay catálogos, categorías y fondos; no una clasificación inequívoca de “originales” identificada | Emily define el concepto y el mapeo por ID; no usar coincidencias de texto | Emily |
| Analítica | Fechas comerciales mayormente String y auditorías UTC | Validar formato, distinguir fecha comercial y registro; usar Bogotá en presentación | Andrés |
| Operación real | Recuperación y persistencia de adjuntos no acreditadas | Probar respaldo, restauración, reinicio y almacenamiento de soportes; revisar vencimiento del servicio | Ambos |

## Aclaración de sueldos
`finanzas_service.add_operation` sí limita pagos de sueldo por persona (campo `seller`) y por jornada, comparándolos con `config.staff[].salary`. `report` calcula el pendiente total del día. Lo que falta no es todo el flujo de sueldo: falta una identidad estable y una relación explícita para saldar obligaciones de una jornada desde pagos de otra. No prometer todavía “saldo de sueldo de octubre incluyendo pagos de noviembre”.

## Aclaración de versionado
`inicializar-postgres` conserva un esquema ya inicializado; no transforma sus columnas al modificar modelos. El directorio `migrations` contiene lógica heredada vinculada a SQLite. Una nueva columna requiere una migración PostgreSQL explícita; no modificar la versión 1 a mano para simular una migración.
