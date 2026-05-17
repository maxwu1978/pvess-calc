"""NREL PVWatts v8 provider — annual solar production estimate at the
given lat/lng.

PVWatts answers: "if you install 1 kW DC of PV here, how much AC kWh
will it produce per year, and what's the average daily solar resource
(kWh/m²/day)?" — exactly the input the K.4 customer-summary needs to
turn 'modules: 24' into 'expected $/year saved'.

Endpoint: https://developer.nrel.gov/api/pvwatts/v8.json
Docs:     https://developer.nrel.gov/docs/solar/pvwatts/v8/

This provider depends on **lat/lng already being in `ProviderResult.fields`**,
which means it MUST be ordered AFTER the geocoder in the orchestrator
chain. When lat/lng aren't present, it returns confidence='miss' with
a clear note — no useless calls.

Returned fields:
  * solar_irradiance_kwh_m2_day — annual-average daily solar resource
  * annual_energy_kwh_per_kw    — annual AC energy per 1 kW DC system

Both are normalised "per 1 kW DC" so the wizard / report can scale by
the actual `pv_array.modules × power_w` without re-querying.
"""
from __future__ import annotations

from typing import Any

from ..address import ParsedAddress
from ..config import get_nrel_api_key
from ._http import ProviderError, http_get_json
from .base import ProviderResult


_PVWATTS_URL = "https://developer.nrel.gov/api/pvwatts/v8.json"


def nrel_pvwatts(
    address: ParsedAddress,
    *,
    lat_lng: tuple[float, float] | None = None,
) -> ProviderResult:
    """Run a PVWatts query. `lat_lng` may be supplied directly (tests +
    cases where another provider already geocoded); otherwise this
    returns 'miss' because PVWatts needs coordinates."""
    key = get_nrel_api_key()
    if not key:
        return ProviderResult(
            source="nrel-pvwatts", confidence="miss",
            note=("PVESS_NREL_API_KEY env var not set — request a free key "
                  "at https://developer.nrel.gov/signup/ to enable annual "
                  "energy estimates."),
        )

    if not lat_lng:
        return ProviderResult(
            source="nrel-pvwatts", confidence="miss",
            note=("PVWatts requires lat/lng — Mapbox geocoder must run "
                  "before this provider."),
        )

    lat, lng = lat_lng
    # PVWatts mandatory params + sensible residential defaults. The
    # caller doesn't pick these — what we want here is *per-1-kW-DC*
    # output that downstream scaling can multiply by the actual system
    # size. All defaults match NREL's "typical residential rooftop"
    # assumption sheet.
    params = {
        "api_key": key,
        "lat": f"{lat:.4f}",
        "lon": f"{lng:.4f}",
        "system_capacity": "1",       # per-1-kW baseline; scale at report
        "azimuth": "180",             # south-facing
        "tilt": "20",                 # ~latitude rule of thumb shy
        "array_type": "1",            # 1 = fixed roof mount
        "module_type": "1",           # 1 = standard crystalline
        "losses": "14",               # NREL default total system loss %
        "timeframe": "monthly",
    }
    try:
        payload = http_get_json(_PVWATTS_URL, params=params)
    except ProviderError as exc:
        return ProviderResult(
            source="nrel-pvwatts", confidence="miss",
            note=f"PVWatts API failed: {exc}",
        )

    return _payload_to_result(payload)


def _payload_to_result(payload: dict[str, Any]) -> ProviderResult:
    """Pull the two fields the wizard cares about. PVWatts is verbose
    (returns per-month arrays, station info, station distance) — we
    keep only the annualised top-level numbers and let the K.4 summary
    re-query for monthly detail if needed."""
    outputs = payload.get("outputs") or {}
    station = (payload.get("station_info") or {}).get("location") or ""

    ac_annual = outputs.get("ac_annual")
    solrad_annual = outputs.get("solrad_annual")
    if ac_annual is None or solrad_annual is None:
        return ProviderResult(
            source="nrel-pvwatts", confidence="miss",
            note=("PVWatts response missing ac_annual / solrad_annual — "
                  "possibly an out-of-coverage location (PVWatts is US + "
                  "territories only)."),
        )

    fields = {
        "annual_energy_kwh_per_kw": float(ac_annual),     # already per-1-kW
        "solar_irradiance_kwh_m2_day": float(solrad_annual),
    }
    note = f"NREL PVWatts v8"
    if station:
        note += f" (TMY station: {station})"

    return ProviderResult(
        source="nrel-pvwatts",
        fields=fields,
        confidence="high",
        note=note,
    )
