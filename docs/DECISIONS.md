# DECISIONS

## D-001: Lumencore Dashboard Is Priority One
- Date: 2026-03-08
- Decision: Stabilize and operationalize Lumencore before expanding integrations.
- Rationale: Dashboard availability is the primary system outcome and dependency for operational confidence.

## D-002: Docker-First Service Runtime
- Date: 2026-03-08
- Decision: Standardize runtime and deployment around Docker services.
- Rationale: Consistent packaging and environment parity across local, staging, and VPS deployment.

## D-003: VPS Deployment Must Support Rollback by Default
- Date: 2026-03-08
- Decision: Every deployment flow must include health verification and rollback path.
- Rationale: Reduces operational risk and downtime during iterative rollout.

## D-004: Claude Must Be Integrated Through an Internal Gateway Layer
- Date: 2026-03-08
- Decision: Use a provider abstraction boundary instead of direct service-to-provider calls.
- Rationale: Enables policy enforcement, observability, model/provider substitution, and safer scaling.

## D-005: Non-Destructive Change Policy
- Date: 2026-03-08
- Decision: Use additive changes, avoid destructive operations, and never store real secrets in repo.
- Rationale: Protects in-progress work, infrastructure state, and operational safety.

## D-006: Lumencore VPS Deployment Topology (Compose + Nginx)
- Date: 2026-03-08
- Decision: Use Nginx as the only public entrypoint and route dashboard/API to internal app services over container networks.
- Rationale: Simplifies exposure, improves service isolation, and standardizes health verification paths.

## D-007: Placeholder-Only VPS Config Policy
- Date: 2026-03-08
- Decision: Commit only placeholder VPS env/config values and require server-side .env.vps population.
- Rationale: Prevents accidental secret leakage and keeps deployment artifacts safe for version control.

## D-008: Contract-Freeze Until Runtime Artifacts Exist
- Date: 2026-03-08
- Decision: Keep VPS deployment files in placeholder mode until Lumencore runtime artifacts are available for verification.
- Rationale: Prevents encoding speculative ports/endpoints/env vars as if they were production truth.

## D-009: Claude Gateway Is Optional and Profile-Gated Until Runtime Validation
- Date: 2026-03-08
- Decision: Add Claude gateway as an optional Docker compose profile (`ai`) with contract-first artifacts and health checks.
- Rationale: Enables Milestone 5 progress without forcing unvalidated runtime dependencies into baseline deploy/rollback paths.

## Logging Rule
- Add one record per significant architecture, deployment, or integration choice.
- Include date, decision, and concise rationale.
## D-010: Phase 5 Connector Framework Is Skeleton-Only and Policy-First
- Date: 2026-03-11
- Decision: Implement connector primitives (registry, policy, audit, mock Git/Search connectors) with all connectors disabled by default and no external provider/runtime operations.
- Rationale: Establishes a safe, auditable integration boundary without altering current runtime behavior or introducing external side effects.

## D-011: Phase 5 Connector Finalization Uses Config-Driven Disabled-By-Default Policy
- Date: 2026-03-11
- Decision: Connector enablement moved to `services/api/app/config/connectors.yaml` with default `false` for all framework connectors.
- Rationale: Ensures connectors can be registered but non-executable until explicitly enabled by policy/config.

## D-012: Connector Audit Integration Is Writer-Adapter Based
- Date: 2026-03-11
- Decision: Connector execution path emits audit events via an `audit_writer` callback adapter so events can flow through the existing audit pipeline without a parallel subsystem.
- Rationale: Prevents duplicate logging systems and keeps `agent_audit_events` as the single target pipeline.

## D-013: Phase 5 Finalization Uses Runtime Startup Registration + Existing Summary Path
- Date: 2026-03-11
- Decision: Final connector integration is completed in the recovered runtime tree by wiring default connector registration in API startup and exposing connector counters through the existing `/api/system/execution-summary` response.
- Rationale: Closes Phase 5 with minimal additive changes while preserving the existing startup lifecycle, audit path, and observability endpoint contracts.

