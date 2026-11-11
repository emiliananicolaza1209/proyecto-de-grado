# Lista de aceptación para la entrega del jueves 12 de noviembre de 2026

Documento de trabajo para probar la versión desplegada, con Emily. **No certifica** que las funciones estén terminadas: registra qué se
probó, quién lo validó y qué queda pendiente.

- **Rama:** `ia-analitica-contable`. **Versión desplegada (SHA del commit):** `________` · **URL:** `________`
- **Suite automática completa al 11-nov-2026:** `580` pruebas, todas en verde (`python -m unittest discover -s tests`, con `PYTHONPATH=tests`).
- **Cómo leer las columnas:**
  - *Resultado real*: si dice **AUTOMATIZADO**, lo cubre la suite y se cita el nombre exacto de la prueba (`archivo.Clase.método`); una prueba
    automática demuestra el comportamiento del código, **no** que la URL desplegada esté bien configurada. Si dice **MANUAL**, debe hacerse a mano
    con la URL real y anotar aquí lo observado.
  - *Quién validó*: nombre y fecha de quien lo vio con sus ojos. Para lo automatizado: "suite automática".
  - *Pendiente*: lo que falta aunque haya prueba automática.

Las pruebas automáticas usan una base temporal con SQLite. **Nada de esto se ha ejecutado contra PostgreSQL.** Todo lo marcado con (PG) debe
repetirse con la base real de Emily.

---

## A. Los 8 criterios de aceptación del plan (condiciones mínimas para aceptar la entrega desplegada)

### Criterio 1 — Acceso por HTTPS, sin depuración activa y con claves fuera del repositorio

| Caso | Resultado esperado | Resultado real | Quién validó | Pendiente |
|---|---|---|---|---|
| A1.1 Entrar desde los dos computadores | La URL empieza con `https://`, el certificado es válido y `http://` redirige a HTTPS o no responde. | **MANUAL** | | Emily: certificado y redirección. |
| A1.2 Cookie de sesión | Con `SESSION_COOKIE_SECURE=1` la cookie es `Secure`, `HttpOnly` y `SameSite=Lax`. | **AUTOMATIZADO** `test_seguridad_sesion.ConfiguracionTests.test_secure_se_activa_por_variable_de_entorno`, `test_seguridad_sesion.ConfiguracionTests.test_secure_se_activa_por_configuracion`, `test_seguridad_sesion.ConfiguracionTests.test_cookie_httponly_samesite_y_sin_secure_por_defecto` | Suite automática | Confirmar en el navegador (Herramientas de desarrollo → Aplicación → Cookies) que la variable está definida en el servidor. |
| A1.3 Cabeceras de seguridad | Todas las respuestas llevan `X-Frame-Options`, `nosniff`, `Referrer-Policy` y la política de contenido, sin scripts en línea. | **AUTOMATIZADO** `test_seguridad_cabeceras.CabecerasTests.test_todas_las_respuestas_llevan_las_cabeceras`, `test_seguridad_cabeceras.CabecerasTests.test_politica_estricta_donde_importa`, `test_seguridad_cabeceras.CabecerasTests.test_el_sitio_no_usa_nada_que_la_politica_bloquee` | Suite automática | Ver en el navegador que la consola no muestra bloqueos de la política y que el proxy del alojamiento no quita las cabeceras. |
| A1.4 Sin depuración | El servidor arranca sin modo de depuración; un error en la URL no muestra el depurador ni trazas. | **AUTOMATIZADO** `test_aceptacion.AceptacionTests.test_arranque_sin_depuracion`, `test_accesos_directos.ErroresSinTrazaTests.test_los_errores_no_muestran_trazas_ni_rutas_del_servidor` | Suite automática | **MANUAL**: abrir `/inventario/compras/999999` y `/console` en la URL real; debe salir 404 sin depurador. |
| A1.5 Claves fuera del repositorio | `.env` no está versionado, el código no trae `SECRET_KEY` ni claves escritas, y los scripts de respaldo no leen ni guardan claves. | **AUTOMATIZADO** `test_aceptacion.AceptacionTests.test_el_repositorio_no_trae_claves_ni_env`, `test_respaldo.CodigoYDocumentacionTests.test_los_scripts_nunca_leen_ni_guardan_claves` | Suite automática | **MANUAL**: confirmar en el panel del servicio que `SECRET_KEY` y la URL de la base están como variables de entorno; rotar cualquier clave que se haya compartido en chats o documentos. |
| A1.6 Dirección del cliente tras el proxy | El límite de intentos de acceso cuenta por la IP real de cada persona, no por la del proxy. | **MANUAL** | | Emily: configurar el reenvío de la IP (ProxyFix o equivalente). Sin esto, todos comparten el mismo límite. |

### Criterio 2 — Permisos comprobados en servidor (enlaces directos, reportes, adjuntos y chatbot)

