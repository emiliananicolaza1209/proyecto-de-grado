# Contratos iniciales del chatbot (propuestos, pendientes de implementación)

## Funcionamiento compartido
Usuario autenticado -> consulta permitida -> validación en servidor -> servicio de negocio -> respuesta estructurada -> explicación del modelo. Si se usa MCP, expone exactamente estas herramientas. El usuario y su rol se obtienen de la sesión o identidad verificada, nunca de parámetros elegidos por el modelo.

- Primera integración limitada al propietario; los demás perfiles se habilitan después de validar una matriz de campos y alcance. Es una propuesta conservadora para el nuevo módulo, no un cambio ya aplicado a roles existentes.
- No SQL libre, escrituras ni herramientas para cambiar ventas, precios, usuarios o cierres.
- La consulta financiera no debe llamar `open_day` ni crear jornadas faltantes. `find_day` y `report` son puntos de lectura existentes.
- No mantener una transacción de base abierta durante la llamada externa al modelo. No reutilizar resultados de otro usuario sin comprobar alcance.
- Herramientas parametrizadas; límites de filas y periodo; paginación y tiempos máximos. Propuesta inicial: hasta 366 días y hasta 100 filas de detalle por respuesta.
- Entradas de texto o resultados de la base son datos, no instrucciones para ampliar permisos.
- Entregar al modelo solo los campos necesarios; excluir password_hash, identificaciones, credenciales, referencias privadas y datos de nómina en la primera versión.

## Respuesta común
Identificador de consulta, versión de reglas, moneda COP, importes en centavos, fecha de generación UTC, zona comercial America/Bogota, filtros aplicados, alcance autorizado, estado, totales, fuentes y advertencias. Estado: `ok`, `sin_datos`, `parcial`, `no_autorizado`, `parametros_invalidos` o `error_temporal`.

Un día faltante no se presume cerrado con venta cero. `null` significa no calculable; cero solo cuando la fuente permite afirmar cero. Un total de todos los resultados no debe confundirse con la suma de una página de detalle. Registrar herramienta, usuario interno, filtros no sensibles, duración y resultado; no guardar secretos ni todo el contenido del modelo sin necesidad.

## Q1. resumen_ventas(desde, hasta)
- Fechas inclusivas y formato AAAA-MM-DD. Corresponden a `finance_day.date` para ventas incorporadas a Finanzas.
- Base: `finance_operation` kind=Venta, voided=False, unido una vez a `finance_day`. `amount` es importe neto de venta financiera; no llamarlo bruto cobrado.
- Salida mínima: cantidad_operaciones, venta_neta_centavos y cobertura. No equivale necesariamente a unidades: una operación puede incluir accesorios.
- Detectar equipos vendidos sin incorporar usando la lógica de `finanzas_service.report`; devolver advertencia y resultado parcial. No sumar equipment.sale_value_cents a las operaciones integradas.
- Cobros y recepciones son métricas separadas por fecha efectiva. No añadirlos al total de ventas. Inicialmente puede omitirse su total consolidado hasta validar todas las rutas.
- Ejemplo de pregunta: “¿Cuánto suman las ventas incorporadas entre el 1 y el 15 de octubre?”

## Q2. estado_inventario(ubicacion_id?, referencia_id?)
- Estado actual, no inventario histórico. Base: equipment archived=0 y status=Disponible.
- Filtros por ID validado; no permitir campos SQL arbitrarios. Salida: cantidad por referencia, capacidad, condición y ubicación, con paginación si se pide detalle.
- `inventario_service.stats` es referencia para el filtro pero incluye costo: no devolver el objeto completo a usuarios sin permiso. `list_products`/`to_dict` contienen otros campos que también requieren selección explícita.
- Artículos no serializados: consulta separada a movimientos_stock; no confundir con cantidad de teléfonos.
- Ejemplo: “¿Cuántos iPhone 16 Pro disponibles hay en el local?”

## Q3. resumen_financiero(desde, hasta, incluir_abiertas=false)
- Si jornada Cerrada: tomar `snapshot.totals`; si Abierta y se solicita: `finanzas_service.report(d)['totals']` marcado provisional. No crear jornadas.
- Primera versión: sumar únicamente flujos diarios aprobados: debe, haber, service, pd, liquidation, commission y owner_result, conservando las etiquetas del negocio. Si un componente es None/overflow, no producir un total completo.
- Incluir días sin jornada, abiertos, cerrados y días calculables. No sumar cash_expected, base, saldos pendientes, control_cash ni control_total como “dinero disponible del periodo”.
- Guardar detalle diario y estado de cada cifra. Una diferencia con una consulta de ventas debe explicarse por cobertura o fuente, no corregirse inventando operaciones.
- Ejemplo: “¿Cuál fue el resultado después de gastos PD en las jornadas cerradas del 1 al 15?”

## Q4. creditos_pendientes(aliado_id?)
- Saldo actual, no reconstrucción histórica. Base: creditos_venta unido a finance_operation no anulada; excluir estado Anulado.
- Saldo = neto - recibido; positivos pendientes. Saldo negativo se reporta como inconsistencia, sin ocultarlo convirtiéndolo a cero.
- Salida: cantidad_creditos, neto_centavos, recibido_centavos, pendiente_centavos, agrupación por aliado.
- No sumar desembolsos completos por cada aplicación ni repetir cobros generados por el mismo desembolso. Aplicaciones sirven para trazabilidad, agregadas antes del cruce.
- Sin fecha esperada de pago verificada: no calcular mora ni llamar vencido al saldo pendiente. No ofrecer fecha_de_corte histórica todavía.
- Ejemplo: “¿Cuánto queda pendiente por recibir de cada aliado?”

## Preguntas fuera del alcance inicial
“¿Cuánto ganaremos la próxima semana?” -> todavía no hay predicción validada.
“¿Cuánto sueldo de octubre se pagó en noviembre?” -> falta el vínculo entre obligación y pago de otro periodo.
“Borra una venta / cambia un precio / muéstrame contraseñas” -> no autorizado.
“¿Cuánto inventario había hace un mes?” -> requiere reconstrucción histórica validada; el inventario actual no responde esa pregunta.