## D-014: Workspace Path Separation Is Canonical For Recovery Snapshot
- Date: 2026-03-11
- Decision: Treat `C:\LUMENCORE_SYSTEM\lumencore` as runtime root and `C:\LUMENCORE_SYSTEM\docs` as documentation root for Phase 5 recovery/finalization work.
- Rationale: The recovered workspace is split by design; forcing a single-root assumption causes false missing-file conclusions and unsafe edits.

## D-015: Phase 6 Connector Activation Uses Central Env-Secret Enforcement and Default-Deny Agent Permissions
- Date: 2026-03-12
- Decision: Activate connectors only through a centralized execution path that enforces connector enablement, per-agent per-operation permissions, required environment-based secrets, audit, and observability before execution.
- Rationale: Preserves the control-plane model, keeps connector execution governed by one enforcement layer, and prevents secret leakage or implicit authorization drift.

## D-016: External Connector Activation Remains Read-Only and Provider-Normalized
- Date: 2026-03-12
- Decision: Keep `git` limited to safe GitHub read-only operations and keep `search` as one logical connector with provider adapters for Brave, Tavily, and Exa behind a normalized result shape.
- Rationale: Enables useful external capability activation without introducing destructive operations, vendor-driven architecture, or connector-specific interface sprawl.

## D-017: Phase 6 Connector Correction Consolidates Secrets and Permissions Into Existing App Systems
- Date: 2026-03-12
- Decision: Connector env-secret handling must reuse the existing app secrets layer, and default-deny agent connector permissions must live in the existing connector YAML config instead of a standalone JSON artifact.
- Rationale: Removes architectural duplication, avoids fragile custom config parsing, and keeps connector control data in one coherent runtime config surface.

## D-018: Phase 7A Introduces a Tool Governance Layer Above Connectors
- Date: 2026-03-12
- Decision: Model tools as first-class governed execution intents above connectors, with their own typed definitions, requests, results, and registry, while keeping connectors disabled-by-default and unchanged.
- Rationale: A tool is a policy-governed capability surface, not a raw connector. This preserves fail-closed design and prepares later agent tool usage without creating direct agent-to-connector shortcuts.

## D-019: Phase 7B Enforces Tool Policy Above Connector Policy
- Date: 2026-03-12
- Decision: Tool execution intent must be validated against registered ToolDefinition objects, command context, tool enablement, agent tool permissions, and existing connector policy before any later execution layer is allowed to run.
- Rationale: This preserves the rule that tools are a governed layer above connectors and prevents agents from reaching connector capability through mismatched or partially trusted request payloads.

## D-020: Phase 7C Uses a Thin Mediation Service With an Adapter Resolver Boundary
- Date: 2026-03-12
- Decision: Tool execution intent is mediated through a dedicated service that evaluates policy before any execution attempt and dispatches only through an internal executor-resolver boundary.
- Rationale: This preserves command-bound execution, keeps adapters isolated for later phases, and gives the execution kernel a stable result envelope without introducing direct agent-to-connector or direct route-level execution paths.

## D-021: Phase 7D Formalizes Adapters as Policy-Dumb Execution Units
- Date: 2026-03-12
- Decision: Tool execution adapters live behind the mediation layer and expose a single `execute_tool(...)` contract, while mediation remains responsible for policy, context shaping, and result-envelope construction.
- Rationale: This preserves adapter isolation, keeps execution single-step, and prevents policy or orchestration concerns from leaking into concrete tool adapters.

## D-022: Phase 7E Makes Command Flow the Sole Legitimate Tool Execution Entry Path
- Date: 2026-03-12
- Decision: Tool execution intent is now constructed from command context and passed through `ToolMediationService` from the existing command runtime path rather than through any direct tool route or adapter entrypoint.
- Rationale: This preserves command-bound execution, keeps mediation as the only execution gate, and ensures future orchestration can build on one runtime primitive instead of parallel access paths.