| Caso | Resultado esperado | Resultado real | Quién validó | Pendiente |
|---|---|---|---|---|
| A2.1 Matriz de rutas por rol | Cada ruta y cada acción de escritura solo la usan los perfiles previstos; una ruta nueva sin clasificar hace fallar la suite. | **AUTOMATIZADO** `test_matriz_permisos.MatrizPermisos.test_cada_ruta_tiene_los_permisos_esperados`, `test_matriz_permisos.MatrizPermisos.test_toda_ruta_de_la_aplicacion_esta_clasificada`, `test_matriz_permisos.MatrizPermisos.test_las_acciones_de_escritura_no_quedan_abiertas_al_socio`, `test_matriz_permisos.MatrizPermisos.test_nada_responde_sin_sesion` | Suite automática | Emily valida que la matriz refleje las reglas vigentes del negocio. |
| A2.2 Enlaces directos con ID | Con ID real o inventado, nunca un 500, y quien no tiene permiso recibe lo mismo (no se puede adivinar qué existe). | **AUTOMATIZADO** `test_accesos_directos.RutasConIdTests.test_ninguna_ruta_con_id_da_500_con_ningun_perfil`, `test_accesos_directos.RutasConIdTests.test_quien_no_puede_ver_una_ruta_recibe_lo_mismo_exista_o_no_el_recurso` | Suite automática | |
| A2.3 Exportaciones y descargas | CSV de Finanzas, consolidado y paquete del contador (Excel y PDF), plantilla de lotes y reportes: solo para el perfil permitido; los demás no reciben el archivo ni con HEAD. | **AUTOMATIZADO** `test_accesos_directos.DescargasYExportacionesTests.test_el_perfil_permitido_descarga_y_los_demas_no_reciben_el_archivo`, `test_accesos_directos.DescargasYExportacionesTests.test_head_nunca_entrega_el_contenido_a_quien_no_tiene_permiso`, `test_accesos_directos.DescargasYExportacionesTests.test_las_descargas_sensibles_no_se_guardan_en_cache` | Suite automática | |
| A2.4 Facturas adjuntas | Solo Propietario, Administrador e Inventario; el nombre en la URL no permite salir de la carpeta; se entregan como descarga. | **AUTOMATIZADO** `test_accesos_directos.FacturasTests.test_quien_tiene_permiso_recibe_el_archivo_exacto_como_descarga`, `test_accesos_directos.FacturasTests.test_los_demas_perfiles_y_los_anonimos_no_reciben_ni_un_byte`, `test_accesos_directos.FacturasTests.test_el_nombre_en_la_url_no_permite_salir_de_la_carpeta`, `test_accesos_directos.FacturasTests.test_un_nombre_raro_guardado_en_la_base_tampoco_sale_de_la_carpeta`, `test_accesos_directos.FacturasTests.test_la_carpeta_de_facturas_no_se_sirve_por_el_estatico` | Suite automática | **MANUAL**: subir una factura real en la URL y descargarla con un usuario de cada rol. |
| A2.5 Chat y reportes | Solo el Propietario; los demás no reciben cifras ni siquiera con una consulta habilitada por configuración. | **AUTOMATIZADO** `test_accesos_directos.ChatYReportesPorPerfilTests.test_solo_el_propietario_usa_el_chat_y_los_reportes`, `test_accesos_directos.ChatYReportesPorPerfilTests.test_ni_siquiera_con_una_consulta_habilitada_se_filtran_las_otras`, `test_chat.RutaTests.test_solo_el_propietario_entra`, `test_reportes.PermisosTests.test_solo_el_propietario_abre_los_reportes` | Suite automática | Emily decide cuándo habilitar otros perfiles (matriz de roles del chat). |
| A2.6 Costos y utilidades | La Vendedora no recibe costos ni utilidades en ninguna respuesta; el servidor toma el costo del inventario. | **AUTOMATIZADO** `test_seguridad_costos.FugaDeCostosTests.test_vendedora_no_recibe_bloques_de_costos_ni_cifras_en_finanzas`, `test_seguridad_costos.FugaDeCostosTests.test_vendedora_no_ve_costos_en_ventas_ni_creditos`, `test_seguridad_costos.FugaDeCostosTests.test_vendedora_vende_y_el_servidor_toma_el_costo_de_inventario` | Suite automática | Ver "Código fuente de la página" de `/finanzas` como Vendedora en la URL real. |
| A2.7 Socio e Inventario | El Socio solo ve lo suyo; Inventario ve equipos por ubicación, sin capital de los socios. | **AUTOMATIZADO** `test_seguridad_costos.FugaDeCostosTests.test_socio_solo_recibe_cifras_de_su_participacion`, `test_seguridad_inversion.InversionPorRolTests.test_inventario_solo_ve_equipos_por_ubicacion`, `test_seguridad_inversion.InversionPorRolTests.test_socio_sigue_viendo_solo_lo_suyo` | Suite automática | |
| A2.8 Los 5 perfiles con la URL real | Cada perfil entra y solo ve lo suyo; teclear a mano URLs ajenas da 403 o lo devuelve a su página. | **MANUAL** | | Completar con Emily con usuarios reales. |
| A2.9 Lectura de créditos por la Vendedora (pendiente 7) | Decidir si la Vendedora puede leer `/finanzas/creditos`. | **DECISIÓN PENDIENTE** (ver `docs/SEGURIDAD.md`) | | Decisión del propietario/Emily. |

