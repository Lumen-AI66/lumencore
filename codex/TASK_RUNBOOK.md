# TASK_RUNBOOK

## Execution Model
- Work milestone by milestone.
- Do not advance to the next milestone until exit criteria are met.
- Keep all changes non-destructive and reversible.
- Update `docs/IMPLEMENTATION_STATUS.md` and `docs/DECISIONS.md` at each milestone boundary.

## VPS Patch Safety
- Do not patch repo files on the VPS with inline substring replacement scripts.
- Apply VPS code changes as full-file writes only.
- Preferred method:
  - `cat <<'EOF' | python3 /opt/lumencore/codex/write_full_file.py /absolute/path/to/file.py --py-compile`
  - file contents
  - `EOF`
- After each write, re-read the file and run `python3 -m py_compile` for Python targets before rebuilding or restarting anything.

## Milestone Runbook

### Milestone 1: Lumencore Dashboard Stabilization
- Inputs:
  - Current `lumencore` workspace state
  - Environment variable requirements
- Actions:
  - Establish folder and config hygiene for dashboard runtime.
  - Add `.env.example` and startup contract docs.
  - Define health and readiness checks.
- Exit Criteria:
  - Dashboard can be started consistently in defined environment.
  - Health checks and required runtime configs are documented.

### Milestone 2: Docker Service Structure
- Inputs:
  - Service inventory and dependencies
- Actions:
  - Create compose base and environment-specific overlays.
  - Define networks, volumes, and service dependencies.
  - Add service health check definitions.
- Exit Criteria:
  - Services can boot via compose with predictable ordering.
  - Core services are isolated by explicit network boundaries.

### Milestone 3: VPS Deployment Flow
- Inputs:
  - Target VPS constraints and deployment strategy
- Actions:
  - Define provisioning and hardening checklist.
  - Implement deployment, verification, and rollback scripts.
  - Define release tagging and artifact flow.
- Exit Criteria:
  - Deployment flow is executable end-to-end with rollback path.
  - Post-deploy verification steps are documented and scriptable.

### Milestone 4: OpenClaw Integration
- Inputs:
  - Orchestration requirements and event contracts
- Actions:
  - Define API/event interface between Lumencore and OpenClaw.
  - Implement retry/idempotency guidance.
  - Add integration test scenarios.
- Exit Criteria:
  - Orchestration flows are contract-defined and testable.
  - Failure handling behavior is explicitly documented.

### Milestone 5: Claude Integration Layer
- Inputs:
  - AI use cases and governance constraints
- Actions:
  - Introduce internal AI gateway contract.
  - Add provider adapter scaffolding for Claude.
  - Define prompt/version/policy management.
- Exit Criteria:
  - Claude integration is abstracted behind internal interfaces.
  - Safety, logging, and usage tracking requirements are documented.

### Milestone 6: Operational Hardening and Documentation
- Inputs:
  - Implementation outputs from Milestones 1-5
- Actions:
  - Reconcile architecture docs and runbooks with actual code.
  - Add incident, backup, and restore procedures.
  - Validate acceptance criteria from `docs/MASTER_PLAN.md`.
- Exit Criteria:
  - Control documents are current and coherent.
  - System is operationally documented for safe continuation.

## Safety Rules for Every Task
- Never overwrite existing files without explicit approval.
- Never commit secrets or production credentials.
- Never perform destructive cleanup unless explicitly requested.
- Prefer staged changes with verifiable checkpoints.
