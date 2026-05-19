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
