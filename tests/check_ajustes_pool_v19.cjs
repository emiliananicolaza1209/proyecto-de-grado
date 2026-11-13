/* Solo contra scripts/preview_ui.py y su base SQLite temporal. */
'use strict';
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const base='http://127.0.0.1:5018';
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const response=await page.goto(base+'/finanzas?accion=compra_pool');
  assert.equal(response.headers()['x-cpstore-test-fixture'],'temporary-sqlite-loopback','No es la base de ensayo: se cancela');
  const form=page.locator('#pool-purchase-form');
  assert.equal(await form.locator('[name=product_id]').count(),0);
  const catalog=JSON.parse(await page.locator('#catalog-data').textContent());
  const reference=catalog.find(x=>x.kind==='reference'&&catalog.some(y=>y.kind==='color'&&y.parent_id===x.id)&&catalog.some(y=>y.kind==='capacity'&&y.parent_id===x.id));
  await form.locator('[name=imei]').fill('990000000001232');
  await form.locator('#brand').selectOption(String(reference.parent_id));
  await form.locator('#model-search').fill(reference.name);
  await form.locator('#model-options [role=option]').filter({hasText:reference.name}).first().click();
  await form.locator('#color').selectOption(String(catalog.find(x=>x.kind==='color'&&x.parent_id===reference.id).id));
  await form.locator('#capacity').selectOption(String(catalog.find(x=>x.kind==='capacity'&&x.parent_id===reference.id).id));
  await form.locator('[name=location_id]').selectOption(String(catalog.find(x=>x.kind==='location'&&!x.name.toUpperCase().includes('BODEGA')).id));
  await form.locator('[name=seller]').selectOption({label:'PRUEBA'});
  for(const [name,value] of Object.entries({purchase_cop:'500000',purchase_gain:'100000',purchase_commission:'20000',funding:'620000'}))await form.locator(`[name=${name}]`).fill(value);
  assert.match(await page.locator('#pool-purchase-preview').textContent(),/600\.000/);
  for(const width of [1440,1024,390,320]){
   await page.setViewportSize({width,height:900});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Compra POOL desbordada a ${width}px`);
  }
  await page.setViewportSize({width:1440,height:1000});
  await form.locator('[name=confirmed]').check();
  await form.getByRole('button',{name:'Guardar compra y equipo',exact:true}).click();
  await page.getByText('Jornada actualizada.',{exact:true}).waitFor();
  assert.equal(await page.locator('#revision-pool').count(),1);
  await page.getByRole('link',{name:'Registrar movimiento',exact:true}).click();
  const sale=page.locator('#operation-form');
  await sale.locator('[name=description]').fill('POOL AJUSTES UI');
  await sale.locator('[name=seller]').selectOption({label:'PRUEBA'});
  await sale.locator('[name=amount]').fill('1100000');
  await page.locator('#add-cost').click();const cost=sale.locator('.f-cost-row');
  await cost.locator('[name=cost_type]').selectOption('Equipo');
  await cost.locator('[name=cost_name]').fill('990000000001232');
  await cost.locator('[name=cost_name]').press('Tab');
  await cost.locator('[name=cost_unit]').fill('800000');
  const payment=sale.locator('.f-payment-row');await payment.locator('[name=payment_account]').selectOption('CRÉDITO');
  await payment.locator('[name=payment_ally_id]').selectOption({label:'SU+PAY'});
  await payment.locator('[name=payment_person_id]').selectOption({label:'TITULAR PRUEBA UI · 00000001'});
  await payment.locator('[name=payment_bank_id]').selectOption({label:'BANCO PRUEBA UI'});
  await payment.locator('[name=payment_credit_rate]').fill('18');
  assert.equal((await page.locator('#preview-margin').textContent()).replace(/\D/g,''),'82000');
  assert.equal(await payment.locator('.credit-net-field').isVisible(),false);
  await payment.locator('[name=payment_credit_mode]').selectOption('Neto pactado');
  await payment.locator('[name=payment_credit_net]').fill('902000');
  assert.equal(await payment.locator('.credit-rate-field').isVisible(),false);
  assert.equal((await page.locator('#preview-margin').textContent()).replace(/\D/g,''),'82000');
  const approved=sale.locator('[name=credit_approved]');
  assert.equal(await approved.isVisible(),true);
  assert.ok(await sale.evaluate(form=>!!(form.querySelector('.f-preview').compareDocumentPosition(form.querySelector('.f-credit-approved'))&Node.DOCUMENT_POSITION_FOLLOWING)));
  await approved.check();await sale.getByRole('button',{name:'Guardar movimiento',exact:true}).click();
  await page.getByText('Jornada actualizada.',{exact:true}).waitFor();
  assert.equal(await page.locator('.f-table').getByText('POOL AJUSTES UI',{exact:true}).count(),1);
  assert.equal(errors.length,0,errors.join('\n'));
  console.log('Ajustes POOL: compra sin alta previa, revisión, 4 tamaños, costo comercial, comisión y crédito correctos.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
