/**
 * monitor.js — Subagent Monitor
 *
 * Dynamic modal following the Gallery/Tasks pattern.
 * Shows subagent runs, status, tree view, controls.
 */

import * as Modals from './modalManager.js';
import { makeWindowDraggable } from './windowDrag.js';

let _open = false;
let _runs = [];
let _refreshTimer = null;
const REFRESH_INTERVAL = 8000;

// ---- Public API ----

export function openMonitor() {
  if (Modals.isRegistered('monitor-modal') && Modals.isMinimized('monitor-modal')) {
    Modals.restore('monitor-modal');
    return;
  }
  if (_open) return;
  _open = true;

  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.id = 'monitor-modal';
  modal.innerHTML = `
    <div class="modal-content monitor-modal-content" style="width:720px;max-width:92vw;max-height:88vh;display:flex;flex-direction:column;">
      <div class="modal-header">
        <h4><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:6px"><circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>Agents <span id="monitor-stats" class="memory-count" style="font-size:0.6em;opacity:0.6;font-weight:normal;margin-left:8px"></span></h4>
        <button class="modal-close" id="monitor-close">&#x2716;</button>
      </div>
      <div class="modal-body" style="flex:1;overflow-y:auto;padding:8px 12px;">
        <div id="monitor-toolbar" style="display:flex;gap:8px;align-items:center;margin-bottom:8px;">
          <select id="monitor-filter" class="memory-edit-cat-select" style="font-size:12px;">
            <option value="">All</option>
            <option value="running">Running</option>
            <option value="pending">Pending</option>
            <option value="paused">Paused</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select>
          <span style="flex:1"></span>
          <button id="monitor-spawn-btn" class="confirm-btn confirm-btn-primary" style="font-size:12px;padding:4px 10px;">+ Spawn</button>
          <button id="monitor-refresh-btn" class="theme-io-btn" style="font-size:12px;height:26px;">Refresh</button>
        </div>
        <div id="monitor-list"></div>
      </div>
    </div>
  `;
  document.body.appendChild(modal);

  Modals.register('monitor-modal', {
    railBtnId: 'rail-monitor',
    sidebarBtnId: 'tool-monitor-btn',
    closeFn: () => _doClose(),
    restoreFn: () => {},
  });

  makeWindowDraggable(modal, {
    content: modal.querySelector('.modal-content'),
    header: modal.querySelector('.modal-header'),
  });

  document.getElementById('monitor-close').addEventListener('click', closeMonitor);
  modal.addEventListener('click', (e) => { if (e.target === modal) closeMonitor(); });

  document.getElementById('monitor-refresh-btn').addEventListener('click', _fetchRuns);
  document.getElementById('monitor-spawn-btn').addEventListener('click', _openSpawnForm);
  document.getElementById('monitor-filter').addEventListener('change', _renderList);

  _fetchRuns();
  _refreshTimer = setInterval(_fetchRuns, REFRESH_INTERVAL);
}

export function closeMonitor() {
  if (!_open && !Modals.isMinimized('monitor-modal')) return;
  if (Modals.isRegistered('monitor-modal')) {
    Modals.close('monitor-modal');
  } else {
    _doClose();
  }
}

export function isMonitorOpen() {
  if (Modals.isMinimized('monitor-modal')) return false;
  return _open;
}

function _doClose() {
  _open = false;
  if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; }
  const modal = document.getElementById('monitor-modal');
  if (modal) {
    const content = modal.querySelector('.modal-content');
    if (content) {
      content.classList.add('modal-closing');
      content.addEventListener('animationend', () => modal.remove(), { once: true });
      setTimeout(() => { if (modal.parentElement) modal.remove(); }, 250);
    } else {
      modal.remove();
    }
  }
  const btn = document.getElementById('tool-monitor-btn');
  if (btn) btn.classList.remove('active');
}

// ---- Data ----

async function _fetchRuns() {
  try {
    const res = await fetch(`${window.location.origin}/api/subagents/runs`);
    if (!res.ok) {
      _runs = [];
      _renderList();
      _updateStats();
      return;
    }
    const data = await res.json();
    _runs = data.items || [];
  } catch (e) {
    // API not available — show empty
    _runs = [];
  }
  _renderList();
  _updateStats();
}

