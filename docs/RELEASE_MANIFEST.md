# Release Manifest

Date: 2026-03-17
Scope: release-ops tightening for controlled launch review
Phase label: 27

## Canonical Release Sources
- Runtime compose source: `C:\LUMENCORE_SYSTEM\lumencore\docker-compose.phase2.yml`
- Env schema source: `C:\LUMENCORE_SYSTEM\lumencore\.env.example`
- Release tooling source: `C:\LUMENCORE_SYSTEM\lumencore\deploy\release_ops.py`
- Release ops guide: `C:\LUMENCORE_SYSTEM\lumencore\deploy\RELEASE_OPS.md`

## Canonical Deploy Target
- Deploy root: `/opt/lumencore`
- Compose file: `/opt/lumencore/docker-compose.phase2.yml`
- Env file: `/opt/lumencore/.env`
- API source root: `/opt/lumencore/services/api`
- Release state root: `/opt/lumencore/.release_state`
- Active release file: `/opt/lumencore/.release_state/ACTIVE_RELEASE`
- Previous release file: `/opt/lumencore/.release_state/PREVIOUS_RELEASE`

## Canonical Manifest Precedence
1. Generated release manifest JSON for the exact release candidate
2. `lumencore/docker-compose.phase2.yml`
3. `lumencore/.env.example`
4. Controlled launch checklist and decision log

## Canonical Deploy And Rollback Commands
- Deploy:
  - `python /opt/lumencore/scripts/release_ops.py deploy --target-root /opt/lumencore --manifest /opt/lumencore/docs/releases/<release_id>.release-manifest.json --package /opt/lumencore/releases/<release_id>.tar.gz --health-base-url http://127.0.0.1`
- Rollback:
  - `python /opt/lumencore/scripts/release_ops.py rollback --target-root /opt/lumencore --health-base-url http://127.0.0.1`

## Canonical Release State Contract
- `ACTIVE_RELEASE` must contain the exact active `release_id`.
- `PREVIOUS_RELEASE` must contain the exact previous `release_id` used for rollback.
- `PREVIOUS_RELEASE=NONE` is the truthful value when no prior canonical rollback target exists.

## Deploy Mode Truth
- Deploy mode: `target_build_from_staged_release_manifest_and_package`
- Rollback mode: `target_build_from_previously_staged_release_manifest_and_package`
- The current system does not deploy immutable prebuilt images.
- The current system stages canonical artifacts and then rebuilds on the live target using the canonical compose file.
- Rollback is only valid when the prior release also has a staged canonical manifest and package on the live target.

## Live Now
- `/api/agents` legacy root surface
- `/api/agents/registry` truthful built-in registry
- `/api/connectors` truthful connector control plane
- `/api/nodes` truthful node control plane
- `/api/operator/*` operator oversight surfaces
- `/api/system/execution-summary` execution overview
- `/api/command/run` direct command path
- `search.web_search` as the only live external connector execution path

## Explicitly Disabled
- Git connector execution
- Remote node execution authority
- OpenClaw integration

## Deferred
- Additional connector rollout
- Remote dispatch and node execution authority
- Public launch approval
- Artifact-only immutable-image deploy mode

## Legacy Non-Canonical Deploy Artifacts
- `C:\LUMENCORE_SYSTEM\vps\deploy\*`
- `C:\LUMENCORE_SYSTEM\docker\docker-compose.vps.yml`

These remain in the repo as historical placeholders and must not be used for current controlled launch operations.
