/* Ejecutar solo contra scripts/preview_ui.py. No puede modificar una web real. */
'use strict';
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const base='http://127.0.0.1:5018';
(async()=>{let browser;const errors=[];
 try{
  browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000}});
  page.on('pageerror',e=>errors.push(e.message));const response=await page.goto(base);
  assert.equal(response.headers()['x-cpstore-test-fixture'],'temporary-sqlite-loopback','No se encontró la base temporal; se cancela sin modificar datos');
  const viewportSizes=[{width:1440,height:1000},{width:1024,height:900},{width:390,height:844},{width:320,height:780}];
  for(const viewport of viewportSizes){
   await page.setViewportSize(viewport);await page.goto(base);
   const overflow=await page.evaluate(()=>({page:document.documentElement.scrollWidth,width:innerWidth}));
   assert.ok(overflow.page<=overflow.width+1,`Dashboard desbordado a ${viewport.width}px`);
   assert.equal(await page.locator('#dashboard-flow svg rect').count()>0,true);
   const sidebar=page.locator('.app-sidebar'),nav=sidebar.getByRole('navigation',{name:'Navegación principal'});
   if(viewport.width<1024){
    await page.getByRole('button',{name:'Abrir navegación',exact:true}).click();
    assert.equal(await sidebar.getAttribute('role'),'dialog');
    assert.equal(await page.locator('#contenido').evaluate(el=>el.inert),true);
    await page.getByRole('button',{name:'Cerrar navegación',exact:true}).click();
    assert.equal(await page.locator('#contenido').evaluate(el=>el.inert),false);
    await page.getByRole('button',{name:'Abrir navegación',exact:true}).click();
   }
   await nav.getByRole('link',{name:'Ventas y pagos',exact:true}).click();
   const table=page.locator('#ventas-tabla');assert.equal(await table.count(),1);
   const salesOverflow=await page.evaluate(()=>({page:document.documentElement.scrollWidth,width:innerWidth}));
   assert.ok(salesOverflow.page<=salesOverflow.width+1,`Ventas desbordadas a ${viewport.width}px`);
   assert.equal(await page.locator('.ui-status svg').count(),0,'Los estados deben mostrarse sin símbolos');
  }
  await page.setViewportSize({width:1440,height:900});await page.goto(base+'/ventas?saldo=1');
  const filter=page.locator('#ventas-filtro-local');await filter.fill('PREVIEW IPHONE');
  await page.locator('tbody tr').last().scrollIntoViewIfNeeded();
  const y=await page.evaluate(()=>scrollY);
  await page.locator('tbody tr').last().getByRole('link',{name:'Registrar abono'}).click();
  assert.equal(await page.locator('#operation-payment').isVisible(),true);
  await page.locator('.ui-back[data-app-back]').click();await page.waitForURL(base+'/ventas?saldo=1');
  assert.equal(await filter.inputValue(),'PREVIEW IPHONE');
  await page.waitForFunction(expected=>Math.abs(scrollY-expected)<10,y);
  // Registrar un abono de prueba en el servidor temporal, no en Render.
  await page.locator('tbody tr').first().getByRole('link',{name:'Registrar abono'}).click();
  const form=page.locator('#operation-payment form');await form.locator('[name=amount]').fill('50000');
  await form.locator('[name=destination]').selectOption('Negocio');
  await form.getByRole('button',{name:'Registrar cobro del cliente'}).click();
  await page.getByText('Movimiento comercial registrado. La disponibilidad está actualizada.').waitFor();
  // V18.1: contabilidad legible, filtros pertinentes y formularios sin acordeones.
  await page.goto(base+'/reportes?tipo=contable');
  assert.equal(await page.getByRole('columnheader',{name:'Banco destino',exact:true}).count(),1);
  assert.equal(await page.getByRole('cell',{name:'BANCO PRUEBA UI',exact:true}).count(),1);
  assert.equal(await page.getByRole('cell',{name:'$ 120.000,25',exact:true}).count(),1);
  for(const viewport of viewportSizes){
   await page.setViewportSize(viewport);
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Reporte desbordado a ${viewport.width}px`);
  }
  await page.setViewportSize({width:1440,height:900});
  await page.locator('#report-kind').selectOption('creditos');
  assert.equal(await page.locator('[name=aliado]').isVisible(),true);
  assert.equal(await page.locator('[name=ubicacion]').isDisabled(),true);
  await page.goto(base+'/finanzas');
  assert.equal(await page.locator('#operation-form').count(),0);
  assert.equal(await page.locator('.f-tabs').count(),0);
  await page.getByRole('link',{name:'Registrar movimiento',exact:true}).click();
  const movement=page.locator('#operation-form');
  assert.equal(await movement.evaluate(el=>el.closest('details')===null),true);
  assert.equal(await page.getByText('Costos y procedencia',{exact:true}).isVisible(),true);
  for(const viewport of viewportSizes){
   await page.setViewportSize(viewport);
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Formulario desbordado a ${viewport.width}px`);
  }
  await page.setViewportSize({width:1440,height:900});
  await movement.locator('[name=description]').fill('VENTA UI AUTOMATIZADA');
  await movement.locator('[name=seller]').selectOption('__other__');
  await movement.locator('[name=seller_other]').fill('PRUEBA UI');
  await movement.locator('[name=amount]').fill('50000');
  await movement.getByRole('button',{name:'Guardar movimiento',exact:true}).click();
  await page.getByText('Jornada actualizada.',{exact:true}).waitFor();
  assert.equal(await page.locator('.f-table').getByText('VENTA UI AUTOMATIZADA',{exact:true}).count(),1);
  assert.equal(errors.length,0,errors.join('\n'));
  console.log('UI: lateral, foco móvil, 4 tamaños, etiquetas, regreso/filtros y abono temporal correctos.');
 }finally{if(browser)await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
