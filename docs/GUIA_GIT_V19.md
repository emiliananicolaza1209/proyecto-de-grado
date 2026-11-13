# Conservar las dos ramas en Git

La revisión e instalación local van antes de publicar. No se ha hecho push ni
merge remoto desde esta entrega. El bundle incluido conserva la historia de la
rama de Andrés y un commit con las correcciones financieras, además del merge
revisado. Su rama es `integracion/cp-store-v19`.

## Si instalaste y probaste el paquete en tu carpeta actual

1. Revisar primero `git status --short` y `git branch --show-current`.
   Mantener tu trabajo en tu propia rama. No usar `reset --hard`, no reemplazar
   la carpeta `.git` y no forzar un push.
2. Guardar los archivos revisados en un commit local. La lista del instalador
   enumera código/documentación de la versión integrada; no incluye privados.
   Desde la raíz, revisar y preparar esa lista:

```powershell
Get-Content integracion_v19\ARCHIVOS_PARA_GIT.txt
Get-Content integracion_v19\ARCHIVOS_PARA_GIT.txt | ForEach-Object { git add -- $_ }
git diff --cached --stat
git diff --cached --check
git diff --cached
```

Comprobar que no contiene credenciales, respaldos, bases ni datos reales. Si
hay cambios tuyos adicionales fuera de esa lista, revisarlos e incluirlos de
forma explícita o guardarlos en otra rama antes de cambiar de rama. No usar
`git add .`. Cuando lo preparado y las pruebas sean correctos:

```powershell
git commit -m "Integra Finanzas corregidas, analitica y reportes V19"
```

3. Obtener los antecedentes y verificar el bundle:

```powershell
git fetch origin migracion/postgresql ia-analitica-contable
git bundle verify .\integracion_v19\cp_store_v19.bundle
git fetch .\integracion_v19\cp_store_v19.bundle refs/heads/integracion/cp-store-v19:refs/remotes/entrega/cp-store-v19
```

El bundle necesita el historial original de GitHub. Si `verify` indica que
faltan commits, no continuar ni sustituir archivos; resolver la descarga del
historial primero. Si GitHub te pide iniciar sesión, usar tu autenticación
habitual; no compartir tokens o contraseñas.

4. Con el árbol de trabajo limpio, crear una rama para integrar y unir el
   historial preparado:

```powershell
git switch -c integracion/cp-store-v19
git merge --no-ff --no-commit entrega/cp-store-v19
git status --short
git diff --cached --stat
```

Si ya existe una rama con ese nombre, revisarla antes de crear otra; no
sobrescribirla. Si Git dice «Already up to date», no hay merge pendiente que
confirmar. Si hay conflictos, comparar función por función conservando las
reglas y pruebas de ambos; no aceptar automáticamente «ours/theirs» para todos
los archivos. Ante una resolución incierta se puede usar `git merge --abort`
antes de crear el commit; el commit local del paso 2 sigue conservado.

La integración está basada en el commit concreto de Andrés
`348a073bd763f2cbb7fdace516798e89690f41fb`. Si su rama tiene commits posteriores,
estos no se deben dar por incorporados: comparar e integrar por separado.

5. Revisar las diferencias reales y repetir pruebas si las resoluciones o los
   nuevos cambios modificaron el código. Comprobar especialmente POOL, créditos,
   roles y cierre en PostgreSQL. Cuando el merge esté revisado:

```powershell
git commit -m "Conserva el historial de ambas ramas en la integracion V19"
git log --graph --oneline -12
git status --short
```

## Publicar después de la aceptación

Cuando ambos hayan revisado la rama y las pruebas, subir esa rama (no `main`
directamente):

```powershell
git push -u origin integracion/cp-store-v19
```

Abrir una pull request hacia la rama acordada y revisar el diff completo. Render
debe desplegar la rama/commit integrado aprobado; `render.yaml` apunta a
`integracion/cp-store-v19` y mantiene desactivado el despliegue automático.
Configurar la PostgreSQL existente y las variables privadas desde el servicio,
validar respaldo/actualización y hacer prueba pública. El ZIP, por sí mismo,
no sube código ni publica un servicio.
