# AGENTS.md — CP Store (Proyecto de Grado UNAB)

Contexto de trabajo para cualquier agente que retome este repositorio.

## Qué es

Prototipo de aplicativo web para transformación digital de los procesos administrativos,
financieros, tributarios y de inventarios de una empresa comercializadora de dispositivos
electrónicos (Santander), con analítica descriptiva + agente por reglas (sin ML, TRL-3).

- Autores: Emily Nicoll David Villadiego, Andrés Felipe Joya Buitrago.
- Director: José Daniel Cabrera Cruz. Codirector: Andrés Felipe Jerez Ariza.
- Repositorio: `https://github.com/emiliananicolaza1209/proyecto-de-grado.git`

## Stack y entorno

- Python 3.11 (sistema: `C:\Program Files\Python311\python.exe`).
- **Venv a usar (NO el de E:, que murió):** `%LOCALAPPDATA%\venvs\cpstore`
- Flask 3.1.2, Flask-SQLAlchemy 3.1.1, python-dotenv 1.1.1 (ver `requirements.txt`).
- Base de datos: **SQLite** en `instance/cpstore.sqlite`.
- Arquitectura: monolito Flask en 3 capas (rutas → servicios → modelos/SQLite).
  Ver `docs/ARQUITECTURA.md` (es la fuente de verdad de diseño, OE2).

## Comandos esenciales

```powershell
# Arrancar servidor (puerto 5000)
& "$env:LOCALAPPDATA\venvs\cpstore\Scripts\python.exe" run.py

# Tests (deben ser 51/51 OK)
$env:PYTHONPATH='tests'
& "$env:LOCALAPPDATA\venvs\cpstore\Scripts\python.exe" -m unittest discover -s tests

# Un test específico
& "$env:LOCALAPPDATA\venvs\cpstore\Scripts\python.exe" -m unittest test_mod05.Mod05Tests.test_corregir_clasificacion_audita_sin_borrar

# BD fresca (migraciones v1-v12 + create_all)
Remove-Item instance\cpstore.sqlite -ErrorAction SilentlyContinue
& "$env:LOCALAPPDATA\venvs\cpstore\Scripts\python.exe" init_db.py
```

## Convenciones NO negociables

1. **Dinero en centavos enteros** (`*_cents`); formularios en `Decimal` con 2 decimales, nunca `float`.
2. **Fechas operativas en texto `YYYY-MM-DD`, hora Colombia.** No usar `datetime.utcnow()` en campos que se filtran por periodo (bug de medianoche ya corregido en contabilidad).
3. **Migraciones versionadas**: cada cambio de esquema es una `upgrade_vN` NUEVA (siguiente libre = v13), idempotente, con copia `.bak` previa y registro en `schema_version`. Nunca editar una migración ya aplicada, nunca reutilizar un número. Cadena actual v1→v12.
4. **Rutas sin SQL, servicios sin `request`/`session`, plantillas sin cálculos** (solo formateo).
5. **CSRF obligatorio**: `protect_forms` en `app.before_request`; todo form HTML lleva `<input type="hidden" name="csrf" value="{{ session.csrf }}">`. En tests, pasar `csrf=self.csrf` en todo POST.
6. **Modelos**: todo modelo nuevo debe importarse en `app/models/__init__.py` (si no, `create_all()` no crea su tabla y solo falla en BD fresca).

## Estado actual (rama `Andres`, commit `c6ef7c0`)

Pusheado a `origin/Andres`. Sincronizado (local = remoto). 51/51 tests OK. Migraciones v1–v12.

### Módulos y avance (41/76 HU ≈ 62%)
- MOD-01 inventario: 65% (lotes, IMEI Luhn, catálogos, traslados). Faltan: adjunto factura, Excel, cámara, etiqueta.
- MOD-02 ventas/pagos: 80% (venta, pasamano, separados/abonos, cobros/recepciones). Faltan: 3 medios, comprobante, anulación, créditos.
- MOD-03 finanzas: 70% (jornadas, operaciones, ingresos/gastos). Falta: liquidación Elías (P-003).
- MOD-04 analítica/agente: 0%, solo diseñado (RN-IA-001–005 en `ARQUITECTURA.md` §6).
- MOD-05 contable-tributaria: 100% (TRI-001 consolidado, TRI-002 CSV+trazabilidad, TRI-003 corrección auditada, alerta UVT).
- MOD-06 usuarios/roles: 20% (CSRF + auditoría). Falta: login/roles.

### Rutas útiles para probar
`/`, `/inventario`, `/ventas`, `/finanzas?date=2026-09-30`, `/modulos/tributario/`

## Decisiones de diseño ya tomadas (no reabrir sin hablar con el director)

- `proveedor` como tabla propia (RD-002); `supplier_id` de `catalog` es histórico.
- `liquidacion_detalle` como tabla (no solo JSON) por RN-LIQ-006.
- `schema_version` fuera del ER (es control de migraciones, no dato de negocio).
- Todo depósito (`consignaciones_bancarias`) debe ligar a una venta (`venta_equipo_id`), obligatorio desde v13, columna anulable por filas históricas.
- Nómina/comisiones fuera de alcance (P-008).

## Pendientes de código (próximo sprint)

1. Migraciones v13–v15: `usuarios`/`sesiones`/`proveedor`/puentes; `participacion`/`liquidacion`/`liquidacion_detalle`/créditos/separados; `accesorio`/`alerta_recomendacion`. (DBML completo entregado; ver esquema objetivo.)
2. Liquidación Elías con % congelados + ajuste $50k (P-003).
3. MOD-06 login + roles (RN-SEG-001/002/004) ANTES de datos reales (Ley 1581).
4. MOD-04 dashboard + alertas + agente solo-lectura por reglas.

## Entregables documentales (fecha límite 09/10/2026)

- `PGII_AVANCE60_David_Joya.pdf` — avance ≥60% con evidencias (capturas, git log, migraciones, 51 tests), cronograma, bitácora 10 sesiones, sección "Resultados" por 4 fases.
- Diagramas: ER (dbdiagram.io), arquitectura 3 capas (Lucidchart), 7 casos de uso UML (00-general + 6 módulos).
- Decisiones abiertas: P-003 (ajuste $50k), P-004 (columnas del reporte del contador).

## Lecciones aprendidas (evitar repetir)

- Ningún commit sin suite en verde.
- No borrar `protect_forms` ni `upgrade()` de `create_app` (regresión ya vivida).
- Push al cierre de cada jornada (el disco E: murió por fallos físicos; hoy se trabaja desde C:).
- Windows PowerShell: en Python usar rutas con `/` no `\` (escape Unicode).
