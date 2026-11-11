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
