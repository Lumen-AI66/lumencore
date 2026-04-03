"""Lumencore Dashboard — Modern AI Control Center"""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("PORT", 8080))
API_BASE = os.environ.get("API_BASE_URL", "http://lumencore-api:8000")

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Lumencore — AI Control Center</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

  :root {
    --bg:        #0a0b0f;
    --bg2:       #0f1117;
    --bg3:       #161820;
    --cyan:      #00d4ff;
    --purple:    #7c3aed;
    --green:     #00e676;
    --red:       #ff4444;
    --yellow:    #ffd740;
    --text:      #e2e8f0;
    --muted:     #64748b;
    --glass:     rgba(255,255,255,0.04);
    --border:    rgba(0,212,255,0.12);
    --radius:    12px;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: 'Inter', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    display: flex;
    height: 100vh;
    overflow: hidden;
  }

  /* SIDEBAR */
  #sidebar {
    width: 220px;
    min-width: 220px;
    background: var(--bg2);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
  }

  .brand {
    padding: 24px 20px 20px;
    border-bottom: 1px solid var(--border);
  }
  .brand-name {
    font-size: 17px;
    font-weight: 700;
    letter-spacing: 2px;
    color: var(--cyan);
    text-shadow: 0 0 20px rgba(0,212,255,0.4);
    display: block;
    margin-top: 6px;
  }
  .brand-phase { font-size: 11px; color: var(--muted); letter-spacing: 1px; text-transform: uppercase; }

  nav { flex: 1; padding: 16px 0; }

  .nav-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 11px 20px;
    cursor: pointer;
    font-size: 14px;
    color: var(--muted);
    transition: all 0.15s ease;
    border-left: 3px solid transparent;
  }
  .nav-item:hover { background: var(--glass); color: var(--text); }
  .nav-item.active { background: rgba(0,212,255,0.08); color: var(--cyan); border-left-color: var(--cyan); }
  .nav-icon { font-size: 16px; width: 20px; text-align: center; }
  .nav-label { font-weight: 500; }

  .sidebar-footer {
    padding: 16px 20px;
    border-top: 1px solid var(--border);
    font-size: 11px;
    color: var(--muted);
  }
  .status-dot {
    display: inline-block;
    width: 7px; height: 7px;
    border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 8px var(--green);
    margin-right: 6px;
    animation: pulse 2s infinite;
  }
  @keyframes pulse { 0%,100%{opacity:1}50%{opacity:0.4} }

  /* MAIN */
  #main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

  #topbar {
    height: 56px;
    background: var(--bg2);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    padding: 0 28px;
    gap: 16px;
  }
  #topbar h1 { font-size: 16px; font-weight: 600; flex: 1; }
  .topbar-refresh {
    background: var(--glass);
    border: 1px solid var(--border);
    color: var(--cyan);
    padding: 6px 14px;
    border-radius: 8px;
    font-size: 12px;
    cursor: pointer;
  }
  .topbar-refresh:hover { background: rgba(0,212,255,0.15); }

  #content { flex: 1; overflow-y: auto; padding: 28px; }

  /* CARDS */
  .card {
    background: var(--glass);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    backdrop-filter: blur(12px);
  }
  .card-title {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: var(--muted);
    margin-bottom: 14px;
    font-weight: 600;
  }

  .grid { display: grid; gap: 16px; }
  .grid-4 { grid-template-columns: repeat(4, 1fr); }
  .grid-3 { grid-template-columns: repeat(3, 1fr); }
  .grid-2 { grid-template-columns: repeat(2, 1fr); }
  .mt { margin-top: 20px; }

  /* STAT CARDS */
  .stat-card {
    background: var(--glass);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px 20px;
    position: relative;
    overflow: hidden;
  }
  .stat-card::before {
    content:'';position:absolute;top:0;left:0;right:0;height:2px;
    background: linear-gradient(90deg, var(--cyan), var(--purple));
  }
  .stat-label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; }
  .stat-value { font-size: 28px; font-weight: 700; margin: 6px 0 2px; }
  .stat-sub { font-size: 12px; color: var(--muted); }

  /* BADGES */
  .badge {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 10px; border-radius: 20px;
    font-size: 11px; font-weight: 600; letter-spacing: 0.5px;
  }
  .badge-green  { background:rgba(0,230,118,0.12);  color:var(--green);  border:1px solid rgba(0,230,118,0.3); }
  .badge-red    { background:rgba(255,68,68,0.12);   color:var(--red);    border:1px solid rgba(255,68,68,0.3); }
  .badge-yellow { background:rgba(255,215,64,0.12);  color:var(--yellow); border:1px solid rgba(255,215,64,0.3); }
  .badge-cyan   { background:rgba(0,212,255,0.12);   color:var(--cyan);   border:1px solid rgba(0,212,255,0.3); }
  .badge-purple { background:rgba(124,58,237,0.15);  color:#a78bfa;       border:1px solid rgba(124,58,237,0.3); }

  /* TABLES */
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align:left; padding:10px 14px; font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:1px; border-bottom:1px solid var(--border); font-weight:600; }
  td { padding:12px 14px; border-bottom:1px solid rgba(255,255,255,0.04); vertical-align:middle; }
  tr:hover td { background: var(--glass); }
  .mono { font-family:'Courier New',monospace; font-size:12px; }

  /* BUTTONS */
  .btn {
    display:inline-flex; align-items:center; gap:6px;
    padding:8px 16px; border-radius:8px;
    font-size:13px; font-weight:500; cursor:pointer;
    transition:all 0.15s; border:none; font-family:inherit;
  }
  .btn-primary { background:linear-gradient(135deg,var(--cyan),var(--purple)); color:#000; }
  .btn-primary:hover { opacity:0.85; transform:translateY(-1px); }
  .btn-ghost { background:var(--glass); border:1px solid var(--border); color:var(--text); }
  .btn-ghost:hover { background:rgba(0,212,255,0.1); border-color:var(--cyan); }
  .btn-danger { background:rgba(255,68,68,0.15); border:1px solid rgba(255,68,68,0.3); color:var(--red); }
  .btn-sm { padding:5px 10px; font-size:12px; }

  /* INPUTS */
  input, select, textarea {
    background:var(--bg3); border:1px solid var(--border); color:var(--text);
    padding:10px 14px; border-radius:8px; font-size:13px; font-family:inherit;
    transition:border-color 0.15s; width:100%;
  }
  input:focus, select:focus, textarea:focus { outline:none; border-color:var(--cyan); box-shadow:0 0 0 2px rgba(0,212,255,0.1); }
  select option { background:var(--bg3); }
  label { font-size:12px; color:var(--muted); display:block; margin-bottom:5px; }
  .form-group { margin-bottom:14px; }

  /* MODAL */
  .modal-overlay {
    display:none; position:fixed; inset:0;
    background:rgba(0,0,0,0.7); backdrop-filter:blur(4px);
    z-index:100; align-items:center; justify-content:center;
  }
  .modal-overlay.open { display:flex; }
  .modal {
    background:var(--bg2); border:1px solid var(--border); border-radius:16px;
    padding:28px; width:480px; max-width:94vw;
    box-shadow:0 24px 48px rgba(0,0,0,0.5);
  }
  .modal h2 { font-size:17px; margin-bottom:20px; color:var(--cyan); }
  .modal-actions { display:flex; gap:10px; margin-top:20px; justify-content:flex-end; }

  /* AGENT CARDS */
  .agent-card {
    background:var(--glass); border:1px solid var(--border);
    border-radius:var(--radius); padding:20px;
    display:flex; flex-direction:column; gap:12px;
    position:relative; overflow:hidden;
  }
  .agent-card::after {
    content:''; position:absolute; bottom:0; left:0; right:0; height:1px;
    background:linear-gradient(90deg,transparent,var(--purple),transparent);
  }
  .agent-name { font-size:15px; font-weight:600; }
  .agent-type { font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:1px; }

  /* WORKSPACE CARDS */
  .ws-card {
    background:var(--glass); border:1px solid var(--border);
    border-radius:var(--radius); padding:20px; cursor:pointer;
    transition:border-color 0.15s, transform 0.15s;
  }
  .ws-card:hover { border-color:var(--cyan); transform:translateY(-2px); }
  .ws-card.selected { border-color:var(--cyan); background:rgba(0,212,255,0.06); }
  .ws-title { font-size:15px; font-weight:600; margin-bottom:4px; }
  .ws-desc { font-size:12px; color:var(--muted); margin-bottom:12px; }

  /* CREDENTIAL CARDS */
  .cred-card {
    background:var(--glass); border:1px solid var(--border);
    border-radius:var(--radius); padding:18px 20px;
    display:flex; align-items:center; gap:14px;
  }
  .cred-icon {
    width:40px; height:40px; border-radius:10px;
    display:flex; align-items:center; justify-content:center;
    font-size:18px; background:var(--bg3); border:1px solid var(--border); flex-shrink:0;
  }
  .cred-info { flex:1; }
  .cred-name { font-size:14px; font-weight:600; }
  .cred-service { font-size:12px; color:var(--muted); }
  .cred-value { font-family:monospace; font-size:13px; color:var(--muted); margin-top:2px; }

  /* HEALTH */
  .health-item {
    display:flex; align-items:center; justify-content:space-between;
    padding:12px 0; border-bottom:1px solid rgba(255,255,255,0.04);
  }
  .health-item:last-child { border-bottom:none; }
  .health-name { font-size:13px; font-weight:500; }

  /* ACTIVITY */
  .activity-item {
    display:flex; gap:12px; padding:10px 0;
    border-bottom:1px solid rgba(255,255,255,0.04); font-size:13px;
  }
  .activity-item:last-child { border-bottom:none; }
  .activity-time { font-size:11px; color:var(--muted); white-space:nowrap; }
  .activity-text { flex:1; }

  .loading { color:var(--muted); font-size:13px; padding:20px; text-align:center; }
  .glow-text { color:var(--cyan); text-shadow:0 0 20px rgba(0,212,255,0.5); }

  ::-webkit-scrollbar { width:5px; height:5px; }
  ::-webkit-scrollbar-track { background:transparent; }
  ::-webkit-scrollbar-thumb { background:var(--border); border-radius:4px; }

  .view { display:none; }
  .view.active { display:block; }

  .section-header {
    display:flex; align-items:center; justify-content:space-between; margin-bottom:20px;
  }
  .section-title { font-size:20px; font-weight:700; }
  .section-sub { font-size:13px; color:var(--muted); margin-top:2px; }

  .cmd-area {
    background:var(--bg3); border:1px solid var(--border);
    border-radius:var(--radius); padding:16px 20px;
    display:flex; gap:12px; align-items:center;
  }
  .cmd-area input { background:transparent; border:none; flex:1; font-size:14px; padding:0; }
  .cmd-area input:focus { box-shadow:none; }

  #toast {
    position:fixed; bottom:24px; right:24px;
    background:var(--bg2); border:1px solid var(--cyan); color:var(--text);
    padding:12px 20px; border-radius:10px; font-size:13px; z-index:999;
    box-shadow:0 0 24px rgba(0,212,255,0.2);
    opacity:0; transition:opacity 0.3s; pointer-events:none;
  }
  #toast.show { opacity:1; }
