"""Provider plug-ins for the lookup orchestrator.

A provider is a callable that takes a `ParsedAddress` and returns a
`ProviderResult` (a dict of fields the provider was able to fill, plus
a confidence string and a source label). The orchestrator merges all
provider outputs in declared order — later providers can override
earlier ones if the user wants e.g. a high-confidence Mapbox geocode
to win over our coarse state-level default.

Offline providers (this Phase K.3a):
  * static_ashrae   → ashrae_2pct_min_c, ashrae_2pct_max_c
  * static_utility  → utility_name, territory_type
  * static_ahj      → ahj_name, permit_portal
  * static_climate  → iecc_climate_zone
  * static_nec      → nec_edition (state default + override note)

Online providers (Phase K.3b, behind env-var API keys):
  * mapbox_geocode  → coordinates (lat, lng), county
  * nrel_pvwatts    → solar_irradiance_kwh_m2_day
  * google_solar    → roof_sections[] (K.3c — per-face pitch / azimuth
                     / area from Google Solar API; replaces $20-40
                     EagleView for the calc-engine path)
  * eia_utility     → finer-grained utility-by-zip
"""
from .base import Provider, ProviderResult
from .static_ahj import static_ahj
from .static_ashrae import static_ashrae
from .static_climate import static_climate
from .static_nec import static_nec
from .static_utility import static_utility
from .static_utility_rate import static_utility_rate


__all__ = [
    "Provider",
    "ProviderResult",
    "static_ahj",
    "static_ashrae",
    "static_climate",
    "static_nec",
    "static_utility",
    "static_utility_rate",
]
