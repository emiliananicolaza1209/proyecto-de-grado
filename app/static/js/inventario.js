const imei = document.querySelector('#imei');
const statusBox = document.querySelector('#scan-status');
let requestNumber = 0;
function showStatus(message, type = '') {
  statusBox.textContent = message;
  statusBox.className = `scan-status ${type}`;
}
async function verifyIMEI(moveFocus = false) {
  const number = ++requestNumber;
  const value = imei.value.trim();
  imei.value = value;
  imei.setCustomValidity('');
  if (!/^[0-9]{15}$/.test(value)) {
    imei.setCustomValidity('Ingresa un IMEI de exactamente 15 dígitos.');
    showStatus('Revisa el código: el IMEI debe tener exactamente 15 dígitos.', 'error');
    return;
  }
  showStatus('Comprobando el IMEI…');
  try {
    const response = await fetch(`/inventario/verificar-imei?imei=${encodeURIComponent(value)}`);
    if (!response.ok) throw new Error('verification');
    const result = await response.json();
    if (number !== requestNumber || imei.value.trim() !== value) return;
    if (!result.valid || result.exists) {
      const message = result.exists ? 'Este IMEI ya está registrado. Consúltalo en el inventario.' : 'El dígito de control del IMEI no es válido. Revisa el código.';
      imei.setCustomValidity(message);
      showStatus(message, 'error');
    } else {
      showStatus('IMEI válido y sin duplicados. Completa los datos del equipo.', 'ok');
      if (moveFocus && document.activeElement === imei) (document.querySelector('#model-search') || document.querySelector('#model')).focus();
    }
  } catch {
    if (number === requestNumber) showStatus('No fue posible comprobarlo ahora. Se validará al guardar.');
  }
}
if (imei) {
  document.querySelector('#focus-scanner').addEventListener('click', () => {
    imei.focus(); imei.select();
    showStatus('Campo preparado. Escanea el código de barras del IMEI.');
  });
  imei.addEventListener('input', () => {
    requestNumber++;
    imei.setCustomValidity('');
    showStatus('Capturando el IMEI…');
    if (imei.value.trim().length === 15) verifyIMEI();
  });
  imei.addEventListener('change', () => { if (imei.value) verifyIMEI(); });
  imei.addEventListener('keydown', event => {
    if (event.key === 'Enter') { event.preventDefault(); verifyIMEI(true); }
  });
}

const catalogElement = document.querySelector('#catalog-data');
if (catalogElement) {
  const catalog = JSON.parse(catalogElement.textContent);
  const brand = document.querySelector('#brand');
  const reference = document.querySelector('#model');
  const search = document.querySelector('#model-search');
  const list = document.querySelector('#model-options');
  const toggle = document.querySelector('#model-toggle');
  const normalizeText = value => value.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]/g, '');
  const capacityLabel = value => Number(value) >= 1024 ? `${Number(value) / 1024} TB` : `${value} GB`;
  if (brand && reference && search && list) {
    const references = catalog.filter(item => item.kind === 'reference');
    let visible = [], cursor = -1;
    const chosen = () => references.find(item => String(item.id) === reference.value && String(item.parent_id) === brand.value);
    function close() {
      list.hidden = true;
      search.setAttribute('aria-expanded', 'false');
      search.removeAttribute('aria-activedescendant');
      cursor = -1;
    }
    function setProperties(preserve) {
      for (const kind of ['color', 'capacity']) {
        const select = document.querySelector(`#${kind}`);
        if (!select) continue;
        const previous = preserve ? select.dataset.selected : '';
        const options = catalog.filter(item => item.kind === kind && String(item.parent_id) === reference.value);
        if (kind === 'capacity') options.sort((a,b) => Number(a.name)-Number(b.name));
        select.replaceChildren(new Option(options.length ? 'Seleccionar' : 'Selecciona primero el modelo', ''));
        for (const item of options) select.add(new Option(kind === 'capacity' ? capacityLabel(item.name) : item.name.toUpperCase(), String(item.id)));
        if (options.some(item => String(item.id) === previous)) select.value = previous;
        else if (options.length === 1) select.value = String(options[0].id);
      }
    }
    function select(item) {
      reference.value = String(item.id);
      search.value = item.name.toUpperCase();
      search.setCustomValidity('');
      setProperties(false);
      close();
      search.focus();
    }
    function render(all = false) {
      const query = all ? '' : normalizeText(search.value);
      visible = references.filter(item => String(item.parent_id) === brand.value && normalizeText(item.name).includes(query));
      list.replaceChildren(); cursor = -1;
      visible.forEach(item => {
        const option = document.createElement('div');
        option.id = 'model-option-' + item.id;
        option.setAttribute('role','option');
        option.setAttribute('aria-selected', String(String(item.id) === reference.value));
        option.textContent = item.name.toUpperCase();
        option.addEventListener('mousedown', event => event.preventDefault());
        option.addEventListener('click', () => select(item));
        list.append(option);
      });
      if (!visible.length) {
        const empty = document.createElement('p');
        empty.textContent = brand.value ? 'Sin coincidencias. Revisa el modelo en Catálogos.' : 'Selecciona primero una marca.';
        list.append(empty);
      }
      list.hidden = false;
      search.setAttribute('aria-expanded','true');
    }
    brand.addEventListener('change', () => {
      reference.value = ''; search.value = ''; search.setCustomValidity('');
      setProperties(false); close();
    });
    search.addEventListener('input', () => {
      reference.value = '';
      search.setCustomValidity('Selecciona un modelo de la lista.');
      setProperties(false); render();
    });
    search.addEventListener('focus', () => render(Boolean(chosen())));
    toggle.addEventListener('click', () => {
      if (!list.hidden) close(); else { search.focus(); render(true); }
    });
    search.addEventListener('keydown', event => {
      if (event.key === 'Escape') { close(); return; }
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        if (list.hidden) render(true);
        if (!visible.length) return;
        cursor = (cursor + (event.key === 'ArrowDown' ? 1 : -1) + visible.length) % visible.length;
        [...list.children].forEach((el,i) => el.classList.toggle('highlight', i === cursor));
        const active = list.children[cursor];
        search.setAttribute('aria-activedescendant',active.id);
        active.scrollIntoView({block:'nearest'});
      } else if (event.key === 'Enter' && !list.hidden) {
        event.preventDefault();
        if (cursor >= 0) select(visible[cursor]);
        else if (visible.length === 1) select(visible[0]);
      } else if (event.key === 'Tab') close();
    });
    document.addEventListener('click', event => {
      if (!event.target.closest('.model-combobox')) close();
    });
    const initial = chosen();
    if (initial) search.value = initial.name.toUpperCase();
    else reference.value = '';
    setProperties(true);
  }
}

