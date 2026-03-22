from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os

HOST = '0.0.0.0'
PORT = int(os.getenv('PORT', '8080'))

HTML = """
<!doctype html>
<html>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>Lumencore Control Center</title>
  <style>
    :root {
      --bg: #f6f3ee;
      --panel: #ffffff;
      --line: #d9d4cb;
      --text: #1d1a17;
      --muted: #6d665f;
      --accent: #0f766e;
      --warn: #9a3412;
      --danger: #b91c1c;
    }
    * { box-sizing: border-box; }
    body { margin: 0; padding: 24px; background: var(--bg); color: var(--text); font-family: Arial, sans-serif; }
    h1, h2, h3, p { margin: 0; }
    .shell { max-width: 1400px; margin: 0 auto; }
    .hero { display: flex; justify-content: space-between; gap: 16px; align-items: end; margin-bottom: 20px; }
    .hero p { color: var(--muted); margin-top: 8px; }
    .meta { display: grid; grid-template-columns: repeat(2, minmax(140px, 1fr)); gap: 10px; }
    .card, .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; }
    .card { padding: 12px; }
    .grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 16px; }
    .panel { padding: 16px; }
    .panel-header { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 12px; }
    .summary { grid-column: span 12; }
    .intake { grid-column: span 12; }
    .commands { grid-column: span 12; }
    @media (min-width: 1100px) {
      .summary { grid-column: span 5; }
      .intake { grid-column: span 7; }
      .commands { grid-column: span 12; }
    }
    .stats { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .stat strong, .meta strong { display: block; margin-top: 4px; }
    .label { color: var(--muted); font-size: 0.82rem; }
    form { display: flex; flex-wrap: wrap; gap: 10px; }
    input, select, button { font: inherit; }
    input, select { border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; background: #fff; }
    input { flex: 1 1 320px; }
    button { border: 0; border-radius: 10px; padding: 10px 14px; background: var(--accent); color: #fff; cursor: pointer; }
    button.secondary { background: #5f6b7a; }
    button.warn { background: var(--warn); }
    button.danger { background: var(--danger); }
    button[disabled] { opacity: 0.55; cursor: default; }
    .message { margin-top: 10px; color: var(--warn); }
    .response { margin-top: 10px; }
    .commands-layout { display: grid; gap: 14px; grid-template-columns: 1fr; }
    @media (min-width: 1100px) { .commands-layout { grid-template-columns: 0.95fr 1.05fr; } }
    .list { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
    .list button { width: 100%; text-align: left; background: #fff; color: var(--text); border: 1px solid var(--line); }
    .list button.active { border-color: var(--accent); background: #eef8f7; }
    .row-main, .row-meta { display: block; }
    .row-main { font-weight: 700; }
    .row-meta { margin-top: 4px; color: var(--muted); font-size: 0.85rem; }
    .detail { min-height: 420px; }
    .detail pre, .attention { white-space: pre-wrap; word-break: break-word; background: #171717; color: #f5f5f5; border-radius: 10px; padding: 12px; overflow: auto; }
    .detail pre { min-height: 280px; }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0; }
    .empty { color: var(--muted); }
  </style>
</head>
<body>
  <div class='shell'>
    <header class='hero'>
      <div>
        <h1>Lumencore Control Center</h1>
        <p>Operator summary, recent command runs, command inspection, and lifecycle actions on the live proxied control-plane.</p>
      </div>
      <div class='meta'>
        <div class='card'><span class='label'>System</span><strong id='system-health'>Loading</strong></div>
        <div class='card'><span class='label'>Queue Size</span><strong id='queue-size'>0</strong></div>
      </div>
    </header>

    <main class='grid'>
      <section class='panel summary'>
        <div class='panel-header'>
          <h2>Operator Summary</h2>
          <button id='refresh-all' type='button'>Refresh</button>
        </div>
        <div class='stats'>
          <div class='card stat'><span class='label'>Pending</span><strong id='count-pending'>0</strong></div>
          <div class='card stat'><span class='label'>Queued</span><strong id='count-queued'>0</strong></div>
          <div class='card stat'><span class='label'>Running</span><strong id='count-running'>0</strong></div>
          <div class='card stat'><span class='label'>Completed</span><strong id='count-completed'>0</strong></div>
          <div class='card stat'><span class='label'>Cancelled</span><strong id='count-cancelled'>0</strong></div>
          <div class='card stat'><span class='label'>Failed</span><strong id='count-failed'>0</strong></div>
        </div>
        <h3 style='margin:14px 0 8px'>Attention</h3>
        <pre id='attention' class='attention'>Loading...</pre>
      </section>

      <section class='panel intake'>
        <div class='panel-header'>
          <h2>Command Run</h2>
          <span class='label'>Posts to /api/command/run</span>
        </div>
        <form id='command-form'>
          <input id='command-input' name='command_text' type='text' placeholder='research execution matrix' required>
          <select id='mode-input' name='mode'>
            <option value=''>auto</option>
            <option value='workflow_job'>workflow_job</option>
          </select>
          <button id='command-submit' type='submit'>Submit</button>
        </form>
        <div id='command-error' class='message'></div>
        <div id='command-response' class='response empty'>No command submitted yet.</div>
      </section>

      <section class='panel commands'>
        <div class='panel-header'>
          <h2>Recent Command Runs</h2>
          <span class='label'>Source: /api/commands</span>
        </div>
        <div class='commands-layout'>
          <ul id='commands-list' class='list'></ul>
          <article class='detail'>
            <div class='panel-header'>
              <h3>Selected Command</h3>
              <strong id='detail-status'>None</strong>
            </div>
            <div id='detail-summary' class='label'>Select a command to inspect it.</div>
            <div id='action-bar' class='actions'></div>
            <div id='action-error' class='message'></div>
            <pre id='command-detail'>Select a command to inspect its persisted state.</pre>
          </article>
        </div>
      </section>
    </main>
  </div>

  <script>
    const endpoints = {
      systemHealth: '/api/system/health',
      operatorSummary: '/api/operator/summary',
      commands: '/api/commands?limit=20',
      commandDetail: (id) => `/api/command/${id}`,
      commandRun: '/api/command/run',
      approve: (id) => `/api/command/${id}/approve`,
      cancel: (id) => `/api/command/${id}/cancel`,
      retry: (id) => `/api/command/${id}/retry`
    };

    let selectedCommandId = null;
    let currentDetail = null;

    async function getJson(url, options) {
      const response = await fetch(url, options);
      const text = await response.text();
      const data = text ? JSON.parse(text) : null;
      if (!response.ok) {
        const message = data && data.detail ? JSON.stringify(data.detail) : `HTTP ${response.status}`;
        throw new Error(message);
      }
      return data;
    }

    function setText(id, value) {
      const node = document.getElementById(id);
      if (node) node.textContent = value ?? '-';
    }

    function pretty(value) {
      return JSON.stringify(value, null, 2);
    }

    function canApprove(item) {
      return item && item.requested_mode === 'workflow_job' && item.status === 'pending' && item.approval_status === 'required';
    }

    function canCancel(item) {
      return item && item.requested_mode === 'workflow_job' && item.status === 'pending' && item.approval_status === 'required';
    }

    function canRetry(item) {
      return item && item.requested_mode === 'workflow_job' && item.status === 'cancelled';
    }

    function renderActions(item) {
      const bar = document.getElementById('action-bar');
      bar.innerHTML = '';
      const actions = [];
      if (canApprove(item)) actions.push({ key: 'approve', label: 'Approve', className: '' });
      if (canCancel(item)) actions.push({ key: 'cancel', label: 'Cancel', className: 'warn' });
      if (canRetry(item)) actions.push({ key: 'retry', label: 'Retry', className: 'secondary' });
      if (!actions.length) {
        const empty = document.createElement('span');
        empty.className = 'empty';
        empty.textContent = 'No lifecycle actions available for this command.';
        bar.appendChild(empty);
        return;
      }
      for (const action of actions) {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = action.label;
        button.className = action.className;
        button.addEventListener('click', () => triggerAction(action.key));
        bar.appendChild(button);
      }
    }

    async function loadSummary() {
      const [health, summary] = await Promise.all([
        getJson(endpoints.systemHealth),
        getJson(endpoints.operatorSummary)
      ]);
      setText('system-health', health.status || 'unknown');
      setText('queue-size', summary.queue_size || 0);
      const counts = (summary.commands && summary.commands.counts_by_status) || {};
      setText('count-pending', counts.pending || 0);
      setText('count-queued', counts.queued || 0);
      setText('count-running', counts.running || 0);
      setText('count-completed', counts.completed || 0);
      setText('count-cancelled', counts.cancelled || 0);
      setText('count-failed', counts.failed || 0);
      document.getElementById('attention').textContent = pretty(summary.operator_attention || {});
    }

    async function selectCommand(commandId) {
      selectedCommandId = commandId;
      const item = await getJson(endpoints.commandDetail(commandId));
      currentDetail = item;
      setText('detail-status', item.status || 'unknown');
      setText('detail-summary', `${item.command_text} | ${item.execution_decision} | approval=${item.approval_status}`);
      document.getElementById('command-detail').textContent = pretty(item);
      document.getElementById('action-error').textContent = '';
      renderActions(item);
      for (const button of document.querySelectorAll('#commands-list button')) {
        button.classList.toggle('active', button.dataset.commandId === commandId);
      }
    }

    async function loadCommands(preferredId) {
      const data = await getJson(endpoints.commands);
      const list = document.getElementById('commands-list');
      list.innerHTML = '';
      for (const item of data.items || []) {
        const li = document.createElement('li');
        const button = document.createElement('button');
        button.type = 'button';
        button.dataset.commandId = item.id;
        button.innerHTML = `<span class='row-main'>${item.command_text}</span><span class='row-meta'>${item.status} | ${item.requested_mode || 'auto'} | ${item.approval_status}</span>`;
        button.addEventListener('click', () => selectCommand(item.id));
        li.appendChild(button);
        list.appendChild(li);
      }
      if (!(data.items || []).length) {
        list.innerHTML = '<li class="empty">No commands found.</li>';
        document.getElementById('command-detail').textContent = 'No commands available.';
        document.getElementById('detail-status').textContent = 'Empty';
        document.getElementById('detail-summary').textContent = 'No command selected.';
        renderActions(null);
        return;
      }
      await selectCommand(preferredId || selectedCommandId || data.items[0].id);
    }

    async function triggerAction(action) {
      if (!selectedCommandId) return;
      document.getElementById('action-error').textContent = '';
      try {
        await getJson(endpoints[action](selectedCommandId), { method: 'POST' });
        await refreshAll(selectedCommandId);
      } catch (err) {
        document.getElementById('action-error').textContent = err.message;
      }
    }

    async function submitCommand(event) {
      event.preventDefault();
      const input = document.getElementById('command-input');
      const mode = document.getElementById('mode-input');
      const error = document.getElementById('command-error');
      const response = document.getElementById('command-response');
      error.textContent = '';
      const payload = { command_text: (input.value || '').trim(), tenant_id: 'owner' };
      if (mode.value) payload.mode = mode.value;
      if (!payload.command_text) {
        error.textContent = 'command_text is required';
        return;
      }
      try {
        const result = await getJson(endpoints.commandRun, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-Lumencore-Owner-Approval': 'true'
          },
          body: JSON.stringify(payload)
        });
        response.textContent = pretty(result);
        await refreshAll(result.id);
      } catch (err) {
        error.textContent = err.message;
      }
    }

    async function refreshAll(preferredId) {
      await Promise.all([
        loadSummary(),
        loadCommands(preferredId)
      ]);
    }

    document.getElementById('command-form').addEventListener('submit', submitCommand);
    document.getElementById('refresh-all').addEventListener('click', () => refreshAll(selectedCommandId));
    window.setInterval(() => {
      if (selectedCommandId) refreshAll(selectedCommandId).catch(() => {});
    }, 7000);
    refreshAll().catch((err) => {
      document.getElementById('command-detail').textContent = `Control center load failed: ${err.message}`;
    });
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, content_type='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.end_headers()
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/health':
            self._send(200, json.dumps({'status': 'ok', 'service': 'dashboard'}))
            return

        if self.path in {'/', '/dashboard', '/agents'}:
            self._send(200, HTML, 'text/html')
            return

        self._send(404, json.dumps({'error': 'not_found'}))


if __name__ == '__main__':
    server = HTTPServer((HOST, PORT), Handler)
    print(f'Dashboard listening on {HOST}:{PORT}')
    server.serve_forever()
