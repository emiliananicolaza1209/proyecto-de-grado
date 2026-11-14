# CP Store · actualización V16.2

El ZIP incluye el proyecto completo con las funcionalidades de V16 y V16.1. Esta actualización añade el desglose de consignaciones por banco, corrige la navegación de Usuarios y permisos y mejora la revisión de nombres del catálogo y los filtros de Ventas.

## Información contable: ingresos por banco

1. Abre Información contable y selecciona el año que quieres consultar.
2. En Personas registradas, pulsa **Ver por banco** junto al total de una persona. También puedes desplegar **Ver ingresos por banco** debajo de la tabla.
3. Verás una tarjeta por banco con importe recibido, número de consignaciones activas y su participación en el total anual de esa persona.
4. El selector permite cambiar de persona. Al cambiar el año se conserva la persona seleccionada.

Las barras muestran una distribución del total: por ejemplo, $130.000 en Bancolombia y $35.000 en Banco de Bogotá suman $165.000, con participaciones de 78,79 % y 21,21 %. No representan límites independientes por cuenta. La barra de uso del umbral continúa calculándose sobre el total de la persona.

Se incluyen todos los movimientos activos del año, aunque no aparezcan entre los últimos registros del historial. Los anulados no suman. Los bancos asociados sin movimientos muestran cero; los movimientos históricos de un banco que ya no esté asociado siguen incluidos. Un ingreso registrado sin banco, como algunos cobros por datáfono, aparece en **Ingresos sin banco asociado** y no se atribuye a un banco inventado.

La vista respeta el modelo actual de una cuenta por persona y banco. Consultar estas barras no crea consignaciones ni modifica ventas. Las ediciones o anulaciones de consignaciones se reflejan al volver a consultar.

## Catálogos: revisión al guardar

Se retiró el listado automático de alertas que ocupaba la parte superior de Catálogos. Al crear o cambiar un nombre, el servidor revisa coincidencias dentro del mismo catálogo y, cuando corresponde, la misma marca o modelo.

- **Nombre parecido:** se abre una ventana con hasta cinco opciones existentes. Puedes abrir el registro con **Usar existente**, volver al formulario con **Revisar nombre** o confirmar **Es distinto: guardar**. El formulario conserva los datos escritos.
- **Duplicado exacto:** no permite crear un segundo registro, incluso si cambia la escritura en mayúsculas, espacios o acentos. Si el registro está inactivo, ofrece revisarlo para reactivarlo.
- **Modelos diferentes:** las diferencias de generación y variante se consideran en la comparación. Por ejemplo, iPhone 11/12, 16/16E, SE de segunda/tercera generación y Pro/Pro Max no se alertan únicamente por compartir texto.

El parecido es una ayuda de revisión, no una identificación automática del producto. No se fusionaron ni borraron registros existentes. Sin JavaScript, la revisión aparece junto al formulario y mantiene la validación y las opciones de decisión. La ventana admite teclado y Escape para regresar al nombre.

## Navegación y botones

- **Usuarios y permisos** muestra su propio encabezado y un enlace **Volver al resumen**. Se retiraron de esa pantalla los accesos a Jornada, Créditos y desembolsos e Historial de Finanzas.
- En **Ventas y pagos**, **Aplicar filtros** y **Limpiar filtros** tienen la misma altura y alineación, con separación uniforme y adaptación a pantalla pequeña.
- Se mantienen los permisos existentes y la navegación de Finanzas, Inventario y Ventas.

## Actualizar en Windows

1. Detén la aplicación con **Ctrl+C**. Respalda `instance` fuera del proyecto y conserva `.env` si lo utilizas.
2. Extrae este ZIP en una carpeta temporal. Copia el contenido de `proyecto-de-grado` dentro de tu proyecto actual y reemplaza el código. Conserva `instance`, `.env`, `.venv` y los archivos de Git. No crees otra carpeta `proyecto-de-grado` dentro de la actual.
3. Desde la terminal de VS Code, ubicada en tu proyecto, ejecuta:

```powershell
.\.venv\Scripts\python.exe run.py
```

4. Abre http://127.0.0.1:5000 y recarga con **Ctrl+F5**.

Para actualizar desde V16.1 no hacen falta dependencias nuevas, nuevas tablas ni una base de datos nueva. Esta entrega conserva las fórmulas financieras. Si vienes de una versión anterior a V16, consulta también `LEEME_V16.md` para la instalación inicial y la creación del propietario. No borres ni reinicies tu base de datos.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

Los 119 casos de la suite pasaron sobre bases temporales. También se comprobaron los flujos de navegación, las barras, la ventana y la alineación en navegador de escritorio y móvil. Detalle: `docs/VALIDACION_V16_2.md`.