</style>
</head>
<body>

<div id="sidebar">
  <div class="brand">
    <span style="font-size:22px">⚡</span>
    <span class="brand-name">LUMENCORE</span>
    <span class="brand-phase">AI Control Center</span>
  </div>
  <nav>
    <div class="nav-item active" onclick="showView('dashboard',this)">
      <span class="nav-icon">🏠</span><span class="nav-label">Dashboard</span>
    </div>
    <div class="nav-item" onclick="showView('agents',this)">
      <span class="nav-icon">🤖</span><span class="nav-label">Agents</span>
    </div>
    <div class="nav-item" onclick="showView('commands',this)">
      <span class="nav-icon">📋</span><span class="nav-label">Commands</span>
    </div>
    <div class="nav-item" onclick="showView('workspaces',this)">
      <span class="nav-icon">🔧</span><span class="nav-label">Workspaces</span>
    </div>
    <div class="nav-item" onclick="showView('credentials',this)">
      <span class="nav-icon">🔑</span><span class="nav-label">Credentials</span>
    </div>
  </nav>
  <div class="sidebar-footer">
    <span class="status-dot"></span>
    <span id="sys-status-text">ONLINE</span>
  </div>
</div>

<div id="main">
  <div id="topbar">
    <h1 id="topbar-title">Dashboard</h1>
    <span style="font-size:12px;color:var(--muted)" id="last-refresh">—</span>
    <button class="topbar-refresh" onclick="refreshCurrent()">↻ Refresh</button>
  </div>

  <div id="content">

    <!-- DASHBOARD -->
    <div class="view active" id="view-dashboard">
      <div class="grid grid-4" id="stat-cards">
        <div class="stat-card"><div class="stat-label">System</div><div class="stat-value" id="sys-health-val">—</div><div class="stat-sub">Overall status</div></div>
        <div class="stat-card"><div class="stat-label">Queue</div><div class="stat-value" id="queue-size-val">—</div><div class="stat-sub">Commands pending</div></div>
        <div class="stat-card"><div class="stat-label">Agents</div><div class="stat-value" id="agents-active-val">—</div><div class="stat-sub">Registered</div></div>
        <div class="stat-card"><div class="stat-label">Commands</div><div class="stat-value" id="cmd-total-val">—</div><div class="stat-sub">All time</div></div>
      </div>

      <div class="grid grid-2 mt">
        <div class="card">
          <div class="card-title">Component Health</div>
          <div id="health-list"><div class="loading">Loading...</div></div>
        </div>
        <div class="card">
          <div class="card-title">Recent Activity</div>
          <div id="activity-feed"><div class="loading">Loading...</div></div>
        </div>
      </div>

      <div class="card mt">
        <div class="card-title">Quick Command</div>
        <div class="cmd-area">
          <input type="text" id="quick-cmd" placeholder="e.g. 'research AI trends 2026' — press Enter or click Run" onkeydown="if(event.key==='Enter')sendQuickCmd()"/>
          <button class="btn btn-primary btn-sm" onclick="sendQuickCmd()">▶ Run</button>
        </div>
        <div id="quick-cmd-result" style="margin-top:12px;font-size:13px;color:var(--muted)"></div>
      </div>
    </div>

    <!-- AGENTS -->
    <div class="view" id="view-agents">
      <div class="section-header">
        <div><div class="section-title">Agents</div><div class="section-sub">Registered AI agents and their status</div></div>
      </div>
      <div class="grid grid-3" id="agent-cards"><div class="loading">Loading...</div></div>
    </div>

    <!-- COMMANDS -->
    <div class="view" id="view-commands">
      <div class="section-header">
        <div><div class="section-title">Commands</div><div class="section-sub">Operator queue and execution history</div></div>
      </div>
      <div class="grid grid-2">
        <div class="card">
          <div class="card-title">Awaiting Approval</div>
          <div id="approval-list"><div class="loading">Loading...</div></div>
        </div>
        <div class="card">
          <div class="card-title">Running Now</div>
          <div id="running-list"><div class="loading">Loading...</div></div>
        </div>
      </div>
      <div class="card mt">
        <div class="card-title">Command History</div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Command</th><th>Intent</th><th>Status</th><th>Time</th><th>Actions</th></tr></thead>
            <tbody id="cmd-history-body"><tr><td colspan="5" class="loading">Loading…</td></tr></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- WORKSPACES -->
    <div class="view" id="view-workspaces">
      <div class="section-header">
        <div><div class="section-title">Workspaces</div><div class="section-sub">Manage workflows and automated tasks</div></div>
        <button class="btn btn-primary" onclick="openModal('ws-modal')">+ New Workspace</button>
      </div>
      <div class="grid grid-3" id="ws-grid"><div class="loading">Loading...</div></div>
      <div id="ws-detail" style="display:none" class="mt">
        <div class="card">
          <div class="card-title" id="ws-detail-title">Workflows</div>
          <div id="ws-workflow-list"><div class="loading">Loading...</div></div>
          <div style="margin-top:14px">
            <button class="btn btn-ghost btn-sm" onclick="openModal('wf-modal')">+ Add Workflow</button>
          </div>
        </div>
      </div>
    </div>

    <!-- CREDENTIALS -->
    <div class="view" id="view-credentials">
      <div class="section-header">
        <div><div class="section-title">Credentials</div><div class="section-sub">Manage API keys, tokens, and webhooks</div></div>
        <button class="btn btn-primary" onclick="openModal('cred-modal')">+ Add Credential</button>
      </div>
      <div id="cred-list" style="display:grid;gap:12px"><div class="loading">Loading...</div></div>
    </div>

  </div>
