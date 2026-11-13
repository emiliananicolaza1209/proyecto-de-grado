# CP Store V19: instalación conjunta y revisión

Esta entrega une V18.3.1 con la rama de Andrés `ia-analitica-contable`, commit
`348a073bd763f2cbb7fdace516798e89690f41fb`. Se verificó la base común Git
`cd7fe8da08bc06b04dc184421e89b7127af5dde6`. El código se integró y probó en
una copia independiente; no se publicó en GitHub ni se desplegó.

**No instalar V18.3.1 aparte.** El paquete es acumulativo para V18.2, V18.3 y
V18.3.1. No es un proyecto vacío ni una orden para reemplazar toda la carpeta.

## Qué se conservó y qué se incorporó

| Área | Decisión de integración |
| --- | --- |
| Resumen principal `/` | Se conserva el panel reciente, sus filtros y permisos. |
| Analítica `/analitica` | Tarjetas de Andrés, periodos y enlaces a reportes. |
| Chat `/chat` | Consultas por reglas; no modifica operaciones ni es un modelo predictivo. |
| Reportes | Conviven `/reportes` y sus exportaciones con `/reportes/ventas`, `/reportes/finanzas` y `/reportes/inventario`. |
| Finanzas | Se conservan apertura revisada, pagos compactos, revisión del cierre, calendario colombiano y reglas del POOL. |
| Información contable | Se conserva la presentación de nombres/bancos/datáfono. Se añade consolidado, registro complementario y paquete del contador. |
| PostgreSQL | Esquema 2: tres tablas contables nuevas, con actualización explícita. |
| Seguridad | Se integran límites de acceso, caducidad por inactividad, contraseñas y descarga protegida; se conserva configuración de producción y cámara. |

Se resolvieron los archivos compartidos, incluyendo registro de rutas, permisos,
plantillas, estilos, scripts, modelos y pruebas. El chat y los reportes consultan
los cálculos de Finanzas: no existe un segundo cálculo de utilidad independiente.
En reportes históricos usan el cierre guardado; días abiertos aparecen provisionales.

## Etiquetas y reglas de dinero

| Etiqueta | Significado |
| --- | --- |
| Utilidad del día / del periodo | Resultado después de sueldos/reglas, comisiones, servicios y gastos PD según Finanzas. No es efectivo. |
| Gastos PD | Solo los movimientos clasificados como PD; no es la utilidad. |
| Efectivo esperado incluyendo base | Dinero físico esperado en caja, incluidos los 200.000 COP de base. |
| Efectivo a entregar, sin base | Efectivo esperado menos la base que permanece en el negocio. |
| Efectivo entregado sin base | Lo contado y confirmado por quien cierra. |
| Efectivo control | Referencia del Excel; puede diferir de la caja física. |
| Margen bruto de equipos | Venta neta menos costo del equipo; no equivale a la utilidad completa de la jornada. |

Las claves internas de datos no se renombraron: los cambios son etiquetas visibles.
La comisión extra de una venta POOL reduce su utilidad en la fecha de origen.
La entrega posterior de dinero se registra en su fecha real y solo afecta caja
si salió de caja. El pago directo de administración no se inventa como entrada.
Una comisión de compra real integra el costo del equipo y el aporte requerido.
Los créditos se reconocen netos al vender; el desembolso no crea otra utilidad.

## Instalar en Windows

1. Detener el servidor con Ctrl+C. Conservar una copia de la carpeta actual y un
   respaldo verificable de PostgreSQL y de sus adjuntos. Para la base, usar un
   respaldo PostgreSQL que se haya restaurado satisfactoriamente en una base de
   ensayo; copiar archivos Python no respalda la base remota.
2. Descomprimir el paquete dentro de la raíz del proyecto. Debe quedar
   `integracion_v19\actualizar.py` junto a `app`, `run.py`, `.venv`, etc. No copiar
   manualmente la carpeta `archivos` encima del proyecto.
3. Desde la terminal de esa raíz, revisar primero:

```powershell
.\.venv\Scripts\python.exe integracion_v19\actualizar.py --proyecto .
```

