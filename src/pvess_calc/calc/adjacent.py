"""Adjacent engineering calculations (Phase H).

- **NEC 690.11**: DC arc-fault protection — verify inverter integrates AFCI.
- **NEC 690.12 / 285**: Surge protection device selection.
- **NEC 250.53(A)(2)**: Ground rod resistance — ≤ 25Ω single, else paralleled.
- **NEC Chapter 9, Table 4/5**: Conduit fill — select minimum raceway size.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Literal

from ..schema import Inputs, RacewayType
from .wire_routing import WireRoutingResult


# --- 690.11 DC AFCI --------------------------------------------------------

@dataclass
class DcAfciCheck:
    inverter_has_integrated_afci: bool
    inverter_model: str
    status: Literal["PASS", "FAIL", "MANUAL"]
    note: str
    evidence: str = ""


# Inverter models locally verified against the project device registry or
# downloaded candidate datasheets. Keys are normalized brand+model fragments.
INVERTER_DC_AFCI_EVIDENCE: dict[str, str] = {
    "solark12k2pn": "Device registry marks Sol-Ark 12K as UL 1699B AFCI listed.",
    "teslapowerwall3": "Device registry marks Powerwall 3 as integrated AFCI listed.",
    "enphaseiq8m722us": "Microinverter architecture; no long DC string homerun.",
    "megarevor8klna": "Candidate datasheet lists DC arc-fault / UL 1699B.",
    "growattmin11400tlxhus": "Selected datasheet lists AFCI protection and UL 1699B.",
    "hoymileshys115lvusg1": "Candidate datasheet lists integrated arc-fault protection and UL 1699B.",
}


def _norm_model(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def check_dc_afci(inputs: Inputs) -> DcAfciCheck:
    inv = inputs.inverter
    model = f"{inv.brand} {inv.model}"
    declared = getattr(inv, "dc_afci", "unknown")
    if declared == "integrated":
        return DcAfciCheck(
            inverter_has_integrated_afci=True,
            inverter_model=model,
            status="PASS",
            note="Inverter is marked as integrated DC AFCI capable.",
            evidence=(
                "Device registry / inputs.yaml sets dc_afci=integrated"
                + (" and ul1699b_listed=true." if inv.ul1699b_listed else ".")
            ),
        )
    if declared == "external_required":
        return DcAfciCheck(
            inverter_has_integrated_afci=False,
            inverter_model=model,
            status="FAIL",
            note=(
                "This inverter is marked external_required; specify a listed "
                "DC AFCI device before permit submission."
            ),
            evidence="inputs.yaml/device registry sets dc_afci=external_required.",
        )

    normalized = _norm_model(model)
    for fragment, evidence in INVERTER_DC_AFCI_EVIDENCE.items():
        if fragment in normalized:
            return DcAfciCheck(
                inverter_has_integrated_afci=True,
                inverter_model=model,
                status="PASS",
                note="Inverter datasheet/listing indicates integrated DC AFCI.",
                evidence=evidence,
            )

    if inv.ul1699b_listed:
        return DcAfciCheck(
            inverter_has_integrated_afci=True,
            inverter_model=model,
            status="PASS",
            note="Inverter is marked UL 1699B listed for DC AFCI.",
            evidence="inputs.yaml/device registry sets ul1699b_listed=true.",
        )

    return DcAfciCheck(
        inverter_has_integrated_afci=False,
        inverter_model=model,
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
    required_locations: list[str] = field(default_factory=list)
    recommended_locations: list[str] = field(default_factory=list)
    service_spd_required: bool = True
    dc_spd_recommended: bool = True


def plan_surge_protection(inputs: Inputs) -> SurgeProtectionPlan:
    """Plan service and PV-system surge protection.

    NEC 230.67 appears in the 2020 cycle and requires Type 1 or Type 2 SPD
    for dwelling-unit services. DC-side PV SPD is treated as a design
    recommendation unless the equipment instructions/AHJ make it mandatory.
    """
    edition = int(inputs.project.nec_edition)
    required: list[str] = []
    recommended = ["PV DC side at inverter / combiner"]

    service_required = edition >= 2020
    if service_required:
        required.append("Main Service Panel (MSP)")
        basis = (
            f"NEC {edition} 230.67 requires a Type 1 or Type 2 SPD at "
            "dwelling-unit services."
        )
    else:
        recommended.insert(0, "Main Service Panel (MSP)")
        basis = (
            "NEC 2017 has no 230.67 dwelling-service SPD mandate; service "
            "SPD remains recommended or AHJ/manufacturer driven."
        )

    if inputs.battery.quantity > 0:
        recommended.append("ESS AC disconnect")
    locations = required + [loc for loc in recommended if loc not in required]
    return SurgeProtectionPlan(
        locations=locations,
        spd_type="Type 2",
        note=(
            basis + " Use UL 1449 listed devices; lightning-prone areas "
            "should evaluate Type 1+2 combined protection."
        ),
        required_locations=required,
        recommended_locations=recommended,
        service_spd_required=service_required,
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


def _infer_rod_spacing_ft(inputs: Inputs) -> float:
    """Best-effort spacing from survey text.

    The current schema records rod locations as free text. Common survey
    wording is "6 ft NW of rod #1"; parse that when present so reports don't
    claim the default spacing when the site data says otherwise.
    """
    rods = inputs.service.grounding_electrode_system.rods
    for rod in rods[1:]:
        match = re.search(r"(\d+(?:\.\d+)?)\s*ft\b", rod.location.lower())
        if match:
            return float(match.group(1))
    return 6.0 if len(rods) >= 2 else 0.0


def check_ground_rods_from_inputs(inputs: Inputs) -> GroundRodCheck:
    ges = inputs.service.grounding_electrode_system
    n_rods = len(ges.rods)
    if n_rods >= 2:
        return check_ground_rods(
            n_rods=n_rods,
            spacing_ft=_infer_rod_spacing_ft(inputs),
        )
    if ges.electrode_count >= 2:
        return GroundRodCheck(
            n_rods=n_rods,
            spacing_ft=0.0,
            status="PASS",
            note=(
                f"Grounding electrode system has {ges.electrode_count} "
                "qualifying electrodes; no single-rod resistance test "
                "is required."
            ),
        )
    return check_ground_rods(n_rods=n_rods, spacing_ft=0.0)


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

# 40%-fill internal area capacities (in²) for common residential raceways.
# These are preliminary-design rows from NEC Chapter 9 Table 4; final plans
# still need AHJ / engineer verification against the adopted code edition.
RACEWAY_FILL_40PCT_IN2: dict[RacewayType, list[tuple[str, float]]] = {
    "EMT": [
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
    ],
    "PVC40": [
        ('1/2"',     0.114),
        ('3/4"',     0.203),
        ('1"',       0.333),
        ('1-1/4"',   0.581),
        ('1-1/2"',   0.794),
        ('2"',       1.316),
        ('2-1/2"',   1.878),
        ('3"',       2.907),
        ('3-1/2"',   3.895),
        ('4"',       5.022),
    ],
    "PVC80": [
        ('1/2"',     0.068),
        ('3/4"',     0.119),
        ('1"',       0.198),
        ('1-1/4"',   0.341),
        ('1-1/2"',   0.467),
        ('2"',       0.762),
        ('2-1/2"',   1.319),
        ('3"',       1.998),
        ('3-1/2"',   2.669),
        ('4"',       3.435),
    ],
    "RMC": [
        ('1/2"',     0.126),
        ('3/4"',     0.220),
        ('1"',       0.355),
        ('1-1/4"',   0.610),
        ('1-1/2"',   0.828),
        ('2"',       1.363),
        ('2-1/2"',   1.946),
        ('3"',       3.000),
        ('3-1/2"',   4.004),
        ('4"',       5.153),
    ],
    "FMC": [
        ('3/8"',     0.046),
        ('1/2"',     0.127),
        ('3/4"',     0.213),
        ('1"',       0.327),
        ('1-1/4"',   0.511),
        ('1-1/2"',   0.743),
        ('2"',       1.308),
        ('2-1/2"',   1.964),
        ('3"',       2.828),
        ('3-1/2"',   3.848),
        ('4"',       5.026),
    ],
}


@dataclass
class ConduitFillResult:
    total_conductor_area_in2: float
    raceway_type: RacewayType
    selected_conduit: str
    fill_capacity_in2: float
    headroom_in2: float
    fill_pct: float


@dataclass
class RacewaySegmentResult:
    tag: str
    circuit: str
    kind: Literal["DC", "AC", "BATTERY"]
    length_ft: float
    wires: str
    conductor_sizes: list[str]
    raceway_type: Literal["FREE AIR"] | RacewayType
    selected_raceway: str
    fill: ConduitFillResult | None
    provenance: Literal["routed", "manual", "default", "not_applicable"]
    note: str = ""


def select_conduit(
    conductor_sizes: list[str],
    *,
    raceway_type: RacewayType = "EMT",
) -> ConduitFillResult:
    """Pick the smallest raceway that can hold the given THWN-2 conductors at
    NEC's 40% fill limit (Chapter 9 Table 1)."""
    unknown = [s for s in conductor_sizes if s not in THWN2_AREA_IN2]
    if unknown:
        raise ValueError(
            "Unknown THWN-2 conductor size(s) for conduit fill: "
            + ", ".join(sorted(set(unknown)))
        )

    table = RACEWAY_FILL_40PCT_IN2[raceway_type]
    total = sum(THWN2_AREA_IN2[s] for s in conductor_sizes)
    for size, capacity in table:
        if capacity >= total:
            return ConduitFillResult(
                total_conductor_area_in2=total,
                raceway_type=raceway_type,
                selected_conduit=size,
                fill_capacity_in2=capacity,
                headroom_in2=capacity - total,
                fill_pct=total / capacity * 100,
            )
    return ConduitFillResult(
        total_conductor_area_in2=total,
        raceway_type=raceway_type,
        selected_conduit=table[-1][0] + "+",
        fill_capacity_in2=table[-1][1],
        headroom_in2=table[-1][1] - total,
        fill_pct=total / table[-1][1] * 100,
    )