</div>

<!-- MODALS -->
<div class="modal-overlay" id="ws-modal">
  <div class="modal">
    <h2>🔧 New Workspace</h2>
    <div class="form-group"><label>Name</label><input id="ws-name" placeholder="e.g. Research Pipeline"/></div>
    <div class="form-group"><label>Description</label><input id="ws-desc" placeholder="What does this workspace do?"/></div>
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeModal('ws-modal')">Cancel</button>
      <button class="btn btn-primary" onclick="createWorkspace()">Create</button>
    </div>
  </div>
</div>

<div class="modal-overlay" id="wf-modal">
  <div class="modal">
    <h2>⚙️ New Workflow</h2>
    <div class="form-group"><label>Name</label><input id="wf-name" placeholder="e.g. Daily Research"/></div>
    <div class="form-group"><label>Trigger</label>
      <select id="wf-trigger">
        <option value="manual">Manual</option>
        <option value="schedule">Schedule</option>
        <option value="webhook">Webhook</option>
        <option value="event">Event</option>
      </select>
    </div>
    <div class="form-group"><label>Steps (JSON array)</label>
      <textarea id="wf-steps" rows="4" placeholder='[{"agent":"research-agent","task":"search topic X"}]'></textarea>
    </div>
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeModal('wf-modal')">Cancel</button>
      <button class="btn btn-primary" onclick="createWorkflow()">Create</button>
    </div>
  </div>
