/* ═══════════════════════════════════════════════════════
   LEAD HUNTER DASHBOARD — Client-Side Logic
   ═══════════════════════════════════════════════════════ */

'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  leads: [],
  filter: 'ALL',
  search: '',
  onlyNew: false,
  logFilter: 'ALL',
  logLineCount: 0,
  isRunning: false,
  sseSource: null,
  statsInterval: null,
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
  state.statsInterval = setInterval(fetchStats, 3000);
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

  if (btnStart) btnStart.disabled = running;
  if (btnStop)  btnStop.disabled  = !running;
  if (progress) progress.classList.toggle('hidden', !running);

  if (badge) {
    badge.textContent = running ? 'RODANDO' : 'PARADO';
    badge.className = 'status-badge ' + (running ? 'status-running' : 'status-idle');
  }
}

function wireRunControls() {
  document.getElementById('btn-start').addEventListener('click', async () => {
    const body = {
      max_apify_calls: parseInt(document.getElementById('cfg-apify').value) || 50,
      limit_cities:    parseInt(document.getElementById('cfg-cities').value) || 0,
      limit_categories: parseInt(document.getElementById('cfg-categories').value) || 0,
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

    // Update progress label with last processing line
    if (event.data.includes('Processando ') || event.data.includes('Resumo final')) {
      const label = document.getElementById('progress-label');
      if (label) {
        const match = event.data.match(/\] (.+)$/);
        if (match) label.textContent = match[1].slice(0, 120);
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
    const matchStatus = state.filter === 'ALL' || lead.status === state.filter;
    if (!matchStatus) return false;
    if (state.onlyNew && lead.is_new === false) return false;
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
    const strengths = (lead.key_strengths || [])
      .map(s => `<li>${escapeHtml(s)}</li>`).join('');

    const phone = lead.phone
      ? `<a href="https://wa.me/55${lead.phone.replace(/\D/g,'')}" target="_blank" class="btn-copy" title="Abrir WhatsApp">
           📱 ${escapeHtml(lead.phone)}
         </a>`
      : '';

    const igLink = lead.instagram_username
      ? `<a href="https://instagram.com/${escapeAttr(lead.instagram_username)}" target="_blank" class="btn-copy" title="Ver Instagram">
           @${escapeHtml(lead.instagram_username)}
         </a>`
      : '';

    const mapsLink = lead.maps_url
      ? `<a href="${escapeAttr(lead.maps_url)}" target="_blank" class="btn-copy btn-copy-maps" title="Ver no Maps">Maps</a>`
      : '';

    const copyWA = lead.whatsapp_message
      ? `<button class="btn-copy" data-msg="${escapeAttr(lead.whatsapp_message)}" data-label="WA" title="Copiar mensagem WhatsApp">
           <span>📋</span> Copiar WA
         </button>`
      : '';

    const copyIG = lead.instagram_dm
      ? `<button class="btn-copy" data-msg="${escapeAttr(lead.instagram_dm)}" data-label="IG" title="Copiar mensagem Instagram">
           <span>📋</span> Copiar IG
         </button>`
      : '';

    return `
      <tr>
        <td>${buildStatusBadge(lead.status, lead)}</td>
        <td><span class="score-num ${scoreClass(lead.score)}">${lead.score}</span></td>
        <td>
          <div class="restaurant-name">${escapeHtml(lead.name)}</div>
          <div class="restaurant-cat">${escapeHtml(lead.category || '')}</div>
          <div style="margin-top:4px;display:flex;gap:4px;flex-wrap:wrap">${phone}${igLink}</div>
        </td>
        <td>${escapeHtml(lead.neighborhood || lead.city || '—')}</td>
        <td><span class="link-tag">${escapeHtml(lead.link_type_label || '—')}</span></td>
        <td>${fmtNumber(lead.followers_count)}<br><small class="text-dim">${fmtPct(lead.engagement_rate)} eng.</small></td>
        <td>${fmtNumber(lead.google_reviews)}<br><small class="text-dim">${lead.google_rating ? lead.google_rating + '★' : ''}</small></td>
        <td><ul class="strengths-list">${strengths}</ul></td>
        <td>
          <div class="action-group">
            ${copyWA}
            ${copyIG}
            ${mapsLink}
          </div>
        </td>
      </tr>`;
  }).join('');
}

function wireLeadsControls() {
  // Filter pills
  document.querySelectorAll('.filter-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-pill').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.filter = btn.dataset.filter;
      renderLeadsTable();
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

  // Copy to clipboard — event delegation on tbody
  document.getElementById('leads-tbody').addEventListener('click', async e => {
    const btn = e.target.closest('.btn-copy[data-msg]');
    if (!btn) return;
    const msg = btn.dataset.msg;
    try {
      await navigator.clipboard.writeText(msg);
    } catch (_) {
      // Fallback for non-HTTPS
      const ta = document.createElement('textarea');
      ta.value = msg;
      ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    // Visual feedback
    const originalHTML = btn.innerHTML;
    btn.classList.add('copied');
    btn.innerHTML = '<span>✓</span> Copiado!';
    setTimeout(() => {
      btn.classList.remove('copied');
      btn.innerHTML = originalHTML;
    }, 2000);
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
  wireRunControls();
  wireLogControls();
  wireLeadsControls();

  fetchLeads();
  startStatsPolling();
  connectSSE();

  // Guided tour button
  const btnTour = document.getElementById('btn-tour');
  if (btnTour) {
    btnTour.addEventListener('click', startTour);
  }
}

document.addEventListener('DOMContentLoaded', init);