### Criterio 3 — Validación de formularios, protección de sesiones y control de intentos de acceso

| Caso | Resultado esperado | Resultado real | Quién validó | Pendiente |
|---|---|---|---|---|
| A3.1 CSRF | Todo formulario exige el token; sin él, 400. | **AUTOMATIZADO** `test_finanzas.FinanceTests.test_duplicate_invalid_money_csrf_and_stale`, `test_catalogs.CatalogTests.test_pages_and_csrf`, `test_chat.RutaTests.test_sin_csrf_es_400` | Suite automática | |
| A3.2 Importes inválidos y datos obsoletos | Importes mal escritos y formularios con una revisión vieja se rechazan sin guardar nada. | **AUTOMATIZADO** `test_mod03.MoneyTests.test_invalid_payments_and_stale_revision`, `test_actions.ActionsTests.test_stale_invalid_and_duplicate_are_atomic` | Suite automática | |
| A3.3 Parámetros raros | Ninguna ruta da 500 con parámetros o formularios basura; los errores no muestran trazas. | **AUTOMATIZADO** `test_accesos_directos.ErroresSinTrazaTests.test_ninguna_ruta_get_da_500_con_parametros_raros`, `test_accesos_directos.ErroresSinTrazaTests.test_ninguna_ruta_post_da_500_con_formularios_basura`, `test_accesos_directos.ErroresSinTrazaTests.test_los_errores_no_muestran_trazas_ni_rutas_del_servidor` | Suite automática | |
| A3.4 Expiración de sesión | A los 30 minutos sin actividad (configurable) pide acceso de nuevo; editar o desactivar al usuario cierra su sesión. | **AUTOMATIZADO** `test_seguridad_sesion.InactividadTests.test_tras_la_inactividad_pide_acceso_de_nuevo`, `test_seguridad_sesion.InactividadTests.test_con_actividad_la_sesion_sigue_viva`, `test_seguridad_sesion.ConfiguracionTests.test_editar_o_desactivar_al_usuario_si_invalida_la_sesion`, `test_gestion_v16.GestionTests.test_auth_role_server_blocks_and_invalidates_sessions` | Suite automática | **MANUAL**: dejar una sesión inactiva en la URL real. Limitación conocida: cerrar sesión no invalida una copia robada de la cookie (`test_seguridad_sesion.ConfiguracionTests.test_limitacion_documentada_sin_invalidacion_en_servidor`). |
| A3.5 Límite de intentos | 5 fallos por usuario y red, 20 por red; los fallos quedan auditados sin la clave. | **AUTOMATIZADO** `test_seguridad_intentos.IntentosTests.test_cinco_fallos_del_mismo_usuario_bloquean_el_sexto`, `test_seguridad_intentos.IntentosTests.test_veinte_fallos_desde_una_red_bloquean_a_todos_sus_usuarios`, `test_seguridad_intentos.IntentosTests.test_cada_fallo_queda_en_la_auditoria_sin_la_clave` | Suite automática | Los contadores viven en la memoria del proceso: con varios procesos o reinicios se pierden (limitación documentada). |
| A3.6 Contraseñas | Mínimo 12 caracteres y sin claves comunes ni que contengan el usuario o el nombre. | **AUTOMATIZADO** `test_seguridad_claves.ValidadorTests.test_minimo_de_doce_caracteres`, `test_seguridad_claves.UsuariosRutaTests.test_crear_usuario_con_clave_comun_se_rechaza_y_no_crea_nada` | Suite automática | |
| A3.7 No se puede adivinar qué usuarios existen | Mismo mensaje y mismo trabajo de cálculo exista o no el usuario. | **AUTOMATIZADO** `test_accesos_directos.TiempoDeAccesoTests.test_siempre_se_calcula_exactamente_un_hash`, `test_accesos_directos.TiempoDeAccesoTests.test_la_respuesta_es_identica_exista_o_no_el_usuario`, `test_accesos_directos.TiempoDeAccesoTests.test_el_tiempo_no_delata_al_usuario_inexistente` | Suite automática | |
| A3.8 Bloqueo y sesión en la URL real | Cinco fallos seguidos bloquean 5 minutos; la sesión caduca. | **MANUAL** | | Hacer la prueba del bloqueo al final con un usuario que no se necesite. |

### Criterio 4 — Datos y archivos conservados después de reiniciar o desplegar

