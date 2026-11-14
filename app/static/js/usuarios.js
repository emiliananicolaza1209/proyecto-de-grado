/* Edición accesible de restricciones; la autorización real permanece en servidor. */
(()=>{'use strict';
 const data=document.getElementById('profile-permissions');if(!data)return;
 const profiles=JSON.parse(data.textContent);
 document.querySelectorAll('[data-user-form]').forEach(form=>{
   const role=form.elements.namedItem('role'),mode=form.elements.namedItem('permission_mode');
   const checks=[...form.querySelectorAll('[data-permission]')];
   function update(reset=false){
     const available=new Set(profiles[role.value]||[]),custom=mode.value==='personalizado'&&role.value!=='Propietario';
     if(role.value==='Propietario')mode.value='perfil';
     mode.disabled=role.value==='Propietario';
     checks.forEach(input=>{
       const enabled=available.has(input.value);
       if(reset||!custom)input.checked=enabled;
       if(!enabled)input.checked=false;
       input.disabled=!custom||!enabled;
       input.closest('label').classList.toggle('is-unavailable',!enabled);
     });
     form.querySelectorAll('[data-module]').forEach(module=>{
       module.classList.toggle('is-unavailable',![...module.querySelectorAll('[data-permission]')].some(i=>available.has(i.value)));
     });
     const partner=form.elements.namedItem('partner_id');partner.disabled=role.value!=='Socio';partner.required=role.value==='Socio';
   }
   role.addEventListener('change',()=>update(true));mode.addEventListener('change',()=>update(false));
   checks.forEach(input=>input.addEventListener('change',()=>{
     const group=input.closest('[data-module]'),read=group.querySelector('[data-read="true"]');
     if(input.checked)read.checked=true;
     else if(input===read)group.querySelectorAll('[data-permission]').forEach(i=>{i.checked=false});
     if(input.value==='inventario.editar'&&input.checked)form.querySelector('[value="inventario.costos"]').checked=true;
     if(input.value==='inventario.costos'&&!input.checked)form.querySelector('[value="inventario.editar"]').checked=false;
   }));
   update();
 });
 const search=document.querySelector('[data-user-search]');
 search?.addEventListener('input',()=>{
   const query=search.value.trim().toLocaleLowerCase('es');let count=0;
   document.querySelectorAll('[data-user-card]').forEach(card=>{card.hidden=!card.dataset.search.includes(query);if(!card.hidden)count++});
   document.querySelector('[data-user-empty]').hidden=count>0;
 });
 document.querySelector('[data-open-user]')?.addEventListener('click',()=>{const card=document.getElementById('crear-usuario');card.open=true;card.querySelector('input[name="name"]').focus()});
})();
