(()=>{'use strict';
const $=s=>document.querySelector(s);
const number=v=>Number(String(v||'').replace(',','.'))||0;
const money=n=>new Intl.NumberFormat('es-CO',{style:'currency',currency:'COP',maximumFractionDigits:0}).format(n||0);
function row(kind,target){const el=document.createElement('div');el.className=kind==='cost'?'f-cost-row':'f-staff-row';
el.innerHTML=kind==='cost'?`<label>Tipo<select name="cost_type"><option>Proveedor</option><option>Fondo</option><option>Equipo</option><option>Bebida</option><option>Artículo</option></select></label><label>Procedencia / bebida<input name="cost_name" list="provider-options" maxlength="120" required></label><label class="f-cost-detail" hidden>Detalle de Otros<input name="cost_detail" maxlength="300" placeholder="Ej. Domicilio o bebida obsequiada"></label><label>Clase<select name="cost_category"><option value="">Según proveedor</option><option>Celulares</option><option>Accesorios</option><option>Servicio técnico</option></select></label><label class="f-external-imei" hidden>IMEI equipo externo<input name="cost_external_imei" inputmode="numeric" pattern="[0-9]{15}" maxlength="15" placeholder="15 dígitos"></label><label>Cantidad<input name="cost_qty" type="text" inputmode="numeric" pattern="[0-9]+" value="1" required></label><label>Costo unitario · COP<input name="cost_unit" type="text" inputmode="decimal" pattern="[0-9]+([.,][0-9]{1,2})?" required></label><button type="button" class="btn-secondary remove-row">Quitar</button>`:`<label>Nombre<input name="staff_name" maxlength="120" required></label><label>Función<select name="staff_role"><option>Principal</option><option>Secundaria</option></select></label><label>Sueldo del día · COP<input name="staff_salary" type="text" inputmode="decimal" pattern="[0-9]+([.,][0-9]{1,2})?" required></label><label class="f-check"><input class="staff-attended" name="staff_attended" type="checkbox" checked> Asistió</label><button type="button" class="btn-secondary remove-row">Quitar</button>`;
(target||$(kind==='cost'?'#cost-rows':'#staff-rows'))?.append(el);if(kind==='cost')costType(el);refreshIndices();return el;}
function refreshIndices(){document.querySelectorAll('#staff-rows .f-staff-row').forEach((r,i)=>r.querySelector('.staff-attended').value=String(i));}
$('#add-cost')?.addEventListener('click',()=>{const target=$('#cost-rows');if(target&&target.children.length<8)row('cost',target);});
$('#add-staff')?.addEventListener('click',()=>row('staff'));
document.addEventListener('click',e=>{if(e.target.closest('.add-linked-cost')){const target=e.target.closest('form').querySelector('.linked-cost-rows');if(target.children.length<8)row('cost',target);}if(e.target.closest('.remove-row')){e.target.closest('.f-cost-row,.f-staff-row').remove();refreshIndices();preview();}if(e.target.closest('.add-payment')){const list=e.target.closest('form').querySelector('.f-payment-list');if(list.children.length>=5)return;const copy=list.firstElementChild.cloneNode(true);copy.querySelectorAll('input').forEach(input=>input.value='');copy.querySelectorAll('select').forEach(select=>{select.selectedIndex=0;select.disabled=false;});copy.querySelector('label').firstChild.textContent='Medio '+(list.children.length+1);list.append(copy);updateChoices();filterBankChoices();}if(e.target.closest('.remove-payment')){const list=e.target.closest('.f-payment-list');if(list.children.length<=1)return; e.target.closest('.f-payment-row').remove();list.querySelectorAll('.f-payment-row').forEach((r,i)=>r.querySelector('label').firstChild.textContent='Medio '+(i+1));preview();}});
function preview(){
 const f=$('#operation-form');if(!f)return;
 const sale=f.elements.kind.value==='Venta';
 f.querySelectorAll('[data-sale]').forEach(x=>{x.hidden=!sale;x.querySelectorAll('input,select').forEach(i=>i.disabled=!sale);});
 const cents=v=>Math.round(number(v)*100);
 const entered=cents(f.elements.amount.value);
 let cost=0;
 f.querySelectorAll('.f-cost-row').forEach(r=>cost+=number(r.querySelector('[name=cost_qty]').value)*cents(r.querySelector('[name=cost_unit]').value));
 let gross=0,net=0;
 f.querySelectorAll('.f-payment-row').forEach(r=>{
  const paid=cents(r.querySelector('[name=payment_amount]').value);
  gross+=paid;
  const kind=r.querySelector('[name=payment_account]').value;let received=paid;if(sale&&kind==='DATÁFONO')received=Math.round(paid/1.05);if(sale&&kind==='CRÉDITO'){const mode=r.querySelector('[name=payment_credit_mode]').value,ally=r.querySelector('[name=payment_ally_id]').selectedOptions[0];received=mode==='Neto pactado'?cents(r.querySelector('[name=payment_credit_net]').value):Math.round(paid*(1-number(r.querySelector('[name=payment_credit_rate]').value||ally?.dataset.rate)/100));}net+=received;
 });
 const inputIsGross=sale&&gross>net&&entered===gross;
 const saleNet=inputIsGross?net:entered;
 $('#preview-margin').textContent=sale?money((saleNet-cost)/100):'GASTO / MOVIMIENTO';
 $('#preview-balance').textContent=money((sale? saleNet-net : entered-gross)/100);
 const fee=$('#preview-card-fee');if(fee){fee.hidden=!sale||gross===net;fee.querySelector('strong').textContent=money((gross-net)/100);}
 const netLine=$('#preview-sale-net');if(netLine){netLine.hidden=!sale||gross===net;netLine.querySelector('strong').textContent=money(saleNet/100);}
}

$('#operation-form')?.addEventListener('input',preview);
const providerCategories=JSON.parse($('#finance-provider-categories')?.textContent||'{}');
const drinkPrices=JSON.parse($('#finance-drink-prices')?.textContent||'{}');
const stockCosts=JSON.parse($('#finance-stock-costs')?.textContent||'{}');
const equipmentCosts=JSON.parse($('#finance-equipment-costs')?.textContent||'{}');
function costType(row){const type=row.querySelector('[name=cost_type]').value;const input=row.querySelector('[name=cost_name]');input.setAttribute('list',({Proveedor:'provider-options',Fondo:'fund-options',Equipo:'equipment-options',Bebida:'drink-options',Artículo:'stock-options'})[type]);input.placeholder=({Proveedor:'Buscar proveedor registrado',Fondo:'Seleccionar fondo',Equipo:'Buscar IMEI disponible',Bebida:'Nombre de bebida',Artículo:'Selecciona artículo o ID/SERIAL'})[type];const other=['OTRO','OTROS'].includes(input.value.trim().toUpperCase());const detail=row.querySelector('.f-cost-detail');if(detail){detail.hidden=!other;detail.querySelector('input').required=other;}const category=row.querySelector('[name=cost_category]');if(category){if(type==='Equipo')category.value='Celulares';else if(type==='Bebida'||type==='Fondo')category.value='Accesorios';else if(providerCategories[input.value])category.value=providerCategories[input.value]==='Ambos'?(category.value||''):providerCategories[input.value];}const imei=row.querySelector('.f-external-imei');if(imei){const external=type==='Proveedor'&&category?.value==='Celulares';imei.hidden=!external;imei.querySelector('input').required=external&&!!row.closest('#operation-form');}const price=row.querySelector('[name=cost_unit]');if(type==='Bebida'&&drinkPrices[input.value]!=null)price.value=drinkPrices[input.value]/100;if(type==='Artículo'){const val=stockCosts[input.value.split('/')[0]];if(val!=null)price.value=val/100;}const equipment=equipmentCosts[input.value];if(type==='Equipo'&&equipment){price.value=equipment.purchase/100;price.closest('label').firstChild.textContent=equipment.pool?'Costo asignado POOL · COP (mín. compra)':'Costo unitario · COP';price.title=equipment.pool?'Valor asignado por administración; la diferencia sobre la compra se reserva para el POOL.':'';}else price.closest('label').firstChild.textContent='Costo unitario · COP';price.readOnly=type==='Artículo'||(type==='Bebida'&&!other)||(type==='Equipo'&&equipment&&!equipment.pool);}
document.querySelectorAll('.f-cost-row').forEach(costType);
document.addEventListener('change',e=>{if(e.target.name==='cost_type'){const r=e.target.closest('.f-cost-row');r.querySelector('[name=cost_name]').value='';r.querySelector('[name=cost_category]').value='';costType(r);}if(e.target.name==='cost_category'){const r=e.target.closest('.f-cost-row'),label=r.querySelector('.f-external-imei');if(label){const external=r.querySelector('[name=cost_type]').value==='Proveedor'&&e.target.value==='Celulares';label.hidden=!external;label.querySelector('input').required=external&&!!r.closest('#operation-form');}}if(e.target.name==='cost_name'){const r=e.target.closest('.f-cost-row');e.target.value=e.target.value.trim().toUpperCase();r.querySelector('[name=cost_category]').value='';costType(r);preview();}});
// Completar primer medio solo hasta que el usuario lo ajuste.
let paymentEdited=false;$('#operation-form')?.addEventListener('input',e=>{if(e.target.name==='payment_amount')paymentEdited=true;});
$('#operation-form [name=amount]')?.addEventListener('input',e=>{if(!paymentEdited){$('#operation-form [name=payment_amount]').value=e.target.value;preview();}});
$('#finance-search')?.addEventListener('input',e=>{const q=e.target.value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();document.querySelectorAll('[data-search]').forEach(r=>r.hidden=!r.dataset.search.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().includes(q));});
const restore=$('#finance-restore');if(restore){const data=JSON.parse(restore.textContent);const f=[...document.querySelectorAll('.finance form')].find(f=>f.elements.action?.value===data.action?.[0]&&(!data.operation_id||f.elements.operation_id?.value===data.operation_id[0])&&(!data.commission_id||f.elements.commission_id?.value===data.commission_id[0]));if(f){if(data.action[0]==='operation')(data.cost_name||[]).forEach(()=>row('cost'));if(data.action[0]==='equipment_costs'){const target=f.querySelector('.linked-cost-rows');target.replaceChildren();(data.cost_name||[]).forEach(()=>row('cost',target));}if(data.action[0]==='config'){$('#staff-rows').replaceChildren();(data.staff_name||[]).forEach(()=>row('staff'));}const list=f.querySelector('.f-payment-list');if(list){while(list.children.length<(data.payment_amount||[]).length&&list.children.length<5)f.querySelector('.add-payment')?.click();}const idx={};for(const el of f.elements){if(!el.name||['csrf','revision','token','action'].includes(el.name))continue;const i=idx[el.name]||0;idx[el.name]=i+1;if(el.type==='checkbox')el.checked=(data[el.name]||[]).includes(el.value);else if(data[el.name]?.[i]!==undefined)el.value=data[el.name][i];}f.querySelectorAll('.f-cost-row').forEach(costType);f.closest('details')?.setAttribute('open','');}}
function updateChoices(){
 document.querySelectorAll('select[name="seller"]').forEach(el=>{
  const extra=el.parentElement.querySelector('[name="seller_other"]');if(!extra)return;
  const other=el.value==='__other__';extra.hidden=!other;extra.required=other;extra.disabled=!other;
 });
 document.querySelectorAll('select[name="payment_account"],select[name="account"]').forEach(el=>{
  const group=el.closest('.f-payment-row')||el.closest('form');
  const person=group?.querySelector('[name="payment_person_id"]'),bank=group?.querySelector('[name="payment_bank_id"]');
  const credits=group?.querySelector('.f-credit-fields');
  if(credits){credits.hidden=el.value!=='CRÉDITO';credits.querySelectorAll('input,select').forEach(i=>i.required=i.name==='payment_ally_id'&&el.value==='CRÉDITO');}
  const retoma=group?.querySelector('.f-retoma-field');
  if(retoma){retoma.hidden=el.value!=='RETOMA';retoma.querySelector('select').required=el.value==='RETOMA';}
  const approved=group?.closest('form')?.querySelector('.f-credit-approved');
  if(approved){const needed=[...group.closest('form').querySelectorAll('[name=payment_account]')].some(s=>s.value==='CRÉDITO');approved.hidden=!needed;approved.querySelector('input').required=needed;}

  const amount=group?.querySelector('[name="payment_amount"]')||group?.querySelector('[name="amount"]');
  for(const [field,enabled] of [[person,el.value==='TRANSFERENCIA'||el.value==='DATÁFONO'||el.value==='CRÉDITO'],[bank,el.value==='TRANSFERENCIA'||el.value==='CRÉDITO']]){
   if(!field)continue;field.closest('label').hidden=!enabled;field.disabled=!enabled;
   field.required=enabled && (amount ? Number(amount.value)>0 : true);
   if(!enabled)field.value='';
  }
 });
}
const bankLinks=JSON.parse(document.querySelector('#finance-person-banks')?.textContent||'{}');
function filterBankChoices(){document.querySelectorAll('select[name="payment_person_id"]').forEach(person=>{
 const group=person.closest('.f-payment-row')||person.closest('form');const bank=group?.querySelector('select[name="payment_bank_id"]');if(!bank)return;
 const allowed=(bankLinks[person.value]||[]).map(String);const chosen=bank.value;
 for(const option of bank.options){option.hidden=!!option.value&&!allowed.includes(option.value);option.disabled=!!option.value&&!allowed.includes(option.value);}
 if(!allowed.includes(chosen))bank.value='';
 if(person.disabled||!person.value||!allowed.length)bank.disabled=true;
 });}
document.addEventListener('change',e=>{if(e.target.name==='payment_ally_id'){const r=e.target.closest('.f-payment-row'),o=e.target.selectedOptions[0];r.querySelector('[name=payment_credit_rate]').value=o.dataset.rate||'';r.querySelector('[name=payment_person_id]').value=o.dataset.person||'';r.querySelector('[name=payment_bank_id]').value=o.dataset.bank||'';}updateChoices();filterBankChoices();preview();});
document.addEventListener('wheel',e=>{if(e.target.matches('.finance input[type="number"]')&&document.activeElement===e.target)e.target.blur();},{passive:true});
document.addEventListener('input',e=>{if(e.target.name==='payment_amount')updateChoices()});
document.querySelectorAll('.finance form').forEach(form=>form.addEventListener('submit',()=>{
  // Conserva una casilla vacía por medio para alinear persona y banco con el importe.
  form.querySelectorAll('.f-payment-row select:disabled').forEach(select=>{select.disabled=false;select.required=false;});
}));
const countedInput=document.querySelector('.f-close [name="counted"]');
function countedDifference(){const box=$('#counted-difference');if(!box||!countedInput)return;if(!countedInput.value.trim()){box.textContent='Ingresa el efectivo contado para ver la diferencia.';box.className='f-cash-difference';return;}const diff=Math.round(number(countedInput.value)*100)-Number(box.dataset.expected);box.className='f-cash-difference '+(diff<0?'f-short':diff>0?'f-over':'f-even');box.textContent=diff<0?'Faltan '+money(-diff/100):diff>0?'Sobran '+money(diff/100):'Caja exacta: sin diferencia.';}
countedInput?.addEventListener('input',countedDifference);countedDifference();
refreshIndices();preview();updateChoices();filterBankChoices();
})();

