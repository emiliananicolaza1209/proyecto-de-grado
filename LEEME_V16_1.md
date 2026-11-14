# CP Store · actualización V16.1

Esta actualización reorganiza la entrega V16 y conserva los nombres de los módulos, sus datos y sus reglas de cálculo. El ZIP completo contiene esta guía y todo el código de la aplicación.

## Qué cambió

- Finanzas muestra arriba DEBE, HABER, liquidación del día, resultado final, cantidad y valor neto de ventas, comisiones y total control. Los importes provienen del mismo cálculo que Cierre. Si consultas una jornada cerrada, muestra sus valores guardados.
- Se retiraron los tres recuadros superiores de créditos netos, desembolsos y ganancia por compras POOL. El detalle sigue disponible en Cierre y Créditos y desembolsos.
- Sociedades y liquidaciones e Inversión por ubicación ahora se encuentran en Ventas y pagos. Se conservan los permisos y los datos existentes.
- La compra POOL se registra directamente en Jornada → Movimientos. Sus comisiones extra se entregan desde Jornada → Proveedores y gastos.
- Los créditos funcionan para equipos del inventario, del POOL y de proveedores externos. No hace falta crear otra venta para registrar el crédito.

## Dónde queda cada operación

| Operación | Acceso |
|---|---|
| Ver Debe, Haber y resultados diarios | Finanzas → Jornada, parte superior |
| Registrar venta al contado o a crédito | Finanzas → Jornada → Movimientos → Registrar venta complementaria o movimiento |
| Registrar aporte y ganancia por compra a cliente | Finanzas → Jornada → Movimientos → Registrar compra POOL |
| Entregar comisión extra de venta POOL | Finanzas → Jornada → Proveedores y gastos → Comisiones extra por ventas del POOL |
| Gestionar aliados y confirmar desembolsos | Finanzas → Créditos y desembolsos |
| Crear socios y sociedades, liquidar utilidad o capital | Ventas y pagos → Sociedades y liquidaciones |
| Consultar inversión según ubicación | Ventas y pagos → Inversión por ubicación |

Los enlaces antiguos a sociedades e inversión siguen funcionando. El enlace antiguo a compras POOL lleva ahora a Jornada.

## Para qué sirve la compra POOL

La compra registra el aporte de administración para comprarle un celular a un cliente y la ganancia asociada. Es una compra, por eso no aumenta el contador de ventas.

Ejemplo: administración entrega $600.000, se pagan $500.000 al cliente y no hay otros costos. La ganancia de compra es $100.000 y aparece en la jornada seleccionada. El capital del equipo para el POOL queda en $600.000; así esa ganancia no vuelve a contarse al vender el celular.

1. Registra la retoma en Compras e inventario con su costo y gastos adicionales.
2. Abre la jornada correcta en Finanzas y selecciona Registrar compra POOL.
3. Elige el equipo pendiente, el aporte y la propiedad. El formulario muestra el cálculo antes de guardar.
4. Confirma solo cuando se haya recibido el aporte y pagado la compra y sus costos.

En una parte de pago, primero registra la venta con el medio RETOMA y el equipo recibido. Luego vincula esa venta en la compra POOL; la recepción de un celular no se trata como efectivo.

Una venta de un equipo POOL se registra en el formulario normal de venta. Puede llevar crédito, transferencia, efectivo u otros medios habilitados. La comisión extra de $20.000 sigue siendo adicional a la comisión habitual y se reparte entre el personal que asistió. Confirmar su entrega afecta caja una sola vez.

## Venta a crédito según el origen del equipo

- **Inventario o POOL:** en costos selecciona Tipo Equipo y su IMEI. Para POOL indica el costo asignado por administración, respetando el capital mínimo registrado.
- **Proveedor externo:** selecciona Tipo Proveedor, proveedor de celulares y el IMEI externo. Queda registro del equipo en la operación sin incorporarlo a las existencias propias.
- En Distribución del dinero selecciona CRÉDITO, aliado, porcentaje o neto pactado, titular y banco. Puedes combinar los medios ya habilitados, hasta cinco.
- La utilidad corresponde a la jornada de venta. La entrada efectiva en la cuenta se registra al confirmar el desembolso. El equipo propio vendido queda pendiente de pago hasta completar los cobros y desembolsos.

## Actualizar en Windows

1. Detén la aplicación con Ctrl+C y respalda `instance` fuera del proyecto. Conserva también `.env` si lo utilizas.
2. Extrae el ZIP en una carpeta temporal y copia el contenido de `proyecto-de-grado` dentro de tu proyecto actual, reemplazando el código. Conserva `instance`, `.env`, `.venv` y los archivos de Git. No anides otra carpeta `proyecto-de-grado` dentro de la actual.
3. En la terminal de VS Code, ubicada en tu proyecto, ejecuta:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

4. Abre http://127.0.0.1:5000 y recarga con Ctrl+F5. Usa tus usuarios de V16; no necesitas crearlos otra vez.

Esta actualización no añade tablas ni cambia las fórmulas financieras. Si vienes de una versión anterior a V16, consulta también LEEME_V16.md para el primer usuario y la actualización inicial de la base. No ejecutes un reinicio o borrado de la base de datos.

## Verificación

Las pruebas se ejecutan sobre bases temporales independientes:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

El detalle de validación de esta entrega está en docs/VALIDACION_V16_1.md. Las guías anteriores se conservan como historial; para los accesos y la actualización actual prevalece esta guía.
