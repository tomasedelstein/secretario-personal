let allCommitments = [];
let activeFilter = 'ALL';

document.addEventListener('DOMContentLoaded', () => {
  loadCommitments();
  checkSystemStatus();
});

async function loadCommitments() {
  try {
    const res = await fetch('/api/commitments');
    if (res.ok) {
      allCommitments = await res.json();
      renderCommitments();
    }
  } catch (err) {
    console.error("Error al cargar compromisos:", err);
  }
}

async function checkSystemStatus() {
  try {
    const res = await fetch('/api/status');
    if (res.ok) {
      const data = await res.json();
      const badge = document.getElementById('systemStatusBadge');
      if (data.configured) {
        badge.className = 'status-badge active';
        badge.innerHTML = '● WhatsApp Conectado';
      } else {
        badge.className = 'status-badge pending';
        badge.innerHTML = '⚙️ Configuración Pendiente';
      }
    }
  } catch (err) {
    console.error("Error al verificar estado:", err);
  }
}

function filterCommitments(status, element) {
  activeFilter = status;
  document.querySelectorAll('.filter-chip').forEach(el => el.classList.remove('active'));
  element.classList.add('active');
  renderCommitments();
}

function renderCommitments() {
  const container = document.getElementById('commitmentsContainer');
  container.innerHTML = '';

  let filtered = allCommitments;
  if (activeFilter !== 'ALL') {
    filtered = allCommitments.filter(c => c.status === activeFilter);
  }

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1;">
        <h3>No tenés compromisos ${activeFilter !== 'ALL' ? 'en este estado' : 'registrados'}</h3>
        <p style="margin-top: 8px;">Podes agregar uno desde aquí o simplemente escribiendo por WhatsApp.</p>
      </div>
    `;
    return;
  }

  filtered.forEach(c => {
    const dt = new Date(c.event_datetime);
    const dateStr = dt.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' });
    const timeStr = dt.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', hour12: false });

    let statusLabel = '';
    if (c.status === 'COMPLETED') statusLabel = '<span style="color: var(--accent-emerald);">✔ Realizado</span>';
    else if (c.status === 'CANCELLED') statusLabel = '<span style="color: var(--accent-rose);">✖ Cancelado</span>';
    else statusLabel = '<span style="color: var(--accent-amber);">⏳ Pendiente</span>';

    const card = document.createElement('div');
    card.className = 'commitment-card';
    card.innerHTML = `
      <div>
        <div class="card-header">
          <span class="card-title">${escapeHtml(c.title)}</span>
          <span class="card-category">${escapeHtml(c.category || 'General')}</span>
        </div>
        <div class="card-body">
          <div class="info-row">📅 <strong>${dateStr}</strong></div>
          <div class="info-row">⏰ <strong>${timeStr} hs</strong></div>
          <div class="info-row">🔔 Aviso: ${c.reminder_offset_minutes} min antes</div>
          <div class="info-row" style="margin-top: 10px;">Estado: ${statusLabel}</div>
        </div>
      </div>
      <div class="card-footer">
        ${c.status === 'PENDING' ? `
          <button class="btn btn-success" style="font-size: 0.8rem; padding: 6px 12px;" onclick="markCompleted(${c.id})">✔ Marcar Listo</button>
          <button class="btn btn-secondary" style="font-size: 0.8rem; padding: 6px 12px;" onclick="openEditModal(${c.id})">✏️ Editar</button>
          <button class="btn btn-danger" style="font-size: 0.8rem; padding: 6px 12px;" onclick="cancelCommitment(${c.id})">✖ Cancelar</button>
        ` : `
          <button class="btn btn-danger" style="font-size: 0.8rem; padding: 6px 12px;" onclick="deleteCommitment(${c.id})">🗑️ Eliminar</button>
        `}
      </div>
    `;
    container.appendChild(card);
  });
}

function openCreateModal() {
  document.getElementById('modalTitle').innerText = 'Nuevo Compromiso';
  document.getElementById('commitmentForm').reset();
  document.getElementById('commitmentId').value = '';
  
  // Establecer fecha por defecto (hoy)
  const now = new Date();
  document.getElementById('formDate').value = now.toISOString().split('T')[0];
  document.getElementById('formTime').value = "17:00";
  
  document.getElementById('commitmentModal').classList.add('open');
}

function openEditModal(id) {
  const c = allCommitments.find(item => item.id === id);
  if (!c) return;

  document.getElementById('modalTitle').innerText = 'Editar Compromiso';
  document.getElementById('commitmentId').value = c.id;
  document.getElementById('formTitle').value = c.title;
  document.getElementById('formCategory').value = c.category || 'General';
  
  const dt = new Date(c.event_datetime);
  document.getElementById('formDate').value = dt.toISOString().split('T')[0];
  
  const hours = String(dt.getHours()).padStart(2, '0');
  const minutes = String(dt.getMinutes()).padStart(2, '0');
  document.getElementById('formTime').value = `${hours}:${minutes}`;
  document.getElementById('formOffset').value = c.reminder_offset_minutes || 60;

  document.getElementById('commitmentModal').classList.add('open');
}

function closeModal(modalId) {
  document.getElementById(modalId).classList.remove('open');
}

async function saveCommitment(e) {
  e.preventDefault();
  const id = document.getElementById('commitmentId').value;
  const title = document.getElementById('formTitle').value;
  const category = document.getElementById('formCategory').value;
  const dateStr = document.getElementById('formDate').value;
  const timeStr = document.getElementById('formTime').value;
  const offset = parseInt(document.getElementById('formOffset').value);

  // Armar iso string
  const event_datetime = `${dateStr}T${timeStr}:00-03:00`;

  const payload = { title, category, event_datetime, reminder_offset_minutes: offset };

  try {
    let res;
    if (id) {
      res = await fetch(`/api/commitments/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    } else {
      res = await fetch('/api/commitments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    }

    if (res.ok) {
      closeModal('commitmentModal');
      loadCommitments();
    }
  } catch (err) {
    alert("Error al guardar compromiso.");
  }
}

