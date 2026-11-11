# Analítica de CP Store: modelo analítico, reglas y límites

Documento para el informe del proyecto. Describe **lo que está implementado**, cómo se calcula, qué no hace y cómo se prueba. No presenta como
hecho nada que sea solo una propuesta: lo propuesto está marcado "queda para después".

## 1. Principios (se aplican a todo lo de este documento)

1. **Los números los calcula la aplicación.** Un modelo de lenguaje, si algún día se usa, solo redacta la explicación; nunca calcula ni corrige
   registros. Hoy no hay modelo de lenguaje: la redacción es determinista (`chat_service.redactar_respuesta`).
2. **Una sola fuente de cálculo.** La pantalla de cada módulo, el reporte por periodo y el chat usan las mismas consultas
   (`app/services/consultas_service.py`). Si una cifra cambia, cambia en todas partes.
3. **Solo lectura.** Ninguna consulta escribe datos del negocio ni abre jornadas (`open_day`). Lo único que se escribe es una fila de auditoría
   por consulta en `registro_gestion` (usuario, fecha, herramienta, periodo y estado; nunca las cifras ni la pregunta).
4. **Dinero en centavos enteros;** fechas `AAAA-MM-DD` inclusivas, hora de Colombia (UTC−5). Sin SQL propio de SQLite: las consultas usan el ORM y
   agrupan por día o semana en Python (para poder pasar a PostgreSQL).
5. **Un valor que no se puede calcular es `null`, no una cifra inventada.** Un día sin jornada es cobertura incompleta, no cero.
6. **Solo valores agregados.** Sin nombres de clientes, cédulas, sueldos por persona ni IMEI. El costo solo lo ve el Propietario.
7. **Estimación frente a comparación frente a hecho.** Cada respuesta dice qué es (`es_estimacion`, `es_comparacion`, `es_prediccion`). **Ninguna de
   las consultas actuales predice**: son hechos medidos o comparaciones de periodos que ya ocurrieron.

## 2. Contrato común de las consultas

Toda consulta devuelve `consulta`, `estado`, `mensaje`, `periodo`, `zona`, `fuentes`, `metodo`, `cobertura`, `advertencias`, `cifras`, `detalle`,
`es_estimacion` y `generado_en`. Cinco estados, siempre distintos:

| Estado | Cuándo | Cifras |
|---|---|---|
| `ok` | Cobertura completa. Un 0 real es una cifra válida. | Reales. |
| `sin_datos` | No existe la fuente para responder. | `null`, nunca 0. |
| `parcial` | Hay datos, pero falta una parte (días sin jornada, jornadas abiertas, equipos por incorporar, una cifra nula). | Las calculables; lo demás `null`, con la razón en `advertencias`. |
| `sin_autorizacion` | El perfil no puede usar la consulta. | Ninguna; ni siquiera se confirma si hay datos. |
| `error_temporal` | Falló la base de forma recuperable. | Ninguna; se puede reintentar. |

Un parámetro mal escrito (fecha inexistente, ID que no corresponde) no es un estado: lanza `ParametroInvalido` y la ruta responde 400.

**Quién puede usar qué.** Hoy solo el **Propietario**, y se controla en una sola constante, `ROLES_CONSULTAS`. El costo inmovilizado depende de otra,
`ROLES_CON_COSTO`. Habilitar a otro perfil exige habilitarlo también en las consultas de las que se alimenta una consulta compuesta.

## 3. Las consultas

### 3.1 Las cuatro consultas base

