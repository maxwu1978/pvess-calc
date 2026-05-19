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
```

## Health Checks

Local:

```bash
set -a
source ~/Services/pvess-calc/deploy/reelamate/local-tunnel/.env
set +a

~/Services/pvess-calc/venv/bin/pvess web-smoke \
  --base-url http://127.0.0.1:8765 \
  --token "$PVESS_WEB_ACCESS_TOKEN" \
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
lsof -nP -iTCP:8765 -sTCP:LISTEN
```

Logs:

```bash
tail -f ~/.pvess/reelamate-web/local-server.launchd.log
tail -f ~/.pvess/reelamate-web/local-server.launchd.err
tail -f ~/.pvess/reelamate-web/cloudflared.launchd.err
```

## Backup

```bash
~/Services/pvess-calc/deploy/reelamate/local-tunnel/backup-local.sh
```

Backups are written to:

```text
~/.pvess/backups
```

## Token Rotation

The initial Cloudflare and Spaceship tokens were exposed during setup. Rotate
them after deployment verification:

1. Delete or rotate the Cloudflare API token used for zone/DNS/tunnel setup.
2. Delete or rotate the Spaceship API key/secret used for nameserver changes.
3. Keep the Cloudflare tunnel token file private:

   ```bash
   chmod 600 ~/.cloudflared/tge-reelamate-pvess.token
   ```

4. If rotating the tunnel token, update the token file and restart:

   ```bash
   launchctl kickstart -k "gui/$UID/com.tge.cloudflared-tunnel"
   ```

Do not paste future provider tokens into chat. Store temporary provider tokens
in a local file with `chmod 600`, then delete the file after use.
