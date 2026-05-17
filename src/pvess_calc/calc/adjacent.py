"""Adjacent engineering calculations (Phase H).

- **NEC 690.11**: DC arc-fault protection — verify inverter integrates AFCI.
- **NEC 690.12 / 285**: Surge protection device selection.
- **NEC 250.53(A)(2)**: Ground rod resistance — ≤ 25Ω single, else paralleled.
- **NEC Chapter 9, Table 4/5**: Conduit fill — select minimum EMT size.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..schema import Inputs


# --- 690.11 DC AFCI --------------------------------------------------------

@dataclass
class DcAfciCheck:
    inverter_has_integrated_afci: bool
    inverter_model: str
    status: Literal["PASS", "FAIL", "MANUAL"]
    note: str


# Inverter models known to include integrated DC AFCI per UL 1699B.
INVERTERS_WITH_DC_AFCI: set[str] = {
    "sol_ark_12k",
    "tesla_powerwall_3",
    "enphase_iq8m",       # microinverters — module-level, no DC string
    "megarevo_r8klna",
}


def check_dc_afci(inputs: Inputs) -> DcAfciCheck:
    inv = inputs.inverter
    model_id = f"{inv.brand}_{inv.model}".lower().replace(" ", "_").replace("-", "_")
    has_afci = any(known in model_id for known in INVERTERS_WITH_DC_AFCI)
    if has_afci:
        return DcAfciCheck(
            inverter_has_integrated_afci=True,
            inverter_model=f"{inv.brand} {inv.model}",
            status="PASS",
            note="Inverter datasheet lists UL 1699B integrated DC AFCI.",
        )
    return DcAfciCheck(
        inverter_has_integrated_afci=False,
        inverter_model=f"{inv.brand} {inv.model}",
        status="MANUAL",
        note=(
            "DC AFCI not confirmed for this inverter — verify against the "
            "manufacturer's UL 1699B listing. Standalone DC AFCI devices "
            "(e.g. Tigo TS4-F) may be required per NEC 690.11."
        ),
    )


# --- 690.12 + 285 Surge Protection -----------------------------------------

@dataclass
class SurgeProtectionPlan:
    locations: list[str]              # where SPDs must be installed
    spd_type: Literal["Type 1", "Type 2", "Type 3"]
    note: str


def plan_surge_protection(inputs: Inputs) -> SurgeProtectionPlan:
    """Per NEC 230.67 (effective 2020+) residential services require Type 1
    or Type 2 SPD at the service. PV+ESS typically adds DC-side SPD at the
    array combiner (NEC 690.4(F) + UL 1449)."""
    locations = ["Main Service Panel (MSP)", "PV combiner (DC side)"]
    if inputs.battery.quantity > 0:
        locations.append("ESS AC disconnect")
    return SurgeProtectionPlan(
        locations=locations,
        spd_type="Type 2",
        note=(
            "Install Type 2 SPDs at each location. Coastal / lightning-prone "
            "areas should upgrade to Type 1+2 combined."
        ),
    )


# --- 250.53(A)(2) Ground rod resistance -----------------------------------

@dataclass
class GroundRodCheck:
    n_rods: int
    spacing_ft: float
    status: Literal["PASS", "MANUAL"]
    note: str


def check_ground_rods(n_rods: int = 1, spacing_ft: float = 8.0) -> GroundRodCheck:
    """A single rod must hit ≤25Ω; otherwise pair with a second rod at ≥6ft
    spacing (≥8ft preferred per 250.53(A)(3)). We can't measure resistance,
    so we just flag the topology."""
    if n_rods >= 2 and spacing_ft >= 6.0:
        return GroundRodCheck(
            n_rods=n_rods, spacing_ft=spacing_ft, status="PASS",
            note=(
                f"{n_rods} rods at {spacing_ft:.0f} ft spacing satisfy "
                "NEC 250.53(A)(2) Exception — no resistance test required."
            ),
        )
    return GroundRodCheck(
        n_rods=n_rods, spacing_ft=spacing_ft, status="MANUAL",
        note=(
            "Single rod requires field resistance test ≤25 Ω per "
            "NEC 250.53(A)(2). If >25 Ω, add a second rod at ≥6 ft spacing."
        ),
    )


# --- Chapter 9 Table 4/5 Conduit Fill --------------------------------------

# Approximate THWN-2 conductor cross-sectional areas (in², NEC Chapter 9 Table 5).
THWN2_AREA_IN2: dict[str, float] = {
    "14":  0.0097,
    "12":  0.0133,
    "10":  0.0211,
    "8":   0.0366,
    "6":   0.0507,
    "4":   0.0824,
    "3":   0.0973,
    "2":   0.1158,
    "1":   0.1562,
    "1/0": 0.1855,
    "2/0": 0.2223,
    "3/0": 0.2679,
    "4/0": 0.3237,
}

# 40%-fill internal area capacities for EMT (NEC Chapter 9 Table 4, EMT).
EMT_FILL_40PCT_IN2: list[tuple[str, float]] = [
    ('1/2"',     0.122),
    ('3/4"',     0.213),
    ('1"',       0.346),
    ('1-1/4"',   0.598),
    ('1-1/2"',   0.814),
    ('2"',       1.342),
    ('2-1/2"',   2.343),
    ('3"',       3.538),
    ('3-1/2"',   4.618),
    ('4"',       5.901),
]


@dataclass
class ConduitFillResult:
    total_conductor_area_in2: float
    selected_conduit: str
    fill_capacity_in2: float
    headroom_in2: float


def select_conduit(conductor_sizes: list[str]) -> ConduitFillResult:
    """Pick the smallest EMT that can hold the given THWN-2 conductors at
    NEC's 40% fill limit (Chapter 9 Table 1)."""
    total = sum(THWN2_AREA_IN2.get(s, 0) for s in conductor_sizes)
    for size, capacity in EMT_FILL_40PCT_IN2:
        if capacity >= total:
            return ConduitFillResult(
                total_conductor_area_in2=total,
                selected_conduit=size,
                fill_capacity_in2=capacity,
                headroom_in2=capacity - total,
            )
    return ConduitFillResult(
        total_conductor_area_in2=total,
        selected_conduit=EMT_FILL_40PCT_IN2[-1][0] + "+",
        fill_capacity_in2=EMT_FILL_40PCT_IN2[-1][1],
        headroom_in2=EMT_FILL_40PCT_IN2[-1][1] - total,
    )


# --- Top-level aggregation -------------------------------------------------

@dataclass
class AdjacentResult:
    dc_afci: DcAfciCheck
    surge: SurgeProtectionPlan
    ground_rods: GroundRodCheck
    pv_conduit: ConduitFillResult
    ac_conduit: ConduitFillResult


def compute_adjacent(
    inputs: Inputs,
    *,
    pv_conductor_size: str,
    ac_conductor_size: str,
    pv_conductor_count: int = 2,        # + + - (DC source)
    ac_conductor_count: int = 3,        # L1 + L2 + N
    pv_ground_size: str = "10",
    ac_ground_size: str = "6",
) -> AdjacentResult:
    return AdjacentResult(
        dc_afci=check_dc_afci(inputs),
        surge=plan_surge_protection(inputs),
        ground_rods=check_ground_rods(n_rods=2, spacing_ft=8.0),
        pv_conduit=select_conduit(
            [pv_conductor_size] * pv_conductor_count + [pv_ground_size]
        ),
        ac_conduit=select_conduit(
            [ac_conductor_size] * ac_conductor_count + [ac_ground_size]
        ),
    )
