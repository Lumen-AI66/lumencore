# LUMENCORE BUILD LOG

Canonical record of what has been built, committed, and verified in the Lumencore repo.
Updated after every completed phase. Source of truth for deployment and planning.

---

## Phase 1 — Task Control Layer
**Date:** 2026-04-01
**Commit:** 22caa7e

### What Was Built
- `Task` model (`tasks` table) with `TaskStatus` enum: `queued → running → done/failed`, `needs_input → queued`
- `approval_required` / `approval_status` fields on `Task` for risky task governance
- `execution_task_id` foreign-key link from `Task` to `ExecutionTaskRecord`
- Service layer: `services/tasks.py` — `create_task`, `get_task`, `list_tasks`, `approve_task`, `mark_task_running`, `mark_task_done`, `mark_task_failed`
- Schemas: `schemas/tasks.py` — `TaskCreateRequest`, `TaskApproveRequest`, `TaskResponse`, `TaskListResponse`
- Route: `routes/tasks.py` — 4 endpoints:
  - `POST /api/tasks` — create and optionally dispatch
  - `GET /api/tasks` — paginated list
  - `GET /api/tasks/{task_id}` — single task
  - `POST /api/tasks/{task_id}/approve` — approval gate, dispatches on approval

### Design Decision (D-059)
Task layer sits above the existing `Job` / `ExecutionTaskRecord` systems. Does not modify any existing execution paths.

---

## Phase 1.5 — Execution Integration Bridge
**Date:** 2026-04-01
**Commit:** 22caa7e

### What Was Built
- `services/task_dispatch.py` — `dispatch_task()` bridge function
  - Creates an `ExecutionTaskRecord` (via `ExecutionTaskStore`) linked to the Task
  - Marks Task as `running`, stores `execution_task_id`
  - Runs `ExecutionScheduler.process_task()` synchronously in the same session
  - Syncs result/error back to Task → `done` or `failed`
- Tasks requiring approval hold in `needs_input` state until `POST /api/tasks/{id}/approve`
- On approval, immediately dispatched via `dispatch_task()`

### Design Decision (D-060)
Thin bridge reuses proven `ExecutionTaskStore` + `ExecutionScheduler`. No new async dispatch mechanism. Synchronous by design.

---

## Phase 2 — Memory System
**Date:** 2026-04-01
**Commit:** 41c86df

### What Was Built

#### Database Models (added to `models.py`)
- `MemoryRecord` (`memory_records` table)
  - Fields: `id`, `type` (fact|preference|context|system), `key`, `content`, `metadata_json`, `source_task_id`, `created_at`, `updated_at`
  - ILIKE keyword search on `key` + `content`
- `SkillMemory` (`skill_memory` table)
  - Fields: `id`, `name` (unique), `description`, `pattern` (JSONB), `success_count`, `last_used_at`, `created_at`
- `DecisionLog` (`decision_logs` table)
  - Fields: `id`, `task_id`, `agent`, `decision`, `reasoning`, `outcome` (success|failure|unknown), `created_at`

#### Service Layer (`services/memory.py`)
- `store_memory()` — write a MemoryRecord
- `retrieve_relevant_memory()` — ILIKE search by task_type/payload keywords, returns top-N records
- `record_task_outcome()` — writes DecisionLog + extracts MemoryRecord from task result
- `list_skills()` — paginated SkillMemory list
- `list_decision_logs()` — paginated DecisionLog list, filterable by task_id

#### API Routes (`routes/memory.py`) — 4 endpoints
- `POST /api/memory` — store a memory record
- `GET /api/memory` — search/list memory records (query, type, pagination)
- `GET /api/memory/skills` — list skill memories
- `GET /api/memory/decisions` — list decision logs

#### task_dispatch.py Integration (Phase 2 hooks)
- Pre-execution: `retrieve_relevant_memory()` enriches task payload with `memory_context`
- Post-execution: `record_task_outcome()` logs decision + extracts memory
- All memory calls wrapped in `try/except` — memory failure never blocks task execution

### Design Decision (D-061)
Three-layer relational memory. ILIKE search only — no vectors, no embeddings. Designed to be extended with vector search later without schema redesign.

---

## Phase 3 — Agent Memory Integration
**Date:** 2026-04-01
**Commit:** 9271bb4

### What Was Built
- Memory hooks integrated into `agents/agent_runtime.py` → `execute_agent()`
- Three non-breaking seams:
  1. **Pre-execution**: `retrieve_relevant_memory()` called before agent loop; result injected into `task_payload["memory_context"]`
  2. **Post-success**: `record_task_outcome(..., outcome="success")` called after successful loop
  3. **Post-failure**: `record_task_outcome(..., outcome="failure")` called in exception handler
- All three hooks wrapped in `try/except` — memory subsystem failure cannot block agent execution or result delivery
- `task_dispatch.py` also carries Phase 2 memory hooks for the task-control dispatch path

### Design Decision (D-062)
Memory enrichment is injected into `task_payload["memory_context"]`. Non-breaking because agent loop and existing execution paths ignore unknown payload keys.

---

## Pre-existing System (Phases 5–27, prior sessions)

The following was built in earlier ChatGPT/Codex sessions and is present in the codebase:

| Component | Status | Location |
|---|---|---|
| Job system (phase3_jobs) | Live | `models.py`, `routes/jobs.py`, `services/jobs.py` |
| Agent registry + policy | Live | `agents/agent_registry.py`, `agents/agent_policy.py` |
| Agent runtime (execute_agent) | Live | `agents/agent_runtime.py` |
| Command run system | Live | `models.py` (CommandRun), `routes/command.py` |
| Execution task layer | Live | `execution/task_store.py`, `execution/scheduler.py` |
| Plan runs + steps | Live | `models.py`, `routes/plans.py`, `planning/` |
| Workflow runs | Live | `models.py`, `routes/workflows.py`, `workflows/` |
| Operator queue + events | Live | `routes/operator.py`, `services/operator_*.py` |
| Connector framework | Skeleton (disabled) | `connectors/` — all connectors disabled by default |
| Tool governance layer | Live | `tools/` |
| Sandbox executor | Live | `sandbox/` |
| Secret manager | Live | `secrets/` |
| Observability / system summary | Live | `services/observability.py`, `routes/system.py` |
| Docker Compose (VPS) | Ready | `lumencore/docker-compose.phase2.yml` |
| Nginx config | Ready | `vps/nginx/lumencore.conf` |
| VPS deploy scripts | Ready | `vps/deploy/` |

---

## Current Layer Status

| Layer | Status | Notes |
|---|---|---|
| Control Layer (tasks, governance) | 90% | Task API + approval gate live |
| Execution Layer (Celery, scheduler) | 90% | Proven, wired to Task dispatch |
| Memory Layer | 30% | Schema + API + hooks live; no vector search |
| Agent Layer | Skeleton | Registry + runtime exist; no autonomous planning |
| Workflow Layer | Skeleton | workflow_runs table + research_brief workflow defined |
| Experience Layer | 20% | Dashboard container exists; no real operator UI |
| Business Layer | 0% | Not started |

---

## Next Phases (in order)

1. **VPS Deploy** — verify docker-compose.phase2.yml against VPS, confirm `.env` is populated, deploy
2. **Operator Dashboard** — working UI over existing API surfaces
3. **Telegram Bot** — external input channel via `/api/input/command`
4. **Workflow Engine** — real multi-step workflows beyond research_brief skeleton
