"""Shared electrical topology for permit drawing projections.

This module is intentionally renderer-neutral. It turns a
``CalculationResult`` into device nodes, conductor edges, and a conductor
schedule. DXF/PDF renderers should consume this data rather than inventing
electrical facts locally.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..calc.conductor import select_copper
from ..calc.engine import CalculationResult
from ..calc.ocpd import select_ocpd


@dataclass(frozen=True)
class ElectricalNode:
    id: str
    tag: str
    label: str
    kind: str
    icon: str
    desc1: str = ""
    desc2: str = ""


@dataclass(frozen=True)
class ElectricalEdge:
    id: str
    source: str
    target: str
    kind: str
    tag: str = ""
    schedule_tag: str = ""
    protection_node: str = ""


@dataclass(frozen=True)
class ConductorScheduleRow:
    tag: str
    circuit: str
    source: str
    target: str
    kind: str
    wires: str
    size: str
    conductor_type: str
    ground: str
    conduit: str
    amps: float
    ampacity: float
    ocpd_a: int
    length_ft: float = 0.0
    fill_pct: float | None = None
    note: str = ""


@dataclass(frozen=True)
class ElectricalTopology:
    nodes: tuple[ElectricalNode, ...]
    edges: tuple[ElectricalEdge, ...]
    schedule: tuple[ConductorScheduleRow, ...]
    interconnection_method: str
    system_dc_kw: float
    system_ac_kw: float

    def node(self, node_id: str) -> ElectricalNode:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(node_id)

    def schedule_by_tag(self) -> dict[str, ConductorScheduleRow]:
        return {row.tag: row for row in self.schedule}

    def edge_by_schedule_tag(self) -> dict[str, ElectricalEdge]:
        return {edge.schedule_tag: edge for edge in self.edges if edge.schedule_tag}


def _per_inverter_ac_spec(result: CalculationResult):
    inv = result.inputs.inverter
    min_a = inv.ac_output_a * 1.25
    ocpd = select_ocpd(min_a)
    cond = select_copper(
        min_a,
        "75C",
        upstream_ocpd_a=ocpd,
        derating_factor=result.ac_derating_factor,
    )
    return ocpd, cond


def _raceway_by_tag(result: CalculationResult):
    return {rw.tag: rw for rw in result.adjacent.raceways}


def build_electrical_topology(result: CalculationResult) -> ElectricalTopology:
    """Build the electrical facts shared by EE-2 and EE-2.1 renderers."""
    i = result.inputs
    n_inv = i.inverter.count(i.battery.quantity)
    dc_kw = i.pv_array.modules * i.pv_array.module.power_w / 1000.0
    ac_kw = i.inverter.ac_output_v * i.inverter.ac_output_a * n_inv / 1000.0
    per_inv_ocpd, per_inv_cond = _per_inverter_ac_spec(result)

    inv_tag = "INV-1" if n_inv == 1 else f"INV-1..{n_inv}"
    opt_qty = i.optimizer.effective_count(i.pv_array.modules, i.pv_array.strings)
    method = (result.interconnect.recommended or "field_verify").replace("_", " ").upper()

    nodes: list[ElectricalNode] = [
        ElectricalNode(
            id="pv",
            tag="PV-1",
            label="PV ARRAY",
            kind="pv_array",
            icon="PV",
            desc1=f"({i.pv_array.modules}) {i.pv_array.module.brand} {i.pv_array.module.model}",
            desc2=f"{i.pv_array.strings} strings / {dc_kw:.2f} kW DC",
        ),
        ElectricalNode(
            id="mlpe",
            tag="MLPE-1",
            label="MLPE / RSD",
            kind="mlpe_rsd",
            icon="MLPE",
            desc1=f"({opt_qty}) {i.optimizer.brand} {i.optimizer.model}".strip(),
            desc2="NEC 690.12 rapid shutdown",
        ),
        ElectricalNode(
            id="dc_ocpd",
            tag="DC-COMB-1",
            label="PV DC OCPD",
            kind="dc_ocpd",
            icon="COMB",
            desc1=f"OCPD: {result.pv_ocpd_a} A",
            desc2=f"COND: {result.pv_conductor.size} AWG CU",
        ),
        ElectricalNode(
            id="inverter",
            tag=inv_tag,
            label="INVERTER",
            kind="inverter",
            icon="INV",
            desc1=f"{i.inverter.brand} {i.inverter.model}",
            desc2=f"{i.inverter.ac_output_a * n_inv:.0f} A @ {i.inverter.ac_output_v:.0f} V",
        ),
        ElectricalNode(
            id="ac_disc",
            tag="AC-DISC-1",
            label="AC DISC",
            kind="ac_disconnect",
            icon="AC DISC",
            desc1=f"OCPD: {result.ess.ac_disconnect_ocpd_a} A",
            desc2="VISIBLE LOCKABLE",
        ),
        ElectricalNode(
            id="tap",
            tag="TAP-1",
            label="LINE SIDE TAP",
            kind="interconnection",
            icon="AC DISC",
            desc1=method,
            desc2="NEC 705.11",
        ),
        ElectricalNode(
            id="msp",
            tag="MSP",
            label="MSP / MAIN",
            kind="service_panel",
            icon="MSP",
            desc1=f"{int(i.service.main_panel_a)} A MAIN",
            desc2=f"{int(i.service.busbar_a)} A BUS",
        ),
        ElectricalNode(
            id="meter",
            tag="METER",
            label="UTILITY METER",
            kind="meter",
            icon="M",
            desc1=i.project.meter_info.number or "FIELD VERIFY",
            desc2=i.project.utility or "UTILITY",
        ),
        ElectricalNode(
            id="utility",
            tag="GRID",
            label="UTILITY SOURCE",
            kind="utility",
            icon="MSP",
            desc1="120/240 V",
            desc2="1 PHASE",
        ),
        ElectricalNode(
            id="ges",
            tag="GES",
            label="GROUNDING ELECTRODE SYSTEM",
            kind="grounding",
            icon="MSP",
            desc1=f"GEC #{result.grounding.ac_gec_size} AWG CU",
            desc2="BOND PER NEC 250",
        ),
    ]

    if i.battery.quantity > 0:
        nodes.append(
            ElectricalNode(
                id="ess",
                tag="ESS-1",
                label="ESS",
                kind="ess",
                icon="ESS",
                desc1=f"{i.battery.brand} {i.battery.model}",
                desc2=f"({i.battery.quantity}) / {i.battery.total_kwh:.1f} kWh",
            )
        )

    pv_base = result.pv_string.isc_690_8_a
    ac_base = i.inverter.ac_output_a
    aggregate_ac_base = result.interconnect.total_backfeed_a
    raceways = _raceway_by_tag(result)
    rw_a = raceways.get("A")
    rw_b = raceways.get("B")
    rw_c = raceways.get("C")
    rw_d = raceways.get("D")
    pv_raceway = (
        rw_b.selected_raceway
        if rw_b else
        f"{result.adjacent.pv_conduit.selected_conduit} {result.adjacent.pv_conduit.raceway_type}"
    )
    inv_raceway = (
        rw_c.selected_raceway
        if rw_c else
        f"{result.adjacent.ac_conduit.selected_conduit} {result.adjacent.ac_conduit.raceway_type}"
    )
    ac_raceway = (
        rw_d.selected_raceway
        if rw_d else
        f"{result.adjacent.ac_conduit.selected_conduit} {result.adjacent.ac_conduit.raceway_type}"
    )
    c_tag = "C" + (f"x{n_inv}" if n_inv > 1 else "")

    schedule: list[ConductorScheduleRow] = [
        ConductorScheduleRow(
            tag="A",
            circuit="PV SOURCE",
            source="mlpe",
            target="dc_ocpd",
            kind="DC",
            wires="2+G",
            size=f"{result.pv_conductor.size} AWG",
            conductor_type="THWN-2 CU",
            ground=f"{result.grounding.egc_pv_source} AWG",
            conduit="FREE AIR",
            amps=pv_base,
            ampacity=result.pv_conductor.ampacity_a,
            ocpd_a=result.pv_ocpd_a,
            length_ft=rw_a.length_ft if rw_a else 0.0,
            fill_pct=None,
            note="module/source circuits",
        ),
        ConductorScheduleRow(
            tag="B",
            circuit="PV DC OUTPUT",
            source="dc_ocpd",
            target="inverter",
            kind="DC",
            wires="2+G",
            size=f"{result.pv_conductor.size} AWG",
            conductor_type="THWN-2 CU",
            ground=f"{result.grounding.egc_pv_source} AWG",
            conduit=pv_raceway,
            amps=pv_base,
            ampacity=result.pv_conductor.ampacity_a,
            ocpd_a=result.pv_ocpd_a,
            length_ft=rw_b.length_ft if rw_b else 0.0,
            fill_pct=rw_b.fill.fill_pct if rw_b and rw_b.fill else None,
            note="PV DC OCPD to inverter",
        ),
        ConductorScheduleRow(
            tag=c_tag,
            circuit="INVERTER AC",
            source="inverter",
            target="ac_disc",
            kind="AC",
            wires="3+G",
            size=f"{per_inv_cond.size} AWG",
            conductor_type="THWN-2 CU",
            ground=f"{result.grounding.egc_inverter_ac} AWG",
            conduit=inv_raceway,
            amps=ac_base,
            ampacity=per_inv_cond.ampacity_a,
            ocpd_a=per_inv_ocpd,
            length_ft=rw_c.length_ft if rw_c else 0.0,
            fill_pct=rw_c.fill.fill_pct if rw_c and rw_c.fill else None,
            note="per inverter" if n_inv > 1 else "inverter output",
        ),
        ConductorScheduleRow(
            tag="D",
            circuit="SUPPLY TAP",
            source="ac_disc",
            target="tap",
            kind="AC",
            wires="3+G",
            size=f"{result.ess_conductor.size} AWG",
            conductor_type="THWN-2 CU",
            ground=f"{result.grounding.egc_aggregate_ac} AWG",
            conduit=ac_raceway,
            amps=aggregate_ac_base,
            ampacity=result.ess_conductor.ampacity_a,
            ocpd_a=result.ess.ac_disconnect_ocpd_a,
            length_ft=rw_d.length_ft if rw_d else 0.0,
            fill_pct=rw_d.fill.fill_pct if rw_d and rw_d.fill else None,
            note="NEC 705.11 / 240.21(B)",
        ),
    ]

    edges = [
        ElectricalEdge("pv_to_mlpe", "pv", "mlpe", "DC"),
        ElectricalEdge("a", "mlpe", "dc_ocpd", "DC", tag="A", schedule_tag="A", protection_node="dc_ocpd"),
        ElectricalEdge("b", "dc_ocpd", "inverter", "DC", tag="B", schedule_tag="B", protection_node="dc_ocpd"),
        ElectricalEdge("c", "inverter", "ac_disc", "AC", tag=c_tag, schedule_tag=c_tag, protection_node="ac_disc"),
        ElectricalEdge("d", "ac_disc", "tap", "AC", tag="D", schedule_tag="D", protection_node="ac_disc"),
        ElectricalEdge("service_meter_to_tap", "meter", "tap", "AC"),
        ElectricalEdge("service_utility_to_meter", "utility", "meter", "AC"),
        ElectricalEdge("service_tap_to_msp", "tap", "msp", "AC"),
        ElectricalEdge("ground_msp_to_ges", "msp", "ges", "GROUND"),
    ]
    if i.battery.quantity > 0:
        edges.append(ElectricalEdge("ess_to_inverter", "ess", "inverter", "DC"))

    return ElectricalTopology(
        nodes=tuple(nodes),
        edges=tuple(edges),
        schedule=tuple(schedule),
        interconnection_method=method,
        system_dc_kw=dc_kw,
        system_ac_kw=ac_kw,
    )
