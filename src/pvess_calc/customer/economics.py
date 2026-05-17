"""Customer-facing economic estimates.

What this module computes (homeowner language):

  * **Annual production** — how many kWh the PV array will produce per
    year. Driven by NREL PVWatts (when available via K.3b) — falls back
    to a coarse latitude-based estimate when offline.
  * **Monthly bill savings** — production × utility retail rate ÷ 12.
    Assumes 1:1 net-metering for simplicity. NEM 3.0 / export-rate
    nuances live one phase deeper — flagged as a caveat in the PDF.
  * **Annual offset %** — production / household consumption. Needs
    `loads.monthly_kwh` to be 12 values; else returns None and the PDF
    hides this number.
  * **Payback period** — system cost / annual savings. Uses
    `system_cost_usd` if present in inputs (Phase K.4.5 will add a
    proper `cost` block); otherwise a tier-based estimate driven by
    system size.

Deliberately NOT NEC-grade math — every number is "good enough for a
homeowner conversation", clearly labelled as an estimate in the PDF.
Engineering-grade analysis stays in `report/markdown.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..schema import Inputs


# Conservative US-average residential retail electricity price as of
# 2026-Q1 (EIA Electric Power Monthly Table 5.6.A 12-month avg). Used
# only when no city-level rate is available from K.3 lookup.
DEFAULT_USA_AVG_RATE_USD_PER_KWH: float = 0.165

# Per-kW DC residential installed cost (2026 NREL Q1 benchmark, post-IRA).
# Used when the project's yaml carries no explicit `system_cost_usd`.
# Includes PV + ESS + soft costs as a single line — fine for an
# order-of-magnitude payback number, NOT for a real quote.
DEFAULT_INSTALLED_COST_USD_PER_W: float = 3.50    # $/W_DC (NREL Q1-2026)
DEFAULT_ESS_COST_USD_PER_KWH: float = 950.0       # incremental ESS cost

# Federal Investment Tax Credit — Inflation Reduction Act (IRA) 2022.
# Residential ITC: 30% from 2022 through 2032, steps down 2033/2034.
# Applies to BOTH PV and ESS (when ESS ≥ 3 kWh, which every project
# this tool generates satisfies).
FEDERAL_ITC_RATE: float = 0.30

# K.7 [2/4]: export tariff models — fraction of retail rate that the
# utility pays for kWh EXPORTED back to the grid. K.4 customer-summary
# computes:
#     annual_savings = annual_production × (
#         self_consumption_fraction × retail
#       + (1 - self_consumption_fraction) × retail × export_ratio
#     )
# where `retail` is the kWh price the homeowner WOULD have paid.
EXPORT_RATIOS: dict[str, float] = {
    # Classic 1:1 NEM — every exported kWh credits at retail rate.
    # Most of the US still operates under this (≈ 30 states).
    "1to1_nem":            1.00,
    # California NEM 3.0 (effective 2023-04). Exports paid at Avoided
    # Cost Calculator (ACC) tariff — roughly 25-30% of retail in
    # PG&E / SCE / SDG&E territory. We use 0.27 as the residential
    # blended average per CPUC ACC 2024 calibration.
    "ca_nem3":             0.27,
    # Hawaii Customer Self-Supply (CSS) / Smart Export (Rule 14H).
    # Exports paid at ~14 ¢/kWh fixed; HECO retail is ~40 ¢/kWh,
    # so the ratio is ~0.35.
    "hi_self_consumption": 0.35,
    # K.4.6.4 TX REP presets. Texas is fully deregulated — every
    # Retail Electric Provider quotes its own buyback rate, and the
    # SAME PV system can have 50%+ savings variance depending on
    # which REP the homeowner picks. Numbers from 2026 plan filings;
    # update annually as REPs adjust rates.
    "tx_default_oncor":    0.50,     # generic Oncor REP default
    "tx_txu_buyback":      1.00,     # TXU Home Solar Buyback
    "tx_green_mountain":   1.00,     # Green Mountain Renewable Rewards
    "tx_reliant_sun":      0.95,     # Reliant Sun Sustainability
    "tx_rhythm_pure":      0.70,     # Rhythm Pure Energy
}

EXPORT_TARIFF_LABELS: dict[str, str] = {
    "1to1_nem":            "1:1 net metering (most US states)",
    "ca_nem3":             "CA NEM 3.0 ACC tariff (post-2023-04, ~25-30% of retail)",
    "hi_self_consumption": "HI Customer Self-Supply / Smart Export (~14¢/kWh export)",
    # K.4.6.4 TX REP plan labels
    "tx_default_oncor":    "TX Oncor default REP (~50% retail buyback)",
    "tx_txu_buyback":      "TX TXU Home Solar Buyback (1:1 retail)",
    "tx_green_mountain":   "TX Green Mountain Renewable Rewards (1:1 retail)",
    "tx_reliant_sun":      "TX Reliant Sun Sustainability (~95% retail)",
    "tx_rhythm_pure":      "TX Rhythm Pure Energy (~70% retail)",
}

# Coarse latitude-band annual yield (kWh per kW DC per year), used as a
# last-resort fallback when neither NREL nor any other lookup field is
# present. Sourced from NREL TMY3 averages clustered by latitude.
_LATITUDE_BAND_KWH_PER_KW: tuple[tuple[float, float], ...] = (
    # (max_lat_inclusive, annual_kwh_per_kw)
    (28.0, 1700.0),    # Deep south (Miami, Houston)
    (35.0, 1600.0),    # Phoenix, Atlanta latitude
    (40.0, 1450.0),    # St. Louis, NYC latitude
    (45.0, 1300.0),    # Chicago, Boston latitude
    (90.0, 1100.0),    # northern tier
)


@dataclass
class EconomicsResult:
    # System size in DC kW (always computable)
    system_kw_dc: float
    battery_kwh_total: float
    # Production estimate
    annual_production_kwh: float
    production_source: str          # "nrel-pvwatts" / "latitude-fallback"
    # Rate + savings
    utility_rate_usd_per_kwh: float
    rate_source: str                # "lookup-utility-rate" / "usa-average" / "user-provided"
    monthly_bill_savings_usd: float
    annual_bill_savings_usd: float
    # Optional fields (None when inputs insufficient)
    annual_household_kwh: Optional[float]
    offset_pct: Optional[float]
    # K.7 [2/4]: export tariff breakdown
    export_tariff_model: str        # "1to1_nem" / "ca_nem3" / "hi_self_consumption"
    export_tariff_label: str        # human-readable description
    self_consumption_fraction: float
    export_ratio_applied: float     # 0..1, the discount applied to exported kWh
    # Investment / payback
    installed_cost_usd: float
    cost_source: str                # "user-provided" / "benchmark-estimate"
    payback_period_years: Optional[float]   # None if savings = 0
    # K.4.5: same payback after applying the 30% federal ITC. The IRA
    # 30% credit is so universal in residential PV+ESS that showing
    # only the pre-incentive number misrepresents the deal — but we
    # ALSO show the pre-incentive so the customer sees both.
    cost_after_itc_usd: float
    payback_after_itc_years: Optional[float]
    # K.8: per-face production breakdown when site.roof_sections is
    # populated. Empty list = single-orientation (system-aggregate path);
    # blended_derate = None in that case too.
    itc_rate_used: float
    production_breakdown: list = field(default_factory=list)
    production_blended_derate: Optional[float] = None


def compute_economics(
    inputs: Inputs,
    *,
    lookup_fields: Optional[dict[str, Any]] = None,
    system_cost_usd_override: Optional[float] = None,
) -> EconomicsResult:
    """Run every customer-economic estimate from one place.

    `lookup_fields` is the merged `LookupResult.fields` dict (the same
    dict the wizard pre-fills from). We probe it for:
      * `annual_energy_kwh_per_kw` (NREL — preferred)
      * `latitude` (Mapbox — for latitude-band fallback)
      * `avg_residential_rate_usd_per_kwh` (utility lookup, K.4 Step 2)
    """
    lookup = lookup_fields or {}

    system_kw_dc = inputs.pv_array.modules * inputs.pv_array.module.power_w / 1000.0
    battery_kwh = inputs.battery.total_kwh

    # Production: NREL > latitude > coarse 1500 baseline
    if "annual_energy_kwh_per_kw" in lookup:
        per_kw = float(lookup["annual_energy_kwh_per_kw"])
        production_source = "nrel-pvwatts"
    elif "latitude" in lookup:
        per_kw = _latitude_fallback_kwh_per_kw(float(lookup["latitude"]))
        production_source = "latitude-fallback"
    else:
        per_kw = 1500.0
        production_source = "us-average-fallback"

    # K.8: per-face production aggregator. When site.roof_sections is
    # populated with module_count > 0 per face, this returns the sum
    # across faces (each face's orientation_derate × shading_factor
    # applied). When sections are absent / empty, returns the legacy
    # single-orientation `per_kw × system_kw_dc` number — pre-K.8
    # projects bit-identical.
    #
    # K.8.2: pass project latitude through so the LRM auto-distribute
    # path can use value-weighted derate when the yaml's
    # `loads.use_value_weighted_distribution` flag is on. Without lat
    # the value-weighted code path can't compute, so we degrade to
    # K.8.1 area-only LRM transparently.
    latitude_deg: Optional[float] = None
    if "latitude" in lookup:
        latitude_deg = float(lookup["latitude"])
    elif inputs.project.coordinates:
        # Best-effort parse of "33.141418, -96.801258" style strings.
        try:
            lat_str = inputs.project.coordinates.split(",")[0].strip()
            latitude_deg = float(lat_str)
        except (ValueError, IndexError):
            latitude_deg = None
    from .production import compute_annual_production
    prod_result = compute_annual_production(
        inputs,
        baseline_kwh_per_kw=per_kw,
        baseline_method=production_source,
        latitude_deg=latitude_deg,
    )
    annual_production_kwh = prod_result.annual_production_kwh

    # Utility rate: lookup → USA average
    if "avg_residential_rate_usd_per_kwh" in lookup:
        rate = float(lookup["avg_residential_rate_usd_per_kwh"])
        rate_source = "lookup-utility-rate"
    else:
        rate = DEFAULT_USA_AVG_RATE_USD_PER_KWH
        rate_source = "usa-average"

    # K.7 [2/4] + K.4.6.4: apply export tariff. Self-consumed kWh credit
    # at full retail rate; exported kWh credit at retail × export_ratio.
    #
    # K.4.6.4 precedence: when `loads.rep_buyback_ratio` is explicitly
    # set, it OVERRIDES the named `export_tariff_model` — this is the
    # escape hatch for TX REP plans that aren't in our preset list, or
    # for mid-year rate changes. Tariff label falls back to
    # `loads.rep_plan_name` so the customer-PDF footer surfaces what
    # the homeowner is actually signed up for.
    self_cons = inputs.loads.self_consumption_fraction
    if inputs.loads.rep_buyback_ratio is not None:
        export_ratio = float(inputs.loads.rep_buyback_ratio)
        tariff_model = "tx_rep_custom"
        tariff_label = (
            inputs.loads.rep_plan_name
            or f"TX REP custom buyback ({export_ratio*100:.0f}% retail)"
        )
    else:
        tariff_model = inputs.loads.export_tariff_model
        export_ratio = EXPORT_RATIOS.get(tariff_model, 1.0)
        tariff_label = EXPORT_TARIFF_LABELS.get(tariff_model, tariff_model)
    effective_rate = rate * (
        self_cons + (1.0 - self_cons) * export_ratio
    )
    annual_savings = annual_production_kwh * effective_rate
    monthly_savings = annual_savings / 12.0

    # Household consumption / offset
    annual_household = inputs.loads.annual_kwh   # property; None if <12 months
    offset_pct: Optional[float] = None
    if annual_household and annual_household > 0:
        offset_pct = 100.0 * annual_production_kwh / annual_household

    # Cost estimate — precedence:
    #   1. `system_cost_usd_override` kwarg (most specific, test injection)
    #   2. `inputs.project.installer_cost_overrides` block (K.4.6.3 yaml)
    #   3. NREL Q1-2026 benchmark (legacy default — bit-identical to
    #      pre-K.4.6.3 behavior for any yaml without overrides)
    if system_cost_usd_override is not None:
        installed_cost = system_cost_usd_override
        cost_source = "user-provided"
    elif inputs.project.installer_cost_overrides is not None:
        installed_cost = _override_installed_cost(
            inputs, system_kw_dc,
        )
        cost_source = "installer-override"
    else:
        installed_cost = _benchmark_installed_cost(system_kw_dc, battery_kwh)
        cost_source = "benchmark-estimate"

    payback_years: Optional[float] = None
    if annual_savings > 0:
        payback_years = installed_cost / annual_savings

    cost_after_itc = installed_cost * (1.0 - FEDERAL_ITC_RATE)
    payback_after_itc: Optional[float] = None
    if annual_savings > 0:
        payback_after_itc = cost_after_itc / annual_savings

    return EconomicsResult(
        system_kw_dc=system_kw_dc,
        battery_kwh_total=battery_kwh,
        annual_production_kwh=annual_production_kwh,
        production_source=production_source,
        utility_rate_usd_per_kwh=rate,
        rate_source=rate_source,
        monthly_bill_savings_usd=monthly_savings,
        annual_bill_savings_usd=annual_savings,
        annual_household_kwh=annual_household,
        offset_pct=offset_pct,
        export_tariff_model=tariff_model,
        export_tariff_label=tariff_label,
        self_consumption_fraction=self_cons,
        export_ratio_applied=export_ratio,
        production_breakdown=prod_result.faces,
        production_blended_derate=prod_result.blended_derate,
        installed_cost_usd=installed_cost,
        cost_source=cost_source,
        payback_period_years=payback_years,
        cost_after_itc_usd=cost_after_itc,
        payback_after_itc_years=payback_after_itc,
        itc_rate_used=FEDERAL_ITC_RATE,
    )


def _latitude_fallback_kwh_per_kw(lat: float) -> float:
    """Map an absolute latitude to a coarse annual-yield band."""
    abs_lat = abs(lat)
    for upper, yield_per_kw in _LATITUDE_BAND_KWH_PER_KW:
        if abs_lat <= upper:
            return yield_per_kw
    return _LATITUDE_BAND_KWH_PER_KW[-1][1]


def _benchmark_installed_cost(system_kw_dc: float, battery_kwh: float) -> float:
    """Crude installed-cost estimate when the yaml doesn't carry a real
    quote. Combines NREL Q1-2026 benchmarks for PV + ESS.

    The point of the benchmark is to give the customer a payback FIGURE,
    not an actual quote — every PDF prints "Cost: $X (benchmark estimate)
    — confirm with installer".
    """
    pv_cost = system_kw_dc * 1000 * DEFAULT_INSTALLED_COST_USD_PER_W
    ess_cost = battery_kwh * DEFAULT_ESS_COST_USD_PER_KWH
    return pv_cost + ess_cost


def _override_installed_cost(inputs: Inputs, system_kw_dc: float) -> float:
    """K.4.6.3 — installer BOM cost using `installer_cost_overrides`.

    Component price precedence (per InstallerCostOverrides docstring):
      1. explicit `*_cost_usd_total` field (one-off custom equipment)
      2. `*_ref` key → device-library wholesale price × project quantity
      3. nothing set → component cost = 0 (assumed bundled in PV turnkey)

    The PV turnkey rate is mandatory when the block is present (pydantic
    enforces > 0). Inverter and battery costs are additive on top.
    """
    o = inputs.project.installer_cost_overrides
    assert o is not None, "_override_installed_cost called without overrides"

    pv_cost = system_kw_dc * 1000.0 * o.pv_turnkey_usd_per_w

    # Inverter: explicit total > ref-lookup > zero
    inverter_cost = 0.0
    if o.inverter_cost_usd_total is not None:
        inverter_cost = float(o.inverter_cost_usd_total)
    elif o.inverter_ref:
        from ..devices import INVERTER_PRICES_USD
        unit_price = INVERTER_PRICES_USD.get(o.inverter_ref)
        if unit_price is not None:
            # inverter.count() handles per-unit (PW3 style) vs explicit
            # quantity logic. Battery quantity needed for per-unit path.
            n_inv = inputs.inverter.count(inputs.battery.quantity)
            inverter_cost = unit_price * n_inv
        # Unknown ref silently → 0; doctor / wizard surfaces typos
        # (no need to crash the cost estimate over a misspelled ref)

    # Battery: explicit total > ref-lookup > zero. Skip entirely when
    # battery isn't installed (PV-only project — TX-market default).
    battery_cost = 0.0
    if inputs.battery.installed:
        if o.battery_cost_usd_total is not None:
            battery_cost = float(o.battery_cost_usd_total)
        elif o.battery_ref:
            from ..devices import BATTERY_PRICES_USD
            unit_price = BATTERY_PRICES_USD.get(o.battery_ref)
            if unit_price is not None:
                battery_cost = unit_price * inputs.battery.quantity

    return pv_cost + inverter_cost + battery_cost
