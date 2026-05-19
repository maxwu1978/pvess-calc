#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-https://tge.reelamate.com}"
ENV_FILE="${PVESS_LOCAL_TUNNEL_ENV:-$HOME/Services/pvess-calc/deploy/reelamate/local-tunnel/.env}"
ACCESS_SERVICE_FILE="${CF_ACCESS_SERVICE_TOKEN_FILE:-$HOME/.pvess/secrets/cloudflare-access-service.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

set -a
source "$ENV_FILE"
if [[ -f "$ACCESS_SERVICE_FILE" ]]; then
  source "$ACCESS_SERVICE_FILE"
fi
set +a

: "${PVESS_WEB_ACCESS_TOKEN:?set PVESS_WEB_ACCESS_TOKEN}"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

curl_auth=()
if [[ -n "${PVESS_WEB_BASIC_AUTH_USER:-}" && -n "${PVESS_WEB_BASIC_AUTH_PASSWORD:-}" ]]; then
  curl_auth=(-u "$PVESS_WEB_BASIC_AUTH_USER:$PVESS_WEB_BASIC_AUTH_PASSWORD")
fi
cf_access=()
if [[ -n "${CF_ACCESS_CLIENT_ID:-}" && -n "${CF_ACCESS_CLIENT_SECRET:-}" ]]; then
  cf_access=(
    -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID"
    -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET"
  )
fi

curl -fsS --max-time 20 "${curl_auth[@]}" "${cf_access[@]}" "$BASE_URL/" > "$tmp"
grep -q "TGE Solar Project Generator" "$tmp"
echo "PASS public index"

curl -fsS --max-time 20 \
  "${curl_auth[@]}" \
  "${cf_access[@]}" \
  -H "X-PVESS-Token: $PVESS_WEB_ACCESS_TOKEN" \
  "$BASE_URL/api/health" > "$tmp"
grep -q '"status":"ok"' "$tmp" || grep -q '"status": "ok"' "$tmp"
grep -q '"storage"' "$tmp"
echo "PASS public health"

curl -fsS --max-time 20 "${curl_auth[@]}" "${cf_access[@]}" "$BASE_URL/assets/app.js" > "$tmp"
grep -q "apiFetch" "$tmp"
echo "PASS public app.js"
