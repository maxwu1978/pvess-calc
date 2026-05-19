#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "[$STAMP] checking https://tge.reelamate.com"
"$SCRIPT_DIR/online-smoke-curl.sh" "${1:-https://tge.reelamate.com}"
echo "[$STAMP] health check passed"
