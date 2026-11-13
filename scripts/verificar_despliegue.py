"""Comprobación HTTPS de lectura. No registra ventas ni modifica datos comerciales.
La contraseña, si se solicita, se introduce localmente con getpass y no se guarda.
"""
import argparse
import getpass
import http.cookiejar
import json
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPCookieProcessor


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class TokenParser(HTMLParser):
    token = None
    def handle_starttag(self, tag, attrs):
        values=dict(attrs)
        if tag=='input' and values.get('name')=='csrf':self.token=values.get('value')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',required=True,help='Dirección HTTPS pública de CP Store')
    parser.add_argument('--con-login',action='store_true',help='Comprobar también las páginas con una cuenta de propietario')
    parser.add_argument('--out',default='instance/revision_despliegue.json')
    args=parser.parse_args();url=args.url.rstrip('/')
    parsed=urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment:
        parser.error('Usa solo el origen HTTPS público, sin credenciales, consultas ni rutas.')
    jar=http.cookiejar.CookieJar();opener=build_opener(HTTPCookieProcessor(jar),NoRedirect())
    checks=[]
    def call(path, data=None):
        req=Request(url+path,data=urlencode(data).encode() if data else None,
                    headers={'User-Agent':'CPStore-Verificacion/18','Accept':'text/html,application/json'})
        try:
            with opener.open(req,timeout=45) as r:return r.status,r.headers,r.read(2*1024*1024)
        except HTTPError as e:
            return e.code,e.headers,e.read(1024*1024)
        except (URLError,TimeoutError,OSError):return 0,{},b''
    def check(name, passed, status=None):
        checks.append(dict(comprobacion=name,correcto=bool(passed),http=status))
        print(('OK  ' if passed else 'FALLO  ')+name)
    code,headers,body=call('/healthz')
    try:healthy=json.loads(body)=={'status':'ok'}
    except (ValueError,TypeError):healthy=False
    check('Conexión de la aplicación con la base de datos',code==200 and healthy,code)
    code,headers,body=call('/iniciar-sesion');p=TokenParser();p.feed(body.decode('utf-8','replace'))
    check('Formulario de acceso y token CSRF',code==200 and bool(p.token),code)
    check('Protección contra incrustación y tipos de contenido',headers.get('X-Frame-Options')=='DENY' and headers.get('X-Content-Type-Options')=='nosniff',code)
    check('Política de contenido y HTTPS',"script-src 'self'" in headers.get('Content-Security-Policy','') and 'max-age=' in headers.get('Strict-Transport-Security',''),code)
    for path in ('/','/reportes/exportar/ventas/xlsx','/api/consultas/inventario'):
        status,head,_=call(path);location=urlsplit(head.get('Location','')).path
        check('Acceso anónimo protegido: '+path,status in (302,303) and location=='/iniciar-sesion',status)
    for path in ('/static/css/business.css?v=18','/static/js/navigation.js?v=18','/static/js/dashboard.js?v=18','/static/img/ui.svg'):
        status,_,asset=call(path);check('Recurso de interfaz: '+path.split('?')[0],status==200 and len(asset)>100,status)
    if args.con_login and p.token:
        usuario=input('Usuario de propietario (no se guardará): ').strip()
        password=getpass.getpass('Contraseña (no se mostrará ni guardará): ')
        status,head,_=call('/iniciar-sesion',dict(csrf=p.token,login=usuario,password=password));password=None
        signed_in=status in (302,303) and urlsplit(head.get('Location','')).path=='/'
        check('Inicio de sesión',signed_in,status)
        check('Cookie de sesión segura',any(c.name=='session' and c.secure for c in jar),status)
        if signed_in:
            for path in ('/?periodo=7','/?periodo=30','/inventario','/ventas','/reportes?tipo=ventas'):
                status,_,page=call(path)
                check('Página autenticada: '+path,status==200 and b'app-sidebar' in page,status)
    report=dict(version='18',fecha=datetime.now(timezone.utc).isoformat(),sitio=url,
        estado='correcto' if all(c['correcto'] for c in checks) else 'requiere_revision',
        comprobaciones=checks,limite='Verificación HTTP de lectura; no sustituye pruebas manuales de venta, cierre o diseño responsivo.')
    dest=Path(args.out)
    # Este informe no contiene respuestas HTML, cookies, tokens ni contraseñas.
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Informe guardado en '+str(dest))
    return 0 if report['estado']=='correcto' else 1


if __name__=='__main__':sys.exit(main())
