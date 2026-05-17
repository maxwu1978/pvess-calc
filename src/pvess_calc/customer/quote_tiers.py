"""K.4.6.5 — 3-tier quote table data model.

The customer PDF's bottom section can render a 2-3 column table comparing
the base project (typically PV-only, TX-market default) against 1-2
battery upgrade tiers. Surfaces the K.4.6 insight that **all tiers
earn the same monthly savings**; the upgrade decision is backup-vs-cost,
NOT a savings-vs-cost choice.

Design split (vs putting all this logic inline in pdf.py):

  * `compute_quote_tiers()` returns a list of `QuoteTier` view-models —
    pure data, no rendering. Tests can lock the math without rendering
    PDFs.
  * pdf.py imports these and just lays them out side-by-side.

Each tier is computed by `model_copy(update=…)`-ing the inputs to
swap in a different battery, then re-running the standard
`compute_economics()` + `compute_backup()` pipeline. The PV array,
roof_sections, and lookup_fields stay identical across tiers — only
the battery (and consequently the cost stack + backup hours) varies.

Note: when the project's `installer_cost_overrides` carries a
`battery_ref`, that's IGNORED for the alternative tiers — each tier
emits its own battery_ref via the BackupOption, which overrides
yaml-level for that tier's computation only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..devices import BATTERIES, BATTERY_PRICES_USD
from ..schema import Battery, BackupOption, Inputs, InstallerCostOverrides
from .backup import BackupResult, compute_backup
from .economics import EconomicsResult, compute_economics


@dataclass
class QuoteTier:
    """One column of the 3-tier table — fully self-contained for rendering.

    Always has the cost / monthly-savings / payback numbers. Backup
    summary is a short human string ("none" / "~14 hr critical loads"
    / "~24 hr whole-home") not the raw hours triple — saves PDF
    real-estate and reads better in a side-by-side comparison.
    """
    name: str
    battery_kwh_total: float            # 0.0 for PV-only base
    installed_cost_usd: float           # full pre-ITC
    cost_after_itc_usd: float           # post 30 % ITC
    monthly_savings_usd: float
    payback_after_itc_years: Optional[float]
    backup_summary: str                 # one-line homeowner-readable
    is_base: bool = False               # True for the "you are here" tier


def compute_quote_tiers(
    inputs: Inputs,
    *,
    lookup_fields: Optional[dict] = None,
) -> list[QuoteTier]:
    """Compute the 2-3 columns of the 3-tier quote table.

    Returns `[base_tier, *option_tiers]`. `base_tier.is_base = True`.
    When `inputs.loads.backup_options` is empty, returns a 1-element
    list (just the base) — caller (pdf.py) skips the block in that
    case.

    The function never raises on a misspelled `battery_ref` — the
    affected tier simply uses the library entry's cost = 0 (which
    the QuoteTier label will reflect, and the doctor check from
    K.4.6.6 will catch).
    """
    tiers: list[QuoteTier] = []

    # Base tier — whatever the yaml says (typically PV-only, K.4.6.1).
    base_econ = compute_economics(inputs, lookup_fields=lookup_fields)
    base_backup = compute_backup(inputs)
    tiers.append(_to_tier(
        name=_base_tier_name(inputs),
        battery_kwh_total=inputs.battery.total_kwh,
        econ=base_econ, backup=base_backup,
        is_base=True,
    ))

    # Option tiers — each swaps in a different battery.
    for opt in inputs.loads.backup_options:
        swapped = _swap_in_option(inputs, opt)
        opt_econ = compute_economics(swapped, lookup_fields=lookup_fields)
        opt_backup = compute_backup(swapped)
        tiers.append(_to_tier(
            name=opt.name,
            battery_kwh_total=swapped.battery.total_kwh,
            econ=opt_econ, backup=opt_backup,
            is_base=False,
        ))

    return tiers


# ─── Helpers ───────────────────────────────────────────────────────────


def _base_tier_name(inputs: Inputs) -> str:
    if not inputs.battery.installed:
        return "PV-only (no backup)"
    return f"{inputs.battery.total_kwh:.0f} kWh ({inputs.battery.brand})"


def _to_tier(
    *,
    name: str, battery_kwh_total: float,
    econ: EconomicsResult, backup: BackupResult,
    is_base: bool,
) -> QuoteTier:
    return QuoteTier(
        name=name,
        battery_kwh_total=battery_kwh_total,
        installed_cost_usd=econ.installed_cost_usd,
        cost_after_itc_usd=econ.cost_after_itc_usd,
        monthly_savings_usd=econ.monthly_bill_savings_usd,
        payback_after_itc_years=econ.payback_after_itc_years,
        backup_summary=_backup_summary(battery_kwh_total, backup),
        is_base=is_base,
    )


def _backup_summary(battery_kwh: float, backup: BackupResult) -> str:
    """One-line human-readable backup capability — shows TWO numbers
    so the homeowner sees both the realistic case (AC running,
    summer outage in DFW) and the long-tail case (essentials only,
    AC off intentionally to stretch the battery).

    Empty battery → "none (grid-tied)" matches the K.4.6.1 PV-only
    notice elsewhere in the PDF.
    """
    if battery_kwh <= 0:
        return "none (grid-tied)"
    h_essentials = backup.backup_hours_loads_only
    h_with_ac = backup.backup_hours_summer
    return (
        f"~{h_essentials:.0f} hr essentials  ·  "
        f"~{h_with_ac:.0f} hr w/ AC"
    )


def _swap_in_option(inputs: Inputs, opt: BackupOption) -> Inputs:
    """Return a deep-copied Inputs with `opt`'s battery swapped in
    AND `installer_cost_overrides.battery_ref` redirected to the
    option's battery_ref. The original Inputs object is unchanged."""
    swapped = inputs.model_copy(deep=True)

    # Swap the Battery block from the library entry.
    if opt.battery_ref in BATTERIES:
        spec = BATTERIES[opt.battery_ref].copy()
        swapped.battery = Battery(
            quantity=opt.quantity,
            install_location=inputs.battery.install_location,
            distance_to_doorway_ft=inputs.battery.distance_to_doorway_ft,
            distance_to_window_ft=inputs.battery.distance_to_window_ft,
            distance_to_egress_ft=inputs.battery.distance_to_egress_ft,
            **spec,
        )
    else:
        # Unknown ref — emit an empty battery block; the resulting tier
        # shows up as "0 kWh" backup which the rendering will surface
        # as a clear "missing data" hint to the designer.
        swapped.battery = inputs.battery.model_copy(update={"quantity": 0})

    # Redirect the cost override (if any) to the new battery_ref so
    # `_override_installed_cost` picks the right wholesale price for
    # this tier's cost.
    if swapped.project.installer_cost_overrides is not None:
        overrides = swapped.project.installer_cost_overrides
        swapped.project.installer_cost_overrides = (
            overrides.model_copy(update={
                "battery_ref": opt.battery_ref,
                "battery_cost_usd_total": None,   # clear any base-tier total
            })
        )

    return swapped
