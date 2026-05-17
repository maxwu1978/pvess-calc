"""ESS battery datasheet registry.

Each entry produces `pvess_calc.schema.Battery` kwargs (without quantity;
project decides the count).

**HV battery entries** (K.4.6.2 — in-house, Growatt APX) pair with
HV-input hybrid inverters (Megarevo R-series, Growatt MIN-X, Sol-Ark
12K). DC-coupled at the inverter, no separate AC bridge — simpler
wiring than the AC-coupled Tesla / FranklinWH approach.
"""
from __future__ import annotations

from ..schema import Battery

BATTERIES: dict[str, dict] = {
    "tesla_powerwall_3": dict(
        brand="Tesla",
        model="Powerwall 3",
        nominal_voltage=240.0,           # AC-coupled (integrated inverter)
        capacity_kwh_each=13.5,
    ),
    "eg4_lifepower4_v2": dict(
        brand="EG4",
        model="LifePower4 V2",
        nominal_voltage=51.2,
        capacity_kwh_each=5.12,
    ),
    "franklinwh_apower": dict(
        brand="FranklinWH",
        model="aPower",
        nominal_voltage=240.0,           # AC-coupled
        capacity_kwh_each=13.6,
    ),
    "enphase_iq_battery_5p": dict(
        brand="Enphase",
        model="IQ Battery 5P",
        nominal_voltage=240.0,           # AC-coupled with integrated micros
        capacity_kwh_each=5.0,
    ),
    # ─── HV battery stacks (K.4.6.2 — pair w/ HV hybrid inverter) ─────
    "inhouse_16kwh_hv": dict(
        brand="InHouse",
        model="HV-16",
        nominal_voltage=400.0,           # HV stack (typical 200-500 V range)
        capacity_kwh_each=16.0,
    ),
    "growatt_apx_20kwh": dict(
        brand="Growatt",
        model="APX HV 20K",
        nominal_voltage=400.0,           # HV stack
        capacity_kwh_each=20.0,
    ),
}


# Per-unit price (USD).
#   * Wholesale for installer-direct sources (in-house, Growatt, EG4)
#   * Retail for premium-tier resellable (Tesla, FranklinWH, Enphase)
# When the project's `installer_cost_overrides` block (K.4.6.3,
# planned) is active, economics.py reads from here instead of the
# NREL benchmark $950/kWh average.
BATTERY_PRICES_USD: dict[str, float] = {
    "tesla_powerwall_3": 9300,
    "eg4_lifepower4_v2": 1700,
    "franklinwh_apower": 8500,
    "enphase_iq_battery_5p": 4200,
    "inhouse_16kwh_hv": 6000,        # in-house BOM cost (2026-05-17)
    "growatt_apx_20kwh": 10000,      # wholesale ($500/kWh)
}


def get_battery(ref: str) -> Battery:
    if ref not in BATTERIES:
        raise KeyError(
            f"Unknown battery ref {ref!r}. "
            f"Available: {sorted(BATTERIES.keys())}"
        )
    # Battery needs `quantity`; caller fills that in.
    return Battery(quantity=1, **BATTERIES[ref])
