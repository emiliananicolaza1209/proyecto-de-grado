/* Prueba DOM opcional: jsdom instalado aparte; FIXTURE_DIR contiene HTML de prueba. */
const {JSDOM} = require('jsdom');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const fixture = process.env.FIXTURE_DIR;
const fields = JSON.parse(fs.readFileSync(path.join(fixture,'fields.json')));
const script = fs.readFileSync(path.join(__dirname,'../app/static/js/inventario.js'),'utf8');
function load(name) {
  const dom = new JSDOM(fs.readFileSync(path.join(fixture,name+'.html'),'utf8'), {url:'http://localhost/inventario',runScripts:'outside-only'});
  dom.window.HTMLElement.prototype.scrollIntoView = () => {};
  dom.window.fetch = async () => ({ok:true,json:async()=>({valid:true,exists:false}),text:async()=>'<p>RESULTADO ACTUALIZADO</p>'});
  dom.window.eval(script);
  return dom;
}
function fire(w, el, name='input') {el.dispatchEvent(new w.Event(name,{bubbles:true}));}
async function run() {
  const dom = load('new'), w=dom.window, d=w.document;
  const brand=d.querySelector('#brand'); brand.value=String(fields.brand_id); fire(w,brand,'change');
  const search=d.querySelector('#model-search');
  search.value='11 pro max'; fire(w,search);
  assert.equal(d.querySelectorAll('#model-options [role=option]').length,1);
  d.querySelector('#model-options [role=option]').click();
  assert.equal(search.value,'IPHONE 11 PRO MAX');
  assert.ok(d.querySelector('#model').value);
  assert.deepEqual([...d.querySelector('#capacity').options].map(o=>o.textContent),['Seleccionar','64 GB','256 GB','512 GB']);
  assert.ok([...d.querySelector('#color').options].some(o=>o.textContent==='VERDE MEDIANOCHE'));
  search.value='texto desconocido'; fire(w,search);
  assert.equal(d.querySelector('#model').value,'');
  assert.equal(search.checkValidity(),false);
  d.querySelector('#model-toggle').click();
  d.querySelector('#model-toggle').click();
  assert.ok(d.querySelectorAll('#model-options [role=option]').length>10);
  search.dispatchEvent(new w.KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true}));
  search.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  assert.ok(search.checkValidity());
  const lot=d.querySelector('#lot-select'); lot.value=String(fields.lot_id); fire(w,lot,'change');
  const rate=d.querySelector('#exchange_rate'); assert.equal(rate.readOnly,false);
  for (const [key,value] of Object.entries({purchase_usd:'100',exchange_rate:'4000',shipping_cop:'10000'})) {
    const input=d.getElementById(key); input.value=value; fire(w,input);
  }
  assert.match(d.querySelector('#total-preview').textContent,/410[.,]000/);
  assert.match(d.querySelector('#subtotal-preview').textContent,/400[.,]000/);
  const sw=d.querySelector('#warranty-enabled'); sw.checked=true; fire(w,sw,'change');
  assert.equal(d.querySelector('#warranty-fields').hidden,false);
  assert.equal(d.querySelector('#warranty-until').required,true);
  sw.checked=false; fire(w,sw,'change');
  assert.equal(d.querySelector('#warranty-until').disabled,true);
  dom.window.close();
  const copy=load('similar'), c=copy.window.document;
  assert.equal(c.querySelector('#imei').value,'');
  assert.equal(c.querySelector('#model').value,String(fields.reference_id));
  assert.equal(c.querySelector('#color').value,String(fields.color_id));
  assert.equal(c.querySelector('#capacity').value,String(fields.capacity_id));
  assert.equal(c.querySelector('#warranty-until').value,'2027-09-12');
  assert.equal(c.querySelector('#purchase_usd').value,'1070');
  copy.window.close();
  const index=load('index'), i=index.window.document;
  i.querySelector('#q').value='IPHONE'; fire(index.window,i.querySelector('#q'));
  await new Promise(resolve=>setTimeout(resolve,300));
  assert.match(i.querySelector('#inventory-results').textContent,/RESULTADO ACTUALIZADO/);
  assert.equal(i.querySelector('#q').value,'IPHONE');
  assert.match(index.window.location.search,/q=IPHONE/);
  index.window.close();
  console.log('OK: selector con teclado, propiedades, costos, cobertura, registro consecutivo y búsqueda dinámica.');
}
run().catch(error=>{console.error(error);process.exitCode=1;});
