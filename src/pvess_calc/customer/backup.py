"""Backup-runtime estimate for ESS at the critical-loads sub-panel.

What this answers for the homeowner: "if the grid goes down on a summer
evening, how long can my fridge / Wi-Fi / a couple of lights run off
the battery?"

Method (deliberately coarse):
  1. Estimate critical-loads peak demand from the critical sub-panel
     amp rating × voltage × a diversity factor (real households never
     load a panel to nameplate).
  2. Adjust for HVAC type — heat pump in winter draws a lot, gas
     furnace + AC almost nothing (gas runs the heat).
  3. Subtract from battery usable kWh (assume 90 % usable DoD —
     LFP chemistry standard).

The result is reported as a RANGE (summer / winter / "loads-only")
because no single number is honest given how much HVAC dominates.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..schema import Inputs


# Fraction of nameplate amp rating that real residential loads draw
# during a multi-hour outage. EPRI / utility load-research suggests
# 10–18% for a critical-loads sub-panel (fridge cycling, Wi-Fi, a few
# LEDs, occasional well-pump or blower) — `critical_subpanel_a` is the
# nameplate, NOT actual draw. 0.15 is the working midpoint; the PDF
# tags every backup-hours figure as an estimate so a homeowner reads it
# as a range, not a guarantee.
DIVERSITY_FACTOR_CRITICAL: float = 0.15

# HVAC peak draw adders (W) — added to the critical-loads base. The
# 'critical sub-panel' typically already includes lights / fridge /
# router / minimal outlets, but HVAC dominates so we model it explicitly.
HVAC_PEAK_W: dict[str, dict[str, float]] = {
    # type → {summer_w, winter_w}
    "heat_pump":              {"summer": 3500, "winter": 4500},
    "gas_furnace_ac":         {"summer": 3500, "winter":  400},  # blower only in winter
    "electric_resistance":    {"summer": 3500, "winter": 8000},
    "unknown":                {"summer": 3000, "winter": 3000},  # midpoint
}

# Usable depth-of-discharge for LFP batteries (Powerwall, EG4, etc.)
LFP_USABLE_DOD: float = 0.90


@dataclass
class BackupResult:
    critical_panel_a: Optional[float]
    critical_baseline_w: float          # critical loads w/o HVAC
    hvac_summer_w: float
    hvac_winter_w: float
    usable_battery_kwh: float
    # Three scenarios — let the homeowner see the range
    backup_hours_loads_only: float      # baseline loads, no HVAC
    backup_hours_summer: float          # baseline + summer HVAC
    backup_hours_winter: float          # baseline + winter HVAC


def compute_backup(inputs: Inputs) -> BackupResult:
    crit_a = inputs.loads.critical_subpanel_a
    voltage = 240.0   # split-phase residential

    if crit_a is not None and crit_a > 0:
        baseline_w = crit_a * voltage * DIVERSITY_FACTOR_CRITICAL
    else:
        # No critical sub-panel — assume "minimum survival" loads:
        # fridge + lights + router ≈ 500 W avg.
        baseline_w = 500.0

    hvac = HVAC_PEAK_W.get(inputs.loads.hvac_type or "unknown",
                           HVAC_PEAK_W["unknown"])
    summer_w = baseline_w + hvac["summer"]
    winter_w = baseline_w + hvac["winter"]

    usable_kwh = inputs.battery.total_kwh * LFP_USABLE_DOD

    def _hours(load_w: float) -> float:
        return (usable_kwh * 1000.0) / load_w if load_w > 0 else 0.0

    return BackupResult(
        critical_panel_a=crit_a,
        critical_baseline_w=baseline_w,
        hvac_summer_w=hvac["summer"],
        hvac_winter_w=hvac["winter"],
        usable_battery_kwh=usable_kwh,
        backup_hours_loads_only=_hours(baseline_w),
        backup_hours_summer=_hours(summer_w),
        backup_hours_winter=_hours(winter_w),
    )
