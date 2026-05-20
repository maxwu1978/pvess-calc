#!/usr/bin/env bash
set -euo pipefail

ACCOUNT_ID="${CF_ACCOUNT_ID:-343e382e126eecf807cc94b006d8466a}"
ZONE_ID="${CF_ZONE_ID:-5a32aaf002f59c88fcbdb46be9cb98a0}"
APP_SCOPE="${CF_ACCESS_APP_SCOPE:-zone}"
HOSTNAME="${CF_ACCESS_HOSTNAME:-tge.reelamate.com}"
APP_NAME="${CF_ACCESS_APP_NAME:-TGE Solar Project Generator}"
TOKEN_FILE="${CF_API_TOKEN_FILE:-$HOME/.pvess/secrets/cloudflare-token}"
EMAIL_FILE="${CF_ACCESS_EMAIL_FILE:-$HOME/.pvess/secrets/cloudflare-access-emails}"
SERVICE_FILE="${CF_ACCESS_SERVICE_TOKEN_FILE:-$HOME/.pvess/secrets/cloudflare-access-service.env}"
API_BASE="https://api.cloudflare.com/client/v4"

if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "Missing Cloudflare API token file: $TOKEN_FILE" >&2
  exit 2
fi

CF_API_TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"
if [[ -z "$CF_API_TOKEN" ]]; then
  echo "Cloudflare API token file is empty: $TOKEN_FILE" >&2
  exit 2
fi

emails_raw="${PVESS_ACCESS_EMAILS:-}"
if [[ -z "$emails_raw" && -f "$EMAIL_FILE" ]]; then
  emails_raw="$(tr '\n' ',' < "$EMAIL_FILE")"
fi
if [[ -z "$emails_raw" ]]; then
  cat >&2 <<EOF
Missing allowed operator email list.

Set one of:
  export PVESS_ACCESS_EMAILS="you@example.com,ops@example.com"
  or write emails to: $EMAIL_FILE

The script intentionally does not create an Include Everyone policy.
EOF
  exit 2
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

api() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  local out="$tmpdir/response.json"
  local args=(-sS -o "$out" -w '%{http_code}' -X "$method"
    -H "Authorization: Bearer $CF_API_TOKEN"
    -H "Content-Type: application/json")
  if [[ -n "$body" ]]; then
    args+=(-d "$body")
  fi
  local code
  code="$(curl "${args[@]}" "$API_BASE$path")"
  python3 - <<'PY' "$code" "$out" "$method" "$path"
import json, sys
code, path, method, endpoint = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
try:
    data = json.load(open(path, encoding="utf-8"))
except Exception as exc:
    print(f"{method} {endpoint} HTTP {code} parse-error {exc}", file=sys.stderr)
    raise SystemExit(1)
if not data.get("success"):
    print(f"{method} {endpoint} HTTP {code} failed", file=sys.stderr)
    for err in (data.get("errors") or [])[:5]:
        print(f"ERROR {err.get('code')} {err.get('message')}", file=sys.stderr)
    raise SystemExit(1)
json.dump(data.get("result"), sys.stdout)
PY
}

verify_access_permissions() {
  if ! api GET "$APP_BASE" >/dev/null; then
    cat >&2 <<EOF

The token can be read, but it cannot manage Cloudflare Access.
Required Cloudflare token permissions:
  - Access: Apps and Policies Write/Edit
  - Access: Service Tokens Write/Edit

Scope it to account: $ACCOUNT_ID
For this deployment, the Access application endpoint is: $APP_BASE
EOF
    exit 3
  fi
  if ! api GET "/accounts/$ACCOUNT_ID/access/service_tokens" >/dev/null; then
    cat >&2 <<EOF

The token can manage Access applications, but it cannot manage Access service
tokens. Add Access: Service Tokens Write/Edit at account scope: $ACCOUNT_ID
EOF
    exit 3
  fi
}

email_rules_json() {
  python3 - <<'PY' "$1"
import json, re, sys
emails = [x.strip() for x in re.split(r"[\n,]+", sys.argv[1]) if x.strip()]
print(json.dumps([{"email": {"email": email}} for email in emails]))
PY
}

