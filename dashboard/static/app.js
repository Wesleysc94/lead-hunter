/* ═══════════════════════════════════════════════════════
   LEAD HUNTER DASHBOARD — Client-Side Logic
   ═══════════════════════════════════════════════════════ */

'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  leads: [],
  filter: 'ALL',
  crmFilter: 'ALL',
  search: '',
  onlyNew: false,
  logFilter: 'ALL',
  logLineCount: 0,
  isRunning: false,
  sseSource: null,
  statsInterval: null,
  selectedCities: [],
  selectedCategories: [],
  allCities: [],
  allCategories: [],
  // CRM modal
  crmModalPlaceId: null,
  crmModalStatus: 'novo',
};

const CRM_LABELS = {
  novo:       'Não Abordado',
  enviado:    'Msg Enviada',
  respondeu:  'Respondeu',
  negociando: 'Negociando',
  fechado:    'Fechado ✓',
  descartado: 'Descartado',
};

// ── Utilities ──────────────────────────────────────────────────────────────────
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escapeAttr(str) {
  return escapeHtml(str);
}

function fmtNumber(val) {
  if (val == null || val === '') return '—';
  return Number(val).toLocaleString('pt-BR');
}

function fmtPct(val) {
  if (val == null || val === '') return '—';
  return Number(val).toFixed(1) + '%';
}

// ── Stats Polling ──────────────────────────────────────────────────────────────
function startStatsPolling() {
  fetchStats();
  fetchCrmStats();
  state.statsInterval = setInterval(() => {
    fetchStats();
    fetchCrmStats();
  }, 5000);
}

async function fetchStats() {
  try {
    const res = await fetch('/api/stats');
    if (!res.ok) return;
    const data = await res.json();
    updateStatCards(data);
    syncRunStatus(data.is_running === true);
  } catch (_) { /* silent */ }
}

function updateStatCards(data) {
  const fields = ['found', 'processed', 'qualified', 'hot', 'warm', 'errors'];
  fields.forEach(key => {
    const el = document.getElementById('stat-' + key);
    if (!el) return;
    const newVal = data[key] != null ? String(data[key]) : '0';
    if (el.textContent !== newVal) {
      el.textContent = newVal;
      el.classList.remove('stat-updated');
      void el.offsetWidth; // reflow to restart animation
      el.classList.add('stat-updated');
    }
  });

  // Conversion bar
  const found = parseInt(data.found) || 0;
  const qualified = parseInt(data.qualified) || 0;
  const pct = found > 0 ? Math.round((qualified / found) * 100) : 0;
  const bar = document.getElementById('conversion-bar');
  const pctEl = document.getElementById('conversion-pct');
  if (bar) bar.style.width = pct + '%';
  if (pctEl) pctEl.textContent = pct + '%';

  const ts = document.getElementById('last-updated');
  if (ts) ts.textContent = new Date().toLocaleTimeString('pt-BR');
}

