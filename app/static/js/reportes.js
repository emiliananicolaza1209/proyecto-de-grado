/* Filtros del reporte elegido. Sin consultas ni modificación de importes. */
(()=>{'use strict';
const form=document.getElementById('report-filters'),kind=document.getElementById('report-kind');if(!form||!kind)return;
function filters(){
 for(const group of form.querySelectorAll('[data-report-types]')){
  const active=group.dataset.reportTypes.split(' ').includes(kind.value);group.hidden=!active;
  for(const control of group.querySelectorAll('input,select'))control.disabled=!active;
 }
 const state=form.elements.estado;if(state){
  for(const option of state.querySelectorAll('[data-state-types]')){
   const active=option.dataset.stateTypes===kind.value;option.hidden=!active;option.disabled=!active;
   if(!active&&option.selected)state.value='';
  }
 }
}
kind.addEventListener('change',filters);window.addEventListener('pageshow',filters);filters();
})();
