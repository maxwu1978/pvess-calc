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
from .geometry import polygons_overlap_area
from .interconnect import InterconnectResult, compute_interconnection
from .ocpd import select_ocpd
from .pv_string import PvStringResult, compute_pv_string
from .roof_layout import RoofLayoutResult, compute_roof_layout
from .site_layout import apply_auto_anchors, auto_anchor_sections
from .voltage_drop import VoltageDropAnalysis, compute_voltage_drop
from .wire_routing import WireRoutingResult, compute_wire_routing, _face_local_to_site


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
    # Phase I: state/AHJ-specific filing and regional-rule summary.
    # Populated after the core result exists because regional checks consume
    # the full CalculationResult.
    regional: Any = None
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
            "regional": (
                asdict(self.regional) if self.regional is not None else None
            ),
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


def run(inputs: Inputs, *, ahj_profile: str | None = None) -> CalculationResult:
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
        per_inverter_ac_conductor_size=per_inv_cond.size,
        pv_conductor_count=2,
        ac_conductor_count=3,
        pv_ground_size=grounding.egc_pv_source,
        per_inverter_ground_size=grounding.egc_inverter_ac,
        ac_ground_size=grounding.egc_aggregate_ac,
        wire_routing=wire_routing,
        ahj_profile=ahj_profile,
    )

    # K.2.6b: NEC 706.10 + IRC R328 ESS install-location compliance.
    ess_install = evaluate_ess_install(inputs)

    # K.2.6c: per-roof-section usable area (setbacks + obstructions).
    roof_layout = compute_roof_layout(inputs)

    result = CalculationResult(
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
    from ..regional.summary import evaluate_regional_requirements

    result.regional = evaluate_regional_requirements(result)
    return result


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
         algorithm prefers face-coupling and keeps string sequencing
         deterministic after the final geometry is selected.

    Returns empty dict for legacy single-orientation projects → PV-4
    v2 falls back to the K.2.8 grid concept; K.11 wire-routing falls
    back to manual wire_lengths.

    Latitude for K.8.2 value-weighting: try project.coordinates first
    (the wizard's K.3 pre-fill writes "lat, lng"); the customer-PDF
    path also pulls from lookup_fields but engine doesn't have those.
    """
    from .face_distribution import distribute_modules_to_faces
    from .module_placement import place_module_candidates, place_modules
    from .string_assignment import assign_modules_to_strings

    latitude_deg = _try_parse_lat(inputs.project.coordinates)
    face_counts = distribute_modules_to_faces(
        inputs, latitude_deg=latitude_deg,
    )
    candidates_by_face: dict[str, list] = {}
    mod = inputs.pv_array.module
    for section in inputs.site.roof_sections:
        count = face_counts.get(section.name, 0)
        if count <= 0:
            candidates_by_face[section.name] = []
            continue
        candidates = place_modules(
            section,
            module_length_in=mod.length_in,
            module_width_in=mod.width_in,
            target_count=max(inputs.pv_array.modules * 2, 60),
        )
        if _should_use_polygon_wedge_candidates(section, count, candidates):
            all_candidates = place_module_candidates(
                section,
                module_length_in=mod.length_in,
                module_width_in=mod.width_in,
            )
            portrait = [
                module for module in all_candidates
                if round(float(module.rotation_deg), 2) == 0.0
            ]
            if (
                len(portrait) >= count
                and _candidate_set_uses_low_left_wedge(portrait)
            ):
                candidates = portrait
            else:
                candidates = all_candidates
        candidates_by_face[section.name] = _ordered_module_candidates(
            section,
            candidates,
            requested_count=count,
        )

    placements = _select_module_placements(
        inputs,
        face_counts=face_counts,
        candidates_by_face=candidates_by_face,
    )

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


def _select_module_placements(
    inputs: Inputs,
    *,
    face_counts: dict[str, int],
    candidates_by_face: dict[str, list],
) -> dict[str, list]:
    """Select final modules from per-face candidates.

    R4 contract:
      * keep designer-declared counts when the geometry allows them;
      * recycle shortfall into better faces before worse faces;
      * prevent the same physical roof area from receiving overlapping
        module rectangles when CAD-reviewed facets overlap.
    """
    target_total = max(0, int(inputs.pv_array.modules))
    if target_total <= 0:
        return {}

    ordered_sections = sorted(
        enumerate(inputs.site.roof_sections),
        key=lambda item: (
            _roof_face_install_priority(item[1]),
            -face_counts.get(item[1].name, 0),
            item[0],
        ),
    )
    placements: dict[str, list] = {}
    selected_polys: list[list[tuple[float, float]]] = []
    used_keys: set[tuple] = set()

    def _try_take(section, module) -> bool:
        key = _module_candidate_key(module)
        if key in used_keys:
            return False
        module_poly = _module_site_polygon(section, module)
        if any(polygons_overlap_area(module_poly, existing)
               for existing in selected_polys):
            return False
        placements.setdefault(section.name, []).append(module)
        selected_polys.append(module_poly)
        used_keys.add(key)
        return True

    non_north_sections = [
        item for item in ordered_sections
        if _roof_face_install_priority(item[1]) < 9
    ]

    def _placed_total_now() -> int:
        return sum(len(face) for face in placements.values())

    def _fill_from_sections(sections) -> None:
        while _placed_total_now() < target_total:
            progressed = False
            for _, section in sections:
                if _placed_total_now() >= target_total:
                    break
                for module in candidates_by_face.get(section.name, []):
                    if _try_take(section, module):
                        progressed = True
                        break
            if not progressed:
                break

    # First pass: honor requested per-face counts as much as possible on
    # usable solar faces. Small requested facets go first so a broad face
    # does not consume the only legal candidate on an adjacent tiny facet.
    # North-facing faces are intentionally deferred until the end; they are
    # a last resort, not a peer target.
    first_pass_sections = sorted(
        non_north_sections,
        key=lambda item: (
            _roof_face_install_priority(item[1]),
            max(0, face_counts.get(item[1].name, 0)),
            item[0],
        ),
    )
    for _, section in first_pass_sections:
        requested = max(0, face_counts.get(section.name, 0))
        if requested <= 0:
            continue
        for module in candidates_by_face.get(section.name, []):
            if len(placements.get(section.name, [])) >= requested:
                break
            _try_take(section, module)

    # Second pass: recycle shortfall into available roof area. The same
    # priority order encodes the R4 design preference: southwest first,
    # east second, south/west acceptable.
    _fill_from_sections(non_north_sections)

    # Final pass: use every remaining face, including north, only if the
    # better orientations cannot physically hit the requested total.
    if _placed_total_now() < target_total:
        _fill_from_sections(ordered_sections)
    return placements


def _ordered_module_candidates(
    section,
    candidates: list,
    *,
    requested_count: int,
) -> list:
    """Order legal module candidates in a drafter-like selection sequence.

    `place_modules()` still returns the historical ridge-first list for direct
    callers.  The engine, however, should consume all legal candidates and
    prefer the eave/down-slope side first.  That makes wedge/triangular usable
    areas at the lower edge visible in the final design instead of silently
    leaving them unused once the target count has already been met.
    """
    if len(candidates) <= max(1, requested_count) + 2:
        return candidates
    return sorted(
        candidates,
        key=lambda m: (
            round(float(m.y_ft), 4),
            round(float(m.x_ft), 4),
        ),
    )


def _should_use_polygon_wedge_candidates(
    section,
    requested_count: int,
    base_candidates: list,
) -> bool:
    """Use alternate orientation candidates only for real polygon wedges."""
    if getattr(section, "shape", "") != "polygon":
        return False
    if requested_count < 20:
        return False
    return len(base_candidates) >= requested_count + 8


def _candidate_set_uses_low_left_wedge(candidates: list) -> bool:
    if not candidates:
        return False
    xs = sorted(float(m.x_ft) for m in candidates)
    ys = sorted(float(m.y_ft) for m in candidates)
    x_cut = xs[max(0, int(len(xs) * 0.30) - 1)]
    y_cut = ys[max(0, int(len(ys) * 0.30) - 1)]
    return any(float(m.x_ft) <= x_cut and float(m.y_ft) <= y_cut for m in candidates)


def _roof_face_install_priority(section) -> int:
    """Lower is better for R4 PV layout selection.

    Azimuth convention follows the schema: 0 north, 90 east, 180 south,
    270 west. This intentionally keeps north-facing roof areas as the
    last-resort bucket.
    """
    az = float(getattr(section, "azimuth_deg", 180.0)) % 360.0
    if 202.5 <= az <= 247.5:
        return 0   # southwest target quadrant
    if 67.5 <= az <= 112.5:
        return 1   # east second
    if 135.0 <= az < 202.5 or 247.5 < az <= 292.5:
        return 2   # south / west usable
    if 112.5 < az < 135.0 or 292.5 < az < 337.5:
        return 3   # southeast / northwest shoulder
    return 9       # north-facing last resort


def _module_candidate_key(module) -> tuple:
    return (
        module.face_name,
        round(float(module.x_ft), 4),
        round(float(module.y_ft), 4),
        round(float(module.width_ft), 4),
        round(float(module.height_ft), 4),
        round(float(module.rotation_deg), 2),
    )


def _module_site_polygon(section, module) -> list[tuple[float, float]]:
    local = [
        (module.x_ft, module.y_ft),
        (module.x_ft + module.width_ft, module.y_ft),
        (module.x_ft + module.width_ft, module.y_ft + module.height_ft),
        (module.x_ft, module.y_ft + module.height_ft),
    ]
    points = [_face_local_to_site(section, x, y) for x, y in local]
    if all(point is not None for point in points):
        return [point for point in points if point is not None]
    return local