| Consulta | Qué responde | Fuente | Regla principal |
|---|---|---|---|
| `resumen_ventas(ini, fin)` | Venta neta incorporada a Finanzas en el periodo, con desglose equipos y complementarias. | Operaciones `Venta` no anuladas, por fecha de jornada (snapshot si la jornada está cerrada). | Venta, cobro y recepción son eventos distintos: no incluye cobrado ni saldo. Avisa de equipos vendidos sin incorporar. |
| `resumen_financiero(ini, fin)` | Flujos del periodo: ventas netas, DEBE, HABER, liquidación, comisiones y "Resultado final del día". | Snapshot de las jornadas cerradas; `report` y `calculate` para las abiertas. | Definitivo (cerradas) y provisional (abiertas) van separados. Nunca suma bases de caja ni saldos. Sin fórmulas propias. |
| `estado_inventario()` | Equipos disponibles hoy, por ubicación y referencia. | Equipos `Disponible` no archivados. | Foto de hoy. Sin IMEI. Costo inmovilizado solo para el Propietario. |
| `creditos_pendientes()` | Saldo actual por aliado = neto − recibido. | Créditos Pendiente o Parcial de operaciones no anuladas. | Sin mora ni reconstrucción histórica. Sin clientes. Los no aprobados irían aparte (hoy la aprobación no se guarda como dato). |

### 3.2 `comparar_periodos(ini, fin)` — comparación, no predicción

- **Entradas:** `ini` y `fin` inclusivas. Un `fin` futuro se recorta a hoy con aviso; un periodo todo en el futuro o de más de 366 días se rechaza.
- **Método:** el periodo anterior es el **inmediatamente anterior y de igual duración** (mismo número de días): si el periodo es del 9 al 11, se
  compara con del 6 al 8. Se llama a `resumen_ventas` y `resumen_financiero` para los dos periodos.
  - *Ventas netas* = `venta_neta_cents` de `resumen_ventas`.
  - *Resultado final* = suma de los "Resultado final del día" (definitivo más provisional) de `resumen_financiero`.
- **Cobertura completa en AMBOS periodos o no se compara.** Cuenta como falta de cobertura: días sin jornada, equipos vendidos sin incorporar a
  Finanzas, un cierre que no trae o no coincide con la venta neta, o un resultado nulo en alguna jornada. Si falta, la comparación va como `null`
  (diferencia y porcentaje), con la razón y el periodo que falla en `advertencias`. El valor de un periodo con cobertura completa sí se informa.
- **Variación:** diferencia en centavos y variación en **puntos básicos enteros** (5000 = +50 %), con redondeo al más cercano y sin decimales
  flotantes. **No hay porcentaje** si el periodo anterior es cero o negativo (se informa solo la diferencia).
- **Provisional:** las jornadas abiertas se comparan pero se marcan `provisional` y la respuesta es `parcial`.
- **Marca:** `cifras.es_comparacion = true`, `es_prediccion = false`, y la primera advertencia y el `metodo` dicen "esto es una COMPARACIÓN … no es
  una predicción ni una estimación del futuro", también en `sin_datos`, `sin_autorizacion` y `error_temporal`.
- **Salidas:** `periodo` (con el periodo anterior), `cifras.ventas_netas` y `cifras.resultado_final` (cada una con `comparable`, `actual_cents`,
  `anterior_cents`, `diferencia_cents`, `variacion_bp`, `variacion_pct`, `provisional` y los motivos de falta de cobertura).

### 3.3 `permanencia_inventario(umbral_dias)` — cuánto llevan los equipos en inventario

- **Entrada:** `umbral_dias` (60 por defecto, constante `UMBRAL_PERMANENCIA_DIAS`; entero entre 1 y 3650).
- **Método:** para cada equipo `Disponible` no archivado, días = hoy − fecha de ingreso. La fecha de ingreso es la **del lote** o, si no tiene lote
  (retomas), la **de creación del equipo**: la misma regla que usa el consolidado contable. Un equipo es de **baja rotación** si lleva **más** de
  `umbral_dias` días (exactamente el umbral no cuenta).
- **Salidas:** cantidad disponible, con y sin fecha de ingreso válida, promedio, mediana y máximo de días, cuántos pasan el umbral; distribución por
  rangos (0–30, 31–60, 61–90, 91–180, más de 180); agrupación por referencia; y la **lista de equipos sobre el umbral** (id interno, referencia,
  ubicación, fecha de ingreso y días; hasta 200, con aviso si hay más). **Nunca el IMEI.**
- **Costo inmovilizado:** total, sobre el umbral, por rango, por referencia y por equipo, **solo** para quien está en `ROLES_CON_COSTO`; para los
  demás las claves ni existen.
