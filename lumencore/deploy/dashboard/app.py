"""Lumencore Dashboard — AI Control Center"""
import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

from auth import (
    PIN_LOGIN_HTML, PIN_SETUP_HTML,
    get_session_from_cookie, is_locked_out,
    is_pin_configured, is_valid_session,
    logout, set_pin, verify_pin,
)

PORT = int(os.environ.get("PORT", 8080))
API_BASE = os.environ.get("API_BASE_URL", "http://lumencore-api:8000")

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Lumencore — Control Center</title>
<style>
/* === BASE === */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

:root {
  --bg:        #08090d;
  --bg2:       #0d0f17;
  --bg3:       #131620;
  --bg4:       #1a1d2a;
  --cyan:      #00d4ff;
  --purple:    #7c3aed;
  --green:     #00e676;
  --red:       #ff4444;
  --yellow:    #ffd740;
  --orange:    #ff9800;
  --text:      #e2e8f0;
  --muted:     #56627a;
  --muted2:    #8897b0;
  --glass:     rgba(255,255,255,0.035);
  --glass2:    rgba(255,255,255,0.06);
  --border:    rgba(0,212,255,0.1);
  --border2:   rgba(255,255,255,0.07);
  --radius:    10px;
  --sidebar-w: 220px;
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

/* === SIDEBAR === */
#sidebar {
  width: var(--sidebar-w);
  min-width: var(--sidebar-w);
  background: var(--bg2);
  border-right: 1px solid var(--border2);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.brand {
  padding: 22px 18px 18px;
  border-bottom: 1px solid var(--border2);
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.brand-logo {
  display: flex;
  align-items: center;
  gap: 9px;
}
.brand-icon {
  width: 28px; height: 28px;
  background: linear-gradient(135deg, var(--cyan), var(--purple));
  border-radius: 7px;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; flex-shrink: 0;
}
.brand-name {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 2.5px;
  color: var(--cyan);
}
.brand-phase {
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 1.5px;
  text-transform: uppercase;
  margin-top: 4px;
}

nav { flex: 1; padding: 10px 0 6px; }

.nav-section-label {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 1.8px;
  color: var(--muted);
  text-transform: uppercase;
  padding: 14px 18px 5px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 18px;
  cursor: pointer;
  font-size: 13px;
  color: var(--muted2);
  transition: all 0.12s ease;
  border-left: 2px solid transparent;
  position: relative;
}
.nav-item:hover { background: var(--glass2); color: var(--text); }
.nav-item.active {
  background: rgba(0,212,255,0.07);
  color: var(--cyan);
  border-left-color: var(--cyan);
}
.nav-icon { font-size: 14px; width: 18px; text-align: center; flex-shrink: 0; }
.nav-label { font-weight: 500; }

.nav-item.nav-soon {
  cursor: default;
  opacity: 0.45;
}
.nav-item.nav-soon:hover { background: none; color: var(--muted2); }
.nav-badge-soon {
  margin-left: auto;
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 0.8px;
  color: var(--muted);
  border: 1px solid var(--border2);
  border-radius: 4px;
  padding: 1px 4px;
}

.sidebar-footer {
  padding: 12px 18px;
  border-top: 1px solid var(--border2);
  font-size: 11px;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 7px;
}
.status-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 7px var(--green);
  flex-shrink: 0;
  animation: pulse-dot 2.5s infinite;
}
.status-dot.degraded { background: var(--red); box-shadow: 0 0 7px var(--red); }
@keyframes pulse-dot { 0%,100%{opacity:1} 50%{opacity:0.45} }

/* === MAIN AREA === */
#main { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-width: 0; }

#topbar {
  height: 52px;
  background: var(--bg2);
  border-bottom: 1px solid var(--border2);
  display: flex;
  align-items: center;
  padding: 0 24px;
  gap: 14px;
  flex-shrink: 0;
}
#topbar-title { font-size: 15px; font-weight: 600; flex: 1; }
#last-refresh { font-size: 11px; color: var(--muted); }
.topbar-btn {
  background: var(--glass);
  border: 1px solid var(--border2);
  color: var(--muted2);
  padding: 5px 12px;
  border-radius: 7px;
  font-size: 12px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.12s;
}
.topbar-btn:hover { background: var(--glass2); color: var(--text); border-color: var(--border); }

#content { flex: 1; overflow-y: auto; padding: 24px; }

/* === LAYOUT === */
.grid { display: grid; gap: 14px; }
.grid-4 { grid-template-columns: repeat(4, 1fr); }
.grid-3 { grid-template-columns: repeat(3, 1fr); }
.grid-2 { grid-template-columns: repeat(2, 1fr); }
.mt { margin-top: 16px; }
.mt2 { margin-top: 24px; }

/* === STAT CARDS === */
.stat-card {
  background: var(--bg2);
  border: 1px solid var(--border2);
  border-radius: var(--radius);
  padding: 18px 20px;
  position: relative;
  overflow: hidden;
}
.stat-card::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
}
.stat-card.c-cyan::before   { background: linear-gradient(90deg, var(--cyan), transparent); }
.stat-card.c-green::before  { background: linear-gradient(90deg, var(--green), transparent); }
.stat-card.c-purple::before { background: linear-gradient(90deg, var(--purple), transparent); }
.stat-card.c-yellow::before { background: linear-gradient(90deg, var(--yellow), transparent); }
.stat-card.c-orange::before { background: linear-gradient(90deg, var(--orange), transparent); }
.stat-label { font-size: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: 1.2px; font-weight: 600; }
.stat-value { font-size: 26px; font-weight: 700; margin: 7px 0 3px; }
.stat-sub { font-size: 11px; color: var(--muted2); }

/* === CARD === */
.card {
  background: var(--bg2);
  border: 1px solid var(--border2);
  border-radius: var(--radius);
  padding: 18px 20px;
}
.card-title {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 1.2px;
  color: var(--muted);
  margin-bottom: 14px;
  font-weight: 600;
}

/* === BADGES === */
.badge {
  display: inline-flex; align-items: center;
  padding: 2px 9px; border-radius: 20px;
  font-size: 10px; font-weight: 700; letter-spacing: 0.6px; text-transform: uppercase;
  white-space: nowrap;
}
.badge-green  { background:rgba(0,230,118,0.1);  color:var(--green);  border:1px solid rgba(0,230,118,0.25); }
.badge-red    { background:rgba(255,68,68,0.1);   color:var(--red);    border:1px solid rgba(255,68,68,0.25); }
.badge-yellow { background:rgba(255,215,64,0.1);  color:var(--yellow); border:1px solid rgba(255,215,64,0.25); }
.badge-cyan   { background:rgba(0,212,255,0.1);   color:var(--cyan);   border:1px solid rgba(0,212,255,0.25); }
.badge-purple { background:rgba(124,58,237,0.12); color:#a78bfa;       border:1px solid rgba(124,58,237,0.25); }
.badge-orange { background:rgba(255,152,0,0.1);   color:var(--orange); border:1px solid rgba(255,152,0,0.25); }

/* === TABLE === */
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th {
  text-align: left; padding: 9px 14px;
  font-size: 10px; color: var(--muted); text-transform: uppercase;
  letter-spacing: 1px; border-bottom: 1px solid var(--border2); font-weight: 600;
}
td { padding: 11px 14px; border-bottom: 1px solid rgba(255,255,255,0.03); vertical-align: middle; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: var(--glass); }
.mono { font-family: 'Courier New', monospace; font-size: 11px; color: var(--muted2); }

/* === BUTTONS === */
.btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 7px 14px; border-radius: 7px;
  font-size: 12px; font-weight: 500; cursor: pointer;
  transition: all 0.12s; border: none; font-family: inherit;
  white-space: nowrap;
}
.btn-primary { background: linear-gradient(135deg, var(--cyan), var(--purple)); color: #000; font-weight: 600; }
.btn-primary:hover { opacity: 0.85; transform: translateY(-1px); }
.btn-ghost { background: var(--glass); border: 1px solid var(--border2); color: var(--muted2); }
.btn-ghost:hover { background: var(--glass2); color: var(--text); border-color: var(--border); }
.btn-danger { background: rgba(255,68,68,0.08); border: 1px solid rgba(255,68,68,0.25); color: var(--red); }
.btn-danger:hover { background: rgba(255,68,68,0.15); }
.btn-sm { padding: 4px 10px; font-size: 11px; }
.btn-approve { background: rgba(0,230,118,0.08); border: 1px solid rgba(0,230,118,0.25); color: var(--green); }
.btn-approve:hover { background: rgba(0,230,118,0.15); }

/* === INPUTS === */
input, select, textarea {
  background: var(--bg3); border: 1px solid var(--border2); color: var(--text);
  padding: 9px 13px; border-radius: 7px; font-size: 13px; font-family: inherit;
  transition: border-color 0.12s; width: 100%;
}
input:focus, select:focus, textarea:focus {
  outline: none; border-color: var(--cyan);
  box-shadow: 0 0 0 2px rgba(0,212,255,0.08);
}
select option { background: var(--bg3); }
label { font-size: 11px; color: var(--muted); display: block; margin-bottom: 5px; font-weight: 500; }
.form-group { margin-bottom: 14px; }

/* === MODAL === */
.modal-overlay {
  display: none; position: fixed; inset: 0;
  background: rgba(0,0,0,0.65); backdrop-filter: blur(4px);
  z-index: 100; align-items: center; justify-content: center;
}
.modal-overlay.open { display: flex; }
.modal {
  background: var(--bg2); border: 1px solid var(--border2);
  border-radius: 14px; padding: 26px; width: 480px; max-width: 94vw;
  box-shadow: 0 24px 48px rgba(0,0,0,0.5);
}
.modal h2 { font-size: 16px; margin-bottom: 20px; color: var(--cyan); }
.modal-actions { display: flex; gap: 10px; margin-top: 20px; justify-content: flex-end; }

/* === SECTION HEADER === */
.section-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 20px;
}
.section-title { font-size: 20px; font-weight: 700; }
.section-sub { font-size: 12px; color: var(--muted2); margin-top: 3px; }

