# Gateway Trace and Usage Fields

## Required Correlation Fields
- `request_id`: caller-provided unique request key.
- `trace_id`: gateway-generated trace key propagated to logs and metrics.
- `origin.system`: `lumencore` or `openclaw`.
- `origin.operation`: operation name in caller domain.

## Required Latency and Status
- `gateway_latency_ms`
- `provider_latency_ms`
- `status` (`ok`, `blocked`, `error`, `timeout`)

## Usage Accounting
- `input_tokens`
- `output_tokens`
- `estimated_cost_usd`
- `provider`
- `model`

## Logging Minimums
- Log structured JSON events for request start and completion.
- Never log raw secrets or unredacted sensitive payload fields.
- Retain error code and message category, not full stack traces in public logs.