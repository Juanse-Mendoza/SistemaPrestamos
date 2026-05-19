// PrestaUni — JS global

// ── Modales ──────────────────────────────────────────────────────────────────
function openModal(id) {
  document.getElementById(id).classList.add('open');
}
function closeModal(id) {
  document.getElementById(id).classList.remove('open');
}
// Cerrar al hacer clic fuera del modal
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-backdrop')) {
    e.target.classList.remove('open');
  }
});
// Cerrar con Escape
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-backdrop.open').forEach(m => m.classList.remove('open'));
  }
});

// ── Abrir modal de edición con datos precargados ──────────────────────────────
function abrirEditarProducto(id, nombre, descripcion, ubicacion, codigoBarras, tiempoMaxValor, tiempoMaxUnidad, estado, multaHora) {
  document.getElementById('edit-id').value       = id;
  document.getElementById('edit-nombre').value   = nombre;
  document.getElementById('edit-desc').value     = descripcion || '';
  document.getElementById('edit-ubic').value     = ubicacion || '';
  const bc = document.getElementById('edit-barcode');
  if (bc) bc.value = codigoBarras || '';
  const tval = document.getElementById('edit-tiempo-max-valor');
  if (tval) tval.value = (tiempoMaxValor === null || tiempoMaxValor === undefined) ? '' : tiempoMaxValor;
  const tuni = document.getElementById('edit-tiempo-max-unidad');
  if (tuni) tuni.value = tiempoMaxUnidad || 'dias';
  const est = document.getElementById('edit-estado');
  if (est) {
    const e = (estado === 'mantenimiento') ? 'mantenimiento' : 'disponible';
    est.value = e;
  }
  const mh = document.getElementById('edit-multa-hora');
  if (mh) mh.value = (multaHora === null || multaHora === undefined) ? '' : multaHora;
  const status = document.getElementById('edit-barcode-status');
  if (status) status.style.display = 'none';
  document.getElementById('edit-form').action    = `/admin/productos/${id}/editar`;
  openModal('modal-editar');
}

function abrirStock(id, nombre, stockActual) {
  document.getElementById('stock-id').value      = id;
  document.getElementById('stock-nombre').textContent = nombre;
  document.getElementById('stock-actual').textContent = stockActual;
  document.getElementById('stock-nuevo').value   = stockActual;
  document.getElementById('stock-form').action   = `/admin/productos/${id}/stock`;
  openModal('modal-stock');
}

function abrirBaja(id, nombre) {
  document.getElementById('baja-nombre').textContent = nombre;
  document.getElementById('baja-form').action = `/admin/productos/${id}/baja`;
  openModal('modal-baja');
}

function abrirDevolucion(id, codigo, articulo, vencido = false) {
  document.getElementById('dev-codigo').textContent  = codigo;
  document.getElementById('dev-articulo').textContent = articulo;
  document.getElementById('dev-form').action = `/admin/prestamos/${id}/devolver`;
  const aviso = document.getElementById('dev-aviso-tarde');
  if (aviso) aviso.style.display = vencido ? 'block' : 'none';
  // Prellenar fecha/hora con el momento actual
  const fechaInp = document.getElementById('dev-fecha');
  if (fechaInp) {
    const ahora = new Date();
    ahora.setMinutes(ahora.getMinutes() - ahora.getTimezoneOffset());
    fechaInp.value = ahora.toISOString().slice(0, 16);
  }
  // Resetear checklist
  document.querySelectorAll('#dev-form input[name="checklist"]').forEach(c => c.checked = false);
  openModal('modal-devolucion');
}

function abrirSolicitar(id, nombre, disponible, total) {
  document.getElementById('sol-nombre').textContent = nombre;
  document.getElementById('sol-stock').textContent  = `${disponible} / ${total} disponibles`;
  document.getElementById('sol-id').value            = id;
  // Fecha mínima: mañana
  const min = new Date(); min.setDate(min.getDate() + 1);
  document.getElementById('sol-fecha').min = min.toISOString().slice(0, 16);
  document.getElementById('sol-fecha').value = min.toISOString().slice(0, 16);
  openModal('modal-solicitar');
}

// ══════════════════════════════════════════════════════════════════════════════
// MODAL NUEVO PRÉSTAMO — escaneo de código de barras (usuario y hasta 2 artículos)
// ══════════════════════════════════════════════════════════════════════════════