function fmtCurrency(val) {
  if (val == null || val === 0) return 'R$ 0';
  return 'R$ ' + Number(val).toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

async function fetchCrmStats() {
  try {
    const res = await fetch('/api/crm/stats');
    if (!res.ok) return;
    const data = await res.json();
    Object.entries(data).forEach(([key, val]) => {
      const el = document.getElementById('crm-count-' + key);
      if (el) el.textContent = val;
    });
    // Revenue row
    const totalEl = document.getElementById('revenue-total');
    const avgEl   = document.getElementById('revenue-avg');
    const dealsEl = document.getElementById('revenue-deals');
    if (totalEl) totalEl.textContent = fmtCurrency(data.total_revenue);
    if (avgEl)   avgEl.textContent   = data.deals_count ? fmtCurrency(data.avg_deal) : '—';
    if (dealsEl) dealsEl.textContent = data.deals_count || 0;
  } catch (_) { /* silent */ }
}

function syncRunStatus(running) {
  if (state.isRunning === running) return;
  setRunningUI(running);
  // Auto-refresh leads when pipeline finishes
  if (!running && state.isRunning) {
    setTimeout(fetchLeads, 2500);
  }
}

// ── Run Controls ───────────────────────────────────────────────────────────────
function setRunningUI(running) {
  state.isRunning = running;

  const btnStart = document.getElementById('btn-start');
  const btnStop  = document.getElementById('btn-stop');
  const progress = document.getElementById('run-progress');
  const badge    = document.getElementById('run-status-badge');
  const bar      = document.getElementById('progress-bar-fill');
  const pctEl    = document.getElementById('progress-pct');

  if (btnStart) btnStart.disabled = running;
  if (btnStop)  btnStop.disabled  = !running;

  if (badge) {
    badge.textContent = running ? 'RODANDO' : 'PARADO';
    badge.className = 'status-badge ' + (running ? 'status-running' : 'status-idle');
  }

  if (running) {
    if (progress) progress.classList.remove('hidden');
    // Reset to indeterminate animation
    if (bar) { bar.className = 'progress-bar-fill indeterminate'; bar.style.width = ''; }
    if (pctEl) pctEl.textContent = '';
  } else {
    // Pipeline finished — hide the bar after a short delay
    // (100% was already set by the [COMPLETE] log event)
    setTimeout(() => {
      if (progress) progress.classList.add('hidden');
      if (bar) { bar.className = 'progress-bar-fill indeterminate'; bar.style.width = ''; }
      if (pctEl) pctEl.textContent = '';
    }, 3000);
  }
}

function updateRealProgress(done, total, pct) {
  const bar   = document.getElementById('progress-bar-fill');
  const label = document.getElementById('progress-label');
  const pctEl = document.getElementById('progress-pct');
  if (bar) {
    bar.className = 'progress-bar-fill';
    bar.style.width = pct + '%';
  }
  if (pct >= 100) {
    if (label) label.textContent = 'Concluído ✓';
    if (pctEl) pctEl.textContent = '100%';
  } else {
    if (label) label.textContent = `Combinação ${done}/${total}`;
    if (pctEl) pctEl.textContent = pct + '%';
  }
}

function wireRunControls() {
  document.getElementById('btn-start').addEventListener('click', async () => {
    const body = {
      max_apify_calls:    parseInt(document.getElementById('cfg-apify').value) || 50,
      selected_cities:    state.selectedCities.length ? state.selectedCities : null,
      selected_categories: state.selectedCategories.length ? state.selectedCategories : null,
      skip_sheets: document.getElementById('cfg-skip-sheets').checked,
      skip_email:  document.getElementById('cfg-skip-email').checked,
    };
    try {
      const res = await fetch('/api/run/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        setRunningUI(true);
        const label = document.getElementById('progress-label');
        if (label) label.textContent = 'Pipeline iniciado...';
      } else {
        const err = await res.json().catch(() => ({}));
        alert('Erro ao iniciar: ' + (err.error || 'HTTP ' + res.status));
      }
    } catch (e) {
      alert('Erro de conexão: ' + e.message);
    }
  });

  document.getElementById('btn-stop').addEventListener('click', async () => {
    try {
      await fetch('/api/run/stop', { method: 'POST' });
      setRunningUI(false);
    } catch (e) {
      alert('Erro ao parar: ' + e.message);
    }
  });
}

// ── SSE Log Stream ─────────────────────────────────────────────────────────────
function connectSSE() {
  if (state.sseSource) {
    state.sseSource.close();
    state.sseSource = null;
  }

  const statusEl = document.getElementById('sse-status');
  if (statusEl) {
    statusEl.textContent = '● Conectando...';
    statusEl.className = 'sse-status sse-connecting';
  }

  const source = new EventSource('/api/stream-logs');
  state.sseSource = source;

  source.onopen = () => {
    if (statusEl) {
      statusEl.textContent = '● Conectado';
      statusEl.className = 'sse-status sse-connected';
    }
  };

  source.onmessage = (event) => {
    if (!event.data || event.data.startsWith(':')) return; // skip keepalive comments
    appendLogLine(event.data);

    // Parse real progress from pipeline logs
    if (event.data.includes('[PROGRESS]')) {
      const m = event.data.match(/\[PROGRESS\]\s+(\d+)\/(\d+)\s+\((\d+)%\)/);
      if (m) {
        // Cap at 95% until [COMPLETE] fires — leave room for export/sheets step
        const pct = Math.min(parseInt(m[3]), 95);
        updateRealProgress(m[1], m[2], pct);
      }
      return;
    }

    // [COMPLETE] fires only after sheets/email/export are done
    if (event.data.includes('[COMPLETE]')) {
      updateRealProgress('✓', '✓', 100);
      return;
    }

    // Update progress label with last processing line
    if (event.data.includes('Processando ')) {
      const label = document.getElementById('progress-label');
      if (label) {
        const match = event.data.match(/Processando (.+?)(\s*\(|$)/);
        if (match) label.textContent = 'Analisando: ' + match[1].trim().slice(0, 80);
      }
    }
  };

  source.onerror = () => {
    if (statusEl) {
      statusEl.textContent = '● Reconectando...';
      statusEl.className = 'sse-status sse-error';
    }
    // EventSource auto-reconnects; no manual retry needed
  };
}

function appendLogLine(text) {
  const container = document.getElementById('log-container');
  if (!container) return;

  // Remove placeholder
  const empty = container.querySelector('.log-empty');
  if (empty) empty.remove();

  const level = detectLogLevel(text);
  state.logLineCount++;

  // Apply log filter
  const visible = (state.logFilter === 'ALL') ||
                  (state.logFilter === level) ||
                  (state.logFilter === 'ERROR' && (level === 'ERROR'));

  const span = document.createElement('span');
  span.className = `log-line log-line--${level.toLowerCase()} log-line--new`;
  if (!visible) span.style.display = 'none';
  span.textContent = text;
  container.appendChild(span);

  // Cap DOM at 500 lines
  while (container.children.length > 500) {
    container.removeChild(container.firstChild);
  }

  const countEl = document.getElementById('log-line-count');
  if (countEl) countEl.textContent = state.logLineCount + ' linhas';

  const autoScroll = document.getElementById('log-autoscroll');
  if (autoScroll && autoScroll.checked) {
    container.scrollTop = container.scrollHeight;
  }
}

function detectLogLevel(text) {
  if (text.includes('[ERROR]') || text.includes('[CRITICAL]')) return 'ERROR';
  if (text.includes('[WARNING]') || text.includes('[WARN]'))   return 'WARN';
  if (text.includes('[DEBUG]'))  return 'DEBUG';
  return 'INFO';
}

function wireLogControls() {
  document.getElementById('btn-clear-log').addEventListener('click', () => {
    const container = document.getElementById('log-container');
    container.innerHTML = '<span class="log-empty">Log limpo.</span>';
    state.logLineCount = 0;
    const countEl = document.getElementById('log-line-count');
    if (countEl) countEl.textContent = '0 linhas';
  });

  document.querySelectorAll('.log-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.log-filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.logFilter = btn.dataset.level;
      applyLogLevelFilter();
    });
  });
}

