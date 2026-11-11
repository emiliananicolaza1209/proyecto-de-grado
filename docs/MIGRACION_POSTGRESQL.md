# CP Store: preparación de PostgreSQL desde cero

## Alcance y estado

Se parte del ZIP CP_Store_para_migracion.zip. Por decisión del negocio, los datos SQLite son de prueba y NO se transfieren. La base SQLite original no se borra. PostgreSQL comienza con los catálogos de marcas, referencias, capacidades, colores, proveedores, ubicación LOCAL CP STORE, aliados y socio JONATAN que ya estaban definidos en el código. No se crean existencias, ventas, jornadas, consignaciones, personas ni usuarios.

Esta entrega adapta el código; no ha conectado ni modificado la base de Render. Validación realizada: 122 pruebas aprobadas (119 existentes y 3 de configuración/compilación PostgreSQL). Las cuatro pruebas de integración PostgreSQL están incluidas, pero no se ejecutaron por no disponer de un servidor PostgreSQL accesible en el entorno de revisión. No equivale a aceptación funcional en Render.

## Aplicar en Windows

1. Detener Flask. Mantener respaldo de la carpeta y de instance. Seguir en migracion/postgresql.
2. Descomprimir este ZIP fuera del proyecto. Copiar su contenido sobre la carpeta del proyecto y reemplazar archivos coincidentes. No borrar .git, .env, instance ni .venv; no vienen incluidos en el ZIP.
3. En terminal de VS Code, con el entorno virtual activado:

```powershell
python -m pip install -r requirements.txt
```

4. Crear .env si todavía no existe (el comando no reemplaza uno existente):

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

5. Generar y guardar una clave sin mostrarla en la terminal. Este comando conserva una SECRET_KEY existente no vacía:

```powershell
python -c "from dotenv import dotenv_values, set_key; import secrets; p='.env'; set_key(p,'SECRET_KEY',dotenv_values(p).get('SECRET_KEY') or secrets.token_hex(32)); print('Clave configurada; no compartir .env')"
```

6. Abrir .env en VS Code. En Render, abrir Connect y copiar External Database URL. Pegar SOLO en el archivo local:

```env
DATABASE_URL=PEGAR_AQUI_LA_URL_EXTERNA_REAL
SESSION_COOKIE_SECURE=false
```

No copiar la contraseña al chat, al README ni a .env.example. La clave SECRET_KEY debe quedar configurada como en el paso anterior. DATABASE_PATH puede permanecer; se usa únicamente cuando DATABASE_URL está vacío. Si Render restringe conexiones externas, autorizar la IP pública del equipo que hará las pruebas. No cambiar a la URL interna desde el computador local.

7. Inicializar la base NUEVA de Render:

```powershell
python -m flask --app run.py inicializar-postgres
python -m flask --app run.py comprobar-db
```

El inicializador exige PostgreSQL. Si encuentra tablas ajenas a esta inicialización, se detiene sin borrarlas. Si se ejecuta de nuevo sobre el esquema ya inicializado, no reinserta catálogos ni elimina registros. La creación inicial y los catálogos se confirman en una transacción. Se registra cp_schema_revision=1. Las migraciones futuras deberán agregar revisiones explícitas: create_all no actualiza columnas de tablas existentes.

8. Crear el propietario, ya que los usuarios de SQLite no se trasladaron:

```powershell
python -m flask --app run.py crear-propietario
```

Se solicitan nombre, usuario y contraseña de al menos 12 caracteres. No incluir la contraseña en un comando ni en Git.

9. Iniciar localmente y entrar con ese usuario:

```powershell
python run.py
```

Abrir http://127.0.0.1:5000. La aplicación corre en el computador y sus datos se guardan en Render. Esto todavía NO publica la aplicación web.

## Pruebas

Pruebas locales existentes y configuración (usan bases temporales SQLite):

```powershell
python -m unittest discover -s tests
```

El test con DATABASE explícito no hereda la URL de Render. Las cuatro pruebas PostgreSQL se omiten mientras CPSTORE_TEST_PG_URL no esté configurada.

