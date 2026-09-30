// Mejoras progresivas: los formularios también funcionan sin JavaScript.
(() => {
  const submitted = document.getElementById('sales-submitted');
  if (submitted) {
    const values = JSON.parse(submitted.textContent);
    document.querySelectorAll('form.sales-form').forEach(form => {
      if (form.elements.action?.value !== values.action) return;
      if (values.record_id && form.elements.record_id?.value !== values.record_id) return;
      if (values.collection_id && form.elements.collection_id?.value !== values.collection_id) return;
      Object.entries(values).forEach(([name,value]) => { if (!['csrf','revision'].includes(name) && form.elements[name]) form.elements[name].value=value; });
      let node=form.parentElement; while(node){if(node.tagName==='DETAILS')node.open=true;node=node.parentElement;}
    });
  }
  const cards = [...document.querySelectorAll('.operation-card')];
  cards.forEach(card => card.addEventListener('toggle', () => {
    if (card.open) cards.forEach(other => { if (other !== card) other.open = false; });
  }));
  document.querySelectorAll('form.sales-form').forEach(form => {
    const date = form.elements.movement_date;
    const reason = form.elements.date_reason;
    if (date && reason) {
      const automatic = date.defaultValue;
      const syncDate = () => {
        const changed = date.value !== automatic || form.elements.action.value === 'correct_date';
        reason.closest('label').hidden = !changed;
        reason.required = changed;
      };
      date.addEventListener('change', syncDate); syncDate();
    }
    const destination = form.elements.destination, collector = form.elements.collector;
    if (destination && collector) {
      const sync = () => { const needed = destination.value === 'Vendedora'; collector.closest('label').hidden = !needed; collector.required = needed; };
      destination.addEventListener('change', sync); sync();
    }
    const method = form.elements.method, reference = form.elements.reference;
    if (method && reference) {
      const sync = () => { const needed = ['Transferencia','Tarjeta'].includes(method.value); reference.required = needed; reference.closest('label').hidden = method.value === 'Efectivo'; };
      method.addEventListener('change', sync); sync();
    }
    // Si la validación detecta un campo oculto en un desplegable, mostrarlo.
    form.addEventListener('invalid', event => { let node=event.target.parentElement; while(node && node!==form){if(node.tagName==='DETAILS')node.open=true;node=node.parentElement;} }, true);
  });
})();