| Caso | Resultado esperado | Resultado real | Quién validó | Pendiente |
|---|---|---|---|---|
| A4.1 Base conservada tras reiniciar | Registrar una venta, reiniciar el servicio y comprobar que sigue ahí. | **MANUAL** (apoyo: `test_migracion_union.BaseConEsquemaDeAndres.test_segunda_migracion_no_cambia_nada`, `test_migracion_union.BaseConEsquemaDeDesarrollo.test_v17_y_v18_son_idempotentes`) | | (PG) Emily. Las migraciones repetidas no cambian ni duplican datos. |
| A4.2 Facturas conservadas | Adjuntar una factura, desplegar de nuevo y descargarla. | **MANUAL** | | **Riesgo:** las facturas se guardan en `instance/facturas` del servidor; sin disco persistente se pierden en cada despliegue o reinicio aunque la base esté a salvo. Emily confirma el disco. |
| A4.3 La aplicación abre una base restaurada | La base restaurada arranca la aplicación con las mismas cifras. | **AUTOMATIZADO** `test_respaldo.RestaurarTests.test_la_aplicacion_abre_la_base_restaurada_con_las_mismas_cifras` | Suite automática | |
| A4.4 Paso a PostgreSQL | Conteos por tabla y totales de control iguales antes y después de migrar. | **MANUAL** (PG) | | Emily; el script de respaldo PostgreSQL puede servir de apoyo pero está sin probar. |

### Criterio 5 — Copia de base de datos y soportes; restauración probada en un entorno separado

| Caso | Resultado esperado | Resultado real | Quién validó | Pendiente |
|---|---|---|---|---|
| A5.1 Copia con fecha y hora y su ficha | Carpeta `cpstore_AAAAMMDD_HHMMSS` con base, soportes y `verificacion.json` (esquema, conteos, totales de control, huellas). | **AUTOMATIZADO** `test_respaldo.CopiarTests.test_la_copia_se_llama_con_fecha_y_hora_y_trae_base_soportes_y_verificacion`, `test_respaldo.CopiarTests.test_la_verificacion_trae_esquema_conteos_controles_y_huellas`, `test_respaldo.CopiarTests.test_la_copia_es_consistente_aunque_haya_una_escritura_sin_terminar` | Suite automática | |
| A5.2 Sin claves | La copia no incluye `.env`, claves ni `SECRET_KEY`, y lo avisa. | **AUTOMATIZADO** `test_respaldo.CopiarTests.test_no_copia_env_claves_ni_secret_key_y_lo_avisa` | Suite automática | |
| A5.3 Restauración verificada | Se restaura en una ruta nueva y se verifican `integrity_check`, conteos, totales de control y huellas. | **AUTOMATIZADO** `test_respaldo.RestaurarTests.test_restaura_en_una_ruta_nueva_y_verifica_todo`, `test_respaldo.RestaurarTests.test_los_totales_restaurados_son_los_de_antes` | Suite automática | |
| A5.4 Casos de fallo | Destino existente o copia dañada: error claro y nada a medias. | **AUTOMATIZADO** `test_respaldo.RestaurarTests.test_se_niega_si_el_destino_ya_existe_y_no_toca_nada`, `test_respaldo.CopiaDaniadaTests.test_base_con_bytes_cambiados`, `test_respaldo.CopiaDaniadaTests.test_conteos_que_no_coinciden_tras_restaurar_se_detectan_y_se_deshace`, `test_respaldo.CopiarTests.test_un_fallo_a_la_mitad_no_deja_archivos_a_medias` | Suite automática | |
| A5.5 Restauración real en un entorno separado | Copiar la base del servicio, restaurarla en otro lugar y comparar las cifras con la pantalla. | **MANUAL** (guía: `docs/RECUPERACION.md`) | | (PG) La variante de PostgreSQL está **sin probar**: probarla en una base de ensayo antes de depender de ella. |
| A5.6 Copia fuera del disco del servidor | Existe al menos una copia reciente en otro disco o lugar. | **MANUAL** | | Definir responsable y frecuencia (diaria al cierre, semanal fuera del servidor). |

### Criterio 6 — Pruebas de venta, cobro, cierre y consulta sin duplicaciones, incluyendo acceso simultáneo