/* === MISC COMPONENTS === */
.cmd-area {
  background: var(--bg3); border: 1px solid var(--border2);
  border-radius: var(--radius); padding: 14px 18px;
  display: flex; gap: 12px; align-items: center;
  transition: border-color 0.12s;
}
.cmd-area:focus-within { border-color: var(--cyan); box-shadow: 0 0 0 2px rgba(0,212,255,0.05); }
.cmd-area input { background: transparent; border: none; flex: 1; font-size: 14px; padding: 0; }
.cmd-area input:focus { box-shadow: none; border: none; }

.health-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 11px 0; border-bottom: 1px solid rgba(255,255,255,0.03);
}
.health-item:last-child { border-bottom: none; }
.health-name { font-size: 13px; font-weight: 500; }
.health-detail { font-size: 11px; color: var(--muted); margin-top: 2px; }

.activity-item {
  display: flex; gap: 12px; padding: 9px 0;
  border-bottom: 1px solid rgba(255,255,255,0.03); font-size: 13px;
}
.activity-item:last-child { border-bottom: none; }
.activity-time { font-size: 10px; color: var(--muted); white-space: nowrap; margin-top: 2px; }

.loading { color: var(--muted); font-size: 12px; padding: 20px; text-align: center; }

.empty-state {
  text-align: center; padding: 48px 20px; grid-column: 1 / -1;
}
.empty-icon { font-size: 36px; margin-bottom: 14px; }
.empty-title { font-size: 15px; font-weight: 600; margin-bottom: 6px; }
.empty-sub { font-size: 12px; color: var(--muted2); margin-bottom: 20px; }

.agent-card {
  background: var(--bg2); border: 1px solid var(--border2);
  border-radius: var(--radius); padding: 18px 20px;
  display: flex; flex-direction: column; gap: 10px;
  transition: border-color 0.12s;
}
.agent-card:hover { border-color: var(--border); }
.agent-name { font-size: 14px; font-weight: 600; }
.agent-type { font-size: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; margin-top: 2px; }

.ws-card {
  background: var(--bg2); border: 1px solid var(--border2);
  border-radius: var(--radius); padding: 18px 20px; cursor: pointer;
  transition: border-color 0.12s, transform 0.12s;
}
.ws-card:hover { border-color: var(--border); transform: translateY(-1px); }
.ws-card.selected { border-color: var(--cyan); background: rgba(0,212,255,0.04); }
.ws-title { font-size: 14px; font-weight: 600; margin-bottom: 4px; }
.ws-desc { font-size: 12px; color: var(--muted2); margin-bottom: 12px; }

.cred-card {
  background: var(--bg2); border: 1px solid var(--border2);
  border-radius: var(--radius); padding: 16px 18px;
  display: flex; align-items: center; gap: 14px;
}
.cred-icon {
  width: 38px; height: 38px; border-radius: 9px;
  display: flex; align-items: center; justify-content: center;
  font-size: 16px; background: var(--bg3); border: 1px solid var(--border2); flex-shrink: 0;
}
.cred-info { flex: 1; min-width: 0; }
.cred-name { font-size: 13px; font-weight: 600; }
.cred-service { font-size: 11px; color: var(--muted); margin-top: 1px; }

.connector-row {
  display: flex; align-items: center; gap: 14px;
  padding: 14px 0; border-bottom: 1px solid rgba(255,255,255,0.03);
}
.connector-row:last-child { border-bottom: none; }
.connector-icon {
  width: 36px; height: 36px; border-radius: 8px;
  background: var(--bg3); border: 1px solid var(--border2);
  display: flex; align-items: center; justify-content: center;
  font-size: 15px; flex-shrink: 0;
}
.connector-name { font-size: 13px; font-weight: 600; }
.connector-meta { font-size: 11px; color: var(--muted); margin-top: 2px; }

.mem-entry {
  padding: 12px 0; border-bottom: 1px solid rgba(255,255,255,0.03);
}
.mem-entry:last-child { border-bottom: none; }
.mem-key { font-size: 12px; font-weight: 600; color: var(--cyan); margin-bottom: 3px; }
.mem-content { font-size: 12px; color: var(--muted2); line-height: 1.5; }
.mem-meta { font-size: 10px; color: var(--muted); margin-top: 4px; }

.tab-row { display: flex; gap: 6px; margin-bottom: 16px; border-bottom: 1px solid var(--border2); padding-bottom: 0; }
.tab-btn {
  background: none; border: none; border-bottom: 2px solid transparent;
  color: var(--muted2); font-size: 12px; font-weight: 600;
  padding: 8px 14px; cursor: pointer; font-family: inherit;
  letter-spacing: 0.5px; transition: all 0.12s; margin-bottom: -1px;
}
.tab-btn:hover { color: var(--text); }
.tab-btn.active { color: var(--cyan); border-bottom-color: var(--cyan); }
.tab-panel { display: none; }
.tab-panel.active { display: block; }

.plan-row {
  padding: 14px 0; border-bottom: 1px solid rgba(255,255,255,0.03);
}
.plan-row:last-child { border-bottom: none; }
.plan-title { font-size: 13px; font-weight: 600; margin-bottom: 4px; }
.plan-meta { font-size: 11px; color: var(--muted2); }
.plan-progress {
  height: 3px; background: var(--bg3); border-radius: 3px;
  margin-top: 8px; overflow: hidden;
}
.plan-progress-fill { height: 100%; border-radius: 3px; background: linear-gradient(90deg, var(--cyan), var(--purple)); }

.glow-text { color: var(--cyan); text-shadow: 0 0 18px rgba(0,212,255,0.5); }
.text-green { color: var(--green); }
.text-red { color: var(--red); }
.text-yellow { color: var(--yellow); }

#toast {
  position: fixed; bottom: 22px; right: 22px;
  background: var(--bg2); border: 1px solid var(--border);
  color: var(--text); padding: 11px 18px;
  border-radius: 9px; font-size: 13px; z-index: 999;
  box-shadow: 0 0 24px rgba(0,212,255,0.15);
  opacity: 0; transition: opacity 0.25s; pointer-events: none;
}
#toast.show { opacity: 1; }

.view { display: none; }
.view.active { display: block; }

::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 4px; }
</style>
</head>
<body>

