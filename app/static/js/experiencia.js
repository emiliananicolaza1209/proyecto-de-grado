(()=>{'use strict';
const menu=document.querySelector('.app-menu-toggle'),sidebar=document.querySelector('.app-sidebar'),close=document.querySelector('.sidebar-close'),backdrop=document.querySelector('.sidebar-backdrop'),main=document.querySelector('#contenido'),mobile=window.matchMedia('(max-width:1023px)');
let lastFocus=null;
function setMenu(open){
 if(!sidebar||!mobile.matches)open=false;
 sidebar?.classList.toggle('nav-open',open);menu?.setAttribute('aria-expanded',String(open));
 if(backdrop)backdrop.hidden=!open;if(main)main.inert=open;
 document.body.style.overflow=open?'hidden':'';
 if(open){lastFocus=document.activeElement;sidebar.setAttribute('role','dialog');sidebar.setAttribute('aria-modal','true');close?.focus();}
 else{sidebar?.removeAttribute('role');sidebar?.removeAttribute('aria-modal');if(lastFocus&&lastFocus.isConnected){lastFocus.focus();lastFocus=null;}}
}
menu?.addEventListener('click',()=>setMenu(!sidebar?.classList.contains('nav-open')));close?.addEventListener('click',()=>setMenu(false));backdrop?.addEventListener('click',()=>setMenu(false));
mobile.addEventListener('change',()=>setMenu(false));window.addEventListener('pageshow',()=>setMenu(false));
document.addEventListener('keydown',e=>{
 if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();document.querySelector('#quick-imei')?.focus();}
 if(e.key==='Escape'&&sidebar?.classList.contains('nav-open'))setMenu(false);
 if(e.key==='Tab'&&sidebar?.classList.contains('nav-open')){
  const items=[...sidebar.querySelectorAll('a[href],button:not([disabled]),input:not([type="hidden"])')].filter(el=>el.getClientRects().length);
  if(!items.length)return;
  if(e.shiftKey&&document.activeElement===items[0]){e.preventDefault();items.at(-1).focus();}
  else if(!e.shiftKey&&document.activeElement===items.at(-1)){e.preventDefault();items[0].focus();}
 }
});
// Prevenir doble envío de acciones que mueven inventario o dinero.
document.querySelectorAll('form[method="post"]').forEach(form=>form.addEventListener('submit',e=>{if(!form.checkValidity())return;if(form.dataset.submitting==='true'){e.preventDefault();return;}form.dataset.submitting='true';const submit=e.submitter;if(submit){submit.setAttribute('aria-disabled','true');submit.classList.add('is-submitting');}setTimeout(()=>{form.dataset.submitting='false';if(submit){submit.removeAttribute('aria-disabled');submit.classList.remove('is-submitting');}},12000);}));
})();
(()=>{'use strict';
const normalize=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
document.querySelectorAll('[data-filter-table]').forEach(input=>{
 const table=document.getElementById(input.dataset.filterTable);if(!table)return;
 const rows=[...table.querySelectorAll('tbody tr:not(.no-data)')];const feedback=document.getElementById(table.id+'-count');const empty=document.getElementById(table.id.replace('-tabla','-empty-filter'));
 function filter(){let shown=0;for(const row of rows){row.hidden=!normalize(row.textContent).includes(normalize(input.value.trim()));if(!row.hidden)shown++;}if(feedback)feedback.textContent=shown+' de '+rows.length+' visibles';if(empty)empty.hidden=shown>0||!rows.length;}
 input.addEventListener('input',filter);filter();
});
})();
(()=>{'use strict';
// Solo una acción comercial abierta: evita formularios largos simultáneos.
document.querySelectorAll('.operation-list').forEach(list=>list.addEventListener('toggle',e=>{const opened=e.target;if(!opened.matches('details.operation-card')||!opened.open)return;list.querySelectorAll('details.operation-card').forEach(other=>{if(other!==opened)other.open=false;});},true));
})();

(()=>{'use strict';
// Acceso directo a los formularios comerciales; detalles nativos sin JavaScript.
for(const list of document.querySelectorAll('.operation-list')){
 const cards=[...list.querySelectorAll('details.operation-card')];if(!cards.length)continue;
 const nav=document.createElement('div');nav.className='ui-action-selector';nav.setAttribute('role','tablist');nav.setAttribute('aria-label','Acciones disponibles para el equipo');
 let chosen=cards.find(c=>c.open)||cards[0];
 const buttons=cards.map((card,i)=>{const summary=card.querySelector('summary'),button=document.createElement('button');button.type='button';button.id='operation-tab-'+card.dataset.action;button.textContent=summary.textContent.trim();button.setAttribute('role','tab');button.setAttribute('aria-controls',card.id);button.className='ui-action-tab';nav.append(button);card.setAttribute('role','tabpanel');card.setAttribute('aria-labelledby',button.id);summary.hidden=true;return button;});
 function select(index,focus=false){chosen=cards[index];cards.forEach((card,i)=>{card.hidden=i!==index;card.open=i===index;buttons[i].setAttribute('aria-selected',String(i===index));buttons[i].tabIndex=i===index?0:-1;});if(focus)buttons[index].focus();}
 buttons.forEach((button,i)=>button.addEventListener('click',()=>select(i)));
 nav.addEventListener('keydown',event=>{const i=buttons.indexOf(document.activeElement);if(i<0||!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?cards.length-1:(i+(event.key==='ArrowRight'?1:-1)+cards.length)%cards.length;select(next,true);});
 list.querySelector('h2')?.after(nav);list.classList.add('ui-actions-enhanced');select(cards.indexOf(chosen));
}
})();

(()=>{'use strict';
// Una sola vista de detalle por movimiento, con regreso al mismo renglón.
const finance=document.querySelector('.finance');if(!finance||typeof HTMLDialogElement==='undefined')return;
const error=document.getElementById('finance-restore');let failed=null;if(error)try{failed=JSON.parse(error.textContent);}catch(_){}
for(const [i,details]of [...finance.querySelectorAll('.f-table td>details')].entries()){
 const cell=details.parentElement,row=cell.closest('tr'),summary=details.querySelector('summary'),dialog=document.createElement('dialog');dialog.className='ui-detail-dialog';dialog.id='movement-dialog-'+i;dialog.setAttribute('aria-labelledby',dialog.id+'-title');
 const header=document.createElement('div');header.className='ui-dialog-heading';const title=document.createElement('h2');title.id=dialog.id+'-title';title.textContent=row.querySelector('td strong')?.textContent||'Detalle del movimiento';const back=document.createElement('button');back.type='button';back.className='btn btn-secondary';back.textContent='Volver a movimientos';header.append(title,back);dialog.append(header);
 const trigger=document.createElement('button');trigger.type='button';trigger.className='ui-dialog-trigger';trigger.textContent='Ver detalle';trigger.setAttribute('aria-haspopup','dialog');trigger.setAttribute('aria-controls',dialog.id);cell.insertBefore(trigger,details);details.classList.add('ui-detail-content');details.open=true;if(summary)summary.hidden=true;dialog.append(details);finance.append(dialog);
 const open=()=>{if(!dialog.open){dialog.showModal();document.body.classList.add('ui-dialog-visible');}};
 trigger.addEventListener('click',open);back.addEventListener('click',()=>dialog.close());dialog.addEventListener('close',()=>{document.body.classList.remove('ui-dialog-visible');trigger.focus();});
 if(failed?.operation_id){const op=details.querySelector('[name="operation_id"]');if(op?.value===failed.operation_id[0])open();}
}
})();