| Caso | Resultado esperado | Resultado real | Quién validó | Pendiente |
|---|---|---|---|---|
| A6.1 Equipo → venta → cobro → Finanzas → cierre | El flujo completo se registra una sola vez y el cierre guarda su snapshot. | **AUTOMATIZADO** `test_finanzas.FinanceTests.test_close_snapshot_and_reopen`, `test_gestion_v16.GestionTests.test_financed_equipment_partial_then_full_no_duplicate_bank`, `test_consulta_resumen_ventas.CierreYCoberturaTests.test_jornada_cerrada_usa_su_snapshot_como_definitivo` | Suite automática | **MANUAL**: repetir el flujo en la URL real. |
| A6.2 El mismo registro enviado dos veces | La segunda vez se rechaza; no hay filas duplicadas. | **AUTOMATIZADO** `test_finanzas.FinanceTests.test_duplicate_invalid_money_csrf_and_stale`, `test_actions.ActionsTests.test_stale_invalid_and_duplicate_are_atomic`, `test_gestion_v16.GestionTests.test_reject_overpayment_duplicate_reference_and_wrong_bank` | Suite automática | |
| A6.3 Retoma, POOL y crédito sin duplicar | Una retoma no se reutiliza; el desembolso de un crédito no repite la venta ni la utilidad. | **AUTOMATIZADO** `test_gestion_v16.GestionTests.test_retoma_duplicate_within_sale_and_non_sale_rejected`, `test_gestion_v16.GestionTests.test_pool_purchase_from_jornada_is_not_sale_and_rejects_duplicate`, `test_consulta_creditos_pendientes.ExclusionesTests.test_el_desembolso_no_aparece_como_venta_ni_utilidad` | Suite automática | |
| A6.4 Consignaciones vinculadas | Editar o anular una transferencia no deja consignaciones duplicadas. | **AUTOMATIZADO** `test_pool_consignment.LinkedConsignmentTests.test_transferencia_edicion_anulacion_y_sin_duplicados` | Suite automática | |
| A6.5 Pantalla, reporte y chat dicen lo mismo | Las mismas cifras en las tres. | **AUTOMATIZADO** `test_chat.MismosTotalesTests.test_ventas`, `test_chat.MismosTotalesTests.test_financiero_coincide_con_finanzas_y_la_consulta`, `test_reportes.PanelYRutaTests.test_la_pantalla_dice_lo_mismo_que_el_chat` | Suite automática | |
| A6.6 Acceso simultáneo desde dos computadores | Dos personas guardan la misma venta o el mismo cierre a la vez: una se guarda y la otra recibe "recarga la página", sin duplicar. | **MANUAL** | | **Crítico (PG):** el código usa `BEGIN IMMEDIATE` (propio de SQLite) en `finanzas_routes.py` y `gestion_routes.py`; en PostgreSQL esa orden falla. Emily debe resolverlo y repetir esta prueba. |

### Criterio 7 — Escenarios no soportados bloqueados, errores comprensibles y trazabilidad

| Caso | Resultado esperado | Resultado real | Quién validó | Pendiente |
|---|---|---|---|---|
| A7.1 Anular ventas con dinero o con jornada cerrada | Se bloquea con una explicación. | **AUTOMATIZADO** `test_modules.ModuleTests.test_reverse_sale_refuses_active_money`, `test_modules.ModuleTests.test_reverse_sale_refuses_closed_finance_day` | Suite automática | |
| A7.2 Disolución y reversión de lotes | No se pueden saltar las reglas. | **AUTOMATIZADO** `test_gestion_v16.GestionTests.test_restore_cannot_bypass_dissolution_or_lot_reversal`, `test_gestion_v16.GestionTests.test_dissolution_equipment_requires_compensation` | Suite automática | |
| A7.3 Ediciones que no se soportan | Una venta en efectivo no puede ganar un crédito; una compra POOL no se edita como movimiento diario. | **AUTOMATIZADO** `test_gestion_v16.GestionTests.test_existing_cash_sale_cannot_gain_an_untracked_credit_on_edit`, `test_gestion_v16.GestionTests.test_pool_purchase_cannot_be_edited_as_a_daily_movement` | Suite automática | Emily completa la lista de escenarios no soportados con su explicación. |
| A7.4 Errores comprensibles | Mensajes claros, sin trazas; el chat dice que no puede y qué sí puede. | **AUTOMATIZADO** `test_accesos_directos.ErroresSinTrazaTests.test_los_errores_no_muestran_trazas_ni_rutas_del_servidor`, `test_chat.FueraDeAlcanceTests.test_no_escribe_ni_corrige`, `test_chat.EstadosSinFiltrarCifrasTests.test_sin_datos_tiene_su_mensaje` | Suite automática | |
| A7.5 Trazabilidad | Quedan registrados quién, cuándo y qué: accesos fallidos, consultas del chat, reportes y descargas del contador. | **AUTOMATIZADO** `test_seguridad_intentos.IntentosTests.test_cada_fallo_queda_en_la_auditoria_sin_la_clave`, `test_chat.RegistroTests.test_cada_consulta_queda_en_registro_gestion`, `test_reportes.GenerarTests.test_cada_consulta_deja_una_fila_en_registro_sin_cifras`, `test_paquete_contador.PaqueteRutasTests.test_cada_descarga_deja_quien_cuando_y_formato` | Suite automática | |

### Criterio 8 — URL, versión de código, evidencias y lista de pendientes entregadas