- **Fechas dudosas:** una fecha de ingreso vacía, mal escrita o futura no se inventa: el equipo no cuenta en los días ni en el umbral, y la respuesta
  es `parcial` con el número de equipos afectados.
- **No predice:** mide lo que ya pasó. No dice cuándo se venderá un equipo.

## 4. Chat, reportes y pantallas (cómo llegan estas consultas al usuario)

- **Chat** (`/chat`): reglas fijas, sin modelo de lenguaje. Interpreta la intención y el periodo ("hoy", "esta semana", "del 1 al 15 de octubre"…),
  llama a la consulta y redacta con `redactar_respuesta`: importes en pesos con separador de miles, "provisional" cuando hay jornadas abiertas,
  advertencias y fuente. Lo que no entiende o intenta escribir, lo rechaza y lista lo que sí puede.
- **Reporte por periodo** (`/reportes/<módulo>`): selector de semana, 15 días, mes o rango en Ventas, Inventario y Finanzas, con CSV y enlaces a las
  exportaciones existentes.
- **Comparación y baja rotación en pantalla y chat:** el botón "Comparar con el periodo anterior" en los reportes de Ventas y de Finanzas, la lista de
  equipos de baja rotación en el reporte de Inventario y las intenciones del chat "comparar con el periodo anterior" y "baja rotación" usan las
  consultas de las secciones 3.2 y 3.3, sin cálculos propios. El botón y la pantalla avisan que es una comparación de periodos pasados, no una
  predicción. El umbral de baja rotación se elige en el panel del reporte de Inventario (por defecto 60 días) o en la pregunta del chat ("más de 90 días").
  El IMEI no se muestra: la lista enlaza al detalle del equipo. Solo el Propietario ve estas pantallas.
- Cada consulta del chat y de los reportes queda en `registro_gestion`.

## 5. Límites conocidos

1. **"Periodo anterior de igual duración" no es "mismo tramo equivalente".** La comparación usa los N días inmediatamente anteriores. Para un periodo
   cerrado (una semana completa, un mes completo) es exactamente lo esperado. Pero un periodo **en curso** se compara con un tramo que cae en otros días
   de la semana: la semana en curso de lunes a miércoles (3 días) se compara con viernes a domingo, no con el lunes a miércoles de la semana pasada.
   Además, los días con poca venta (domingos, festivos) pesan distinto en cada tramo. Una variación grande entre tramos desiguales puede deberse
   solo a eso. *Queda para después:* un modo "equivalente" que compare el mismo tramo del periodo anterior (lunes a miércoles contra lunes a
   miércoles de la semana pasada; días 1 a 11 de este mes contra días 1 a 11 del mes pasado; mismo periodo del año anterior). Falta definir con Emily
   qué es "equivalente" para cada tipo de periodo.
2. **La cobertura exige jornadas.** En la práctica, un periodo con domingos o festivos sin jornada nunca tendrá cobertura "completa" y la comparación
   saldrá `null`. Mientras no se defina qué días no laborales son normales (decisión pendiente de Emily), la aplicación prefiere no comparar a comparar
   con huecos.
3. **Lo provisional puede cambiar.** Los datos de una jornada abierta pueden cambiar al cerrar el día (comisiones, anulaciones).
4. **El inventario es una foto de hoy.** No hay inventario histórico: no se puede decir cuánto llevaban en inventario los equipos ya vendidos ni
   reconstruir el stock de una fecha pasada.
5. **La permanencia depende de la fecha de ingreso registrada.** Si el lote se registró tarde o la fecha está mal, los días salen mal; no se corrige.
6. **Sin mora.** `creditos_pendientes` informa el saldo actual, no su antigüedad ni vencimiento: no hay una fecha esperada de pago en los datos.
7. **Sueldos por persona fuera.** No existe un vínculo entre un pago de un periodo y la obligación de otro; por eso no se muestra saldo de sueldos y
   los sueldos no salen en el chat.
8. **Solo el Propietario** (hasta que Emily valide la matriz de roles del chat).
9. **Probado con SQLite.** Nada se ha ejecutado contra PostgreSQL; `BEGIN IMMEDIATE` y `PRAGMA` (fuera de la analítica) siguen siendo de SQLite.
10. **Los datos de prueba demuestran que el proceso funciona, no que acierte:** con registros de ejemplo no se puede juzgar la utilidad de ninguna cifra.