<!-- === SIDEBAR === -->
<div id="sidebar">
  <div class="brand">
    <div class="brand-logo">
      <div class="brand-icon">⚡</div>
      <span class="brand-name">LUMENCORE</span>
    </div>
    <span class="brand-phase">Control Center</span>
  </div>

  <nav>
    <div class="nav-section-label">Control</div>
    <div class="nav-item active" onclick="showView('overview',this)">
      <span class="nav-icon">◈</span><span class="nav-label">Overview</span>
    </div>
    <div class="nav-item" onclick="showView('tasks',this)">
      <span class="nav-icon">✓</span><span class="nav-label">Tasks</span>
    </div>
    <div class="nav-item" onclick="showView('projects',this)">
      <span class="nav-icon">◻</span><span class="nav-label">Projects</span>
    </div>

    <div class="nav-section-label">Execution</div>
    <div class="nav-item" onclick="showView('workflows',this)">
      <span class="nav-icon">⟳</span><span class="nav-label">Workflows</span>
    </div>
    <div class="nav-item" onclick="showView('connectors',this)">
      <span class="nav-icon">⬡</span><span class="nav-label">Connectors</span>
    </div>
    <div class="nav-item" onclick="showView('agents',this)">
      <span class="nav-icon">◉</span><span class="nav-label">Agents</span>
    </div>
    <div class="nav-item" onclick="showView('commands',this)">
      <span class="nav-icon">≡</span><span class="nav-label">Commands</span>
    </div>

    <div class="nav-item" onclick="showView('telegram',this)">
      <span class="nav-icon">✈</span><span class="nav-label">Telegram</span>
    </div>

    <div class="nav-section-label">Data</div>
    <div class="nav-item" onclick="showView('memory',this)">
      <span class="nav-icon">◫</span><span class="nav-label">Memory</span>
    </div>

    <div class="nav-section-label">Config</div>
    <div class="nav-item" onclick="showView('workspaces',this)">
      <span class="nav-icon">⊞</span><span class="nav-label">Workspaces</span>
    </div>
    <div class="nav-item" onclick="showView('credentials',this)">
      <span class="nav-icon">◆</span><span class="nav-label">Credentials</span>
    </div>

    <div class="nav-section-label">System</div>
    <div class="nav-item" onclick="showView('system',this)">
      <span class="nav-icon">⬥</span><span class="nav-label">Health</span>
    </div>

    <div class="nav-section-label">Coming Soon</div>
    <div class="nav-item nav-soon">
      <span class="nav-icon">▤</span><span class="nav-label">Content</span>
      <span class="nav-badge-soon">SOON</span>
    </div>
    <div class="nav-item nav-soon">
      <span class="nav-icon">⏱</span><span class="nav-label">Automation</span>
      <span class="nav-badge-soon">SOON</span>
    </div>
  </nav>

  <div class="sidebar-footer">
    <div class="status-dot" id="sys-dot"></div>
    <span id="sys-status-text">ONLINE</span>
  </div>
</div>

<!-- === MAIN === -->
<div id="main">
  <div id="topbar">
    <h1 id="topbar-title">Overview</h1>
    <span id="last-refresh"></span>
    <button class="topbar-btn" onclick="refreshCurrent()">↻ Refresh</button>
  </div>

  <div id="content">

    <!-- === VIEW: OVERVIEW === -->
    <div class="view active" id="view-overview">
      <div class="grid grid-4" id="stat-cards">
        <div class="stat-card c-cyan">
          <div class="stat-label">System</div>
          <div class="stat-value" id="sys-health-val">—</div>
          <div class="stat-sub">Overall status</div>
        </div>
        <div class="stat-card c-yellow">
          <div class="stat-label">Queue</div>
          <div class="stat-value" id="queue-size-val">—</div>
          <div class="stat-sub">Pending commands</div>
        </div>
        <div class="stat-card c-purple">
          <div class="stat-label">Agents</div>
          <div class="stat-value" id="agents-count-val">—</div>
          <div class="stat-sub">Registered</div>
        </div>
        <div class="stat-card c-green">
          <div class="stat-label">Uptime</div>
          <div class="stat-value" id="uptime-val">—</div>
          <div class="stat-sub">Seconds running</div>
        </div>
      </div>

      <div class="grid grid-2 mt">
        <div class="card">
          <div class="card-title">Component Health</div>
          <div id="health-list"><div class="loading">Loading…</div></div>
        </div>
        <div class="card">
          <div class="card-title">Recent Activity</div>
          <div id="activity-feed"><div class="loading">Loading…</div></div>
        </div>
      </div>

      <div class="card mt">
        <div class="card-title">Quick Command</div>
        <div class="cmd-area">
          <input type="text" id="quick-cmd"
            placeholder="e.g. 'research AI trends 2026' — press Enter or click Run"
            onkeydown="if(event.key==='Enter')sendQuickCmd()"/>
          <button class="btn btn-primary btn-sm" onclick="sendQuickCmd()">▶ Run</button>
        </div>
        <div id="quick-cmd-result" style="margin-top:12px;font-size:13px;color:var(--muted)"></div>
      </div>
    </div>

    <!-- === VIEW: TASKS === -->
    <div class="view" id="view-tasks">
      <div class="section-header">
        <div>
          <div class="section-title">Tasks</div>
          <div class="section-sub">Control layer task queue — approval, dispatch, execution</div>
        </div>
      </div>
      <div class="card">
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Type</th>
                <th>Agent</th>
                <th>Priority</th>
                <th>Status</th>
                <th>Approval</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody id="tasks-body">
              <tr><td colspan="7" class="loading">Loading…</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- === VIEW: PROJECTS === -->
    <div class="view" id="view-projects">
      <div class="section-header">
        <div>
          <div class="section-title">Projects</div>
          <div class="section-sub">Active plans and their execution progress</div>
        </div>
      </div>
      <div id="projects-list"><div class="loading">Loading…</div></div>
    </div>

    <!-- === VIEW: WORKFLOWS === -->
    <div class="view" id="view-workflows">
      <div class="section-header">
        <div>
          <div class="section-title">Workflows</div>
          <div class="section-sub">System-level workflow runtime state</div>
        </div>
      </div>
      <div class="card">
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Type</th>
                <th>Status</th>
                <th>Linked Plan</th>
                <th>Created</th>
                <th>Completed</th>
              </tr>
            </thead>
            <tbody id="workflows-body">
              <tr><td colspan="6" class="loading">Loading…</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- === VIEW: CONNECTORS === -->
    <div class="view" id="view-connectors">
      <div class="section-header">
        <div>
          <div class="section-title">Connectors</div>
          <div class="section-sub">Registered integrations and their runtime status</div>
        </div>
      </div>
      <div class="grid grid-2" id="connectors-grid">
        <div class="loading">Loading…</div>
      </div>
    </div>

    <!-- === VIEW: AGENTS === -->
    <div class="view" id="view-agents">
      <div class="section-header">
        <div>
          <div class="section-title">Agents</div>
          <div class="section-sub">Registered AI agents and capability registry</div>
        </div>
      </div>
      <div class="grid grid-3" id="agent-cards"><div class="loading">Loading…</div></div>
    </div>

    <!-- === VIEW: COMMANDS === -->
    <div class="view" id="view-commands">
      <div class="section-header">
        <div>
          <div class="section-title">Commands</div>
          <div class="section-sub">Operator queue and execution history</div>
        </div>
      </div>
      <div class="grid grid-2">
        <div class="card">
          <div class="card-title">Awaiting Approval</div>
          <div id="approval-list"><div class="loading">Loading…</div></div>
        </div>
        <div class="card">
          <div class="card-title">Running Now</div>
          <div id="running-list"><div class="loading">Loading…</div></div>
        </div>
      </div>
      <div class="card mt">
        <div class="card-title">Command History</div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>Command</th><th>Intent</th><th>Status</th><th>Time</th><th>Actions</th></tr>
            </thead>
            <tbody id="cmd-history-body">
              <tr><td colspan="5" class="loading">Loading…</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- === VIEW: TELEGRAM === -->
    <div class="view" id="view-telegram">
      <div class="section-header">
        <div>
          <div class="section-title">Telegram — LumenClaw</div>
          <div class="section-sub">Commands ontvangen via @LumenClawwBot</div>
        </div>
        <button class="btn-sm" onclick="loadTelegram()">Vernieuwen</button>
      </div>
      <div class="grid grid-3" id="telegram-stats-grid">
        <div class="card stat-card">
          <div class="stat-val" id="tg-total">—</div>
          <div class="stat-label">Totaal</div>
        </div>
        <div class="card stat-card">
          <div class="stat-val" id="tg-completed" style="color:var(--green)">—</div>
          <div class="stat-label">Voltooid</div>
        </div>
        <div class="card stat-card">
          <div class="stat-val" id="tg-failed" style="color:var(--red)">—</div>
          <div class="stat-label">Mislukt</div>
        </div>
      </div>
      <div class="card mt">
        <div class="card-title">Recente Telegram Commando's</div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>Commando</th><th>Status</th><th>Resultaat</th><th>Tijd</th></tr>
            </thead>
            <tbody id="telegram-history-body">
              <tr><td colspan="4" class="loading">Loading…</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- === VIEW: MEMORY === -->
    <div class="view" id="view-memory">
      <div class="section-header">
        <div>
          <div class="section-title">Memory</div>
          <div class="section-sub">Agent memory store, skills, and decision logs</div>
        </div>
      </div>
      <div class="card">
        <div class="tab-row">
          <button class="tab-btn active" onclick="switchMemTab('entries',this)">Memory Entries</button>
          <button class="tab-btn" onclick="switchMemTab('skills',this)">Skills</button>
          <button class="tab-btn" onclick="switchMemTab('decisions',this)">Decisions</button>
        </div>
        <div class="tab-panel active" id="mem-tab-entries">
          <div id="mem-entries-list"><div class="loading">Loading…</div></div>
        </div>
        <div class="tab-panel" id="mem-tab-skills">
          <div id="mem-skills-list"><div class="loading">Loading…</div></div>
        </div>
        <div class="tab-panel" id="mem-tab-decisions">
          <div id="mem-decisions-list"><div class="loading">Loading…</div></div>
        </div>
      </div>
    </div>

    <!-- === VIEW: WORKSPACES === -->
    <div class="view" id="view-workspaces">
      <div class="section-header">
        <div>
          <div class="section-title">Workspaces</div>
          <div class="section-sub">Organize automated workflows and pipelines</div>
        </div>
        <button class="btn btn-primary" onclick="openModal('ws-modal')">+ New Workspace</button>
      </div>
      <div class="grid grid-3" id="ws-grid"><div class="loading">Loading…</div></div>
      <div id="ws-detail" style="display:none" class="mt">
        <div class="card">
          <div class="card-title" id="ws-detail-title">Workflows</div>
          <div id="ws-workflow-list"><div class="loading">Loading…</div></div>
          <div style="margin-top:14px">
            <button class="btn btn-ghost btn-sm" onclick="openModal('wf-modal')">+ Add Workflow</button>
          </div>
        </div>
      </div>
    </div>

    <!-- === VIEW: CREDENTIALS === -->
    <div class="view" id="view-credentials">
      <div class="section-header">
        <div>
          <div class="section-title">Credentials</div>
          <div class="section-sub">API keys, OAuth tokens, and webhook secrets</div>
        </div>
        <button class="btn btn-primary" onclick="openModal('cred-modal')">+ Add Credential</button>
      </div>
      <div id="cred-list" style="display:grid;gap:12px"><div class="loading">Loading…</div></div>
    </div>

    <!-- === VIEW: SYSTEM HEALTH === -->
    <div class="view" id="view-system">
      <div class="section-header">
        <div>
          <div class="section-title">System Health</div>
          <div class="section-sub">Runtime component status and deployment info</div>
        </div>
      </div>
      <div class="grid grid-2">
        <div class="card">
          <div class="card-title">Components</div>
          <div id="system-components"><div class="loading">Loading…</div></div>
        </div>
        <div class="card">
          <div class="card-title">Deployment</div>
          <div id="system-deployment"><div class="loading">Loading…</div></div>
        </div>
      </div>
      <div class="card mt">
        <div class="card-title">Recovery Status</div>
        <div id="system-recovery"><div class="loading">Loading…</div></div>
      </div>
    </div>

  </div><!-- #content -->
