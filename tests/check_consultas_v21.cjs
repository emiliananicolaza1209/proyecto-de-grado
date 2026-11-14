/* Recorrido de consultas sobre la base desechable. No admite una URL de producción. */
'use strict';
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base='http://127.0.0.1:5018';
(async()=>{
 const health=await fetch(base+'/healthz');
 assert.equal(health.headers.get('x-cpstore-test-fixture'),'temporary-sqlite-loopback');
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1366,height:900},locale:'es-CO',timezoneId:'America/Bogota'});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',route=>{
   const request=route.request(),url=new URL(request.url());
   if(['GET','HEAD'].includes(request.method()) || (url.origin===base&&url.pathname==='/chat/consultar'))return route.continue();
   return route.abort();
  });
  await page.goto(base+'/modulos/tributario/',{waitUntil:'networkidle'});
  assert.equal(await page.locator('#consolidado').isVisible(),true);
  assert.equal(await page.locator('#personas').isVisible(),false);
  await page.getByRole('tab',{name:'Personas y bancos'}).click();
  assert.equal(await page.locator('#personas').isVisible(),true);
  await page.getByRole('tab',{name:'Personas y bancos'}).press('ArrowRight');
  assert.equal(await page.locator('#consignaciones').isVisible(),true);
  await page.getByRole('link',{name:'+ Registrar persona',exact:true}).click();
  assert.equal(await page.locator('#personas').isVisible(),true,'El enlace abre la sección antes de enfocar el formulario');
  await page.goto(base+'/chat',{waitUntil:'networkidle'});
  const historicResponse=page.waitForResponse(r=>r.url().endsWith('/chat/consultar'));
  await page.locator('[data-chat-quick]').click();
  await historicResponse;
  const card=page.locator('.chat-respuesta').last();
  await card.waitFor();
  assert.match(await card.innerText(),/853\.000/);
  assert.match(await card.innerText(),/12/);
  const last=await page.locator('.chat-period-controls').getAttribute('data-ultimo-cierre');
  await page.locator('#chat-periodo').selectOption('rango');
  await page.locator('#chat-desde').fill(last);await page.locator('#chat-hasta').fill(last);
  await page.locator('#chat-pregunta').fill('ventas');
  const response=page.waitForResponse(r=>r.url().endsWith('/chat/consultar'));
  await page.getByRole('button',{name:'Preguntar',exact:true}).click();
  const data=await (await response).json();
  assert.equal(data.periodo.ini,last);
  assert.equal(data.tarjeta.cifras.find(row=>row.etiqueta==='Operaciones de venta').valor,'12');
  assert.equal(data.tarjeta.cifras.find(row=>row.etiqueta==='Venta neta').valor,'$853.000');
  assert.deepEqual(errors,[]);
  console.log('Consultas V21: pestañas, teclado, enlaces, cierre histórico y fechas del chat correctos.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
