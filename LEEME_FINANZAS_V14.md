# Finanzas: medios, proveedores y capital de equipos

Aplica los archivos del paquete sobre la rama `desarrollo`, sin reemplazar `instance/` ni `.env`. Con la aplicación detenida, guarda una copia de `instance/cpstore.sqlite` antes de iniciarla. Al ejecutar `python run.py` se aplica una migración aditiva hasta la versión 14 y se crea `cpstore.sqlite.antes_finanzas_v14.bak`. Prueba primero con una copia de tu base.

## Registro de ventas y dinero

- La venta complementaria ya no pide una segunda persona contable. La persona se elige en cada medio bancario. Si todos los medios bancarios tienen el mismo titular, la ficha de la operación conserva ese titular; si tienen titulares distintos, cada medio conserva el suyo sin adjudicar toda la venta a una sola persona.
- Se admiten hasta cinco medios de pago. La suma debe coincidir con el valor registrado.
- Transferencia exige titular registrado y banco asociado. Datáfono solo exige titular registrado: la consignación contable guarda `banco_id` vacío y el cierre muestra **DATÁFONO · TARJETA POR IDENTIFICAR**. Las transferencias históricas rotuladas «por identificar» se muestran agregadas bajo **TRANSFERENCIA**, con advertencia de conciliación; no se les inventa una cuenta ni un titular.
- Bebidas: CORONA $4.000; AGUA, AGUA CON GAS, PONY y GASEOSA $2.000; POKER y COCACOLA $3.000. Por ahora el costo unitario es fijo y se valida en el servidor. La edición de precios por administración queda para una versión con permisos.

## Proveedores y sugerencia de reparto

El catálogo de proveedores tiene las clases **Celulares**, **Accesorios** y **Ambos**. Se precargan las listas entregadas para compras inmediatas. Los proveedores que aparecen en las dos listas conservan una sola ficha de clase Ambos y, al registrar un costo, se elige explícitamente si corresponde a celular o accesorio. En Compras y lotes se muestra esta clasificación junto al nombre. **Gastos PD** y **Gastos de servicio** se registran como movimientos, no como proveedores. Los fondos internos CP VARIOS, CP HIDROGELES, BATERÍAS y MEMORIAS siguen siendo capital de reposición sin deuda externa.

En **Proveedores y gastos**, cada obligación indica el saldo pendiente, la parte del efectivo de esa venta disponible después de separar la ganancia y la parte del costo del celular que debe gestionarse con administración. Por ejemplo, venta $700.000, costo del equipo $580.000, cobro $500.000 en efectivo y $200.000 por datáfono: ganancia $120.000, sugerencia de $380.000 del efectivo y $200.000 con administración. Los accesorios pueden salir de caja aunque el cliente haya pagado por transferencia, siempre que exista efectivo suficiente; la aplicación sigue mostrando el saldo de caja para comprobarlo. Estos importes son sugerencias: el dinero solo sale al registrar el pago real.

Los equipos del inventario y del POOL vendidos desde el módulo 03 muestran por separado una **referencia de recuperación del capital** según los cobros en efectivo confirmados. No genera otra obligación ni descuenta de nuevo el costo. Los cobros de fechas distintas, anticipos y confirmaciones posteriores deben revisarse en Ventas y pagos antes de tomar decisiones de caja.

Los pagos a proveedores de una jornada abierta pueden corregirse con motivo. Importe, medio, titular y banco se actualizan y se conserva el antes y después en la auditoría. Si un pago deja de ser bancario, su consignación automática se marca inactiva y deja de sumar al control tributario. Un pago de una jornada cerrada exige reabrir esa jornada con motivo; no se reescribe un cierre anterior silenciosamente.

## Verificación

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p "test_*.py" -q
python run.py
```

Se mantiene el acceso abierto acordado: no se implementaron permisos por rol en esta entrega.
