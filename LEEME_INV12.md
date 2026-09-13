# CP Store · Actualización INV-12

Esta versión actualiza Compras e inventario y conserva Ventas y pagos.
La versión visible en la cabecera debe ser INV-12.

## Instalación en Windows

1. Detén el servidor en Visual Studio Code con Ctrl+C.
2. Haz una copia de la carpeta actual del proyecto con el servidor detenido.
3. Extrae el ZIP. Copia el CONTENIDO de cpstore_mvc dentro de la carpeta de tu proyecto donde está run.py. Reemplaza los archivos de código.
4. Conserva instance, .venv y .env de tu instalación. No copies archivos de otra base de datos.
5. Desde la terminal de esa carpeta ejecuta, uno por uno:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

6. Abre http://127.0.0.1:5000/inventario y pulsa Ctrl+F5.
7. Comprueba que aparezca INV-12. Ejecutar el antiguo app.py puede abrir la aplicación anterior.

Al iniciar se aplica la migración 8 y se conserva una copia de la base anterior
con el sufijo .antes_INV12.bak. No se eliminan equipos ni sus relaciones.
No es necesario instalar Node ni jsdom para utilizar la aplicación.

## Los 16 ajustes solicitados

| Punto | Comportamiento |
|---|---|
| 1 | La búsqueda actualiza los resultados mientras escribes la referencia o el IMEI. |
| 2 | En la tabla principal queda solamente Ver equipo. La ficha conserva correcciones, traslados e historial. |
| 3 | Muestra el total filtrado y un conteo por referencia, agrupando colores, capacidades y lotes. Respeta la bodega seleccionada. |
| 4 | Cada lote muestra disponibles, vendidos, otros estados y retirados. Un pasamano no cuenta como vendido. Una venta en atención de garantía sigue en vendidos. |
| 5 | Están cargados iPhone 11 a 17 y variantes confirmadas, además de los modelos anteriores ya disponibles. iPhone 18 y sus variantes quedan pendientes de datos oficiales. |
| 6 | Colores predeterminados asociados a cada modelo confirmado de Apple. |
| 7 | Enlaces de regreso en compras, detalle del lote, registro del equipo e inventario. Al registrar en un lote, regresar lleva a ese lote. |
| 8 | Vendidos reemplaza el botón principal Eliminados. Los registros retirados por error quedan en un apartado secundario para recuperación. |
| 9 | Nombres de todos los catálogos en MAYÚSCULAS, incluidos registros anteriores y caracteres acentuados. |
| 10 | Modelo integra búsqueda y selección en un solo campo, con flecha, ratón y teclado. Un texto libre no se guarda como modelo. |
| 11 | Condiciones: Nuevo, Usado, Exhibición, Open box y 0 ciclos. La condición es independiente de Disponible/Vendido. |
| 12 | Interruptor opcional de cobertura de garantía; al activarlo exige una fecha válida. También se consulta y corrige en la ficha, con historial. |
| 13 | Capacidades por modelo. Presentación 64/128/256/512 GB y 1/2 TB según corresponda; no todos los modelos admiten todas. |
| 14 | Precio pagado por dólar editable. El lote sugiere su tasa, pero el equipo puede guardar otra. |
| 15 | Subtotal = compra USD × precio del dólar. Total = subtotal + envío COP asignado al equipo. Se visualiza al escribir y se recalcula en el servidor al guardar. |
| 16 | Guardar y escanear siguiente conserva lote, modelo, color, capacidad, condición, cobertura, proveedor, bodega y costos. Vacía únicamente el IMEI del siguiente registro. |

## Ejemplo: cinco equipos iguales

Abre el lote, registra las características y costos del primer equipo, escanea
su IMEI y pulsa **Guardar y escanear siguiente**. Escanea el siguiente IMEI
y repite. En el último pulsa **Guardar equipo**.

Cada equipo se guarda individualmente y aparece disponible de inmediato.
El escaneo no guarda por sí solo: debes pulsar el botón. Esto permite revisar
el resultado y evita que un Enter del lector registre datos incompletos.
Un IMEI repetido se rechaza, sin duplicar el equipo.
Si el siguiente tiene diferente garantía o costo, puedes ajustarlo antes de guardar.
La cantidad esperada del lote es informativa; no bloquea ingresos adicionales.

## Catálogo y garantía

Fuente de modelos, colores y capacidades:
https://support.apple.com/es-co/108044, consultada el 12 de septiembre de 2026.
La fuente consultada aún no incluye iPhone 18. No se inventaron sus variantes,
colores ni capacidades. Los modelos nuevos se podrán añadir desde Catálogos.
Las opciones personalizadas anteriores no se borran ni se fusionan automáticamente.
ROJO representa el acabado (PRODUCT)RED en las generaciones correspondientes.

La fecha de cobertura puede estar vencida: se conserva como dato, sin afirmar
que la garantía siga vigente. Activar el interruptor no envía el equipo a
reparación ni cambia su estado comercial. Ese proceso sigue en Ventas y pagos.

## Retirados y vendidos

Retirar sirve para corregir un ingreso equivocado, conservando historial y la
posibilidad de restaurarlo. No es una venta. Disponible/Vendido/Pasamano se
gestionan desde Ventas y pagos, usando el mismo registro del equipo.
Los lotes mantienen el conteo de retirados separado de las existencias.

## Verificación de esta entrega

- 29 pruebas automatizadas del servidor: costos, duplicados, cobertura,
  registro consecutivo, catálogo, migración, movimientos y conteos.
- Prueba del código de interfaz en DOM simulado: selector con teclado,
  propiedades dependientes, cálculo, interruptor y búsqueda dinámica.
- Comprobación sintáctica de JavaScript.
- Falta revisión visual en tu navegador y prueba con el lector físico.
  El DOM simulado no comprueba la apariencia ni sustituye esa prueba.

Para ejecutar las pruebas del servidor:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

En tu navegador prueba: buscar una referencia, vender uno de sus equipos,
revisar el conteo del lote, registrar dos similares, cambiar la tasa del
segundo y activar/desactivar la cobertura. Comprueba el resumen antes de guardar.

Las instrucciones INV-11 y anteriores se conservan como antecedentes.
Para los cambios descritos aquí prevalece este documento.
Los roles y permisos completos siguen pendientes del alcance anterior.