def _route_lengths(
    inputs: Inputs,
    wire_routing: WireRoutingResult | None,
) -> tuple[dict[str, float], str]:
    if wire_routing is not None and wire_routing.routed:
        return {
            "A": wire_routing.pv_string_one_way_ft,
            "B": wire_routing.pv_to_combiner_ft,
            "C": wire_routing.inverter_to_ac_disc_ft,
            "D": wire_routing.ac_disc_to_msp_ft,
            "E": wire_routing.ess_to_inverter_ft,
        }, "routed"
    wl = inputs.wire_lengths
    lengths = {
        "A": wl.pv_string_one_way_ft,
        "B": wl.pv_to_combiner_ft or wl.combiner_to_inverter_ft,
        "C": wl.inverter_to_ac_disc_ft,
        "D": wl.ac_disc_to_msp_ft,
        "E": wl.ess_to_inverter_ft,
    }
    if any(v > 0 for v in lengths.values()):
        return lengths, "manual"
    return lengths, "default"


def _raceway_segment(
    *,
    tag: str,
    circuit: str,
    kind: Literal["DC", "AC", "BATTERY"],
    length_ft: float,
    wires: str,
    conductor_sizes: list[str],
    raceway_type: Literal["FREE AIR"] | RacewayType,
    provenance: Literal["routed", "manual", "default", "not_applicable"],
    note: str = "",
) -> RacewaySegmentResult:
    if raceway_type == "FREE AIR":
        return RacewaySegmentResult(
            tag=tag,
            circuit=circuit,
            kind=kind,
            length_ft=length_ft,
            wires=wires,
            conductor_sizes=conductor_sizes,
            raceway_type=raceway_type,
            selected_raceway="FREE AIR",
            fill=None,
            provenance=provenance,
            note=note,
        )
    fill = select_conduit(conductor_sizes, raceway_type=raceway_type)
    return RacewaySegmentResult(
        tag=tag,
        circuit=circuit,
        kind=kind,
        length_ft=length_ft,
        wires=wires,
        conductor_sizes=conductor_sizes,
        raceway_type=raceway_type,
        selected_raceway=f"{fill.selected_conduit} {raceway_type}",
        fill=fill,
        provenance=provenance,
        note=note,
    )


