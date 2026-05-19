#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
ENV_FILE="${1:-$SCRIPT_DIR/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  echo "Copy deploy/reelamate/local-tunnel/.env.example to .env and set PVESS_WEB_ACCESS_TOKEN." >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

: "${PVESS_WEB_ACCESS_TOKEN:?set PVESS_WEB_ACCESS_TOKEN}"

PVESS_WEB_PORT="${PVESS_WEB_PORT:-8765}"
PVESS_WEB_WORKDIR="${PVESS_WEB_WORKDIR:-$HOME/.pvess/reelamate-web}"
mkdir -p "$PVESS_WEB_WORKDIR"

cd "$REPO_ROOT"

if [[ -x "$REPO_ROOT/venv/bin/pvess" ]]; then
  PVESS_CMD=("$REPO_ROOT/venv/bin/pvess")
elif command -v pvess >/dev/null 2>&1; then
  PVESS_CMD=("pvess")
else
  echo "pvess CLI not found. Run: python -m venv venv && venv/bin/pip install -e ." >&2
  exit 1
fi

exec "${PVESS_CMD[@]}" serve \
  --host 127.0.0.1 \
  --port "$PVESS_WEB_PORT" \
  --workdir "$PVESS_WEB_WORKDIR" \
  --access-token "$PVESS_WEB_ACCESS_TOKEN"
