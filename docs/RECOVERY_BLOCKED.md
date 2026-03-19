# RECOVERY_BLOCKED

Date: 2026-03-11
Status: BLOCKED: SOURCE NOT PRESENT

## Evidence Summary
- No git repository metadata exists in this workspace (`.git` not found anywhere under `C:\LUMENCORE_SYSTEM`).
- No FastAPI runtime source found (`main.py`, `FastAPI(`, `include_router`, `lifespan`, `on_startup` all absent).
- No runtime integration modules found (`policy_engine/audit_logger.py`, `services/observability.py` absent).
- Deployment uses prebuilt images only (`docker/docker-compose.vps.yml` uses `image:` refs and no `build/context` for API source).
- Connector code exists only under a partial tree: `lumencore/services/api/app/connectors`.

## Exact Missing Runtime Paths (expected by Phase 5 integration)
- `services/api/app/main.py`
- `services/api/app/policy_engine/audit_logger.py`
- `services/api/app/services/observability.py`
- API route/runtime modules containing `/api/system/execution-summary`
- Local Docker build context or Dockerfile for API runtime source

## Safe Next-Step Extraction / Sync Plan

### Option 1: Sync from VPS source tree (preferred if VPS is source-of-truth)
PowerShell:

```powershell
# 1) Pull runtime tree (read-only sync)
scp -r root@<vps-host>:/opt/lumencore/services/api C:/LUMENCORE_SYSTEM/lumencore/services/
scp root@<vps-host>:/opt/lumencore/docker-compose.phase2.yml C:/LUMENCORE_SYSTEM/lumencore/
scp root@<vps-host>:/opt/lumencore/infra/nginx/nginx.conf C:/LUMENCORE_SYSTEM/lumencore/infra/nginx/

# 2) Verify critical files arrived
Get-ChildItem C:/LUMENCORE_SYSTEM/lumencore/services/api/app/main.py
Get-ChildItem C:/LUMENCORE_SYSTEM/lumencore/services/api/app/policy_engine/audit_logger.py
Get-ChildItem C:/LUMENCORE_SYSTEM/lumencore/services/api/app/services/observability.py
```

### Option 2: Recover from running container image if source repo is unavailable
Linux shell on host with container/image access:

```bash
# Example: extract app tree from running API container
CID=$(docker ps --filter name=lumencore-api --format '{{.ID}}' | head -n1)
mkdir -p /tmp/lumencore-api-recovery
docker cp "$CID":/app /tmp/lumencore-api-recovery/

# Optional: pack and transfer to workspace
tar -C /tmp -czf lumencore-api-recovery.tgz lumencore-api-recovery
```

### Option 3: Pull correct source repository/branch
- Identify canonical repo URL and branch containing the API runtime.
- Clone into `C:\LUMENCORE_SYSTEM\lumencore` (or merge into that tree) before any Phase 5 integration wiring.

## Recovery Gate
Do not continue Phase 5 integration until the runtime files listed above exist locally and are verified.