## 6. Qué queda para después

- `tendencia_ventas` (ventas por semana, tendencia y estimado simple de la siguiente semana) y `proyeccion_uvt` (cuándo se alcanzaría el tope de
  1.400 UVT al ritmo actual de consignaciones activas). Son estimaciones: llevarán `es_estimacion = true` y datos suficientes explícitos.
- Modo "mismo tramo equivalente" para la comparación (límite 1).
- Alertas configurables (inventario bajo, baja rotación) y recomendaciones por reglas, sin tablas nuevas salvo aprobación.
- Servidor MCP de solo lectura con las mismas consultas, sin escritura ni SQL libre.
- Predicción de demanda o utilidad con un modelo (sección 7).
- Rol Contador (hoy recibe el paquete descargado) y reportes programados.

## 7. Modelo predictivo futuro (diseño; no está implementado)

Hoy no hay ningún modelo entrenado. Cuando haya historial suficiente, se debe documentar y respetar lo siguiente antes de mostrar un solo pronóstico.

| Aspecto | Definición propuesta |
|---|---|
| **Variable a estimar** | Primero: **ventas netas por semana** (centavos), porque es lo que ya mide `resumen_ventas`. Después, por referencia: unidades vendidas por semana. La utilidad se deja para el final porque depende de reglas de liquidación y comisión. |
| **Historial requerido** | Al menos **26 semanas** (seis meses) con jornadas **cerradas** y al menos **90 % de los días laborales con jornada**; por referencia, al menos 8 semanas con ventas. Sin jornadas abiertas (provisionales), sin días sin jornada contados como cero y sin cambios de reglas del negocio dentro de la ventana, o se parte la serie en el cambio. |
| **Método de referencia (el que hay que superar)** | Dos líneas base simples y explicables: (1) **promedio móvil de las últimas 4 semanas** y (2) **semana anterior** (pronóstico ingenuo). Después, una **tendencia lineal** por mínimos cuadrados sobre 8 a 12 semanas. Un método más complejo solo se acepta si supera a estas líneas base con la misma evaluación. |
| **Separación temporal** | Nunca se mezcla al azar. Se entrena con las semanas hasta una fecha T y se evalúa en las semanas siguientes, **avanzando T semana a semana** (validación de origen móvil). Los parámetros se eligen con un tramo intermedio de validación; el tramo final de prueba no se toca hasta el final. |
| **Medida de error** | **MAE** (en pesos) y **sMAPE** (no se usa MAPE con ceros), más el error **relativo a la línea base** (por ejemplo MASE): si no mejora a la línea base, no se publica. El error medido se muestra junto a cada pronóstico. |
| **Respuesta con datos insuficientes** | Estado `sin_datos` (o `parcial` con el motivo): "hay N semanas utilizables y se necesitan 26"; **ninguna cifra**, ni siquiera aproximada. El pronóstico siempre dice que es una estimación, el horizonte (una semana) y el error histórico. |
| **Fuera de alcance al inicio** | Intervalos de confianza, predicción por ubicación o por modelo de equipo, recomendaciones de compra y acciones automáticas. |
| **Reglas que se mantienen** | La aplicación calcula; un modelo de lenguaje solo redacta. Solo valores agregados. Solo Propietario hasta validar los roles con Emily. |

## 8. Cómo se prueba

Todo se prueba con la suite automática (`$env:PYTHONPATH='tests'; python -m unittest discover -s tests`), con una base temporal de SQLite por prueba.