## D-023: Command-Triggered Tool Results Preserve Denied vs Failed Semantics and Reuse Command Correlation
- Date: 2026-03-12
- Decision: Tool-mediated command execution maps `ToolResult.status` into more precise `CommandRun.status` values and reuses the `CommandRun.id` as the tool correlation lineage anchor instead of generating an unrelated correlation identifier.
- Rationale: This preserves execution meaning at the command layer and gives future orchestration, dashboards, and retries a stable lineage between command and tool envelopes without introducing a broader command model redesign.

## D-024: Phase 7F Emits Tool Audit and Metrics Only From the Mediation Layer
- Date: 2026-03-12
- Decision: Tool lifecycle audit events and tool metrics are emitted only from `ToolMediationService`, while command flow passes an audit-writer into mediation for persistence through the existing audit pipeline.
- Rationale: This keeps mediation as the single execution gate, avoids duplicating instrumentation in adapters or routes, and preserves stable semantics for future orchestration and observability layers.

## D-025: Phase 7G Activates Only system.echo Through the Command-Bound Tool Kernel
- Date: 2026-03-12
- Decision: Enable only `system.echo` in `tools.yaml` and allow only the internal `command-system` actor to invoke it through the existing command-mediated tool path.
- Rationale: Validates the governed execution kernel end-to-end with one read-only internal tool while keeping all other tools and external connectors disabled by default.


## D-026: Phase 8 Adds a Deterministic Agent Runtime Between Planning and Tool Execution
- Date: 2026-03-13
- Decision: Route Phase 8 agent-mode commands through a deterministic in-process agent runtime that selects one governed tool step and executes it only through `ToolMediationService`.
- Rationale: Establishes the execution-kernel foundation for future orchestration without introducing autonomous behavior, direct agent-to-connector calls, or a second execution path outside the existing command-bound kernel.

## D-027: Phase 9 Persists Deterministic Agent Runtime State As Structured Operational Records
- Date: 2026-03-13
- Decision: Persist Phase 9 runtime state using explicit relational records for run state, task state, and append-only state events, and integrate those transitions directly into the existing deterministic agent runtime path.
- Rationale: This adds restart-safe, auditable operational memory for control flow and recovery without introducing semantic memory, workflow engines, or a second orchestration subsystem.

## D-028: Phase 10 Adds A Deterministic Execution Task Control Plane
- Date: 2026-03-13
- Decision: Add a small persisted execution task layer that wraps existing agent runtime execution without replacing the proven command or worker paths.
- Rationale: This creates bounded task tracking, explicit status transitions, and retry-ready control-plane behavior without introducing a new queue framework or background orchestration subsystem.

## 2026-03-13 - Phase 11 deterministic plan runs
- Added a minimal planning layer on top of the Phase 10 scheduler.
- Planning remains linear, bounded, rule-based, and scheduler-backed.
- Existing direct command paths (`tool_sync`, `agent_sync`, `agent_job`) remain valid; `plan_sync` is an additive command mode for bounded multi-step execution.
- Phase 11 does not add branching workflows, dynamic replanning, background daemons, or external orchestration frameworks.

## 2026-03-13 - Phase 11 fix pass semantics hardening
- `plan_started_total` now increments only on the first pending-to-running transition of a plan run.
- Execution summary now distinguishes plan state snapshots from plan event counters more explicitly.
- Plan-to-command status mapping now preserves pending and running states explicitly.

## D-030: Phase 12 Adds Deterministic Named Workflow Runs Over Plan Runtime
- Date: 2026-03-13
- Decision: Add a narrow `workflow_runs` layer and a `workflow_sync` command path for one supported workflow (`research_brief`) that deterministically maps into the existing Phase 11 plan runtime.
- Rationale: This adds a named workflow entrypoint and persisted workflow tracking without introducing a second execution engine, background orchestration, or generalized workflow compilation.

