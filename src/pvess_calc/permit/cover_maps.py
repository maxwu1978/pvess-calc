"""K.12.2 + K.12.3 — aerial + vicinity map fetchers for the PV-1 cover.

Both maps are **opt-in** (no API key → blank placeholder, cover still
renders). The cover sheet asks `fetch_aerial_map_png(...)` and
`fetch_vicinity_map_png(...)` for byte blobs; if either returns None
the renderer falls back to a "(no map available)" label.

Endpoints:
  * Aerial:   Google Solar dataLayers (K.3c, already wired) → RGB
              GeoTIFF of the roof. Cached in caller's local cache.
  * Vicinity: Mapbox Static Images API. Reuses the existing
              `PVESS_MAPBOX_TOKEN` from K.3b. No additional credential
              required. URL signed by token.

Cost:
  * Aerial   ~$0.50 / render (dataLayers SKU — same as K.3c+ paid path)
  * Vicinity $0.005 / render (Mapbox raster tile, ~10× cheaper than
              geocoding)

Both calls cached at the function level via a tiny on-disk png cache
keyed by lat/lng — re-rendering the same project shouldn't ring the
Mapbox / Google billing every time.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

import requests

from ..lookup.config import (
    DEFAULT_HTTP_TIMEOUT_S,
    get_google_solar_key,
    get_mapbox_token,
)


# Default cache root mirrors the K.3 lookup cache convention.
_CACHE_ROOT = Path.home() / ".pvess" / "cache" / "cover_maps"


def _cache_path(prefix: str, lat: float, lng: float, **extras) -> Path:
    """Build a deterministic cache path. Same lat/lng + same kwargs
    → same hash → same file → cache hit."""
    key_parts = [f"{lat:.6f}", f"{lng:.6f}"]
    for k in sorted(extras.keys()):
        key_parts.append(f"{k}={extras[k]}")
    key = "|".join(key_parts)
    digest = hashlib.sha1(key.encode()).hexdigest()[:16]
    return _CACHE_ROOT / f"{prefix}-{digest}.png"


def _npz_cache_path(prefix: str, lat: float, lng: float, **extras) -> Path:
    png_path = _cache_path(prefix, lat, lng, **extras)
    return png_path.with_suffix(".npz")


def fetch_satellite_assets_cached(
    lat: float, lng: float, *,
    radius_m: float = 25.0,
    cache: bool = True,
    allow_network: bool = True,
):
    """Return decoded Google Solar satellite assets with an `.npz` cache.

    EE-4 Stage 7 needs both RGB and mask. `fetch_aerial_map_png()` only
    cached the RGB PNG, so this function stores the decoded arrays once
    and lets the PDF renderer reuse them without ringing dataLayers on
    every preview render.
    """
    if not get_google_solar_key():
        return None

    cp = _npz_cache_path("satellite-assets", lat, lng, radius=radius_m)
    if cache and cp.exists():
        try:
            import numpy as np
            from ..customer.roof_satellite import SatelliteAssets

            data = np.load(cp, allow_pickle=False)
            return SatelliteAssets(
                rgb=data["rgb"],
                annual_flux=data["annual_flux"],
                mask=data["mask"].astype(bool),
                imagery_date=str(data["imagery_date"]),
                imagery_quality=str(data["imagery_quality"]),
            )
        except Exception:
            # Corrupt cache should behave like a miss.
            pass

    if not allow_network:
        return None

    try:
        from ..customer.roof_satellite import fetch_satellite_assets
        assets = fetch_satellite_assets(lat, lng, radius_m=radius_m)
    except Exception:
        return None

    if cache:
        try:
            import numpy as np

            cp.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(
                cp,
                rgb=assets.rgb,
                annual_flux=assets.annual_flux,
                mask=assets.mask.astype("uint8"),
                imagery_date=assets.imagery_date,
                imagery_quality=assets.imagery_quality,
            )
        except Exception:
            pass
    return assets


# ─── Aerial map (Google Solar dataLayers RGB) ───────────────────────────


def fetch_aerial_map_png(
    lat: float, lng: float, *,
    radius_m: float = 25.0,
    cache: bool = True,
    allow_network: bool = True,
) -> Optional[bytes]:
    """K.12.2 — return PNG bytes of the roof aerial imagery, or None
    when Google Solar key is missing / API fails. Cached on disk.

    Reuses the K.3c+ paid-render plumbing in
    `customer.roof_satellite.fetch_satellite_assets`; we extract the
    `rgb` numpy array and re-encode as PNG for the reportlab Image
    (which doesn't accept GeoTIFF directly).
    """
    if not get_google_solar_key():
        return None

    cp = _cache_path("aerial", lat, lng, radius=radius_m)
    if cache and cp.exists():
        return cp.read_bytes()
    if not allow_network:
        return None

    try:
        from PIL import Image
        import io
        assets = fetch_satellite_assets_cached(
            lat, lng,
            radius_m=radius_m,
            cache=cache,
            allow_network=allow_network,
        )
        if assets is None:
            return None
    except Exception:
        # Any failure (missing key, API down, network) → silent None.
        # Cover renderer surfaces "no aerial available" placeholder.
        return None

    # Convert numpy RGB (H, W, 3) uint8 → PNG bytes via Pillow
    try:
        img = Image.fromarray(assets.rgb, mode="RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()
    except Exception:
        return None

    if cache:
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_bytes(png_bytes)
    return png_bytes


# ─── Vicinity map (Mapbox Static Images) ────────────────────────────────


_MAPBOX_STATIC_BASE = (
    "https://api.mapbox.com/styles/v1/mapbox/streets-v12/static"
)


def fetch_vicinity_map_png(
    lat: float, lng: float, *,
    zoom: float = 15.0,
    width_px: int = 600,
    height_px: int = 400,
    cache: bool = True,
) -> Optional[bytes]:
    """K.12.3 — return PNG bytes of a street-style vicinity map
    centred on the project, with a red pin at the building.

    Mapbox Static Images API: ~$0.005/render. Reuses the K.3b
    `PVESS_MAPBOX_TOKEN`. Returns None when:
      * token missing  → cover skips the block
      * HTTP error     → cover skips the block (no broken-link image)
    """
    token = get_mapbox_token()
    if not token:
        return None

    cp = _cache_path("vicinity", lat, lng,
                     zoom=zoom, w=width_px, h=height_px)
    if cache and cp.exists():
        return cp.read_bytes()

    # Mapbox URL convention: /pin-l+ff0000(lng,lat)/lng,lat,zoom/widthxheight
    # The "pin-l+ff0000" is a red large pin marker at the centre.
    pin = f"pin-l+ff0000({lng:.6f},{lat:.6f})"
    url = (
        f"{_MAPBOX_STATIC_BASE}/{pin}/{lng:.6f},{lat:.6f},{zoom}/"
        f"{width_px}x{height_px}@2x"
    )
    try:
        resp = requests.get(
            url, params={"access_token": token},
            timeout=DEFAULT_HTTP_TIMEOUT_S * 2.0,   # static images are slower
        )
    except requests.exceptions.RequestException:
        return None
    if resp.status_code >= 400:
        return None

    png_bytes = resp.content
    if cache:
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_bytes(png_bytes)
    return png_bytes


# ─── Helpers ───────────────────────────────────────────────────────────


def coordinates_to_lat_lng(coords_str: str) -> Optional[tuple[float, float]]:
    """Parse `project.coordinates` strings like '33.141418, -96.801258'.
    Returns None when malformed (best-effort)."""
    if not coords_str:
        return None
    try:
        parts = coords_str.split(",")
        if len(parts) != 2:
            return None
        return float(parts[0].strip()), float(parts[1].strip())
    except (ValueError, IndexError):
        return None
