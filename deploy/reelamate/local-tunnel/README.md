# Local Cloudflare Tunnel Deployment

This profile exposes the local TGE Solar Project Generator at
`https://tge.reelamate.com` while the app keeps running on this machine.

Use this when a Docker VPS is not ready yet. The tradeoff is operational: the
Mac running the app must stay powered on, awake, and online.

## DNS Prerequisite

Cloudflare Tunnel custom hostnames require the zone to be managed in
Cloudflare. Current DNS checks show:

- `tge.reelamate.com` has no A or CNAME record.
- `reelamate.com` currently uses `launch1.spaceship.net` and
  `launch2.spaceship.net` nameservers.

Before the tunnel can serve the public hostname:

1. Add `reelamate.com` to Cloudflare.
2. Change the domain nameservers at Spaceship to the Cloudflare nameservers.
3. Recreate any existing apex / `www` records in Cloudflare so the current site
   keeps working.

## Local App

Create the local environment file:

```bash
cp deploy/reelamate/local-tunnel/.env.example deploy/reelamate/local-tunnel/.env
openssl rand -hex 32
```

Paste the random value into
`deploy/reelamate/local-tunnel/.env` as `PVESS_WEB_ACCESS_TOKEN`.

Start the local app:

```bash
deploy/reelamate/local-tunnel/run-local.sh
```

The app listens only on `127.0.0.1:8765`. Generated jobs, uploaded evidence,
PDFs, DXFs, ZIPs, and `web-jobs.sqlite3` are stored in
`~/.pvess/reelamate-web` by default.

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
export PVESS_WEB_ACCESS_TOKEN="$(grep '^PVESS_WEB_ACCESS_TOKEN=' deploy/reelamate/local-tunnel/.env | cut -d= -f2-)"
pvess web-smoke \
  --base-url https://tge.reelamate.com \
  --token "$PVESS_WEB_ACCESS_TOKEN"
```

## Security

- Keep `PVESS_WEB_ACCESS_TOKEN` private. Do not commit `.env`.
- Leave the app bound to `127.0.0.1`; the tunnel is the only public entry.
- Add Cloudflare Access before sharing the URL outside the internal team.
- Disable sleep on the host machine if the site needs to stay available.