## D-032 Phase 13 Async Workflow Wrapper
- Added one explicit additive mode: `workflow_job`.
- Scope is limited to research intent and `workflow_type=research_brief`.
- The async path reuses the existing Phase 12 workflow runtime through the existing job worker path.
- Existing direct, `plan`, and synchronous `workflow` paths remain unchanged.
- No new workflow engine, branching, parallelism, or DB tables were introduced.

## D-033 Phase 14 Read-Only Workflow Inspection
- Added read-only workflow inspection surfaces: GET /api/workflows and GET /api/workflows/{workflow_id}.
- Responses are sourced from persisted workflow_runs and include only bounded workflow state plus a thin linked plan summary.
- No execution behavior, worker behavior, scheduler behavior, or workflow runtime logic was changed for this phase.
- No mutation routes, cancel/retry/resume flows, or new tables were introduced.


## D-034 Phase 15 Read-Only Plan Inspection
- Added read-only plan inspection surfaces: GET /api/plans and GET /api/plans/{plan_id}.
- Responses are sourced from persisted plan_runs and plan_steps and expose bounded persisted plan state only.
- Plan detail includes ordered persisted steps, but no mutation, control-plane changes, or runtime behavior changes.
- No new plan engine, no execution changes, and no new tables were introduced.


## D-035 Phase 16 Read-Only Execution Task Inspection
- Added read-only execution task inspection surfaces: GET /api/execution-tasks and GET /api/execution-tasks/{task_id}.
- Responses are sourced from persisted execution_tasks and expose bounded execution task state only.
- No worker, scheduler, workflow, plan, or command execution behavior was changed for this phase.
- No mutation routes, retry controls, or new tables were introduced.


## D-036 Phase 17 Read-Only Agent Run Inspection
- Added read-only agent run inspection surfaces: GET /api/agent-runs and GET /api/agent-runs/{run_id}.
- Responses are sourced from persisted agent_runs and expose bounded execution state only.
- No direct, plan, workflow, workflow_job, worker, or scheduler execution behavior was changed for this phase.
- No mutation routes, lifecycle controls, or new tables were introduced.


## D-037 Phase 18 Read-Only Command Run Inspection
- Added read-only command run inspection surfaces: GET /api/commands and GET /api/commands/{command_id}.
- Responses are sourced from persisted command_runs and reuse existing command run list/get/update helpers.
- No direct, plan, workflow, workflow_job, worker, scheduler, or execution runtime behavior was changed for this phase.
- No mutation routes, lifecycle controls, or new tables were introduced.

## Decision D-019: Phase 19 Deterministic Execution Gate
Date: 2026-03-13

- Added a thin deterministic execution gate at the top-level command seam rather than inside worker, plan, or workflow runtimes.
- Gate decisions are fixed and code-defined only: `allowed`, `approval_required`, `denied`.
- `execution_decision` is the persistent governance classification, `approval_status` is the approval lifecycle state, and `status` remains the runtime execution state.
- Phase 19 stores gate metadata on `command_runs` so list/detail inspection and observability remain persistence-backed.
- `workflow_job` now requires explicit approval before job creation; approved commands keep `execution_decision=approval_required` and transition only `approval_status` to `approved`.
- Execution summary exposes a persistence-backed execution gate state snapshot, not a true append-only event stream.
- Added one minimal approval endpoint to release held commands into the existing job-backed workflow path.
- Deferred: richer approval workflows, RBAC, UI approval flows, cancellation, retry approval semantics, and policy editors.

