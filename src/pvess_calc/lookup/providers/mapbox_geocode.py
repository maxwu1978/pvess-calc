"""Mapbox Geocoding v5 provider — turn a free-text address into lat/lng
+ administrative context (county / city / state).

Why Mapbox over Google: Mapbox's free tier is generous (100k req/mo) and
the v5 forward-geocoding endpoint returns lat/lng + a context array with
county/region in one hop; no second reverse-geocode round trip. The
token is a public-scoped `pk.` token, safe to put in CI secrets with a
URL whitelist.

Endpoint chosen: **v5 `mapbox.places`** (stable, generally available on
every account tier). v6 `/search/geocoding/v6/forward` exists but is
gated on some account tiers — empirically returns 404 on accounts that
haven't been migrated. v5 has been GA since 2017 and serves the same
output we need for residential PV site lookup.

Endpoint docs:
  https://docs.mapbox.com/api/search/geocoding-v5/

Without `PVESS_MAPBOX_TOKEN` this provider returns confidence='miss'
with a clear note — the offline chain handles everything else and
the wizard continues unaffected.

Returned fields:
  * latitude / longitude — float, decimal degrees
  * county — string, e.g. "Maricopa County" (from feature.context[]
    where id starts with `district.`)
  * canonical_address — Mapbox's normalised `place_name`
"""
from __future__ import annotations

import urllib.parse
from typing import Any

from ..address import ParsedAddress
from ..config import get_mapbox_token
from ._http import ProviderError, http_get_json
from .base import ProviderResult


# v5 endpoint takes the search text as a URL-path segment, not a query
# param — so we format the URL per request rather than holding a constant.
_MAPBOX_V5_BASE = "https://api.mapbox.com/geocoding/v5/mapbox.places"


def mapbox_geocode(address: ParsedAddress) -> ProviderResult:
    token = get_mapbox_token()
    if not token:
        return ProviderResult(
            source="mapbox-geocode",
            confidence="miss",
            note=("PVESS_MAPBOX_TOKEN env var not set — set a Mapbox public "
                  "token (https://account.mapbox.com/access-tokens/) to "
                  "enable geocoded lat/lng + county lookups."),
        )

    if not address.raw or not address.raw.strip():
        return ProviderResult(
            source="mapbox-geocode", confidence="miss",
            note="empty address",
        )

    # v5 puts the (URL-encoded) query in the path. Mapbox also has a
    # documented rule against commas+spaces in the path segment; encoding
    # `,` as `%2C` is safest.
    quoted = urllib.parse.quote(address.raw.strip(), safe="")
    url = f"{_MAPBOX_V5_BASE}/{quoted}.json"
    params = {
        "country": "us",
        "limit": 1,
        "access_token": token,
    }
    try:
        payload = http_get_json(url, params=params)
    except ProviderError as exc:
        return ProviderResult(
            source="mapbox-geocode", confidence="miss",
            note=f"Mapbox API failed: {exc}",
        )

    features = payload.get("features") or []
    if not features:
        return ProviderResult(
            source="mapbox-geocode", confidence="miss",
            note="Mapbox returned no features for this address.",
        )

    return _feature_to_result(features[0])


def _feature_to_result(feature: dict[str, Any]) -> ProviderResult:
    """Translate one Mapbox v5 GeoJSON feature → ProviderResult.

    v5 puts administrative context in a `context` ARRAY of {id, text}
    objects — county lives under `id` starting with 'district.'. This
    differs from v6 where context is a keyed object.
    """
    coords = (feature.get("geometry") or {}).get("coordinates") or []
    fields: dict[str, Any] = {}
    if len(coords) == 2:
        lng, lat = coords
        fields["latitude"] = float(lat)
        fields["longitude"] = float(lng)

    # v5 context is a list. County is the entry whose id starts with
    # `district.` (Mapbox's term for US counties).
    county: str | None = None
    for ctx in feature.get("context", []) or []:
        ctx_id = ctx.get("id", "")
        if ctx_id.startswith("district."):
            county = ctx.get("text")
            break
    if county:
        fields["county"] = county

    full_address = feature.get("place_name") or feature.get("text") or ""
    if full_address:
        fields["canonical_address"] = full_address

    if not fields:
        return ProviderResult(
            source="mapbox-geocode", confidence="miss",
            note="Mapbox response missing coordinates and context.",
        )

    # Confidence: coords + county = high; coords-only = medium.
    has_coords = "latitude" in fields and "longitude" in fields
    has_district = "county" in fields
    confidence = "high" if (has_coords and has_district) else "medium"

    return ProviderResult(
        source="mapbox-geocode",
        fields=fields,
        confidence=confidence,
        note=(f"Geocoded by Mapbox v5 → {full_address}" if full_address
              else "Geocoded by Mapbox v5."),
    )
