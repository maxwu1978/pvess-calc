"""K.3c+ — Google Solar `dataLayers:get` HTTP wrapper.

**Deliberately NOT a `Provider` in the orchestrator chain.** The
`dataLayers` SKU is ~$0.50 per call (vs $0.05 for buildingInsights),
returns short-lived signed URLs to multi-MB GeoTIFF assets that don't
fit the lookup cache pattern, and is only useful when we have a
specific reason to render real imagery (signed customer, design
review). The standard `resolve()` path stays cheap and offline-tolerant.

Endpoint: https://solar.googleapis.com/v1/dataLayers:get
Docs:     https://developers.google.com/maps/documentation/solar/data-layers

What it gives us:

  * `rgbUrl` — true-colour aerial photo of the roof (3-band uint8 TIFF)
  * `annualFluxUrl` — single-band float32 TIFF, kWh/m²/year per pixel
  * `maskUrl` — single-band uint8 TIFF; 1 = building roof, 0 = ground
  * `dsmUrl` / `monthlyFluxUrl` / `hourlyShadeUrls` — not currently used
  * `imageryDate` / `imageryProcessedDate` / `imageryQuality`

Two-step fetch: this endpoint returns URLs only; each layer requires
a follow-up GET. We expose both calls (`fetch_data_layers` and
`download_layer_bytes`) so the renderer can stream large assets to
disk + decode incrementally rather than buffer everything in memory.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ..config import get_google_solar_key
from ._http import ProviderError, http_get_json


_DATA_LAYERS_URL = "https://solar.googleapis.com/v1/dataLayers:get"


# Google's `view` enum — picks which subset of layers comes back.
# IMAGERY_AND_ANNUAL_FLUX_LAYERS is the cheapest combination that
# carries every layer roof_satellite.py needs (RGB + flux + mask).
DEFAULT_VIEW: str = "IMAGERY_AND_ANNUAL_FLUX_LAYERS"


@dataclass
class DataLayersResult:
    """Parsed dataLayers:get response. URLs are short-lived (hours)
    and tied to the originating API key — re-fetching the URL with
    that key authenticates the layer GET."""
    rgb_url: Optional[str]
    annual_flux_url: Optional[str]
    mask_url: Optional[str]
    dsm_url: Optional[str]
    imagery_date: Optional[str]              # ISO "YYYY-MM-DD"
    imagery_processed_date: Optional[str]
    imagery_quality: str                     # "HIGH" / "MEDIUM" / "LOW"

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DataLayersResult":
        def _date_str(key: str) -> Optional[str]:
            d = payload.get(key) or {}
            y, m, day = d.get("year"), d.get("month"), d.get("day")
            if y and m and day:
                return f"{int(y):04d}-{int(m):02d}-{int(day):02d}"
            return None
        return cls(
            rgb_url=payload.get("rgbUrl"),
            annual_flux_url=payload.get("annualFluxUrl"),
            mask_url=payload.get("maskUrl"),
            dsm_url=payload.get("dsmUrl"),
            imagery_date=_date_str("imageryDate"),
            imagery_processed_date=_date_str("imageryProcessedDate"),
            imagery_quality=(payload.get("imageryQuality") or "LOW").upper(),
        )


class DataLayersError(RuntimeError):
    """Raised when dataLayers:get or the follow-up TIFF GET fails.
    Distinct exception so callers can distinguish 'cheap K.3c missed'
    (silent miss) from 'expensive K.3c+ blew up' (user paid for
    something and got an error)."""


def fetch_data_layers(
    lat: float, lng: float, *,
    radius_m: float = 25.0,
    view: str = DEFAULT_VIEW,
    quality: str = "LOW",
    pixel_size_m: float = 0.25,
    api_key: Optional[str] = None,
) -> DataLayersResult:
    """Hit dataLayers:get; return parsed layer URLs.

    Args:
        lat, lng: building lat/lng (Mapbox-resolved coords).
        radius_m: radius (m) of the square area returned. Default 25 m
            → 50×50 m view, which puts the target house in the centre
            with 1-2 neighbouring lots visible — dense subdivisions
            (Frisco, Phoenix tract homes) would otherwise pack 8-10
            houses into a 100m frame and the target gets lost. Bump
            to 50-100 for rural / large-lot homes where the building
            doesn't fill its plot. Google clamps max to 100 (LOW),
            175 (MEDIUM), 250 (HIGH).
        view: Solar API `view` enum. Default
            IMAGERY_AND_ANNUAL_FLUX_LAYERS — cheapest combo that has
            RGB + annual flux + mask.
        quality: minimum imageryQuality floor (LOW accepts every site).
        pixel_size_m: spatial resolution. 0.25 m / px keeps the imagery
            crisp at the tighter default radius (200×200 px @ 25m =
            same pixel density as the legacy 50m / 0.5m configuration).
        api_key: override key (test injection). Otherwise reads
            PVESS_GOOGLE_SOLAR_KEY.

    Raises:
        DataLayersError: missing key / HTTP failure / building-not-found.
    """
    key = api_key or get_google_solar_key()
    if not key:
        raise DataLayersError(
            "PVESS_GOOGLE_SOLAR_KEY not set — dataLayers requires the same "
            "API key as buildingInsights. See .env.example."
        )
    params = {
        "location.latitude": f"{lat:.6f}",
        "location.longitude": f"{lng:.6f}",
        "radiusMeters": str(radius_m),
        "view": view,
        "requiredQuality": quality,
        "pixelSizeMeters": str(pixel_size_m),
        "key": key,
    }
    try:
        payload = http_get_json(_DATA_LAYERS_URL, params=params,
                                timeout=15.0)
    except ProviderError as exc:
        msg = str(exc)
        if "HTTP 404" in msg:
            raise DataLayersError(
                "Google Solar dataLayers found no building at this "
                "lat/lng (coverage gap or new construction)."
            ) from exc
        raise DataLayersError(f"dataLayers:get failed: {exc}") from exc

    return DataLayersResult.from_payload(payload)


def download_layer_bytes(
    url: str, *, api_key: Optional[str] = None, timeout: float = 30.0,
) -> bytes:
    """GET a signed layer URL → raw bytes (GeoTIFF for RGB/flux/mask).

    Why this isn't a `provider`: the URL is keyed (no JSON, no auth
    header), short-lived (signed for ~1 hour), and the response is
    multi-MB binary — none of the lookup cache patterns apply. The
    renderer calls this directly with a freshly-resolved URL.

    Raises DataLayersError on any network/HTTP problem.
    """
    import requests
    key = api_key or get_google_solar_key()
    if not key:
        raise DataLayersError(
            "PVESS_GOOGLE_SOLAR_KEY not set — required for signed-URL fetch"
        )
    # Google's signed layer URLs accept the key as ?key=… (the same
    # auth surface the orchestrator uses for everything else).
    try:
        resp = requests.get(url, params={"key": key}, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        raise DataLayersError(f"layer fetch crashed: {exc}") from exc
    if resp.status_code >= 400:
        raise DataLayersError(
            f"layer fetch HTTP {resp.status_code}: {resp.text[:200]}"
        )
    return resp.content
