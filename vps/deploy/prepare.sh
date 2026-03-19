#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "${SCRIPT_DIR}/.env.vps" ]]; then
  cp "${SCRIPT_DIR}/.env.vps.example" "${SCRIPT_DIR}/.env.vps"
  echo "Created .env.vps from template. Fill server-side values before deploy."
else
  echo ".env.vps already exists; leaving unchanged."
fi