// Funciones globales para los botones onclick
window.agregarArticulo2 = function() {
  document.getElementById('art2-container').style.display = 'block';
  document.getElementById('btn-agregar-art2').style.display = 'none';
};
window.quitarArticulo2 = function() {
  document.getElementById('art2-container').style.display = 'none';
  document.getElementById('btn-agregar-art2').style.display = 'inline-block';
  // Limpiar campos
  const sel = document.getElementById('np-articulo-2');
  if (sel) sel.value = '';
  const f = document.querySelector('input[name="fecha_devolucion_2"]');
  if (f) f.value = '';
  const info = document.getElementById('np-art-info-2');
  if (info) info.innerHTML = '';
  const bc = document.getElementById('np-bc-articulo-2');
  if (bc) bc.value = '';
};

(function() {
  const bcUsuario  = document.getElementById('np-bc-usuario');
  const bcArticulo = document.getElementById('np-bc-articulo');
  if (!bcUsuario && !bcArticulo) return;  // este template no tiene el modal

  let timerUsr = null, timerArt1 = null, timerArt2 = null;

  function setInfo(elId, html, color) {
    const el = document.getElementById(elId);
    if (!el) return;
    el.innerHTML = html;
    el.style.color = color || '';
  }

  // ── Usuario por código de barras ──
  async function buscarUsuario(codigo) {
    if (!codigo) return;
    setInfo('np-usr-info', `Buscando estudiante con código «${codigo}»...`, '');
    try {
      const r = await fetch(`/admin/api/buscar-usuario-barcode/${encodeURIComponent(codigo)}`);
      const d = await r.json();
      if (!d.encontrado) {
        setInfo('np-usr-info', '❌ ' + d.mensaje, 'var(--danger)');
        return;
      }
      if (!d.activo) {
        setInfo('np-usr-info', '⚠ ' + d.mensaje, 'var(--warning)');
        return;
      }
      // Llenar correo automáticamente
      document.getElementById('np-correo').value = d.usuario.correo;
      setInfo('np-usr-info',
        `✓ <strong>${d.usuario.nombre}</strong> · ${d.usuario.correo}${d.usuario.documento ? ' · doc: ' + d.usuario.documento : ''}`,
        'var(--success)');
      bcUsuario.value = '';
    } catch (e) {
      setInfo('np-usr-info', '⚠ Error al consultar el servidor.', 'var(--danger)');
    }
  }

  if (bcUsuario) {
    bcUsuario.addEventListener('keydown', (e) => {
      clearTimeout(timerUsr);
      if (e.key === 'Enter') {
        e.preventDefault();
        const c = bcUsuario.value.trim();
        if (c) buscarUsuario(c);
        return;
      }
      timerUsr = setTimeout(() => {
        const c = bcUsuario.value.trim();
        if (c.length >= 4) buscarUsuario(c);
      }, 200);
    });
  }

  // ── Aplicar tiempo máximo al input de fecha (en minutos), target = '1' o '2' ──
  function aplicarTiempoMax(minutosMax, nombreArticulo, legible, target) {
    const fechaInp = document.querySelector(`#np-form input[name="fecha_devolucion_${target}"]`);
    if (!fechaInp) return;
    if (minutosMax && minutosMax > 0) {
      const max = new Date();
      max.setMinutes(max.getMinutes() + parseInt(minutosMax));
      const isoLocal = new Date(max.getTime() - max.getTimezoneOffset() * 60000)
        .toISOString().slice(0, 16);
      fechaInp.max   = isoLocal;
      fechaInp.value = isoLocal;
      fechaInp.title = `Máximo ${legible || minutosMax + ' min'} — devolución calculada automáticamente.`;
      fechaInp.classList.add('input-autocompletado');
      setTimeout(() => fechaInp.classList.remove('input-autocompletado'), 1500);
    } else {
      fechaInp.removeAttribute('max');
      fechaInp.title = '';
    }
  }

  function getInfoId(target) {
    return target === '2' ? 'np-art-info-2' : 'np-art-info';
  }

  // ── Cargar opciones del dropdown si no están precargadas (caso dashboard) ──
  async function asegurarOpcionesDropdown() {
    const sel1 = document.getElementById('np-articulo');
    if (sel1 && sel1.options.length <= 1) {
      try {
        const r = await fetch('/admin/api/articulos-disponibles');
        const arts = await r.json();
        const sel2 = document.getElementById('np-articulo-2');
        arts.forEach(a => {
          const txt = `${a.articulo} (disp: ${a.stock_disponible})`;
          const opt1 = document.createElement('option'); opt1.value = a.articulo_id; opt1.textContent = txt;
          sel1.appendChild(opt1);
          if (sel2) {
            const opt2 = document.createElement('option'); opt2.value = a.articulo_id; opt2.textContent = txt;
            sel2.appendChild(opt2);
          }
        });
      } catch (_) {}
    }
  }
  asegurarOpcionesDropdown();

  // ── Cambio de dropdown manual aplica tiempo máximo automáticamente ──
  async function onChangeArticulo(sel, target) {
    const id = sel.value;
    if (!id) { aplicarTiempoMax(null, '', '', target); return; }
    try {
      const r = await fetch('/admin/api/articulos-disponibles');
      const arts = await r.json();
      const art = arts.find(a => String(a.articulo_id) === String(id));
      if (art) aplicarTiempoMax(art.tiempo_maximo_minutos, art.articulo, art.tiempo_maximo_legible, target);
    } catch (_) {}
  }
  const sel1 = document.getElementById('np-articulo');
  if (sel1) sel1.addEventListener('change', () => onChangeArticulo(sel1, '1'));
  const sel2 = document.getElementById('np-articulo-2');
  if (sel2) sel2.addEventListener('change', () => onChangeArticulo(sel2, '2'));

  // ── Búsqueda de artículo por código de barras (target = '1' o '2') ──
  async function buscarArticulo(codigo, target) {
    if (!codigo) return;
    const infoId = getInfoId(target);
    setInfo(infoId, `Buscando artículo con código «${codigo}»...`, '');
    try {
      const r = await fetch(`/admin/api/buscar-articulo-barcode/${encodeURIComponent(codigo)}`);
      const d = await r.json();
      if (!d.encontrado) { setInfo(infoId, '❌ ' + d.mensaje, 'var(--danger)'); return; }
      if (!d.disponible) { setInfo(infoId, '⚠ ' + d.mensaje, 'var(--warning)'); return; }
      const a = d.articulo;
      const sel = document.getElementById(target === '2' ? 'np-articulo-2' : 'np-articulo');
      let opt = sel.querySelector(`option[value="${a.articulo_id}"]`);
      if (!opt) {
        opt = document.createElement('option');
        opt.value = a.articulo_id;
        opt.textContent = `${a.articulo} (disp: ${a.stock_disponible})`;
        sel.appendChild(opt);
      }
      sel.value = a.articulo_id;
      const minMax = a.tiempo_maximo_minutos;
      let legible = '';
      if (minMax) {
        if (minMax % 1440 === 0) legible = (minMax / 1440) + ' día(s)';
        else if (minMax % 60 === 0) legible = (minMax / 60) + ' hora(s)';
        else legible = minMax + ' min';
      }
      aplicarTiempoMax(minMax, a.articulo, legible, target);
      const limiteInfo = minMax ? ` · máx. ${legible}` : ' · sin límite de tiempo';
      setInfo(infoId,
        `✓ <strong>${a.articulo}</strong> · stock: ${a.stock_disponible}/${a.stock_total}${limiteInfo}`,
        'var(--success)');
      const bcInp = document.getElementById(target === '2' ? 'np-bc-articulo-2' : 'np-bc-articulo');
      if (bcInp) bcInp.value = '';
    } catch (e) {
      setInfo(infoId, '⚠ Error al consultar el servidor.', 'var(--danger)');
    }
  }

  function attachBarcodeListener(inputEl, target) {
    if (!inputEl) return;
    let timer = null;
    inputEl.addEventListener('keydown', (e) => {
      clearTimeout(timer);
      if (e.key === 'Enter') {
        e.preventDefault();
        const c = inputEl.value.trim();
        if (c) buscarArticulo(c, target);
        return;
      }
      timer = setTimeout(() => {
        const c = inputEl.value.trim();
        if (c.length >= 4) buscarArticulo(c, target);
      }, 200);
    });
  }
  attachBarcodeListener(bcArticulo, '1');
  attachBarcodeListener(document.getElementById('np-bc-articulo-2'), '2');
})();

// ── Auto-ocultar alertas ──────────────────────────────────────────────────────
document.querySelectorAll('.alert').forEach(el => {
  setTimeout(() => el.style.opacity = '0', 4000);
  setTimeout(() => el.remove(), 4500);
});
