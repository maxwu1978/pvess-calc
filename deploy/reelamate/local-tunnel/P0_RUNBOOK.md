# P0 Operations Runbook

Current production URL:

```text
https://tge.reelamate.com
```

## Runtime Layout

Service checkout:

```text
~/Services/pvess-calc
```

Generated files and job database:

```text
~/.pvess/reelamate-web
```

Cloudflare tunnel token:

```text
~/.cloudflared/tge-reelamate-pvess.token
```

LaunchAgents:

```text
~/Library/LaunchAgents/com.tge.pvess-web.plist
~/Library/LaunchAgents/com.tge.cloudflared-tunnel.plist
~/Library/LaunchAgents/com.tge.pvess-backup.plist
~/Library/LaunchAgents/com.tge.pvess-healthcheck.plist
```

## Access Control

Site-level Basic Auth is enabled through the service env file:

```text
~/Services/pvess-calc/deploy/reelamate/local-tunnel/.env
```

The browser must pass Basic Auth before it can load the static UI. API and
file routes still require the PVESS admin/operator token after the page loads.
This closes the "anyone with the link can open the page" gap while Cloudflare
Zero Trust Access remains a dashboard-managed follow-up.

Unauthenticated check:

```bash
curl -sS -o /tmp/tge-noauth.html -w "%{http_code}\n" https://tge.reelamate.com/
# expected: 401
```

## Cloudflare Access

P2 automation is available at:

```bash
~/Services/pvess-calc/deploy/reelamate/local-tunnel/configure-cloudflare-access.sh
```

Prerequisites:

```bash
mkdir -p ~/.pvess/secrets
chmod 700 ~/.pvess/secrets

# Cloudflare API token with Access: Apps and Policies Write/Edit
# and Access: Service Tokens Write/Edit at the account scope.
nano ~/.pvess/secrets/cloudflare-token
chmod 600 ~/.pvess/secrets/cloudflare-token

# One email per line, or comma-separated emails.
nano ~/.pvess/secrets/cloudflare-access-emails
chmod 600 ~/.pvess/secrets/cloudflare-access-emails
```

Run:

```bash
~/Services/pvess-calc/deploy/reelamate/local-tunnel/configure-cloudflare-access.sh
```

The script creates or reuses:

- a self-hosted Access application for `tge.reelamate.com`
- an email Allow policy for the listed operators
- a Service Auth token and policy for the automated health check
- path-scoped Bypass applications for `/lead` and `/api/leads`

The Access service token is stored locally at:

```text
~/.pvess/secrets/cloudflare-access-service.env
```

`online-smoke-curl.sh` automatically reads that file and sends
`CF-Access-Client-Id` / `CF-Access-Client-Secret` headers.

## Health Checks

Local:

```bash
set -a
source ~/Services/pvess-calc/deploy/reelamate/local-tunnel/.env
set +a

~/Services/pvess-calc/venv/bin/pvess web-smoke \
  --base-url http://127.0.0.1:8765 \
  --token "$PVESS_WEB_ACCESS_TOKEN" \
  --basic-user "$PVESS_WEB_BASIC_AUTH_USER" \
  --basic-password "$PVESS_WEB_BASIC_AUTH_PASSWORD" \
  --skip-generate
```

Public Cloudflare path:

```bash
~/Services/pvess-calc/deploy/reelamate/local-tunnel/online-smoke-curl.sh
```

Use the curl smoke for the public URL because Cloudflare may reject Python
urllib clients with Error 1010 browser-signature checks.

## Restart

Web app:

```bash
launchctl kickstart -k "gui/$UID/com.tge.pvess-web"
```

Cloudflare tunnel:

```bash
launchctl kickstart -k "gui/$UID/com.tge.cloudflared-tunnel"
```

Status:

```bash
launchctl print "gui/$UID/com.tge.pvess-web" | grep -E "state =|pid =|last exit code"
launchctl print "gui/$UID/com.tge.cloudflared-tunnel" | grep -E "state =|pid =|last exit code"
launchctl print "gui/$UID/com.tge.pvess-backup" | grep -E "state =|pid =|last exit code"
launchctl print "gui/$UID/com.tge.pvess-healthcheck" | grep -E "state =|pid =|last exit code"
lsof -nP -iTCP:8765 -sTCP:LISTEN
```

Logs:

```bash
tail -f ~/.pvess/reelamate-web/local-server.launchd.log
tail -f ~/.pvess/reelamate-web/local-server.launchd.err
tail -f ~/.pvess/reelamate-web/cloudflared.launchd.err
tail -f ~/.pvess/reelamate-web/backup.launchd.log
tail -f ~/.pvess/reelamate-web/healthcheck.launchd.log
tail -f ~/.pvess/reelamate-web/healthcheck.launchd.err
```

## Backup

Automatic backup is installed as `com.tge.pvess-backup` and runs daily at
02:15 local time.

Manual backup:

```bash
~/Services/pvess-calc/deploy/reelamate/local-tunnel/backup-local.sh
```

Backups are written to:

```text
~/.pvess/backups
```

Restore drill:

```bash
~/Services/pvess-calc/deploy/reelamate/local-tunnel/restore-drill.sh
```

The drill extracts the latest backup into a temporary directory and runs
SQLite integrity checks when `web-jobs.sqlite3` is present.

## Uptime Check

Automatic public health checks are installed as `com.tge.pvess-healthcheck`
and run every 5 minutes.

Manual check:

```bash
~/Services/pvess-calc/deploy/reelamate/local-tunnel/health-check-curl.sh
```

## Token Rotation

The initial Cloudflare and Spaceship tokens were exposed during setup. They
were deleted/rotated after deployment verification on 2026-05-19.

Keep the Cloudflare tunnel token file private:

```bash
chmod 600 ~/.cloudflared/tge-reelamate-pvess.token
```

If rotating the tunnel token, update the token file and restart:

```bash
launchctl kickstart -k "gui/$UID/com.tge.cloudflared-tunnel"
```

Do not paste future provider tokens into chat. Store temporary provider tokens
in a local file with `chmod 600`, then delete the file after use.