</div>

<div class="modal-overlay" id="cred-modal">
  <div class="modal">
    <h2>🔑 Add Credential</h2>
    <div class="form-group"><label>Name</label><input id="cred-name" placeholder="e.g. OpenAI Production"/></div>
    <div class="form-group"><label>Service</label>
      <select id="cred-service">
        <option value="openai">OpenAI</option>
        <option value="telegram">Telegram</option>
        <option value="github">GitHub</option>
        <option value="slack">Slack</option>
        <option value="webhook">Webhook</option>
        <option value="custom">Custom</option>
      </select>
    </div>
    <div class="form-group"><label>Type</label>
      <select id="cred-type">
        <option value="api_key">API Key</option>
        <option value="oauth_token">OAuth Token</option>
        <option value="webhook_url">Webhook URL</option>
        <option value="basic_auth">Basic Auth</option>
      </select>
    </div>
    <div class="form-group"><label>Value</label><input type="password" id="cred-value" placeholder="Paste your key or URL"/></div>
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeModal('cred-modal')">Cancel</button>
      <button class="btn btn-primary" onclick="saveCred()">Save</button>
    </div>
  </div>
</div>

<div class="modal-overlay" id="cmd-detail-modal">
  <div class="modal" style="width:560px">
    <h2>Command Detail</h2>
    <div id="cmd-detail-body" style="font-size:13px;color:var(--muted)"></div>
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeModal('cmd-detail-modal')">Close</button>
    </div>
  </div>