| Qué | Archivo | Ejemplos de pruebas |
|---|---|---|
| Contrato y estados de las consultas base | `tests/test_consulta_*.py` | `test_consulta_resumen_ventas.FuenteYCifrasTests.test_coincide_con_la_pantalla_de_finanzas`, `test_consulta_resumen_financiero.JornadaCerradaTests.test_el_snapshot_manda_sobre_el_calculo_actual`, `test_consulta_creditos_pendientes.EjemploDelPdfTests.test_bruto_650000_costo_18_neto_533000_y_abonos_hasta_saldo_cero`, `test_consulta_estado_inventario.EstadosTests.test_sin_datos_cuando_no_hay_equipos_registrados` |
| Comparación de periodos | `tests/test_analitica_comparar_periodos.py` | `test_analitica_comparar_periodos.ComparacionCompletaTests.test_el_periodo_anterior_es_el_inmediato_y_de_igual_duracion`, `test_analitica_comparar_periodos.ComparacionCompletaTests.test_redondeo_de_la_variacion`, `test_analitica_comparar_periodos.SinCoberturaTests.test_falta_cobertura_en_el_periodo_actual`, `test_analitica_comparar_periodos.SinCoberturaTests.test_ninguna_respuesta_sin_cobertura_trae_un_porcentaje`, `test_analitica_comparar_periodos.SinCoberturaTests.test_el_periodo_anterior_en_cero_no_da_porcentaje`, `test_analitica_comparar_periodos.ProvisionalTests.test_con_la_jornada_de_hoy_abierta_se_marca_provisional_y_es_parcial`, `test_analitica_comparar_periodos.EstadosYPermisosTests.test_sin_autorizacion_para_todo_perfil_distinto_del_propietario` |
| Permanencia del inventario | `tests/test_analitica_permanencia_inventario.py` | `test_analitica_permanencia_inventario.DiasYUmbralTests.test_sobre_el_umbral_significa_mas_dias_que_el_umbral`, `test_analitica_permanencia_inventario.DiasYUmbralTests.test_umbrales_invalidos`, `test_analitica_permanencia_inventario.FechaDeIngresoTests.test_la_fecha_del_lote_manda_sobre_la_de_creacion`, `test_analitica_permanencia_inventario.FechaDeIngresoTests.test_fechas_vacias_mal_escritas_o_futuras_no_se_inventan`, `test_analitica_permanencia_inventario.CostoYPrivacidadTests.test_quien_no_ve_costos_no_los_recibe_ni_una_clave`, `test_analitica_permanencia_inventario.CostoYPrivacidadTests.test_nunca_devuelve_imei_proveedor_ni_personas` |
| Chat y reportes | `tests/test_chat.py`, `tests/test_chat_pantalla.py`, `tests/test_reportes.py` | `test_chat.MismosTotalesTests.test_ventas`, `test_reportes.PermisosTests.test_solo_el_propietario_abre_los_reportes` |
| Comparación y baja rotación en pantalla y chat | `tests/test_analitica_pantalla.py` | `test_analitica_pantalla.ReporteCompararTests.test_ventas_y_finanzas_ofrecen_el_boton_con_el_aviso`, `test_analitica_pantalla.ReporteBajaRotacionTests.test_lista_los_equipos_sobre_el_umbral_sin_imei`, `test_analitica_pantalla.ChatTests.test_baja_rotacion_en_el_chat`, `test_analitica_pantalla.ChatTests.test_comparar_con_el_periodo_anterior_en_el_chat`, `test_analitica_pantalla.PoliticaTests.test_sin_scripts_ni_estilos_en_linea_en_las_pantallas_nuevas` |
| Permisos de todas las rutas | `tests/test_matriz_permisos.py`, `tests/test_accesos_directos.py` | `test_matriz_permisos.MatrizPermisos.test_toda_ruta_de_la_aplicacion_esta_clasificada` |

Las reglas de este documento que no tienen prueba propia están marcadas como límites o propuestas. `tests/test_analitica_doc.py` comprueba que cada prueba
citada aquí exista y que no falte ninguna sección.

## 9. Reglas de oro para quien siga ampliando la analítica

1. Primero una ficha (entradas, fuente exacta, reglas, salida, permisos, caso de prueba y qué valida Emily); después el código.
2. Reutilizar las consultas existentes; no inventar fórmulas de utilidad.
3. Sin cobertura, sin cifra: `null` y la razón.
4. Toda ruta nueva exige una capacidad y se clasifica en `tests/test_matriz_permisos.py`.
5. Nada de scripts en línea ni SQL propio de un motor de base de datos.
