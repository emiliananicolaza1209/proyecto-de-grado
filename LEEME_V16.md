# CP Store · entrega V16

Esta entrega conserva los nombres de los módulos y amplía la base existente con compras por borrador, accesorios por cantidad, créditos, retomas/POOL, sociedades, liquidaciones y usuarios con permisos. No incluye una base de datos ni credenciales de ejemplo.

## Actualizar tu instalación en Windows

1. Detén el servidor en VS Code con **Ctrl+C**. Haz la actualización primero en tu copia de desarrollo.
2. Respalda `instance` fuera de la carpeta del proyecto. Conserva también tu `.env` si lo utilizas. En PowerShell, desde `C:\Users\Usuario\Documents\proyecto-de-grado`:

```powershell
$destinoCp = Join-Path $env:USERPROFILE ("Documents\respaldo_cp_store_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
New-Item -ItemType Directory -Path $destinoCp
Copy-Item .\instance -Destination $destinoCp -Recurse
if (Test-Path .\.env) { Copy-Item .\.env -Destination $destinoCp }
```

3. Extrae el ZIP en una carpeta temporal. **Copia el contenido de `proyecto-de-grado` dentro de tu carpeta actual**, reemplazando el código. No crees una segunda carpeta `proyecto-de-grado` dentro de la primera. Conserva tu `instance`, `.env`, `.venv` y la información de Git. El ZIP no incluye esos datos.
4. Instala las dependencias usando el mismo entorno con el que ejecutas la aplicación:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Si es una instalación nueva y aún no existe `.venv`:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

5. **Crea el primer usuario propietario una sola vez**:

```powershell
.\.venv\Scripts\python.exe -m flask --app run crear-propietario
```

El comando solicita usuario, nombre y contraseña de al menos 12 caracteres. La contraseña no se muestra al escribir. No hay usuario ni contraseña predeterminados. Si ya lo creaste en esta versión, omite este paso.

6. Inicia la aplicación:

```powershell
.\.venv\Scripts\python.exe run.py
```

Abre **http://127.0.0.1:5000**, inicia sesión y usa **Usuarios** para crear los accesos del personal. Recarga con **Ctrl+F5** después de actualizar.

El primer arranque crea las nuevas tablas y conserva los registros anteriores. Antes de la primera actualización V16 de una base existente, también genera un respaldo SQLite en `instance/respaldos`. Este mecanismo complementa la copia manual anterior. No ejecutes scripts de inicialización para borrar o reconstruir la base.

## Recorrido recomendado

| Necesidad | Acceso |
|---|---|
| Proveedores, alias, compras e importación Excel | Compras e inventario → opciones superiores |
| Crear un lote y revisar sus líneas antes de ingresarlas | Compras y lotes → nuevo borrador → confirmar |
| Registrar accesorios/repuestos y revisar existencias | Accesorios y repuestos |
| Incorporar una compra de celular a cliente | Compras e inventario → Registrar retoma |
| Confirmar el aporte y la ganancia de esa compra | Finanzas → Compras y comisiones POOL |
| Registrar venta con efectivo, banco, datáfono, crédito o retoma | Finanzas → Movimientos → Registrar venta |
| Confirmar el desembolso de una o varias ventas | Finanzas → Créditos y desembolsos |
| Crear socios y configurar capital/utilidad | Finanzas → Sociedades y liquidaciones |
| Pagar utilidades por intervalo de fechas | Sociedades y liquidaciones → Confirmar liquidación |
| Consultar capital por ubicación y propietario | Inversión por ubicación |
| Consultar responsables y motivos de cambios nuevos | Historial |

Los aliados iniciales son ADDI, SISTECRÉDITO, SU+PAY, BANCO DE BOGOTÁ e IPHONE ALIADOS. **Sus porcentajes iniciales son 0 %**, porque no se han supuesto tarifas comerciales. Configura el porcentaje real y, si corresponde, la cuenta habitual antes de utilizarlos. Cada venta conserva sus propias condiciones.

Para el ejemplo acordado, SU+PAY puede configurarse en **18 %**: un crédito bruto de $650.000 deja $533.000 netos. Es diferente del datáfono con recargo: $1.155.000 / 1,05 = $1.100.000.

## Perfiles incluidos

| Perfil | Alcance principal |
|---|---|
| Propietario | Todas las funciones, usuarios, socios y reglas de sociedades. |
| Administrador | Operación, costos, cierre, desembolsos y liquidaciones; no administra usuarios ni configura socios/sociedades. |
| Inventario | Equipos, proveedores, catálogos, preparación de lotes y traslados; consulta artículos y costos. La confirmación de lotes y los cambios de artículos/costos de stock corresponden a administración. |
| Vendedora | Consulta de equipos, pasamano/cobros, ventas del día y consulta de créditos. No confirma desembolsos, cierres ni liquidaciones. |
| Socio | Consulta de sus resultados, pagos e inversión. Requiere asociar el usuario al socio correspondiente. |

Los permisos se comprueban en el servidor. Desactivar un usuario o modificar sus permisos invalida sus sesiones anteriores. Los accesos pertenecen a CP Store; no son las cuentas de GitHub o ChatGPT.

## Documentos incluidos

- `docs/REGLAS_V16.md`: fórmulas, ejemplos y reglas operativas aplicadas.
- `docs/EVALUACION_V16.md`: alcance por historia, evidencia y pendientes.
- `docs/VALIDACION_V16.md`: resultados de las pruebas y recorrido de aceptación.

## Compartir con tu compañera

Comparte el código y `requirements.txt` mediante Git en la rama de desarrollo. Cada persona crea su propio entorno y su base local; las nuevas tablas se crean al arrancar esta versión. **Git comparte la estructura y el código, no sincroniza los datos que cada una registra.**

No subas `instance`, `.env`, contraseñas, bases SQLite ni facturas a GitHub. Conserva los cierres y archivos de `instance` en los respaldos. La migración a PostgreSQL continúa fuera de esta entrega.

## Ejecutar las pruebas

Desde la raíz del proyecto:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

Las pruebas utilizan bases temporales. La revisión de entrega pasó 100 pruebas en Python 3.12. La comprobación visual adicional se realizó con Chromium; no equivale a probar impresoras, cámaras o todos los navegadores.