def build_raceway_segments(
    inputs: Inputs,
    *,
    pv_conductor_size: str,
    aggregate_ac_conductor_size: str,
    per_inverter_ac_conductor_size: str,
    pv_ground_size: str,
    per_inverter_ground_size: str,
    aggregate_ac_ground_size: str,
    wire_routing: WireRoutingResult | None = None,
) -> list[RacewaySegmentResult]:
    lengths, provenance = _route_lengths(inputs, wire_routing)
    pv_raceway = inputs.routing.pv_raceway_type
    ac_raceway = inputs.routing.ac_raceway_type
    return [
        _raceway_segment(
            tag="A",
            circuit="PV SOURCE",
            kind="DC",
            length_ft=lengths["A"],
            wires="2+G",
            conductor_sizes=[pv_conductor_size, pv_conductor_size, pv_ground_size],
            raceway_type="FREE AIR",
            provenance=provenance,
            note="module/source circuit conductors on roof",
        ),
        _raceway_segment(
            tag="B",
            circuit="PV DC OUTPUT",
            kind="DC",
            length_ft=lengths["B"],
            wires="2+G",
            conductor_sizes=[pv_conductor_size, pv_conductor_size, pv_ground_size],
            raceway_type=pv_raceway,
            provenance=provenance,
            note="PV DC OCPD to inverter",
        ),
        _raceway_segment(
            tag="C",
            circuit="INVERTER AC",
            kind="AC",
            length_ft=lengths["C"],
            wires="3+G",
            conductor_sizes=[
                per_inverter_ac_conductor_size,
                per_inverter_ac_conductor_size,
                per_inverter_ac_conductor_size,
                per_inverter_ground_size,
            ],
            raceway_type=ac_raceway,
            provenance=provenance,
            note="per-inverter output conductors",
        ),
        _raceway_segment(
            tag="D",
            circuit="SUPPLY TAP",
            kind="AC",
            length_ft=lengths["D"],
            wires="3+G",
            conductor_sizes=[
                aggregate_ac_conductor_size,
                aggregate_ac_conductor_size,
                aggregate_ac_conductor_size,
                aggregate_ac_ground_size,
            ],
            raceway_type=ac_raceway,
            provenance=provenance,
            note="AC disconnect to line-side tap",
        ),
    ]


