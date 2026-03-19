# Lumencore Service Structure (VPS)

## Primary Runtime Services
- `lumencore-dashboard`: Frontend/dashboard application container.
- `lumencore-api`: Backend API container used by dashboard.
- `nginx`: Edge reverse proxy and routing layer.

## Supporting Services
- `postgres`: Persistent relational datastore for Lumencore API.
- `redis`: Cache/queue backend for async and session-related workloads.
- `claude-gateway` (optional profile `ai`): Internal AI provider boundary exposed through Nginx `/ai` route.

## Network Boundaries
- `edge_net`: Public edge network for inbound HTTP/HTTPS to Nginx.
- `app_net`: Internal service network for app-to-app communication.
- Only `nginx` exposes host ports.

## Persistent State
- `postgres_data`: Database volume.
- `redis_data`: Optional persistence for Redis.
- `nginx_logs`: Nginx access/error logs.

## Health Model
- Dashboard health: `GET /health`
- API health: `GET /health`
- Nginx health: `GET /healthz` on edge route
- Claude gateway health (optional): `GET /ai/health`
- Readiness checks must pass before marking deploy complete.

## Configuration Rules
- Use `.env.vps.example` as template only.
- Real values are injected on server, never committed.
- Service images are tag-driven (`LUMENCORE_VERSION`) for rollback safety.
- Claude runtime is toggled via `ENABLE_CLAUDE_GATEWAY` and compose profile `ai`.