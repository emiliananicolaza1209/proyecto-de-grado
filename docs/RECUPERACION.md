# Copia de seguridad y restauración de CP Store

Guía para una persona no técnica. Los comandos se escriben en **PowerShell**, dentro de la carpeta del proyecto. Ninguno de estos comandos
cambia la aplicación ni la base en uso: copiar solo lee, y restaurar **nunca sobrescribe** (siempre crea una carpeta nueva).

## 1. Qué se copia y qué no

| Se copia | Dónde está |
|---|---|
| La base de datos (ventas, inventario, finanzas, usuarios, auditoría) | `instance/cpstore.sqlite` (o la ruta de `DATABASE_PATH`) |
| Las facturas adjuntas a los lotes (PDF, PNG, JPG) | `instance/facturas`. Es la **única** carpeta de archivos subidos de la aplicación. |

Los reportes del contador (Excel, PDF y CSV) y la plantilla de lotes se generan al momento y no se guardan en disco: no hay nada que copiar.

**Lo que NO se copia, a propósito:** el archivo `.env`, el archivo `.session-secret`, cualquier clave (`*.pem`, `*.key`) y la `SECRET_KEY`.
El programa lo avisa cada vez. Guárdalos por separado, en un gestor de contraseñas o un lugar seguro. Sin ellos la aplicación vuelve a arrancar,
pero las sesiones abiertas se cierran y cada persona tendrá que iniciar sesión de nuevo.

> **Cuidado con la copia misma (Ley 1581).** Contiene datos personales (cédulas, bancos, personas) y los hashes de las contraseñas. Protégela
> como a la base original: no la subas a repositorios, no la envíes por correo sin proteger, y no la dejes en un computador compartido.

## 2. Cada cuánto copiar y dónde guardarla

| Cuándo | Qué hacer |
|---|---|
| **Al cerrar cada jornada** (todos los días de trabajo) | Una copia. Es lo mínimo: si algo falla, se pierde como máximo un día. |
| **Antes de cualquier cambio** (actualizar la aplicación, migrar la base, desplegar) | Una copia, y comprobar que sirve (paso 4). |
| **Una vez por semana** | Llevar la copia más reciente a un lugar **fuera del disco del servidor** (ver abajo). |
| **Una vez al mes** | Probar de verdad una restauración (paso 5). Una copia que nunca se ha probado no es una garantía. |

**Cuántas conservar:** las 7 copias diarias más recientes, las 4 semanales y la última de cada mes. Lo demás se puede borrar.

**Dónde guardarla: NUNCA solo en el mismo disco que la base.** Si el disco falla, se pierden la base y su copia a la vez. Usa al menos uno de estos:
- un **disco externo o USB** distinto al disco del servidor (el que se guarda en un cajón no sirve si se queda conectado y falla con el equipo);
- otro **computador** de la empresa;
- una **nube privada** con acceso restringido y, de preferencia, cifrada.

Lo ideal es una copia en el servidor (rápida de restaurar) y otra fuera de él. El programa avisa cuando la copia queda en el mismo disco que la base.

## 3. Hacer una copia

```powershell
$py = "$env:LOCALAPPDATA\venvs\cpstore\Scripts\python.exe"
Set-Location 'E:\ruta\al\proyecto-de-grado'
& $py scripts\respaldo.py copiar --destino 'F:\RespaldosCPStore'
```

- `--destino` es la carpeta donde se guardan las copias (de preferencia en otro disco, por ejemplo un USB: `F:`).
- Si la base no está en `instance/cpstore.sqlite`, indícalo con `--base 'ruta\a\la\base.sqlite'` (o define `DATABASE_PATH`).
- Si las facturas no están en `instance/facturas`, usa `--soportes 'ruta\a\las\facturas'`.
- **La aplicación puede seguir encendida:** la copia es consistente (usa la función de respaldo de SQLite).

Cada copia es una carpeta con fecha y hora, por ejemplo `cpstore_20261112_183005` (formato **cpstore_AAAAMMDD_HHMMSS**, hora de Colombia):

```
cpstore_20261112_183005/
  cpstore.sqlite       la base de datos
  soportes/            las facturas
  verificacion.json    la "ficha" de la copia
```

`verificacion.json` guarda la versión del esquema (`schema_version`), el número de filas de cada tabla, dos totales de control (**ventas netas** e
**inventario disponible**) y la huella (hash SHA-256) de la base y de cada factura. Con eso se puede comprobar, sin duda, que la copia es la misma
que se hizo y que nadie la cambió.

Si algo sale mal a la mitad (se corta la luz, el disco se llena), el programa borra lo que hubiera empezado: **no deja copias a medias.** Si ves
una carpeta que empieza con `.en_curso_`, es de un corte brusco y se puede borrar.

## 4. Comprobar que una copia sirve (sin restaurarla)

```powershell
& $py scripts\respaldo.py verificar --copia 'F:\RespaldosCPStore\cpstore_20261112_183005'
```

Dice "La copia está íntegra" o explica qué está mal (la base cambió, falta una factura, hay un archivo de más, la ficha está dañada).

## 5. Restaurar (y probar la restauración)

La restauración **nunca sobrescribe**: crea una carpeta **nueva** y se niega a seguir si ya existe.

```powershell
& $py scripts\respaldo.py restaurar --copia 'F:\RespaldosCPStore\cpstore_20261112_183005' --destino 'D:\Pruebas\restaurado_20261112'
```