find_app_id() {
  local apps_json
  apps_json="$(api GET "$APP_BASE")"
  python3 -c '
import json, sys
hostname = sys.argv[1]
apps = json.load(sys.stdin)
for app in apps:
    if app.get("domain") == hostname:
        print(app.get("id", ""))
        break
' "$HOSTNAME" <<< "$apps_json"
}

find_app_id_for_domain() {
  local domain="$1"
  local apps_json
  apps_json="$(api GET "$APP_BASE")"
  python3 -c '
import json, sys
domain = sys.argv[1]
apps = json.load(sys.stdin)
for app in apps:
    if app.get("domain") == domain:
        print(app.get("id", ""))
        break
' "$domain" <<< "$apps_json"
}

ensure_access_app() {
  local name="$1"
  local domain="$2"
  local app_id
  app_id="$(find_app_id_for_domain "$domain" || true)"
  if [[ -z "$app_id" ]]; then
    local body
    body="$(python3 - <<'PY' "$name" "$domain"
import json, sys
print(json.dumps({
    "name": sys.argv[1],
    "domain": sys.argv[2],
    "type": "self_hosted",
    "session_duration": "24h",
    "app_launcher_visible": False,
    "auto_redirect_to_identity": False,
}))
PY
)"
    app_id="$(api POST "$APP_BASE" "$body" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
    echo "Created Access app for $domain" >&2
  else
    echo "Access app already exists for $domain" >&2
  fi
  printf '%s' "$app_id"
}

policy_id_by_name_from_json() {
  python3 - <<'PY' "$1" "$2"
import json, sys
policies = json.loads(sys.argv[1])
name = sys.argv[2]
for policy in policies:
    if policy.get("name") == name:
        print(policy.get("id", ""))
        break
PY
}

ensure_bypass_policy() {
  local app_id="$1"
  local policy_name="$2"
  local policy_base="$APP_BASE/$app_id/policies"
  local policies_json
  local policy_id
  policies_json="$(api GET "$policy_base")"
  policy_id="$(policy_id_by_name_from_json "$policies_json" "$policy_name")"
  local body
  body="$(python3 - <<'PY' "$policy_name"
import json, sys
print(json.dumps({
    "name": sys.argv[1],
    "decision": "bypass",
    "include": [{"everyone": {}}],
}))
PY
)"
  if [[ -z "$policy_id" ]]; then
    api POST "$policy_base" "$body" >/dev/null
    echo "Created path-scoped bypass policy: $policy_name"
  else
    api PUT "$policy_base/$policy_id" "$body" >/dev/null
    echo "Updated path-scoped bypass policy: $policy_name"
  fi
}

case "$APP_SCOPE" in
  account)
    APP_BASE="/accounts/$ACCOUNT_ID/access/apps"
    ;;
  zone)
    APP_BASE="/zones/$ZONE_ID/access/apps"
    ;;
  *)
    echo "CF_ACCESS_APP_SCOPE must be account or zone, got: $APP_SCOPE" >&2
    exit 2
    ;;
esac
verify_access_permissions

app_id="$(find_app_id || true)"
if [[ -z "$app_id" ]]; then
  body="$(python3 - <<'PY' "$APP_NAME" "$HOSTNAME"
import json, sys
print(json.dumps({
    "name": sys.argv[1],
    "domain": sys.argv[2],
    "type": "self_hosted",
    "session_duration": "24h",
    "app_launcher_visible": False,
    "auto_redirect_to_identity": False,
}))
PY
)"
  app_id="$(api POST "$APP_BASE" "$body" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
  echo "Created Access app for $HOSTNAME"
else
  echo "Access app already exists for $HOSTNAME"
fi
echo "ACCESS_APP_ID=$app_id"

