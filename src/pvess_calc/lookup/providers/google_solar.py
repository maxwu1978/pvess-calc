"""K.3c — Google Solar API provider.

What it does: turns a lat/lng into a **per-roof-face geometry list**
that maps 1:1 onto our K.2.6c `site.roof_sections` schema. Replaces the
$20-40/property EagleView roof report with a $0.05 API call for the
calc-engine path (EagleView's 18-page PDF stays as an optional permit
attachment when the AHJ demands one).

Endpoint: `buildingInsights:findClosest` (Solar API v1, GA 2024).
Docs:     https://developers.google.com/maps/documentation/solar/building-insights

The endpoint returns, for the building closest to a lat/lng:

  * `roofSegmentStats[]` — per-face pitch / azimuth / area / sunshine
  * `solarPotential.maxArrayPanelsCount` — Google's auto-placed panel cap
  * `imageryQuality` — HIGH / MEDIUM / LOW (HIGH = aerial photogrammetry,
    LOW = derived from DSM only, no per-face confidence)
  * `imageryDate` — when the imagery was captured (months-to-years ago)

We pick up the per-face geometry, name each face by 8-direction compass
(South Roof, Southwest Roof, …), and emit a `roof_sections` field
ready for the wizard / yaml writer to consume.

Caveats deliberately surfaced upstream:
  * Google returns axis-aligned bounding boxes only — no K.2.7 polygon
    vertices. Faces are emitted as `shape: "rect"`. Hip / L-shape roofs
    therefore approximate to a same-area rectangle; for those a manual
    EagleView pass at submit-time still wins.
  * Building lookup is by closest-to-lat/lng; on townhomes / duplex
    rows the API occasionally returns an adjacent unit. Always
    eyeball the canonical_address vs Google's returned center coords.
  * imageryQuality LOW → we downgrade confidence to "low" so the
    wizard surfaces the field as REVIEW-ME, not silent-assume.

Returned fields:
  * `roof_sections` — list of dicts (see `_segment_to_section` for the
     exact shape; matches `schema.RoofSection` field names so the
     wizard's pre-fill can pass them straight through pydantic)
  * `google_solar_imagery_quality` — "HIGH" | "MEDIUM" | "LOW"
  * `google_solar_imagery_date` — ISO "YYYY-MM-DD"
  * `google_solar_max_panels` — int, Google's auto-placement panel count
  * `google_solar_whole_roof_area_m2` — float, total roof area (m²)

When `PVESS_GOOGLE_SOLAR_KEY` is missing this provider returns
confidence='miss' with a clear note — the offline chain handles the
rest and the wizard continues unaffected.
"""
from __future__ import annotations

from typing import Any

from ..address import ParsedAddress
from ..config import get_google_solar_key
from ._http import ProviderError, http_get_json
from .base import ProviderResult


_GOOGLE_SOLAR_URL = (
    "https://solar.googleapis.com/v1/buildingInsights:findClosest"
)

# Google's confidence band → our internal scale.
_QUALITY_TO_CONFIDENCE: dict[str, str] = {
    "HIGH":   "high",
    "MEDIUM": "medium",
    "LOW":    "low",
}

# Compass directions for face naming. Index = round(azimuth / 45) % 8.
_COMPASS_8: tuple[str, ...] = (
    "North", "Northeast", "East", "Southeast",
    "South", "Southwest", "West", "Northwest",
)

# Square-feet per square-meter (NIST exact).
_M2_TO_FT2: float = 10.7639104167


def google_solar(
    address: ParsedAddress,
    *,
    lat_lng: tuple[float, float] | None = None,
) -> ProviderResult:
    """Run a Solar API buildingInsights query. Like nrel_pvwatts, this
    provider needs lat/lng from a prior geocoder — Mapbox supplies it
    via the orchestrator's `_call_provider` sniffer.
    """
    key = get_google_solar_key()
    if not key:
        return ProviderResult(
            source="google-solar", confidence="miss",
            note=("PVESS_GOOGLE_SOLAR_KEY env var not set — enable Solar API "
                  "at https://console.cloud.google.com/apis/library/solar.googleapis.com "
                  "and create a key to populate roof_sections automatically."),
        )

    if not lat_lng or lat_lng[0] is None or lat_lng[1] is None:
        return ProviderResult(
            source="google-solar", confidence="miss",
            note=("Solar API requires lat/lng — Mapbox geocoder must run "
                  "before this provider."),
        )

    lat, lng = lat_lng
    params = {
        "location.latitude": f"{lat:.6f}",
        "location.longitude": f"{lng:.6f}",
        # LOW floor: accept every building Google has data for, no matter
        # how confident Google is in the imagery. We do our OWN confidence
        # downgrade afterward by mapping `imageryQuality` (HIGH/MEDIUM/LOW)
        # to provider confidence (high/medium/low). Asking Google to
        # pre-filter at MEDIUM would lose us the entire response for
        # rural / older-imagery sites — degraded data is more useful than
        # no data, and we surface the degradation via the wizard's
        # REVIEW-ME flag.
        "requiredQuality": "LOW",
        "key": key,
    }
    try:
        payload = http_get_json(_GOOGLE_SOLAR_URL, params=params)
    except ProviderError as exc:
        # Special-case 404: the API returns 404 NOT_FOUND when no
        # building exists within the search radius (rural / new
        # construction). Keep it as 'miss' with a more actionable note.
        msg = str(exc)
        if "HTTP 404" in msg:
            return ProviderResult(
                source="google-solar", confidence="miss",
                note=("Google Solar API found no building at this lat/lng "
                      "(coverage gap or new construction). EagleView fallback "
                      "recommended for this site."),
            )
        return ProviderResult(
            source="google-solar", confidence="miss",
            note=f"Google Solar API failed: {exc}",
        )

    return _payload_to_result(payload)