const lotSelect = document.querySelector('#lot-select');
const costFields = ['purchase_usd', 'exchange_rate', 'shipping_cop'].map(id => document.getElementById(id));
function previewCost() {
  if (!costFields.every(Boolean)) return;
  const [usd, rate, shipping] = costFields.map(input => input.value === '' ? NaN : Number(input.value));
  const valid = [usd, rate, shipping].every(Number.isFinite) && usd > 0 && rate > 0 && shipping >= 0;
  const format = amount => amount.toLocaleString('es-CO', {style:'currency', currency:'COP'});
  const subtotal = Math.round((usd * rate + Number.EPSILON) * 100) / 100;
  document.getElementById('subtotal-preview').textContent = valid ? format(subtotal) : '—';
  document.getElementById('total-preview').textContent = valid ? format(subtotal + shipping) : '—';
  document.getElementById('cost-status').textContent = valid ? 'El sistema verificará el cálculo al guardar.' : 'Completa compra, precio del dólar y envío.';
}
costFields.filter(Boolean).forEach(input => input.addEventListener('input', previewCost));
previewCost();
if (lotSelect) {
  const applyLot = (initial = false) => {
    const option = lotSelect.selectedOptions[0];
    document.querySelector('#supplier').value = option?.dataset.supplier || '';
    const rate = document.querySelector('#exchange_rate');
    if (!initial || !rate.value) rate.value = option?.dataset.rate || '';
    rate.readOnly = false;
    rate.dispatchEvent(new Event('input', {bubbles:true}));
  };
  lotSelect.addEventListener('change', () => applyLot(false));
  applyLot(true);
}

const warrantySwitch = document.querySelector('#warranty-enabled');
if (warrantySwitch) {
  const updateWarranty = () => {
    const field = document.querySelector('#warranty-until');
    document.querySelector('#warranty-fields').hidden = !warrantySwitch.checked;
    field.disabled = !warrantySwitch.checked;
    field.required = warrantySwitch.checked;
  };
  warrantySwitch.addEventListener('change',updateWarranty);
  updateWarranty();
}

// Solo se sustituye la zona de resultados: el cursor y el formulario se conservan.
const inventorySearch = document.querySelector('#inventory-search');
if (inventorySearch) {
  const results = document.querySelector('#inventory-results');
  const feedback = document.querySelector('#search-feedback');
  let timer, controller, sequence = 0;
  async function refresh() {
    const id = ++sequence;
    if (controller) controller.abort();
    controller = new AbortController();
    const params = new URLSearchParams(new FormData(inventorySearch));
    const pageURL = '/inventario?' + params.toString();
    params.set('fragment','1');
    results.setAttribute('aria-busy','true');
    feedback.textContent = 'Buscando…';
    try {
      const response = await fetch('/inventario?' + params, {signal:controller.signal});
      if (!response.ok) throw new Error('search');
      const html = await response.text();
      if (id !== sequence) return;
      results.innerHTML = html;
      history.replaceState(null,'',pageURL);
      feedback.textContent = '';
    } catch (error) {
      if (id === sequence && error.name !== 'AbortError') feedback.textContent = 'No se pudo actualizar. Pulsa Buscar para intentar de nuevo.';
    } finally {
      if (id === sequence) results.removeAttribute('aria-busy');
    }
  }
  inventorySearch.querySelector('#q').addEventListener('input', () => {
    clearTimeout(timer);
    ++sequence;
    if (controller) controller.abort();
    timer = setTimeout(refresh,200);
  });
  inventorySearch.querySelector('select').addEventListener('change', () => { clearTimeout(timer); refresh(); });
  inventorySearch.addEventListener('submit', event => {event.preventDefault(); clearTimeout(timer); refresh();});
}