function applyLogLevelFilter() {
  const container = document.getElementById('log-container');
  if (!container) return;
  Array.from(container.querySelectorAll('.log-line')).forEach(el => {
    const level = Array.from(el.classList)
      .find(c => c.startsWith('log-line--') && c !== 'log-line--new')
      ?.replace('log-line--', '').toUpperCase() || 'INFO';
    el.style.display = (state.logFilter === 'ALL' || state.logFilter === level) ? '' : 'none';
  });
}

// ── Leads Table ────────────────────────────────────────────────────────────────
async function fetchLeads() {
  try {
    const res = await fetch('/api/leads');
    if (!res.ok) return;
    state.leads = await res.json();
    renderLeadsTable();
  } catch (_) { /* silent */ }
}

function getFilteredLeads() {
  const q = state.search.toLowerCase().trim();
  return state.leads.filter(lead => {
    if (state.filter !== 'ALL' && lead.status !== state.filter) return false;
    if (state.onlyNew && lead.is_new === false) return false;
    if (state.crmFilter !== 'ALL' && (lead.crm_status || 'novo') !== state.crmFilter) return false;
    if (!q) return true;
    return [lead.name, lead.neighborhood, lead.city, lead.category, lead.instagram_username]
      .some(v => v && v.toLowerCase().includes(q));
  });
}

function buildStatusBadge(status, lead) {
  let badge = '';
  if (status === 'HOT')  badge = '<span class="badge badge-hot">HOT 🔥</span>';
  else if (status === 'WARM') badge = '<span class="badge badge-warm">WARM ✓</span>';
  else badge = `<span class="badge">${escapeHtml(status)}</span>`;

  if (lead.is_new === true) {
    badge += ' <span class="badge badge-new">NOVO</span>';
  } else if (lead.is_new === false) {
    const times = lead.run_count > 1 ? `${lead.run_count}×` : '';
    badge += ` <span class="badge badge-seen">VISTO ${times}</span>`;
  }
  return badge;
}

function scoreClass(score) {
  if (score >= 75) return 'score-high';
  if (score >= 60) return 'score-mid';
  return 'score-low';
}