</div><!-- #main -->

<!-- === MODALS === -->
<div class="modal-overlay" id="ws-modal">
  <div class="modal">
    <h2>New Workspace</h2>
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
    <h2>New Workflow</h2>
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
    <h2>Add Credential</h2>
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
    <div class="form-group"><label>Value</label>
      <input type="password" id="cred-value" placeholder="Paste your key or URL"/>
    </div>
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeModal('cred-modal')">Cancel</button>
      <button class="btn btn-primary" onclick="saveCred()">Save</button>
    </div>
  </div>
</div>

<div class="modal-overlay" id="cmd-detail-modal">
  <div class="modal" style="width:560px">
    <h2>Command Detail</h2>
    <div id="cmd-detail-body" style="font-size:13px;color:var(--muted2)"></div>
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeModal('cmd-detail-modal')">Close</button>
    </div>
  </div>
</div>

<div id="toast"></div>

<script>
// === CORE ===
const API = '/proxy';
let currentView = 'overview';
let selectedWorkspaceId = null;

function showView(name, el) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('view-' + name).classList.add('active');
  if (el) el.classList.add('active');
  currentView = name;
  document.getElementById('topbar-title').textContent =
    el ? el.querySelector('.nav-label').textContent : name;
  loadView(name);
}

function refreshCurrent() { loadView(currentView); }

function loadView(name) {
  document.getElementById('last-refresh').textContent = new Date().toLocaleTimeString();
  const map = {
    overview:    loadOverview,
    tasks:       loadTasks,
    projects:    loadProjects,
    workflows:   loadWorkflowsGlobal,
    connectors:  loadConnectors,
    agents:      loadAgents,
    commands:    loadCommands,
    telegram:    loadTelegram,
    memory:      loadMemory,
    workspaces:  loadWorkspaces,
    credentials: loadCredentials,
    system:      loadSystem,
  };
  if (map[name]) map[name]();
}

async function api(path, opts = {}) {
  try {
    const r = await fetch(API + path, {
      headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
      ...opts
    });
    if (r.status === 204) return { ok: true };
    if (!r.ok) throw new Error(r.status);
    return await r.json();
  } catch { return null; }
}

function toast(msg, ms = 3000) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), ms);
}

function openModal(id)  { document.getElementById(id).classList.add('open'); }
function closeModal(id) { document.getElementById(id).classList.remove('open'); }
document.querySelectorAll('.modal-overlay').forEach(m => {
  m.addEventListener('click', e => { if (e.target === m) m.classList.remove('open'); });
});

// === HELPERS ===
function statusBadge(s) {
  if (!s) return '<span class="badge badge-cyan">—</span>';
  s = String(s).toLowerCase();
  const map = {
    ok:'green', healthy:'green', active:'green', completed:'green', success:'green',
    enabled:'green', configured:'green',
    running:'cyan', pending:'yellow', queued:'yellow', awaiting_approval:'yellow',
    in_progress:'cyan', executing:'cyan',
    failed:'red', error:'red', cancelled:'red', denied:'red', disabled:'red',
    idle:'purple', unknown:'purple',
  };
  return `<span class="badge badge-${map[s] || 'cyan'}">${s}</span>`;
}

function serviceIcon(svc) {
  const icons = {
    openai:'🤖', telegram:'✈️', github:'🐙', slack:'💬',
    webhook:'🔗', custom:'⚙️', search:'🔍', openai_api:'🤖'
  };
  return icons[svc] || '⚡';
}

function connectorIcon(kind) {
  const icons = {
    llm:'🤖', ai_model:'🤖',
    research:'🔍', search:'🔍',
    scm:'🐙',
    webhook:'🔗',
    database:'🗄️', db:'🗄️',
    api:'⚙️',
  };
  return icons[kind] || '⬡';
}

function shortId(id) { return id ? String(id).slice(0, 8) + '…' : '—'; }

function fmtTime(ts) {
  if (!ts) return '—';
  try { return new Date(ts).toLocaleString(); } catch { return ts; }
}

function fmtUptime(s) {
  if (s == null || s < 0) return '—';
  if (s < 60) return s + 's';
  if (s < 3600) return Math.floor(s / 60) + 'm';
  return Math.floor(s / 3600) + 'h ' + Math.floor((s % 3600) / 60) + 'm';
}

function progressBar(current, total) {
  if (!total) return '';
  const pct = Math.min(100, Math.round((current / total) * 100));
  return `<div class="plan-progress">
    <div class="plan-progress-fill" style="width:${pct}%"></div>
  </div>`;
}

