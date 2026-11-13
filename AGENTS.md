# CP Store: instrucciones para continuar la integración V19

Autores: Emily Nicoll David Villadiego y Andrés Felipe Joya Buitrago.

Esta versión une las correcciones financieras V18.3.1 y la rama
`ia-analitica-contable` en `348a073bd763f2cbb7fdace516798e89690f41fb`.
Base Git común: `cd7fe8da08bc06b04dc184421e89b7127af5dde6`.
Ver `docs/INTEGRACION_V19.md` y `docs/PRUEBAS_INTEGRADAS_V19.md`.
Los documentos de versiones anteriores conservan contexto histórico, no el estado actual.

## Entorno y validación

Usar el entorno virtual del proyecto y `requirements.txt`. En Windows:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m flask --app run.py comprobar-db
```

SQLite temporal para pruebas locales; PostgreSQL para la instalación compartida.
No hay migración PostgreSQL automática al arrancar la aplicación.
`actualizar-postgres` actualiza una base existente del esquema 1 o 2 al 3 agregando
las tres tablas contables de v2 y la tabla permisos_usuario de v3. `inicializar-postgres` se reserva para bases nuevas.
Las pruebas PostgreSQL requieren `CPSTORE_TEST_PG_URL` de una base de ensayo,
crean esquemas aislados y los eliminan. Nunca heredan `DATABASE_URL` para probar.

## Reglas de implementación

- Dinero en centavos enteros; Decimal para entradas. Nunca float en cálculos monetarios.
- Fechas operativas YYYY-MM-DD, hora Colombia. Separar fecha de origen y pago real.
- Migraciones nuevas e idempotentes; no reutilizar revisiones ya aplicadas.
  PostgreSQL está en revisión 3; SQLite incluye la reconciliación 19 y accesos 20.
- Rutas, servicios y modelos separados. Sin request/session en servicios.
- CSRF y permisos en servidor; importar modelos nuevos en `app/models/__init__.py`.
- Mantener validación de concurrencia, sesiones, auditoría y cierres guardados.
- No hacer commit mientras la suite tenga fallos. No tratar pruebas omitidas como aprobadas.
- No incluir .env, bases, copias, facturas privadas ni datos reales en Git.

## Reglas del negocio que no deben perderse

- La revisión de personal y reglas es obligatoria para abrir/operar/cerrar.
- Base de caja: 200.000 COP. Utilidad y efectivo a entregar son cifras distintas.
- Comisión de venta POOL: gasto una sola vez en la venta de origen.
  Entrega posterior: solo cambia la caja de la fecha real si se pagó desde caja.
  Pago directo de administración no genera ingreso ni salida ficticia en caja.
- Comisión real de compra POOL integra el costo y el aporte requerido.
- Una comisión histórica pendiente no bloquea una jornada ajena.
- Sueldos/proveedores/comisiones exigibles conservan las reglas de cierre vigentes.
- Créditos: venta neta al origen; desembolsos parciales/finales no crean otra utilidad.
- Los cierres guardados son la fuente de las consultas históricas.
- Chat por reglas y analítica usan consultas comunes. No inventar IA predictiva.
- Registro contable complementario no mueve caja ni reemplaza Finanzas.

## Superficies que coexisten

`/`: resumen habitual. `/analitica`: consultas agregadas del propietario.
`/chat`: consultas por reglas. `/reportes`: informes/exportaciones anteriores.
`/reportes/<modulo>`: reportes de Andrés. `/analitica/alertas`: ajustes anteriores.
Roles del chat/analítica: propietario por defecto; respetar permisos por consulta.
