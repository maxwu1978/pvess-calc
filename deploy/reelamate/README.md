# reelamate.com Deployment

This profile runs the TGE Solar Project Generator at
`https://tge.reelamate.com` with Docker, Caddy TLS, and persistent job
storage.

## DNS

Keep `reelamate.com` and `www.reelamate.com` on their current Vercel records.
Create a new DNS record for the PVESS tool:

| Host | Type | Value |
|---|---|---|
| `tge` | `A` | public IPv4 of the Docker host |

If the host also has IPv6, add an `AAAA` record for `tge`.

## Server Setup

On a Docker-capable Linux host:

```bash
git clone https://github.com/maxwu1978/pvess-calc.git
cd pvess-calc
cp deploy/reelamate/.env.example deploy/reelamate/.env
openssl rand -hex 32
```

Paste the random value into `deploy/reelamate/.env` as
`PVESS_WEB_ACCESS_TOKEN`.

Start the service:

```bash
docker compose --env-file deploy/reelamate/.env \
  -f deploy/reelamate/docker-compose.yml up -d --build
```

Caddy will request and renew TLS certificates automatically once
`tge.reelamate.com` resolves to the server.

## Smoke Check

```bash
export PVESS_WEB_ACCESS_TOKEN="$(grep '^PVESS_WEB_ACCESS_TOKEN=' deploy/reelamate/.env | cut -d= -f2-)"
pvess web-smoke \
  --base-url https://tge.reelamate.com \
  --token "$PVESS_WEB_ACCESS_TOKEN"
```

## Backup

Generated jobs, uploaded evidence, ZIP packages, and `web-jobs.sqlite3` live
in the Docker volume `reelamate_pvess-web-data`.

```bash
docker compose --env-file deploy/reelamate/.env \
  -f deploy/reelamate/docker-compose.yml stop pvess-web
docker run --rm \
  -v reelamate_pvess-web-data:/data:ro \
  -v "$PWD:/backup" \
  alpine tar -czf /backup/pvess-web-backup-$(date +%Y%m%d).tgz -C /data .
docker compose --env-file deploy/reelamate/.env \
  -f deploy/reelamate/docker-compose.yml start pvess-web
```