## D-038 Phase 20 Narrow Lifecycle Control On Command Runs
- Added minimal lifecycle controls only on `command_runs`, the narrowest stable control-plane object already exposed by the API.
- Supported transitions are intentionally limited to truthful existing seams: `cancel` for held `workflow_job` commands awaiting approval, and `retry` for cancelled or failed `workflow_job` commands by creating a new command run.
- No pause/resume was added because the current runtime has no safe narrow seam for it without worker or scheduler refactoring.
- Lifecycle metadata is persistence-backed on `command_runs` and execution summary exposes a current state snapshot, not an append-only lifecycle event log.
- Deferred: job-level cancellation after dispatch, pause/resume, retry on sync paths, and broader object-type lifecycle control.
## D-039 Phase 21 Operator Queue Visibility
- Added a narrow operator queue visibility layer derived entirely from persisted `command_runs` state.
- Queue buckets are fixed and code-defined only: `awaiting_approval`, `retryable`, `denied`, and `failed`.
- Queue bucket precedence is explicit and stable: `awaiting_approval` -> `denied` -> `retryable` -> `failed`.
- `retryable` is reserved only for `workflow_job` commands that the current runtime can truthfully retry through the existing lifecycle seam; failed commands that are not truthfully retryable remain in `failed`.
- `denied` is terminal governance classification and is never re-labeled as `retryable`.
- The queue bucket is a derived read-model classification only; it is not persisted and does not replace `status`, `execution_decision`, or `approval_status`.
- Added one narrow read surface, `GET /api/command-queue`, with optional explicit `bucket=` filtering.
- Execution summary now exposes a persistence-backed operator queue current-state snapshot, not an event stream, SLA system, or assignment system.
- Deferred: generic command filtering, queue assignment/claiming, operator notes, bulk actions, and dashboard/UI work.


## D-040 Phase 21 Operator Control Layer
- Added a thin operator surface above the existing command runtime instead of introducing a second execution engine.
- Operator intake reuses the existing command route semantics so sync and async execution remain truthful.
- Operator queue and summaries are read-only views over existing persisted command state plus narrow runtime event counters.
- Deferred: operator assignment, bulk control, UI workflow, and runtime redesign.

## D-041 Phase 21 Operator Control Plane Finalization
- Operator intake now creates a stable queued command id before execution and dispatches through a narrow operator-only job path.
- The operator layer uses a strict derived lifecycle: queued -> running -> completed|failed.
- Queue admission is capped at 100 queued operator-visible commands and rejects overflow with HTTP 429.
- Operator observability remains runtime-backed and now records structured recent events with command_id, timestamp, and event_type.


## D-042 Phase 21.1 Persists Operator Events As The Smallest Shared Observability Layer
- Date: 2026-03-14
- Decision: Persist operator observability as append-only operator_events rows keyed by command_id instead of extending the existing runtime-local in-memory counters.
- Rationale: This closes the Phase 21 gap with the smallest safe additive change, keeps operator execution semantics unchanged, and makes STARTED/COMPLETED/FAILED visible across separate API and worker processes through existing summary/read surfaces.

## D-043 Phase 21 Final Hardening Uses One Canonical Operator Event Seam Per Lifecycle Transition
- Date: 2026-03-14
- Decision: Keep operator lifecycle event ownership at one seam per transition and ignore repeated writes for the same (command_id, event_type) in observability.
- Rationale: This preserves append-only operator events while making STARTED, COMPLETED, and FAILED deterministic and summary counts semantically exact without redesigning command execution.

## D-044 Phase 22 Agent Registry Foundation
- Added a deterministic in-process agent registry foundation instead of introducing persistence or distributed registry complexity too early.
- Built-in agents are now explicitly defined with stable agent_key, capability metadata, source, visibility, and runtime binding metadata.
- The registry remains separate from execution authority: existing command, planner, scheduler, workflow, and operator execution paths still use the current runtime seams unchanged.

## D-045: Phase 23 Single Entry Control Plane
- Date: 2026-03-18
- Decision: Keep Lumencore command ingress inside the existing API control plane only, with public traffic entering through Nginx `/api/` and internal execution entering through the existing command routes rather than standalone sidecar services or external-input daemons.
- Rationale: This preserves one auditable execution path, prevents architecture drift, and keeps future input layers behind the same policy, observability, and execution surfaces already proven on the VPS.
- Agent status is a cheap merged read model derived from explicit registry definitions plus existing persisted agent rows, with no background polling or external health checks.
- Added read-only registry surfaces: GET /api/agents, GET /api/agents/{agent_key}, and GET /api/agents/{agent_key}/status.
- Deferred: registry persistence, distributed heartbeats, plugin loading, scheduler-driven registry authority, and dynamic agent discovery.