// Compra POOL: origen y cálculo informativo. El servidor valida los importes.
(()=>{
 const form=document.querySelector('#pool-purchase-form');if(!form)return;
 const output=document.querySelector('#pool-purchase-preview');
 const format=cents=>new Intl.NumberFormat('es-CO',{style:'currency',currency:'COP',minimumFractionDigits:0,maximumFractionDigits:2}).format(cents/100);
 function update(){
  const partial=form.elements.purchase_mode.value==='Parte de pago';
  form.querySelector('[data-pool-origin]').hidden=!partial;
  form.elements.origin_sale_id.disabled=!partial;form.elements.origin_sale_id.required=partial;
  const option=form.elements.product_id.selectedOptions[0];
  const value=form.elements.funding.value.trim();
  if(!option?.value||!value){output.textContent='Selecciona el equipo e ingresa el aporte para consultar la ganancia.';return;}
  const amount=Number(value.replace(',','.'));
  if(!Number.isFinite(amount)){output.textContent='Revisa el valor del aporte.';return;}
  const cost=Number(option.dataset.cost),client=Number(option.dataset.client);
  const gain=Math.round(amount*100)-cost;
  output.textContent='Compra al cliente: '+format(client)+' · Otros costos: '+format(cost-client)+' · Ganancia de compra: '+format(gain)+(gain<0?' · El aporte no cubre compra y costos.':'');
 }
 form.addEventListener('input',update);form.addEventListener('change',update);update();
 if(location.hash==='#compra-pool')form.closest('details')?.setAttribute('open','');
})();