| Caso | Resultado esperado | Resultado real | Quién validó | Pendiente |
|---|---|---|---|---|
| A8.1 URL y versión | URL entregada y SHA del commit desplegado anotado arriba. | **MANUAL** | | Completar al desplegar. |
| A8.2 Suite completa | Todas las pruebas en verde con el código que se despliega. | **MANUAL** (ejecutar `python -m unittest discover -s tests` con el commit exacto que se despliega y anotar aquí el resultado) | | Repetirla también contra PostgreSQL cuando exista esa rama (PG). |
| A8.3 Casos ejecutados | Este documento con "resultado real" y "quién validó" llenos. | **MANUAL** | | |
| A8.4 Pendientes y límites conocidos | Lista entregada junto con la versión. | **AUTOMATIZADO** (existe y está al día) `test_accesos_directos.DocumentacionTests.test_seguridad_marca_8_y_9_como_corregidos_y_deja_el_7_pendiente`, `test_respaldo.CodigoYDocumentacionTests.test_la_documentacion_cubre_lo_pedido` | Suite automática | Ver la sección D de este documento. |
| A8.5 Copia previa al despliegue | Existe una copia verificada justo antes de desplegar. | **MANUAL** | | Hacerla con `scripts/respaldo.py copiar` y anotar el nombre de la carpeta. |

---

## B. Los 16 casos de las cuatro consultas (4 por consulta)

Son los casos de las fichas de diseño. **Los 16 casos de aceptación del paquete técnico de Emily (el ZIP) no están en el repositorio**: hay que
contrastar estos con los suyos y anotar las diferencias aquí.

