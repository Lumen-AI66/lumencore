# Claude Gateway (Provider-Agnostic Boundary)

This directory defines the internal AI gateway boundary for Lumencore.

## Purpose
- Prevent direct app-to-provider coupling.
- Enforce policy and versioned prompt controls.
- Provide consistent tracing and usage accounting.

## Scope
- Contract-first integration for Lumencore and OpenClaw callers.
- Provider adapter scaffolding for Claude and future providers.
- Observability fields for request tracing and cost tracking.

## Status
- Placeholder contracts only. Runtime implementation is intentionally deferred until Lumencore API runtime contracts are available.

## Entry Contract
- Request/response schema: `contracts/ai-gateway.schema.json`
- Adapter contract: `contracts/provider-adapter.md`
- Policy template: `policies/policy.v1.yaml`
- Trace/usage fields: `observability/trace-fields.md`