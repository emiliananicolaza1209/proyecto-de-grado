# Pruebas de aceptación de CP Store integrado

Las pruebas previas sin POOL ni créditos cubren solo parte de los recorridos.
Repetirlas después de integrar sirve para detectar diferencias entre módulos.
Usar una base de ensayo con respaldo y datos reales anonimizados. No alterar
operaciones reales para hacer que una cifra coincida con Excel.

## Evidencia que se registra por caso

Fecha operativa, tipo de día, rol, versión/commit, datos ingresados, resultado
esperado calculado antes de probar, resultado obtenido, captura sin datos
privados, identificadores de venta/pago y estado aprobado o pendiente.
Guardar por separado origen del gasto y fecha/medio del desembolso.

## Escenario automático integrado de referencia

Es sintético, no es el Excel de la tienda. Se ejecuta en
`test_integracion_v19.IntegracionV19Tests` y, si se configura una base de ensayo,
en `test_integracion_postgres_v19.IntegracionPostgresV19Tests`.

Fecha: 12/10/2026, festivo. Sueldos: ANA 50.000 y LUZ 25.000 COP.

| Paso | Importe COP / efecto esperado |
| --- | --- |
| Compra POOL | Equipo 500.000 + comisión real de compra 20.000 = costo 520.000. |
| Aporte administrativo de compra | 620.000; ganancia de compra 100.000; capital asignado 620.000. |
| Venta POOL a crédito | Bruto 800.000; costo financiero 18 % = 144.000; neto 656.000. |
| Utilidad de reventa POOL | 656.000 − 620.000 − comisión extra de venta 20.000 = 16.000. |
| Venta complementaria | Cobro efectivo 100.000; proveedor externo 30.000; margen 70.000. |
| Costos menores | 5.000. |
| Pago de proveedor | 30.000 efectivo; no descuenta nuevamente la utilidad. |
| Sueldos pagados | 75.000 efectivo; no descuentan nuevamente el resultado ya liquidado. |
| Servicio y PD | 6.000 + 9.000 efectivo. |
| Margen total | 100.000 + 16.000 + 70.000 = 186.000. |
| Utilidad final | 186.000 − 5.000 − 75.000 − 6.000 − 9.000 = 91.000. |
| Entrega sin base con POOL pagado por administración directa | 100.000 + 100.000 − 30.000 − 75.000 − 6.000 − 9.000 = 80.000. |
| Entrega si esos 20.000 POOL salen de caja | 60.000; misma utilidad de 91.000. |
| Crédito desembolsado el 13 | 200.000 + 456.000: 656.000 bancarios, sin nueva venta/utilidad y sin alterar cierre del 12. |

Las pruebas comparan cierre, inventario vendido, crédito parcial/final, consulta
financiera, chat y reporte. Una diferencia entre utilidad y efectivo es normal
si se explica por capital, gastos pagados, crédito y medios de cobro.

## Matriz manual mínima antes del despliegue

| Caso | Comprobación |
| --- | --- |
| Día normal | Aplicación de reglas/sueldos, proveedores, accesorios y cierre frente al Excel. |
| Domingo y festivo | Marcación inicial correcta, reglas y umbrales correctos; no aplicar reglas normales por error. |
| POOL comprado y vendido | Costo con comisión real; venta descuenta comisión una vez; fuente de entrega y fecha visibles. |
| POOL histórico pendiente | No bloquea un día ajeno; pagar después cambia solo caja real de ese día. |
| Anulación/reintegro POOL | Requiere devolución real y motivo; no duplica efectivo ni modifica cierre de origen. |
| Crédito | 18 %, neto pactado, cuota inicial, parcial/final y agrupado; sin segunda venta ni ingreso duplicado. |
| Efectivo, transferencia, datáfono | 5 % solo cuando corresponde, bruto/neto coherentes, persona/banco correctos; no mezclar medios reales por la etiqueta Excel. |
| Accesorios propios / proveedor | Reserva propia sigue en efectivo hasta salida real; deuda externa y pago no descuentan dos veces utilidad. |
| Personal y reglas | Sin revisión no abre/guarda/operan; pagar sueldos y comisiones desde el formulario compacto. |
| Cierre | Pendientes llevan a su sección; no cierra si faltan pagos exigibles; contado, base y diferencia se entienden. |
| Inventario y ventas | IMEI duplicado, venta/abono/recepción, anulación auditada, faltantes y cantidades sin stock negativo. |
| Roles | Propietario, administrador, vendedora e inventario; probar URL directa además del menú. |
| Concurrencia | Dos ventanas intentan vender, pagar o cerrar lo mismo: no duplica y solicita recargar. |
| Chat/analítica/reportes | Mismo periodo y utilidad; cerrar/provisional separados; sin datos no se inventa cero; exportaciones coinciden. |
| Contabilidad | Nombres/bancos/fechas legibles; registro complementario no altera caja; paquete XLSX/PDF disponible según permisos. |
| Navegación | Celular/computador, pagos compactos, registro abre donde corresponde, volver/errores, cambios sin guardar y carga. |
| Reinicio y recuperación | Datos y adjuntos permanecen; restauración validada de respaldo en base de ensayo. |

## PostgreSQL de ensayo

La suite normal no demuestra funcionamiento contra PostgreSQL. No configurar
las pruebas con la base de producción ni publicar su URL. En PowerShell, pedir
la conexión de una base de ensayo sin mostrarla:

```powershell
$conexionPrueba = Read-Host "URL PostgreSQL de una base DE ENSAYO" -AsSecureString
$env:CPSTORE_TEST_PG_URL = [System.Net.NetworkCredential]::new('', $conexionPrueba).Password
try {
    .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_postgres_esquema_v2.py" -v
    if ($LASTEXITCODE -ne 0) { throw "Revisar esquema PostgreSQL antes de seguir" }
    .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_integracion_postgres_v19.py" -v
    if ($LASTEXITCODE -ne 0) { throw "Revisar recorrido integrado PostgreSQL" }
} finally {
    Remove-Item Env:CPSTORE_TEST_PG_URL -ErrorAction SilentlyContinue
    Remove-Variable conexionPrueba -ErrorAction SilentlyContinue
}
```

Se crean esquemas `cp_test_...` separados y se eliminan al terminar cada caso.
Requiere permiso para crearlos; si se interrumpe una ejecución, revisar esquemas
temporales restantes. Después repetir las demás pruebas PostgreSQL de créditos,
dashboard, jornadas y POOL incluidas en `tests`. Un corte de conexión es una
prueba fallida que se investiga y repite; no se marca aprobada por pasar aislada.

## Decisión de despliegue

Primero corregir fallos de cifras, permisos, duplicados y pérdida de datos.
Luego registrar los resultados PostgreSQL y manuales, revisar con ambos autores
la versión exacta, subir la rama integrada y desplegar. Desde la URL pública
repetir acceso, venta/pago/cierre, reportes y persistencia; conservar una versión
recuperable. Aprobar las pruebas locales no implica que ya esté desplegado.
