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


/* Reportes por periodo y tarjetas analíticas. */
(() => {
  'use strict';
  // Muestra las fechas "Desde / Hasta" solo cuando el periodo elegido es un rango, y avisa si van al revés.
  document.querySelectorAll('.reporte-form').forEach((form) => {
    const periodo = form.querySelector('[name=periodo]');
    const rango = form.querySelector('.reporte-rango');
    if (!periodo || !rango) return;
    const ini = rango.querySelector('[name=ini]');
    const fin = rango.querySelector('[name=fin]');

    function ajustar() {
      const esRango = periodo.value === 'rango' && !periodo.disabled;
      rango.hidden = !esRango;
      ini.required = esRango;
      fin.required = esRango;
    }

    periodo.addEventListener('change', ajustar);
    form.addEventListener('submit', (evento) => {
      fin.setCustomValidity('');
      if (periodo.value === 'rango' && ini.value && fin.value && ini.value > fin.value) {
        fin.setCustomValidity('La fecha final no puede ser anterior a la inicial.');
        fin.reportValidity();
        evento.preventDefault();
      }
    });
    ajustar();
  });
})();
