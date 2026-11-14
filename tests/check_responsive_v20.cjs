/* Emulación de tamaños y entrada táctil. No equivale a hardware iOS/Android real.
 * Solo lee el servidor temporal: URL fija + cabecera obligatoria + bloqueo POST.
 */
'use strict';
const {chromium,webkit}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const base='http://127.0.0.1:5018',out=path.resolve('instance/responsive-v20');
const sizes=[
 ['compacto',320,780],['android-pequeno',360,800],['iphone-se',375,667],['iphone',390,844],
 ['android',412,915],['iphone-grande',430,932],['ipad',768,1024],['tablet',810,1080],
 ['tablet-horizontal',1024,768],['portatil',1366,768],['escritorio',1920,1080]
];
const routes=['/','/inventario','/inventario/nuevo','/inventario/lotes','/inventario/compras',
 '/inventario/articulos','/inventario/catalogos','/inventario/proveedores','/inventario/alias',
 '/inventario/1','/inventario/2','/ventas','/ventas/1','/ventas/2','/ventas/recepciones','/ventas/recepciones/1','/finanzas?tab=movimientos','/finanzas?accion=registrar',
 '/finanzas?accion=compra_pool','/finanzas?tab=proveedores','/finanzas?tab=personal','/finanzas?tab=cierre',
 '/finanzas/creditos','/ventas/sociedades','/reportes?tipo=inventario','/reportes?tipo=ventas',
 '/reportes?tipo=contable','/reportes/ventas?periodo=mes','/analitica','/chat','/modulos/tributario/',
 '/modulos/tributario/#personas','/modulos/tributario/#consignaciones','/gestion/historial',
 '/iniciar-sesion','/usuarios'];
const report={scope:'Solo SQLite temporal. Viewports y motores emulados; no dispositivos físicos.',checks:[],errors:[]};
fs.mkdirSync(out,{recursive:true});
(async()=>{
 const fixture=await fetch(base+'/healthz',{signal:AbortSignal.timeout(5000)});
 assert.equal(fixture.headers.get('x-cpstore-test-fixture'),'temporary-sqlite-loopback','Se cancela: inicia scripts/preview_ui.py, no una instalación real');
 for(const [engine,launcher] of [['chromium',chromium],['webkit',webkit]]){
  const browser=await launcher.launch({headless:true});
  try{
   for(const [label,width,height] of sizes.filter(s=>engine==='chromium'||[375,390,430,768,810,1024].includes(s[1]))){
    const context=await browser.newContext({viewport:{width,height},locale:'es-CO',timezoneId:'America/Bogota',isMobile:width<=1024,hasTouch:width<=1024,deviceScaleFactor:width===375?2:width<600?3:width<=1024?2:1});
    await context.route('**/*',route=>['GET','HEAD','OPTIONS'].includes(route.request().method())?route.continue():route.abort());
    const page=await context.newPage(),errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('dialog',dialog=>dialog.type()==='beforeunload'?dialog.accept():dialog.dismiss());
    try{
     for(const url of routes){
      const startErrors=errors.length;
      try{
       const response=await page.goto(base+url,{waitUntil:'networkidle',timeout:30000});
       if(response){
        assert.equal(response.status(),200,`HTTP ${response.status()}`);
        assert.equal(response.headers()['x-cpstore-test-fixture'],'temporary-sqlite-loopback','Se cancela: no es el servidor temporal');
       }else{assert.equal(new URL(page.url()).origin,base,'El cambio de sección conserva el servidor temporal');}
       if(url.startsWith('/modulos/tributario/#'))await page.locator('#'+url.split('#')[1]).waitFor({state:'visible'});
       if(url==='/usuarios'){
        await page.locator('#crear-usuario>summary').click();
        const form=page.locator('#crear-usuario form');
        await form.locator('[name=role]').selectOption('Administrador');
        await form.locator('[name=permission_mode]').selectOption('personalizado');
        await form.locator('[value="ventas.ver"]').uncheck();
        await form.locator('[value="ventas.cobrar"]').check();
        assert.equal(await form.locator('[value="ventas.ver"]').isChecked(),true,'La acción activa la consulta');
        assert.equal(await form.locator('[value="usuarios.administrar"]').isEnabled(),false,'No permite elevar el perfil');
       }
       if(url==='/chat'){
        await page.locator('#chat-periodo').selectOption('rango');
        assert.equal(await page.locator('#chat-desde').isVisible(),true,'Las fechas se pueden elegir');
       }
       const metrics=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,
        main:!!document.querySelector('main'),viewport:!!document.querySelector('meta[name=viewport]')}));
       assert.ok(metrics.viewport&&metrics.main,'Estructura responsive incompleta');
       assert.ok(metrics.scroll<=metrics.width+1,`Desbordamiento horizontal: ${metrics.scroll} > ${metrics.width}`);
       if(url==='/'&&width<1024){
        await page.getByRole('button',{name:'Abrir navegación',exact:true}).click();
        assert.equal(await page.locator('.app-sidebar').getAttribute('role'),'dialog');
        await page.keyboard.press('Escape');
        assert.equal(await page.locator('#contenido').evaluate(el=>el.inert),false);
       }
       assert.deepEqual(errors.slice(startErrors),[],'Errores JavaScript');
       if(['/usuarios','/modulos/tributario/','/modulos/tributario/#personas','/modulos/tributario/#consignaciones','/chat','/analitica','/finanzas?accion=registrar'].includes(url)&&[390,768,1366].includes(width)){
        const name=url==='/usuarios'?'usuarios':url.startsWith('/modulos')?'contabilidad-'+(url.split('#')[1]||'consolidado'):url==='/chat'?'chat':url==='/analitica'?'analitica':'finanzas';
        await page.screenshot({path:path.join(out,`${engine}-${width}-${name}.png`),fullPage:false});
       }
       report.checks.push({engine,label,width,height,url,ok:true});
      }catch(error){
       report.checks.push({engine,label,width,height,url,ok:false,error:error.message});
       report.errors.push({engine,label,url,error:error.message});
       await page.screenshot({path:path.join(out,`fallo-${engine}-${width}-${report.checks.length}.png`),fullPage:false}).catch(()=>{});
       if(report.errors.length>=15)throw new Error('Se detiene la revisión tras 15 fallos. Revisa resultado.json y las capturas.');
      }
     }
    }finally{await context.close();}
   }
  }finally{await browser.close();}
 }
})().catch(error=>{report.errors.push({error:error.message});}).finally(()=>{
 fs.writeFileSync(path.join(out,'resultado.json'),JSON.stringify(report,null,2));
 console.log(`${report.checks.filter(c=>c.ok).length}/${report.checks.length} páginas/tamaños correctos; ${report.errors.length} fallos.`);
 if(report.errors.length){console.error(JSON.stringify(report.errors,null,2));process.exitCode=1;}
});
