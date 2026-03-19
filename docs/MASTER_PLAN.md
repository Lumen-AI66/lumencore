# MASTER_PLAN

## System Architecture
- Runtime model: Docker-first, service-oriented deployment on a VPS.
- Core domains:
  - Lumencore Dashboard (`lumencore`): user-facing operations surface.
  - OpenClaw Orchestration (`openclaw`): workflow and task coordination.
  - Infrastructure (`docker`, `vps`): compose stacks, network boundaries, deployment runtime.
  - AI Integration (`claude`): provider integration behind an internal abstraction layer.
  - Automation (`scripts`): deploy, rollback, health checks, migration support.

## Milestones

### M1: Lumencore Dashboard Stabilization (First Operational Priority)
- Define runtime dependencies and environment templates.
- Establish health endpoint expectations.
- Ensure deterministic local and VPS startup path.
- Add baseline observability hooks (logs + health checks).

### M2: Docker Service Architecture
- Define compose topology for dashboard/API/dependencies.
- Define service boundaries, networks, and persistent volumes.
- Add baseline startup order and readiness checks.

### M3: VPS Deployment Foundation
- Define server bootstrap, directory layout, and service supervisor strategy.
- Implement deployment script flow with migration gate.
- Implement rollback workflow and post-deploy verification.

### M4: OpenClaw Integration
- Define integration contract between Lumencore and OpenClaw.
- Add orchestration event flow and retry behavior.
- Validate failure handling and idempotency.

### M5: Claude Integration Readiness
- Introduce provider-agnostic AI gateway interface.
- Define prompt/policy/versioning approach.
- Add request tracing, cost usage metrics, and safety controls.

### M6: Documentation and Operational Hardening
- Finalize architecture, runbooks, incident and recovery procedures.
- Ensure all control docs and deployment docs are synchronized.

## Acceptance Criteria

### Architecture
- Service boundaries are documented and mapped to folders.
- All runtime-sensitive config has `.example` templates.
- No production secrets are stored in repository files.

### Reliability
- Deploy path supports: deploy -> verify -> rollback.
- Health checks exist for critical services.
- Failure modes and mitigation steps are documented.

### Operations
- Implementation status and decisions are current.
- Milestones can be executed from the task runbook without ambiguity.
- VPS operations can be performed with non-destructive defaults.