| Caso | Resultado esperado | Resultado real | Quién validó | Pendiente |
|---|---|---|---|---|
| **estado_inventario** EI-1 | Cuenta solo equipos disponibles no archivados y coincide con el Resumen. | **AUTOMATIZADO** `test_consulta_estado_inventario.ContratoYCifrasTests.test_solo_cuenta_disponibles_no_archivados`, `test_consulta_estado_inventario.ContratoYCifrasTests.test_coincide_con_el_resumen_del_sistema` | Suite automática | |
| EI-2 | Filtros por ID de ubicación y referencia; IDs inválidos rechazados. | **AUTOMATIZADO** `test_consulta_estado_inventario.ContratoYCifrasTests.test_filtros_por_id`, `test_consulta_estado_inventario.ContratoYCifrasTests.test_filtros_invalidos_lanzan_parametro_invalido` | Suite automática | |
| EI-3 | Sin equipos: sin datos; equipos sin catálogo: parcial; nunca IMEI. | **AUTOMATIZADO** `test_consulta_estado_inventario.EstadosTests.test_sin_datos_cuando_no_hay_equipos_registrados`, `test_consulta_estado_inventario.EstadosTests.test_parcial_si_hay_equipos_sin_ubicacion_o_referencia`, `test_consulta_estado_inventario.ContratoYCifrasTests.test_no_devuelve_imei_ni_datos_de_personas` | Suite automática | Emily: ¿una retoma puede registrarse sin ubicación de catálogo? |
| EI-4 | Sin autorización o con error temporal: sin cifras. | **AUTOMATIZADO** `test_consulta_estado_inventario.PermisosTests.test_sin_autorizacion_para_todo_perfil_distinto_del_propietario`, `test_consulta_estado_inventario.EstadosTests.test_error_temporal_de_la_base_no_devuelve_cifras_y_la_sesion_sigue_usable` | Suite automática | Emily: ¿"disponible" incluye En pasamano y Separado como comprometido? |
| **creditos_pendientes** CP-1 | Ejemplo del plan: bruto $650.000, costo 18 % = $117.000, neto $533.000; con abonos de $200.000 y $333.000 el saldo llega a $0. | **AUTOMATIZADO** `test_consulta_creditos_pendientes.EjemploDelPdfTests.test_bruto_650000_costo_18_neto_533000_y_abonos_hasta_saldo_cero` | Suite automática | |
| CP-2 | Saldo por aliado y total; filtro por aliado. | **AUTOMATIZADO** `test_consulta_creditos_pendientes.ContratoYAgrupacionTests.test_saldo_por_aliado_y_total`, `test_consulta_creditos_pendientes.ContratoYAgrupacionTests.test_filtro_por_aliado` | Suite automática | |
| CP-3 | Anulados fuera del saldo; sin aprobación aparte; saldo inconsistente = nulo. | **AUTOMATIZADO** `test_consulta_creditos_pendientes.ExclusionesTests.test_creditos_anulados_y_operaciones_anuladas_no_suman`, `test_consulta_creditos_pendientes.AprobacionTests.test_credito_sin_aprobacion_va_aparte_y_fuera_del_saldo`, `test_consulta_creditos_pendientes.EstadosYPermisosTests.test_parcial_si_hay_saldo_inconsistente_y_el_valor_es_null` | Suite automática | Emily: hoy la aprobación no se guarda como dato; decidir si se guarda. |
| CP-4 | Sin créditos: sin datos; sin autorización: nada; sin mora ni clientes. | **AUTOMATIZADO** `test_consulta_creditos_pendientes.EstadosYPermisosTests.test_sin_datos_si_nunca_se_registro_un_credito`, `test_consulta_creditos_pendientes.EstadosYPermisosTests.test_sin_autorizacion_no_revela_nada`, `test_consulta_creditos_pendientes.SinMoraNiClientesTests.test_sin_mora_ni_antiguedad_ni_vencimiento` | Suite automática | |
| **resumen_ventas** RV-1 | Venta neta = "Ventas netas" de Finanzas; coincide con Información contable cuando solo hay equipos. | **AUTOMATIZADO** `test_consulta_resumen_ventas.FuenteYCifrasTests.test_coincide_con_la_pantalla_de_finanzas`, `test_consulta_resumen_ventas.FuenteYCifrasTests.test_coincide_con_informacion_contable_cuando_solo_hay_equipos` | Suite automática | |
| RV-2 | Desglose equipos y complementarias; la diferencia con el consolidado es exactamente las complementarias. | **AUTOMATIZADO** `test_consulta_resumen_ventas.FuenteYCifrasTests.test_desglose_equipos_y_complementarias_suma_el_total`, `test_consulta_resumen_ventas.FuenteYCifrasTests.test_diferencia_con_el_consolidado_es_exactamente_las_complementarias` | Suite automática | Emily: ¿las complementarias entran en "ventas"? |
| RV-3 | Anuladas fuera; equipos por incorporar avisados; abiertas provisionales; días sin jornada = cobertura incompleta. | **AUTOMATIZADO** `test_consulta_resumen_ventas.AnuladasTests.test_una_operacion_anulada_no_suma`, `test_consulta_resumen_ventas.PorIncorporarTests.test_avisa_de_equipos_vendidos_sin_operacion_y_no_los_suma`, `test_consulta_resumen_ventas.CierreYCoberturaTests.test_jornada_abierta_va_como_provisional_separada_del_definitivo`, `test_consulta_resumen_ventas.CierreYCoberturaTests.test_dias_sin_jornada_son_cobertura_incompleta_no_cero` | Suite automática | |
| RV-4 | Sin datos, sin autorización, error temporal y periodo inválido tienen su respuesta. | **AUTOMATIZADO** `test_consulta_resumen_ventas.EstadosYPermisosTests.test_sin_datos_si_no_hay_jornadas_ni_equipos_por_incorporar`, `test_consulta_resumen_ventas.EstadosYPermisosTests.test_sin_autorizacion_para_todo_perfil_distinto_del_propietario`, `test_consulta_resumen_ventas.EstadosYPermisosTests.test_error_temporal_de_la_base`, `test_consulta_resumen_ventas.PeriodoTests.test_fechas_invalidas` | Suite automática | |
| **resumen_financiero** RF-1 | Jornada abierta con `report` y `calculate`, sin fórmulas nuevas. | **AUTOMATIZADO** `test_consulta_resumen_financiero.JornadaAbiertaTests.test_abierta_usa_report_y_calculate_sin_formulas_nuevas` | Suite automática | |
| RF-2 | Jornada cerrada usa su snapshot; abiertas y cerradas van separadas. | **AUTOMATIZADO** `test_consulta_resumen_financiero.JornadaCerradaTests.test_cerrada_usa_su_snapshot_como_definitivo`, `test_consulta_resumen_financiero.JornadaCerradaTests.test_el_snapshot_manda_sobre_el_calculo_actual`, `test_consulta_resumen_financiero.JornadaCerradaTests.test_definitivo_y_provisional_van_separados_en_un_periodo_mixto` | Suite automática | Emily: qué significa "soportado" y cómo tratar una jornada abierta. |
| RF-3 | Un día con valor nulo o una clave ausente en un snapshot antiguo deja esa cifra en null con la fecha; días sin jornada = cobertura incompleta. | **AUTOMATIZADO** `test_consulta_resumen_financiero.ValoresNulosTests.test_un_dia_con_null_hace_null_esa_cifra_del_total_con_la_fecha`, `test_consulta_resumen_financiero.ValoresNulosTests.test_clave_ausente_en_un_snapshot_antiguo_es_null_con_la_fecha`, `test_consulta_resumen_financiero.CoberturaYEstadosTests.test_dias_sin_jornada_son_cobertura_incompleta_no_cero` | Suite automática | |
| RF-4 | Solo flujos (nunca bases de caja ni saldos); "Resultado final del día" no es el margen bruto de Información contable; solo Propietario. | **AUTOMATIZADO** `test_consulta_resumen_financiero.SoloFlujosTests.test_nunca_suma_ni_muestra_bases_de_caja_ni_saldos`, `test_consulta_resumen_financiero.RotuloYDiferenciaTests.test_el_resultado_del_dia_difiere_del_margen_bruto_por_definicion_no_por_error`, `test_consulta_resumen_financiero.PermisosYPrivacidadTests.test_sin_autorizacion_para_todo_perfil_distinto_del_propietario` | Suite automática | |