</div>

<div id="toast"></div>

<script>
const API = '/proxy';
let currentView = 'dashboard';
let selectedWorkspaceId = null;

function showView(name, el) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('view-' + name).classList.add('active');
  if (el) el.classList.add('active');
  currentView = name;
  document.getElementById('topbar-title').textContent = el ? el.querySelector('.nav-label').textContent : name;
  loadView(name);
}

function refreshCurrent() { loadView(currentView); }

function loadView(name) {
  document.getElementById('last-refresh').textContent = new Date().toLocaleTimeString();
  if (name === 'dashboard') loadDashboard();
  else if (name === 'agents') loadAgents();
  else if (name === 'commands') loadCommands();
  else if (name === 'workspaces') loadWorkspaces();
  else if (name === 'credentials') loadCredentials();
}

async function api(path, opts = {}) {
  try {
    const r = await fetch(API + path, {
      headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) }, ...opts
    });
    if (r.status === 204) return { ok: true };
    if (!r.ok) throw new Error(r.status);
    return await r.json();
  } catch (e) { return null; }
}

function toast(msg, ms = 3000) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), ms);
}

function openModal(id) { document.getElementById(id).classList.add('open'); }
function closeModal(id) { document.getElementById(id).classList.remove('open'); }
document.querySelectorAll('.modal-overlay').forEach(m => {
  m.addEventListener('click', e => { if (e.target === m) m.classList.remove('open'); });
});

function statusBadge(s) {
  if (!s) return '<span class="badge badge-cyan">—</span>';
  s = String(s).toLowerCase();
  const map = {
    ok:'green', healthy:'green', active:'green', completed:'green', success:'green',
    running:'cyan', pending:'yellow', queued:'yellow', awaiting_approval:'yellow',
    failed:'red', error:'red', cancelled:'red', denied:'red', idle:'purple'
  };
  return `<span class="badge badge-${map[s]||'cyan'}">${s}</span>`;
}

function serviceIcon(svc) {
  return {openai:'🤖',telegram:'✈️',github:'🐙',slack:'💬',webhook:'🔗',custom:'⚙️'}[svc] || '🔑';
}

function shortId(id) { return id ? id.slice(0,8)+'…' : '—'; }
function fmtTime(ts) {
  if (!ts) return '—';
  try { return new Date(ts).toLocaleString(); } catch { return ts; }
}

// DASHBOARD
async function loadDashboard() {
  const summary = await api('/api/operator/summary');
  if (summary) {
    const h = summary.health || {};
    const s = h.status || 'unknown';
    document.getElementById('sys-health-val').innerHTML = s === 'ok'
      ? '<span class="glow-text">OK</span>' : `<span style="color:var(--red)">${s.toUpperCase()}</span>`;
    document.getElementById('queue-size-val').textContent = summary.queue_size ?? '—';
    document.getElementById('sys-status-text').textContent = s === 'ok' ? 'ONLINE' : 'DEGRADED';

    const comps = h.components || {};
    const healthEl = document.getElementById('health-list');
    if (Object.keys(comps).length) {
      healthEl.innerHTML = Object.entries(comps).map(([k, v]) => {
        const ok = v === 'ok' || v === true || (typeof v === 'object' && v.ok);
        return `<div class="health-item"><div><div class="health-name">${k}</div></div>${ok ? '<span class="badge badge-green">OK</span>' : '<span class="badge badge-red">ERR</span>'}</div>`;
      }).join('');
    } else {
      healthEl.innerHTML = '<div class="health-item"><div class="health-name">API</div><span class="badge badge-green">OK</span></div>';
    }

    const agentList = summary.agents || [];
    document.getElementById('agents-active-val').textContent = agentList.length || '—';
  }

  const cmds = await api('/api/operator/commands?limit=6');
  const feedEl = document.getElementById('activity-feed');
  if (cmds && cmds.length) {
    document.getElementById('cmd-total-val').textContent = cmds.length + (cmds.length >= 6 ? '+' : '');
    feedEl.innerHTML = cmds.map(c => `
      <div class="activity-item">
        <span class="activity-time">${fmtTime(c.created_at).split(',').pop() || ''}</span>
        <span class="activity-text">${(c.command_text||'—').slice(0,50)} ${statusBadge(c.status)}</span>
      </div>`).join('');
  } else {
    feedEl.innerHTML = '<div class="loading">No recent activity</div>';
  }
}

