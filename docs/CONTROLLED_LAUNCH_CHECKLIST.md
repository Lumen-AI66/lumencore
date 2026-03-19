# Controlled Launch Checklist

Use this checklist for controlled/private launch review only.

## Release Identity
- Confirm one immutable `release_id` exists.
- Confirm one `manifest_sha256` exists.
- Confirm the generated release manifest JSON path is recorded.
- Confirm the generated `.tar.gz` package path is recorded.
- Confirm the canonical deploy mode recorded in the manifest is `target_build_from_staged_release_manifest_and_package`.
- Confirm the canonical rollback mode recorded in the manifest is `target_build_from_previously_staged_release_manifest_and_package`.

## Package Completeness
- Confirm the package contains:
  - `lumencore/docker-compose.phase2.yml`
  - `lumencore/.env.example`
  - `lumencore/services/api/Dockerfile`
  - `lumencore/services/api/requirements.txt`
  - `lumencore/services/api/app/**`
- Confirm the manifest lists file hashes for all packaged files.

## Target Verification
- Verify deploy root is exactly `/opt/lumencore`.
- Verify compose path is exactly `/opt/lumencore/docker-compose.phase2.yml`.
- Verify API source root is exactly `/opt/lumencore/services/api`.
- Verify `/opt/lumencore/lumencore/services/api` does not exist.
- Verify `/opt/lumencore/.release_state/ACTIVE_RELEASE` exists after canonical deploy.
- Verify `/opt/lumencore/.release_state/PREVIOUS_RELEASE` exists after canonical deploy.
- Verify `/opt/lumencore/.env` contains:
  - `LUMENCORE_SYSTEM_PHASE=27`
  - `LUMENCORE_RELEASE_ID=<release_id>`
  - `LUMENCORE_RELEASE_MANIFEST_SHA256=<manifest_sha256>`

## Deployment Success
- Run the canonical `release_ops.py deploy` command, not an ad hoc compose command.
- Rebuild only the required services for the release scope.
- Confirm the running API exposes the expected `release_id`.
- Confirm the running API exposes the expected `phase`.

## Health Verification
- `GET /health` is treated only as public liveness if routed by the proxy.
- `GET /api/system/health` returns `status=ok`.
- `GET /api/system/execution-summary` returns `status=ok` or a truthful degraded state with exact failing component.
- `GET /api/operator/summary` uses grounded health derivation and does not overclaim healthy state.

## Scope Verification
- Confirm `/api/connectors` still shows only:
  - `search` enabled and ready
  - `git` disabled
- Confirm `/api/nodes` still shows only the local control-plane node.
- Confirm OpenClaw is not integrated.
- Confirm no additional connector path is live.

## Rollback Readiness
- Confirm one previous release manifest exists.
- Confirm one previous release package exists.
- Confirm `PREVIOUS_RELEASE` names that exact prior release or is truthfully `NONE`.
- Confirm rollback is executed through the canonical `release_ops.py rollback` command.
- Confirm rollback currently does require a target rebuild and is documented that way.
- Confirm rollback target root is the same `/opt/lumencore`.

## Launch Discipline
- Controlled/private launch may proceed only after all items above pass.
- Unrestricted public launch remains blocked until separately re-reviewed.
