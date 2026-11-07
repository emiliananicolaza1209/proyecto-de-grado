# Evidencia técnica de entrega · V16

Fecha de ejecución: 28 de octubre de 2026. Entorno: Python 3.12, SQLite, Flask y Chromium de pruebas. La base de trabajo del usuario no fue modificada por estas comprobaciones.

## Resultado automatizado

`python -m unittest discover -s tests -p "test_*.py"`

**100 pruebas aprobadas.** Se conservaron las 76 pruebas de la base anterior, adaptando el caso POOL a la nueva comisión extra aprobada, y se agregaron 24 casos de integración en `tests/test_gestion_v16.py`.

La batería cubre, entre otros:

- Crédito de $650.000 al 18 %: costo $117.000 y neto $533.000; sin consignación antes de desembolsar.
- Neto pactado de $900.000 más $500.000 reales de inicial: venta neta de $1.400.000, sin descontar otra vez la inicial asumida.
- Desembolsos parciales y agrupados, sumas exactas, exceso de pago, referencia repetida y cuenta no asociada.
- Compra POOL de $500.000 con aporte $600.000; ganancia diaria $100.000 y base del POOL $600.000.
- Venta POOL con costo asignado, comisión extra de $20.000 y reparto exacto entre tres personas; pagarla no descuenta otra vez la utilidad.
- Liquidación de socio sin recaudo bloqueada salvo anticipo expreso; pagos ya liquidados excluidos del saldo pendiente.
- Salida de socio mediante dinero o equipo, valoración y compensación.
- Lote en borrador, confirmación, reversión, conservación de identificadores e importación duplicada sin ingreso parcial.
- Stock por cantidad, prevención de saldo negativo y conservación del efectivo de los fondos CP.
- Parte de pago con equipo sin inventar una transferencia o entrada de efectivo; bloqueo de uso duplicado.
- Restricciones del servidor para vendedoras, invalidación de sesiones y acceso a reportes.
- Bloqueos para evitar restaurar un equipo entregado a socio o editar aisladamente una compra financiada.

## Prueba en navegador

Se recorrieron las pantallas nuevas de compras, artículos, Finanzas, créditos, sociedades, POOL y usuarios con Chromium. Las páginas respondieron correctamente y no presentaron desbordamiento horizontal del documento en el recorrido revisado. Las tablas extensas usan desplazamiento dentro de su contenedor. Se revisó también Sociedades en un ancho de 390 píxeles. No se detectaron errores JavaScript en esos recorridos.

Se ejecutó desde el formulario una venta combinada:

| Medio | Importe COP |
|---|---:|
| Crédito bruto SU+PAY | 650.000 |
| Descuento del aliado | 117.000 |
| Crédito neto | 533.000 |
| Efectivo recibido | 100.000 |
| Venta neta guardada | 633.000 |

Después se confirmó desde el formulario un desembolso de $533.000. El crédito pasó a Pagado y se verificó una sola consignación contable asociada. Los datos del recorrido eran sintéticos y no se incluyen en el ZIP.

## Prueba de actualización

Se tomó una copia de la base incluida en el proyecto recibido y se inició V16 contra esa copia:

- 16 tablas originales y 384 registros originales conservados sin cambios.
- `PRAGMA integrity_check`: `ok`.
- `PRAGMA foreign_key_check`: sin errores.
- Respaldo previo V16 creado.
- Archivo original sin modificaciones, comprobado mediante hash.

Este resultado corresponde a esa copia concreta. Debe conservarse un respaldo de la instalación que se vaya a actualizar y validarse con sus datos actuales.

## Aceptación operativa sugerida

1. Crear propietario y usuarios de prueba; comprobar que cada perfil vea y ejecute solo sus funciones.
2. Crear un lote de dos equipos y un artículo; comprobar que no estén disponibles antes de confirmar.
3. Probar rechazo de un IMEI repetido y de una plantilla Excel con errores.
4. Vender un artículo y un equipo; comprobar cantidades, estado e historia en los módulos conectados.
5. Ejecutar los tres ejemplos monetarios de `REGLAS_V16.md` y comparar con una jornada real.
6. Probar el desembolso al día siguiente y verificar que no duplique la utilidad del día anterior.
7. Configurar una sociedad, vender un equipo y liquidar solo utilidad; comprobar que el capital siga separado.
8. Probar un anticipo y una disolución por equipo en una base de pruebas.
9. Cerrar una jornada con efectivo contado diferente al esperado y revisar la diferencia y el motivo.
10. Validar impresoras, lectores específicos, otros navegadores y equipos móviles cuando estén disponibles; no se declaran probados en esta entrega.
