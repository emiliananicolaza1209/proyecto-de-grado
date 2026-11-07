# Validación de CP Store V16.2

Fecha: 4 de noviembre de 2026. Fuente: entrega completa V16.1. Pruebas realizadas con bases SQLite temporales y datos ficticios, sin acceso a la base del equipo del usuario.

## Suite automatizada

Comando: `python -m unittest discover -s tests -p "test_*.py" -v`

Resultado: **119 pruebas aprobadas en 33,253 segundos**, sin errores ni fallos. Incluye las pruebas existentes de compras, inventario, POOL, ventas, cobros, finanzas, créditos, sociedades, permisos e integración contable.

### Nuevos casos

| Archivo | Casos | Cobertura |
|---|---:|---|
| `tests/test_accounting_bank_summary.py` | 6 | Persona y año correctos; movimientos activos; bancos sin ingresos; ingresos sin banco; bancos históricos; decimales; más de 150 movimientos; edición de consignaciones; transferencia y datáfono vinculados; consulta sin escrituras; selección y estado vacío. |
| `tests/test_catalog_review.py` | 6 | Generaciones y variantes distintas; aviso de parecido antes de guardar; confirmación explícita; duplicados exactos y registros inactivos; aislamiento por catálogo y padre; edición protegida; navegación de Usuarios, Finanzas y Ventas. |

Se actualizaron dos comprobaciones de texto en `tests/test_brands.py` para reconocer las nuevas etiquetas de la revisión; se conserva el caso que exige confirmar un nombre parecido.

## Navegador

Revisión automatizada con Chromium y Playwright 1.56.0, aplicación local temporal y vista de escritorio de 1440 × 1000 y móvil de 390 × 844.

- Selección de persona por enlace y selector en el desglose bancario; total de $165.000 distribuido en $130.000 y $35.000, con otro banco en cero.
- Cambio de año conservando la selección y diferenciación de movimientos sin banco.
- Navegación y formulario de consulta del desglose sin JavaScript.
- Pantalla de Usuarios sin navegación de Finanzas; Finanzas mantiene su propia barra.
- Comparación de coordenadas y alturas de Aplicar filtros y Limpiar filtros: alineación igual en escritorio y móvil.
- Aviso de catálogo en ventana; abrir existente, cancelar, conservar datos, confirmar un nombre distinto, bloquear duplicados y regresar con Escape.
- Revisión del catálogo sin JavaScript y confirmación mediante el formulario estándar.
- Sin errores de JavaScript en los flujos comprobados. Sin desbordamiento horizontal de la página contable ni los filtros de Ventas en el ancho móvil comprobado; la ventana adapta su contenido.

Se inspeccionaron capturas de las barras, Usuarios, filtros y ventana en ambos tamaños. Los estilos nuevos conservan contraste de texto en los botones primarios aunque el CSS externo no esté disponible.

## Alcance y límites

V16.2 no modifica los modelos ni las migraciones de V16.1, los cálculos financieros, los permisos o el historial existente. El desglose es de lectura. La revisión del catálogo no fusiona ni elimina datos.

La similitud de nombres es una ayuda para el usuario, no una garantía de identidad comercial. Las pruebas de navegador corresponden a Chromium; no sustituyen una revisión del proyecto con los datos reales ni pruebas en todos los navegadores o dispositivos físicos. No se realizó un despliegue ni una actualización del repositorio de GitHub.
