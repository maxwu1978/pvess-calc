"""Lookup service — turn a free-text site address into a structured set
of site characteristics the wizard can pre-fill.

Design:

  * **Orchestrator pattern.** `resolve(address)` calls each provider in
    declared order, merges the `ProviderResult.fields`, and returns a
    single `LookupResult` to the wizard / CLI. Failures of one provider
    never block another — every provider returns a result even on miss.

  * **Offline-first.** Phase K.3a ships purely static JSON datasets.
    The orchestrator therefore needs no API key, no network, and no
    rate limit. Phase K.3b adds online providers (Mapbox geocoding,
    NREL PVWatts) behind env-var keys — they slot into the same
    `Provider` Protocol, so the orchestrator code does not change.

  * **Cached.** Each successful `resolve()` writes its result to
    `~/.pvess/cache/lookup/<sha>.json` with a 24-hour TTL. Re-running
    the wizard for the same address (e.g. after `ctrl-C, --resume`) is
    free and works offline even if a future online provider was down.

  * **Confidence-aware.** Every field carries provenance: which provider
    supplied it, what confidence level, and a human-readable note. The
    wizard surfaces low-confidence fields as "review me" defaults
    instead of silent assumptions.

Public API:

    >>> from pvess_calc.lookup import resolve
    >>> r = resolve("2500 Hollow Hill Lane, Lewisville, TX 75067")
    >>> r.fields["utility_name"]
    'Oncor Electric Delivery'
    >>> r.fields["nec_edition"]
    '2020'
    >>> r.field_sources["utility_name"]
    'utility-offline'
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from . import cache
from .address import ParsedAddress, parse_address
from .providers import (
    Provider,
    ProviderResult,
    static_ahj,
    static_ashrae,
    static_climate,
    static_nec,
    static_utility,
    static_utility_rate,
)
from .providers.google_solar import google_solar
from .providers.mapbox_geocode import mapbox_geocode
from .providers.nrel_pvwatts import nrel_pvwatts


# Declared in priority order: later providers override earlier on
# conflicting keys.
#
# K.3a (offline) providers run first — they're cheap, deterministic,
# and produce the bulk of the wizard's pre-fill set. K.3b online
# providers run AFTER so they can read the geocoded lat/lng out of the
# accumulated results (PVWatts in particular needs coords from Mapbox).
# K.4 adds `static_utility_rate` (offline retail $/kWh per city) — used
# by `customer/economics.py` for first-pass bill-savings estimates.
#
# Each online provider is a no-op when its env-var key is missing — so
# in the default config (no keys set) this chain behaves IDENTICALLY to
# the K.3a-only chain. Pure additive.
DEFAULT_PROVIDERS: tuple[Provider, ...] = (
    static_ashrae,
    static_utility,
    static_utility_rate,
    static_ahj,
    static_climate,
    static_nec,
    mapbox_geocode,
    nrel_pvwatts,
    # K.3c: Google Solar API → per-face roof geometry. Same dependency
    # pattern as nrel_pvwatts (reads lat/lng from mapbox via the
    # _call_provider sniffer). When PVESS_GOOGLE_SOLAR_KEY is missing
    # this provider returns 'miss' and the chain falls back to the
    # site-survey input path — pure additive.
    google_solar,
)


@dataclass
class LookupResult:
    """Merged output of every provider for one address."""
    address: ParsedAddress
    fields: dict[str, Any] = field(default_factory=dict)
    field_sources: dict[str, str] = field(default_factory=dict)
    field_confidence: dict[str, str] = field(default_factory=dict)
    provider_results: list[ProviderResult] = field(default_factory=list)

    @property
    def hit_count(self) -> int:
        """Number of providers that found anything."""
        return sum(1 for r in self.provider_results if r.hit)

    def to_dict(self) -> dict[str, Any]:
        """Cache-friendly serialisation."""
        return {
            "address": {
                "raw": self.address.raw,
                "street": self.address.street,
                "city": self.address.city,
                "state": self.address.state,
                "zip_code": self.address.zip_code,
            },
            "fields": self.fields,
            "field_sources": self.field_sources,
            "field_confidence": self.field_confidence,
            "provider_results": [
                {"source": r.source, "fields": r.fields,
                 "confidence": r.confidence, "note": r.note}
                for r in self.provider_results
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LookupResult":
        addr_data = data.get("address", {})
        address = ParsedAddress(
            raw=addr_data.get("raw", ""),
            street=addr_data.get("street"),
            city=addr_data.get("city"),
            state=addr_data.get("state"),
            zip_code=addr_data.get("zip_code"),
        )
        prs = [
            ProviderResult(
                source=p["source"],
                fields=p.get("fields", {}),
                confidence=p.get("confidence", "low"),
                note=p.get("note", ""),
            )
            for p in data.get("provider_results", [])
        ]
        return cls(
            address=address,
            fields=data.get("fields", {}),
            field_sources=data.get("field_sources", {}),
            field_confidence=data.get("field_confidence", {}),
            provider_results=prs,
        )


# ─── Orchestrator ──────────────────────────────────────────────────────────


def resolve(
    raw_address: str,
    *,
    providers: Optional[Iterable[Provider]] = None,
    use_cache: bool = True,
) -> LookupResult:
    """Resolve `raw_address` to a `LookupResult`. Cached for 24h.

    Pass `providers=` to override the default chain (used by tests to
    pin a deterministic set, or by future code to opt-in to online
    providers)."""
    chain: tuple[Provider, ...] = (
        tuple(providers) if providers is not None else DEFAULT_PROVIDERS
    )
    cache_key = _cache_key(raw_address, chain)

    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return LookupResult.from_dict(cached)

    address = parse_address(raw_address)
    result = LookupResult(address=address)

    for provider in chain:
        try:
            pr = _call_provider(provider, address, result.fields)
        except Exception as exc:   # provider error is non-fatal
            pr = ProviderResult(
                source=getattr(provider, "__name__", "unknown-provider"),
                confidence="miss",
                note=f"Provider crashed: {exc!r}",
            )
        result.provider_results.append(pr)
        if pr.hit:
            for k, v in pr.fields.items():
                result.fields[k] = v
                result.field_sources[k] = pr.source
                result.field_confidence[k] = pr.confidence

    if use_cache:
        cache.put(cache_key, result.to_dict())
    return result


def _cache_key(raw_address: str, providers: tuple[Provider, ...]) -> str:
    """Cache key includes the provider chain so swapping providers
    invalidates stale entries."""
    chain_id = ",".join(getattr(p, "__name__", repr(p)) for p in providers)
    return f"{raw_address.strip().lower()}|{chain_id}"


def _call_provider(
    provider: Provider, address: ParsedAddress, prior_fields: dict[str, Any],
) -> ProviderResult:
    """Call a provider with the address. Providers that accept extra
    inferred state (e.g., `nrel_pvwatts` needs lat/lng from a prior
    geocoder) opt in via a known kwarg; we sniff for it and supply it
    only when present.

    This keeps the `Provider` Protocol minimal — most providers stay as
    pure `(ParsedAddress) -> ProviderResult` functions and don't pay
    any complexity tax."""
    import inspect

    sig = inspect.signature(provider)
    if "lat_lng" in sig.parameters:
        lat = prior_fields.get("latitude")
        lng = prior_fields.get("longitude")
        lat_lng = (lat, lng) if lat is not None and lng is not None else None
        return provider(address, lat_lng=lat_lng)   # type: ignore[call-arg]
    return provider(address)


# ─── Field → wizard-yaml-path mapping ──────────────────────────────────────
#
# Used by `pvess-init --address` to translate lookup output into the
# flat answer dict the wizard runner consumes. Keys are LookupResult
# field names; values are the WIZARD_FIELDS yaml_path.

LOOKUP_FIELD_TO_YAML_PATH: dict[str, str] = {
    "utility_name":              "project.utility",
    "ahj_name":                  "project.ahj",
    "nec_edition":               "project.nec_edition",
    "ashrae_2pct_min_c":         "pv_array.ashrae_2pct_min_c",
    # K.7 [3/4]: per-state export tariff recommendation drives K.4
    # customer-summary ROI math. CA → ca_nem3, HI → hi_self_consumption,
    # else → 1to1_nem.
    "recommended_export_tariff": "loads.export_tariff_model",
    # NB: ashrae_2pct_max_c maps to routing.ambient_temp_c only at
    # wizard pre-fill time — see wizard/runner.py prefill logic.
}


__all__ = [
    "resolve",
    "LookupResult",
    "DEFAULT_PROVIDERS",
    "LOOKUP_FIELD_TO_YAML_PATH",
    "ParsedAddress",
    "parse_address",
]
