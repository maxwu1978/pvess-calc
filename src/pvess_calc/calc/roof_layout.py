"""K.2.6c — roof usable-area engine.

For each `RoofSection` compute the area that's actually available for
PV modules after subtracting:

  1. Per-edge setbacks (NEC 690.12 fire access, IRC 2024 rooftop
     pathway requirements). Each edge type (eave / ridge / rake /
     valley / hip / apex) carries its own setback distance.
  2. Obstructions (chimneys, skylights, VTRs, HVAC units) plus a
     clear-space halo around each (default 18").

Geometry support — two shapes:
  * `rect` — standard gable / shed face. Axis-aligned inset rectangle
    math: shrink by per-side setback, then AABB-subtract every
    obstruction-with-halo.
  * `tri` — hip-roof triangular face. Uses the inradius-shrink
    formula:  A' = A × ((r − d) / r)² where r = 2A/P (incircle radius)
    and d is the uniform inset. Exact for uniform setbacks; when eave
    and hip setbacks differ we use the larger (most restrictive).

Module fit check: given a section's usable area, can we fit
`module_count` modules of standard size (~22 sqft each + 10 % spacing
overhead)? Used by the doctor to flag "you said 20 modules but the
roof only fits 14".

The whole module is additive-compatible: a yaml without
`obstructions` / `edge_setbacks` simply uses `default_setback_ft`
(1.5 ft / 18") on every edge.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from ..schema import Inputs, RoofSection


# Per-module footprint (sqft) — based on a 60-cell mono module
# 65 × 39 in = ~17.5 sqft + ~25 % spacing/walking room → 22 sqft
# This is intentionally conservative; the doctor compares against
# `module_count × MODULE_FOOTPRINT_SQFT` so a slight overestimate
# protects against over-promising what the roof can hold.
MODULE_FOOTPRINT_SQFT: float = 22.0


@dataclass
class SectionLayoutResult:
    """Per-RoofSection usable-area breakdown."""
    name: str
    shape: str                    # "rect" / "tri"
    gross_area_sqft: float
    setback_loss_sqft: float
    obstruction_loss_sqft: float
    usable_area_sqft: float
    module_count: int             # what yaml claims fits here
    module_demand_sqft: float     # module_count × MODULE_FOOTPRINT_SQFT
    fits: bool                    # demand ≤ usable_area
    obstructions_outside_usable_area: list[str] = field(default_factory=list)


@dataclass
class RoofLayoutResult:
    sections: list[SectionLayoutResult]

    @property
    def total_gross_sqft(self) -> float:
        return sum(s.gross_area_sqft for s in self.sections)

    @property
    def total_usable_sqft(self) -> float:
        return sum(s.usable_area_sqft for s in self.sections)

    @property
    def total_module_count(self) -> int:
        return sum(s.module_count for s in self.sections)

    @property
    def all_fit(self) -> bool:
        return all(s.fits for s in self.sections)


def compute_roof_layout(inputs: Inputs) -> RoofLayoutResult:
    """Run usable-area for every roof_section in `inputs.site`."""
    sections = [_evaluate_section(rs) for rs in inputs.site.roof_sections]
    return RoofLayoutResult(sections=sections)


# ─── Per-section evaluation ────────────────────────────────────────────


def _evaluate_section(rs: RoofSection) -> SectionLayoutResult:
    gross = rs.gross_area_sqft
    if rs.shape == "rect":
        usable_polygon_area, setback_loss = _rect_usable_after_setbacks(rs)
    elif rs.shape == "tri":
        usable_polygon_area, setback_loss = _tri_usable_after_setbacks(rs)
    else:  # K.2.7 polygon
        usable_polygon_area, setback_loss = _polygon_usable_after_setbacks(rs)

    # Subtract obstructions (AABB approximation w/ halo).
    obs_loss = 0.0
    outside: list[str] = []
    for obs in rs.obstructions:
        halo_w = obs.width_ft + 2 * obs.setback_ft
        halo_h = obs.height_ft + 2 * obs.setback_ft
        # Treat each obstruction's halo box as its loss area, but cap
        # at usable_polygon_area so we never report negative.
        loss = halo_w * halo_h
        if loss <= 0:
            continue
        # Lightweight sanity check: if obstruction sits entirely outside
        # the section's bounding box, flag it (yaml input error).
        if (obs.x_ft + obs.width_ft < 0 or obs.x_ft > rs.width_ft
                or obs.y_ft + obs.height_ft < 0 or obs.y_ft > rs.height_ft):
            outside.append(f"{obs.kind} at ({obs.x_ft},{obs.y_ft})")
            continue
        obs_loss += loss

    usable = max(0.0, usable_polygon_area - obs_loss)
    demand = rs.module_count * MODULE_FOOTPRINT_SQFT
    return SectionLayoutResult(
        name=rs.name,
        shape=rs.shape,
        gross_area_sqft=gross,
        setback_loss_sqft=setback_loss,
        obstruction_loss_sqft=obs_loss,
        usable_area_sqft=usable,
        module_count=rs.module_count,
        module_demand_sqft=demand,
        fits=demand <= usable,
        obstructions_outside_usable_area=outside,
    )


def _rect_usable_after_setbacks(rs: RoofSection) -> tuple[float, float]:
    """Rectangle inset by per-edge setbacks → (area, loss_vs_gross)."""
    eave = rs.edge_setback_for("eave")
    ridge = rs.edge_setback_for("ridge")
    rake = rs.edge_setback_for("rake")
    usable_w = rs.width_ft - 2 * rake
    usable_h = rs.height_ft - eave - ridge
    if usable_w <= 0 or usable_h <= 0:
        return 0.0, rs.gross_area_sqft
    area = usable_w * usable_h
    return area, rs.gross_area_sqft - area


def _polygon_usable_after_setbacks(rs: RoofSection) -> tuple[float, float]:
    """K.2.7 — polygon usable area via Minkowski inset on the polygon's
    `vertices` list. Uses the largest setback across all edge types
    (eave / ridge / rake / valley / hip / apex) as the uniform inset
    distance — same conservative choice the triangle path makes.

    Per-edge polygon clipping (variable inset per edge) is K.2.8+.
    """
    from .polygon import polygon_inset_area

    A = rs.gross_area_sqft
    if A <= 0:
        return 0.0, 0.0
    # Use the max declared setback across all edge types as the inset.
    d = rs.default_setback_ft
    for es in rs.edge_setbacks:
        if es.setback_ft > d:
            d = es.setback_ft
    A_inset = polygon_inset_area(rs.vertices, d)
    return A_inset, A - A_inset


def _tri_usable_after_setbacks(rs: RoofSection) -> tuple[float, float]:
    """Triangle uniform inset by largest applicable setback → (area, loss).

    Inradius-shrink formula:
        A' = A × ((r - d) / r)²
        where r = 2A / P
    is exact for uniform inset. We use max(eave, hip) so the result is
    on the safe side when the user specifies different setbacks per
    edge — proper per-edge polygon clipping is K.2.7+ territory.
    """
    A = rs.gross_area_sqft
    base = rs.width_ft
    h = rs.height_ft
    apex_x = rs.apex_x_ratio * base
    left_len = math.hypot(apex_x, h)
    right_len = math.hypot(base - apex_x, h)
    P = base + left_len + right_len
    if P <= 0 or A <= 0:
        return 0.0, 0.0
    r = 2 * A / P
    d = max(rs.edge_setback_for("eave"), rs.edge_setback_for("hip"))
    r_new = r - d
    if r_new <= 0:
        return 0.0, A
    A_new = A * (r_new / r) ** 2
    return A_new, A - A_new
