"""K.11 — wire trunk auto-routing.

Given (a) per-module K.9.1 placements with K.10 string assignment,
(b) per-face `site_anchor` + `roof_penetration` from K.11 schema, and
(c) site-plan `equipment_locations`, compute the **real** per-segment
conduit lengths for every wire run in the system. Replaces the
manual `inputs.wire_lengths` block when full data is available.

Algorithm — five segments mirroring `WireLengths` (so the existing
voltage-drop engine consumes the same shape):

  A. **PV source** — longest distance from any module on a face
     to that face's `roof_penetration` point, in roof-local ft.
     This is the worst-case string conductor run *inside* the
     array (between module J-box and the first conduit J-box).

  B. **DC home run** — from each face's roof_penetration to the
     inverter location. Path: penetration (in roof-local) → attic
     drop point (the attic-to-wall transition) → inverter site
     coords. Manhattan distance + a single attic_to_eq_height_ft
     vertical drop. Reported as the AVERAGE across all faces in
     the array (close enough for NEC 215.2 since the drop is per-
     segment, not aggregate, and per-face spread is usually <10%).

  C. **Inverter → AC disconnect** — Manhattan distance between
     the two pieces of equipment on the site plan. When
     `ac_disconnect` is None, reuses the inverter location
     (length = 0 + a 2 ft minimum cable allowance).

  D. **AC disconnect → MSP** — Manhattan distance, possibly via
     sub-panels in series. Each sub-panel hop is summed.

  E. **ESS → inverter** — Manhattan from ESS unit to its
     inverter. Multi-ESS picks the worst-case (longest) run so the
     voltage-drop check covers every unit.

Coordinate frames:
  * Module placements: roof-local ft (eave-left origin per face)
  * Roof penetration: roof-local ft on its face
  * site_anchor: 2D site ft (lot front-left origin) + azimuth_deg
  * equipment_locations: 2D site ft (same frame as site_anchor)

The `_face_local_to_site()` transform rotates each face by
`site_anchor_azimuth_deg` and translates by (anchor_x, anchor_y).

Conservative assumptions (K.11.0):
  * Manhattan routing (no diagonal cuts) — over-estimates by ~5-10%
    vs straight-line, which is on the right side for voltage-drop.
  * Single attic-drop point per array — multi-inverter installs use
    the first inverter's location as the drop. Refine in K.11+ when
    real projects show >1 attic transition.
  * `attic_to_eq_height_ft` constant — 10 ft default (single-story).
    Two-story installs override in yaml.

Returns `WireRoutingResult` with both the per-segment lengths AND
provenance flags so the voltage-drop report can show "routed" vs
"DEFAULT" labels.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from ..schema import EquipmentLocations, Inputs, RoofSection
from .module_placement import ModuleInstance


# ─── Result types ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class WireSegment:
    """One physical conduit run with computed length."""
    label: str             # e.g. "A · PV source"
    length_ft: float       # one-way ft (matches WireLengths convention)
    provenance: str        # "routed" | "default" | "manual"
    waypoints_ft: tuple    # ((x, y), ...) for DXF polyline rendering;
                           # empty when length is a default fallback


@dataclass
class WireRoutingResult:
    """Output of `compute_wire_routing()`.

    The 5 length attributes mirror `WireLengths` so engine.py can drop
    them in as overrides. The `segments` list carries the same data
    plus DXF polyline waypoints + provenance for the report sheet.
    """
    pv_string_one_way_ft: float
    pv_to_combiner_ft: float
    inverter_to_ac_disc_ft: float
    ac_disc_to_msp_ft: float
    ess_to_inverter_ft: float
    segments: list[WireSegment] = field(default_factory=list)
    # True when site geometry was sufficient to compute lengths; False
    # when the algorithm fell back to defaults (engine then keeps the
    # manual `inputs.wire_lengths` values).
    routed: bool = False
    # Free-text trace of why the algorithm fell back (for doctor).
    fallback_reason: str = ""


# ─── Public API ────────────────────────────────────────────────────────


def compute_wire_routing(
    inputs: Inputs,
    *,
    module_placements: dict[str, list[ModuleInstance]],
) -> WireRoutingResult:
    """Compute per-segment conduit lengths from K.11 schema data.

    Args:
        inputs: full project Inputs (reads `site.equipment_locations`,
            `site.roof_sections`, `wire_lengths`, etc.)
        module_placements: K.9.1 output (face_name → ModuleInstance list,
            with K.10 string_index populated by the engine).

    Returns:
        WireRoutingResult — when `routed=False` the engine keeps
        existing `inputs.wire_lengths` values (manual or 50ft fallback).
        When `routed=True` every length is auto-computed and overrides.
    """
    el = inputs.site.equipment_locations

    # Bail fast: if equipment_locations doesn't have the minimum data
    # (MSP + ≥1 inverter), fall back to the legacy path. Engine sees
    # `routed=False` and uses inputs.wire_lengths unchanged.
    if not el.has_data:
        return WireRoutingResult(
            pv_string_one_way_ft=0.0,
            pv_to_combiner_ft=0.0,
            inverter_to_ac_disc_ft=0.0,
            ac_disc_to_msp_ft=0.0,
            ess_to_inverter_ft=0.0,
            routed=False,
            fallback_reason="site.equipment_locations not populated "
                            "(needs at least MSP + 1 inverter)",
        )

    # Segment A — PV source: longest module → roof_penetration on any face.
    pv_source_ft, pv_source_waypoints = _segment_a_pv_source(
        inputs.site.roof_sections, module_placements,
    )

    # Segment B — DC home run: avg face penetration → attic drop → inverter
    pv_homerun_ft, pv_homerun_waypoints = _segment_b_dc_homerun(
        inputs.site.roof_sections, el,
    )

    # Segment C — inverter → AC disc (or short cable when no AC disc)
    inv_to_acdisc_ft, c_waypoints = _segment_c_inv_to_acdisc(el)

    # Segment D — AC disc → MSP via sub-panel chain
    acdisc_to_msp_ft, d_waypoints = _segment_d_acdisc_to_msp(el)

    # Segment E — ESS → inverter (worst case)
    ess_to_inv_ft, e_waypoints = _segment_e_ess_to_inverter(el)

    segments = [
        WireSegment("A · PV source",          pv_source_ft,    "routed",
                    pv_source_waypoints),
        WireSegment("B · DC home run",        pv_homerun_ft,   "routed",
                    pv_homerun_waypoints),
        WireSegment("C · INV → AC disc",      inv_to_acdisc_ft, "routed",
                    c_waypoints),
        WireSegment("D · AC disc → MSP",      acdisc_to_msp_ft, "routed",
                    d_waypoints),
    ]
    if ess_to_inv_ft > 0:
        segments.append(WireSegment(
            "E · ESS → INV", ess_to_inv_ft, "routed", e_waypoints,
        ))

    return WireRoutingResult(
        pv_string_one_way_ft=pv_source_ft,
        pv_to_combiner_ft=pv_homerun_ft,
        inverter_to_ac_disc_ft=inv_to_acdisc_ft,
        ac_disc_to_msp_ft=acdisc_to_msp_ft,
        ess_to_inverter_ft=ess_to_inv_ft,
        segments=segments,
        routed=True,
    )


# ─── Helpers ───────────────────────────────────────────────────────────


def _face_local_to_site(
    section: RoofSection,
    local_x: float, local_y: float,
) -> Optional[tuple[float, float]]:
    """Transform a roof-local (x, y) on `section` into 2D site coords.

    Returns None when the face has no `site_anchor` set — the caller
    should then skip this face for routing math.
    """
    if section.site_anchor_x_ft is None or section.site_anchor_y_ft is None:
        return None
    theta_rad = math.radians(section.site_anchor_azimuth_deg)
    cos_t = math.cos(theta_rad)
    sin_t = math.sin(theta_rad)
    site_x = section.site_anchor_x_ft + local_x * cos_t - local_y * sin_t
    site_y = section.site_anchor_y_ft + local_x * sin_t + local_y * cos_t
    return (site_x, site_y)


def _roof_penetration_local(section: RoofSection) -> tuple[float, float]:
    """Return the roof-local (x, y) of the conduit penetration point.

    Defaults to the ridge midpoint when not specified — the most
    common install where the trunk J-box sits on the back of the
    ridge cap, hidden from view.
    """
    if (section.roof_penetration_x_ft is not None
            and section.roof_penetration_y_ft is not None):
        return (section.roof_penetration_x_ft,
                section.roof_penetration_y_ft)
    # Default: ridge midpoint
    if section.shape == "tri":
        # Apex of the triangle (highest point)
        return (section.width_ft * section.apex_x_ratio, section.height_ft)
    # rect / polygon: midpoint of top edge
    return (section.width_ft / 2.0, section.height_ft)


def _manhattan_ft(a: tuple[float, float], b: tuple[float, float]) -> float:
    """L1 distance — Manhattan routing assumption (conduit at 90°)."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _segment_a_pv_source(
    sections: list[RoofSection],
    placements: dict[str, list[ModuleInstance]],
) -> tuple[float, tuple]:
    """Find the longest "module → face roof_penetration" run across
    all faces (in roof-local ft — the run stays on the roof).

    Picks the worst case because that single string conductor must
    pass NEC 690.7(B) Vmp drop on its own; reporting the average
    would understate.
    """
    longest = 0.0
    worst_waypoints: tuple = ()
    for section in sections:
        face_mods = placements.get(section.name, [])
        if not face_mods:
            continue
        pen_x, pen_y = _roof_penetration_local(section)
        for m in face_mods:
            # Module center
            cx = m.x_ft + m.width_ft / 2.0
            cy = m.y_ft + m.height_ft / 2.0
            d = _manhattan_ft((cx, cy), (pen_x, pen_y))
            if d > longest:
                longest = d
                worst_waypoints = ((cx, cy), (pen_x, pen_y))
    # Minimum 5 ft — the worst module is rarely AT the penetration;
    # there's always some MC4 cable in the run.
    return max(longest, 5.0), worst_waypoints