async function markCompleted(id) {
  try {
    const res = await fetch(`/api/commitments/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'COMPLETED' })
    });
    if (res.ok) loadCommitments();
  } catch (err) {
    console.error(err);
  }
}

async function cancelCommitment(id) {
  if (!confirm("¿Deseás cancelar este compromiso?")) return;
  try {
    const res = await fetch(`/api/commitments/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'CANCELLED' })
    });
    if (res.ok) loadCommitments();
  } catch (err) {
    console.error(err);
  }
}

async function deleteCommitment(id) {
  if (!confirm("¿Eliminar definitivamente este compromiso?")) return;
  try {
    const res = await fetch(`/api/commitments/${id}`, { method: 'DELETE' });
    if (res.ok) loadCommitments();
  } catch (err) {
    console.error(err);
  }
}

function openSettingsModal() {
  loadCurrentSettings();
  document.getElementById('settingsModal').classList.add('open');
}

async function loadCurrentSettings() {
  try {
    const res = await fetch('/api/settings');
    if (res.ok) {
      const data = await res.json();
      document.getElementById('cfgPhoneNumberId').value = data.phone_number_id || '';
      document.getElementById('cfgAccessToken').value = data.access_token || '';
      document.getElementById('cfgAppId').value = data.app_id || '';
      document.getElementById('cfgAppSecret').value = data.app_secret || '';
      document.getElementById('cfgWebhookToken').value = data.webhook_token || 'secretario_verify_token_2026';
      document.getElementById('cfgAuthorizedPhone').value = data.authorized_phone || '';
    }
  } catch (err) {
    console.error(err);
  }
}

async function saveSettings(e) {
  e.preventDefault();
  const payload = {
    phone_number_id: document.getElementById('cfgPhoneNumberId').value,
    access_token: document.getElementById('cfgAccessToken').value,
    app_id: document.getElementById('cfgAppId').value,
    app_secret: document.getElementById('cfgAppSecret').value,
    webhook_token: document.getElementById('cfgWebhookToken').value,
    authorized_phone: document.getElementById('cfgAuthorizedPhone').value
  };

  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      alert("✅ Configuración guardada de forma segura.");
      closeModal('settingsModal');
      checkSystemStatus();
    }
  } catch (err) {
    alert("Error al guardar credenciales.");
  }
}

function escapeHtml(str) {
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