function _updateStats() {
  const el = document.getElementById('monitor-stats');
  if (!el) return;
  const running = _runs.filter(r => r.status === 'running').length;
  const total = _runs.length;
  el.textContent = total > 0 ? `${running} running / ${total} total` : '';
}

// ---- Render ----

function _renderList() {
  const container = document.getElementById('monitor-list');
  if (!container) return;

  const filterVal = document.getElementById('monitor-filter')?.value || '';
  const filtered = filterVal ? _runs.filter(r => r.status === filterVal) : _runs;

  if (filtered.length === 0) {
    container.innerHTML = `
      <div style="text-align:center;padding:40px 20px;color:var(--text-secondary);">
        <div style="font-size:32px;margin-bottom:12px;opacity:0.4;">&#x1F916;</div>
        <div style="font-size:14px;font-weight:500;">No subagent runs${filterVal ? ` with status "${filterVal}"` : ''}</div>
        <div style="font-size:12px;margin-top:4px;opacity:0.7;">Spawn a subagent to get started</div>
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.map(run => {
    const statusClass = _statusClass(run.status);
    const duration = run.started_at ? _formatDuration(run.started_at, run.completed_at) : '-';
    const typeIcon = _typeIcon(run.agent_type);

    return `
      <div class="admin-card" style="margin-bottom:6px;padding:10px 12px;" data-run-id="${_esc(run.id)}">
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="font-size:16px;">${typeIcon}</span>
          <div style="flex:1;min-width:0;">
            <div style="font-size:13px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${_esc(run.name || run.task_description)}</div>
            <div style="font-size:11px;color:var(--text-secondary);margin-top:1px;">
              <span style="font-family:var(--mono);opacity:0.7;">${_esc(run.id?.substring(0, 8))}</span>
              &nbsp;&bull;&nbsp;${_esc(run.agent_type || 'general')}
              &nbsp;&bull;&nbsp;${duration}
              ${run.iteration_count ? `&nbsp;&bull;&nbsp;${run.iteration_count} iters` : ''}
            </div>
          </div>
          <span class="memory-cat-badge" style="font-size:10px;padding:2px 6px;${statusClass}">${_esc(run.status)}</span>
          <div style="display:flex;gap:2px;">
            ${run.status === 'running' ? `<button class="memory-item-btn" onclick="window._monitorAction('pause','${_esc(run.id)}')" title="Pause" style="font-size:11px;">pause</button>` : ''}
            ${run.status === 'paused' ? `<button class="memory-item-btn save" onclick="window._monitorAction('resume','${_esc(run.id)}')" title="Resume" style="font-size:11px;">resume</button>` : ''}
            ${['running','paused','pending'].includes(run.status) ? `<button class="memory-item-btn delete" onclick="window._monitorAction('cancel','${_esc(run.id)}')" title="Cancel" style="font-size:11px;">cancel</button>` : ''}
          </div>
        </div>
        ${run.result_summary ? `<div style="font-size:11px;color:var(--text-secondary);margin-top:4px;padding:4px 6px;background:var(--bg-tertiary);border-radius:4px;max-height:60px;overflow:hidden;">${_esc(run.result_summary)}</div>` : ''}
        ${run.error_message ? `<div style="font-size:11px;color:var(--accent-danger,#f85149);margin-top:4px;padding:4px 6px;background:rgba(248,81,73,0.08);border-radius:4px;">${_esc(run.error_message)}</div>` : ''}
      </div>
    `;
  }).join('');
}

// ---- Actions ----

window._monitorAction = async function(action, runId) {
  try {
    const res = await fetch(`${window.location.origin}/api/subagents/runs/${runId}/${action}`, {
      method: 'POST'
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `${action} failed`);
    }
    _fetchRuns();
  } catch (e) {
    if (window.uiModule) window.uiModule.showError(`${action} failed: ${e.message}`);
  }
};

// ---- Spawn Form ----

function _openSpawnForm() {
  const container = document.getElementById('monitor-list');
  if (!container) return;

  const existing = document.getElementById('monitor-spawn-form');
  if (existing) { existing.remove(); return; }

  const form = document.createElement('div');
  form.id = 'monitor-spawn-form';
  form.className = 'admin-card';
  form.style.cssText = 'margin-bottom:10px;padding:12px;border:1px solid var(--accent, var(--border));';
  form.innerHTML = `
    <div style="font-size:13px;font-weight:600;margin-bottom:8px;">Spawn New Subagent</div>
    <div style="margin-bottom:6px;">
      <textarea id="spawn-task" placeholder="Task description..." rows="2" style="width:100%;background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:6px 8px;color:var(--text-primary);font-size:13px;resize:vertical;"></textarea>
    </div>
    <div style="display:flex;gap:6px;margin-bottom:8px;">
      <select id="spawn-type" class="memory-edit-cat-select" style="flex:1;font-size:12px;">
        <option value="general">General</option>
        <option value="research">Research</option>
        <option value="code">Code</option>
        <option value="analysis">Analysis</option>
        <option value="creative">Creative</option>
      </select>
      <input type="number" id="spawn-iterations" value="50" min="1" max="200" style="width:70px;background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:4px 6px;color:var(--text-primary);font-size:12px;" title="Max iterations">
      <input type="number" id="spawn-timeout" value="600" min="10" max="3600" style="width:80px;background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:4px 6px;color:var(--text-primary);font-size:12px;" title="Timeout (seconds)">
    </div>
    <div style="display:flex;justify-content:flex-end;gap:6px;">
      <button class="memory-item-btn" id="spawn-cancel-btn" style="font-size:12px;">cancel</button>
      <button class="confirm-btn confirm-btn-primary" id="spawn-submit-btn" style="font-size:12px;padding:4px 12px;">Spawn</button>
    </div>
  `;

  container.insertBefore(form, container.firstChild);

  document.getElementById('spawn-cancel-btn').addEventListener('click', () => form.remove());
  document.getElementById('spawn-submit-btn').addEventListener('click', async () => {
    const task = document.getElementById('spawn-task')?.value?.trim();
    if (!task) return;
    const type = document.getElementById('spawn-type')?.value || 'general';
    const iters = parseInt(document.getElementById('spawn-iterations')?.value) || 50;
    const timeout = parseInt(document.getElementById('spawn-timeout')?.value) || 600;

    try {
      const res = await fetch(`${window.location.origin}/api/subagents/spawn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          config: { name: `${type}-agent`, agent_type: type, max_iterations: iters, timeout_seconds: timeout },
          task_description: task,
          input_data: {}
        })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Spawn failed');
      }
      form.remove();
      if (window.uiModule) window.uiModule.showToast('Subagent spawned');
      _fetchRuns();
    } catch (e) {
      if (window.uiModule) window.uiModule.showError('Spawn failed: ' + e.message);
    }
  });

  document.getElementById('spawn-task')?.focus();
}