service_token_name="${CF_ACCESS_SERVICE_TOKEN_NAME:-TGE Solar Project Generator healthcheck}"
service_id=""
client_id=""
client_secret=""
if [[ -f "$SERVICE_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$SERVICE_FILE"
  client_id="${CF_ACCESS_CLIENT_ID:-}"
  client_secret="${CF_ACCESS_CLIENT_SECRET:-}"
fi

service_tokens_json="$(api GET "/accounts/$ACCOUNT_ID/access/service_tokens")"
service_id="$(python3 -c '
import json, sys
name = sys.argv[1]
tokens = json.load(sys.stdin)
for token in tokens:
    if token.get("name") == name:
        print(token.get("id", ""))
        break
' "$service_token_name" <<< "$service_tokens_json")"
if [[ -z "$service_id" || -z "$client_id" || -z "$client_secret" ]]; then
  body="$(python3 - <<'PY' "$service_token_name"
import json, sys
print(json.dumps({"name": sys.argv[1], "duration": "8760h"}))
PY
)"
  service_json="$(api POST "/accounts/$ACCOUNT_ID/access/service_tokens" "$body")"
  service_id="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<< "$service_json")"
  client_id="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["client_id"])' <<< "$service_json")"
  client_secret="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["client_secret"])' <<< "$service_json")"
  mkdir -p "$(dirname "$SERVICE_FILE")"
  {
    printf 'CF_ACCESS_CLIENT_ID=%q\n' "$client_id"
    printf 'CF_ACCESS_CLIENT_SECRET=%q\n' "$client_secret"
  } > "$SERVICE_FILE"
  chmod 600 "$SERVICE_FILE"
  echo "Created Access service token and wrote $SERVICE_FILE"
else
  echo "Access service token already exists and local credentials file is present"
fi
echo "ACCESS_SERVICE_TOKEN_ID=$service_id"

POLICY_BASE="$APP_BASE/$app_id/policies"
policies_json="$(api GET "$POLICY_BASE")"
policy_id_by_name() {
  python3 - <<'PY' "$policies_json" "$1"
import json, sys
policies = json.loads(sys.argv[1])
name = sys.argv[2]
for policy in policies:
    if policy.get("name") == name:
        print(policy.get("id", ""))
        break
PY
}

email_policy_name="TGE operator email allow"
email_policy_id="$(policy_id_by_name "$email_policy_name")"
include_json="$(email_rules_json "$emails_raw")"
body="$(python3 - <<'PY' "$email_policy_name" "$include_json"
import json, sys
print(json.dumps({
    "name": sys.argv[1],
    "decision": "allow",
    "include": json.loads(sys.argv[2]),
    "session_duration": "24h",
}))
PY
)"
if [[ -z "$email_policy_id" ]]; then
  api POST "$POLICY_BASE" "$body" >/dev/null
  echo "Created email allow policy"
else
  api PUT "$POLICY_BASE/$email_policy_id" "$body" >/dev/null
  echo "Updated email allow policy"
fi

service_policy_name="TGE healthcheck service auth"
service_policy_id="$(policy_id_by_name "$service_policy_name")"
body="$(python3 - <<'PY' "$service_policy_name" "$service_id"
import json, sys
print(json.dumps({
    "name": sys.argv[1],
    "decision": "non_identity",
    "include": [{"service_token": {"token_id": sys.argv[2]}}],
}))
PY
)"
if [[ -z "$service_policy_id" ]]; then
  api POST "$POLICY_BASE" "$body" >/dev/null
  echo "Created service auth policy"
else
  api PUT "$POLICY_BASE/$service_policy_id" "$body" >/dev/null
  echo "Updated service auth policy"
fi

lead_page_app_id="$(ensure_access_app "TGE public lead intake page" "$HOSTNAME/lead")"
echo "LEAD_PAGE_ACCESS_APP_ID=$lead_page_app_id"
ensure_bypass_policy "$lead_page_app_id" "TGE public lead page bypass"

lead_api_app_id="$(ensure_access_app "TGE public lead intake API" "$HOSTNAME/api/leads")"
echo "LEAD_API_ACCESS_APP_ID=$lead_api_app_id"
ensure_bypass_policy "$lead_api_app_id" "TGE public lead API bypass"

echo "Cloudflare Access configuration complete for $HOSTNAME"