Para ejecutar pruebas reales de créditos, desembolsos, inventario y montos grandes contra la base DE DESARROLLO:

```powershell
$env:CPSTORE_TEST_PG_URL = (python -c "from dotenv import dotenv_values; print(dotenv_values('.env')['DATABASE_URL'])")
python -m unittest discover -s tests -p test_postgres_integration.py
Remove-Item Env:CPSTORE_TEST_PG_URL
```

Cada caso crea un esquema cp_test_<identificador> separado y lo elimina al finalizar; no borra public. Requiere permiso CREATE SCHEMA. No ejecutar contra producción. Si la ejecución se interrumpe, puede quedar un esquema de prueba para revisar y retirar posteriormente.

Pruebas manuales indispensables antes del uso empresarial:
- Catálogos y proveedores, lotes, POOL, accesorios y seriales opcionales.
- Venta y actualización consistente del inventario; reversión permitida con historial.
- Efectivo, transferencia, datáfono, pagos combinados y créditos; cuenta contable correcta.
- Créditos al 18 %, neto pactado, cuota inicial y desembolsos parciales/agrupados.
- DEBE/HABER, fondos CP, pagos a proveedores, comisiones y cierre contra los casos Excel.
- Permisos con usuarios distintos y dos ventanas que intenten vender/cobrar/cerrar lo mismo.
- Restauración de copia PostgreSQL y conservación de archivos adjuntos.

## Cambios técnicos

- DATABASE_URL selecciona PostgreSQL mediante psycopg; URL externa Render con SSL.
- PostgreSQL no ejecuta migraciones SQLite ni crea/modifica tablas al arrancar la app.
- Se conserva el arranque y las migraciones SQLite para desarrollo y regresión.
- Importes enteros en centavos usan BIGINT. Los importes contables Numeric(14,2) siguen en pesos.
- Fechas históricas de texto mantienen el contrato de la aplicación; el valor por defecto usa un cast explícito. La conexión PostgreSQL usa UTC y las funciones de fecha de negocio existentes se conservan.
- Se conservan las restricciones de valores positivos que existían solo en el DDL heredado.
- Las transacciones web de escritura PostgreSQL toman un bloqueo asesor común antes de leer saldos. Evita que dos solicitudes calculen pagos sobre el mismo saldo anterior. Se libera al commit/rollback. Es una estrategia conservadora para pocos usuarios; no bloquea consultas de lectura. Clientes SQL externos y futuros procesos de escritura deben respetar la misma estrategia. Una optimización futura puede usar bloqueos por entidad con pruebas de concurrencia.
- Pool de conexiones pequeño para el plan gratuito; comprobar capacidad con carga real.

## Despliegue posterior

No desplegar hasta validar el paso local contra PostgreSQL. Para Render Web Service: mismo repositorio/rama de migración en entorno de pruebas y misma región que la base. Build: pip install -r requirements.txt. Start: gunicorn run:app --bind 0.0.0.0:$PORT --workers 1 --threads 4. Configurar DATABASE_URL interna, SECRET_KEY y SESSION_COOKIE_SECURE=true como variables privadas. Nunca ejecutar el inicializador como parte de cada petición.

Los adjuntos actuales guardados dentro de instance requieren almacenamiento persistente antes de usar esa función online. La base PostgreSQL no guarda automáticamente esos archivos. El filesystem web gratuito es efímero.

El plan gratuito de la base vence 30 días después de crearla. Cambiar a pago antes de vencer o exportar los datos que se quieran conservar. Antes de iniciar la empresa, usar un entorno limpio de producción y conservar las pruebas en desarrollo; no existe en esta entrega un comando de borrado masivo.

## Referencias técnicas

- https://render.com/docs/postgresql-creating-connecting
- https://render.com/docs/free
- https://docs.sqlalchemy.org/en/20/dialects/postgresql.html
- https://www.postgresql.org/docs/current/explicit-locking.html
