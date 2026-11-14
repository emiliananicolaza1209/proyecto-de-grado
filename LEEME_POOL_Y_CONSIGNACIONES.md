# Actualización: Finanzas, contabilidad y POOL de retomas

Este paquete se aplica sobre CP Store con los módulos 02, 03, 04 y 06 existentes. Copia las carpetas `app`, `migrations` y `tests`, además de este documento y `.env.example`, en tu rama `desarrollo`. **No sustituyas `instance/` ni tu `.env`**. Antes de iniciar, guarda una copia de `instance/cpstore.sqlite` con la aplicación detenida. Al iniciar `python run.py` se ejecutan migraciones aditivas hasta la versión 13. Se conservan los datos existentes y se generan copias `*.antes_pool_y_consignaciones.bak` y `*.antes_bancos_persona.bak` cuando corresponda. Comprueba primero en una copia de tu base real.

## Finanzas

- En Movimientos, el responsable comienza sin selección; se ofrecen las personas con asistencia confirmada ese día y `Otro` permite un nombre adicional. El pago de sueldo solo admite personal presente.
- Los medios son **EFECTIVO, TRANSFERENCIA y DATÁFONO**. Una transferencia exige persona y banco asociados; un datáfono solo exige titular registrado. En Finanzas se pueden combinar hasta cinco medios. Si falta la persona o el banco, se registra en Información contable y se regresa a Finanzas.
- Cada medio bancario de Finanzas crea una consignación vinculada dentro de la misma transacción. Su edición actualiza el mismo registro; al anular el movimiento se excluye del total anual, conservando el historial. Las transferencias usadas para pagar una obligación externa también se vinculan, sin crear una segunda venta.
- Los costos de **CP VARIOS, CP HIDROGELES, BATERÍAS y MEMORIAS**, aun si se elige el tipo `Proveedor`, se suman por día como capital de reposición de accesorios propios. Descuentan margen, pero no aparecen como obligaciones pendientes a un tercero. El resto de proveedores sigue generando su saldo.

## Registro de personas

En esta etapa cualquier persona que acceda al aplicativo puede registrar personas y bancos desde Información contable. El enlace **Registrar persona o banco** aparece en Finanzas para facilitar el registro cuando aún no existe el destinatario de una transferencia. Los controles de acceso por usuario y rol se implementarán de manera unificada más adelante en el módulo 07. Conserva el `SECRET_KEY` permanente de la aplicación y no publiques tu archivo `.env`.

Información contable separa **Registrar una persona** de **Agregar banco a una persona**. Comprueba la identificación sin puntos, espacios ni guiones: si ya existe, muestra la ficha encontrada y evita crear otra aunque se haya escrito un nombre diferente. Con un nombre igual o parecido y una identificación distinta, requiere confirmar que se trata de otra persona. Una persona puede tener varios bancos; volver a asociar el mismo no crea un duplicado. Al iniciar sobre una base existente, la migración versión 13 vincula automáticamente los bancos que ya constan en consignaciones y pagos a proveedores. En consignaciones y en Finanzas solo pueden seleccionarse bancos asociados a la persona. El antecedente de declaración de renta permanece como dato opcional dentro de la ficha, sin ocupar el formulario principal.

El historial contable distingue el origen automático de Finanzas y muestra consignaciones anuladas. Una corrección manual en Contabilidad no altera la venta; si posteriormente se vuelve a editar el mismo medio desde Finanzas, prevalecerán los datos de esa operación y quedará auditado.

## Compras e inventario

Usa **Retoma · POOL** para equipos comprados a clientes en el local. No selecciona lote, USD ni TRM. Se registra el importe pagado en COP más hasta cinco costos adicionales (por ejemplo, comisión y reparaciones); el costo total se calcula automáticamente. El proveedor es CP CELULARES y la condición Usado. Se crea la ubicación LOCAL CP STORE, que puede cambiarse por otra ubicación local registrada. La ficha del equipo muestra el detalle y permite corregirlo con motivo. El POOL agrupa unidades disponibles y vendidas, capital aún invertido y margen bruto de las ventas registradas.

**Alcance actual:** los cobros bancarios originados en el módulo 03 todavía se agrupan por medio y no identifican un banco o cuenta individual; esta sincronización automática se aplica a los medios registrados en Finanzas. El control de 1.400 UVT es una alerta de seguimiento, no una determinación tributaria.

## Verificación y Git

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p "test_*.py" -q
python run.py
```

Prueba una retoma con comisión y reparación, una venta complementaria mitad efectivo y mitad transferencia, su edición y anulación; revisa que Información contable contabilice el medio una sola vez. Después revisa el POOL y los costos diarios de CP VARIOS. Para compartir el cambio: `git status`, `git add app migrations tests LEEME_POOL_Y_CONSIGNACIONES.md .env.example`, `git commit -m "Integrar retomas POOL y consignaciones financieras"`, `git push origin desarrollo`.