El programa primero revisa la copia (huellas e integridad). Si está dañada, se detiene con un mensaje claro y **no crea nada**. Si está bien,
restaura en una carpeta temporal, verifica y solo entonces la deja en el destino. La verificación comprueba:

1. `PRAGMA integrity_check` de la base restaurada (debe decir ok);
2. la versión del esquema (`schema_version`);
3. el número de filas de **cada tabla**;
4. los totales de control: **ventas netas** e **inventario disponible**;
5. la huella de cada factura y la de la base.

Verás una línea `[OK]` por cada prueba. Si alguna dice `FALLA`, el programa deshace todo y explica la diferencia.

**Para usar la restauración en lugar de la base actual** (solo si la base actual está perdida o dañada):
1. Detén la aplicación.
2. **No borres** la base actual: renombra la carpeta `instance` a `instance_vieja_AAAAMMDD` (así tienes marcha atrás).
3. Crea una carpeta `instance` nueva y copia dentro `cpstore.sqlite` y la carpeta `soportes` renombrada como `facturas`.
4. Vuelve a poner el archivo `.env` (o la variable `SECRET_KEY`) que guardaste por separado.
5. Arranca la aplicación e inicia sesión. Compara las ventas netas y el inventario disponible con los de la ficha `verificacion.json`.

## 6. Errores frecuentes

| Mensaje | Qué significa | Qué hacer |
|---|---|---|
| `El destino ya existe ... nunca sobrescribe` | Ya hay algo en esa ruta. | Elige otra ruta que no exista. No se tocó nada. |
| `La copia está dañada o fue modificada` | Una huella no coincide, falta un archivo o sobra uno. | Usa otra copia. Revisa el disco donde estaba guardada. |
| `La base está ocupada o no se pudo copiar` | Alguien estaba escribiendo justo en ese momento. | Repite en unos minutos. |
| `Las copias están en el mismo disco que la base` | Es un aviso, no un error. | Copia la carpeta a otro disco. |
| `La base cita la factura ... pero el archivo no está` | Falta un archivo de factura en la carpeta de soportes. | Recupera el archivo de una copia anterior. La copia se hizo igual, con este aviso en `verificacion.json`. |

Códigos de salida del programa: `0` todo bien · `2` uso incorrecto (ruta existente, base inexistente) · `3` copia dañada · `4` la restauración no
coincide con la copia · `5` la base estaba ocupada.

## 7. Variante PostgreSQL (pg_dump y pg_restore) — **SIN PROBAR**

> **SIN PROBAR.** El script `scripts/respaldo_postgres.py` sigue la misma lógica que el de SQLite, pero **no se ha ejecutado contra una base
> PostgreSQL real** (en el equipo donde se escribió no hay PostgreSQL). Solo están probadas por automático la lectura de la variable de entorno,
> el armado de las órdenes y las protecciones, con las herramientas simuladas. Pruébalo primero en una base de ensayo, antes de depender de él.

Cómo funciona:
- Requiere las herramientas cliente de PostgreSQL en el PATH: `pg_dump`, `pg_restore`, `psql`, `createdb` y `dropdb`.
- La URL de conexión se lee de la variable de entorno **`CPSTORE_PG_URL`** (o la que indiques con `--variable`), con el formato
  `postgresql://usuario:clave@servidor:5432/base`. **Nunca se escribe en un archivo, ni en la línea de órdenes, ni en pantalla.** Se reparte en
  las variables `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD` y `PGDATABASE` solo para los procesos que lanza.
- Define la variable solo en la ventana de PowerShell donde la uses (`$env:CPSTORE_PG_URL = ...`) o en el panel de secretos del servicio; no en
  archivos del proyecto.

```powershell
& $py scripts\respaldo_postgres.py copiar --destino 'F:\RespaldosCPStore' --soportes 'ruta\a\las\facturas'
& $py scripts\respaldo_postgres.py verificar --copia 'F:\RespaldosCPStore\cpstore_20261112_183005'
& $py scripts\respaldo_postgres.py restaurar --copia 'F:\RespaldosCPStore\cpstore_20261112_183005' --base-nueva cpstore_prueba --soportes-destino 'D:\Pruebas\soportes'
```

La copia es una carpeta `cpstore_AAAAMMDD_HHMMSS` con `base.dump` (formato personalizado de `pg_dump`), `soportes/` y `verificacion.json` (con la
marca `sin_probar`). La restauración crea una **base nueva** (nunca la actual), la verifica con los mismos conteos y totales de control, y si algo
falla borra la base que creó y los archivos temporales. Se niega si la base nueva ya existe, si se llama igual que la actual o si el destino de los
soportes existe.

**Atención con los soportes en la nube.** La aplicación guarda las facturas en `instance/facturas` del servidor donde corre. En servicios como
Render, el disco de la aplicación **se borra en cada despliegue o reinicio** a menos que se configure un disco persistente. Sin disco persistente
las facturas se pierden aunque la base de datos esté a salvo en PostgreSQL. Debe confirmarlo quien administra el despliegue.

## 8. Qué hace falta que revise una persona

- Que la copia semanal salga realmente del disco del servidor.
- Que la restauración de prueba del mes se haga y se anote (fecha, quién, resultado).
- Que el archivo `.env` y la `SECRET_KEY` estén guardados aparte y que alguien más de confianza sepa dónde.
