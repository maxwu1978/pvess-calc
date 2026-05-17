"""California Title 24 / CalGreen residential PV+ESS checks.

Title 24 Part 6 (2022 cycle): all newly constructed single-family residences
must include solar PV sized to offset annual electrical consumption, and
multi-family low-rise must include both PV and battery storage. CalGreen
A4.106.8 requires battery-ready provisioning in some construction types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..calc.engine import CalculationResult


@dataclass
class CaliforniaTitle24Result:
    pv_sizing_min_kw: float           # T24 prescriptive PV size (climate-zone based)
    pv_provided_kw: float
    pv_meets_t24: bool
    battery_storage_ready: bool       # CalGreen A4.106.8.3
    nem_3_aware: bool                 # NEM 3.0 export rate awareness
    notes: list[str] = field(default_factory=list)


def check_title_24(
    result: CalculationResult,
    *,
    climate_zone: int = 10,           # default to LA basin
    annual_load_kwh: float = 6500,    # typical SFH
) -> CaliforniaTitle24Result:
    """Very simplified T24 PV sizing rule: PV kWdc ≥ 1 kW per ~1500 kWh of
    annual electrical consumption (varies by CZ). Real T24 worksheets are
    far more detailed; this is a sanity threshold."""
    i = result.inputs
    pv_kw = i.pv_array.modules * i.pv_array.module.power_w / 1000.0

    # Climate zone correction (rough proxy — actual CECPV tables differ).
    cz_factor = {
        1: 1.00, 2: 1.00, 3: 1.00,
        4: 0.95, 5: 0.90, 6: 0.85,
        7: 0.85, 8: 0.85, 9: 0.85,
        10: 0.85, 11: 0.85, 12: 0.85,
        13: 0.85, 14: 0.90, 15: 0.95,
        16: 1.00,
    }.get(climate_zone, 0.90)
    target_kw = (annual_load_kwh / 1500.0) * cz_factor

    notes: list[str] = []
    notes.append(
        f"T24 prescriptive PV minimum ≈ {target_kw:.2f} kW (CZ{climate_zone}, "
        f"{annual_load_kwh:.0f} kWh/yr load)"
    )
    if pv_kw < target_kw:
        notes.append(
            f"⚠️ Provided {pv_kw:.2f} kW is below T24 prescriptive size. "
            "Either upsize array or pursue T24 performance path."
        )
    notes.append(
        "NEM 3.0 reduces export credit by ~75% vs NEM 2.0 — sizing should "
        "now prioritize self-consumption with ESS, not export."
    )

    return CaliforniaTitle24Result(
        pv_sizing_min_kw=target_kw,
        pv_provided_kw=pv_kw,
        pv_meets_t24=pv_kw >= target_kw,
        battery_storage_ready=(i.battery.quantity > 0),
        nem_3_aware=True,
        notes=notes,
    )
