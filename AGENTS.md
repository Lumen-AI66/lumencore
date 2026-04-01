# LumenCore — Agent and Memory System Reference

Last updated: 2026-04-01

---

## What Lumencore Is

Lumencore is an AI control plane — not a chatbot. It controls AI systems.
Agents plan. Tasks execute. Memory persists context across runs.

---

## Agent System

### Agent Registry (`agents/agent_registry.py`)
- Deterministic in-process registry of built-in agents
- Each agent has: `agent_key`, `agent_type`, `name`, capability metadata, runtime binding
- Registry membership is the execution authority for `agent_task` commands
- Synthetic/internal rows (e.g. `runtime.core`) exist for compatibility but are not registry-backed execution targets

### Agent Runtime (`agents/agent_runtime.py`)
Entry point: `execute_agent(session, task, tenant_id, project_id, command_id)`

Execution flow:
1. Resolve registry definition for agent_type
2. **Pre-execution**: retrieve relevant memory → inject into `task_payload["memory_context"]`
3. Validate agent policy (approval, capabilities, owner-only)
4. Create `AgentRun` record + state store entries
5. Run agent loop via `run_agent()` with governed tool steps through `ToolMediationService`
6. **Post-execution**: `record_task_outcome()` — success or failure path
7. Return structured result envelope

Supported built-in task types: `agent.ping`, `agent.echo`

### Agent Policy (`agents/agent_policy.py`)
- `validate_agent_policy()` checks: execution allowed, task type allowed, owner-only, max runtime
- Policy stored in `agent_policies` table per agent

### Agent Loop (`agents/agent_loop.py`)
- Deterministic step-based execution
- Each step selects one governed tool and executes through `ToolMediationService`
- Step limit enforced — no unbounded loops

### State Persistence
Three tables track runtime state:
- `agent_run_state` — run-level status, current step, last decision, retry count
- `agent_task_state` — task-level input/output summaries
- `agent_state_events` — append-only event log per run

---

## Memory System (Phase 2)

### Three-Layer Architecture

#### Layer 1: MemoryRecord (`memory_records` table)
General-purpose fact/preference/context/system storage.
- `type`: `fact` | `preference` | `context` | `system`
- `key`: searchable identifier
- `content`: text content (up to free-form)
- `source_task_id`: links memory to originating task
- Search: ILIKE on `key` + `content` — no vectors yet

#### Layer 2: SkillMemory (`skill_memory` table)
Learned patterns with success tracking.
- `name` (unique), `description`, `pattern` (JSONB)
- `success_count`, `last_used_at`
- Designed for future skill improvement loops

#### Layer 3: DecisionLog (`decision_logs` table)
Reasoning trace per task execution.
- `task_id`, `agent`, `decision`, `reasoning`, `outcome` (success|failure|unknown)
- Append-only audit trail of what was decided and why

### Memory Service (`services/memory.py`)
- `store_memory(session, type, key, content, ...)` — write MemoryRecord
- `retrieve_relevant_memory(session, task_context, limit=5)` — ILIKE search by task_type/payload keywords
- `record_task_outcome(session, task_id, task_type, agent, result, error, outcome)` — writes DecisionLog + extracts MemoryRecord
- `list_skills(session, limit)` — paginated SkillMemory
- `list_decision_logs(session, task_id, limit, offset)` — paginated DecisionLog

### Memory API Endpoints (`routes/memory.py`)
| Method | Path | Description |
|---|---|---|
| POST | `/api/memory` | Store a memory record |
| GET | `/api/memory` | Search/list memory (query, type, pagination) |
| GET | `/api/memory/skills` | List skill memories |
| GET | `/api/memory/decisions` | List decision logs |

---

## Memory Integration Hooks

### In `task_dispatch.py` (Task Control Layer)
- **Pre-dispatch**: `retrieve_relevant_memory()` → attached to `task_metadata["memory_context"]` for observability
- **Post-dispatch**: `record_task_outcome()` → DecisionLog + MemoryRecord extraction

### In `agent_runtime.py` (Agent Execution)
- **Pre-execution**: `retrieve_relevant_memory()` → injected into `task_payload["memory_context"]`
- **Post-success**: `record_task_outcome(..., outcome="success")`
- **Post-failure**: `record_task_outcome(..., outcome="failure")`

**Rule**: All memory hooks are wrapped in `try/except`. Memory failure NEVER blocks execution or result delivery.

---

## Task Control Layer (Phase 1)

Tasks are the operator-visible control object above Jobs and ExecutionTasks.

### Task State Machine
```
queued → running → done
queued → running → failed
needs_input → queued (on approval)
```

### Task API (`routes/tasks.py`)
| Method | Path | Description |
|---|---|---|
| POST | `/api/tasks` | Create task; dispatches immediately if no approval needed |
| GET | `/api/tasks` | List tasks (paginated) |
| GET | `/api/tasks/{id}` | Get single task |
| POST | `/api/tasks/{id}/approve` | Approve/deny; dispatches on approval |

### Execution Bridge (`services/task_dispatch.py`)
- `dispatch_task(session, task)` — bridges Task → ExecutionTaskStore → ExecutionScheduler
- Synchronous, same session, no new async infrastructure
- `execution_task_id` stored on Task for lineage

---

## Workspace Scope

- Workspace root: `C:\Users\klus_\lumencore`
- API source: `lumencore/services/api/app/`
- Docker Compose (VPS): `lumencore/docker-compose.phase2.yml`
- Deploy scripts: `vps/deploy/`
- Docs: `docs/`

## Non-Destructive Rules

- Do not delete or overwrite existing files unless explicitly requested
- Do not run destructive git commands without approval
- Use `.env.example` templates only — never commit real secrets
- All changes must be additive and bounded
- Read files before changing anything
- Stop and report after each phase