function renderLeadsTable() {
  const tbody = document.getElementById('leads-tbody');
  if (!tbody) return;

  const leads = getFilteredLeads();
  const countEl = document.getElementById('leads-count');
  if (countEl) {
    const suffix = state.filter !== 'ALL' ? ` (${state.filter})` : '';
    countEl.textContent = leads.length + ' leads' + suffix;
  }

  if (!leads.length) {
    tbody.innerHTML = '<tr class="table-empty-row"><td colspan="9">Nenhum lead encontrado.</td></tr>';
    return;
  }

  tbody.innerHTML = leads.map(lead => {
    const crm = lead.crm_status || 'novo';
    const crmLabel = CRM_LABELS[crm] || crm;
    const crmNote = lead.crm_note ? `<div class="crm-note-preview">${escapeHtml(lead.crm_note.slice(0, 60))}${lead.crm_note.length > 60 ? '…' : ''}</div>` : '';
    const contactedAt = lead.contacted_at ? `<div class="crm-date">Enviado ${escapeHtml(lead.contacted_at)}</div>` : '';
    const contractVal = (crm === 'fechado' && lead.contract_value)
      ? `<div class="crm-contract-display">${fmtCurrency(lead.contract_value)}</div>` : '';

    const phone = lead.phone
      ? `<a href="https://wa.me/55${lead.phone.replace(/\D/g,'')}" target="_blank" class="btn-copy" title="Abrir WhatsApp">📱 ${escapeHtml(lead.phone)}</a>`
      : '';

    const igLink = lead.instagram_username
      ? `<a href="https://instagram.com/${escapeAttr(lead.instagram_username)}" target="_blank" class="btn-copy" title="Ver Instagram">@${escapeHtml(lead.instagram_username)}</a>`
      : '';

    const emailLink = lead.contact_email
      ? `<a href="mailto:${escapeAttr(lead.contact_email)}" class="btn-copy btn-copy-email" title="Abrir cliente de e-mail">📧 ${escapeHtml(lead.contact_email)}</a>`
      : '';

    const mapsLink = lead.maps_url
      ? `<a href="${escapeAttr(lead.maps_url)}" target="_blank" class="btn-copy btn-copy-maps" title="Ver no Maps">Maps</a>`
      : '';

    const copyWA = lead.whatsapp_message
      ? `<button class="btn-copy" data-msg="${escapeAttr(lead.whatsapp_message)}" title="Copiar 1ª mensagem WhatsApp"><span>📋</span> 1º Contato</button>`
      : '';

    const copyFU = lead.whatsapp_followup
      ? `<button class="btn-copy btn-copy-fu" data-msg="${escapeAttr(lead.whatsapp_followup)}" title="Copiar follow-up (3 dias depois)"><span>🔁</span> Follow-up</button>`
      : '';

    const copyIG = lead.instagram_dm
      ? `<button class="btn-copy" data-msg="${escapeAttr(lead.instagram_dm)}" title="Copiar Instagram DM"><span>📋</span> Instagram</button>`
      : '';

    const emailFull = lead.email_body
      ? 'Assunto: ' + (lead.subject_email || '') + '\n\n' + lead.email_body
      : '';
    const copyEmail = emailFull
      ? `<button class="btn-copy btn-copy-email" data-msg="${escapeAttr(emailFull)}" title="Copiar e-mail completo (assunto + corpo)"><span>📧</span> E-mail</button>`
      : '';

    return `
      <tr data-place-id="${escapeAttr(lead.place_id || '')}" class="crm-row crm-row--${crm}">
        <td class="col-score" data-label="Score">
          ${buildStatusBadge(lead.status, lead)}
          <span class="score-num ${scoreClass(lead.score)}">${lead.score}</span>
        </td>
        <td class="col-name" data-label="Restaurante">
          <div class="restaurant-name">${escapeHtml(lead.name)}</div>
          <div class="restaurant-cat">${escapeHtml(lead.category || '')}</div>
        </td>
        <td class="col-bairro" data-label="Bairro">${escapeHtml(lead.neighborhood || lead.city || '—')}</td>
        <td class="col-contato" data-label="Contato">
          <div class="restaurant-contact">${phone}${igLink}${emailLink}${mapsLink}</div>
        </td>
        <td class="col-link" data-label="Link"><span class="link-tag">${escapeHtml(lead.link_type_label || '—')}</span></td>
        <td class="col-instagram" data-label="Instagram">${fmtNumber(lead.followers_count)}<br><small class="text-dim">${fmtPct(lead.engagement_rate)} eng.</small></td>
        <td class="col-google" data-label="Google">${fmtNumber(lead.google_reviews)} <small class="text-dim">${lead.google_rating ? lead.google_rating + '★' : ''}</small></td>
        <td class="col-crm" data-label="CRM">
          <button class="crm-badge crm-badge--${crm} btn-open-crm"
                  data-place-id="${escapeAttr(lead.place_id || '')}"
                  data-name="${escapeAttr(lead.name || '')}"
                  data-crm="${crm}"
                  title="Atualizar status de abordagem">
            ${escapeHtml(crmLabel)}
          </button>
          ${contractVal}
          ${crmNote}
          ${contactedAt}
        </td>
        <td class="col-actions" data-label="Mensagens">
          <div class="action-group">
            ${copyWA}
            ${copyFU}
            ${copyIG}
            ${copyEmail}
          </div>
        </td>
      </tr>`;
  }).join('');
}

