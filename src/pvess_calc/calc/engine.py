"""Top-level orchestrator: inputs.yaml → all NEC calculations."""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Optional

from ..nec.tables import conduit_fill_adjustment, temperature_correction_75c
from ..schema import Inputs, WireLengths
from .adjacent import AdjacentResult, compute_adjacent
from .aic import AicResult, compute_aic
from .conductor import ConductorResult, VoltageDropResult, select_copper, voltage_drop_dc
from .ess import EssResult, compute_ess
from .grounding import GroundingResult, compute_grounding
from .ess_install import EssInstallCompliance, evaluate_ess_install
from .interconnect import InterconnectResult, compute_interconnection
from .ocpd import select_ocpd
from .pv_string import PvStringResult, compute_pv_string
from .roof_layout import RoofLayoutResult, compute_roof_layout
from .site_layout import apply_auto_anchors, auto_anchor_sections
from .voltage_drop import VoltageDropAnalysis, compute_voltage_drop
from .wire_routing import WireRoutingResult, compute_wire_routing


@dataclass
class CalculationResult:
    inputs: Inputs
    pv_string: PvStringResult
    pv_conductor: ConductorResult
    pv_ocpd_a: int
    pv_voltage_drop: VoltageDropResult
    ess: EssResult
    ess_conductor: ConductorResult
    interconnect: InterconnectResult
    grounding: GroundingResult
    # Phase D additions
    voltage_drop_analysis: VoltageDropAnalysis
    aic: AicResult
    pv_derating_factor: float           # NEC 310.15(B) combined
    ac_derating_factor: float
    adjacent: AdjacentResult            # Phase H: AFCI / SPD / ground / conduit
    ess_install: EssInstallCompliance   # K.2.6b: NEC 706.10 + IRC R328
    roof_layout: RoofLayoutResult       # K.2.6c: per-section usable area
    # K.9.1: per-face module placements. Maps roof_section name →
    # list[ModuleInstance]. Empty dict for legacy single-orientation
    # projects (no roof_sections defined) — PV-4 v2 falls back to the
    # K.2.8 grid concept in that case.
    module_placements: dict[str, list] = field(default_factory=dict)
    # K.11: auto-routed wire-trunk lengths from `site.equipment_locations`.
    # When `wire_routing.routed=False` the voltage_drop block used the
    # manual `inputs.wire_lengths` block instead. Always present (even
    # for legacy projects) so consumers can guard on `.routed`.
    wire_routing: Optional[WireRoutingResult] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "inputs": self.inputs.model_dump(mode="json"),
            "pv_string": asdict(self.pv_string),
            "pv_conductor": asdict(self.pv_conductor),
            "pv_ocpd_a": self.pv_ocpd_a,
            "pv_voltage_drop": asdict(self.pv_voltage_drop),
            "ess": asdict(self.ess),
            "ess_conductor": asdict(self.ess_conductor),
            "interconnect": {
                "total_backfeed_a": self.interconnect.total_backfeed_a,
                "existing_solar_a": self.interconnect.existing_solar_a,
                "combined_backfeed_a": self.interconnect.combined_backfeed_a,
                "main_breaker_a": self.interconnect.main_breaker_a,
                "busbar_a": self.interconnect.busbar_a,
                "evaluations": [asdict(e) for e in self.interconnect.evaluations],
                "recommended": self.interconnect.recommended,
                "overall_status": self.interconnect.overall_status,
            },
            "grounding": asdict(self.grounding),
            "voltage_drop_analysis": asdict(self.voltage_drop_analysis),
            "aic": asdict(self.aic),
            "pv_derating_factor": self.pv_derating_factor,
            "ac_derating_factor": self.ac_derating_factor,
            "adjacent": asdict(self.adjacent),
            "ess_install": {
                "install_location": self.ess_install.install_location,
                "overall_status": self.ess_install.overall_status,
                "checks": [asdict(c) for c in self.ess_install.checks],
            },
            "roof_layout": {
                "total_gross_sqft": self.roof_layout.total_gross_sqft,
                "total_usable_sqft": self.roof_layout.total_usable_sqft,
                "total_module_count": self.roof_layout.total_module_count,
                "all_fit": self.roof_layout.all_fit,
                "sections": [asdict(s) for s in self.roof_layout.sections],
            },
            "wire_routing": (
                {
                    "routed": self.wire_routing.routed,
                    "fallback_reason": self.wire_routing.fallback_reason,
                    "pv_string_one_way_ft": self.wire_routing.pv_string_one_way_ft,
                    "pv_to_combiner_ft": self.wire_routing.pv_to_combiner_ft,
                    "inverter_to_ac_disc_ft": self.wire_routing.inverter_to_ac_disc_ft,
                    "ac_disc_to_msp_ft": self.wire_routing.ac_disc_to_msp_ft,
                    "ess_to_inverter_ft": self.wire_routing.ess_to_inverter_ft,
                    "segments": [asdict(s) for s in self.wire_routing.segments],
                }
                if self.wire_routing is not None
                else None
            ),
        }


