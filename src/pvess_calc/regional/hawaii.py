"""Hawaii HECO Rule 14H interconnection screening.

Rule 14H governs all distributed energy resource interconnections with HECO,
MECO, and HELCO. Screening logic (simplified):

- Aggregate inverter capacity ≤ 25% of distribution circuit minimum daytime
  load → fast-track (typically OK for single-family residential).
- Smart inverter requirement (IEEE 1547-2018 + HI Schedule M settings).
- Battery storage CSS (Customer Self-Supply, no export) bypasses some
  screens.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..calc.engine import CalculationResult


@dataclass
class HawaiiRule14HResult:
    total_ac_kw: float
    smart_inverter_required: bool
    css_eligible: bool                 # CSS = no export
    fast_track_eligible: bool
    notes: list[str]


def check_rule_14h(result: "CalculationResult") -> HawaiiRule14HResult:
    i = result.inputs
    n_inv = i.inverter.count(i.battery.quantity)
    ac_kw = i.inverter.ac_output_v * i.inverter.ac_output_a * n_inv / 1000.0
    notes: list[str] = []

    # HECO fast-track residential limit is 10 kW AC per service (approximation).
    fast_track = ac_kw <= 10.0
    notes.append(
        f"Residential aggregate AC capacity = {ac_kw:.2f} kW "
        f"({'≤' if fast_track else '>'} 10 kW fast-track threshold)"
    )

    # Smart inverter mandatory since 2017 for new installs.
    smart = True
    notes.append(
        "Smart inverter w/ Schedule M (Volt/VAR, Volt/Watt, ride-through) "
        "is mandatory for all new HECO interconnections."
    )

    # CSS eligibility: present only if battery is included AND project opts
    # out of export. We can't tell from inputs, so flag as MANUAL.
    css = i.battery.quantity > 0
    if css:
        notes.append(
            "ESS present — eligible for CSS (Customer Self-Supply) if you "
            "configure non-export operation. CSS has faster approval but "
            "no grid export credit."
        )

    if not fast_track:
        notes.append(
            "⚠️ System exceeds residential fast-track limit; expect a "
            "supplemental review (up to 90 days)."
        )

    return HawaiiRule14HResult(
        total_ac_kw=ac_kw,
        smart_inverter_required=smart,
        css_eligible=css,
        fast_track_eligible=fast_track,
        notes=notes,
    )