## D-045 Phase 22 Tightening Patch Restores /api/agents Compatibility And Registry Truthfulness
- Restored the pre-Phase-22 /api/agents root contract instead of keeping the new registry snapshot on the existing route.
- Moved Phase 22 registry read surfaces to additive routes: GET /api/agents/registry, GET /api/agents/registry/{agent_key}, and GET /api/agents/registry/{agent_key}/status.
- Limited the primary registry snapshot to real BaseAgent-backed built-in agents only; synthetic internal executor rows remain seeded for runtime compatibility but are not advertised as registry-ready built-ins.
- 
eady is now only possible when a registry entry has both an explicit built-in runtime binding and a matching active or idle persisted agent row.


## D-046 Phase 23 Makes Built-In Registry Membership The Execution Authority For agent_task
- agent_task execution resolution now accepts only registry-backed built-in agents from the explicit Phase 22 registry definitions.
- Persisted non-registry rows such as the synthetic runtime.core seed remain in the system for internal compatibility, but they are not valid agent_task execution targets.
- The enforcement seam is narrow: capability validation, runtime agent selection, and final agent resolution now all require registry-backed membership for agent_task.
- Built-in registry identity is now attached to the execution path through existing JSON metadata and result surfaces instead of a broader schema redesign.


## D-047 Phase 24 Adds A Truthful Connector Control-Plane Foundation
- Added read-only connector registry surfaces under /api/connectors backed by the real in-process connector registry plus current config-backed enablement.
- Connector status now separates configured presence, administrative enablement, and narrow runtime readiness without claiming external reachability when it cannot be proven.
- Health is intentionally bounded: disabled connectors report disabled, connectors with grounded secret/runtime prerequisites can report ready, and anything unproven remains unknown or misconfigured.
- Deferred: connector activation flows, OAuth, secret mutation APIs, external side-effect execution, remote membership, and UI work.


## D-048 Phase 25 Adds A Truthful Remote Node Membership Foundation
- Added read-only node registry surfaces under /api/nodes using a narrow config-backed membership definition and bounded runtime status assembly.
- The current truthful membership set contains only the local Lumencore control-plane node; no OpenClaw integration or remote execution authority was introduced.
- Node status now separates registered presence, administrative enablement, local readiness, and heartbeat-backed truth without pretending remote readiness where no heartbeat exists.
- Deferred: remote dispatch, remote job authority, remote heartbeat write flows, OpenClaw execution integration, and broader cluster orchestration.


## D-049 Phase 26 Sharpens Operator Execution Oversight Without Expanding Execution Authority
- Extended the existing operator control surface with read-oriented command, job, and agent-run oversight routes instead of creating a second control model.
- Operator summaries now expose grounded approval, denial, queue, and execution outcome signals derived from existing command, job, and agent-run state only.
- Command detail now surfaces operator-useful execution metadata such as selected agent, registry key, execution decision, approval status, queue bucket, and policy reason where present.
- Deferred: new approval engines, new control actions, remote execution controls, and broader orchestration redesign.

## D-050 Phase 27 Adds The First Governed Search Connector Execution Path
- Activated exactly one external connector execution path: the read-only `search.web_search` tool through the existing search connector.
- The search path stays inside the current control-plane seams: command parsing, task planning, tool policy, connector policy, connector readiness, operator visibility, and execution-summary metrics.
- Search execution now requires both policy enablement and connector readiness; disabled or misconfigured search fails truthfully instead of fabricating results.
- Deferred: git execution, multi-connector rollout, remote dispatch, OpenClaw integration, and broader connector activation flows.



## D-051 Launch Hardening Pass Prioritizes Truthful Runtime Semantics Over Broader Scope
- Tool and connector execution summaries now keep request totals separate from per-dimension execution outcome buckets so operator-visible rollups do not double-count a single successful run.
- Operator command surfaces now expose both the normalized operator lifecycle state and the underlying persisted runtime status to reduce misleading flattening of denied, cancelled, and timeout outcomes.
- Operator summary health is now intentionally conservative instead of overclaiming a healthy system without a shared health derivation.
- Historical notes from earlier phases were reconciled against the current live kernel state; this pass did not expand connector scope, remote execution scope, or execution authority.

