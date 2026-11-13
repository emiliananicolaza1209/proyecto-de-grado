# Migración de ensayo sin el respaldo privado

## Qué se comprueba

La suite ordinaria ya no depende de un archivo de una máquina particular.
Los seis escenarios de `BaseConEsquemaDeAndres` se ejecutan siempre sobre una
SQLite temporal creada con el esquema histórico y registros ficticios.
Conservan sus verificaciones anteriores y añaden comprobaciones de equipos,
consignaciones, cobros, recepciones, pagos y jornadas abiertas/cerradas.

Se comprueban conservación de importes e identificadores, relaciones válidas,
estructura completa, ausencia de versiones duplicadas, repetición sin cambios,
integridad SQLite y respaldos previos que retienen las filas originales.
No se modifica código de producción, la base del usuario ni la configuración
de PostgreSQL. Tampoco se cambian las condiciones de las pruebas PostgreSQL.

## Procedencia independiente del esquema

`tests/fixtures/andres_v12_c6ef7c0.sql` contiene solo DDL público y los números
de versión 1 a 12. Se obtuvo de las migraciones y de los modelos del commit
`c6ef7c0a4592e213e9e65ba83f08754923140d8a` de la rama histórica de Andrés.
En un proceso separado se aplicaron sus migraciones a una SQLite vacía y se
crearon las tablas que faltaban con **sus modelos históricos**, antes de
exportar `sqlite_master`. Son 17 tablas y 3 índices explícitos.

No se construye el esquema de partida con las migraciones o modelos actuales
que se pretenden validar. En particular, faltan `finance_operation.person_id`,
`consignaciones_bancarias.activa` y `usuarios`: la migración real debe añadirlos.
Los registros de ensayo se insertan en el directorio temporal de cada caso.
El fixture no contiene usuarios, identificaciones ni movimientos reales.
La excepción de `.gitignore` permite únicamente este archivo SQL de ensayo;
los demás volcados y respaldos siguen excluidos.

## Ejecución reproducible

Desde la raíz del proyecto, en Windows:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_migracion_union.py -v
```

Resultado dirigido verificado en Python 3.12 y 3.13: **10 pruebas aprobadas,
sin omisiones** (6 del esquema histórico, 3 del esquema de desarrollo y 1 de
base fresca). Como controles negativos se introdujeron en memoria dos defectos:
omitir la reconciliación v19 y alterar un cierre anterior. Ambos fueron
detectados. No se dejó ninguno de esos defectos en el código.

Validación ampliada en Python 3.13: **20 pruebas aprobadas, sin omisiones**
al ejecutar los módulos de unión, distribución financiera, cierre de conexiones
de migración y recursos SQLite. La comprobación opcional también rechazó un
archivo de ensayo distinto por SHA-256 antes de modificarlo.

La suite completa conserva 816 casos Python. El workflow existente permite
ejecutar los 49 casos PostgreSQL con su contenedor temporal. El resultado de
la próxima ejecución debe registrarse después de subir esta actualización;
no se presenta el resultado anterior como si ya incluyera estos cambios.

## Evidencia histórica que no se recupera

Esto valida la migración desde el esquema histórico con datos controlados.
**No demuestra que aquella base privada exacta migre correctamente ni recupera
sus registros.** Esa comprobación no se marca como aprobada.

Se conserva por separado en `tests/validar_respaldo_andres.py`. Cuando el archivo
original esté disponible, se puede ejecutar explícitamente:

```powershell
$env:CPSTORE_RESPALDO_ANDRES = 'C:\ruta\al\respaldo\cpstore.sqlite'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p validar_respaldo_andres.py -v
Remove-Item Env:CPSTORE_RESPALDO_ANDRES
```

Mantiene la huella SHA-256 original:
`11c990140b809d5dc6a8f104b9c41e6f1ab0f2faad6ce6515a1672249d141723`.
Un archivo distinto se rechaza antes de migrarlo. La validación trabaja con
copias temporales. No subir la base privada a GitHub.

El archivo de validación histórica comienza por `validar_`, no por `test_`:
se invoca expresamente cuando existe ese insumo privado. No se cuenta como
aprobado dentro de la suite reproducible ni se usa el fixture como supuesto
respaldo original. Sigue pendiente la prueba manual del programa integrado.
