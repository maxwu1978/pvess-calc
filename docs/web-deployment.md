# Web Deployment

W20 adds a production profile for the **TGE Solar Project Generator** without
changing the local `pvess serve` workflow.

## Local Production Profile

Build the image:

```bash
docker build -t pvess-web .
```

Run it with a persistent job directory:

```bash
mkdir -p .pvess-web-data

docker run --rm \
  -p 8765:8765 \
  -e PVESS_WEB_ACCESS_TOKEN="$PVESS_WEB_ACCESS_TOKEN" \
  -v "$PWD/.pvess-web-data:/data/pvess-web" \
  pvess-web
```

Open `http://127.0.0.1:8765`.

The volume mount is required. Generated packages, uploaded source material,
`job-status.json`, and `web-jobs.sqlite3` live under `/data/pvess-web`, which
keeps artifacts outside the container image layer.

## Smoke Check

Run the production smoke check against the running service:

```bash
pvess web-smoke \
  --base-url http://127.0.0.1:8765 \
  --token "$PVESS_WEB_ACCESS_TOKEN"
```

The smoke check verifies:

- `/api/health` returns app, version, auth, and storage status
- `/` and `/assets/app.js` load
- auth mode is understood
- a lightweight sync job can write generated artifacts to the persistent
  workdir

Use `--skip-generate` only when checking a read-only environment.

## Environment

| Variable | Required | Notes |
|---|---:|---|
| `PVESS_WEB_WORKDIR` | yes in production | Defaults to `/data/pvess-web` in the Docker image |
| `PVESS_WEB_ACCESS_TOKEN` | strongly recommended | Admin/bootstrap token for API and file routes |
| `PVESS_WEB_CORS_ORIGINS` | optional | Comma-separated origins when the frontend is hosted separately |
| `PVESS_QET_TEMPLATE` | optional | Override QET template path if the deployment does not run from the repo root |
| `PORT` | optional | Container listen port. Defaults to `8765` |
| `PVESS_MAPBOX_TOKEN` | optional | Online address/coordinate lookup |
| `PVESS_NREL_API_KEY` | optional | Online PVWatts production lookup |
| `PVESS_GOOGLE_SOLAR_KEY` | optional | Online roof-section lookup |

## Backup

Back up the mounted workdir, not the container:

```bash
tar -czf pvess-web-backup-$(date +%Y%m%d).tgz .pvess-web-data
```

The backup contains:

- generated project folders
- uploaded source material
- `web-jobs.sqlite3`
- SQLite WAL/SHM sidecar files when present

For a live server, stop the container before a filesystem-level backup or use
a storage snapshot that preserves SQLite consistency.

## Reverse Proxy

Recommended assumptions:

- terminate TLS at the reverse proxy
- forward `Host`, `X-Forwarded-Proto`, and `X-Forwarded-For`
- set request body limits above the Web upload limit, currently 20 MB per file
- keep `/api/*`, `/files/*`, and `/assets/*` routed to the same app instance
- require `PVESS_WEB_ACCESS_TOKEN` unless the service is only bound to a local
  private network

The app itself does not terminate TLS and does not store browser sessions.
Operator tokens are bearer tokens sent by the browser with API/file requests.

## reelamate.com Rollout

The selected public hostname for the generator is:

```text
tge.reelamate.com
```

This keeps the apex domain available for the existing marketing/site property
while giving the generator a dedicated URL.

### Option A: Local App + Cloudflare Tunnel

Use this first when the system should keep running on the local workstation
instead of a rented Docker host. The app stays bound to `127.0.0.1:8765`; only
`cloudflared` exposes it publicly.

Current production state as of 2026-05-19:

- `reelamate.com` is delegated to Cloudflare.
- The apex `reelamate.com` record remains pointed at the existing Vercel site.
- `www.reelamate.com` remains pointed at `cname.vercel-dns.com`.
- `tge.reelamate.com` is routed through Cloudflare Tunnel.
- The Web service runs from `~/Services/pvess-calc` and listens on
  `127.0.0.1:8765`.
- The Cloudflare Tunnel and Web service are managed by user LaunchAgents.
- Generated jobs and `web-jobs.sqlite3` live under `~/.pvess/reelamate-web`.

Cloudflare Tunnel custom hostnames require the zone to be managed by
Cloudflare. If the deployment has to be recreated, add `reelamate.com` to
Cloudflare, switch the domain nameservers at the registrar, recreate existing
apex / `www` records in Cloudflare, then create the `tge.reelamate.com` tunnel
route.

Local profile files live in `deploy/reelamate/local-tunnel/`:

- `.env.example` stores the local Web token, port, workdir, and optional lookup
  API keys.
- `run-local.sh` starts `pvess serve` on `127.0.0.1`.
- `cloudflared-config.example.yml` maps `tge.reelamate.com` to the local app.
- `online-smoke-curl.sh` verifies the public Cloudflare route with `curl`.
- `backup-local.sh` creates a tar backup of the persistent local workdir.
- `restore-drill.sh` validates the latest backup and SQLite database copy.
- `health-check-curl.sh` runs the public smoke path for uptime checks.
- `install-p1-launchagents.sh` installs scheduled backup and health-check
  LaunchAgents.