Si aparecen diferencias, el instalador se detiene antes de cambiar archivos.
Conservar esa lista para integrar los cambios locales; no forzar reemplazos.
Si dice «Base compatible», aplicar:

```powershell
.\.venv\Scripts\python.exe integracion_v19\actualizar.py --proyecto . --aplicar
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

El instalador guarda los originales en `instance\actualizaciones` y muestra la
ruta. No toca `.env`, `.venv`, usuarios, ventas o respaldos y no ejecuta SQL.
Repetirlo es seguro: omite archivos que ya coinciden.

4. Después del respaldo, actualizar la **PostgreSQL existente**:

```powershell
.\.venv\Scripts\python.exe -m flask --app run.py actualizar-postgres
.\.venv\Scripts\python.exe -m flask --app run.py comprobar-db
```

El primer comando exige una base ya inicializada en revisión 1 o 2. De 1 a 2
crea únicamente `ingresos_gastos`, `correcciones_clasificacion` y
`reportes_generados` en una transacción; conserva las filas anteriores. En
revisión 2 comprueba las tablas y no repite cambios. Se niega a crear una base
vacía o aceptar una revisión desconocida. `comprobar-db` debe indicar PostgreSQL
y las 43 tablas de la aplicación; `cp_schema_revision` es control adicional.
No usar SQLite ni `init_db.py` para modificar la PostgreSQL existente.

Si falla la actualización, detenerse y conservar el mensaje sin divulgar
credenciales. No borrar tablas ni volver a crear la base. Estos comandos deben
validarse en tu entorno: aquí no se ejecutaron contra un PostgreSQL real.

5. Ejecutar las pruebas locales y arrancar:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe run.py
```

La suite normal usa bases SQLite temporales y omite PostgreSQL cuando no está
configurada la variable de ensayo. `OK (skipped=...)` no acredita esas pruebas.
Entrar como propietario y recargar con Ctrl+F5. Revisar también otro rol.
Seguir `PRUEBAS_INTEGRADAS_V19.md` antes de desplegar.

## Contabilidad, acceso y experiencia

El registro contable complementario de Andrés es independiente de la caja de
Finanzas. No volver a registrar allí una misma venta o pago ya incorporado a
Finanzas esperando que cambie el cierre. La pantalla indica esta diferencia.
El propietario accede inicialmente al chat y a los reportes analíticos. Los
informes anteriores conservan sus permisos específicos; los perfiles operativos
no reciben costos y cifras agregadas privadas.

Se conservan las consultas agrupadas y los formularios compactos recientes.
Las cinco tarjetas analíticas se calculan al abrir Analítica, no en cada visita
al resumen principal. Los indicadores de carga no significan que se haya
reducido la latencia de la base remota: falta medirla desde tu equipo y probar
la navegación en computador y celular. No se promete un tiempo de carga medido.

## Git e integración con Andrés

El ZIP descargado con Chrome es una copia de la rama: no actualiza tu carpeta
ni instala cambios por sí solo. Esta entrega incluye un bundle Git con una
rama local integrada y sus dos padres, para conservar la historia de ambos.
Ver `GUIA_GIT_V19.md`. No se debe sustituir toda tu rama por la de Andrés.

No subir `.env`, `.venv`, `instance`, respaldos, facturas, datos reales ni el
instalador descomprimido. La lista `ARCHIVOS_PARA_GIT.txt` y el cambio Git
preparado contienen solo código, pruebas y documentación revisados.

## Volver a los archivos anteriores

El instalador muestra un nombre de copia `v19_FECHA_HORA_ID`. Para revertir los
archivos, detener Flask y usar exactamente ese nombre:

```powershell
.\.venv\Scripts\python.exe integracion_v19\actualizar.py --proyecto . --revertir NOMBRE_COPIA
```

Se niega a reemplazar archivos con cambios posteriores. No revierte SQL: las
tres tablas adicionales no se borran automáticamente. Si hay que recuperar
datos, restaurar el respaldo validado en otra base, comprobarlo y decidir el
cambio de conexión con evidencia. No eliminar tablas contables con registros.
