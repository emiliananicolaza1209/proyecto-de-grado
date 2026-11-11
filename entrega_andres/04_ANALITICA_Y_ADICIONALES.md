# Base para analítica y desarrollos adicionales

## Primera capa de lectura
Preparar funciones reutilizables y, cuando convenga, vistas de lectura. No es obligatorio crear un almacén de datos separado ahora. Los siguientes nombres son propuestas, no tablas ya existentes.

| Conjunto | Una fila representa | Fuente | Uso |
|---|---|---|---|
| ventas_operaciones | Una operación de venta | finance_operation + finance_day | Ventas netas por día; cantidades de operaciones |
| cobros_cliente | Un cobro no anulado | customer_collection | Cobros por fecha efectiva; conciliación con créditos |
| recepciones_admin | Una recepción no anulada de cobro activo | admin_receipt + customer_collection | Entregas confirmadas, sin sumar de nuevo como ventas |
| resultado_jornada | Una jornada, con origen snapshot o provisional | finance_day + servicio report | Resultados y comparaciones por periodos |
| credito_actual | Un crédito con saldo actual | creditos_venta + operación | Pendientes por aliado |
| inventario_actual | Un equipo / artículo, en conjuntos distintos | equipment / movimientos_stock | Disponibilidad y alertas |

Primero agregar cada relación de varios registros (pagos, costos y aplicaciones) y después unirla. Un join directo de 2 pagos por 3 costos produce 6 filas y puede inflar importes. No resolverlo con SUM(DISTINCT amount): importes iguales pueden ser operaciones distintas.

## Consolidado adicional por fechas y conceptos
Registrar como desarrollo adicional, sin modificar las 86 historias originales.

- Filtros: desde/hasta inclusivos, concepto aprobado, persona o proveedor cuando corresponda.
- Cada variable debe indicar si es flujo (sumable por periodo), saldo a una fecha o porcentaje (no sumable).
- CP VARIOS: `report(...).totals.funds['CP VARIOS']` representa capital reservado en costos de ventas. No es automáticamente venta bruta de CP Varios. Definir etiquetas independientes para capital, ventas y utilidad.
- Originales: construir mapeo de categorías/artículos/proveedores por ID y aprobado por Emily. Evitar LIKE '%ORIGINAL%' como regla oficial.
- Sueldo en la misma jornada: `config.staff[].salary` con asistencia; pagos `kind='Pago sueldo'`, seller igual al nombre validado, voided=False. Mostrar limitación de identidad por nombre.
- Sandra: `sandra_sunday` participa en liquidación especial y `sandra_control_*` en control. Emily debe definir qué conceptos cuentan como obligación salarial; no sumarlos por compartir el nombre.

## Evolución de nómina propuesta (no aplicada)
Identidad estable de trabajador; obligación por persona, jornada y concepto; pago con fecha y medio; aplicación de pago a una o varias obligaciones. Así un pago de noviembre puede saldar obligaciones de octubre y se distingue fecha de causación de fecha de pago. Diseñar migración y clasificación de datos previos antes de crear tablas. No deducir automáticamente la identidad histórica de un nombre ambiguo.

## Analítica descriptiva para la siguiente etapa
- Comparación de periodos de igual duración y cobertura. Si el periodo anterior suma cero, variación porcentual no calculable; mostrar diferencia absoluta.
- Equipos disponibles por encima de un umbral de días, con fecha de ingreso validada. Llamarlo antigüedad/permanencia, no rotación completa de inventario.
- Créditos pendientes por aliado y distribución de tiempos hasta desembolso, si hay fechas suficientes.
- Fondos y resultados por día, distinguiendo valores provisionales y cierres.

## Predicción futura
Seleccionar una variable (por ejemplo unidades vendidas por semana y categoría), documentar origen, ausencias, devoluciones y cambios de catálogo; medir historial suficiente según frecuencia/estacionalidad. Comparar con un método básico, separar entrenamiento y evaluación por tiempo y medir error (por ejemplo MAE). No mezclar datos futuros en entrenamiento. Con datos sintéticos se prueba el flujo; no se demuestra precisión comercial. Mostrar “datos insuficientes” cuando corresponda.