function wireLeadsControls() {
  // Score filter pills
  document.querySelectorAll('#filter-pills .filter-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#filter-pills .filter-pill').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.filter = btn.dataset.filter || 'ALL';
      renderLeadsTable();
    });
  });

  // CRM filter pills
  document.querySelectorAll('#crm-filter-pills .filter-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#crm-filter-pills .filter-pill').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.crmFilter = btn.dataset.crmFilter || 'ALL';
      renderLeadsTable();
    });
  });

  // Also allow clicking funnel stages
  document.querySelectorAll('.funnel-stage[data-crm]').forEach(el => {
    el.style.cursor = 'pointer';
    el.addEventListener('click', () => {
      const crm = el.dataset.crm;
      state.crmFilter = crm;
      document.querySelectorAll('#crm-filter-pills .filter-pill').forEach(b => {
        b.classList.toggle('active', b.dataset.crmFilter === crm);
      });
      renderLeadsTable();
      document.getElementById('leads-table')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });

  // Search
  document.getElementById('leads-search').addEventListener('input', e => {
    state.search = e.target.value;
    renderLeadsTable();
  });

  // "Apenas novos" toggle
  const btnOnlyNew = document.getElementById('btn-only-new');
  if (btnOnlyNew) {
    btnOnlyNew.addEventListener('click', () => {
      state.onlyNew = !state.onlyNew;
      btnOnlyNew.dataset.onlyNew = String(state.onlyNew);
      btnOnlyNew.classList.toggle('active', state.onlyNew);
      renderLeadsTable();
    });
  }

  // Refresh button
  document.getElementById('btn-refresh-leads').addEventListener('click', fetchLeads);

  // Message preview modal
  let _previewSourceBtn = null;
  document.getElementById('modal-msg-preview-close').addEventListener('click', () => {
    document.getElementById('modal-msg-preview').classList.add('hidden');
    _previewSourceBtn = null;
  });
  document.getElementById('modal-msg-preview').addEventListener('click', e => {
    if (e.target === document.getElementById('modal-msg-preview')) {
      document.getElementById('modal-msg-preview').classList.add('hidden');
      _previewSourceBtn = null;
    }
  });
  document.getElementById('msg-preview-copy-btn').addEventListener('click', async () => {
    const msg = document.getElementById('msg-preview-body').textContent;
    try {
      await navigator.clipboard.writeText(msg);
    } catch (_) {
      const ta = document.createElement('textarea');
      ta.value = msg;
      ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    const btn = document.getElementById('msg-preview-copy-btn');
    const orig = btn.innerHTML;
    btn.classList.add('copied');
    btn.innerHTML = '<span>✓</span> Copiado!';
    setTimeout(() => { btn.classList.remove('copied'); btn.innerHTML = orig; }, 2000);
    if (_previewSourceBtn) {
      const origSrc = _previewSourceBtn.innerHTML;
      _previewSourceBtn.classList.add('copied');
      _previewSourceBtn.innerHTML = '<span>✓</span> Copiado!';
      setTimeout(() => { _previewSourceBtn.classList.remove('copied'); _previewSourceBtn.innerHTML = origSrc; }, 2000);
    }
  });

  // Copy buttons — open preview modal instead of copying directly
  document.getElementById('leads-tbody').addEventListener('click', async e => {
    const copyBtn = e.target.closest('.btn-copy[data-msg]');
    if (copyBtn) {
      const msg = copyBtn.dataset.msg;
      const title = copyBtn.title || 'Mensagem';
      document.getElementById('msg-preview-title').textContent = title;
      document.getElementById('msg-preview-body').textContent = msg;
      document.getElementById('msg-preview-copy-btn').innerHTML = '📋 Copiar';
      document.getElementById('msg-preview-copy-btn').classList.remove('copied');
      _previewSourceBtn = copyBtn;
      document.getElementById('modal-msg-preview').classList.remove('hidden');
      return;
    }

    // Open CRM modal
    const crmBtn = e.target.closest('.btn-open-crm');
    if (crmBtn) {
      openCrmModal(
        crmBtn.dataset.placeId,
        crmBtn.dataset.name,
        crmBtn.dataset.crm,
      );
    }
  });
}

// ── CRM Modal ─────────────────────────────────────────────────────────────────
function openCrmModal(placeId, name, currentStatus) {
  state.crmModalPlaceId = placeId;
  state.crmModalStatus = currentStatus || 'novo';

  const lead = state.leads.find(l => l.place_id === placeId);
  const history = lead ? (lead.crm_history || []) : [];
  const note = lead ? (lead.crm_note || '') : '';
  const contractValue = lead ? (lead.contract_value || '') : '';

  // Contract value field — show for all, highlight when fechado
  const valInput = document.getElementById('crm-contract-value');
  if (valInput) valInput.value = contractValue || '';

  document.getElementById('crm-modal-name').textContent = name || 'Lead';
  document.getElementById('crm-note-input').value = note;

  // Set active status button
  document.querySelectorAll('.crm-status-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.status === state.crmModalStatus);
  });
  document.querySelectorAll('.crm-status-btn').forEach(btn => {
    btn.onclick = () => {
      state.crmModalStatus = btn.dataset.status;
      document.querySelectorAll('.crm-status-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      updateCrmCurrentLabel();
      // Highlight value field when fechado is selected
      const wrap = document.getElementById('crm-value-wrap');
      if (wrap) wrap.classList.toggle('crm-value-highlighted', btn.dataset.status === 'fechado');
    };
  });

  // Pre-highlight if already fechado
  const wrap = document.getElementById('crm-value-wrap');
  if (wrap) wrap.classList.toggle('crm-value-highlighted', (currentStatus || 'novo') === 'fechado');

  updateCrmCurrentLabel();
  renderCrmHistory(history);
  document.getElementById('modal-crm').classList.remove('hidden');
}

function updateCrmCurrentLabel() {
  const el = document.getElementById('crm-current-status-label');
  if (el) el.textContent = 'Status: ' + (CRM_LABELS[state.crmModalStatus] || state.crmModalStatus);
}

function renderCrmHistory(history) {
  const el = document.getElementById('crm-history-list');
  if (!el) return;
  if (!history || !history.length) {
    el.innerHTML = '<span class="log-empty">Sem histórico ainda.</span>';
    return;
  }
  el.innerHTML = history.slice().reverse().map(h => `
    <div class="crm-history-item">
      <span class="crm-history-date">${escapeHtml(h.at || '')}</span>
      <span class="crm-history-arrow">${escapeHtml(CRM_LABELS[h.from] || h.from)} → <strong>${escapeHtml(CRM_LABELS[h.to] || h.to)}</strong></span>
      ${h.note ? `<span class="crm-history-note">${escapeHtml(h.note)}</span>` : ''}
    </div>
  `).join('');
}

async function saveCrmModal() {
  const placeId = state.crmModalPlaceId;
  if (!placeId) return;
  const note = document.getElementById('crm-note-input').value;
  const valRaw = document.getElementById('crm-contract-value')?.value;
  const contractValue = valRaw !== '' && valRaw != null ? parseFloat(valRaw) : null;
  try {
    const res = await fetch(`/api/crm/${encodeURIComponent(placeId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: state.crmModalStatus, note, contract_value: contractValue }),
    });
    if (!res.ok) { alert('Erro ao salvar CRM'); return; }
    const data = await res.json();
    // Update in-memory lead
    const lead = state.leads.find(l => l.place_id === placeId);
    if (lead) {
      lead.crm_status      = data.entry.status;
      lead.crm_note        = data.entry.note;
      lead.crm_history     = data.entry.history;
      lead.contacted_at    = data.entry.contacted_at;
      lead.contract_value  = data.entry.contract_value;
    }
    document.getElementById('modal-crm').classList.add('hidden');
    renderLeadsTable();
    fetchCrmStats();
  } catch (err) {
    alert('Erro de conexão: ' + err.message);
  }
}

function wireCrmModal() {
  document.getElementById('modal-crm-close').addEventListener('click', () => {
    document.getElementById('modal-crm').classList.add('hidden');
  });
  document.getElementById('modal-crm').addEventListener('click', e => {
    if (e.target === document.getElementById('modal-crm'))
      document.getElementById('modal-crm').classList.add('hidden');
  });
  document.getElementById('crm-save-btn').addEventListener('click', saveCrmModal);
}

// ── City / Category Selectors ─────────────────────────────────────────────────
const BURGER_CATS = ['hamburgueria artesanal', 'smash burger', 'burger artesanal'];

async function loadTargets() {
  try {
    const res = await fetch('/api/config/targets');
    if (!res.ok) return;
    const data = await res.json();
    state.allCities = data.cities || [];
    state.allCategories = data.categories || [];
    updateCitiesSummary();
    updateCategoriesSummary();
  } catch (_) { /* silent */ }
}

function renderCitiesModal() {
  const list = document.getElementById('cities-list');
  if (!list) return;
  const cities = state.allCities;
  const allSelected = state.selectedCities.length === 0;

  // Group by city name (part after comma)
  const groups = {};
  const groupOrder = [];
  cities.forEach(c => {
    const comma = c.indexOf(',');
    const key = comma > -1 ? c.slice(comma + 1).trim() : 'Outras';
    if (!groups[key]) { groups[key] = []; groupOrder.push(key); }
    groups[key].push(c);
  });

  // São Paulo first
  const ordered = ['São Paulo', ...groupOrder.filter(k => k !== 'São Paulo')];

  list.innerHTML = ordered.filter(g => groups[g]).map(group => `
    <div class="sel-group">
      <div class="sel-group-label">${escapeHtml(group)}</div>
      ${groups[group].map(city => {
        const label = city.indexOf(',') > -1 ? city.slice(0, city.indexOf(',')).trim() : city;
        const checked = allSelected || state.selectedCities.includes(city);
        return `<label class="sel-item">
          <input type="checkbox" class="sel-check city-check" value="${escapeAttr(city)}"${checked ? ' checked' : ''}>
          <span class="sel-item-label">${escapeHtml(label)}</span>
        </label>`;
      }).join('')}
    </div>
  `).join('');

  updateCitiesCount();
  list.querySelectorAll('.city-check').forEach(cb => cb.addEventListener('change', updateCitiesCount));
}

function renderCategoriesModal() {
  const list = document.getElementById('categories-list');
  if (!list) return;
  const cats = state.allCategories;
  const allSelected = state.selectedCategories.length === 0;

  list.innerHTML = `<div class="sel-group"><div class="sel-group-label">Todas as categorias</div>${
    cats.map(cat => {
      const checked = allSelected || state.selectedCategories.includes(cat);
      return `<label class="sel-item">
        <input type="checkbox" class="sel-check cat-check" value="${escapeAttr(cat)}"${checked ? ' checked' : ''}>
        <span class="sel-item-label">${escapeHtml(cat)}</span>
      </label>`;
    }).join('')
  }</div>`;

  updateCategoriesCount();
  list.querySelectorAll('.cat-check').forEach(cb => cb.addEventListener('change', updateCategoriesCount));
}

function updateCitiesCount() {
  const count = document.querySelectorAll('.city-check:checked').length;
  const el = document.getElementById('cities-count');
  if (el) el.textContent = count + ' selecionadas';
}

function updateCategoriesCount() {
  const count = document.querySelectorAll('.cat-check:checked').length;
  const el = document.getElementById('categories-count');
  if (el) el.textContent = count + ' selecionadas';
}

function updateCitiesSummary() {
  const el = document.getElementById('cities-summary');
  if (!el) return;
  if (state.selectedCities.length === 0) {
    el.textContent = `Todas (${state.allCities.length || '…'})`;
  } else {
    const spCount = state.selectedCities.filter(c => c.includes('São Paulo')).length;
    if (spCount === state.selectedCities.length) {
      el.textContent = `São Paulo (${spCount})`;
    } else {
      el.textContent = `${state.selectedCities.length} cidade${state.selectedCities.length > 1 ? 's' : ''}`;
    }
  }
}

function updateCategoriesSummary() {
  const el = document.getElementById('categories-summary');
  if (!el) return;
  if (state.selectedCategories.length === 0) {
    el.textContent = `Todas (${state.allCategories.length || '…'})`;
  } else {
    el.textContent = `${state.selectedCategories.length} categoria${state.selectedCategories.length > 1 ? 's' : ''}`;
  }
}

function setChecks(selector, predicate) {
  document.querySelectorAll(selector).forEach(cb => { cb.checked = predicate(cb.value); });
}

function wireSelectorModals() {
  // ── Cities ──
  const citiesOverlay = document.getElementById('modal-cities');
  document.getElementById('btn-select-cities').addEventListener('click', () => {
    renderCitiesModal();
    citiesOverlay.classList.remove('hidden');
  });
  document.getElementById('modal-cities-close').addEventListener('click', () => citiesOverlay.classList.add('hidden'));
  citiesOverlay.addEventListener('click', e => { if (e.target === citiesOverlay) citiesOverlay.classList.add('hidden'); });

  document.getElementById('cities-sp').addEventListener('click', () => {
    setChecks('.city-check', v => v.includes('São Paulo'));
    updateCitiesCount();
  });
  document.getElementById('cities-all').addEventListener('click', () => {
    setChecks('.city-check', () => true);
    updateCitiesCount();
  });
  document.getElementById('cities-none').addEventListener('click', () => {
    setChecks('.city-check', () => false);
    updateCitiesCount();
  });
  document.getElementById('cities-confirm').addEventListener('click', () => {
    const checked = [...document.querySelectorAll('.city-check:checked')].map(cb => cb.value);
    state.selectedCities = checked.length === state.allCities.length ? [] : checked;
    updateCitiesSummary();
    citiesOverlay.classList.add('hidden');
  });

  // ── Categories ──
  const catsOverlay = document.getElementById('modal-categories');
  document.getElementById('btn-select-categories').addEventListener('click', () => {
    renderCategoriesModal();
    catsOverlay.classList.remove('hidden');
  });
  document.getElementById('modal-categories-close').addEventListener('click', () => catsOverlay.classList.add('hidden'));
  catsOverlay.addEventListener('click', e => { if (e.target === catsOverlay) catsOverlay.classList.add('hidden'); });

  document.getElementById('cats-burgers').addEventListener('click', () => {
    setChecks('.cat-check', v => BURGER_CATS.includes(v));
    updateCategoriesCount();
  });
  document.getElementById('cats-all').addEventListener('click', () => {
    setChecks('.cat-check', () => true);
    updateCategoriesCount();
  });
  document.getElementById('cats-none').addEventListener('click', () => {
    setChecks('.cat-check', () => false);
    updateCategoriesCount();
  });
  document.getElementById('categories-confirm').addEventListener('click', () => {
    const checked = [...document.querySelectorAll('.cat-check:checked')].map(cb => cb.value);
    state.selectedCategories = checked.length === state.allCategories.length ? [] : checked;
    updateCategoriesSummary();
    catsOverlay.classList.add('hidden');
  });
}

// ── Guided Tour ────────────────────────────────────────────────────────────────
function startTour() {
  if (typeof window.driver === 'undefined') {
    alert('Biblioteca do tour não carregou. Verifique sua conexão com a internet.');
    return;
  }
  const driverObj = window.driver.js.driver({
    popoverClass: 'lh-tour',
    showProgress: true,
    animate: true,
    smoothScroll: true,
    overlayColor: 'rgba(8,8,8,0.88)',
    nextBtnText: 'Próximo →',
    prevBtnText: '← Anterior',
    doneBtnText: 'Concluir ✓',
    progressText: '{{current}} de {{total}}',
    steps: [
      {
        element: '#run-status-badge',
        popover: {
          title: 'Status do Pipeline',
          description: '<b>PARADO</b> = nenhuma busca ativa. <b>RODANDO</b> = pipeline coletando leads agora. O badge pisca em laranja durante a execução.',
          side: 'bottom', align: 'end',
        },
      },
      {
        element: '.stats-grid',
        popover: {
          title: 'Painel de Estatísticas',
          description: '<b>Encontrados:</b> total de restaurantes no Maps.<br><b>Processados:</b> já analisados.<br><b>Qualificados:</b> HOT + WARM juntos.<br><b>HOT 🔥</b> = score ≥75 — abordar essa semana.<br><b>WARM ✓</b> = score 60-74 — abordar no mês.',
          side: 'bottom', align: 'start',
        },
      },
      {
        element: '.conversion-bar-wrap',
        popover: {
          title: 'Taxa de Qualificação',
          description: 'Percentual de restaurantes encontrados que passaram na qualificação. Uma taxa saudável fica entre 15% e 35%.',
          side: 'top', align: 'start',
        },
      },
      {
        element: '#cfg-apify',
        popover: {
          title: 'Configuração: Apify',
          description: 'Limita quantos perfis do Instagram serão buscados por rodada. O plano gratuito tem ~250/mês. Use <b>50</b> por rodada para não esgotar o crédito.',
          side: 'bottom', align: 'start',
        },
      },
      {
        element: '#cfg-cities',
        popover: {
          title: 'Configuração: Cidades e Categorias',
          description: '<b>0 = busca completa</b> (17 cidades × 14 categorias = centenas de leads). Para testes rápidos, use <b>1</b> cidade e <b>1</b> categoria.',
          side: 'bottom', align: 'start',
        },
      },
      {
        element: '#btn-start',
        popover: {
          title: 'Iniciar Busca',
          description: 'Clique aqui para disparar o pipeline. O processo roda em background — você pode fechar o painel e ele continua. O botão <b>Parar</b> encerra a execução a qualquer momento.',
          side: 'bottom', align: 'start',
        },
      },
      {
        element: '#log-container',
        popover: {
          title: 'Log em Tempo Real',
          description: 'Acompanhe o que o sistema está fazendo agora. Cores:<br>• <span style="color:#6b7280">Cinza = INFO</span> (progresso normal)<br>• <span style="color:#FFB703">Amarelo = AVISO</span><br>• <span style="color:#C8102E">Vermelho = ERRO</span><br><br>Use os filtros para focar no que importa.',
          side: 'top', align: 'start',
        },
      },
      {
        element: '#filter-pills',
        popover: {
          title: 'Filtros de Leads',
          description: '<b>HOT 🔥</b> = prioridade máxima, abordar essa semana.<br><b>WARM ✓</b> = bom potencial, abordar no mês.<br><b>✦ Apenas novos</b> = esconde leads de rodadas anteriores, mostra só os descobertos recentemente.',
          side: 'bottom', align: 'start',
        },
      },
      {
        element: '#leads-search',
        popover: {
          title: 'Busca de Leads',
          description: 'Digite o nome do restaurante, bairro, categoria ou @ do Instagram para filtrar a tabela em tempo real.',
          side: 'bottom', align: 'end',
        },
      },
      {
        element: '.leads-table tbody tr:first-child .btn-copy',
        popover: {
          title: 'Copiar Mensagem',
          description: '<b>Copiar WA</b> = copia a mensagem de WhatsApp personalizada, pronta para colar no chat.<br><b>Copiar IG</b> = versão adaptada para Direct do Instagram.<br><br>Cada mensagem referencia algo específico do restaurante.',
          side: 'left', align: 'start',
        },
      },
      {
        element: '.export-group',
        popover: {
          title: 'Exportar Leads',
          description: '<b>CSV</b> = abre no Excel. <b>JSON</b> = para integrar com outros sistemas. <b>HTML</b> = relatório visual abre no navegador.<br><br>Os arquivos ficam na pasta <code>exports/</code> do projeto.',
          side: 'top', align: 'end',
        },
      },
    ],
  });
  driverObj.drive();
}

// ── Init ───────────────────────────────────────────────────────────────────────
function init() {
  // Wire controls — each wrapped so one failure doesn't block the others
  try { wireRunControls(); }    catch(e) { console.error('wireRunControls', e); }
  try { wireLogControls(); }    catch(e) { console.error('wireLogControls', e); }
  try { wireLeadsControls(); }  catch(e) { console.error('wireLeadsControls', e); }
  try { wireSelectorModals(); } catch(e) { console.error('wireSelectorModals', e); }
  try { wireCrmModal(); }       catch(e) { console.error('wireCrmModal', e); }

  // Data — must run regardless of UI wiring errors
  fetchLeads();
  startStatsPolling();
  connectSSE();
  loadTargets();

  const btnTour = document.getElementById('btn-tour');
  if (btnTour) btnTour.addEventListener('click', startTour);
}

document.addEventListener('DOMContentLoaded', init);