**Comprobación manual de las 4 consultas con la URL real (chat):** abrir `/chat` como Propietario y pulsar los cuatro botones; comparar cada cifra
con la pantalla de su módulo (Ventas, Inventario, Finanzas) y con el reporte por periodo. Resultado: `________` · Validó: `________`

---

## C. Casos manuales con la URL desplegada (para completar con Emily)

| Caso | Resultado esperado | Resultado real | Quién validó | Pendiente |
|---|---|---|---|---|
| C1 Ingreso desde el computador 1 y el 2 | Los cinco perfiles entran con su usuario; cada uno ve su menú. | | | |
| C2 Crear un equipo, venderlo, cobrarlo y cerrar la jornada | Cada paso aparece una sola vez en Inventario, Ventas, Finanzas y el cierre. | | | |
| C3 Venta a crédito y desembolso del aliado | El saldo pendiente baja con cada abono; la utilidad no se repite. | | | |
| C4 Retoma como parte de pago | La retoma entra como equipo del POOL y no se puede reutilizar. | | | |
| C5 Misma venta guardada desde dos computadores a la vez | Una se guarda; la otra pide recargar. Sin duplicados. (PG) | | | |
| C6 Consulta por periodo (reporte) | Semana, 15 días, mes y rango; las cifras coinciden con Finanzas y con el chat. | | | |
| C7 Cuatro consultas del chat por perfil | El Propietario las ve; los demás no tienen chat. | | | |
| C8 Reiniciar el servicio | Los datos y las facturas siguen ahí. | | | |
| C9 Desplegar una versión nueva | Los datos y las facturas siguen ahí; las migraciones no duplican nada. | | | |
| C10 Restaurar una copia en un entorno separado | Las cifras de control coinciden con las de la copia. | | | |
| C11 Adjuntar y descargar una factura | Solo Propietario, Administrador e Inventario la descargan. | | | |
| C12 Teclear URLs ajenas a mano | 403, o vuelve a su página; nunca datos de otro perfil. | | | |
| C13 Sesión sin actividad 30 minutos | Pide iniciar sesión de nuevo. | | | |
| C14 Cinco fallos de acceso | Bloqueo de 5 minutos; queda en la auditoría. | | | |
| C15 Crear un usuario con clave común | Se rechaza con un mensaje claro. | | | |
| C16 Ver el código fuente de `/finanzas` como Vendedora | Sin costos del inventario. | | | |
| C17 Provocar un error (ID inexistente) | Mensaje claro, sin traza ni depurador. | | | |
| C18 Descargar el paquete del contador (Excel y PDF) | Se descarga; el PDF abre; las hojas cuadran con Información contable. | | | |
| C19 Cabeceras y cookie desde el navegador | Cookie `Secure`; sin bloqueos de la política en la consola. | | | |
| C20 Copia fuera del disco del servidor | Existe una copia reciente en otro lugar. | | | |

---

## D. Pendientes y límites conocidos (se entregan junto con la versión)

1. **(PG)** `BEGIN IMMEDIATE` (en `finanzas_routes.py` y `gestion_routes.py`) y `PRAGMA foreign_keys=ON` (en `app/__init__.py`) son propios de SQLite. Emily los resuelve en la rama de PostgreSQL; hasta entonces no se puede probar el acceso simultáneo.
2. **(PG)** La variante de respaldo para PostgreSQL (`scripts/respaldo_postgres.py`) está **sin probar**.
3. Las facturas viven en `instance/facturas`: hace falta un disco persistente en el alojamiento.
4. La IP del cliente detrás del proxy debe reenviarse (el límite de intentos depende de ella).
5. Pendiente 7: la Vendedora puede leer `/finanzas/creditos` (a la espera de decisión; ver `docs/SEGURIDAD.md`).
6. Sesión sin invalidación en servidor y contadores de intentos en memoria (limitaciones documentadas en `docs/SEGURIDAD.md`).
7. "Resultado financiero soportado": falta la definición de Emily (jornadas abiertas, días sin jornada, consignaciones como soporte).
8. Sueldos por persona (por ejemplo, el de Sandra): no hay vínculo entre un pago de otro periodo y la obligación; no se muestra saldo definitivo y los sueldos quedan fuera del chat.
9. La aprobación de un crédito no se guarda como dato; por eso "créditos sin aprobación" hoy no aparece nunca.
10. La copia de seguridad no está cifrada y contiene datos personales (Ley 1581): protegerla.
11. Rol Contador: no existe; el contador recibe el paquete (Excel y PDF) descargado por el Propietario o el Administrador.
12. El reporte por periodo y el consolidado contable usan definiciones distintas de "ventas" (por operación de Finanzas frente a por equipo vendido); la diferencia es por definición, no un error.
13. Fechas con `utcnow` en algunos modelos y `AGENTS.md` desactualizado (anotados en la memoria del proyecto).
14. Analítica avanzada (cierre comparado, tendencia, rotación, proyección UVT) y MCP: fuera de esta entrega.
