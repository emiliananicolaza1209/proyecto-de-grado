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

    if (t && t.cifras && t.cifras.length) {
      entrada.appendChild(el('h3', 'chat-titulo', t.titulo));
      const periodo = t.periodo && (t.periodo.etiqueta || t.periodo.fecha_corte);
      if (periodo) entrada.appendChild(el('p', 'chat-periodo', 'Periodo: ' + periodo + (t.periodo.ini ? ' (' + t.periodo.ini + (t.periodo.fin && t.periodo.fin !== t.periodo.ini ? ' a ' + t.periodo.fin : '') + ')' : '')));
      const lista = el('dl', 'chat-cifras');
      t.cifras.forEach((c) => {
        const fila = el('div', 'chat-cifra');
        fila.appendChild(el('dt', '', c.etiqueta));
        fila.appendChild(el('dd', '', c.valor));
        lista.appendChild(fila);
      });
      entrada.appendChild(lista);
      (t.notas || []).forEach((n) => entrada.appendChild(el('p', 'chat-nota', 'Nota: ' + n)));
      if (t.advertencias && t.advertencias.length) {
        const aviso = el('ul', 'chat-advertencias');
        t.advertencias.forEach((a) => aviso.appendChild(el('li', '', a)));
        entrada.appendChild(aviso);
      }
      entrada.appendChild(el('p', 'chat-fuente', 'Fuente: ' + t.fuente));
    } else {
      entrada.appendChild(el('p', 'chat-texto chat-linea', datos.respuesta));
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
})();
