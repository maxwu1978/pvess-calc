"""PV module datasheet registry.

Each entry is the kwargs dict for `pvess_calc.schema.PvModule`. Values are
copied from manufacturer datasheets; verify against the latest spec sheet
before submitting to AHJ.
"""
from __future__ import annotations

from ..schema import PvModule

MODULES: dict[str, dict] = {
    "talesun_tp7g54m_415": dict(
        brand="Talesun",
        model="TP7G54M-415",
        power_w=415.0,
        voc_stc=37.55,
        isc_stc=14.04,
        voc_temp_coeff_pct_per_c=-0.25,
        isc_temp_coeff_pct_per_c=0.045,
    ),
    "canadian_solar_hiku7_595": dict(
        brand="Canadian Solar",
        model="HiKu7 CS7N-595MS",
        power_w=595.0,
        voc_stc=52.6,
        isc_stc=14.20,
        voc_temp_coeff_pct_per_c=-0.26,
        isc_temp_coeff_pct_per_c=0.050,
    ),
    "rec_alpha_pure_410": dict(
        brand="REC",
        model="Alpha Pure REC410AA",
        power_w=410.0,
        voc_stc=44.7,
        isc_stc=11.46,
        voc_temp_coeff_pct_per_c=-0.24,
        isc_temp_coeff_pct_per_c=0.044,
    ),
    # Backward-compat alias the existing demo projects use.
    "generic_420": dict(
        brand="Generic",
        model="MONO-420-144",
        power_w=420.0,
        voc_stc=49.5,
        isc_stc=13.8,
        voc_temp_coeff_pct_per_c=-0.28,
        isc_temp_coeff_pct_per_c=0.048,
    ),
}


# Per-unit retail price (USD) for BOM estimation. Approximate distributor
# pricing as of 2024-2025 — verify before sending quotes to clients.
MODULE_PRICES_USD: dict[str, float] = {
    "talesun_tp7g54m_415": 145,
    "canadian_solar_hiku7_595": 210,
    "rec_alpha_pure_410": 195,
    "generic_420": 150,
}


def get_module(ref: str) -> PvModule:
    if ref not in MODULES:
        raise KeyError(
            f"Unknown PV module ref {ref!r}. "
            f"Available: {sorted(MODULES.keys())}"
        )
    return PvModule(**MODULES[ref])
