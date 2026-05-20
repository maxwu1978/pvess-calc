# Local Cloudflare Tunnel Deployment

This profile exposes the local TGE Solar Project Generator at
`https://tge.reelamate.com` while the app keeps running on this machine.

Use this when a Docker VPS is not ready yet. The tradeoff is operational: the
Mac running the app must stay powered on, awake, and online.

## Current Production State

As of 2026-05-19, the local tunnel deployment is active:

- `reelamate.com` is delegated to Cloudflare nameservers.
- `reelamate.com` keeps the existing Vercel apex record.
- `www.reelamate.com` keeps the existing Vercel `cname.vercel-dns.com` record.
- `tge.reelamate.com` points to the Cloudflare Tunnel hostname and is proxied.
- The Web app runs from `~/Services/pvess-calc` on `127.0.0.1:8765`.
- Generated jobs and `web-jobs.sqlite3` live under `~/.pvess/reelamate-web`.

P0 operator scripts:

```bash
deploy/reelamate/local-tunnel/online-smoke-curl.sh
deploy/reelamate/local-tunnel/backup-local.sh
deploy/reelamate/local-tunnel/configure-cloudflare-access.sh
deploy/reelamate/local-tunnel/restore-drill.sh
deploy/reelamate/local-tunnel/health-check-curl.sh
deploy/reelamate/local-tunnel/install-p1-launchagents.sh
```

See `P0_RUNBOOK.md` for restart, status, backup, and token-rotation commands.

## DNS Prerequisite

Cloudflare Tunnel custom hostnames require the zone to be managed in
Cloudflare. If this deployment has to be rebuilt from scratch:

1. Add `reelamate.com` to Cloudflare.
2. Change the domain nameservers at Spaceship to the Cloudflare nameservers.
3. Recreate any existing apex / `www` records in Cloudflare so the current site
   keeps working.
4. Add or recreate the `tge.reelamate.com` tunnel route.

## Local App

Create the local environment file:

```bash
cp deploy/reelamate/local-tunnel/.env.example deploy/reelamate/local-tunnel/.env
openssl rand -hex 32
```

Paste the random value into
`deploy/reelamate/local-tunnel/.env` as `PVESS_WEB_ACCESS_TOKEN`.
Set `PVESS_WEB_BASIC_AUTH_USER` and `PVESS_WEB_BASIC_AUTH_PASSWORD` to enable
site-level Basic Auth for the static UI and every route.

Start the local app:

```bash
deploy/reelamate/local-tunnel/run-local.sh
```

The app listens only on `127.0.0.1:8765`. Generated jobs, uploaded evidence,
PDFs, DXFs, ZIPs, and `web-jobs.sqlite3` are stored in
`~/.pvess/reelamate-web` by default.

For the active production instance, the canonical env file is:

```text
~/Services/pvess-calc/deploy/reelamate/local-tunnel/.env
```

## Cloudflare Tunnel

Install and authenticate `cloudflared`:

```bash
brew install cloudflare/cloudflare/cloudflared
cloudflared tunnel login
```

Create a named tunnel and route the hostname:

```bash
cloudflared tunnel create tge-reelamate-pvess
cloudflared tunnel route dns tge-reelamate-pvess tge.reelamate.com
```

Copy the example config and replace `TUNNEL_UUID_OR_NAME`,
`TUNNEL_UUID.json`, and `YOUR_USER` with values printed by the create command:

```bash
mkdir -p ~/.cloudflared
cp deploy/reelamate/local-tunnel/cloudflared-config.example.yml \
  ~/.cloudflared/tge-reelamate-pvess.yml
```

Run the tunnel in a second terminal:

```bash
cloudflared tunnel --config ~/.cloudflared/tge-reelamate-pvess.yml run tge-reelamate-pvess
```

## Smoke Check

With both processes running:

```bash
deploy/reelamate/local-tunnel/online-smoke-curl.sh
```

The public smoke uses `curl`, because Cloudflare may reject Python urllib
clients with Error 1010 browser-signature checks. For local loopback checks,
source the `.env` file and use
`pvess web-smoke --base-url http://127.0.0.1:8765 --skip-generate`.

## P1 Scheduled Operations

Install daily backups and 5-minute public health checks:

```bash
deploy/reelamate/local-tunnel/install-p1-launchagents.sh
```

Manual commands:

```bash
deploy/reelamate/local-tunnel/backup-local.sh
deploy/reelamate/local-tunnel/restore-drill.sh
deploy/reelamate/local-tunnel/health-check-curl.sh
```

## P2 Cloudflare Access

Configure Cloudflare Zero Trust Access after creating an account-scoped API
token with:

- `Access: Apps and Policies Write/Edit`
- `Access: Service Tokens Write/Edit`

Then provide the allowed operator emails:

```bash
mkdir -p ~/.pvess/secrets
chmod 700 ~/.pvess/secrets
nano ~/.pvess/secrets/cloudflare-token
nano ~/.pvess/secrets/cloudflare-access-emails
chmod 600 ~/.pvess/secrets/cloudflare-token ~/.pvess/secrets/cloudflare-access-emails
```

Run:

```bash
deploy/reelamate/local-tunnel/configure-cloudflare-access.sh
```

The script also creates path-scoped Bypass applications for `/lead` and
`/api/leads`, so customers can submit estimate requests without login while
the generator UI and generated files remain protected.

## Security

- Keep `PVESS_WEB_ACCESS_TOKEN` private. Do not commit `.env`.
- Keep `PVESS_WEB_BASIC_AUTH_PASSWORD` private. Do not commit `.env`.
- Leave the app bound to `127.0.0.1`; the tunnel is the only public entry.
- Site-level Basic Auth should stay enabled as a fallback even after
  Cloudflare Zero Trust Access is configured.
- Disable sleep on the host machine if the site needs to stay available.
- Rotate any temporary Cloudflare or registrar API tokens used during setup.
