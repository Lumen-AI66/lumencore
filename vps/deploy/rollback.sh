#!/usr/bin/env bash
set -euo pipefail

echo "Legacy rollback path blocked."
echo "This script is not the canonical rollback path for the current Phase 27 Lumencore runtime."
echo "Rollback must use a known release manifest and package generated through C:\\LUMENCORE_SYSTEM\\lumencore\\deploy\\release_ops.py."
exit 1
