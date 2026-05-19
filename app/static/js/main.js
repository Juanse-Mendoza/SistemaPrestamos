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
function abrirEditarProducto(id, nombre, descripcion, ubicacion) {
  document.getElementById('edit-id').value       = id;
  document.getElementById('edit-nombre').value   = nombre;
  document.getElementById('edit-desc').value     = descripcion || '';
  document.getElementById('edit-ubic').value     = ubicacion || '';
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

function abrirDevolucion(id, codigo, articulo) {
  document.getElementById('dev-codigo').textContent  = codigo;
  document.getElementById('dev-articulo').textContent = articulo;
  document.getElementById('dev-form').action = `/admin/prestamos/${id}/devolver`;
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

// ── Auto-ocultar alertas ──────────────────────────────────────────────────────
document.querySelectorAll('.alert').forEach(el => {
  setTimeout(() => el.style.opacity = '0', 4000);
  setTimeout(() => el.remove(), 4500);
});
