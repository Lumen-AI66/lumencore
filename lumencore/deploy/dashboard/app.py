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
      --soft: #eef8f7;
    }
    * { box-sizing: border-box; }
    body { margin: 0; padding: 24px; background: var(--bg); color: var(--text); font-family: Arial, sans-serif; }
    h1, h2, h3, p { margin: 0; }
    button, input, select { font: inherit; }
    .shell { max-width: 1380px; margin: 0 auto; }
    .hero { display: flex; justify-content: space-between; gap: 16px; align-items: end; margin-bottom: 20px; }
    .hero p { color: var(--muted); margin-top: 8px; max-width: 760px; }
    .grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 16px; }
    .panel, .card { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; }
    .panel { padding: 16px; }
    .card { padding: 12px; }
    .panel-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; }
    .summary { grid-column: span 12; }
    .intake { grid-column: span 12; }
    .queue { grid-column: span 12; }
    .recent { grid-column: span 12; }
    @media (min-width: 1100px) {
      .summary { grid-column: span 5; }
      .intake { grid-column: span 7; }
      .queue { grid-column: span 5; }
      .recent { grid-column: span 7; }
    }
    .stats { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    @media (min-width: 900px) { .stats { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
    .label { color: var(--muted); font-size: 0.82rem; }
    .value { display: block; margin-top: 4px; font-size: 1.35rem; font-weight: 700; }
    .status-ok { color: var(--accent); }
    .status-warn { color: var(--warn); }
    .status-danger { color: var(--danger); }
    .status-emphasis { font-size: 1.2rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.04em; }
    .attention-list, .queue-list, .recent-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
    .attention-item, .queue-item, .recent-item { border: 1px solid var(--line); border-radius: 10px; padding: 12px; background: #fff; }
    .attention-item { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
    .queue-item button, .recent-item button { width: 100%; text-align: left; border: 0; background: transparent; color: inherit; padding: 0; cursor: pointer; }
    .item-title { font-weight: 700; }
    .item-meta { color: var(--muted); font-size: 0.86rem; margin-top: 4px; }
    .item-status-row { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
    .item-status { font-size: 0.88rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.04em; }
    .badge-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
    .badge { display: inline-block; padding: 4px 8px; border-radius: 999px; font-size: 0.78rem; background: #efe9e2; color: var(--text); }
    .badge.warn { background: #fff1e8; color: var(--warn); }
    .badge.ok { background: #e7f7f5; color: var(--accent); }
    .badge.danger { background: #fde8e8; color: var(--danger); }
    .columns { display: grid; gap: 12px; grid-template-columns: 1fr; }
    @media (min-width: 900px) { .columns { grid-template-columns: 1fr 1fr; } }
    form { display: flex; flex-wrap: wrap; gap: 10px; }
    input, select { border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; background: #fff; }
    input { flex: 1 1 320px; }
    button.action, button.submit { border: 0; border-radius: 10px; padding: 10px 14px; color: #fff; cursor: pointer; }
    button.submit { background: var(--accent); }
    button.secondary { background: #5f6b7a; }
    button.warn { background: var(--warn); }
    button.danger { background: var(--danger); }
    button.action[disabled] { opacity: 0.55; cursor: default; }
    .message { margin-top: 10px; color: var(--warn); }
    .response, .detail-shell { margin-top: 10px; }
    .detail-grid { display: grid; gap: 10px; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 12px 0; }
    .detail-card { border: 1px solid var(--line); border-radius: 10px; padding: 10px; background: var(--soft); }
    .detail-card strong { display: block; margin-top: 4px; }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0; }
    .error-panel { border: 1px solid #fecaca; border-radius: 12px; background: #fef2f2; padding: 14px; margin: 12px 0; color: var(--danger); }
    .error-code { display: inline-block; margin-top: 8px; font-size: 0.82rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; }
    .result-panel { border: 1px solid var(--line); border-radius: 12px; background: #fcfbf8; padding: 14px; margin: 12px 0; }
    .result-grid { display: grid; gap: 10px; grid-template-columns: repeat(2, minmax(0, 1fr)); margin-bottom: 12px; }
    .result-output-card { padding: 12px; background: #171717; border-radius: 12px; margin-top: 8px; }
    .result-output { margin: 0; background: #171717; color: #f5f5f5; }
    .empty { color: var(--muted); }
    details { margin-top: 12px; }
    pre { white-space: pre-wrap; word-break: break-word; background: #171717; color: #f5f5f5; border-radius: 10px; padding: 12px; overflow: auto; }
  </style>
</head>
<body>
  <div class='shell'>
    <header class='hero'>
      <div>
        <h1>Lumencore Control Center</h1>
        <p>Live operator cockpit for current queue state, approval attention, recent command outcomes, and bounded lifecycle actions.</p>
      </div>
      <button id='refresh-all' type='button' class='submit'>Refresh</button>
    </header>

    <main class='grid'>
      <section class='panel summary'>
        <div class='panel-header'>
          <h2>System Awareness</h2>
          <span class='label'>Primary source: /api/operator/summary</span>
        </div>
        <div class='stats'>
          <div class='card'><span class='label'>System Health</span><strong id='system-health' class='value'>Loading</strong></div>
          <div class='card'><span class='label'>Queue Size</span><strong id='queue-size' class='value'>0</strong></div>
          <div class='card'><span class='label'>Approval Required</span><strong id='approval-required' class='value'>0</strong></div>
          <div class='card'><span class='label'>Completed</span><strong id='count-completed' class='value'>0</strong></div>
          <div class='card'><span class='label'>Failed</span><strong id='count-failed' class='value'>0</strong></div>
          <div class='card'><span class='label'>Cancelled</span><strong id='count-cancelled' class='value'>0</strong></div>
        </div>
        <h3 style='margin:16px 0 10px'>Needs Attention</h3>
        <ul id='attention-list' class='attention-list'></ul>
      </section>

      <section class='panel intake'>
        <div class='panel-header'>
          <h2>Command Intake</h2>
          <span class='label'>Posts to /api/command/run</span>
        </div>
        <form id='command-form'>
          <input id='command-input' name='command_text' type='text' placeholder='research execution matrix' required>
          <select id='mode-input' name='mode'>
            <option value=''>auto</option>
            <option value='workflow_job'>workflow_job</option>
          </select>
          <button id='command-submit' type='submit' class='submit'>Submit</button>
        </form>
        <div id='command-error' class='message'></div>
        <div id='command-response' class='response empty'>No command submitted yet.</div>
      </section>

      <section class='panel queue'>
        <div class='panel-header'>
          <h2>Operator Queue</h2>
          <span class='label'>Primary source: /api/operator/queue</span>
        </div>
        <div class='columns'>
          <div>
            <h3 style='margin-bottom:10px'>Awaiting Approval</h3>
            <ul id='awaiting-list' class='queue-list'></ul>
          </div>
          <div>
            <h3 style='margin-bottom:10px'>Running</h3>
            <ul id='running-list' class='queue-list'></ul>
          </div>
        </div>
      </section>

      <section class='panel recent'>
        <div class='panel-header'>
          <h2>Recent Commands</h2>
          <span class='label'>Primary source: /api/operator/summary.recent_commands</span>
        </div>
        <ul id='recent-list' class='recent-list'></ul>
        <div class='detail-shell'>
          <div class='panel-header' style='margin-top:16px'>
            <h3>Selected Command</h3>
            <strong id='detail-status'>None</strong>
          </div>
          <div id='detail-summary' class='label'>Select a command to inspect it.</div>
          <div class='detail-grid'>
            <div class='detail-card'><span class='label'>Command</span><strong id='detail-command-text'>-</strong></div>
            <div class='detail-card'><span class='label'>Lifecycle</span><strong id='detail-lifecycle'>-</strong></div>
            <div class='detail-card'><span class='label'>Approval</span><strong id='detail-approval'>-</strong></div>
            <div class='detail-card'><span class='label'>Queue Bucket</span><strong id='detail-queue-bucket'>-</strong></div>
          </div>
          <div id='error-panel' class='error-panel' hidden>
            <div class='panel-header' style='margin-bottom:8px'>
              <h3>Error</h3>
              <span id='detail-error-code' class='error-code'>-</span>
            </div>
            <strong id='detail-error-message'>-</strong>
          </div>
          <div id='result-panel' class='result-panel'>
            <div class='panel-header'>
              <h3>AI Result</h3>
              <span id='detail-result-state' class='label'>No governed AI result for this command.</span>
            </div>
            <div class='result-grid'>
              <div class='detail-card'><span class='label'>Provider</span><strong id='detail-result-provider'>-</strong></div>
              <div class='detail-card'><span class='label'>Model</span><strong id='detail-result-model'>-</strong></div>
              <div class='detail-card'><span class='label'>Tokens Used</span><strong id='detail-result-tokens'>-</strong></div>
              <div class='detail-card'><span class='label'>Duration</span><strong id='detail-result-duration'>-</strong></div>
            </div>
            <span class='label'>Output</span>
            <div class='result-output-card'>
              <pre id='detail-result-output' class='result-output'>Select a completed AI command to inspect its output.</pre>
            </div>
          </div>
          <div id='action-bar' class='actions'></div>
          <div id='action-error' class='message'></div>
          <details>
            <summary>Raw persisted detail</summary>
            <pre id='command-detail'>Select a command to inspect its persisted state.</pre>
          </details>
        </div>
      </section>
    </main>
  </div>

  <script>
    const endpoints = {
      operatorSummary: '/api/operator/summary',
      operatorQueue: '/api/operator/queue?limit=20',
      commandDetail: (id) => `/api/command/${id}`,
      commandRun: '/api/command/run',
      approve: (id) => `/api/command/${id}/approve`,
      cancel: (id) => `/api/command/${id}/cancel`,
      retry: (id) => `/api/command/${id}/retry`
    };

    let selectedCommandId = null;
    let currentDetail = null;
    let recentCommands = [];

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

    function formatDuration(value) {
      if (value === null || value === undefined || value === '') return '-';
      const numeric = Number(value);
      if (!Number.isFinite(numeric)) return String(value);
      return `${numeric.toFixed(2)} ms`;
    }

    function formatTimestamp(value) {
      if (!value) return '-';
      const parsed = new Date(value);
      if (Number.isNaN(parsed.getTime())) return String(value);
      return parsed.toLocaleString();
    }

    function formatLifecycle(item) {
      const runtimeStatus = item.runtime_status || item.status || 'unknown';
      const startedAt = formatTimestamp(item.started_at);
      const finishedAt = formatTimestamp(item.finished_at);
      return `STATUS: ${runtimeStatus}\nLIFECYCLE: ${startedAt} -> ${finishedAt}`;
    }

    function detailSummaryText(item, agentResult) {
      return (agentResult && `${agentResult.provider || 'ai'} ${agentResult.model || ''}`.trim()) ||
        item.policy_reason ||
        item.error_message ||
        item.command_text ||
        item.command_id ||
        '-';
    }

    function setStatusEmphasis(id, value) {
      const node = document.getElementById(id);
      if (!node) return;
      const tone = statusTone(value) || 'warn';
      node.className = `status-emphasis status-${tone}`;
      node.textContent = value || '-';
    }

    function statusTone(value) {
      const lower = String(value || '').toLowerCase();
      if (lower === 'ok' || lower === 'completed' || lower === 'approved') return 'ok';
      if (lower === 'failed' || lower === 'denied') return 'danger';
      if (lower === 'required' || lower === 'pending' || lower === 'queued' || lower === 'running' || lower === 'cancelled') return 'warn';
      return '';
    }

    function badge(label, tone) {
      return `<span class="badge ${tone || ''}">${label}</span>`;
    }

    function renderAttention(summary) {
      const list = document.getElementById('attention-list');
      list.innerHTML = '';
      const buckets = (((summary || {}).operator_attention || {}).state_summary || {}).by_bucket || {};
      const entries = Object.entries(buckets).filter(([, count]) => count > 0);
      if (!entries.length) {
        list.innerHTML = '<li class="empty">No current operator attention items.</li>';
        return;
      }
      for (const [bucket, count] of entries) {
        const li = document.createElement('li');
        li.className = 'attention-item';
        li.innerHTML = `<span>${bucket.replaceAll('_', ' ')}</span><strong>${count}</strong>`;
        list.appendChild(li);
      }
    }

    function renderQueueList(id, items, emptyText) {
      const list = document.getElementById(id);
      list.innerHTML = '';
      if (!items.length) {
        list.innerHTML = `<li class="empty">${emptyText}</li>`;
        return;
      }
      for (const item of items) {
        const li = document.createElement('li');
        li.className = 'queue-item';
        const button = document.createElement('button');
        button.type = 'button';
        const status = item.runtime_status || item.status || 'unknown';
        button.innerHTML = `
          <div class='item-status-row'>
            <div class='item-title'>${item.command_text || item.command_id}</div>
            <span class='item-status status-${statusTone(status) || 'warn'}'>${status}</span>
          </div>
          <div class='item-meta'>approval=${item.approval_status || '-'} | ${item.requested_mode || 'auto'}</div>
          <div class='badge-row'>
            ${badge(item.queue_bucket || 'active', 'warn')}
            ${badge(item.execution_decision || 'unknown', '')}
          </div>
        `;
        button.addEventListener('click', () => selectCommand(item.command_id));
        li.appendChild(button);
        list.appendChild(li);
      }
    }

    function renderRecent(summary) {
      recentCommands = (summary && summary.recent_commands) || [];
      const list = document.getElementById('recent-list');
      list.innerHTML = '';
      if (!recentCommands.length) {
        list.innerHTML = '<li class="empty">No recent commands available.</li>';
        return;
      }
      for (const item of recentCommands) {
        const li = document.createElement('li');
        li.className = 'recent-item';
        const button = document.createElement('button');
        const status = item.runtime_status || item.status || 'unknown';
        const approval = item.approval_status || 'not_required';
        const summaryText = item.policy_reason || item.error_code || item.queue_bucket || item.execution_decision || 'no additional context';
        button.innerHTML = `
          <div class='item-status-row'>
            <div class='item-title'>${item.command_text || item.command_id}</div>
            <span class='item-status status-${statusTone(status) || 'warn'}'>${status}</span>
          </div>
          <div class='item-meta'>${status} | approval=${approval} | ${summaryText}</div>
          <div class='badge-row'>
            ${badge(status, statusTone(status))}
            ${badge(approval, statusTone(approval))}
            ${item.queue_bucket ? badge(item.queue_bucket, 'warn') : ''}
          </div>
        `;
        button.addEventListener('click', () => selectCommand(item.command_id));
        li.appendChild(button);
        list.appendChild(li);
      }
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
      if (canApprove(item)) actions.push({ key: 'approve', label: 'Approve', className: 'action submit' });
      if (canCancel(item)) actions.push({ key: 'cancel', label: 'Cancel', className: 'action warn' });
      if (canRetry(item)) actions.push({ key: 'retry', label: 'Retry', className: 'action secondary' });
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

    function renderAgentResult(item) {
      const agentResult = (((item || {}).result_summary) || {}).agent_result || null;
      const state = document.getElementById('detail-result-state');
      const output = document.getElementById('detail-result-output');
      if (!agentResult) {
        state.textContent = 'No AI result available.';
        setText('detail-result-provider', '-');
        setText('detail-result-model', '-');
        setText('detail-result-tokens', '-');
        setText('detail-result-duration', '-');
        output.textContent = 'No AI result available for this command.';
        return;
      }
      state.textContent = 'Governed AI result loaded from CommandRun.result_summary.agent_result.';
      setText('detail-result-provider', agentResult.provider || '-');
      setText('detail-result-model', agentResult.model || '-');
      setText('detail-result-tokens', agentResult.tokens_used ?? '-');
      setText('detail-result-duration', formatDuration(agentResult.duration_ms));
      output.textContent = agentResult.output_text || 'No output_text returned.';
    }

    function renderErrorState(item) {
      const panel = document.getElementById('error-panel');
      const resultSummary = (item && item.result_summary) || {};
      const runtimeStatus = String(item.runtime_status || item.status || '').toLowerCase();
      const executionTaskStatus = String(resultSummary.execution_task_status || '').toLowerCase();
      let errorMessage = resultSummary.error || resultSummary.job_error || resultSummary.error_message || item.error_message || '';
      let errorCode = resultSummary.error_code || item.error_code || '';
      if (!errorMessage && executionTaskStatus === 'failed') {
        errorMessage = 'Execution failed before returning a complete AI result.';
        errorCode = errorCode || 'execution_failed';
      } else if (!errorMessage && runtimeStatus === 'failed') {
        errorMessage = 'Command failed before completion.';
        errorCode = errorCode || 'command_failed';
      } else if (!errorMessage && runtimeStatus === 'denied') {
        errorMessage = item.policy_reason || 'Command was denied by current policy.';
        errorCode = errorCode || 'command_denied';
      }
      if (!errorMessage && !errorCode) {
        panel.hidden = true;
        setText('detail-error-code', '-');
        setText('detail-error-message', '-');
        return;
      }
      panel.hidden = false;
      setText('detail-error-code', errorCode || '-');
      setText('detail-error-message', errorMessage || 'Unknown error');
    }

    async function loadOperatorSurface() {
      const [summary, queue] = await Promise.all([
        getJson(endpoints.operatorSummary),
        getJson(endpoints.operatorQueue)
      ]);
      const counts = (summary.commands && summary.commands.counts_by_status) || {};
      setText('system-health', summary.system_health || 'unknown');
      document.getElementById('system-health').className = `value status-${statusTone(summary.system_health) || 'warn'}`;
      setText('queue-size', summary.queue_size || 0);
      setText('approval-required', (summary.commands && summary.commands.approval_required_total) || 0);
      setText('count-completed', counts.completed || 0);
      setText('count-failed', counts.failed || 0);
      setText('count-cancelled', counts.cancelled || 0);
      renderAttention(summary);
      renderQueueList('awaiting-list', queue.queued_commands || [], 'No commands are awaiting approval.');
      renderQueueList('running-list', queue.running_commands || [], 'No commands are currently running.');
      renderRecent(summary);
      return { summary, queue };
    }

    async function selectCommand(commandId) {
      selectedCommandId = commandId;
      const item = await getJson(endpoints.commandDetail(commandId));
      currentDetail = item;
      const agentResult = (((item || {}).result_summary) || {}).agent_result || null;
      const approval = `${item.approval_status || '-'} | required=${item.approval_required ? 'true' : 'false'}`;
      setStatusEmphasis('detail-status', item.runtime_status || item.status || 'unknown');
      setText('detail-summary', detailSummaryText(item, agentResult));
      setText('detail-command-text', item.command_text || item.command_id || '-');
      setText('detail-lifecycle', formatLifecycle(item));
      setText('detail-approval', approval);
      setText('detail-queue-bucket', item.queue_bucket || 'none');
      renderErrorState(item);
      renderAgentResult(item);
      document.getElementById('command-detail').textContent = pretty(item);
      document.getElementById('action-error').textContent = '';
      renderActions(item);
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
      await loadOperatorSurface();
      const targetId = preferredId || selectedCommandId || (recentCommands[0] && recentCommands[0].command_id);
      if (targetId) {
        await selectCommand(targetId);
      } else {
        renderActions(null);
      }
    }

    document.getElementById('command-form').addEventListener('submit', submitCommand);
    document.getElementById('refresh-all').addEventListener('click', () => refreshAll(selectedCommandId));
    window.setInterval(() => {
      refreshAll(selectedCommandId).catch(() => {});
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