# Default assumed DC home-run length when inputs.yaml does not specify one.
# Phase 0: information-only voltage-drop estimate.
DEFAULT_PV_DC_LENGTH_FT = 50.0


def _try_parse_lat(coordinates: str) -> Optional[float]:
    """K.9.2 — pull lat from `project.coordinates` strings like
    "33.141418, -96.801258" (the wizard's K.3 pre-fill format).
    Returns None when the string is empty or malformed (best-effort)."""
    if not coordinates:
        return None
    try:
        return float(coordinates.split(",")[0].strip())
    except (ValueError, IndexError):
        return None


def run(inputs: Inputs) -> CalculationResult:
    # Stage B — auto-anchor any RoofSection without explicit
    # `site_anchor_x_ft`. Patches `inputs.site.roof_sections` in a
    # fresh copy; downstream code (wire_routing, EE-4 renderer, doctor)
    # sees consistent anchor state regardless of yaml verbosity.
    auto_anchors = auto_anchor_sections(inputs.site)
    if auto_anchors:
        patched_site = apply_auto_anchors(inputs.site, auto_anchors)
        inputs = inputs.model_copy(update={"site": patched_site})

    # NEC 310.15(B)(2)(a) + (3)(a)(1) derating from project routing context.
    routing = inputs.routing
    temp_factor = temperature_correction_75c(routing.ambient_temp_c)
    pv_derating = temp_factor * conduit_fill_adjustment(routing.pv_conduit_fill_count)
    ac_derating = temp_factor * conduit_fill_adjustment(routing.ac_conduit_fill_count)

    pv = compute_pv_string(inputs.pv_array, nec_edition=inputs.project.nec_edition)
    # OCPD is sized first; conductor must then satisfy both 310.16 ampacity
    # AND 240.4(D) small-conductor rule given the selected OCPD.
    pv_ocpd = select_ocpd(pv.ocpd_minimum_a)
    pv_conductor = select_copper(
        pv.conductor_required_a,
        insulation="75C",
        upstream_ocpd_a=pv_ocpd,
        derating_factor=pv_derating,
    )
    pv_vd = voltage_drop_dc(
        size=pv_conductor.size,
        one_way_length_ft=DEFAULT_PV_DC_LENGTH_FT,
        current_a=pv.isc_690_8_a,
        nominal_voltage=pv.string_voc_cold,
    )

    ess = compute_ess(inputs)
    ess_conductor = select_copper(
        ess.ac_disconnect_min_a,
        insulation="75C",
        upstream_ocpd_a=ess.ac_disconnect_ocpd_a,
        derating_factor=ac_derating,
    )

    interconnect = compute_interconnection(inputs)

    # NEC 250.66 / 250.122 grounding sizes. Per-inverter OCPD matters when
    # multiple inverters share an AC trunk — each leg gets its own EGC.
    per_inv_ocpd = select_ocpd(inputs.inverter.ac_output_a * 1.25)
    grounding = compute_grounding(
        service_amps=inputs.service.main_panel_a,
        pv_source_amps=pv.isc_690_8_a,
        pv_ocpd_a=pv_ocpd,
        per_inverter_ocpd_a=per_inv_ocpd,
        aggregate_ac_ocpd_a=ess.ac_disconnect_ocpd_a,
        ess_ocpd_a=ess.ac_disconnect_ocpd_a,
        # K.5: pass the project's actual GES so the result carries
        # GEC comparison + real electrode list. The compute_grounding
        # function preserves legacy behaviour when ges=None.
        ges=inputs.service.grounding_electrode_system,
    )

    # Phase D voltage-drop analysis (uses real wire lengths from inputs).
    n_inv = inputs.inverter.count(inputs.battery.quantity)
    per_inv_cond = select_copper(
        inputs.inverter.ac_output_a * 1.25,
        insulation="75C",
        upstream_ocpd_a=per_inv_ocpd,
        derating_factor=ac_derating,
    )

    # K.9.1 + K.10 — must run BEFORE voltage_drop because K.11 wire
    # routing needs the K.9.1 module placements. Placements stored in
    # a local `module_placements` here; voltage_drop sees auto-routed
    # lengths when `site.equipment_locations` is populated.
    module_placements = _compute_module_placements(inputs)

    # K.11 — auto-route wire trunks from site geometry. When
    # `equipment_locations.has_data` is False, returns `routed=False`
    # and the engine keeps the manual `inputs.wire_lengths` block.
    wire_routing = compute_wire_routing(
        inputs, module_placements=module_placements,
    )
    if wire_routing.routed:
        # Build an overlay Inputs with auto-computed wire_lengths.
        # `WireLengths` is treated as a value object — Pydantic
        # model_copy + update keeps everything else identical.
        overlay_wl = WireLengths(
            pv_string_one_way_ft=wire_routing.pv_string_one_way_ft,
            pv_to_combiner_ft=wire_routing.pv_to_combiner_ft,
            combiner_to_inverter_ft=wire_routing.pv_to_combiner_ft,
            inverter_to_ac_disc_ft=wire_routing.inverter_to_ac_disc_ft,
            ac_disc_to_msp_ft=wire_routing.ac_disc_to_msp_ft,
            ess_to_inverter_ft=wire_routing.ess_to_inverter_ft,
        )
        inputs_for_vd = inputs.model_copy(update={"wire_lengths": overlay_wl})
    else:
        inputs_for_vd = inputs

    vd_analysis = compute_voltage_drop(
        inputs_for_vd,
        pv_string_voc_cold=pv.string_voc_cold,
        pv_source_current_a=pv.isc_690_8_a,
        pv_conductor_size=pv_conductor.size,
        per_inverter_current_a=inputs.inverter.ac_output_a,
        per_inverter_conductor_size=per_inv_cond.size,
        aggregate_ac_current_a=ess.ac_disconnect_min_a,
        aggregate_ac_conductor_size=ess_conductor.size,
    )

    # Phase D AIC validation (NEC 110.24).
    aic = compute_aic(
        inputs,
        ocpd_ratings={
            "PV source OCPD": pv_ocpd,
            "Per-inverter AC OCPD": per_inv_ocpd,
            "ESS AC disconnect OCPD": ess.ac_disconnect_ocpd_a,
            "MSP main breaker": int(inputs.service.main_panel_a),
        },
    )

    # Phase H: AFCI / SPD / ground rod topology / conduit fill
    adjacent = compute_adjacent(
        inputs,
        pv_conductor_size=pv_conductor.size,
        ac_conductor_size=ess_conductor.size,
        pv_conductor_count=2,
        ac_conductor_count=3,
        pv_ground_size=grounding.egc_pv_source,
        ac_ground_size=grounding.egc_aggregate_ac,
    )

    # K.2.6b: NEC 706.10 + IRC R328 ESS install-location compliance.
    ess_install = evaluate_ess_install(inputs)

    # K.2.6c: per-roof-section usable area (setbacks + obstructions).
    roof_layout = compute_roof_layout(inputs)

    return CalculationResult(
        inputs=inputs,
        pv_string=pv,
        pv_conductor=pv_conductor,
        pv_ocpd_a=pv_ocpd,
        pv_voltage_drop=pv_vd,
        ess=ess,
        ess_conductor=ess_conductor,
        interconnect=interconnect,
        grounding=grounding,
        voltage_drop_analysis=vd_analysis,
        aic=aic,
        pv_derating_factor=pv_derating,
        ac_derating_factor=ac_derating,
        adjacent=adjacent,
        ess_install=ess_install,
        roof_layout=roof_layout,
        module_placements=module_placements,
        wire_routing=wire_routing,
    )


