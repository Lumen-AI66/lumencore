# LUMENCORE — FULL LOCAL STACK LAUNCH SCRIPT
# Paste this entire block into Claude Code terminal and let it run autonomously.
# Claude Code will execute every step, verify each result, fix errors if found, then commit to GitHub.

---

## CLAUDE CODE EXECUTION PROMPT (copy everything below this line)

---

You are operating inside the Lumencore project at C:\Users\klus_\lumencore.

Your job: execute the complete local stack launch from A to Z — build, start, verify, smoke test, commit to GitHub, verify VPS. Work autonomously. One step at a time. Wait for output. Analyze. Proceed or fix. Never skip a verification.

Follow this exact sequence. Stop immediately and fix any error before continuing.

---

### WHAT IS ALREADY DONE (do not redo these):
- `lumencore/services/api/app/agents/agent_loop.py` — enum bug already fixed (is → ==), verified
- `lumencore/docker-compose.local.yml` — already created and compose config validated
- `.env.local` — already created at repo root (gitignored)
- `lumencore/opt/lumencore/.env` — stub file already created

---

### STEP 1 — Verify prerequisites

Run these checks. If any fails, stop and report what is missing:

```bash
docker info
```
Expected: Docker daemon info printed (no error). If Docker is not running → stop and tell the user to start Docker Desktop.

```bash
cd C:\Users\klus_\lumencore && git status
```
Expected: on branch main, clean or with only the files we modified.

```bash
type C:\Users\klus_\lumencore\.env.local | findstr OPENAI
```
Expected: line containing `LUMENCORE_OPENAI_API_KEY=sk-` with a real key.
If value is still `sk-PASTE_YOUR_OPENAI_KEY_HERE` → STOP. Tell the user: "Please open C:\Users\klus_\lumencore\.env.local and replace sk-PASTE_YOUR_OPENAI_KEY_HERE with your actual OpenAI API key, then tell me to continue."

---

### STEP 2 — Validate compose config

```bash
cd C:\Users\klus_\lumencore && docker compose -f lumencore/docker-compose.phase2.yml -f lumencore/docker-compose.local.yml --env-file .env.local config --quiet
```
Expected: exits 0, output "COMPOSE CONFIG OK" or empty (no errors).
If error → read the error, fix the relevant file, revalidate before continuing.

---

### STEP 3 — Build all Docker images

```bash
cd C:\Users\klus_\lumencore && docker compose -f lumencore/docker-compose.phase2.yml -f lumencore/docker-compose.local.yml --env-file .env.local build --no-cache 2>&1
```
Expected: all 3 images built successfully (lumencore-api, lumencore-worker/scheduler use same image, lumencore-dashboard).
Watch for: pip install errors, COPY failures, syntax errors in Python files.
If any image fails to build → read the error, fix the root cause, rebuild that specific service, then continue.

---

### STEP 4 — Start the full stack

```bash
cd C:\Users\klus_\lumencore && docker compose -f lumencore/docker-compose.phase2.yml -f lumencore/docker-compose.local.yml --env-file .env.local up -d
```
Expected: 7 containers started: lumencore-postgres, lumencore-redis, lumencore-api, lumencore-worker, lumencore-scheduler, lumencore-dashboard, lumencore-proxy.

---

### STEP 5 — Wait for healthchecks

```bash
timeout /t 35 /nobreak > nul && docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```
Expected: all 7 containers show `Up (healthy)`.
If any container shows `unhealthy` or `restarting` → run:
```bash
docker logs <container-name> --tail 50
```
Read the logs, identify the error, fix it (edit the relevant Python file if needed, or fix environment variable), then restart that container:
```bash
cd C:\Users\klus_\lumencore && docker compose -f lumencore/docker-compose.phase2.yml -f lumencore/docker-compose.local.yml --env-file .env.local restart <service-name>
```
Wait 20 seconds, re-check `docker ps`. Only continue when all 7 are healthy.

---

### STEP 6 — Verify API health (direct on port 8000)

```bash
curl -s http://localhost:8000/health
```
Expected: `{"status":"ok","service":"lumencore-api",...}`

If connection refused → check if lumencore-api is running. Check logs. Fix and retry.

---

### STEP 7 — Verify full system health via proxy (port 80)

```bash
curl -s http://localhost/api/system/health
```
Expected: JSON with `"status":"ok"` and all 4 components healthy:
- `"database":{"ok":true}`
- `"redis":{"ok":true}`
- `"worker":{"ok":true}`
- `"scheduler":{"ok":true, "last_heartbeat_at":"..."}`

If proxy returns 502/connection refused → check lumencore-proxy logs:
```bash
docker logs lumencore-proxy --tail 30
```

---

### STEP 8 — Verify database schema (28 tables)

```bash
docker exec lumencore-postgres psql -U lumencore -d lumencore -c "\dt public.*" 2>&1
```
Expected: list of 28 tables including: tasks, memory_records, skill_memory, decision_logs, agents, agent_runs, command_runs, execution_tasks, plan_runs, plan_steps, workflow_runs.

If fewer tables → the DB schema was not initialized. Check API logs:
```bash
docker logs lumencore-api --tail 50
```
Look for errors in `init_db()`. Fix and restart API.

---

### STEP 9 — Verify agent registry

```bash
curl -s http://localhost/api/agents/registry
```
Expected: JSON array with 3 agents: research-agent, automation-agent, analysis-agent.

---

### STEP 10 — Smoke test: send a command to the research agent

