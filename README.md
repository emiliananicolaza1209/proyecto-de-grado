# CP Store — versión integrada V19

Integra Finanzas e inventario corregidos hasta V18.3.1 con analítica, chat por reglas,
reportes por periodo y módulo contable de Andrés. Incluye cambios acumulados:
**no es necesario instalar V18.3.1 por separado**.

- Instalación y decisiones: [docs/INTEGRACION_V19.md](docs/INTEGRACION_V19.md).
- Recorridos y evidencia: [docs/PRUEBAS_INTEGRADAS_V19.md](docs/PRUEBAS_INTEGRADAS_V19.md).
- Validación de esta entrega: [docs/VALIDACION_V19.md](docs/VALIDACION_V19.md).

El instalador revisa archivos y guarda copias; no ejecuta SQL ni modifica `.env`.
La actualización PostgreSQL se realiza en un paso explícito después del respaldo.
Las pruebas automáticas no sustituyen la aceptación en PostgreSQL y el navegador.

---

## Documentación anterior (histórica)

# proyecto-de-grado

Aplicación CP Store. La entrega actual es V16.2.

Lee [LEEME_V16_2.md](LEEME_V16_2.md) para actualizar y consultar el desglose bancario, la revisión de nombres similares y las correcciones de navegación y botones.

Para la primera instalación V16, consulta también [LEEME_V16.md](LEEME_V16.md): incluye respaldo, dependencias, creación del propietario y arranque.

Validación actual: [docs/VALIDACION_V16_2.md](docs/VALIDACION_V16_2.md). Reglas de base: [docs/REGLAS_V16.md](docs/REGLAS_V16.md). Las guías anteriores se conservan como historial.
