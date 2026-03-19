# Provider Adapter Contract (Claude Gateway)

## Adapter Interface (Conceptual)
- `initialize(config) -> void`
- `invoke(normalized_request) -> normalized_response`
- `health() -> { status, provider, model, latency_ms }`

## Required Adapter Inputs
- Provider credentials loaded from runtime env (never from repo files).
- Normalized request shape from `ai-gateway.schema.json`.
- Policy bundle (`policy_version`, redaction mode, allowed templates).

## Required Adapter Outputs
- Normalized response shape from `ai-gateway.schema.json`.
- Provider usage fields mapped to gateway usage fields.
- Stable error codes (`PROVIDER_UNAVAILABLE`, `POLICY_BLOCKED`, `TIMEOUT`, `INVALID_REQUEST`).

## Claude-Specific Notes
- Claude adapter must not expose vendor-specific payloads to callers.
- Model names remain configurable by env and gateway allow-list.
- Streaming support is optional and deferred until dashboard/API runtime contracts are present.

## Safety Requirements
- Deny requests with unknown prompt template versions.
- Deny requests missing `request_id` or origin metadata.
- Redact sensitive fields before provider submission according to policy.