if(new URL(location.href).searchParams.has("accion")){history.scrollRestoration="manual";requestAnimationFrame(()=>window.scrollTo(0,0));}

// Un solo formulario de pagos para todos los sueldos y comisiones habituales.
(()=>{
 const form=document.querySelector('#pago-personal-form');if(!form)return;
 const choice=form.elements.staff_choice,amount=form.elements.amount;
 function select(value){if(value)choice.value=value;amount.value=choice.selectedOptions[0]?.dataset.amount||'';}
 if(!amount.value&&!document.querySelector('#finance-restore'))select();
 for(const link of document.querySelectorAll('.f-select-staff'))link.addEventListener('click',event=>{
  if(event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
  event.preventDefault();select(link.dataset.choice);form.dispatchEvent(new Event('cpstore:form-ready',{bubbles:true}));form.hidden=false;form.scrollIntoView({block:'nearest'});amount.focus({preventScroll:true});
 });
 choice.addEventListener('change',()=>select());
 document.querySelector('#cancel-staff-payment')?.addEventListener('click',()=>{
  form.reset();select();form.elements.payment_account.dispatchEvent(new Event('change',{bubbles:true}));form.dispatchEvent(new Event('cpstore:form-ready',{bubbles:true}));form.hidden=true;document.querySelector('.f-select-staff')?.focus();
 });
})();

(()=>{
 for(const form of document.querySelectorAll('.f-pool-payment')){
  function update(){form.elements.reference.required=form.elements.payment_source.value==='ADMINISTRACIÓN DIRECTA';}
  form.elements.payment_source.addEventListener('change',update);update();
 }
 const form=document.querySelector('#pool-purchase-form');if(!form)return;
 form.elements.product_id.addEventListener('change',()=>{
  const selected=form.elements.product_id.selectedOptions[0];
  for(const box of form.querySelectorAll('[data-pool-cost]'))box.hidden=box.dataset.poolCost!==selected?.value;
  if(selected?.value&&!form.elements.funding.value){form.elements.funding.value=String(Number(selected.dataset.cost)/100);form.dispatchEvent(new Event('input',{bubbles:true}));}
 });
 for(const box of form.querySelectorAll('[data-pool-cost]'))box.hidden=box.dataset.poolCost!==form.elements.product_id.value;
})();
