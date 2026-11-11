# CP Store | Entrega de PostgreSQL, chatbot y analítica

Preparado el 9 de noviembre de 2026 para Emily y Andrés. Versión 1.0.

## Qué está entregado
Una base documental y técnica para que Andrés empiece a implementar. Incluye un inventario de las **40 tablas ORM**, sus columnas y relaciones; reglas vinculadas al código; cuatro contratos de consulta; casos de aceptación y una comprobación de estructura de solo lectura.

**No es una nueva versión del aplicativo ni un chatbot ya implementado.** No incluye credenciales, datos de usuarios, un respaldo de la base ni cambios ejecutados en Render. La fuente revisada es el ZIP de preparación de PostgreSQL, no el estado actual del computador ni un commit descargado de GitHub. La comparación local permite detectar diferencias.

## Orden de lectura
1. `CP_Store_Entrega_PostgreSQL_Chatbot_Analitica.pdf`: resumen para coordinar el trabajo.
2. `01_HALLAZGOS_Y_PENDIENTES.md`: qué existe y qué falta comprobar.
3. `02_REGLAS_Y_FUENTES.md`: significado de cifras y reglas.
4. `03_CONTRATOS_CHATBOT.md`: alcance exacto de las consultas iniciales.
5. `04_ANALITICA_Y_ADICIONALES.md`: estructura para reportes, sueldo y CP Varios.
6. `05_ACCESO_VERSIONADO_Y_PRUEBAS.md`: integración y seguridad.
7. `tecnico/`: diccionario CSV, esquema JSON, diagramas, contratos y casos de prueba.
8. `scripts/verificar_entrega.py`: comparación de archivos o inspección de estructura.

## Primeros pasos de Emily
Extraer el ZIP en la raíz del proyecto: el paquete contiene la carpeta `entrega_andres`. Evitar crear una carpeta `entrega_andres` dentro de otra. No sobrescribe los archivos de `app`.
Desde la terminal de PowerShell, ubicada en la raíz del proyecto:

```powershell
git branch --show-current
git status --short
git ls-files -- .env
git check-ignore .env
.\.venv\Scripts\python.exe entrega_andres\scripts\verificar_entrega.py --source-root . --out entrega_andres\comparacion_codigo.json
.\.venv\Scripts\python.exe entrega_andres\scripts\verificar_entrega.py --env-file .env --schema public --out entrega_andres\revision_postgres.json
```

La primera comprobación no se conecta a ninguna base. La segunda utiliza DATABASE_URL, abre una transacción READ ONLY, consulta metadatos y la versión del esquema; no lee ventas, usuarios, contraseñas ni filas comerciales. No imprime la URL. Requiere `psycopg` y `python-dotenv` ya incluidos en la preparación del proyecto. Si tu esquema no es `public`, usa el correcto; una lista vacía también puede deberse a permisos insuficientes.

Comparte los dos JSON de revisión, **no el archivo `.env`**. Un resultado sin diferencias de tablas/columnas no certifica todos los tipos, índices, permisos, datos o reglas. La revisión incluye una lista de claves foráneas, restricciones e índices para inspección humana.

Si `git ls-files -- .env` devuelve `.env`, sigue las instrucciones de protección del archivo en `05_ACCESO_VERSIONADO_Y_PRUEBAS.md` antes de subir cambios.

## Primeros pasos de Andrés
- Revisar contratos y ejemplos; crear su rama desde el commit de migración que Emily publique.
- Implementar adaptadores de lectura y pruebas antes de conectar el modelo de lenguaje.
- Empezar con inventario y créditos pendientes; continuar ventas y resultado financiero.
- Proponer cambios de esquema por separado. No reinicializar ni borrar la base compartida.
- Dejar sueldo entre periodos, clasificación de originales y vencimientos como pendientes explícitos hasta resolver sus fuentes.

## Criterio para empezar
Andrés puede trabajar con este paquete y la versión de código acordada mientras se prepara el despliegue. Para integrar contra la base compartida se necesita confirmar estructura, acceso y versión. Para operar con datos reales se requiere, además, validar permisos, cierre, respaldo/restauración y configuración del alojamiento.