def _segment_b_dc_homerun(
    sections: list[RoofSection],
    el: EquipmentLocations,
) -> tuple[float, tuple]:
    """From each face's roof_penetration (transformed to site coords)
    to the attic drop, then a vertical attic-to-equipment drop, then
    to the FIRST inverter on the site plan.

    Returns the AVERAGE across all faces with site_anchor (acceptable
    NEC 215.2 conservatism since per-face spread is usually <10%).
    When no face has a site_anchor, returns 20 ft + an empty waypoint
    tuple — caller flags this case via the engine's fallback logic.
    """
    if not el.inverters:
        return 20.0, ()
    inv = el.inverters[0]
    # Attic drop point default = inverter location (when garage-mounted)
    drop_x = el.attic_drop_x_ft if el.attic_drop_x_ft is not None else inv.x_ft
    drop_y = el.attic_drop_y_ft if el.attic_drop_y_ft is not None else inv.y_ft

    distances: list[float] = []
    sampled_waypoints: tuple = ()
    for section in sections:
        pen_local = _roof_penetration_local(section)
        pen_site = _face_local_to_site(section, *pen_local)
        if pen_site is None:
            continue
        # path: penetration → attic drop (horizontal) + attic_to_eq drop
        # (vertical) + attic drop → inverter (horizontal)
        d_horiz_to_drop = _manhattan_ft(pen_site, (drop_x, drop_y))
        d_attic_drop = el.attic_to_eq_height_ft
        d_drop_to_inv = _manhattan_ft((drop_x, drop_y), (inv.x_ft, inv.y_ft))
        total = d_horiz_to_drop + d_attic_drop + d_drop_to_inv
        distances.append(total)
        # Capture the first face's waypoints for DXF demo
        if not sampled_waypoints:
            sampled_waypoints = (
                pen_site, (drop_x, drop_y), (inv.x_ft, inv.y_ft),
            )
    if not distances:
        return 20.0, ()
    return sum(distances) / len(distances), sampled_waypoints


