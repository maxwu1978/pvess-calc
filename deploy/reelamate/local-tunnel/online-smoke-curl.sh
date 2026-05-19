#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-https://tge.reelamate.com}"
ENV_FILE="${PVESS_LOCAL_TUNNEL_ENV:-$HOME/Services/pvess-calc/deploy/reelamate/local-tunnel/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

: "${PVESS_WEB_ACCESS_TOKEN:?set PVESS_WEB_ACCESS_TOKEN}"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

curl -fsS --max-time 20 "$BASE_URL/" > "$tmp"
grep -q "TGE Solar Project Generator" "$tmp"
echo "PASS public index"

curl -fsS --max-time 20 \
  -H "X-PVESS-Token: $PVESS_WEB_ACCESS_TOKEN" \
  "$BASE_URL/api/health" > "$tmp"
grep -q '"status":"ok"' "$tmp" || grep -q '"status": "ok"' "$tmp"
grep -q '"storage"' "$tmp"
echo "PASS public health"

curl -fsS --max-time 20 "$BASE_URL/assets/app.js" > "$tmp"
grep -q "apiFetch" "$tmp"
echo "PASS public app.js"
