# V18.2 — preparación de jornadas, pagos y revisión de interfaz

Base: V18.1. No modifica el esquema ni transforma registros históricos. Se conservan centavos en servicios y pesos en presentación. Se añade la clase de movimiento Pago comisión: reduce caja, no vuelve a restar utilidad.

- Apertura web transaccional: requiere personal, responsable y revisión expresa. Una solicitud inválida no deja una jornada creada. GET es de lectura. Los registros antiguos sin revisión muestran preparación antes de permitir movimientos.
- Guardar configuración exige también revisión en servidor. No se pueden eliminar asistentes con sueldos pagados ni reducir el sueldo por debajo de lo pagado.
- Personal y reglas incluye pago de sueldo y comisión habitual por persona, saldo y límite del pago. Se impide el cierre con sueldos/comisiones del día, proveedores y comisiones POOL pendientes hasta la fecha. Créditos por recibir no son pagos al personal. Los avisos enlazan al apartado relacionado.
- Anulación específica de entrega POOL: conserva el pago anulado, exige reintegro real y motivo, registra auditoría y devuelve la comisión a pendiente. No elimina la comisión causada por una venta válida. Los cierres relacionados deben reabrirse antes de corregir.
- Datáfono: clasificación basada en los medios vinculados a las consignaciones. No se asigna un banco destino ficticio ni se alteran montos o consignaciones históricas. Un movimiento no identificado sigue separado.
- Calendario local anual: domingo, fechas fijas, traslado al lunes, Semana Santa, Ascensión, Corpus Christi y Sagrado Corazón. Incluye Chiquinquirá desde 2026. Se determina al preparar/confirmar, sin red. Cierres anteriores mantienen su configuración.
- Navegación de formulario nuevo al inicio, enlaces de advertencias con anclas, fechas dd/mm/aaaa sin salto, alineación de Quitar y del conteo. Buscador global limitado a los contextos de equipos, sin repetirlo en Finanzas. Cuatro pictogramas retirados de los indicadores principales.
- Rendimiento: consultas de pagos agrupadas; no se cargan todos los catálogos de inventario en Personal/Cierre. Medición controlada de report con 50 ventas y bebidas: 58→9 consultas, mismos totales. 0,0252→0,0135 segundos localmente. No es una medición de red/Render.

## Evidencia

13 casos nuevos de reglas/recorridos y los mismos casos optativos sobre un esquema PostgreSQL temporal. Los fixtures antiguos de apertura se actualizan para enviar personal/revisión válidos; las comprobaciones de importes se conservan. El caso de cierre paga antes los $20.000 de comisión y cuenta $980.000 en lugar de $1.000.000, coherente con la regla nueva. Las comprobaciones antiguas del texto «tarjeta por identificar» pasan a exigir «DATÁFONO». No se omiten fallos de negocio.

La regresión completa se entrega en el log del paquete. PostgreSQL real no ejecutado en este entorno. La ejecución visual de Chromium no estuvo disponible; es necesario revisar escritorio/móvil tras instalar y ejecutar CI. Las configuraciones de pago, saldos y jornadas históricas no se reparan inventando entregas de dinero.

## Fuentes del calendario

- Ley 51 de 1983: https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=4954
- Ley 2578 de 2026, art. 6: https://dapre.presidencia.gov.co/normativa/normativa/LEY%20No.%202578%20DEL%2001%20DE%20JUNIO%20DE%202026.pdf
- Circular 23 de 2026 del Ministerio TIC: https://normograma.mintic.gov.co/mintic/compilacion/docs/circular_mintic_0023_2026.htm

Los cambios legales posteriores requieren actualizar y probar el calendario. Se mantienen fechas excepcionales configurables por el negocio.
