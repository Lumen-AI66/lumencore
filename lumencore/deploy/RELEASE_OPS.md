# Lumencore Release Ops

This is the canonical release-ops path for the current Phase 27 runtime.

## Canonical Sources
- Compose file: `C:\LUMENCORE_SYSTEM\lumencore\docker-compose.phase2.yml`
- Env schema: `C:\LUMENCORE_SYSTEM\lumencore\.env.example`
- Release tooling: `C:\LUMENCORE_SYSTEM\lumencore\deploy\release_ops.py`
- Release manifest summary: `C:\LUMENCORE_SYSTEM\docs\RELEASE_MANIFEST.md`
- Controlled launch checklist: `C:\LUMENCORE_SYSTEM\docs\CONTROLLED_LAUNCH_CHECKLIST.md`

## Canonical Live Target
- Deploy root: `/opt/lumencore`
- Compose file: `/opt/lumencore/docker-compose.phase2.yml`
- Env file: `/opt/lumencore/.env`
- API source root: `/opt/lumencore/services/api`
- Release state root: `/opt/lumencore/.release_state`
- Active release file: `/opt/lumencore/.release_state/ACTIVE_RELEASE`
- Previous release file: `/opt/lumencore/.release_state/PREVIOUS_RELEASE`

## Required Release Evidence
Every controlled launch candidate must have:
- one immutable `release_id`
- one `release-manifest.json`
- one deterministic `.tar.gz` package
- one `manifest_sha256`
- one previous rollback target reference

## Canonical Release-Ops Commands
- Generate manifest only:
  - `python C:\LUMENCORE_SYSTEM\lumencore\deploy\release_ops.py manifest --release-id <release_id> --rollback-release-id <previous_release_id_or_NONE> --output <manifest_path>`
- Generate manifest and deterministic package:
  - `python C:\LUMENCORE_SYSTEM\lumencore\deploy\release_ops.py package --release-id <release_id> --rollback-release-id <previous_release_id_or_NONE> --manifest-output <manifest_path> --package-output <package_path>`
- Verify target root:
  - `python C:\LUMENCORE_SYSTEM\lumencore\deploy\release_ops.py verify-target --target-root /opt/lumencore --manifest <manifest_path>`
- Canonical deploy:
  - `python /opt/lumencore/scripts/release_ops.py deploy --target-root /opt/lumencore --manifest /opt/lumencore/docs/releases/<release_id>.release-manifest.json --package /opt/lumencore/releases/<release_id>.tar.gz --health-base-url http://127.0.0.1`
- Canonical rollback:
  - `python /opt/lumencore/scripts/release_ops.py rollback --target-root /opt/lumencore --health-base-url http://127.0.0.1`

## Canonical Release State Model
- `ACTIVE_RELEASE` contains the exact currently deployed `release_id`.
- `PREVIOUS_RELEASE` contains the exact rollback target `release_id`.
- If no prior canonical rollback target exists yet, `PREVIOUS_RELEASE` must contain `NONE`.
- These files are written only by the canonical `deploy` and `rollback` commands.

## Deploy And Rollback Mode Truth
- Deploy mode: `target_build_from_staged_release_manifest_and_package`
- Rollback mode: `target_build_from_previously_staged_release_manifest_and_package`
- Operational truth:
  - the release package and manifest are staged artifacts
  - the live deploy still rebuilds the runtime image on the target host from `/opt/lumencore/services/api`
  - rollback is not artifact-only today
  - rollback remains dependent on a previously staged canonical manifest and package for the prior release

## Required Verification
Before deploy:
- generate the manifest and package
- verify the target root against the manifest
- confirm `/opt/lumencore/lumencore/services/api` does not exist
- confirm `LUMENCORE_RELEASE_ID` and `LUMENCORE_RELEASE_MANIFEST_SHA256` are set in `/opt/lumencore/.env`
- confirm `.release_state/ACTIVE_RELEASE` and `.release_state/PREVIOUS_RELEASE` are present or truthfully absent before the first canonical deploy

After deploy:
- verify `/health` only as public liveness if it is routed by the proxy
- verify `/api/system/health`
- verify `/api/system/execution-summary`
- verify `/api/operator/summary`
- verify only `search` is enabled for external connector execution
- verify `.release_state/ACTIVE_RELEASE` matches the deployed `release_id`
- verify `.release_state/PREVIOUS_RELEASE` matches the recorded rollback target

## Legacy Note
`C:\LUMENCORE_SYSTEM\vps\deploy\*` and `C:\LUMENCORE_SYSTEM\docker\docker-compose.vps.yml` are historical placeholder artifacts and are not the canonical launch path for the current Phase 27 runtime.
