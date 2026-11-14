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
  // Cambiar pestaña conserva el contexto y no agrega pasos al regreso al módulo de origen.
  await page.goto(base+'/ventas',{waitUntil:'networkidle'});
  await Promise.all([
   page.waitForURL(base+'/modulos/tributario',{waitUntil:'networkidle'}),
   page.locator('.app-sidebar').getByRole('link',{name:'Información contable',exact:true}).click()
  ]);
  const arrivalState=await page.evaluate(()=>history.state);
  assert.equal(arrivalState.cpstoreView.native,true,'La entrada desde Ventas conserva su regreso nativo');
  await page.getByRole('tab',{name:'Personas y bancos'}).click();
  assert.deepEqual(await page.evaluate(()=>history.state),arrivalState,'La pestaña conserva el estado de navegación');
  await Promise.all([
   page.waitForURL(base+'/ventas',{waitUntil:'networkidle'}),
   page.locator('[data-app-back]').click()
  ]);
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
  for(const width of [1366,390]){
   await page.setViewportSize({width,height:900});
   if(width<1024)await page.waitForFunction(()=>document.querySelector('.app-sidebar').getBoundingClientRect().right<=1);
   const guide=page.locator('.chat-guide');
   await guide.scrollIntoViewIfNeeded();
   assert.equal(await guide.getByRole('heading',{name:'Cómo preguntar',exact:true}).isVisible(),true,`Ayuda visible a ${width}px`);
   assert.equal(await guide.locator('.chat-last-close').isVisible(),true,`Último cierre visible a ${width}px`);
   const [guideBox,layoutBox,sidebarBox]=await Promise.all([
    guide.boundingBox(),page.locator('.chat-layout').boundingBox(),page.locator('.app-sidebar').boundingBox()
   ]);
   assert.ok(guideBox&&layoutBox,'La guía y su contenedor tienen dimensiones visibles');
   assert.ok(guideBox.x>=layoutBox.x-1&&guideBox.y>=layoutBox.y-1&&
    guideBox.x+guideBox.width<=layoutBox.x+layoutBox.width+1&&
    guideBox.y+guideBox.height<=layoutBox.y+layoutBox.height+1,`La guía permanece dentro del chat a ${width}px`);
   if(sidebarBox)assert.ok(guideBox.x>=sidebarBox.x+sidebarBox.width-1||
    guideBox.x+guideBox.width<=sidebarBox.x+1||guideBox.y>=sidebarBox.y+sidebarBox.height-1||
    guideBox.y+guideBox.height<=sidebarBox.y+1,`La guía no invade la navegación a ${width}px`);
  }
  await page.setViewportSize({width:1366,height:900});
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
  console.log('Consultas V21: regreso a Ventas, pestañas, teclado, enlaces, guía responsive, cierre histórico y fechas del chat correctos.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