```bash
curl -s -X POST http://localhost/api/input/command -H "Content-Type: application/json" -d "{\"input_text\": \"research what makes a great AI agent architecture\"}"
```
Expected: 202 response with a `command_id`. Note the command_id value.

Wait 10 seconds for async execution:
```bash
timeout /t 10 /nobreak > nul
```

Check the command result (replace COMMAND_ID with actual value from previous response):
```bash
curl -s http://localhost/api/commands?limit=1
```
Expected: command with status `completed` or `running`.

Check agent runs:
```bash
curl -s http://localhost/api/agent-runs?limit=1
```
Expected: at least 1 agent run record.

Check memory was stored:
```bash
curl -s "http://localhost/api/memory?limit=5"
```
Expected: memory records array (may be empty if agent did not produce memory yet — that is acceptable).

---

### STEP 11 — Verify dashboard in browser

```bash
start http://localhost
```
The dashboard should open in the browser at http://localhost.
Also open the direct dashboard port:
```bash
start http://localhost:8080
```

Verify the proxy health endpoint:
```bash
curl -s http://localhost/healthz
```
Expected: `ok`

---

### STEP 12 — Final container status report

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```
Print the full output. All 7 containers must be `Up (healthy)` before proceeding to commit.

---

### STEP 13 — Safety check before commit

```bash
cd C:\Users\klus_\lumencore && git diff --name-only
```
Check what files were changed. Expected changed files:
- `lumencore/services/api/app/agents/agent_loop.py` (bug fix)

```bash
git status
```
Expected new (untracked) files:
- `lumencore/docker-compose.local.yml`
- `.gitignore` (modified)

Verify NO secrets are staged:
```bash
git diff lumencore/services/api/app/agents/agent_loop.py
```
Should only show 3 lines changed (is → ==). Nothing else.

Verify .env.local is gitignored:
```bash
git check-ignore -v .env.local
```
Expected: `.gitignore:2:.env.*	.env.local`

Verify lumencore/opt/ is gitignored:
```bash
git check-ignore -v lumencore/opt/lumencore/.env
```
Expected: line showing it is gitignored.

---

### STEP 14 — Commit to GitHub

Stage only specific safe files:
```bash
cd C:\Users\klus_\lumencore && git add lumencore/services/api/app/agents/agent_loop.py
git add lumencore/docker-compose.local.yml
git add .gitignore
```

Final check — confirm nothing sensitive is staged:
```bash
git diff --cached --stat
```
Expected: only 3 files, no .env files, no secrets.

Commit:
```bash
git commit -m "fix(agent): correct enum comparison + add local dev compose override

- Fix ToolResultStatus enum comparison: use == instead of is in _derive_status()
  (agent_loop.py lines 31-35) — ensures correct timeout/failed/denied status
  reporting for all agent executions
- Add lumencore/docker-compose.local.yml: laptop development override that
  replaces all VPS absolute paths (/opt/lumencore/) with relative paths,
  sets networks to external:false for auto-creation, exposes ports 8000/8080
- Update .gitignore: add lumencore/opt/ stub directory used for local path resolution

Tested: full 7-container stack healthy on local laptop, smoke test passed.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

Push:
```bash
git push origin main
```
Expected: push succeeds, shows branch main → origin/main.

---

### STEP 15 — Verify VPS is still healthy after push

```bash
ssh root@187.77.172.140 "curl -s http://187.77.172.140/api/system/health"
```
Expected: same healthy JSON response as before. The VPS uses docker-compose.phase2.yml WITHOUT the local override — it is unaffected by our changes.

If VPS shows any degradation → investigate immediately before declaring success.

---

### STEP 16 — Final success report

Print a summary table:

| Service | Local Status | VPS Status |
|---------|-------------|------------|
| lumencore-api | ✅ healthy | ✅ healthy |
| lumencore-worker | ✅ healthy | ✅ healthy |
| lumencore-scheduler | ✅ healthy | ✅ healthy |
| lumencore-dashboard | ✅ healthy | ✅ healthy |
| lumencore-proxy | ✅ healthy | ✅ healthy |
| lumencore-postgres | ✅ healthy | ✅ healthy |
| lumencore-redis | ✅ healthy | ✅ healthy |

**URLs live on laptop:**
- Dashboard: http://localhost
- Dashboard direct: http://localhost:8080
- API health: http://localhost:8000/health
- System health: http://localhost/api/system/health
- Send command: POST http://localhost/api/input/command

**GitHub:** commit pushed to main, VPS unaffected.

---

### ERROR RECOVERY RULES (apply if anything fails)

1. **Container unhealthy** → `docker logs <name> --tail 50` → read error → fix Python file or env var → `docker compose restart <service>`
2. **Port 80 not working** → check lumencore-proxy logs → check nginx config at `vps/nginx/lumencore.conf`
3. **DB connection error** → check POSTGRES_PASSWORD matches in .env.local → restart api
4. **Redis connection error** → check REDIS_PASSWORD matches → restart api + worker
5. **OpenAI tool fails** → check LUMENCORE_OPENAI_API_KEY is set correctly in .env.local
6. **Build fails** → read exact error → if Python syntax: fix file + `python -m py_compile` → rebuild
7. **Git push rejected** → `git pull origin main --rebase` then push again
8. **VPS degraded after push** → the new files don't affect VPS (no path changes to phase2.yml) → check if VPS had a separate issue unrelated to push

---

## END OF SCRIPT