// === OVERVIEW ===
async function loadOverview() {
  // Pull from two sources: system/overview for core metrics, operator/summary for activity
  const [sys, summary] = await Promise.all([
    api('/api/system/overview'),
    api('/api/operator/summary'),
  ]);

  // Stat cards — prefer system/overview, fall back to summary
  const sysStatus = sys?.system_status || summary?.system_health || 'unknown';
  const isOk = sysStatus === 'healthy' || sysStatus === 'ok';

  document.getElementById('sys-health-val').innerHTML = isOk
    ? '<span class="glow-text">OK</span>'
    : `<span class="text-red">${sysStatus.toUpperCase()}</span>`;

  document.getElementById('queue-size-val').textContent =
    sys?.queue_size ?? summary?.queue_size ?? '—';

  document.getElementById('agents-count-val').textContent =
    sys?.agents ?? '—';

  document.getElementById('uptime-val').textContent =
    sys ? fmtUptime(sys.uptime_seconds) : '—';

  // Sidebar dot
  const dot = document.getElementById('sys-dot');
  dot.className = 'status-dot' + (isOk ? '' : ' degraded');
  document.getElementById('sys-status-text').textContent = isOk ? 'ONLINE' : 'DEGRADED';

  // Component health panel
  if (sys) {
    const healthEl = document.getElementById('health-list');
    const dbOk  = sys.database_status === 'healthy';
    const redOk = sys.redis_status === 'healthy';
    const comps = [
      { name: 'Database', ok: dbOk,  detail: sys.database_status },
      { name: 'Redis',    ok: redOk, detail: sys.redis_status },
      { name: 'API',      ok: isOk,  detail: sys.system_status },
    ];
    if (summary) {
      const agentRuns = summary.agent_runs || {};
      comps.push({ name: 'Agent Runs', ok: true, detail: `${agentRuns.total || 0} total` });
    }
    healthEl.innerHTML = comps.map(c => `
      <div class="health-item">
        <div>
          <div class="health-name">${c.name}</div>
          <div class="health-detail">${c.detail || ''}</div>
        </div>
        ${c.ok
          ? '<span class="badge badge-green">OK</span>'
          : '<span class="badge badge-red">ERR</span>'}
      </div>`).join('');
  }

  // Activity feed from operator/summary
  if (summary) {
    const recent = summary.recent_commands || [];
    const feedEl = document.getElementById('activity-feed');
    if (recent.length) {
      feedEl.innerHTML = recent.slice(0, 8).map(c => {
        const answer = c.result?.agent_result?.output_text;
        const preview = answer ? answer.slice(0, 80) + (answer.length > 80 ? '…' : '') : null;
        return `<div class="activity-item" style="flex-direction:column;gap:3px;cursor:pointer"
                     onclick="showCmdDetail('${c.command_id || c.id}')">
          <div style="display:flex;gap:10px;align-items:center">
            <span class="activity-time">${fmtTime(c.timestamp || c.created_at).split(',').pop() || ''}</span>
            <span style="font-weight:500;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
              ${(c.command_text || '—').slice(0, 52)}
            </span>
            ${statusBadge(c.status)}
          </div>
          ${preview
            ? `<div style="font-size:11px;color:var(--cyan);padding-left:2px;line-height:1.4">"${preview}"</div>`
            : ''}
        </div>`;
      }).join('');
    } else {
      feedEl.innerHTML = '<div class="loading">No recent activity</div>';
    }
  }
}

// === TASKS ===
async function loadTasks() {
  const data = await api('/api/tasks?limit=50');
  const tbody = document.getElementById('tasks-body');
  const items = data?.items || [];
  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="loading">No tasks yet</td></tr>';
    return;
  }
  tbody.innerHTML = items.map(t => `
    <tr>
      <td><span class="badge badge-purple">${t.task_type || '—'}</span></td>
      <td style="color:var(--muted2)">${t.agent || '—'}</td>
      <td>${t.priority != null ? `<span class="badge badge-cyan">${t.priority}</span>` : '—'}</td>
      <td>${statusBadge(t.status)}</td>
      <td>${t.approval_required
            ? (t.approval_status === 'approved'
                ? '<span class="badge badge-green">approved</span>'
                : t.approval_status === 'denied'
                  ? '<span class="badge badge-red">denied</span>'
                  : '<span class="badge badge-yellow">required</span>')
            : '<span style="color:var(--muted);font-size:11px">—</span>'}</td>
      <td class="mono">${fmtTime(t.created_at)}</td>
      <td>
        ${t.approval_required && !t.approval_status
          ? `<button class="btn btn-approve btn-sm"
               onclick="approveTask('${t.id}')">✓ Approve</button>`
          : ''}
      </td>
    </tr>`).join('');
}

async function approveTask(id) {
  const r = await api(`/api/tasks/${id}/approve`, {
    method: 'POST',
    body: JSON.stringify({ approved: true })
  });
  if (r) { toast('Task approved'); loadTasks(); }
  else toast('✗ Failed to approve task');
}

// === PROJECTS (PLANS) ===
async function loadProjects() {
  const data = await api('/api/plans?limit=20');
  const el = document.getElementById('projects-list');
  const items = data?.items || [];
  if (!items.length) {
    el.innerHTML = `<div class="card empty-state">
      <div class="empty-icon">◻</div>
      <div class="empty-title">No plans yet</div>
      <div class="empty-sub">Plans are created automatically when commands are executed</div>
    </div>`;
    return;
  }
  el.innerHTML = `<div class="card">` + items.map(p => {
    const pct = p.total_steps
      ? Math.round(((p.current_step_index || 0) / p.total_steps) * 100)
      : 0;
    return `<div class="plan-row">
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
        <div style="flex:1;min-width:200px">
          <div class="plan-title">${p.intent || p.plan_type || shortId(p.plan_id)}</div>
          <div class="plan-meta">
            Plan <span class="mono">${shortId(p.plan_id)}</span>
            · ${p.total_steps || 0} steps
            · cmd <span class="mono">${shortId(p.command_id)}</span>
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:10px;flex-shrink:0">
          ${statusBadge(p.status)}
          <span style="font-size:11px;color:var(--muted2)">${fmtTime(p.created_at)}</span>
        </div>
      </div>
      ${p.total_steps ? progressBar(p.current_step_index || 0, p.total_steps) + `
        <div style="font-size:10px;color:var(--muted);margin-top:4px">
          Step ${p.current_step_index || 0} of ${p.total_steps} · ${pct}%
        </div>` : ''}
    </div>`;
  }).join('') + `</div>`;
}

// === WORKFLOWS (GLOBAL) ===
async function loadWorkflowsGlobal() {
  const data = await api('/api/workflows?limit=20');
  const tbody = document.getElementById('workflows-body');
  const items = data?.items || [];
  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="loading">No workflows in the runtime yet</td></tr>';
    return;
  }
  tbody.innerHTML = items.map(w => `
    <tr>
      <td class="mono">${shortId(w.workflow_id)}</td>
      <td><span class="badge badge-purple">${w.workflow_type || '—'}</span></td>
      <td>${statusBadge(w.status)}</td>
      <td class="mono">${w.linked_plan_id ? shortId(w.linked_plan_id) : '—'}</td>
      <td class="mono">${fmtTime(w.created_at)}</td>
      <td class="mono">${fmtTime(w.completed_at)}</td>
    </tr>`).join('');
}

// === CONNECTORS ===
async function loadConnectors() {
  const data = await api('/api/connectors');
  const el = document.getElementById('connectors-grid');
  const items = data?.items || [];
  if (!items.length) {
    el.innerHTML = '<div class="loading" style="grid-column:1/-1">No connectors registered</div>';
    return;
  }
  el.innerHTML = items.map(c => {
    const healthBadge = c.healthy === true
      ? '<span class="badge badge-green">healthy</span>'
      : c.healthy === false
        ? '<span class="badge badge-red">unhealthy</span>'
        : statusBadge(c.status);
    const actions = c.supported_actions && c.supported_actions.length
      ? c.supported_actions.slice(0, 3).join(' · ')
      : null;
    return `<div class="card">
      <div class="connector-row">
        <div class="connector-icon">${connectorIcon(c.kind)}</div>
        <div style="flex:1;min-width:0">
          <div class="connector-name">${c.name || c.connector_key}</div>
          <div class="connector-meta">${c.kind} · ${c.source}</div>
        </div>
        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:5px;flex-shrink:0">
          ${healthBadge}
          ${c.enabled
            ? '<span class="badge badge-green">enabled</span>'
            : '<span class="badge badge-red">disabled</span>'}
        </div>
      </div>
      ${actions
        ? `<div style="font-size:10px;color:var(--muted);margin-top:6px">Actions: ${actions}</div>`
        : ''}
    </div>`;
  }).join('');
}

