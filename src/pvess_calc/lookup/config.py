"""Centralised env-var access for the lookup service.

All API credentials live in environment variables — NEVER in the repo,
NEVER in inputs.yaml. The module exposes one accessor per provider
that returns `Optional[str]`; the corresponding online provider
short-circuits to `confidence='miss'` when its key is absent.

Reading is cached for the process lifetime — env vars don't change at
runtime, and the accessors are called from inside hot resolve() loops.

**`.env` file support.** Many launchers (Claude Code, IDE run configs,
launchd plists) don't inherit the user's interactive-shell environment,
which means an `export PVESS_MAPBOX_TOKEN=…` in `~/.zshrc` is invisible
to the running tool. To paper over that we look for a project-local
`.env` file at import time and copy its KEY=VALUE lines into
`os.environ`. The format is the de-facto dotenv subset (no
substitution, no `export` keyword, `#` for comments). Already-set env
vars win — `.env` only fills gaps, so a shell-set value is never
silently overridden.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional


# Env var names — also documented in CLAUDE.md so users know what to set.
ENV_MAPBOX_TOKEN: str = "PVESS_MAPBOX_TOKEN"
ENV_NREL_API_KEY: str = "PVESS_NREL_API_KEY"
# K.3c — Google Solar API key (Google Cloud Platform, Solar API enabled).
# Same pattern as the others: a missing key turns the provider into a
# clean 'miss' without breaking the offline chain.
ENV_GOOGLE_SOLAR_KEY: str = "PVESS_GOOGLE_SOLAR_KEY"
# Optional Google Maps Platform key for Static Maps / Map Tiles visual
# fallbacks. If unset, callers may reuse the Solar key; restricted keys
# should prefer this separate env var.
ENV_GOOGLE_MAPS_KEY: str = "PVESS_GOOGLE_MAPS_KEY"

# Network defaults — every provider uses these unless it has a reason not to.
DEFAULT_HTTP_TIMEOUT_S: float = 5.0


def _find_dotenv() -> Optional[Path]:
    """Walk up from CWD looking for a .env file. Stops at the
    filesystem root or when it finds one. Returning the path lets the
    loader log where the file came from when running under -v."""
    for d in (Path.cwd(), *Path.cwd().parents):
        candidate = d / ".env"
        if candidate.is_file():
            return candidate
    return None


def _load_dotenv_into_environ() -> None:
    """Read `.env` and copy KEY=VALUE lines into `os.environ`.

    Rules:
      * Skips lines that are empty / start with `#`.
      * Strips a leading `export ` (so shell-style exports work as-is).
      * Trims matching single or double quotes off the value.
      * **Does NOT** overwrite existing env vars — a real shell export
        wins over the file. This means rotating a key during a session
        is safe: just `export` the new one and the old `.env` entry is
        ignored.
    """
    path = _find_dotenv()
    if path is None:
        return
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("export "):
                stripped = stripped[len("export "):].lstrip()
            if "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip matching wrapping quotes.
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        # Unreadable .env is non-fatal — fall back to shell env only.
        pass


# Auto-load on import. Cheap (one file read at most) and idempotent —
# subsequent imports hit the same `os.environ`.
_load_dotenv_into_environ()


@lru_cache(maxsize=1)
def get_mapbox_token() -> Optional[str]:
    """Returns the Mapbox public/secret token if set, else None.

    NB: tokens with prefix `sk.` are secret — never log them. Tokens with
    prefix `pk.` are scoped public tokens and safer to use here.
    """
    val = os.environ.get(ENV_MAPBOX_TOKEN, "").strip()
    return val or None


@lru_cache(maxsize=1)
def get_nrel_api_key() -> Optional[str]:
    """NREL Developer API key (free signup at developer.nrel.gov).
    Used by PVWatts / utility-rate / solar-resource endpoints.
    """
    val = os.environ.get(ENV_NREL_API_KEY, "").strip()
    return val or None


@lru_cache(maxsize=1)
def get_google_solar_key() -> Optional[str]:
    """K.3c — Google Cloud Solar API key. Enable Solar API in the GCP
    console (https://console.cloud.google.com/apis/library/solar.googleapis.com),
    create an API key with Solar API restriction, paste here. Free tier
    is generous (~1k Building Insights requests/month) and per-request
    cost is ~$0.05 after that — orders of magnitude cheaper than an
    EagleView roof report ($20-40/property).
    """
    val = os.environ.get(ENV_GOOGLE_SOLAR_KEY, "").strip()
    return val or None


@lru_cache(maxsize=1)
def get_google_maps_key() -> Optional[str]:
    """Google Maps Platform key for visual satellite fallback imagery.

    `PVESS_GOOGLE_MAPS_KEY` is preferred because production keys are often
    API-restricted. Falling back to `PVESS_GOOGLE_SOLAR_KEY` keeps existing
    local setups working when the same key is allowed to call Static Maps.
    """
    val = os.environ.get(ENV_GOOGLE_MAPS_KEY, "").strip()
    if val:
        return val
    return get_google_solar_key()


def reset_cache_for_tests() -> None:
    """Clear lru_cache so tests can set / unset env vars between cases."""
    get_mapbox_token.cache_clear()
    get_nrel_api_key.cache_clear()
    get_google_solar_key.cache_clear()
    get_google_maps_key.cache_clear()


# ─── Public helpers for the verification CLI / doctor ──────────────────────


def token_fingerprint(token: Optional[str]) -> str:
    """Format a token for human verification WITHOUT exposing its full
    value. Returns "pk.eyJ1...XYz9 (len=84)" or "(not set)".

    The fingerprint preserves: the 3-char prefix (so user sees pk./sk.),
    next 4 chars (for visual identification across rotations), the last
    4 chars, and total length. That's enough to tell two tokens apart
    or confirm "this is the one I just exported" — without leaking
    enough material to make API calls.
    """
    if not token:
        return "(not set)"
    if len(token) <= 12:
        return f"<short token, len={len(token)}>"
    return f"{token[:7]}...{token[-4:]} (len={len(token)})"
