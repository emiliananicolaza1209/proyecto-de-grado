(()=>{'use strict';
const menu=document.querySelector('.app-menu-toggle');const sidebar=document.querySelector('.app-sidebar');
menu?.addEventListener('click',()=>{const open=sidebar.classList.toggle('nav-open');menu.setAttribute('aria-expanded',String(open));menu.setAttribute('aria-label',open?'Ocultar navegación':'Mostrar navegación');});
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();document.querySelector('#quick-imei')?.focus();}if(e.key==='Escape'&&sidebar?.classList.contains('nav-open')){sidebar.classList.remove('nav-open');menu?.setAttribute('aria-expanded','false');}});
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