// === AGENTS ===
async function loadAgents() {
  const resp = await api('/api/agents/registry');
  const data = (resp && resp.items) ? resp.items : (Array.isArray(resp) ? resp : []);
  const el = document.getElementById('agent-cards');
  if (!data.length) {
    el.innerHTML = '<div class="loading">No agents registered</div>';
    return;
  }
  el.innerHTML = data.map(a => {
    const meta = a.metadata || {};
    const caps = (a.capabilities || []).slice(0, 3).join(' · ');
    return `<div class="agent-card">
      <div>
        <div class="agent-name">${a.name || a.agent_key || '—'}</div>
        <div class="agent-type">${a.agent_type || 'agent'}</div>
      </div>
      <div>${statusBadge(a.status || 'active')}</div>
      <div style="font-size:12px;color:var(--muted2)">
        Runs <strong style="color:var(--text)">${a.run_count ?? '—'}</strong>
        ${meta.phase ? ` · Phase <strong style="color:var(--text)">${meta.phase}</strong>` : ''}
      </div>
      ${caps ? `<div style="font-size:10px;color:var(--muted)">${caps}</div>` : ''}
    </div>`;
  }).join('');
}

// === COMMANDS ===
async function loadCommands() {
  const queue = await api('/api/operator/queue');
  const awaiting = queue?.queued_commands || queue?.awaiting_approval || [];
  const running  = queue?.running_commands || queue?.running || [];

  document.getElementById('approval-list').innerHTML = awaiting.length
    ? awaiting.map(c => `
        <div class="activity-item">
          <div style="flex:1">
            <div style="font-size:13px;font-weight:500">${c.command_text || '—'}</div>
            <div style="font-size:10px;color:var(--muted)">${shortId(c.id)}</div>
          </div>
          <div style="display:flex;gap:6px">
            <button class="btn btn-approve btn-sm" onclick="approveCmd('${c.id}')">✓ Approve</button>
            <button class="btn btn-danger btn-sm" onclick="cancelCmd('${c.id}')">✗</button>
          </div>
        </div>`).join('')
    : '<div class="loading">No commands awaiting approval</div>';

  document.getElementById('running-list').innerHTML = running.length
    ? running.map(c => `
        <div class="activity-item">
          <div style="flex:1">
            <div style="font-size:13px;font-weight:500">${c.command_text || '—'}</div>
            <div style="font-size:10px;color:var(--muted)">${shortId(c.id)}</div>
          </div>
          ${statusBadge('running')}
        </div>`).join('')
    : '<div class="loading">Nothing running</div>';

  const histResp = await api('/api/operator/commands?limit=25');
  const history = (histResp && histResp.items) ? histResp.items
    : (Array.isArray(histResp) ? histResp : []);
  const tbody = document.getElementById('cmd-history-body');
  if (!history.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="loading">No commands yet</td></tr>';
    return;
  }
  tbody.innerHTML = history.map(c => {
    const cid = c.command_id || c.id;
    return `<tr>
      <td style="max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
        ${c.command_text || '—'}
      </td>
      <td><span class="badge badge-purple">${c.intent || c.planned_task_type || '—'}</span></td>
      <td>${statusBadge(c.status)}</td>
      <td class="mono">${fmtTime(c.timestamp || c.created_at)}</td>
      <td>
        <button class="btn btn-ghost btn-sm" onclick="showCmdDetail('${cid}')">Detail</button>
        ${c.status === 'awaiting_approval'
          ? `<button class="btn btn-approve btn-sm" onclick="approveCmd('${cid}')">Approve</button>`
          : ''}
        ${c.status === 'failed'
          ? `<button class="btn btn-ghost btn-sm" onclick="retryCmd('${cid}')">Retry</button>`
          : ''}
      </td>
    </tr>`;
  }).join('');
}

async function approveCmd(id) {
  await api(`/api/command/${id}/approve`, { method: 'POST' });
  toast('Command approved'); loadCommands();
}
async function cancelCmd(id) {
  await api(`/api/command/${id}/cancel`, { method: 'POST' });
  toast('Command cancelled'); loadCommands();
}
async function retryCmd(id) {
  await api(`/api/command/${id}/retry`, { method: 'POST' });
  toast('Command retried'); loadCommands();
}

async function showCmdDetail(id) {
  const d = await api(`/api/operator/command/${id}`);
  if (!d) return;
  const result = d.result || d.result_summary;
  const agentResult = result?.agent_result;
  document.getElementById('cmd-detail-body').innerHTML = `
    <div class="form-group"><strong>ID:</strong> <span class="mono">${d.command_id || d.id}</span></div>
    <div class="form-group"><strong>Command:</strong> ${d.command_text}</div>
    <div class="form-group"><strong>Type:</strong> ${d.planned_task_type || d.intent || '—'}</div>
    <div class="form-group"><strong>Status:</strong> ${statusBadge(d.status)}</div>
    <div class="form-group"><strong>Decision:</strong> ${d.execution_decision || '—'}</div>
    <div class="form-group"><strong>Time:</strong> ${fmtTime(d.timestamp || d.created_at)}</div>
    ${agentResult ? `
      <div class="form-group">
        <strong>Agent output:</strong>
        <div style="background:var(--bg3);padding:10px;border-radius:6px;font-size:12px;
                    margin-top:6px;max-height:150px;overflow:auto;white-space:pre-wrap">
          ${agentResult.output_text || ''}
        </div>
        <div style="font-size:10px;color:var(--muted);margin-top:4px">
          Model: ${agentResult.model || '—'} · Tokens: ${agentResult.tokens_used || 0}
        </div>
      </div>` : ''}
    ${result && !agentResult ? `
      <div class="form-group">
        <strong>Result:</strong>
        <pre style="background:var(--bg3);padding:10px;border-radius:6px;font-size:11px;
                    overflow:auto;max-height:120px">${JSON.stringify(result, null, 2)}</pre>
      </div>` : ''}
  `;
  openModal('cmd-detail-modal');
}

// === MEMORY ===
let memTabLoaded = { entries: false, skills: false, decisions: false };

function switchMemTab(tab, btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('mem-tab-' + tab).classList.add('active');
  if (!memTabLoaded[tab]) {
    memTabLoaded[tab] = true;
    if (tab === 'entries')   loadMemEntries();
    if (tab === 'skills')    loadMemSkills();
    if (tab === 'decisions') loadMemDecisions();
  }
}

async function loadTelegram() {
  const tbody = document.getElementById('telegram-history-body');
  tbody.innerHTML = '<tr><td colspan="4" class="loading">Loading…</td></tr>';

  const data = await api('/api/command/history?limit=100');
  if (!data) {
    tbody.innerHTML = '<tr><td colspan="4" class="muted">Niet bereikbaar</td></tr>';
    return;
  }

  const items = (data.items || []).filter(i => i.tenant_id === 'telegram');

  const total = items.length;
  const completed = items.filter(i => i.status === 'completed').length;
  const failed = items.filter(i => ['failed','denied','timeout'].includes(i.status)).length;

  document.getElementById('tg-total').textContent = total;
  document.getElementById('tg-completed').textContent = completed;
  document.getElementById('tg-failed').textContent = failed;

  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="muted">Geen Telegram commando\'s gevonden</td></tr>';
    return;
  }

  tbody.innerHTML = items.slice(0, 25).map(item => {
    const ts = (item.created_at || '').slice(0, 16).replace('T', ' ');
    const status = item.status || '?';
    const statusColor = status === 'completed' ? 'var(--green)' : status === 'failed' || status === 'denied' ? 'var(--red)' : 'var(--yellow)';
    const cmd = (item.command_text || '').substring(0, 60);
    const summary = item.result_summary || {};
    const result = (item.result || summary.output_text || summary.answer || '—');
    const resultShort = typeof result === 'string' ? result.substring(0, 80) : '—';
    return `<tr>
      <td style="max-width:200px;word-break:break-word">${cmd}</td>
      <td><span style="color:${statusColor}">${status}</span></td>
      <td style="max-width:250px;word-break:break-word;color:var(--muted2)">${resultShort}</td>
      <td style="color:var(--muted)">${ts}</td>
    </tr>`;
  }).join('');
}

async function loadMemory() {
  memTabLoaded = { entries: false, skills: false, decisions: false };
  // Reset to first tab
  document.querySelectorAll('.tab-btn').forEach((b, i) => b.classList.toggle('active', i === 0));
  document.querySelectorAll('.tab-panel').forEach((p, i) => p.classList.toggle('active', i === 0));
  loadMemEntries();
}

