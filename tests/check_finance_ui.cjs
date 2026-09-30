/* Ejecutar con NODE_PATH apuntando a jsdom y FIXTURE_DIR con HTML de Flask. */
const {JSDOM}=require('jsdom');const fs=require('fs');const assert=require('assert/strict');
const dom=new JSDOM(fs.readFileSync(process.env.FIXTURE_DIR+'/movimientos.html','utf8'),{runScripts:'outside-only'});const w=dom.window,d=w.document;
w.eval(fs.readFileSync(__dirname+'/../app/static/js/finanzas.js','utf8'));
function input(selector,value,type='input'){const e=d.querySelector(selector);e.value=value;e.dispatchEvent(new w.Event(type,{bubbles:true}));}
input('#operation-form [name=amount]','105000');assert.equal(d.querySelector('[name=payment_amount]').value,'105000');
d.querySelector('#add-cost').click();input('[name=cost_qty]','3');input('[name=cost_unit]','10000');assert.match(d.querySelector('#preview-margin').textContent,/75[.,]000/);
input('[name=payment_amount]','55000');input('#operation-form [name=amount]','110000');assert.equal(d.querySelector('[name=payment_amount]').value,'55000');
input('[name=cost_type]','Bebida','change');input('[name=cost_unit]','');input('[name=cost_name]','AGUA','change');assert.equal(d.querySelector('[name=cost_unit]').value,'2000');
input('#f-kind','PD');assert.equal(d.querySelector('[name=minor_cost]').disabled,true);assert.equal(d.querySelector('[data-sale]').hidden,true);
input('#f-kind','Venta');assert.equal(d.querySelector('[name=minor_cost]').disabled,false);
d.querySelector('.remove-row').click();assert.equal(d.querySelectorAll('.f-cost-row').length,0);
console.log('DOM OK: autocompletar pago, cálculo, bebidas, tipos de gasto y filas dinámicas.');
