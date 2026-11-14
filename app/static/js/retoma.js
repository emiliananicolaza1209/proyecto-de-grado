(()=>{
  const form=document.querySelector('#equipment-form')||document.querySelector('form.actions');if(!form)return;
  const rows=document.querySelector('#retoma-cost-rows');
  const money=n=>new Intl.NumberFormat('es-CO',{style:'currency',currency:'COP'}).format(n);
  const preview=()=>{
    const base=Number(form.elements.purchase_cop.value);
    const values=[...rows.querySelectorAll('[name=additional_amount]')].map(i=>Number(i.value));
    const valid=base>0&&Number.isFinite(base)&&values.every(v=>Number.isFinite(v)&&v>0);
    document.querySelector('#subtotal-preview').textContent=valid?money(base):'—';
    document.querySelector('#total-preview').textContent=valid?money(base+values.reduce((a,b)=>a+b,0)):'—';
    document.querySelector('#cost-status').textContent=valid?'El valor se verificará al guardar.':'Ingresa el valor de compra y completa los costos añadidos.';
  };
  document.querySelector('#add-retoma-cost')?.addEventListener('click',()=>{
    if(rows.children.length>=5)return;
    const row=document.createElement('div');row.className='form-grid retoma-cost-row';
    row.innerHTML='<label>Tipo de costo<input name="additional_name" class="form-control" maxlength="120" required placeholder="Comisión, cambio de batería..."></label><label>Valor · COP<input name="additional_amount" class="form-control" type="number" min="0.01" max="999999999" step="0.01" required></label><button type="button" class="btn btn-light retoma-remove">Quitar</button>';
    rows.append(row);row.querySelector('input').focus();preview();
  });
  rows.addEventListener('click',e=>{if(e.target.closest('.retoma-remove')){e.target.closest('.retoma-cost-row').remove();preview();}});
  form.addEventListener('input',preview);preview();
})();
