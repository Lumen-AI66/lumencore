# LumenCore Workspace Agent Rules

## Project Scope
- Workspace root: `C:\LUMENCORE_SYSTEM`
- In-scope components: `lumencore`, `openclaw`, `docker`, `vps`, `claude`, `scripts`, `docs`, and `codex`.
- Target platform: VPS-hosted Lumencore system using Dockerized services, with OpenClaw orchestration and future Claude integration.

## Operational Priorities
1. Stabilize and operationalize the Lumencore dashboard first.
2. Establish reliable Docker service architecture and service boundaries.
3. Implement VPS deployment flow with rollback and health checks.
4. Integrate OpenClaw orchestration layer.
5. Add Claude integration through a decoupled gateway layer.
6. Keep documentation current and decision-driven.

## Non-Destructive Rules
- Do not delete or overwrite existing files unless explicitly requested.
- Do not run destructive git commands (`reset --hard`, force checkout, history rewrite).
- Do not remove directories or data volumes without explicit approval.
- Create new files as placeholders before introducing runtime-sensitive changes.
- Use `.env.example` templates only; never commit real secrets or production values.

## Operating Constraints
- Prefer additive, reversible changes with small increments.
- Keep service contracts explicit (API schemas, interfaces, config templates).
- Enforce environment separation: local/dev vs VPS/prod.
- Require health checks and rollback steps for deployment changes.
- Keep architecture aligned to these domains:
  - Lumencore dashboard and API
  - OpenClaw orchestration
  - Docker runtime
  - VPS deployment operations
  - Claude integration boundary

## Change Control
- Update `docs/DECISIONS.md` for each significant technical decision.
- Update `docs/IMPLEMENTATION_STATUS.md` after each implementation session.
- Validate milestone acceptance criteria in `docs/MASTER_PLAN.md` before advancing.
- Execute tasks according to `codex/TASK_RUNBOOK.md`.