// AGENTS
async function loadAgents() {
  const data = await api('/api/agents/registry');
  const el = document.getElementById('agent-cards');
  if (!data || !data.length) { el.innerHTML = '<div class="loading">No agents registered</div>'; return; }
  el.innerHTML = data.map(a => {
    const meta = a.metadata_json || {};
    const caps = (meta.capabilities || []).slice(0,3).join(' · ');
    return `<div class="agent-card">
      <div><div class="agent-name">${a.name || a.agent_key || '—'}</div><div class="agent-type">${a.agent_type||'agent'}</div></div>
      <div>${statusBadge(a.status||'active')}</div>
      <div style="font-size:12px;color:var(--muted)">Runs <strong style="color:var(--text)">${a.run_count??'—'}</strong>${meta.phase ? ` · Phase <strong style="color:var(--text)">${meta.phase}</strong>` : ''}</div>
      ${caps ? `<div style="font-size:11px;color:var(--muted)">${caps}</div>` : ''}
    </div>`;
  }).join('');
}

// COMMANDS
async function loadCommands() {
  const queue = await api('/api/operator/queue');
  const awaiting = queue?.awaiting_approval || [];
  const running = queue?.running || [];

  document.getElementById('approval-list').innerHTML = awaiting.length
    ? awaiting.map(c => `<div class="activity-item">
        <div style="flex:1"><div style="font-size:13px;font-weight:500">${c.command_text||'—'}</div><div style="font-size:11px;color:var(--muted)">${shortId(c.id)}</div></div>
        <div style="display:flex;gap:6px">
          <button class="btn btn-ghost btn-sm" onclick="approveCmd('${c.id}')">✓ Approve</button>
          <button class="btn btn-danger btn-sm" onclick="cancelCmd('${c.id}')">✗</button>
        </div>
      </div>`).join('')
    : '<div class="loading">No commands awaiting approval</div>';

  document.getElementById('running-list').innerHTML = running.length
    ? running.map(c => `<div class="activity-item">
        <div style="flex:1"><div style="font-size:13px;font-weight:500">${c.command_text||'—'}</div><div style="font-size:11px;color:var(--muted)">${shortId(c.id)}</div></div>
        ${statusBadge('running')}
      </div>`).join('')
    : '<div class="loading">Nothing running</div>';

  const history = await api('/api/operator/commands?limit=25');
  const tbody = document.getElementById('cmd-history-body');
  if (!history || !history.length) { tbody.innerHTML = '<tr><td colspan="5" class="loading">No commands yet</td></tr>'; return; }
  tbody.innerHTML = history.map(c => `
    <tr>
      <td style="max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${c.command_text||'—'}</td>
      <td><span class="badge badge-purple">${c.intent||'—'}</span></td>
      <td>${statusBadge(c.status)}</td>
      <td class="mono">${fmtTime(c.created_at)}</td>
      <td>
        <button class="btn btn-ghost btn-sm" onclick="showCmdDetail('${c.id}')">Detail</button>
        ${c.status==='awaiting_approval'?`<button class="btn btn-ghost btn-sm" onclick="approveCmd('${c.id}')">Approve</button>`:''}
        ${c.status==='failed'?`<button class="btn btn-ghost btn-sm" onclick="retryCmd('${c.id}')">Retry</button>`:''}
      </td>
    </tr>`).join('');
}

async function approveCmd(id) { await api(`/api/command/${id}/approve`,{method:'POST'}); toast('Command approved'); loadCommands(); }
async function cancelCmd(id)  { await api(`/api/command/${id}/cancel`, {method:'POST'}); toast('Command cancelled'); loadCommands(); }
async function retryCmd(id)   { await api(`/api/command/${id}/retry`,  {method:'POST'}); toast('Command retried');  loadCommands(); }