async function loadMemEntries() {
  const data = await api('/api/memory?limit=50');
  const el = document.getElementById('mem-entries-list');
  const items = data?.items || [];
  if (!items.length) {
    el.innerHTML = '<div class="loading">No memory entries stored</div>';
    return;
  }
  el.innerHTML = items.map(m => `
    <div class="mem-entry">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        <span class="mem-key">${m.key || '—'}</span>
        <span class="badge badge-purple">${m.type || '—'}</span>
      </div>
      <div class="mem-content">${(m.content || '').slice(0, 180)}${(m.content || '').length > 180 ? '…' : ''}</div>
      <div class="mem-meta">${fmtTime(m.created_at)}${m.source_task_id ? ' · task ' + shortId(m.source_task_id) : ''}</div>
    </div>`).join('');
}

async function loadMemSkills() {
  const data = await api('/api/memory/skills?limit=50');
  const el = document.getElementById('mem-skills-list');
  const items = data?.items || [];
  if (!items.length) {
    el.innerHTML = '<div class="loading">No skills learned yet</div>';
    return;
  }
  el.innerHTML = `<div class="table-wrap"><table>
    <thead><tr><th>Skill</th><th>Description</th><th>Used</th><th>Last Used</th></tr></thead>
    <tbody>${items.map(s => `
      <tr>
        <td style="font-weight:600">${s.name || '—'}</td>
        <td style="color:var(--muted2)">${(s.description || '—').slice(0, 80)}</td>
        <td><span class="badge badge-cyan">${s.success_count || 0}</span></td>
        <td class="mono">${fmtTime(s.last_used_at)}</td>
      </tr>`).join('')}
    </tbody>
  </table></div>`;
}

async function loadMemDecisions() {
  const data = await api('/api/memory/decisions?limit=50');
  const el = document.getElementById('mem-decisions-list');
  const items = data?.items || [];
  if (!items.length) {
    el.innerHTML = '<div class="loading">No decision logs recorded</div>';
    return;
  }
  el.innerHTML = items.map(d => `
    <div class="mem-entry">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        <span class="mem-key">${d.decision || '—'}</span>
        <span class="badge badge-orange">${d.agent || '—'}</span>
        ${d.outcome ? statusBadge(d.outcome) : ''}
      </div>
      <div class="mem-content">${(d.reasoning || '').slice(0, 160)}${(d.reasoning || '').length > 160 ? '…' : ''}</div>
      <div class="mem-meta">${fmtTime(d.created_at)}${d.task_id ? ' · task ' + shortId(d.task_id) : ''}</div>
    </div>`).join('');
}

// === SYSTEM HEALTH ===
async function loadSystem() {
  const data = await api('/api/system/health');
  if (!data) {
    document.getElementById('system-components').innerHTML =
      '<div class="loading">Unable to reach system health endpoint</div>';
    return;
  }

  const comps = data.components || {};
  const db  = comps.database || {};
  const red = comps.redis || {};
  const wkr = comps.worker || {};
  const sch = comps.scheduler || {};

  const rows = [
    { name: 'Database',  ok: db.ok,  detail: db.message  || db.detail  || db.error  || '' },
    { name: 'Redis',     ok: red.ok, detail: red.message || red.detail || red.error || '' },
    { name: 'Worker',    ok: wkr.ok !== false, detail: wkr.message || wkr.detail || (typeof wkr === 'string' ? wkr : '') },
    { name: 'Scheduler', ok: sch.ok !== false, detail: sch.message || sch.detail || (typeof sch === 'string' ? sch : '') },
  ];

  document.getElementById('system-components').innerHTML =
    rows.map(r => `
      <div class="health-item">
        <div>
          <div class="health-name">${r.name}</div>
          ${r.detail ? `<div class="health-detail">${String(r.detail).slice(0, 80)}</div>` : ''}
        </div>
        ${r.ok
          ? '<span class="badge badge-green">OK</span>'
          : '<span class="badge badge-red">ERR</span>'}
      </div>`).join('');

  const dep = data.deployment || {};
  document.getElementById('system-deployment').innerHTML = `
    <div class="health-item">
      <div class="health-name">Release</div>
      <span class="mono">${data.release?.release_id || '—'}</span>
    </div>
    <div class="health-item">
      <div class="health-name">Phase</div>
      <span class="badge badge-cyan">${data.phase || '—'}</span>
    </div>
    <div class="health-item">
      <div class="health-name">Restarts</div>
      <span style="font-size:13px;font-weight:600">${dep.restart_count ?? '—'}</span>
    </div>
    <div class="health-item">
      <div class="health-name">Failed Restarts</div>
      <span style="font-size:13px;font-weight:600;color:${dep.failed_restarts ? 'var(--red)' : 'var(--muted2)'}">
        ${dep.failed_restarts ?? '—'}
      </span>
    </div>
    <div class="health-item">
      <div class="health-name">Last Restart</div>
      <span class="mono" style="font-size:11px">${fmtTime(dep.last_restart_at)}</span>
    </div>`;

  const rec = data.recovery || {};
  document.getElementById('system-recovery').innerHTML = `
    <div class="health-item">
      <div class="health-name">Recovery Status</div>
      ${statusBadge(rec.status || (rec.recoverable === true ? 'ok' : rec.recoverable === false ? 'degraded' : 'unknown'))}
    </div>
    ${rec.last_action ? `
      <div class="health-item">
        <div class="health-name">Last Action</div>
        <span style="font-size:12px;color:var(--muted2)">${rec.last_action}</span>
      </div>` : ''}
    ${rec.message ? `
      <div style="font-size:12px;color:var(--muted2);margin-top:8px">${rec.message}</div>` : ''}`;
}

// === QUICK COMMAND ===
async function sendQuickCmd() {
  const txt = document.getElementById('quick-cmd').value.trim();
  if (!txt) return;
  const el = document.getElementById('quick-cmd-result');
  el.innerHTML = '<span style="color:var(--muted)">⏳ Sending to agent…</span>';
  document.getElementById('quick-cmd').value = '';

  const r = await api('/api/input/command', {
    method: 'POST',
    body: JSON.stringify({ input_text: txt })
  });
  if (!r) { el.textContent = '✗ Failed to send command'; return; }

  const cmdId = r.command_id || r.id;
  if (!cmdId) { el.innerHTML = `✓ Sent ${statusBadge(r.status)}`; return; }

  el.innerHTML = '<span style="color:var(--muted)">⏳ Agent is thinking…</span>';

  for (let i = 0; i < 40; i++) {
    await new Promise(res => setTimeout(res, 1500));
    const d = await api(`/api/operator/command/${cmdId}`);
    if (!d) continue;
    if (['completed', 'failed', 'cancelled', 'denied'].includes(d.status)) {
      const result = d.result || d.result_summary;
      const agentResult = result?.agent_result;
      const outputText = agentResult?.output_text;
      if (outputText) {
        el.innerHTML = `
          <div style="border-left:2px solid var(--cyan);padding-left:14px;margin-top:4px">
            <div style="font-size:10px;color:var(--muted);margin-bottom:6px">
              ${d.planned_task_type || 'agent'} · ${agentResult.model || ''} · ${agentResult.tokens_used || 0} tokens
            </div>
            <div style="font-size:14px;line-height:1.65;color:var(--text);white-space:pre-wrap">${outputText}</div>
          </div>`;
      } else if (d.status === 'failed') {
        el.innerHTML = `<span style="color:var(--red)">✗ ${result?.error || 'Agent failed'}</span>`;
      } else {
        el.innerHTML = `✓ Done ${statusBadge(d.status)}`;
      }
      loadOverview();
      return;
    }
  }
  el.innerHTML = '<span style="color:var(--yellow)">⏱ Timeout — check Commands for result</span>';
}

// === WORKSPACES ===
async function loadWorkspaces() {
  const data = await api('/api/workspaces');
  const el = document.getElementById('ws-grid');
  if (!data || !data.length) {
    el.innerHTML = `<div class="card empty-state">
      <div class="empty-icon">⊞</div>
      <div class="empty-title">No workspaces yet</div>
      <div class="empty-sub">Create a workspace to organize your automated workflows</div>
      <button class="btn btn-primary" onclick="openModal('ws-modal')">+ Create First Workspace</button>
    </div>`;
    return;
  }
  el.innerHTML = data.map(w => `
    <div class="ws-card ${selectedWorkspaceId === w.id ? 'selected' : ''}"
         onclick="selectWorkspace('${w.id}','${w.name}')">
      <div class="ws-title">${w.name}</div>
      <div class="ws-desc">${w.description || 'No description'}</div>
      <div>${statusBadge(w.status)}</div>
    </div>`).join('');
}

