(() => {
  'use strict';
  const form = document.getElementById('chat-form');
  const historial = document.getElementById('chat-historial');
  if (!form || !historial) return;
  const campo = document.getElementById('chat-pregunta');
  const boton = document.getElementById('chat-enviar');
  const vacio = document.getElementById('chat-vacio');
  const MAX_ENTRADAS = 30;
  const ESTADOS = {
    ok: 'Completo', parcial: 'Parcial', sin_datos: 'Sin datos', sin_autorizacion: 'Sin autorización',
    error_temporal: 'Error temporal', fuera_de_alcance: 'Fuera de alcance', periodo_invalido: 'Periodo no válido'
  };

  // Todo el contenido llega como texto (textContent): nunca se interpreta HTML de la respuesta.
  function el(etiqueta, clase, texto) {
    const nodo = document.createElement(etiqueta);
    if (clase) nodo.className = clase;
    if (texto !== undefined && texto !== null) nodo.textContent = texto;
    return nodo;
  }

  function agregar(nodo) {
    if (vacio) vacio.hidden = true;
    historial.appendChild(nodo);
    while (historial.querySelectorAll('.chat-entrada').length > MAX_ENTRADAS) {
      historial.querySelector('.chat-entrada').remove();
    }
    historial.scrollTop = historial.scrollHeight;
  }

  function burbujaUsuario(texto) {
    const entrada = el('div', 'chat-entrada chat-usuario');
    entrada.appendChild(el('p', 'chat-quien', 'Tú'));
    entrada.appendChild(el('p', 'chat-texto', texto));
    agregar(entrada);
  }

  function tarjetaDeRespuesta(datos) {
    const entrada = el('div', 'chat-entrada chat-respuesta');
    const t = datos.tarjeta;
    const cabecera = el('div', 'chat-cabecera');
    cabecera.appendChild(el('p', 'chat-quien', 'CP Store'));
    const estado = el('span', 'chat-estado estado-' + datos.estado, ESTADOS[datos.estado] || datos.estado);
    cabecera.appendChild(estado);
    if (t && t.provisional) cabecera.appendChild(el('span', 'chat-estado estado-provisional', 'Provisional'));
    entrada.appendChild(cabecera);

    if (t) {
      entrada.appendChild(el('h3', 'chat-titulo', t.titulo));
      const periodo = t.periodo && (t.periodo.etiqueta || t.periodo.fecha_corte);
      if (periodo) entrada.appendChild(el('p', 'chat-periodo', 'Periodo: ' + periodo + (t.periodo.ini ? ' (' + t.periodo.ini + (t.periodo.fin && t.periodo.fin !== t.periodo.ini ? ' a ' + t.periodo.fin : '') + ')' : '')));
    }
    if (t && t.cifras && t.cifras.length) {
      const lista = el('dl', 'chat-cifras');
      t.cifras.forEach((c) => {
        const fila = el('div', 'chat-cifra');
        fila.appendChild(el('dt', '', c.etiqueta));
        fila.appendChild(el('dd', '', c.valor));
        lista.appendChild(fila);
      });
      entrada.appendChild(lista);
    } else {
      entrada.appendChild(el('p', 'chat-texto chat-linea', datos.respuesta));
    }
    if (t) {
      (t.notas || []).forEach((n) => entrada.appendChild(el('p', 'chat-nota', 'Nota: ' + n)));
      if (t.advertencias && t.advertencias.length && t.cifras.length) {
        const aviso = el('ul', 'chat-advertencias');
        t.advertencias.forEach((a) => aviso.appendChild(el('li', '', a)));
        entrada.appendChild(aviso);
      }
      const fuente = el('details', 'chat-source');
      fuente.appendChild(el('summary', '', 'Ver fuente de la respuesta'));
      fuente.appendChild(el('p', 'chat-fuente', t.fuente));
      entrada.appendChild(fuente);
    }
    agregar(entrada);
  }

  function mensajeDeError(texto) {
    const entrada = el('div', 'chat-entrada chat-respuesta chat-error');
    entrada.setAttribute('role', 'alert');
    entrada.appendChild(el('p', 'chat-quien', 'CP Store'));
    entrada.appendChild(el('p', 'chat-texto', texto));
    agregar(entrada);
  }

  async function preguntar(texto) {
    if (campo.disabled) return;
    burbujaUsuario(texto);
    boton.disabled = true;
    campo.disabled = true;
    boton.textContent = 'Consultando…';
    try {
      const datos = new FormData(form);
      datos.set('pregunta', texto);
      const r = await fetch(form.action, { method: 'POST', body: datos, credentials: 'same-origin', headers: { Accept: 'application/json' } });
      const tipo = r.headers.get('content-type') || '';
      if (r.redirected || !tipo.includes('application/json')) {
        mensajeDeError(r.status === 403 ? 'Tu perfil no tiene permiso para usar el chat.' : 'Tu sesión terminó o el formulario venció. Recarga la página e inicia sesión de nuevo.');
        return;
      }
      const cuerpo = await r.json();
      if (!r.ok) {
        mensajeDeError(cuerpo.error || 'No se pudo hacer la consulta.');
        return;
      }
      tarjetaDeRespuesta(cuerpo);
    } catch (e) {
      mensajeDeError('No se pudo conectar con el servidor. Intenta de nuevo en unos segundos.');
    } finally {
      boton.disabled = false;
      campo.disabled = false;
      boton.textContent = 'Preguntar';
      campo.focus();
    }
  }

  form.addEventListener('submit', (evento) => {
    evento.preventDefault();
    const texto = campo.value.trim();
    if (!texto) { campo.focus(); return; }
    campo.value = '';
    preguntar(texto);
  });

  document.querySelectorAll('.chat-ejemplo').forEach((boton_) => {
    boton_.addEventListener('click', () => {
      if (campo.disabled) return;
      campo.value = boton_.dataset.pregunta || boton_.textContent;
      form.requestSubmit();
    });
  });

  document.querySelectorAll('[data-chat-quick]').forEach((quick) => quick.addEventListener('click', () => {
    if (!campo.disabled) { campo.value = quick.dataset.chatQuick; form.requestSubmit(); }
  }));

  const selector = document.getElementById('chat-periodo');
  const rango = document.getElementById('chat-rango');
  const desde = document.getElementById('chat-desde');
  const hasta = document.getElementById('chat-hasta');
  const ayuda = document.getElementById('chat-periodo-ayuda');
  const controls = document.querySelector('.chat-period-controls');
  if (selector && rango && desde && hasta && controls) {
    function ajustarPeriodo() {
      const tipo = selector.value, hoy = controls.dataset.hoy;
      rango.hidden = tipo !== 'rango';
      desde.disabled = hasta.disabled = tipo === 'auto';
      desde.required = hasta.required = tipo !== 'auto';
      hasta.setCustomValidity('');
      if (tipo !== 'rango' && tipo !== 'auto') {
        let inicio = hoy, fin = hoy;
        if (tipo === 'cierre') inicio = fin = controls.dataset.ultimoCierre;
        if (tipo === 'mes') inicio = hoy.slice(0, 8) + '01';
        if (tipo === 'ayer') {
          const ayer = new Date(hoy + 'T12:00:00Z');
          ayer.setUTCDate(ayer.getUTCDate() - 1);
          inicio = fin = ayer.toISOString().slice(0, 10);
        }
        desde.value = inicio; hasta.value = fin;
      }
      const format = (fecha) => fecha.split('-').reverse().join('/');
      ayuda.textContent = tipo === 'auto' ? 'Si no escribes una fecha, se consulta hoy. Una fecha escrita en tu pregunta tiene prioridad.' :
        'Fechas seleccionadas: ' + format(desde.value) + ' a ' + format(hasta.value) + '. Una fecha escrita en tu pregunta tiene prioridad.';
    }
    selector.addEventListener('change', ajustarPeriodo);
    for (const input of [desde, hasta]) input.addEventListener('change', () => {
      ajustarPeriodo();
      if (desde.value && hasta.value && desde.value > hasta.value) hasta.setCustomValidity('La fecha final no puede ser anterior a la inicial.');
    });
    ajustarPeriodo();
  }
})();
