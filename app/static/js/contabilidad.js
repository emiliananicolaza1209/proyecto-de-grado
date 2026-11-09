document.addEventListener('change',event=>{const campo=event.target;if(campo.matches&&campo.matches('select[data-autosubmit]'))campo.form.submit();});
(()=>{'use strict';
const byId=id=>document.getElementById(id);
const links=JSON.parse(byId('person-bank-data')?.textContent||'{}');
const bankNames=JSON.parse(byId('bank-names')?.textContent||'{}');
const personForm=byId('accounting-person-form'),name=byId('person-name'),documentId=byId('person-id');
const alertBox=byId('person-match-alert'),confirm=byId('person-confirm'),save=byId('person-save');
const bankPerson=byId('bank-person'),tags=byId('person-banks');
let timer,requestNo=0;
function renderBanks(){const ids=links[bankPerson.value]||[];tags.replaceChildren();
  if(!bankPerson.value)return;
  if(!ids.length){tags.textContent='Todavía no tiene bancos asociados.';return;}
  ids.forEach(id=>{const chip=document.createElement('span');chip.className='accounting-tag';chip.textContent=bankNames[id]||'Banco';tags.append(chip);});
}
function selectPerson(id){bankPerson.value=String(id);renderBanks();bankPerson.focus();byId('asociar-banco').scrollIntoView({behavior:'smooth',block:'center'});}
document.addEventListener('click',event=>{const link=event.target.closest('[data-select-person]');if(link)selectPerson(link.dataset.selectPerson);});
bankPerson?.addEventListener('change',renderBanks);renderBanks();
const existing=byId('existing-bank'),newBank=byId('new-bank');
existing?.addEventListener('change',()=>{if(existing.value)newBank.value='';});
newBank?.addEventListener('input',()=>{if(newBank.value)existing.value='';});
document.querySelectorAll('.accounting-person-select').forEach(person=>{
  const bank=person.closest('form').querySelector('.accounting-bank-select');
  if(!bank)return;
  function refresh(){const allowed=(links[person.value]||[]).map(String);const chosen=bank.value;
    for(const option of bank.options){option.hidden=!!option.value&&!allowed.includes(option.value);option.disabled=!!option.value&&!allowed.includes(option.value);}
    if(!allowed.includes(chosen))bank.value='';bank.disabled=!person.value||!allowed.length;
  }
  person.addEventListener('change',refresh);refresh();
});
function showMatches(data){
  const exact=data.exact||[],similar=data.similar||[];
  alertBox.replaceChildren();alertBox.hidden=!exact.length&&!similar.length;
  alertBox.classList.toggle('danger',!!exact.length);
  confirm.hidden=!similar.length||!!exact.length;
  save.disabled=!!exact.length;
  if(exact.length){const person=exact[0];alertBox.append(document.createTextNode(`La identificación ya pertenece a ${person.nombre} (${person.identificacion}). No crees otra ficha. `));
    const link=document.createElement('a');link.href='#asociar-banco';link.dataset.selectPerson=person.id;link.textContent='Agregarle otro banco';alertBox.append(link);
  }else if(similar.length){alertBox.textContent='Nombre igual o parecido a: '+similar.map(p=>`${p.nombre} (${p.identificacion})`).join(', ')+'. Compara la cédula; si corresponde a otra persona, confirma antes de guardar.';}
}
async function check(){const seq=++requestNo,n=name.value.trim(),id=documentId.value.trim();
  if(n.length<3&&id.length<3){showMatches({});return;}
  try{const response=await fetch('/modulos/tributario/personas/verificar?'+new URLSearchParams({nombre:n,identificacion:id}),{headers:{Accept:'application/json'}});
    if(!response.ok)return;const result=await response.json();if(seq===requestNo)showMatches(result);
  }catch(_error){alertBox.hidden=true;save.disabled=false;confirm.hidden=true;}
}
personForm?.addEventListener('input',event=>{if(event.target!==name&&event.target!==documentId)return;clearTimeout(timer);timer=setTimeout(check,260);});
if(name?.value||documentId?.value)check();
document.querySelectorAll('[data-width]').forEach(bar=>{bar.style.width=Math.min(100,Math.max(0,Number(bar.dataset.width)||0))+'%';});
})();

// Desglose por banco: cambia de persona sin recargar ni modificar consignaciones.
(()=>{'use strict';
 const details=document.getElementById('desglose-bancos');
 const form=document.getElementById('bank-breakdown-form');
 const select=document.getElementById('bank-breakdown-person');
 if(!details||!form||!select)return;
 const panels=[...details.querySelectorAll('[data-bank-person]')];
 function show(id,focus=false){
  const selected=panels.find(panel=>panel.dataset.bankPerson===String(id));
  if(!selected)return;
  select.value=String(id);panels.forEach(panel=>panel.hidden=panel!==selected);details.open=true;
  const url=new URL(location.href);url.searchParams.set('detalle_bancos',String(id));
  url.searchParams.set('anio',form.elements.anio.value);url.hash='desglose-bancos';
  history.replaceState(null,'',url);
  if(focus){selected.querySelector('h3').focus({preventScroll:true});details.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});}
 }
 select.addEventListener('change',()=>show(select.value));
 form.addEventListener('submit',event=>{event.preventDefault();show(select.value);});
 document.addEventListener('click',event=>{
  const link=event.target.closest('[data-bank-breakdown-person]');
  if(!link||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
  event.preventDefault();show(link.dataset.bankBreakdownPerson,true);
 });
 const yearSelect=document.querySelector('.accounting-year select');
 if(yearSelect){
  const carry=document.createElement('input');carry.type='hidden';carry.name='detalle_bancos';
  carry.value=select.value;carry.disabled=!details.open;yearSelect.form.append(carry);
  details.addEventListener('toggle',()=>carry.disabled=!details.open);
  select.addEventListener('change',()=>carry.value=select.value);
  document.addEventListener('click',event=>{if(event.target.closest('[data-bank-breakdown-person]'))carry.value=select.value;});
 }
})();
