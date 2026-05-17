"""Conductor sizing and voltage drop (NEC 310.15, 690.8(B))."""
from __future__ import annotations

from dataclasses import dataclass

from ..nec.tables import (
    COPPER_AMPACITY_TABLE_310_16,
    COPPER_RESISTANCE_OHM_PER_KFT,
    smallest_copper_for_ampacity,
)


@dataclass
class ConductorResult:
    size: str
    insulation: str
    ampacity_a: int
    headroom_a: float   # ampacity - required


def select_copper(
    required_a: float,
    insulation: str = "75C",
    upstream_ocpd_a: int | None = None,
    derating_factor: float = 1.0,
) -> ConductorResult:
    """Select the smallest copper conductor satisfying Table 310.16, 240.4(D),
    and any NEC 310.15(B) environmental derating."""
    size, ampacity = smallest_copper_for_ampacity(  # type: ignore[arg-type]
        required_a,
        insulation=insulation,
        upstream_ocpd_a=upstream_ocpd_a,
        derating_factor=derating_factor,
    )
    return ConductorResult(
        size=size,
        insulation=insulation,
        ampacity_a=ampacity,
        headroom_a=ampacity - required_a,
    )


@dataclass
class VoltageDropResult:
    size: str
    one_way_length_ft: float
    current_a: float
    nominal_voltage: float
    drop_volts: float
    drop_percent: float


def voltage_drop_dc(
    size: str, one_way_length_ft: float, current_a: float, nominal_voltage: float
) -> VoltageDropResult:
    """DC voltage drop = 2 × L × I × R / 1000 (R in ohm/kft, L in ft)."""
    r = COPPER_RESISTANCE_OHM_PER_KFT[size]
    drop_v = 2 * one_way_length_ft * current_a * r / 1000.0
    drop_pct = (drop_v / nominal_voltage) * 100.0 if nominal_voltage > 0 else 0.0
    return VoltageDropResult(
        size=size,
        one_way_length_ft=one_way_length_ft,
        current_a=current_a,
        nominal_voltage=nominal_voltage,
        drop_volts=drop_v,
        drop_percent=drop_pct,
    )


def ampacity_lookup(size: str, insulation: str = "75C") -> int:
    return COPPER_AMPACITY_TABLE_310_16[size][insulation]  # type: ignore[index]
