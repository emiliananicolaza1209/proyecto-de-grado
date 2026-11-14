"""Señala formularios de solo consulta; el guard de autenticación es la autoridad.

Conserva el HTML original y solo envuelve formularios POST sin ninguna acción
permitida. No cambia formularios GET, descargas, servicios ni reglas de negocio.
"""
from html.parser import HTMLParser
from urllib.parse import urlsplit, parse_qs
from flask import current_app, g, request
from werkzeug.exceptions import HTTPException
from .services.permisos_service import route_keys


class Forms(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source=source; self.offsets=[0]; self.forms=[]; self.current=None;self.select_name=None
        for line in source.splitlines(keepends=True): self.offsets.append(self.offsets[-1]+len(line))

    def absolute_pos(self):
        line,column=self.getpos();return self.offsets[line-1]+column

    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=='form':
            self.current=dict(start=self.absolute_pos()+len(self.get_starttag_text()),attrs=attrs,fields={})
        elif self.current and tag in ('input','button') and attrs.get('name') in ('action','kind','tab'):
            self.current['fields'].setdefault(attrs['name'],[]).append(attrs.get('value',''))
        elif self.current and tag=='select':self.select_name=attrs.get('name')
        elif self.current and tag=='option' and self.select_name in ('action','kind','tab'):
            self.current['fields'].setdefault(self.select_name,[]).append(attrs.get('value',''))

    def handle_endtag(self, tag):
        if tag=='select':self.select_name=None
        if tag=='form' and self.current:
            self.current['end']=self.absolute_pos();self.forms.append(self.current);self.current=None


def restrict_forms(response):
    if not getattr(g,'acceso_personalizado',False) or response.status_code!=200 or response.mimetype!='text/html':return response
    parser=Forms(response.get_data(as_text=True));parser.feed(parser.source)
    adapter=current_app.url_map.bind_to_environ(request.environ)
    replacements=[]
    for form in parser.forms:
        if form['attrs'].get('method','get').lower()!='post':continue
        url=urlsplit(form['attrs'].get('action') or request.path)
        if url.netloc and url.netloc!=request.host:continue
        try:endpoint,args=adapter.match(url.path or request.path,method='POST')
        except HTTPException:continue
        base={k:v[0] for k,v in parse_qs(url.query).items()}
        fields=form['fields'];actions=fields.get('action',['']);kinds=fields.get('kind',['Venta'])
        possibilities=[route_keys(endpoint,'POST',dict(base,action=a,kind=k),args) for a in actions for k in kinds]
        if any(keys.issubset(g.permisos_efectivos) for keys in possibilities):continue
        original=parser.source[form['start']:form['end']]
        replacement='<p class="access-notice" role="note">Solo consulta: esta acción no está habilitada para tu usuario.</p><fieldset disabled class="access-readonly">'+original+'</fieldset>'
        replacements.append((form['start'],form['end'],replacement))
    result=parser.source
    for start,end,value in reversed(replacements):result=result[:start]+value+result[end:]
    response.set_data(result)
    return response