async function selectWorkspace(id, name) {
  selectedWorkspaceId = id;
  document.getElementById('ws-detail').style.display = 'block';
  document.getElementById('ws-detail-title').textContent = `Workflows — ${name}`;
  await loadWsWorkflows(id);
  loadWorkspaces();
}

async function loadWsWorkflows(wsId) {
  const data = await api(`/api/workspaces/${wsId}/workflows`);
  const el = document.getElementById('ws-workflow-list');
  if (!data || !data.length) {
    el.innerHTML = '<div class="loading">No workflows yet — add one below</div>';
    return;
  }
  el.innerHTML = data.map(wf => `
    <div style="background:var(--bg3);border:1px solid var(--border2);border-radius:9px;
                padding:13px 16px;margin-bottom:10px;display:flex;align-items:center;gap:12px">
      <div style="flex:1">
        <div style="font-size:13px;font-weight:600">${wf.name}</div>
        <div style="font-size:11px;color:var(--muted);margin-top:3px">
          Trigger: <span style="color:var(--cyan)">${wf.trigger_type}</span>
          ${wf.last_run_at ? ' · Last: ' + fmtTime(wf.last_run_at) : ' · Never run'}
        </div>
      </div>
      ${statusBadge(wf.status)}
      <button class="btn btn-ghost btn-sm"
        onclick="runWsWorkflow('${wsId}','${wf.id}','${wf.name}')">▶ Run</button>
    </div>`).join('');
}

async function runWsWorkflow(wsId, wfId, name) {
  const r = await api(`/api/workspaces/${wsId}/workflows/${wfId}/run`, { method: 'POST' });
  toast(r && r.ok ? `✓ Workflow "${name}" triggered` : '✗ Failed');
  loadWsWorkflows(wsId);
}

async function createWorkspace() {
  const name = document.getElementById('ws-name').value.trim();
  const desc = document.getElementById('ws-desc').value.trim();
  if (!name) { toast('Name is required'); return; }
  const r = await api('/api/workspaces', {
    method: 'POST',
    body: JSON.stringify({ name, description: desc })
  });
  if (r && r.id) {
    toast(`✓ Workspace "${name}" created`);
    closeModal('ws-modal');
    document.getElementById('ws-name').value = '';
    document.getElementById('ws-desc').value = '';
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
    method: 'POST',
    body: JSON.stringify({ name, trigger_type: trigger, steps })
  });
  if (r && r.id) {
    toast(`✓ Workflow "${name}" created`);
    closeModal('wf-modal');
    document.getElementById('wf-name').value = '';
    document.getElementById('wf-steps').value = '';
    loadWsWorkflows(selectedWorkspaceId);
  } else toast('✗ Failed to create workflow');
}

// === CREDENTIALS ===
async function loadCredentials() {
  const data = await api('/api/credentials');
  const el = document.getElementById('cred-list');
  if (!data || !data.length) {
    el.innerHTML = `<div class="card empty-state">
      <div class="empty-icon">◆</div>
      <div class="empty-title">No credentials stored</div>
      <div class="empty-sub">Add API keys, OAuth tokens, and webhooks for your agents</div>
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
      </div>
      <div style="display:flex;align-items:center;gap:8px;flex-shrink:0">
        <span class="badge badge-green">Stored</span>
        <button class="btn btn-danger btn-sm"
          onclick="deleteCred('${c.id}','${c.name}')">✕</button>
      </div>
    </div>`).join('');
}

async function saveCred() {
  const name    = document.getElementById('cred-name').value.trim();
  const service = document.getElementById('cred-service').value;
  const ctype   = document.getElementById('cred-type').value;
  const value   = document.getElementById('cred-value').value.trim();
  if (!name || !value) { toast('Name and value required'); return; }
  const r = await api('/api/credentials', {
    method: 'POST',
    body: JSON.stringify({ name, service, credential_type: ctype, value })
  });
  if (r && r.id) {
    toast(`✓ Credential "${name}" saved`);
    closeModal('cred-modal');
    document.getElementById('cred-name').value = '';
    document.getElementById('cred-value').value = '';
    loadCredentials();
  } else toast('✗ Failed to save credential');
}

async function deleteCred(id, name) {
  if (!confirm(`Delete credential "${name}"?`)) return;
  const r = await fetch(API + `/api/credentials/${id}`, { method: 'DELETE' });
  if (r.ok || r.status === 204) { toast('✓ Deleted'); loadCredentials(); }
  else toast('✗ Failed to delete');
}

// === BOOT ===
loadOverview();
setInterval(() => { if (currentView === 'overview') loadOverview(); }, 12000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress access log noise

    def _get_session_token(self) -> str | None:
        return get_session_from_cookie(self.headers.get("Cookie"))

    def _is_authenticated(self) -> bool:
        return is_valid_session(self._get_session_token())

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def _serve_page(self, html: str, status: int = 200) -> None:
        data = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle_auth_post(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        params = dict(urllib.parse.parse_qsl(raw))

        if self.path == "/auth/setup":
            pin = params.get("pin", "")
            confirm = params.get("confirm", "")
            if len(pin) != 4 or not pin.isdigit():
                self._serve_page(PIN_SETUP_HTML.replace("__ERROR__", "PIN must be 4 digits"), 400)
                return
            if pin != confirm:
                self._serve_page(PIN_SETUP_HTML.replace("__ERROR__", "PINs do not match"), 400)
                return
            set_pin(pin)
            token = verify_pin(pin)
            self.send_response(302)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", f"lc_session={token}; HttpOnly; SameSite=Strict; Path=/")
            self.end_headers()
            return

        if self.path == "/auth/login":
            locked, remaining = is_locked_out()
            if locked:
                page = PIN_LOGIN_HTML.replace("__ERROR__", f"Too many attempts. Wait {remaining}s.")
                self._serve_page(page, 429)
                return
            pin = params.get("pin", "")
            token = verify_pin(pin)
            if token:
                self.send_response(302)
                self.send_header("Location", "/")
                self.send_header("Set-Cookie", f"lc_session={token}; HttpOnly; SameSite=Strict; Path=/")
                self.end_headers()
            else:
                locked, remaining = is_locked_out()
                if locked:
                    msg = f"Too many failed attempts. Locked for {remaining}s."
                else:
                    msg = "Incorrect PIN. Try again."
                page = PIN_LOGIN_HTML.replace("__ERROR__", msg)
                self._serve_page(page, 401)
            return

        if self.path == "/auth/logout":
            token = self._get_session_token()
            if token:
                logout(token)
            self.send_response(302)
            self.send_header("Location", "/auth/login")
            self.send_header("Set-Cookie", "lc_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")
            self.end_headers()
            return

    def do_GET(self):
        if self.path.startswith("/proxy/"):
            if not self._is_authenticated():
                self._serve_page('{"error":"unauthorized"}', 401)
                return
            self._proxy(self.path[7:], "GET", None)
            return

        if self.path in ("/auth/login", "/auth/logout"):
            self._redirect("/")
            return

        # Auth gate
        if not is_pin_configured():
            self._serve_page(PIN_SETUP_HTML.replace("__ERROR__", ""))
            return
        if not self._is_authenticated():
            self._serve_page(PIN_LOGIN_HTML.replace("__ERROR__", ""))
            return

        self._serve_html()

    def do_POST(self):
        if self.path in ("/auth/setup", "/auth/login", "/auth/logout"):
            self._handle_auth_post()
            return

        if self.path.startswith("/proxy/"):
            if not self._is_authenticated():
                err = b'{"error":"unauthorized"}'
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(err)))
                self.end_headers()
                self.wfile.write(err)
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else None
            self._proxy(self.path[7:], "POST", body)
            return

        self.send_response(404)
        self.end_headers()

    def do_PUT(self):
        if self.path.startswith("/proxy/"):
            if not self._is_authenticated():
                self.send_response(401)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else None
            self._proxy(self.path[7:], "PUT", body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_DELETE(self):
        if self.path.startswith("/proxy/"):
            if not self._is_authenticated():
                self.send_response(401)
                self.end_headers()
                return
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