def _compute_module_placements(inputs: Inputs) -> dict[str, list]:
    """K.9.1 + K.10 — per-face module placements with string assignment.

    Two-step pipeline:
      1. Resolve per-face module counts via `distribute_modules_to_faces`
         — this respects designer-pinned yaml counts AND falls back to
         K.8.1 LRM auto-distribute when yaml has all zeros (K.3c init).
      2. For each face with a positive count, run `place_modules` to
         figure out (x, y, rotation) per module.
      3. K.10.2 — assign each placement a string_index. Flat-list pass
         over ALL faces so a string can span face boundaries when needed
         (typical: South + South #2 each hold partial strings). The
         algorithm prefers face-coupling and ridge-first sequence.

    Returns empty dict for legacy single-orientation projects → PV-4
    v2 falls back to the K.2.8 grid concept; K.11 wire-routing falls
    back to manual wire_lengths.

    Latitude for K.8.2 value-weighting: try project.coordinates first
    (the wizard's K.3 pre-fill writes "lat, lng"); the customer-PDF
    path also pulls from lookup_fields but engine doesn't have those.
    """
    from .face_distribution import distribute_modules_to_faces
    from .module_placement import place_modules
    from .string_assignment import assign_modules_to_strings

    latitude_deg = _try_parse_lat(inputs.project.coordinates)
    face_counts = distribute_modules_to_faces(
        inputs, latitude_deg=latitude_deg,
    )
    placements: dict[str, list] = {}
    mod = inputs.pv_array.module
    for section in inputs.site.roof_sections:
        count = face_counts.get(section.name, 0)
        if count <= 0:
            continue
        placed = place_modules(
            section,
            module_length_in=mod.length_in,
            module_width_in=mod.width_in,
            target_count=count,
        )
        if placed:
            placements[section.name] = placed

    all_placements = [m for face_list in placements.values()
                      for m in face_list]
    assigned = assign_modules_to_strings(
        all_placements,
        n_strings=inputs.pv_array.strings,
        modules_per_string=inputs.pv_array.modules_per_string,
    )
    placements = {}
    for m in assigned:
        placements.setdefault(m.face_name, []).append(m)
    return placements