def _payload_to_result(payload: dict[str, Any]) -> ProviderResult:
    """Translate one buildingInsights:findClosest response →
    ProviderResult. The `roofSegmentStats[]` list is the meat."""
    solar = payload.get("solarPotential") or {}
    segments = solar.get("roofSegmentStats") or []

    if not segments:
        return ProviderResult(
            source="google-solar", confidence="miss",
            note=("Google Solar API returned no roofSegmentStats for the "
                  "closest building (probably a multi-family / commercial "
                  "structure outside Solar API residential coverage)."),
        )

    quality = (payload.get("imageryQuality") or "LOW").upper()
    confidence = _QUALITY_TO_CONFIDENCE.get(quality, "low")

    # Name faces by compass direction; suffix duplicates "#2" / "#3"
    # so the user can tell two south-facing dormers apart.
    names_used: dict[str, int] = {}
    roof_sections: list[dict[str, Any]] = []
    for seg in segments:
        section = _segment_to_section(seg, names_used)
        if section is not None:
            roof_sections.append(section)

    if not roof_sections:
        # Every segment failed schema mapping — possible if Google
        # returns a degenerate response with NaN areas.
        return ProviderResult(
            source="google-solar", confidence="miss",
            note="Google Solar API returned segments but none could be mapped.",
        )

    fields: dict[str, Any] = {
        "roof_sections": roof_sections,
        "google_solar_imagery_quality": quality,
    }

    imagery_date = payload.get("imageryDate") or {}
    y, m, d = imagery_date.get("year"), imagery_date.get("month"), imagery_date.get("day")
    if y and m and d:
        fields["google_solar_imagery_date"] = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    # `maxArrayPanelsCount` is documented as int but defensive against
    # JSON serializers that emit `76.0` instead of `76` for whole numbers.
    # Negative values are nonsense (Google never emits them but worth
    # guarding so a malformed response can't pollute the wizard yaml).
    max_panels = solar.get("maxArrayPanelsCount")
    if isinstance(max_panels, (int, float)) and max_panels >= 0:
        fields["google_solar_max_panels"] = int(max_panels)

    whole = solar.get("wholeRoofStats") or {}
    area_m2 = whole.get("areaMeters2")
    if isinstance(area_m2, (int, float)):
        fields["google_solar_whole_roof_area_m2"] = float(area_m2)

    note = (
        f"Google Solar API → {len(roof_sections)} face(s), "
        f"quality={quality}"
    )
    if "google_solar_imagery_date" in fields:
        note += f", imagery {fields['google_solar_imagery_date']}"

    return ProviderResult(
        source="google-solar", fields=fields,
        confidence=confidence, note=note,
    )


def _segment_to_section(
    seg: dict[str, Any], names_used: dict[str, int],
) -> dict[str, Any] | None:
    """Map one Google `roofSegmentStats` entry → our RoofSection dict.

    The output dict's keys match `schema.RoofSection` field names so a
    downstream `RoofSection(**dict)` would validate as-is. We pick a
    same-area square (sqrt(area)) for `width_ft` / `height_ft` because
    Google doesn't tell us aspect ratio of the underlying photogrammetry
    polygon — only an axis-aligned bounding box that includes nearby
    obstructions. Designer fine-tunes during site survey.
    """
    pitch = seg.get("pitchDegrees")
    az = seg.get("azimuthDegrees")
    stats = seg.get("stats") or {}
    area_m2 = stats.get("areaMeters2")
    if pitch is None or az is None or area_m2 is None or area_m2 <= 0:
        return None

    pitch = float(pitch)
    az = float(az) % 360.0
    area_ft2 = float(area_m2) * _M2_TO_FT2

    # Same-area square fallback. Real width × height tweaked on-site or
    # via the wizard's "fix this section" step.
    side_ft = round(area_ft2 ** 0.5, 1)

    name = _name_from_azimuth(az, names_used)

    return {
        "name":            name,
        "roof_type":       "Comp Shingle",   # Google doesn't return material
        "pitch_deg":       round(pitch, 1),
        "azimuth_deg":     round(az, 1),
        "width_ft":        side_ft,
        "height_ft":       side_ft,
        "module_count":    0,                # designer fills after layout
        "shape":           "rect",           # see module docstring caveat
    }


def _name_from_azimuth(az: float, names_used: dict[str, int]) -> str:
    """0=N, 90=E, 180=S, 270=W → 8-direction name with disambiguating
    suffix when a direction recurs. Two south faces → 'South Roof' +
    'South Roof #2'."""
    idx = round(az / 45.0) % 8
    base = f"{_COMPASS_8[idx]} Roof"
    count = names_used.get(base, 0) + 1
    names_used[base] = count
    return base if count == 1 else f"{base} #{count}"
