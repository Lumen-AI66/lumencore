# OpenClaw -> Claude Gateway Event Contract (Draft)

## Objective
Define a stable orchestration event boundary so OpenClaw can request AI execution through Lumencore's internal gateway.

## Event Name
- `openclaw.ai.requested.v1`

## Required Payload
- `event_id` (string)
- `created_at` (ISO-8601 timestamp)
- `workflow_id` (string)
- `task_id` (string)
- `idempotency_key` (string)
- `gateway_request` (object matching `claude/gateway/contracts/ai-gateway.schema.json` request block)

## Response Event
- `openclaw.ai.completed.v1`

## Response Payload Minimum
- `event_id`
- `created_at`
- `workflow_id`
- `task_id`
- `idempotency_key`
- `gateway_response` (object matching schema response block)

## Reliability Rules
- OpenClaw must reuse `idempotency_key` on retry.
- Gateway consumers must treat duplicate `idempotency_key` as safe replay.
- Retry policy starts with exponential backoff and max 3 attempts (placeholder rule).

## Failure Modes
- `POLICY_BLOCKED`: terminal, do not retry.
- `PROVIDER_UNAVAILABLE`: retryable.
- `TIMEOUT`: retryable with same idempotency key.
- `INVALID_REQUEST`: terminal until payload fix.