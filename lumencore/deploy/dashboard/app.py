from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os

HOST = '0.0.0.0'
PORT = int(os.getenv('PORT', '8080'))


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
            html = """
            <!doctype html>
            <html>
            <head>
              <meta charset='utf-8'>
              <title>Lumencore Dashboard</title>
              <style>
                body { font-family: Arial, sans-serif; margin: 24px; }
                .card { border: 1px solid #ddd; padding: 12px; margin-bottom: 12px; border-radius: 8px; }
                h1,h2 { margin: 0 0 8px 0; }
                pre { white-space: pre-wrap; word-break: break-word; }
                input[type=text] { width: 100%; max-width: 560px; padding: 8px; }
                button { padding: 8px 12px; margin-top: 8px; }
              </style>
            </head>
            <body>
              <h1>Lumencore Dashboard</h1>
              <p>Phase 4B command layer active with bounded deterministic commands.</p>

              <div class='card'>
                <h2>Commands Panel</h2>
                <input id='cmdInput' type='text' placeholder='e.g. ping agent / echo hello / show system status'>
                <br>
                <button onclick='runCommand()'>Run Command</button>
                <div id='cmdResult'>idle</div>
              </div>

              <div class='card'>
                <h2>Recent Commands</h2>
                <div id='cmdHistory'>loading...</div>
              </div>

              <div class='card'>
                <h2>Agents Panel</h2>
                <div id='agents'>loading...</div>
              </div>

              <div class='card'>
                <h2>Agent Status</h2>
                <div id='status'>loading...</div>
              </div>

              <div class='card'>
                <h2>Run History (Recent Agent Jobs)</h2>
                <div id='history'>loading...</div>
              </div>

              <script>
                async function loadJson(path, options) {
                  const res = await fetch(path, options || { headers: { 'Accept': 'application/json' } });
                  if (!res.ok) throw new Error(path + ' -> HTTP ' + res.status);
                  return res.json();
                }

                async function runCommand() {
                  const val = (document.getElementById('cmdInput').value || '').trim();
                  if (!val) {
                    document.getElementById('cmdResult').innerHTML = '<pre>command is required</pre>';
                    return;
                  }
                  try {
                    const data = await loadJson('/api/command/run', {
                      method: 'POST',
                      headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        'X-Lumencore-Owner-Approval': 'true'
                      },
                      body: JSON.stringify({ command_text: val, tenant_id: 'owner' })
                    });
                    document.getElementById('cmdResult').innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
                    await render();
                  } catch (err) {
                    document.getElementById('cmdResult').innerHTML = '<pre>' + String(err) + '</pre>';
                  }
                }

                async function render() {
                  try {
                    const [agents, statusData, recentJobs, history] = await Promise.all([
                      loadJson('/api/agents/list'),
                      loadJson('/api/agents/status'),
                      loadJson('/api/jobs/recent?limit=20'),
                      loadJson('/api/commands?limit=10')
                    ]);

                    document.getElementById('agents').innerHTML = '<pre>' + JSON.stringify(agents, null, 2) + '</pre>';
                    document.getElementById('status').innerHTML = '<pre>' + JSON.stringify(statusData, null, 2) + '</pre>';
                    const agentJobs = (recentJobs.items || []).filter(j => j.job_type === 'agent_task');
                    document.getElementById('history').innerHTML = '<pre>' + JSON.stringify(agentJobs, null, 2) + '</pre>';
                    document.getElementById('cmdHistory').innerHTML = '<pre>' + JSON.stringify(history, null, 2) + '</pre>';
                  } catch (err) {
                    const msg = '<pre>' + String(err) + '</pre>';
                    document.getElementById('agents').innerHTML = msg;
                    document.getElementById('status').innerHTML = msg;
                    document.getElementById('history').innerHTML = msg;
                    document.getElementById('cmdHistory').innerHTML = msg;
                  }
                }

                render();
              </script>
            </body>
            </html>
            """
            self._send(200, html, 'text/html')
            return

        self._send(404, json.dumps({'error': 'not_found'}))


if __name__ == '__main__':
    server = HTTPServer((HOST, PORT), Handler)
    print(f'Dashboard listening on {HOST}:{PORT}')
    server.serve_forever()
