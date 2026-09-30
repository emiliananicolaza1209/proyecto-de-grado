# Arquitectura modular — CP Store (OE2)

Evidencia del objetivo específico 2: *diseñar la arquitectura modular del aplicativo
web para la integración y digitalización de los procesos administrativos, financieros,
tributarios y de inventarios, que incorpore un módulo de analítica de datos e
inteligencia artificial orientado al soporte en la toma de decisiones.*

Referencia de requerimientos: especificación v2.2, §6.1 (MOD-01–MOD-06), §8 (RN), §9 (RD).
Estado del código al redactar: v0.6 (39 pruebas `OK`, migraciones v1–v10).

## 1. Vista por capas

```
Navegador (Bootstrap + JS validación/escaneo)
        │  HTTP GET/POST + CSRF por sesión
app/routes/*.py  (blueprints: main, inventory, catalogos, ventas, lotes, contabilidad)
        │  llamadas a servicios, sin SQL directo
app/services/*.py (reglas: inventario, operación, lote, catálogo, costo, contabilidad)
        │  ORM
app/models/*.py  (SQLAlchemy)  ──  SQLite (instance/cpstore.sqlite)
        │                          migrations/__init__.py upgrade_v1..v10 (idempotente, con .bak)

Transversales: app/security.py (CSRF), equipment_event (auditoría),
schema_version (migraciones), reportes_generados (trazabilidad TRI-002).
```

Regla de dependencia: las rutas nunca tocan SQL; los servicios nunca tocan
`request/session`; las plantillas nunca calculan dinero (solo formatean).

## 2. Módulos y estado

| Código | Módulo | Prefijo / entrada | Estado |
|---|---|---|---|
| MOD-01 | Inventario, compras y códigos | `/inventario`, `/inventario/lotes` | Implementado (lote manual, IMEI Luhn, catálogos, traslados; pendiente: adjunto factura, Excel, cámara, etiqueta impresa) |
| MOD-02 | Ventas, pagos y créditos | `/ventas` | Parcial (venta, pasamano, separado/abono, garantía, corrección fecha; pendiente: 3 medios, comprobante, anulación, créditos) |
| MOD-03 | Finanzas y liquidaciones | — (datos vía MOD-05) | Datos base listos (`ingresos_gastos`); pendiente: participación Elías y liquidación |
| MOD-04 | Reportes, analítica, alertas y agente | — | **Diseñado, no implementado** (ver §6) |
| MOD-05 | Información contable y tributaria | `/modulos/tributario` | Implementado: TRI-001 (consolidado), TRI-002 (CSV + quién/cuándo), TRI-003 (corrección auditada) |
| MOD-06 | Usuarios, roles y seguridad | — | Parcial (CSRF + permisos documentados; pendiente: login y roles) |

## 3. Dependencias entre módulos

```
MOD-01 ──equipos/lotes──▶ MOD-02 ──ventas/costos──▶ MOD-05 ──CSV──▶ Contador
   │                          │                         ▲
   │                          └────pagos/entregas────────┘
   ▼
MOD-03 (ingresos/gastos base en MOD-05; liquidación usa ventas congeladas)
   │   MOD-04 (futuro) lee de MOD-01/02/03/05, nunca escribe operaciones
   ▼
Transversales: auditoría, migraciones, reportes (sirven a todos)
```

Prohibido: MOD-04 ejecutando ventas/pagos/liquidaciones (RN-IA-001); MOD-05
determinando impuestos (RN-TRI-001); ventas sin equipo Disponible (RN-VEN-001).

## 4. Permisos por rol (RN-SEG-001/002/004; MOD-06 pendiente de código)

| Rol | Ve costos/utilidad | Liquida (Elías) | Corrige clasificación | Opera ventas |
|---|---|---|---|---|
| Jonatan | Sí | Sí | Sí | Sí |
| Elías | Solo su participación | Solo consulta | No | No |
| Sandra | Sí | No | Sí | Sí |
| Vendedor | No | No | No | Sí (registra) |
| Contador | Reportes autorizados | No | Solo propone* | No |

\* Hoy sin login rige `actor='Sesión local sin autenticación'`; al implementar
MOD-06 estos permisos se validan en servidor (RNF-SEG-003), no solo en el menú.

## 5. Modelo de datos (RD-001–016 + contables)

