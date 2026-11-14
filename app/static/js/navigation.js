/* Navegación local, regreso contextual y restauración por pestaña. Sin POST repetidos. */
(function(global){'use strict';
const blocked=/^\/(?:api\/|static\/|healthz(?:$|\?)|cerrar-sesion(?:$|\?))/;
function localURL(value,origin){
 if(typeof value!=='string'||value.length>4096||/[\u0000-\u001f\u007f\\]/.test(value))return null;
 try{const decoded=decodeURIComponent(value);if(/[\u0000-\u001f\u007f\\]/.test(decoded))return null;const u=new URL(value,origin);if(u.origin!==origin||!['http:','https:'].includes(u.protocol)||blocked.test(u.pathname))return null;return u.pathname+u.search+u.hash;}catch(_){return null;}
}
function parentFor(pending,here,fallback){
 if(!pending||pending.to!==here||Date.now()-pending.at>60000)return {parent:fallback,native:false};
 return pending.post?{parent:pending.parent||fallback,native:false}:{parent:pending.from===here?pending.parent||fallback:pending.from,native:pending.from!==here};
}
function sectionMatches(value,current,origin){
 const target=localURL(value,origin),page=localURL(current,origin);if(!target||!page)return false;
 const a=new URL(target,origin),b=new URL(page,origin);if(a.pathname!==b.pathname)return false;
 for(const [key,value]of a.searchParams){if(key==='date')continue;const selected=b.searchParams.get(key)||(key==='tab'&&b.pathname==='/finanzas'?'movimientos':'');if(selected!==value)return false;}
 return true;
}
function formSignature(entries){
 const ignored=new Set(['csrf','revision','token','action','return_tab']);
 return JSON.stringify([...entries].filter(([key])=>!ignored.has(key)).map(([key,value])=>[key,typeof value==='string'?value:String(value?.name||'')]));
}
if(typeof module==='object'&&module.exports)module.exports={localURL,parentFor,sectionMatches,formSignature};
if(typeof document==='undefined')return;
const body=document.body;if(!body.classList.contains('business-app'))return;
const origin=location.origin,here=()=>location.pathname+location.search+location.hash,storageKey='cpstore.navigation.v18',pendingKey=storageKey+'.pending';
// Los controles llamados method/action/target ocultan las propiedades del form.
// Leer sus atributos conserva el método HTTP y no confunde el medio de pago.
const formMethod=form=>(form.getAttribute('method')||'get').toLowerCase();
let store={},pending=null;try{store=JSON.parse(sessionStorage.getItem(storageKey)||'{}');pending=JSON.parse(sessionStorage.getItem(pendingKey)||'null');sessionStorage.removeItem(pendingKey);}catch(_){store={};}
const fallback=localURL(body.dataset.returnTo||'/',origin)||'/';
let state=history.state?.cpstoreView;
if(!state||state.url!==here())state={url:here(),...parentFor(pending,here(),fallback)};
state.parent=localURL(state.parent,origin)||fallback;
function replace(){try{history.replaceState({...history.state,cpstoreView:state},'');}catch(_){}}
replace();
function write(){try{const keys=Object.keys(store);while(keys.length>35)delete store[keys.shift()];sessionStorage.setItem(storageKey,JSON.stringify(store));}catch(_){}}
function capture(){
 const filters=[...document.querySelectorAll('[data-filter-table],[data-nav-filter]')].filter(el=>el.id).map(el=>[el.id,el.value]);
 const details=[...document.querySelectorAll('details')].map((el,i)=>el.open?i:null).filter(i=>i!==null);
 store[here()]={y:window.scrollY,filters,details};write();replace();
}
function restore(){
 if(location.hash){const target=document.getElementById(decodeURIComponent(location.hash.slice(1)));if(target){if(target.tagName==='DETAILS')target.open=true;target.scrollIntoView();}return;}
 if(new URL(location.href).searchParams.has('accion')){window.scrollTo(0,0);return;}
 const saved=store[here()];if(!saved||body.dataset.hasError==='true')return;
 for(const [id,value] of saved.filters||[]){const input=document.getElementById(id);if(input){input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}));}}
 const details=[...document.querySelectorAll('details')];for(const i of saved.details||[]){const detail=details[i];if(!detail)continue;if(detail.matches('.operation-card'))document.getElementById('operation-tab-'+detail.dataset.action)?.click();else detail.open=true;}
 requestAnimationFrame(()=>requestAnimationFrame(()=>window.scrollTo({top:saved.y||0,behavior:'instant'})));
}
for(const link of document.querySelectorAll('[data-app-back]'))link.href=state.parent;
document.addEventListener('click',event=>{
 const link=event.target.closest('a[href]');if(!link||event.defaultPrevented||event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey||link.target==='_blank'||link.hasAttribute('download'))return;
 const to=localURL(link.href,origin);if(!to||/\.(?:pdf|xlsx|csv|zip)(?:[?#]|$)/i.test(to)||to.startsWith('/reportes/exportar/'))return;
 capture();
 if(link.hasAttribute('data-app-back')){if(state.native&&localURL(state.parent,origin)){event.preventDefault();history.back();}return;}
 if(to===here()||link.getAttribute('href').startsWith('#'))return;
 try{sessionStorage.setItem(pendingKey,JSON.stringify({from:here(),to,at:Date.now(),parent:state.parent,post:false}));}catch(_){}
});
document.addEventListener('submit',event=>{
 const form=event.target;if(!(form instanceof HTMLFormElement)||!form.checkValidity())return;
 capture();if(formMethod(form)==='post'){
   const to=localURL(new URL(form.getAttribute('action')||location.href,document.baseURI).href,origin);if(to)try{sessionStorage.setItem(pendingKey,JSON.stringify({from:here(),to,at:Date.now(),parent:state.parent,post:true}));}catch(_){}
 }
});
window.addEventListener('pagehide',capture);window.addEventListener('pageshow',restore);
if(document.readyState==='complete')restore();
// Los filtros GET ya están en la URL; solo se guardan filtros locales, no datos
// de formularios comerciales ni contraseñas. El aviso protege cambios sin guardar.
let leaving=false;
const baselines=new Map(),busyButtons=new Map();
const signature=form=>formSignature(new FormData(form));
function baseline(form){if(form&&formMethod(form)==='post'&&!form.hasAttribute('data-no-dirty'))baselines.set(form,signature(form));}
setTimeout(()=>{for(const form of document.forms)baseline(form);},0);
document.addEventListener('cpstore:form-ready',event=>baseline(event.target));
function unsaved(){return [...baselines].some(([form,before])=>form.isConnected&&signature(form)!==before);}
const status=document.createElement('div');status.id='app-loading-status';status.role='status';status.setAttribute('aria-live','polite');status.hidden=true;document.body.append(status);
function loading(message){status.textContent=message;status.hidden=false;}
function idle(){status.hidden=true;leaving=false;for(const [button,label]of busyButtons){button.textContent=label;button.disabled=false;button.removeAttribute('aria-busy');}busyButtons.clear();}
document.addEventListener('submit',event=>{
 const form=event.target;if(!(form instanceof HTMLFormElement)||event.defaultPrevented||!form.checkValidity()||form.getAttribute('target')==='_blank')return;
 // La navegación nativa puede comenzar antes de un temporizador.
 leaving=true;
 queueMicrotask(()=>{if(event.defaultPrevented){idle();return;}loading(formMethod(form)==='post'?'Guardando…':'Cargando…');});
 const button=event.submitter;
 setTimeout(()=>{if(!event.defaultPrevented&&button){busyButtons.set(button,button.textContent);button.textContent=formMethod(form)==='post'?'Guardando…':'Consultando…';button.disabled=true;button.setAttribute('aria-busy','true');}},0);
});
document.addEventListener('click',event=>{
 const link=event.target.closest('a[href]');
 if(!link||event.defaultPrevented||event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey||link.target==='_blank'||link.hasAttribute('download'))return;
 const to=localURL(link.href,origin);if(!to||to===here()||link.getAttribute('href').startsWith('#')||/\.(?:pdf|xlsx|csv|zip)(?:[?#]|$)/i.test(to)||to.startsWith('/reportes/exportar/'))return;
 // Con cambios sin guardar, la confirmación del navegador decide la salida.
 if(!unsaved())loading('Cargando…');
});
window.addEventListener('beforeunload',event=>{if(!leaving&&unsaved()){idle();event.preventDefault();event.returnValue='';}});
window.addEventListener('pageshow',idle);

// Solo subraya la sección actual; los enlaces globales siguen en el lateral.
for(const link of document.querySelectorAll('.app-subnav a')){if(sectionMatches(link.href,location.href,origin))link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');}
// Tablas de consulta simples se apilan en móvil; matrices contables complejas
// conservan su desplazamiento dentro de la tabla, sin desbordar toda la página.
function enhanceTables(){for(const table of document.querySelectorAll('.sales-table,.f-table table,.inventory-panel table,table[data-ui-responsive]')){
 if(table.dataset.uiReady==='true')continue;table.dataset.uiReady='true';
 const headers=[...table.querySelectorAll('thead tr:first-child th')].map(th=>th.textContent.trim());
 if(!headers.length||headers.length>7||table.querySelector('[rowspan]'))continue;
 table.classList.add('ui-responsive-table');for(const row of table.querySelectorAll('tbody tr'))[...row.children].forEach((cell,i)=>{if(!cell.hasAttribute('colspan'))cell.dataset.label=headers[i]||'';});
}
}
enhanceTables();
const results=document.querySelector('.inventory-panel');if(results&&typeof MutationObserver!=='undefined')new MutationObserver(enhanceTables).observe(results,{childList:true,subtree:true});
// Formularios anuales GET conservan el envío sin un controlador inline.
for(const select of document.querySelectorAll('select[data-auto-submit]'))select.addEventListener('change',()=>select.form.requestSubmit());
})(globalThis);