## D-052 Final Excellence Pass Sharpens Runtime Status, Lineage, And Launch Documentation
- Command execution now preserves grounded runtime outcomes such as `denied` and `timeout` instead of flattening them into `failed` in the existing operator command execution seam.
- Command and operator read surfaces now expose request-level lineage fields already present in live execution payloads: `request_id`, `run_id`, `correlation_id`, `connector_name`, and `error_code` when available.
- Existing `started_at` and `finished_at` command timestamps are now surfaced through command and operator APIs where populated, improving launch-time auditability without a schema redesign.
- Added a release manifest document that states what is live, what is disabled, what is deferred, and what the deploy scope actually is for launch review.

## D-053 Release Ops Tightening Uses One Canonical Phase 27 Deploy Contract
- Date: 2026-03-17
- Decision: Treat `lumencore/docker-compose.phase2.yml`, `lumencore/.env.example`, and `lumencore/deploy/release_ops.py` as the canonical release-ops contract for the current live runtime, and block the older placeholder `vps/deploy` path from current launch use.
- Rationale: The workspace previously contained two conflicting deploy stories, and the live system already runs from `/opt/lumencore` with a Phase 27 compose contract. Canonicalizing that path closes provenance gaps, reduces wrong-target deploy risk, and makes rollback evidence explicit.

## D-054 Canonical Release State And Rollback Entry Points Govern Controlled Launch Ops
- Date: 2026-03-17
- Decision: Treat `release_ops.py deploy` and `release_ops.py rollback` as the only canonical release execution entrypoints for the current Phase 27 runtime, with release state written to `/opt/lumencore/.release_state/ACTIVE_RELEASE` and `/opt/lumencore/.release_state/PREVIOUS_RELEASE`.
- Rationale: The prior release-ops pass established manifest, package, and target verification discipline but still left deploy execution, rollback execution, and active-versus-previous release identity partly implicit. Canonical state files and canonical deploy/rollback commands make the current live release explicit and auditable.
- Truth constraints: Deploy and rollback currently remain `target_build_*` flows that rebuild on the live target from staged canonical artifacts. Rollback is only valid when the prior release also has a staged canonical manifest and package on the target.

## D-046: Phase 24 Canonical Command Ingress Is /api/command/run
- Date: 2026-03-18
- Decision: Treat `POST /api/command/run` as the canonical internal command-ingress route, with `command_text` as the canonical request field and `/api/operator/command` remaining a separate operator queue intake surface rather than a peer command contract.
- Rationale: This removes ambiguity at the top-level command seam, preserves one deterministic future attachment point for input layers, and keeps the operator surface clearly scoped to queue-oriented operational control instead of general command ingress.

## D-055 Phase 24 Sealing Restricts Non-Canonical Execution Routes To Internal Control-Plane Use
- Date: 2026-03-19
- Decision: Require the `x-lumencore-internal-route: true` boundary on non-canonical execution surfaces, including `/api/operator/command`, `/api/agents/run`, and legacy top-level `command` usage on `/api/command/run`.
- Rationale: Phase 24 previously defined `/api/command/run` with `command_text` as the canonical ingress contract, but sealing required preventing public callers from silently using alternate ingress contracts or lower-level raw execution routes. This preserves one future attachment point for external channels while keeping existing internal compatibility paths available for control-plane use only.

## D-056 Phase 25 Uses One Thin External Input Forwarder Over The Canonical Command Route
- Date: 2026-03-19
- Decision: Expose `POST /api/input/command` as the only minimal external input abstraction in this phase, and implement it as a thin forwarder that constructs a canonical `CommandRunRequest` and invokes the existing `/api/command/run` handler logic with `command_text`, `tenant_id='owner'`, and `project_id='default'`.
- Rationale: This adds one removable external-facing seam without duplicating parser, planner, validation, or execution logic, and preserves the Phase 24 requirement that all external command-style ingress stays anchored to the canonical command contract.

