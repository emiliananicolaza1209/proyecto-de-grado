# CP Store · Módulo 03 · MOD03-01

Esta actualización parte de INV-12. No se ha publicado en GitHub ni se han podido revisar cambios posteriores de tu repositorio.

## Qué incluye

- Pasamano y cobros en /ventas: equipos compartidos con inventario, local o persona que recibe, encargada del pasamano, precio acordado opcional, vencimiento, devolución, venta y abonos.
- Recepción de dinero en /ventas/recepciones: entregas parciales por cobro, administradora que recibe, medio y comprobante, pagos directos y pendientes por vendedora.
- El cobro del cliente se cuenta una vez. Confirmar su entrega en administración no incrementa ese cobro.
- Cada operación conserva el historial. Las fechas salen automáticamente y cambiar la fecha requiere un motivo.
- No permite cobrar por encima del saldo ni recibir más de lo pendiente. Rechaza formularios con una revisión anterior del equipo.
- Una devolución de pasamano puede restablecer Disponible y conserva el historial del préstamo.

## Instalar en tu rama de desarrollo

1. Detén el servidor con Ctrl+C. Conserva una copia de la carpeta original y de instance, especialmente de tu base de datos. No subas esa base a GitHub.
2. Extrae este ZIP en Descargas. No copies todavía la carpeta archivos al proyecto: el parche aplica exactamente esos cambios y comprueba que encajen.
3. En la terminal de VS Code, abre la carpeta proyecto-de-grado y ejecuta:

```powershell
git status
git switch desarrollo
```

Si tienes cambios pendientes, guárdalos en un commit de trabajo antes de aplicar el parche. Si desarrollo no existe, créala con `git switch -c desarrollo`.

4. Sustituye la ruta de ejemplo por la ubicación del parche extraído. Ejecuta primero:

```powershell
git apply --check "C:\Users\Usuario\Downloads\CP_Store_MOD03\modulo03.patch"
```

Si no muestra errores, aplica:

```powershell
git apply "C:\Users\Usuario\Downloads\CP_Store_MOD03\modulo03.patch"
```

Si muestra que un parche no encaja, no fuerces ni reemplaces archivos: tu copia contiene cambios diferentes. Conserva el mensaje para adaptar la actualización. La carpeta archivos contiene los archivos nuevos y modificados para revisión.

5. Con el entorno virtual existente:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe run.py
```

Si la nueva carpeta aún no tiene entorno virtual, créalo antes con `python -m venv .venv`.
Al iniciar, se aplica la migración 9 a la base configurada y se crea una copia .antes_MOD03.bak. No borres instance. La migración conserva los equipos y los importes anteriores.

6. Abre http://127.0.0.1:5000/ventas y entra a Recepción de dinero desde sus pestañas.
7. Tras probar, revisa `git status`, agrega únicamente los archivos del cambio y realiza un commit en desarrollo. No se necesita modificar main.

## Prueba sugerida con datos de prueba

1. Presta un equipo disponible: indica local, encargada, precio y fecha límite. Devuélvelo y comprueba que reaparece disponible.
2. Registra una venta por 3.000 COP y un cobro de 3.000 a nombre de una vendedora.
3. En Recepción de dinero confirma 2.000 COP: quedan 1.000 pendientes de esa vendedora. El cobro del cliente sigue siendo 3.000.
4. Confirma los otros 1.000: el pendiente queda en cero.
5. Prueba un pago directo al negocio: queda por confirmar por administración sin atribuir deuda a una vendedora.
6. Si registraste un importe por error, anula primero su recepción y después su cobro. El historial conserva ambas correcciones. Esto no ejecuta reembolsos reales.

## Límites de esta entrega

- Los nombres se ingresan manualmente. Todavía falta autenticación y permisos reales para vendedoras, administradora y propietario. Las pestañas no restringen el acceso.
- Los pagos de versiones anteriores quedan Por conciliar; no se inventa quién recibió el dinero. Falta la pantalla de conciliación de esos importes.
- Se bloquea cancelar separados con dinero registrado: falta el proceso de reembolso real y su conciliación.
- La recepción se registra por cobro. No incluye aún una entrega agrupada para varios equipos.
- Se ejecutaron 33 pruebas automatizadas satisfactoriamente. Se verificaron las respuestas HTML con el cliente de Flask; falta la revisión visual en tu navegador y la prueba física con tu lector.
