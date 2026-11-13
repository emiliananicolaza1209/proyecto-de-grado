"""Copias verificables y restauración solo a destinos aislados, vía CLI local."""
import os, json, hashlib, sqlite3, zipfile, tempfile, subprocess, shutil
from pathlib import Path
from datetime import datetime,timezone
import click
from flask import current_app
from sqlalchemy.engine import make_url
from .extensions import db
from .sqlite_resources import sqlite_connection
from .services.gestion_comun import audit


def digest(data):return hashlib.sha256(data).hexdigest()


def pg_env(url):
    u=make_url(url);e=dict(os.environ)
    e.update(PGHOST=u.host or 'localhost',PGPORT=str(u.port or 5432),PGUSER=u.username or '',
             PGPASSWORD=u.password or '',PGDATABASE=u.database or '',PGCONNECT_TIMEOUT='10')
    e['PGSSLMODE']=u.query.get('sslmode','require' if (u.host or '').endswith('.render.com') else 'prefer')
    return e


def run_pg(command,url):
    if not shutil.which(command[0]):raise ValueError('Instala las herramientas PostgreSQL (pg_dump y pg_restore), de versión compatible con el servidor.')
    result=subprocess.run(command,env=pg_env(url),capture_output=True,timeout=300)
    if result.returncode:raise ValueError('La herramienta PostgreSQL no completó la operación. Revisa versión, acceso y permisos; no compartas credenciales.')


def backup(destination):
    destination=Path(destination).resolve()
    if destination.exists():raise ValueError('El archivo destino ya existe.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        tmp=Path(temp);engine=db.engine
        if engine.name=='postgresql':
            name='database.dump';run_pg(['pg_dump','--format=custom','--no-owner','--no-privileges','--file',str(tmp/name)],engine.url)
        else:
            name='database.sqlite'
            with sqlite_connection(str(engine.url.database)) as src,sqlite_connection(str(tmp/name)) as target:src.backup(target)
        members={name:(tmp/name).read_bytes()}
        invoices=Path(current_app.instance_path)/'facturas'
        if invoices.exists():
            for path in invoices.rglob('*'):
                if path.is_symlink():raise ValueError('No se admiten enlaces simbólicos en soportes.')
                if path.is_file():members['facturas/'+path.relative_to(invoices).as_posix()]=path.read_bytes()
        manifest=dict(version=1,motor=engine.name,fecha=datetime.now(timezone.utc).isoformat(),
                      files={k:digest(v) for k,v in members.items()},
                      limite='Base consistente al corte del motor; evitar cambios de soportes durante la copia.')
        # Publish only a complete archive; no partial file is presented as a backup.
        staged=destination.with_suffix(destination.suffix+'.partial')
        if staged.exists():raise ValueError('Existe una copia parcial en ese destino; revisa antes de continuar.')
        try:
            with staged.open('xb') as handle:
                os.chmod(staged,0o600)
                with zipfile.ZipFile(handle,'w',zipfile.ZIP_DEFLATED) as archive:
                    for k,v in members.items():archive.writestr(k,v)
                    archive.writestr('manifest.json',json.dumps(manifest))
            verify(staged);staged.rename(destination)
        finally:
            if staged.exists():staged.unlink()
    audit('respaldo',0,'Crear copia',{'sha256':digest(destination.read_bytes())});db.session.commit()
    return destination


def verify(path):
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if len(names)!=len(set(names)):raise ValueError('Entradas repetidas en el respaldo.')
        if sum(i.file_size for i in z.infolist())>4*1024**3:raise ValueError('Respaldo demasiado grande para este verificador.')
        manifest=json.loads(z.read('manifest.json'))
        if manifest.get('version')!=1 or manifest.get('motor') not in ('sqlite','postgresql'):raise ValueError('Formato de respaldo no compatible.')
        for name,sha in manifest['files'].items():
            if name.startswith('/') or '..' in Path(name).parts or '\\' in name:raise ValueError('Ruta inválida en el respaldo.')
            if name not in ('database.sqlite','database.dump') and not name.startswith('facturas/'):raise ValueError('Contenido no autorizado.')
            if digest(z.read(name))!=sha:raise ValueError('El respaldo no coincide con su huella.')
        required='database.dump' if manifest['motor']=='postgresql' else 'database.sqlite'
        if required not in manifest['files'] or set(names)!=set(manifest['files'])|{'manifest.json'}:raise ValueError('Contenido incompleto o inesperado.')
    return manifest


def restore(path,target):
    manifest=verify(path);target=Path(target).resolve()
    if target.exists():raise ValueError('Usa una carpeta nueva y vacía para la restauración aislada.')
    current=Path(current_app.instance_path).resolve()
    if target==current or current in target.parents or target in current.parents:raise ValueError('El destino debe estar fuera de instance.')
    with tempfile.TemporaryDirectory() as temp:
        tmp=Path(temp)
        with zipfile.ZipFile(path) as z:
            for name in manifest['files']:
                dest=tmp/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(name))
        if manifest['motor']=='postgresql':
            import psycopg
            raw=os.getenv('CPSTORE_RESTORE_URL','')
            if not raw:raise ValueError('Configura CPSTORE_RESTORE_URL para una base de recuperación aislada y vacía.')
            u=make_url(raw);live=db.engine.url
            if not (u.database or '').endswith('_restore') or (u.host,u.port or 5432,u.database)==(live.host,live.port or 5432,live.database):raise ValueError('La base de recuperación debe ser distinta y terminar en _restore.')
            with psycopg.connect(**dict(host=u.host,port=u.port or 5432,user=u.username,password=u.password,dbname=u.database,sslmode=pg_env(raw)['PGSSLMODE'])) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema')")
                    if cur.fetchone()[0]:raise ValueError('La base de recuperación no está vacía.')
            run_pg(['pg_restore','--no-owner','--no-privileges','--exit-on-error','--single-transaction','--dbname',u.database,str(tmp/'database.dump')],raw)
        else:
            with sqlite_connection(str(tmp/'database.sqlite')) as conn:
                if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('La copia SQLite no supera la verificación de integridad.')
        shutil.copytree(tmp,target)
    audit('respaldo',0,'Restaurar en entorno aislado',{'motor':manifest['motor'],'sha256':digest(Path(path).read_bytes())});db.session.commit()


def register(app):
    @app.cli.command('crear-respaldo')
    @click.option('--destino',required=True,type=click.Path())
    def create(destino):
        try:backup(destino);click.echo('Copia creada y huellas verificadas. Conserva el archivo en almacenamiento privado externo.')
        except (ValueError,OSError,zipfile.BadZipFile,subprocess.TimeoutExpired) as e:raise click.ClickException(str(e))
    @app.cli.command('verificar-respaldo')
    @click.argument('archivo',type=click.Path(exists=True))
    def check(archivo):
        try:verify(archivo);click.echo('Formato y huellas correctos; aún debe probarse la restauración.')
        except (ValueError,OSError,zipfile.BadZipFile,KeyError) as e:raise click.ClickException('El respaldo no supera la verificación.') from None
    @app.cli.command('restaurar-respaldo')
    @click.argument('archivo',type=click.Path(exists=True))
    @click.option('--destino-aislado',required=True,type=click.Path())
    @click.confirmation_option(prompt='¿Restaurar exclusivamente en un entorno aislado?')
    def recovery(archivo,destino_aislado):
        try:restore(archivo,destino_aislado);click.echo('Restauración aislada completada. Valida registros, totales y soportes antes de cualquier sustitución de servicio.')
        except Exception:raise click.ClickException('Restauración no completada. Revisa formato, herramientas, destino vacío y configuración privada.') from None