- `configure-cloudflare-access.sh` creates the Zero Trust Access app, operator
  email policy, health-check service token, and service-auth policy.
- `P0_RUNBOOK.md` contains the active operator runbook.

Initial local setup:

```bash
cp deploy/reelamate/local-tunnel/.env.example deploy/reelamate/local-tunnel/.env
openssl rand -hex 32
# paste the random value into local-tunnel/.env as PVESS_WEB_ACCESS_TOKEN
# set PVESS_WEB_BASIC_AUTH_USER/PASSWORD to protect the whole site

deploy/reelamate/local-tunnel/run-local.sh
```

In a second terminal, after installing and authenticating `cloudflared`, create
or recreate the tunnel:

```bash
cloudflared tunnel create tge-reelamate-pvess
cloudflared tunnel route dns tge-reelamate-pvess tge.reelamate.com
mkdir -p ~/.cloudflared
cp deploy/reelamate/local-tunnel/cloudflared-config.example.yml \
  ~/.cloudflared/tge-reelamate-pvess.yml
# edit tunnel, credentials-file, and user path in the copied config
cloudflared tunnel --config ~/.cloudflared/tge-reelamate-pvess.yml run tge-reelamate-pvess
```

For the active deployment, the canonical service checkout is:

```text
~/Services/pvess-calc
```

Active smoke checks:

```bash
~/Services/pvess-calc/venv/bin/pvess web-smoke \
  --base-url http://127.0.0.1:8765 \
  --token "$PVESS_WEB_ACCESS_TOKEN" \
  --basic-user "$PVESS_WEB_BASIC_AUTH_USER" \
  --basic-password "$PVESS_WEB_BASIC_AUTH_PASSWORD" \
  --skip-generate

~/Services/pvess-calc/deploy/reelamate/local-tunnel/online-smoke-curl.sh
```

Use the curl-based public smoke for `https://tge.reelamate.com`, because
Cloudflare may reject Python urllib clients with Error 1010 browser-signature
checks.

Operational constraints:

- The local machine must stay powered on, awake, and online.
- Generated source files remain on the local machine under
  `~/.pvess/reelamate-web` by default.
- Keep `PVESS_WEB_ACCESS_TOKEN` private and add Cloudflare Access before
  sharing the URL outside the internal team.
- Keep site-level Basic Auth enabled until Cloudflare Zero Trust Access is
  configured; this protects the static page itself, not only API/file routes.
- Rotate registrar and Cloudflare API tokens after setup if they were created
  for one-time provisioning.

Scheduled P1 operations:

```bash
~/Services/pvess-calc/deploy/reelamate/local-tunnel/install-p1-launchagents.sh
```

This installs:

- `com.tge.pvess-backup`: daily local workdir backup at 02:15.
- `com.tge.pvess-healthcheck`: public curl smoke every 5 minutes.

Cloudflare Access setup:

```bash
mkdir -p ~/.pvess/secrets
chmod 700 ~/.pvess/secrets
nano ~/.pvess/secrets/cloudflare-token
nano ~/.pvess/secrets/cloudflare-access-emails
chmod 600 ~/.pvess/secrets/cloudflare-token ~/.pvess/secrets/cloudflare-access-emails

~/Services/pvess-calc/deploy/reelamate/local-tunnel/configure-cloudflare-access.sh
```

The Cloudflare API token must be scoped to the account and include
`Access: Apps and Policies Write/Edit` plus
`Access: Service Tokens Write/Edit`. The script intentionally refuses to
create an `Include Everyone` policy.

Cloudflare references: locally managed tunnel creation, DNS route creation, and
ingress config are documented at
`https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/create-local-tunnel/`,
`https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/routing-to-tunnel/dns/`,
and
`https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/configuration-file/`.

### Option B: Docker Host + Caddy

The repo also includes a Docker Compose + Caddy profile in
`deploy/reelamate/` for a future Docker-capable Linux host:

- `docker-compose.yml` builds the PVESS image and mounts persistent job storage
  at `/data/pvess-web`.
- `Caddyfile` terminates TLS for `tge.reelamate.com` and proxies to the
  FastAPI container.
- `.env.example` lists the required access token and optional lookup-provider
  API keys.

DNS record:

| Host | Type | Value |
|---|---|---|
| `tge` | `A` | public IPv4 of the Docker host |

Add `AAAA` as well if the host has IPv6.

Deployment:

```bash
cp deploy/reelamate/.env.example deploy/reelamate/.env
openssl rand -hex 32
# paste the random value into deploy/reelamate/.env as PVESS_WEB_ACCESS_TOKEN

docker compose --env-file deploy/reelamate/.env \
  -f deploy/reelamate/docker-compose.yml up -d --build
```

Smoke test:

```bash
export PVESS_WEB_ACCESS_TOKEN="$(grep '^PVESS_WEB_ACCESS_TOKEN=' deploy/reelamate/.env | cut -d= -f2-)"
pvess web-smoke \
  --base-url https://tge.reelamate.com \
  --token "$PVESS_WEB_ACCESS_TOKEN"
```

Do not deploy this app as a Vercel serverless function without reworking job
storage. The current Web generator intentionally writes uploaded source
materials, PDFs, DXFs, ZIPs, and `web-jobs.sqlite3` to a persistent workdir.
