(() => {
  'use strict';
  const review = document.getElementById('catalog-review');
  const form = document.getElementById('catalog-form');
  if (!review || !form || typeof HTMLDialogElement === 'undefined') return;

  // La validación viene del servidor. Sin JavaScript, la revisión queda visible
  // junto al formulario y conserva las mismas opciones de guardar o corregir.
  const dialog = document.createElement('dialog');
  if (typeof dialog.showModal !== 'function') return;
  dialog.className = 'catalog-review-dialog';
  dialog.setAttribute('aria-labelledby', 'catalog-review-title');
  dialog.setAttribute('aria-describedby', 'catalog-review-description');
  document.body.append(dialog);
  dialog.append(review);
  const cancel = review.querySelector('[data-review-cancel]');
  cancel.setAttribute('autofocus', '');
  cancel.addEventListener('click', event => {
    event.preventDefault();
    dialog.close();
  });
  dialog.addEventListener('close', () => document.getElementById('name')?.focus());
  dialog.showModal();
})();