async function showCmdDetail(id) {
  const d = await api(`/api/operator/command/${id}`);
  if (!d) return;
  document.getElementById('cmd-detail-body').innerHTML = `
    <div class="form-group"><strong>ID:</strong> <span class="mono">${d.id}</span></div>
    <div class="form-group"><strong>Command:</strong> ${d.command_text}</div>
    <div class="form-group"><strong>Intent:</strong> ${d.intent}</div>
    <div class="form-group"><strong>Status:</strong> ${statusBadge(d.status)}</div>
    <div class="form-group"><strong>Decision:</strong> ${d.execution_decision||'—'}</div>
    <div class="form-group"><strong>Created:</strong> ${fmtTime(d.created_at)}</div>
    ${d.result_summary?`<div class="form-group"><strong>Result:</strong><pre style="background:var(--bg3);padding:10px;border-radius:6px;font-size:11px;overflow:auto;max-height:120px">${JSON.stringify(d.result_summary,null,2)}</pre></div>`:''}
  `;
  openModal('cmd-detail-modal');
}

// QUICK COMMAND
async function sendQuickCmd() {
  const txt = document.getElementById('quick-cmd').value.trim();
  if (!txt) return;
  const el = document.getElementById('quick-cmd-result');
  el.textContent = 'Sending…';
  const r = await api('/api/input/command', { method:'POST', body:JSON.stringify({input_text:txt}) });
  document.getElementById('quick-cmd').value = '';
  el.innerHTML = r
    ? `✓ Sent — ID: <span class="mono">${r.command_id||r.id||'?'}</span> ${statusBadge(r.status)}`
    : '✗ Failed to send command';
}

// WORKSPACES
async function loadWorkspaces() {
  const data = await api('/api/workspaces');
  const el = document.getElementById('ws-grid');
  if (!data || !data.length) {
    el.innerHTML = `<div class="card" style="grid-column:1/-1;text-align:center;padding:40px">
      <div style="font-size:32px;margin-bottom:12px">🔧</div>
      <div style="font-size:15px;font-weight:600;margin-bottom:6px">No workspaces yet</div>
      <div style="font-size:13px;color:var(--muted);margin-bottom:20px">Create a workspace to organize your automated workflows</div>
      <button class="btn btn-primary" onclick="openModal('ws-modal')">+ Create First Workspace</button>
    </div>`;
    return;
  }
  el.innerHTML = data.map(w => `
    <div class="ws-card ${selectedWorkspaceId===w.id?'selected':''}" onclick="selectWorkspace('${w.id}','${w.name}')">
      <div class="ws-title">${w.name}</div>
      <div class="ws-desc">${w.description||'No description'}</div>
      <div style="display:flex;gap:8px;align-items:center">${statusBadge(w.status)}</div>
    </div>`).join('');
}

async function selectWorkspace(id, name) {
  selectedWorkspaceId = id;
  document.getElementById('ws-detail').style.display = 'block';
  document.getElementById('ws-detail-title').textContent = `Workflows — ${name}`;
  await loadWorkflows(id);
  loadWorkspaces();
}

async function loadWorkflows(wsId) {
  const data = await api(`/api/workspaces/${wsId}/workflows`);
  const el = document.getElementById('ws-workflow-list');
  if (!data || !data.length) { el.innerHTML = '<div class="loading">No workflows yet — add one below</div>'; return; }
  el.innerHTML = data.map(wf => `
    <div style="background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:14px 16px;margin-bottom:10px;display:flex;align-items:center;gap:12px">
      <div style="flex:1">
        <div style="font-size:14px;font-weight:600">${wf.name}</div>
        <div style="font-size:11px;color:var(--muted);margin-top:3px">Trigger: <span style="color:var(--cyan)">${wf.trigger_type}</span>${wf.last_run_at?' · Last: '+fmtTime(wf.last_run_at):' · Never run'}</div>
      </div>
      ${statusBadge(wf.status)}
      <button class="btn btn-ghost btn-sm" onclick="runWorkflow('${wsId}','${wf.id}','${wf.name}')">▶ Run</button>
    </div>`).join('');
}

async function runWorkflow(wsId, wfId, name) {
  const r = await api(`/api/workspaces/${wsId}/workflows/${wfId}/run`, {method:'POST'});
  toast(r&&r.ok ? `✓ Workflow "${name}" triggered` : '✗ Failed');
  loadWorkflows(wsId);
}

async function createWorkspace() {
  const name = document.getElementById('ws-name').value.trim();
  const desc = document.getElementById('ws-desc').value.trim();
  if (!name) { toast('Name is required'); return; }
  const r = await api('/api/workspaces', {method:'POST', body:JSON.stringify({name,description:desc})});
  if (r && r.id) {
    toast(`✓ Workspace "${name}" created`); closeModal('ws-modal');
    document.getElementById('ws-name').value = ''; document.getElementById('ws-desc').value = '';
    loadWorkspaces();
  } else toast('✗ Failed to create workspace');
}

