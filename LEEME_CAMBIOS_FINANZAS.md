# Integración de ventas, caja, finanzas e información contable

Esta entrega parte del ZIP de `proyecto-de-grado` recibido el 25 de octubre de 2026. Mantiene SQLite y agrega la migración aditiva 11. No incluye bases de datos locales ni claves.

## Antes de reemplazar los archivos en Windows

1. Cierra la aplicación. Copia `instance/cpstore.sqlite` a un lugar seguro fuera de la carpeta del proyecto.
2. Conserva tu rama `desarrollo` y cualquier cambio local sin guardar. Descomprime esta entrega en otra carpeta y compara los archivos antes de copiarlos.
3. Si aceptas la versión, copia `app/`, `migrations/` y `tests/` junto con este archivo a tu rama. Al iniciar con `python run.py`, la migración 11 conserva tablas y añade `person_id`, el antecedente de declaración, y el historial de consignaciones. Ajusta la base fija a $200.000 en jornadas **abiertas** y registra el cambio en auditoría; los cierres guardados quedan intactos.
4. Prueba con `python -m unittest discover -s tests -p "test_*.py" -q`. En PowerShell puedes activar `.venv\Scripts\Activate.ps1` antes.

## Uso diario

- En **Personal y reglas**, registra al menos una persona, marca su asistencia, revisa el sueldo y confirma las reglas. Los sueldos planificados afectan la liquidación; el efectivo solo baja cuando se registra `Pago sueldo` en Movimientos.
- La base de caja de **$200.000** queda fija. El cierre pide el efectivo que se entrega **sin esa base**. Puede aparecer un saldo calculado negativo; el importe físico contado no puede ser negativo. El sistema muestra cuánto falta para reponer base y para sueldos pendientes si van a pagarse en efectivo. Registra `Confirmar aporte recibido` únicamente tras la entrega real del efectivo por el administrador o propietario; se conserva el responsable y el motivo en auditoría. Si se cierra con déficit pendiente, se exige observación y reconocimiento de la alerta.
- `Servicio` corresponde a pérdidas y garantías del negocio y reduce el resultado sobre el que se calculan comisiones. `PD` es retiro personal y reduce la utilidad posterior a comisiones. `Fondo` es una reserva interna de accesorios (CP Varios, Hidrogel, Baterías, Memorias), no una entrada de caja.
- En costos, `Proveedor` usa el catálogo de proveedores activos (enlace para crear uno), `Fondo` muestra fondos, `Equipo` lista IMEI disponibles y `Bebida` permite consumos por cantidad. Las ventas de equipos se confirman en el módulo 03; registrar un costo complementario en Finanzas no cambia por sí solo el estado de un IMEI.
- Una venta complementaria con varios medios muestra cuánto de cada medio corresponde a ganancia y cuánto queda para costos: asigna primero la ganancia al efectivo disponible. La salida real de caja ocurre al registrar el pago correspondiente. La venta se puede corregir con un motivo; el historial conserva antes y después. Si ya tiene pagos asociados, hay que conciliarlos antes de editarla.
- En el módulo 03, una venta cambia de inmediato la disponibilidad del equipo y, si su jornada financiera ya está abierta, se incorpora automáticamente al resultado. Si aún no está abierta o ya fue cerrada, la venta aparece pendiente de revisión en Finanzas. `Corregir venta` actualiza la operación financiera abierta y registra auditoría; para modificar un cierre primero se debe reabrir.
- Puedes asociar una persona contable a una venta desde el módulo 03 o desde una venta complementaria de Finanzas. Se muestra en Información contable como referencia informativa; **no** crea una consignación ni duplica un cobro.
- Información contable permite marcar declaraciones anteriores y corregir consignaciones, dejando historial de cambios. Estas correcciones solo afectan el control de consignaciones por persona, sin alterar ventas o pagos del módulo 03.

## Regla tributaria y límites actuales

El control de consignaciones usa 1.400 UVT para los años 2025 y 2026, con valores de UVT configurados por año y cifras redondeadas a miles. La casilla de declaración anterior no cambia ese control: $183.309.000 equivale a 3.500 UVT de 2026 y **no es un límite general alternativo por haber declarado antes**. El programa emite alertas para revisión profesional, no decide la obligación tributaria de una persona. Cuando se configure una vigencia nueva, debe añadirse su UVT oficial antes de emitir un umbral.

Fuentes de consulta: [DIAN, declaración de renta año gravable 2025](https://micrositios.dian.gov.co/renta-personas-naturales-ag-2025/todo-lo-que-usted-debe-saber-sobre-renta/) y [Resolución DIAN 000238 de 2025, UVT 2026](https://normograma.dian.gov.co/dian/compilacion/docs/resolucion_dian_0238_2025.htm).

El proyecto recibido aún no dispone de autenticación ni permisos por rol; el registro de quién confirmó un aporte no equivale a verificar su identidad. Antes de usar dinero real, implementen inicio de sesión y permisos de administrador/propietario. La interfaz de catálogos abre una página aparte para crear proveedores; las ventas de equipos sin jornada abierta requieren incorporación posterior en Finanzas.