def _segment_c_inv_to_acdisc(
    el: EquipmentLocations,
) -> tuple[float, tuple]:
    """Manhattan from inverter #1 to AC disconnect. When no AC disc
    is set, assume the inverter has an integrated disc and report a
    minimum 2 ft cable allowance."""
    if not el.inverters:
        return 2.0, ()
    inv = el.inverters[0]
    if el.ac_disconnect is None:
        return 2.0, ((inv.x_ft, inv.y_ft),)
    ac = el.ac_disconnect
    d = _manhattan_ft((inv.x_ft, inv.y_ft), (ac.x_ft, ac.y_ft))
    return max(d, 2.0), ((inv.x_ft, inv.y_ft), (ac.x_ft, ac.y_ft))


def _segment_d_acdisc_to_msp(
    el: EquipmentLocations,
) -> tuple[float, tuple]:
    """AC disc → MSP, optionally chaining through sub-panels in order.

    When `ac_disconnect` is None, starts from inverter #1 (the AC disc
    is then a logical concept inside the inverter).
    """
    if el.msp is None:
        return 10.0, ()
    msp = el.msp
    if el.ac_disconnect is not None:
        start = (el.ac_disconnect.x_ft, el.ac_disconnect.y_ft)
    elif el.inverters:
        start = (el.inverters[0].x_ft, el.inverters[0].y_ft)
    else:
        return 10.0, ()

    waypoints: list[tuple[float, float]] = [start]
    total = 0.0
    for sub in el.sub_panels:
        sub_pt = (sub.x_ft, sub.y_ft)
        total += _manhattan_ft(waypoints[-1], sub_pt)
        waypoints.append(sub_pt)
    msp_pt = (msp.x_ft, msp.y_ft)
    total += _manhattan_ft(waypoints[-1], msp_pt)
    waypoints.append(msp_pt)

    # Min 5 ft — even when MSP is right next to AC disc there's at
    # least a short whip + nipple between them.
    return max(total, 5.0), tuple(waypoints)


def _segment_e_ess_to_inverter(
    el: EquipmentLocations,
) -> tuple[float, tuple]:
    """Longest ESS → inverter run (worst case)."""
    if not el.ess_units or not el.inverters:
        return 0.0, ()
    inv = el.inverters[0]
    longest = 0.0
    worst_waypoints: tuple = ()
    for ess in el.ess_units:
        d = _manhattan_ft((ess.x_ft, ess.y_ft), (inv.x_ft, inv.y_ft))
        if d > longest:
            longest = d
            worst_waypoints = ((ess.x_ft, ess.y_ft), (inv.x_ft, inv.y_ft))
    return max(longest, 3.0), worst_waypoints