async function createWorkflow() {
  if (!selectedWorkspaceId) { toast('Select a workspace first'); return; }
  const name = document.getElementById('wf-name').value.trim();
  const trigger = document.getElementById('wf-trigger').value;
  let steps = [];
  try { steps = JSON.parse(document.getElementById('wf-steps').value || '[]'); } catch {}
  if (!name) { toast('Name is required'); return; }
  const r = await api(`/api/workspaces/${selectedWorkspaceId}/workflows`, {
    method:'POST', body:JSON.stringify({name,trigger_type:trigger,steps})
  });
  if (r && r.id) {
    toast(`✓ Workflow "${name}" created`); closeModal('wf-modal');
    document.getElementById('wf-name').value = ''; document.getElementById('wf-steps').value = '';
    loadWorkflows(selectedWorkspaceId);
  } else toast('✗ Failed to create workflow');
}

// CREDENTIALS
async function loadCredentials() {
  const data = await api('/api/credentials');
  const el = document.getElementById('cred-list');
  if (!data || !data.length) {
    el.innerHTML = `<div class="card" style="text-align:center;padding:40px">
      <div style="font-size:32px;margin-bottom:12px">🔑</div>
      <div style="font-size:15px;font-weight:600;margin-bottom:6px">No credentials stored</div>
      <div style="font-size:13px;color:var(--muted);margin-bottom:20px">Add API keys, OAuth tokens, and webhooks for your agents</div>
      <button class="btn btn-primary" onclick="openModal('cred-modal')">+ Add First Credential</button>
    </div>`;
    return;
  }
  el.innerHTML = data.map(c => `
    <div class="cred-card">
      <div class="cred-icon">${serviceIcon(c.service)}</div>
      <div class="cred-info">
        <div class="cred-name">${c.name}</div>
        <div class="cred-service">${c.service} · ${c.credential_type}</div>
        <div class="cred-value">${c.value_masked||'••••••••'}</div>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <span class="badge badge-green">Stored</span>
        <button class="btn btn-danger btn-sm" onclick="deleteCred('${c.id}','${c.name}')">🗑</button>
      </div>
    </div>`).join('');
}

async function saveCred() {
  const name = document.getElementById('cred-name').value.trim();
  const service = document.getElementById('cred-service').value;
  const ctype = document.getElementById('cred-type').value;
  const value = document.getElementById('cred-value').value.trim();
  if (!name || !value) { toast('Name and value required'); return; }
  const r = await api('/api/credentials', {method:'POST', body:JSON.stringify({name,service,credential_type:ctype,value})});
  if (r && r.id) {
    toast(`✓ Credential "${name}" saved`); closeModal('cred-modal');
    document.getElementById('cred-name').value = ''; document.getElementById('cred-value').value = '';
    loadCredentials();
  } else toast('✗ Failed to save credential');
}

async function deleteCred(id, name) {
  if (!confirm(`Delete credential "${name}"?`)) return;
  const r = await fetch(API + `/api/credentials/${id}`, {method:'DELETE'});
  if (r.ok || r.status === 204) { toast('✓ Deleted'); loadCredentials(); }
  else toast('✗ Failed to delete');
}

// AUTO REFRESH
loadDashboard();
setInterval(() => { if (currentView === 'dashboard') loadDashboard(); }, 10000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress access log noise

    def do_GET(self):
        if self.path.startswith("/proxy/"):
            self._proxy(self.path[7:], "GET", None)
        else:
            self._serve_html()

    def do_POST(self):
        if self.path.startswith("/proxy/"):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else None
            self._proxy(self.path[7:], "POST", body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_PUT(self):
        if self.path.startswith("/proxy/"):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else None
            self._proxy(self.path[7:], "PUT", body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_DELETE(self):
        if self.path.startswith("/proxy/"):
            self._proxy(self.path[7:], "DELETE", None)
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_html(self):
        data = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _proxy(self, path: str, method: str, body):
        import http.client
        import urllib.parse

        parsed = urllib.parse.urlparse(API_BASE)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        https = parsed.scheme == "https"

        full_path = "/" + path
        if "?" in self.path:
            full_path += "?" + self.path.split("?", 1)[1]

        try:
            conn = (
                http.client.HTTPSConnection(host, port)
                if https
                else http.client.HTTPConnection(host, port)
            )
            headers = {"Content-Type": "application/json"}
            conn.request(method, full_path, body=body, headers=headers)
            resp = conn.getresponse()
            resp_body = resp.read()
            self.send_response(resp.status)
            ct = resp.getheader("Content-Type", "application/json")
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(resp_body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp_body)
        except Exception as exc:
            err = json.dumps({"error": str(exc)}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Lumencore Dashboard running on http://0.0.0.0:{PORT}")
    server.serve_forever()