// ---- Helpers ----

function _statusClass(status) {
  const map = {
    running:    'background:rgba(63,185,80,0.15);color:#3fb950;',
    pending:    'background:rgba(217,151,34,0.15);color:#d29922;',
    spawning:   'background:rgba(88,166,255,0.15);color:#58a6ff;',
    paused:     'background:rgba(217,151,34,0.15);color:#d29922;',
    completed:  'background:rgba(88,166,255,0.15);color:#58a6ff;',
    failed:     'background:rgba(248,81,73,0.15);color:#f85149;',
    cancelled:  'background:rgba(139,148,158,0.15);color:#8b949e;',
    timeout:    'background:rgba(248,81,73,0.15);color:#f85149;',
    orphaned:   'background:rgba(163,113,247,0.15);color:#a371f7;',
    recovering: 'background:rgba(88,166,255,0.15);color:#58a6ff;',
  };
  return map[status] || '';
}

function _typeIcon(type) {
  const map = {
    general:   '\u{1F527}',
    research:  '\u{1F52C}',
    code:      '\u{1F4BB}',
    analysis:  '\u{1F4CA}',
    creative:  '\u{1F3A8}',
    planning:  '\u{1F4CB}',
    review:    '\u{1F50D}',
    test:      '\u{1F9EA}',
    debug:     '\u{1F41B}',
  };
  return map[type] || '\u{1F916}';
}

function _formatDuration(startIso, endIso) {
  const start = new Date(startIso);
  const end = endIso ? new Date(endIso) : new Date();
  const sec = Math.floor((end - start) / 1000);
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ${sec % 60}s`;
  return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`;
}

function _esc(str) {
  if (!str) return '';
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

// ---- Export ----

const monitorModule = { openMonitor, closeMonitor, isMonitorOpen };
export default monitorModule;
window.monitorModule = monitorModule;