## D-057 Phase 25 Removes External Input Route Coupling By Sharing One Command Execution Seam
- Date: 2026-03-19
- Decision: Route-level command execution logic is factored into a shared non-route callable in `lumencore/services/api/app/commands/command_runtime.py`, and both `/api/command/run` and `/api/input/command` invoke that callable.
- Rationale: This removes route-to-route coupling without changing the canonical command contract, parser/planner ownership, execution branching, or response shape.



## D-058 Phase 45 Closes The Operator Live-Readiness Boundary On Existing Read Surfaces
- Date: 2026-03-23
- Decision: Treat the current operator live-readiness boundary as closed on the existing `/api/operator/*` read surfaces and the standalone proxied control-center surface, without adding new runtime architecture or UI scope.
- Rationale: Phases 40-44 established coherent operator summary, recent-item, and queue truth directly against persisted lifecycle state on the VPS. The remaining gap was factual boundary visibility, not runtime behavior. Closing that boundary in status/decision records preserves the bounded live-v1 posture without reopening execution, lifecycle, or dashboard architecture.

## D-059 Phase 1 Adds A Governed Task Control Layer Above The Existing Job System
- Date: 2026-04-01
- Decision: Add a `Task` model and `/api/tasks` surface as a first-class control layer above the existing `Job` and `ExecutionTaskRecord` systems, with a strict status machine (`queued → running → done/failed`, `needs_input → queued`) and an explicit approval gate for risky task types.
- Rationale: The existing job system is tightly coupled to Celery and the worker path. A dedicated Task layer provides operator-visible task control, approval governance, and a stable integration seam for future execution and memory systems without modifying the proven job/worker infrastructure.

## D-060 Phase 1.5 Bridges Task Control Layer To Existing Execution Infrastructure
- Date: 2026-04-01
- Decision: Connect Task lifecycle to the existing `ExecutionTaskStore` + `ExecutionScheduler` through a thin `task_dispatch.py` bridge that creates an `ExecutionTaskRecord`, runs the scheduler synchronously in the same session, and syncs the result back to the Task — without modifying any existing execution paths.
- Rationale: Reusing the proven scheduler and store preserves all existing execution governance (policy, retry, audit) while giving the Task layer full execution lineage through `execution_task_id`. A synchronous dispatch keeps the integration simple and avoids introducing a second async dispatch mechanism.

## D-061 Phase 2 Adds A Structured Queryable Memory System With Three Layers
- Date: 2026-04-01
- Decision: Implement memory as three explicit relational layers — `MemoryRecord` (fact/preference/context/system), `SkillMemory` (learned patterns with success tracking), and `DecisionLog` (reasoning trace per task) — backed by PostgreSQL with ILIKE keyword search. No embeddings or vector DB in this phase.
- Rationale: Deterministic, structured memory with ILIKE search is sufficient for cross-task recall and decision auditing at the current system scale. Introducing embeddings or a vector database before operational need is justified would add infrastructure cost and complexity without a measurable gain. The three-layer model is designed to be extended with vector search later without a schema redesign.

## D-062 Phase 3 Integrates Memory Into Agent Execution At Three Non-Breaking Seams
- Date: 2026-04-01
- Decision: Hook memory into `execute_agent()` at exactly three points — pre-execution retrieval injected into `task_payload["memory_context"]`, post-success `record_task_outcome()`, and post-failure `record_task_outcome()` — all wrapped in `try/except` so memory failure can never block agent execution or result delivery.
- Rationale: Memory enrichment must not become a new failure mode for agent execution. Injecting context into `task_payload` is non-breaking because the agent loop and existing execution paths ignore unknown payload keys. Wrapping all memory calls in `try/except` enforces a strict boundary between the memory subsystem and the execution critical path.
