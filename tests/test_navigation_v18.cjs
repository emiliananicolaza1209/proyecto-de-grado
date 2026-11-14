'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {localURL,parentFor}=require('../app/static/js/navigation.js');
const origin='https://cp.example';
test('Los filtros y el punto de regreso pertenecen al mismo sitio',()=>{
 assert.equal(localURL('/ventas?saldo=1&q=IPHONE#equipo',origin),'/ventas?saldo=1&q=IPHONE#equipo');
 for(const bad of ['https://evil.example','//evil.example','javascript:alert(1)','/\\evil.example','/api/consultas/ventas','/static/x.js','/x%0aevil'])assert.equal(localURL(bad,origin),null,bad);
});
test('Volver conserva el origen y no repite un formulario POST',()=>{
 const p={from:'/ventas?saldo=1',to:'/ventas/2',parent:'/',at:Date.now(),post:false};
 assert.deepEqual(parentFor(p,'/ventas/2','/ventas'),{parent:'/ventas?saldo=1',native:true});
 assert.deepEqual(parentFor({...p,post:true,parent:'/ventas?saldo=1'},'/ventas/2','/ventas'),{parent:'/ventas?saldo=1',native:false});
 assert.deepEqual(parentFor({...p,at:1},'/ventas/2','/ventas'),{parent:'/ventas',native:false});
 assert.deepEqual(parentFor(p,'/usuarios','/'),{parent:'/',native:false});
});
