# Validación V16.1 · 4 de noviembre de 2026

## Alcance

Reorganización de Finanzas y Ventas y pagos sobre la entrega V16. No se modifican las tablas ni las fórmulas de cálculo. Se conserva el comportamiento de sociedades, desembolsos, capital, utilidad y permisos. Se añade validación para impedir pagar una comisión POOL antes de la fecha de su venta.

## Pruebas automatizadas

Comando: `python -m unittest discover -s tests -p "test_*.py"`.

Resultado: **107 pruebas aprobadas**, en bases SQLite temporales. Incluye las 100 pruebas anteriores y siete nuevas comprobaciones:

1. Crédito de un equipo POOL: equipo vendido y pendiente de pago, comisión extra creada una sola vez y pago actualizado al desembolsar.
2. Crédito de proveedor externo: conservación del IMEI en la operación sin crear un equipo en el inventario propio.
3. Compra POOL desde Jornada: aporte de $600.000, compra de $500.000, ganancia de $100.000; no aumenta el contador de ventas y no permite duplicarla.
4. Compra con aporte insuficiente o jornada cerrada: no deja compras ni operaciones parciales.
5. Nuevos accesos de Sociedades e Inversión en Ventas y pagos; enlaces antiguos compatibles; resumen superior usa el cierre guardado cuando corresponde.
6. Comisión POOL: fecha de origen, ausencia de comisiones futuras, rechazo de pago anterior a la venta y descuento en caja una sola vez.
7. La vendedora no puede registrar compras POOL ni acceder al resumen administrativo; mantiene el resumen de ventas de su perfil.

Se conserva la prueba previa de crédito de equipo propio, pagos parciales y pago completo. Durante la ejecución se observa un aviso de deprecación de `datetime.utcnow` en código existente; no produce fallos de pruebas. Su actualización es independiente de esta entrega.

## Recorrido de navegador

Prueba con Chromium y datos sintéticos en una base temporal:

- Registro de compra POOL desde el nuevo formulario y vista previa de la ganancia.
- Tres ventas desde el formulario de Jornada: POOL, inventario propio y proveedor externo. Cada venta usa un crédito de $1.000.000 al 18 %, con neto de $820.000.
- Verificación de tres ventas, dos equipos propios y ningún equipo externo añadido al inventario.
- Entrega de la comisión extra desde Proveedores y gastos.
- Navegación a Sociedades y liquidaciones e Inversión por ubicación, con Ventas y pagos activo.
- Revisión visual a 1440 px y 390 px. Finanzas, Ventas, Sociedades e Inversión no desbordan horizontalmente la página en 390 px. Las tablas anchas se desplazan dentro de su contenedor.
- Sin errores de JavaScript durante el recorrido.

Se añadió un respaldo de estilos para el desplazamiento de tablas y las etiquetas accesibles, de modo que esos elementos no dependan de que se descargue Bootstrap desde el CDN.

## Límites de la verificación

Las pruebas no usan la base real del negocio ni conectan plataformas de crédito o bancos externos. El registro de créditos y la confirmación de desembolsos siguen siendo operaciones internas de CP Store. Las fórmulas existentes se conservan y se validan por regresión; esta entrega no vuelve a auditar los Excel originales.
