"""Hybrid inverter datasheet registry.

Each entry produces `pvess_calc.schema.Inverter` kwargs (without quantity
or per_unit; those stay in inputs.yaml as project-specific).

**Wholesale-priced** entries (K.4.6.2 — Megarevo / Growatt / Hoymiles)
reflect installer-direct pricing, NOT retail. Use these for cost-override
when the project ships under the installer's real BOM, not the NREL
benchmark. Retail-tier brands (Tesla, FranklinWH) keep retail prices
because they're typically MSRP-resold.
"""
from __future__ import annotations

from ..schema import Inverter

INVERTERS: dict[str, dict] = {
    "sol_ark_12k": dict(
        brand="Sol-Ark",
        model="12K-2P-N",
        ac_output_v=240.0,
        ac_output_a=50.0,            # 12 kW / 240 V = 50 A continuous
        dc_afci="integrated",
        ul1699b_listed=True,
    ),
    # ─── Megarevo hybrid series (Chinese OEM, DFW installer staple) ───
    "megarevo_r8klna": dict(
        brand="Megarevo",
        model="R8KLNA",
        ac_output_v=240.0,
        ac_output_a=33.3,            # 8 kW / 240 V
        dc_afci="integrated",
        ul1699b_listed=True,
    ),
    "megarevo_r11klna": dict(
        brand="Megarevo",
        model="R11KLNA",
        ac_output_v=240.0,
        ac_output_a=45.8,            # 11 kW / 240 V — sweet spot for 14 kW DC array
    ),
    # ─── Growatt MIN 11.4K hybrid (HV battery compatible) ─────────────
    "growatt_min11400tl_xh_us": dict(
        brand="Growatt",
        model="MIN 11400TL-XH-US",
        ac_output_v=240.0,
        ac_output_a=48.0,            # datasheet max output current @ 240 V
        dc_afci="integrated",
        ul1699b_listed=True,
    ),
    # Back-compat alias kept for earlier K.4.6 configs.
    "growatt_min11000tl_x": dict(
        brand="Growatt",
        model="MIN 11000TL-X",
        ac_output_v=240.0,
        ac_output_a=45.8,            # legacy 11 kW alias
    ),
    # ─── Hoymiles HYS-LV 11.5K (LV battery side) ─────────────────────
    "hoymiles_hys_11_5lv_usg1": dict(
        brand="Hoymiles",
        model="HYS-11.5LV-USG1",
        ac_output_v=240.0,
        ac_output_a=48.0,
        dc_afci="integrated",
        ul1699b_listed=True,
    ),
    # Back-compat alias kept for earlier K.4.6 configs.
    "hoymiles_hys_lv_11k": dict(
        brand="Hoymiles",
        model="HYS-LV-11K",
        ac_output_v=240.0,
        ac_output_a=45.8,            # legacy 11 kW alias
    ),
    "tesla_powerwall_3": dict(
        brand="Tesla",
        model="Powerwall 3 (integrated)",
        ac_output_v=240.0,
        ac_output_a=48.0,            # 11.5 kW continuous backup
        per_unit=True,               # integrated inverter, 1 per battery
        dc_afci="integrated",
        ul1699b_listed=True,
    ),
    "enphase_iq8m": dict(
        brand="Enphase",
        model="IQ8M-72-2-US",
        ac_output_v=240.0,
        ac_output_a=1.36,            # microinverter — typically many per project
        dc_afci="integrated",
        ul1699b_listed=True,
    ),
    "generic_8k_hybrid": dict(
        brand="Generic",
        model="8K Hybrid",
        ac_output_v=240.0,
        ac_output_a=33.0,
    ),
}


# Per-unit wholesale price (USD) — installer's BOM cost, not retail.
# Used when the project's `installer_cost_overrides` block routes
# economics through real wholesale (K.4.6.3, planned). Retail-tier
# brands (Tesla, Sol-Ark, Enphase) keep retail price because that's
# how they ship to most installers.
INVERTER_PRICES_USD: dict[str, float] = {
    "sol_ark_12k": 5500,
    "megarevo_r8klna": 1600,    # wholesale (2026-05-17 DFW installer)
    "megarevo_r11klna": 2000,   # wholesale (~25% premium for +3 kW vs R8)
    "growatt_min11400tl_xh_us": 2500,
    "growatt_min11000tl_x": 2500,
    "hoymiles_hys_11_5lv_usg1": 2200,
    "hoymiles_hys_lv_11k": 2200,
    "tesla_powerwall_3": 9300,  # retail (integrated battery+inverter)
    "enphase_iq8m": 235,
    "generic_8k_hybrid": 3500,
}


def get_inverter(ref: str) -> Inverter:
    if ref not in INVERTERS:
        raise KeyError(
            f"Unknown inverter ref {ref!r}. "
            f"Available: {sorted(INVERTERS.keys())}"
        )
    return Inverter(**INVERTERS[ref])