```
catalog ──┲ brand/reference/color/capacity/supplier/location (jerárquico, UNIQUE kind+normal_key+parent)
          ┗ purchase_lot (supplier_id, entry_date, expected_count)
equipment (imei UNIQUE, reference/color/capacity/supplier/location_id, lot_id,
           cost_cents, sale_value_cents, paid_cents, status, sale_date, revision)
equipment_event (product_id, action, reason, before/after JSON, actor)   [RD-016]
personas_contables ─┐
bancos_destino ─────┴── consignaciones_bancarias (persona_id, banco_id, monto, fecha, referencia)
ingresos_gastos (tipo, concepto, categoria, valor_cents, fecha, relacion, soporte_ref)
correcciones_clasificacion (entidad, entidad_id, anterior, nueva, motivo, actor)  [HU-TRI-003]
reportes_generados (fecha_ini, fecha_fin, actor, totales_json, created_at)        [HU-TRI-002]
```

Dinero siempre en centavos enteros (`valor_cents`); montos de formulario en
`Decimal` con 2 decimales (nunca `float`). Fechas operativas en texto
`YYYY-MM-DD` validadas contra zona Colombia; año fiscal con `extract(year)`.
Migraciones `upgrade_v1..v10` idempotentes con copia `.bak` previa.

## 6. MOD-04 diseñado (analítica e IA, implementación diferida)

Sin aprendizaje automático (delimitación del anteproyecto, TRL-3): agente
consultivo basado en reglas + analítica descriptiva.

| Regla | Datos de entrada | Salida explicable |
|---|---|---|
| RN-IA-001 stock mínimo | existencias vs nivel por referencia/ubicación | Alerta con referencia y ubicación |
| RN-IA-002 baja rotación | `created_at` vs umbral configurable | Equipos + costo inmovilizado + días sin venta |
| RN-IA-003 recomendación | ventas/costos/gastos del periodo | Recomendación con regla y datos citados, marcable revisada/descartada |
| RN-IA-004 consulta | inventario/ventas/finanzas/tributario autorizados | Respuesta con periodo, filtros y fuente; “fuera de alcance” si no aplica; **nunca presenta sugerencia tributaria como obligación** |
| RN-IA-005 evidencia | alertas atendidas/descartadas | Causa, estado, fecha, responsable y decisión conservados |

Contrato futuro: `GET /modulos/analitica?q=` solo lectura, respeta permisos por
rol, no ejecuta operaciones. Tablas previstas: `alerta`/`recomendacion`
(RD-015: tipo, regla, datos origen, fecha, estado, revisor).

## 7. Flujos principales

Compra: lote manual → equipos por IMEI (Luhn + duplicado) → Disponible.
Venta: equipo Disponible → venta (valor, vendedor, fecha auto) → pagos/abonos →
`payment_status` Pendiente/Parcial/Pagada → separado convertible con saldo cero.
Tributario: rango periodo → consolida compras (fecha lote), ventas (`sale_date`),
ingresos/gastos (fecha), consignaciones → señala faltantes → export CSV +
registro quién/cuándo → corrección de categoría auditada (documento intacto).

## 8. Decisiones (ADR resumidos)

1. Flask + SQLite + `create_all` tras `upgrade()` versionado: prototipo local sin
   servidor de BD; migraciones con backup permiten evolucionar sin borrar.
2. CSRF propio por sesión (`security.protect_forms` + `before_request`): sin
   dependencias extra; todo POST lo exige, todo form lo incluye.
3. CSV con BOM antes que Excel/PDF: cumple “permite exportación” sin nuevas
   dependencias; conserva filtros y advierte RN-TRI-001 en el propio archivo.
4. Utilidad estimada = venta − costo (gastos asignables pendientes de MOD-03
   liquidación); se declara como estimada en UI y CSV.
5. Sin auth en v0.6: actor explícito sin autenticación + permisos documentados
   (§4); MOD-06 obligatorio antes de datos reales.

## 9. Validación OE2 y pendientes

OE2 se valida con: este documento + modelo de datos (§5) + maquetas (plantillas
`inventario/*`, `ventas/*`, `contabilidad/*`) + revisión técnica (acta F-05 con
director/codirector). Pendientes que no bloquean el diseño: P-003 (tratamiento
contable del ajuste $50k), P-004 (columnas exactas del reporte del contador —
TRI-002 técnicamente lista), P-008 (comisiones/nómina como ampliación).