# --- Top-level aggregation -------------------------------------------------

@dataclass
class AdjacentResult:
    dc_afci: DcAfciCheck
    surge: SurgeProtectionPlan
    ground_rods: GroundRodCheck
    pv_conduit: ConduitFillResult
    ac_conduit: ConduitFillResult
    raceways: list[RacewaySegmentResult] = field(default_factory=list)


def compute_adjacent(
    inputs: Inputs,
    *,
    pv_conductor_size: str,
    ac_conductor_size: str,
    per_inverter_ac_conductor_size: str | None = None,
    pv_conductor_count: int = 2,        # + + - (DC source)
    ac_conductor_count: int = 3,        # L1 + L2 + N
    pv_ground_size: str = "10",
    per_inverter_ground_size: str | None = None,
    ac_ground_size: str = "6",
    wire_routing: WireRoutingResult | None = None,
) -> AdjacentResult:
    per_inv_cond = per_inverter_ac_conductor_size or ac_conductor_size
    per_inv_ground = per_inverter_ground_size or ac_ground_size
    raceways = build_raceway_segments(
        inputs,
        pv_conductor_size=pv_conductor_size,
        aggregate_ac_conductor_size=ac_conductor_size,
        per_inverter_ac_conductor_size=per_inv_cond,
        pv_ground_size=pv_ground_size,
        per_inverter_ground_size=per_inv_ground,
        aggregate_ac_ground_size=ac_ground_size,
        wire_routing=wire_routing,
    )
    return AdjacentResult(
        dc_afci=check_dc_afci(inputs),
        surge=plan_surge_protection(inputs),
        ground_rods=check_ground_rods_from_inputs(inputs),
        pv_conduit=select_conduit(
            [pv_conductor_size] * pv_conductor_count + [pv_ground_size],
            raceway_type=inputs.routing.pv_raceway_type,
        ),
        ac_conduit=select_conduit(
            [ac_conductor_size] * ac_conductor_count + [ac_ground_size],
            raceway_type=inputs.routing.ac_raceway_type,
        ),
        raceways=raceways,
    )
