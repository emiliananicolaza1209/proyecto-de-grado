# Subir CP Store V18 y verificarlo por HTTPS

## 1. Antes del despliegue
Aplicar la actualización con el servidor local detenido. El instalador no toca `.env` ni la base de datos. Revisar las pruebas locales y las de PostgreSQL descritas en LEEME_PRIMERO.md del paquete.
Subir todos los archivos de ARCHIVOS_PARA_GIT.txt: también incluye los archivos V17/V17.1 que aún podrían estar sin seguimiento. De lo contrario, Render podría recibir el nuevo `__init__.py` sin los módulos de los que depende.

```powershell
git branch --show-current
git add -- (Get-Content .\actualizacion_v18\ARCHIVOS_PARA_GIT.txt)
git --no-pager diff --cached --name-only
git commit -m "Integra interfaz V18, dashboard operativo y preparacion de despliegue"
git push origin migracion/postgresql
```

La rama debe ser `migracion/postgresql`. En la lista puede aparecer `.env.example`; no debe aparecer `.env` ni `instance/`. El script no hace commit o push por sí mismo ni modifica trabajo de otra rama.
En GitHub Actions, comprobar el resultado de "Pruebas CP Store". Si el repositorio no permite Actions, ejecutar las comprobaciones localmente y revisar por separado el navegador; no afirmar que CI pasó.

## 2. Crear Web Service, no otra base de datos
En la cuenta de Render donde está `cp-store-db`, crear **New → Web Service** con el repositorio existente.

| Campo | Valor |
| --- | --- |
| Branch | `migracion/postgresql` |
| Runtime | Python 3 |
| Region | La misma región de `cp-store-db` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn -c gunicorn.conf.py run:app` |
| Health Check Path | `/healthz` |
| Auto-deploy | Off inicialmente; publicar manualmente el commit comprobado |

El archivo `.python-version` selecciona Python 3.13 y el parche disponible. No dejar una variable PYTHON_VERSION antigua que lo sobreescriba. Las pruebas locales de este paquete se hicieron en 3.13.5; el trabajo de CI comprueba Python 3.13 del runner.
También puede usarse `render.yaml` como Blueprint. Si la base no está en Oregon, añadir la región real antes de sincronizar; el YAML sin región usa el valor por defecto del proveedor. El archivo no crea bases.

## 3. Variables del servicio web (privadas en Render)

| Variable | Configuración |
| --- | --- |
| `APP_ENV` | `production` |
| `DATABASE_URL` | URL **interna** de `cp-store-db`, desde Connect; no la credencial limitada de Andrés |
| `SECRET_KEY` | Una clave nueva aleatoria, privada, generada en Render o localmente; no cambiarla con cada despliegue |
| `SESSION_COOKIE_SECURE` | `true` |
| `TRUST_PROXY` | `true` para el proxy de Render |
| `UPLOADS_ENABLED` | `false` en Free |
| `PERSISTENT_INSTANCE` | `false` en Free |

Render proporciona `RENDER_EXTERNAL_HOSTNAME`. Si se añade un dominio propio, incluir todos los dominios válidos en `APP_ALLOWED_HOSTS`, separados por coma. No usar `*`.
Generar una clave en tu propio equipo, sin enviarla al chat ni a GitHub:
```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```
Copiar el resultado únicamente al campo privado SECRET_KEY de Render.
No subir el `.env` local. No ejecutar inicialización o seed durante Build/Start. La base ya está inicializada y los usuarios ya existen en ella.
No ejecutar pruebas que creen esquemas con las credenciales de la aplicación en el servicio público. CI tiene su propio contenedor y las pruebas PostgreSQL locales usan un esquema cp_test aislado.

## 4. Primera verificación
Esperar al estado Live y comprobar que `/healthz` devuelve `{"status":"ok"}`. Entrar con la cuenta existente del aplicativo; el usuario SQL y el usuario del aplicativo son distintos.
Desde el equipo local, utilizando la URL real asignada al Web Service:
```powershell
.\.venv\Scripts\python.exe scripts\verificar_despliegue.py --url https://TU-SERVICIO.onrender.com --con-login --out instance\revision_despliegue.json
```
Reemplazar solo el origen del ejemplo por el mostrado por Render. El script solicita usuario y contraseña localmente, no los imprime ni guarda, y realiza lecturas. No crea jornadas, ventas, pagos o usuarios. El JSON solo conserva resultados de comprobaciones HTTP, sin contenido de respuestas ni cookies.
La comprobación de `/healthz` valida conectividad, no todos los flujos comerciales. Una respuesta Live no equivale por sí sola a aplicativo validado.

## 5. Pruebas de entrega sobre la web publicada
Utilizar exclusivamente registros identificados como pruebas:
1. Propietario y cuenta operativa: iniciar/cerrar sesión; verificar que los accesos coincidan con el rol.
2. Navegación a 1440, 1024, 390 y 320 px: lateral en escritorio; panel lateral en móvil; teclado, Escape y foco. Sin desplazamiento horizontal de toda la página.
3. Ventas con filtros → equipo → acción → Volver. Se conservan filtro y posición; no se regresa al inicio ni se repite un POST.
4. Ingreso de un equipo con IMEI único; persistencia después de reiniciar o redesplegar.
5. Venta y abono: verificar saldo, inventario y registro en Finanzas. Confirmar una recepción no vuelve a incrementar el cobro.
6. Datáfono con recargo y crédito con desembolso: comparar cifras con las reglas ya aceptadas; pendiente no aparece como recibido.
7. Jornada: configurar asistencia, sueldos y costos; conciliar, cerrar y volver a consultar el cierre guardado.
8. Dashboard: fechas de prueba de octubre, fechas actuales y rango sin registros. Valores reales y advertencias, sin datos ficticios ni falsa predicción.
9. Exportación CSV/Excel con rol autorizado y denegación con rol operativo.
10. Facturas: si se eligió almacenamiento persistente, subir PDF de prueba y verificarlo después de redesplegar. En Free la carga debe aparecer deshabilitada.

Registrar resultado, fecha, rol y evidencia sin mostrar `.env`, contraseñas o URL de la base.

## 6. Alcance y bloqueos actuales
El código se prepara aquí; subirlo y crear el servicio no se consideran hechos hasta que exista un commit remoto y una URL funcionando. La conexión GitHub usada en esta sesión devolvió 403 y el navegador de Render pidió iniciar sesión. Esas son limitaciones del acceso disponible aquí, no evidencia de que tu terminal o tu sesión propia de Render fallen.
La versión de UI no resuelve por suposición devoluciones monetarias con créditos/liquidaciones dependientes. Ver ENTREGA_V18.md para las reglas aún pendientes.

## Referencias oficiales revisadas
- https://render.com/docs/deploy-flask
- https://render.com/docs/blueprint-spec
- https://render.com/docs/health-checks
- https://render.com/docs/python-version
- https://render.com/docs/free
- https://flask.palletsprojects.com/en/stable/deploying/proxy_fix/
