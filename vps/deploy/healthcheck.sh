#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1}"
ENABLE_CLAUDE_GATEWAY="${ENABLE_CLAUDE_GATEWAY:-false}"

check() {
  local name="$1"
  local url="$2"
  echo "Checking ${name}: ${url}"
  curl --fail --silent --show-error "${url}" > /dev/null
}

check "nginx" "${BASE_URL}/healthz"
check "dashboard" "${BASE_URL}/health"
check "api" "${BASE_URL}/api/health"

if [[ "${ENABLE_CLAUDE_GATEWAY}" == "true" ]]; then
  check "claude-gateway" "${BASE_URL}/ai/health"
fi

echo "All health checks passed."