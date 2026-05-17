"""K.9.1 — module placement algorithm.

Bridge between K.2.6c roof geometry + K.8.1 per-face module counts and the
PV-4 attachment plan's "draw each module rectangle at its real (x, y,
rotation)" requirement.

Inputs:
  * A single `RoofSection` (rect / tri / polygon) with optional
    `edge_setbacks[]` and `obstructions[]`
  * Module physical dimensions (length × width in inches, datasheet
    convention: length = long edge)
  * Target module count (typically `section.module_count` from K.8.1
    auto-distribute or designer-pinned yaml)

Output:
  list of `ModuleInstance` dataclasses, each carrying the
  roof-local placement (origin = eave-left corner; +x along eave,
  +y toward ridge) ready for PV-4 (K.9.3) to render rectangles.

Algorithm (K.9.1-v1):
  1. Compute the **usable polygon** = roof shape inset by edge setbacks.
  2. For each candidate orientation in {portrait, landscape}:
       a. Compute module footprint in roof-local units (ft).
       b. Lay an evenly-spaced grid covering the bounding box.
       c. Filter cells whose center is INSIDE the usable polygon
          AND whose footprint is OUTSIDE every obstruction halo.
  3. Pick the orientation that fits the MORE modules (tie-break:
     prefer landscape — fewer rows, cleaner aesthetics).
  4. Sort centers top-down (ridge to eave) then left-to-right within
     each row. Truncate to `target_count`.

Closed boundary cases (Pythonic fail-loud, not silent zero):
  * `target_count = 0` → empty list.
  * Section gross_area = 0 (degenerate yaml) → empty list.
  * Setbacks > face dimensions → empty list (no usable area).
  * Module larger than face → empty list (neither orientation fits).
  * Obstruction covers entire usable area → empty list.

Not in K.9.1 (deliberately):
  * Walking-row spacing differentiation (currently single gap value)
  * String / inverter MPPT grouping (K.10)
  * Module skew on tilted hip-roof faces beyond axis-aligned grid
  * Auto-shifting modules to balance whitespace
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from ..schema import RoofSection
from .polygon import bounding_box, offset_polygon, point_in_polygon


# ─── Public dataclass ──────────────────────────────────────────────────


@dataclass(frozen=True)
class ModuleInstance:
    """One placed module — what PV-4 renderer needs to draw a rectangle.

    Coordinates are roof-local: origin (0, 0) at eave-left corner,
    +x along eave (rake-to-rake direction), +y from eave toward ridge.
    `width_ft` × `height_ft` are post-rotation footprint dimensions:
      * Portrait: width = module short edge, height = module long edge
      * Landscape: width = module long edge, height = module short edge

    `rotation_deg` is informational (0 = portrait, 90 = landscape) for
    consumers that need to draw the long edge orientation differently
    (e.g., dimension callouts).

    `string_index` (K.10.1) — which inverter MPPT string this module
    belongs to (0-indexed). None when the project's K.10 string
    assignment hasn't run yet, or when n_strings=0 (degenerate yaml).
    """
    face_name: str
    x_ft: float            # bottom-left corner (NOT center)
    y_ft: float
    width_ft: float        # along-eave dimension after rotation
    height_ft: float       # eave-to-ridge dimension after rotation
    rotation_deg: float    # 0 = portrait, 90 = landscape
    string_index: Optional[int] = None    # K.10.1 string ID (0..n_strings-1)


# ─── Public API ────────────────────────────────────────────────────────


def place_modules(
    section: RoofSection,
    *,
    module_length_in: float = 67.80,
    module_width_in: float = 44.65,
    target_count: Optional[int] = None,
    inter_module_gap_in: float = 0.5,
    inter_row_gap_in: float = 0.5,
) -> list[ModuleInstance]:
    """Place up to `target_count` modules on the given roof section.

    Args:
        section: Pydantic RoofSection (rect / tri / polygon).
        module_length_in: long edge of the module (datasheet convention).
            Default 67.80" matches Talesun TP7G54M 415 — the 2026-05-17
            Frisco reference module.
        module_width_in: short edge of the module. Default 44.65".
        target_count: how many modules to place. None defaults to
            `section.module_count`; pass an int to override (e.g., when
            evaluating "how many WOULD fit" for capacity checks).
        inter_module_gap_in: rail gap between adjacent modules (along
            both axes). 0.5" is the IronRidge XR100 standard.
        inter_row_gap_in: extra gap between rows (perpendicular to eave).
            Some installs want walking paths every 2-3 rows; for K.9.1
            we use the same 0.5" everywhere. Reserved for K.10 polish.

    Returns:
        List of `ModuleInstance`. Length ≤ target_count. Empty list
        when the geometry can't fit any modules.
    """
    if target_count is None:
        target_count = section.module_count
    if target_count <= 0:
        return []

    # Convert to ft (roof-local units)
    long_ft = module_length_in / 12.0
    short_ft = module_width_in / 12.0
    gap_ft = inter_module_gap_in / 12.0
    row_gap_ft = inter_row_gap_in / 12.0

    # Inset polygon (apply edge setbacks once; the orientation loop
    # doesn't re-inset — same usable region for both orientations).
    usable = _usable_polygon(section)
    if not usable:
        return []

    # Try both orientations, pick whichever fits more modules.
    # When both fit ≥ target_count, prefer landscape (fewer rows, less
    # walking-path waste on chunky residential roofs).
    candidates: list[tuple[int, str, list[ModuleInstance]]] = []
    for orient_name, w_ft, h_ft in [
        ("landscape", long_ft, short_ft),
        ("portrait", short_ft, long_ft),
    ]:
        instances = _grid_place(
            section, usable, w_ft, h_ft,
            gap_ft, row_gap_ft, orient_name,
        )
        candidates.append((len(instances), orient_name, instances))

    # Sort: most modules first; tie-break by orientation order above
    # (landscape ahead of portrait by stable sort on insertion order).
    candidates.sort(key=lambda c: -c[0])
    _, _, best = candidates[0]

    return best[:target_count]


# ─── Helpers ───────────────────────────────────────────────────────────


def _usable_polygon(section: RoofSection) -> list[tuple[float, float]]:
    """Return CCW polygon vertices of the usable area (after setbacks).

    Rect: apply per-edge setbacks (eave / rake / ridge) if available,
    else the `default_setback_ft` uniformly. Edges:
      * y = 0           is the eave
      * y = height_ft   is the ridge (or apex for tri)
      * x = 0           is the left rake
      * x = width_ft    is the right rake

    Tri: convert to polygon vertices first, then uniform-inset
    (per-edge setbacks not supported for tri — too few edges to map
    meaningfully).

    Polygon: pull `vertices` directly from schema, apply uniform
    inset via `offset_polygon`.
    """
    if section.shape == "rect":
        eave = _setback_for(section, "eave")
        ridge = _setback_for(section, "ridge")
        rake = _setback_for(section, "rake")
        x0, y0 = rake, eave
        x1, y1 = section.width_ft - rake, section.height_ft - ridge
        if x1 <= x0 or y1 <= y0:
            return []
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

    if section.shape == "tri":
        apex_x = section.width_ft * section.apex_x_ratio
        verts = [(0.0, 0.0), (section.width_ft, 0.0), (apex_x, section.height_ft)]
        return offset_polygon(verts, section.default_setback_ft)

    if section.shape == "polygon":
        if not section.vertices:
            return []
        return offset_polygon(
            [(v[0], v[1]) for v in section.vertices],
            section.default_setback_ft,
        )

    return []


def _setback_for(section: RoofSection, edge_type: str) -> float:
    """Look up the explicit per-edge setback if present, else fall
    back to the section's default_setback_ft."""
    for es in section.edge_setbacks:
        if es.edge_type == edge_type:
            return es.setback_ft
    return section.default_setback_ft


def _grid_place(
    section: RoofSection,
    usable: list[tuple[float, float]],
    mod_w_ft: float, mod_h_ft: float,
    gap_w_ft: float, gap_h_ft: float,
    orient_name: str,
) -> list[ModuleInstance]:
    """Lay an axis-aligned grid over the usable polygon's bounding box
    and emit ModuleInstance for every cell whose CENTER falls inside
    the polygon AND whose FOOTPRINT is outside every obstruction halo.
    """
    if mod_w_ft <= 0 or mod_h_ft <= 0:
        return []
    xmin, ymin, xmax, ymax = bounding_box(usable)
    usable_w = xmax - xmin
    usable_h = ymax - ymin
    if mod_w_ft > usable_w or mod_h_ft > usable_h:
        return []

    # Center the grid in the usable box. If we put the first module at
    # xmin + mod_w/2, we'd hug the rake setback. Adding a small
    # margin (gap/2) gives visible breathing room at both edges and
    # reads cleaner on the PV-4 drawing.
    step_x = mod_w_ft + gap_w_ft
    step_y = mod_h_ft + gap_h_ft
    n_cols = int((usable_w + gap_w_ft) / step_x)
    n_rows = int((usable_h + gap_h_ft) / step_y)
    if n_cols < 1 or n_rows < 1:
        return []

    # Inset so the grid sits centered in any leftover width.
    block_w = n_cols * step_x - gap_w_ft
    block_h = n_rows * step_y - gap_h_ft
    x_origin = xmin + (usable_w - block_w) / 2
    y_origin = ymin + (usable_h - block_h) / 2

    rotation_deg = 0.0 if orient_name == "portrait" else 90.0
    instances: list[ModuleInstance] = []
    # Sort top-down: ridge-side rows first → the K.8.1 LRM "best
    # spots first" convention. Useful for truncation to target_count.
    for row in range(n_rows - 1, -1, -1):     # iterate ridge → eave
        y_center = y_origin + mod_h_ft / 2 + row * step_y
        for col in range(n_cols):
            x_center = x_origin + mod_w_ft / 2 + col * step_x
            if not point_in_polygon((x_center, y_center), usable):
                continue
            if _hits_obstruction(
                x_center, y_center, mod_w_ft, mod_h_ft, section.obstructions,
            ):
                continue
            instances.append(ModuleInstance(
                face_name=section.name,
                x_ft=x_center - mod_w_ft / 2,
                y_ft=y_center - mod_h_ft / 2,
                width_ft=mod_w_ft,
                height_ft=mod_h_ft,
                rotation_deg=rotation_deg,
            ))
    return instances


def _hits_obstruction(
    cx: float, cy: float, mod_w_ft: float, mod_h_ft: float,
    obstructions: Iterable,
) -> bool:
    """True iff the module's bounding box intersects any obstruction
    halo (obstruction expanded uniformly by `obs.setback_ft` on each
    side). Axis-aligned overlap test."""
    m_x0 = cx - mod_w_ft / 2
    m_y0 = cy - mod_h_ft / 2
    m_x1 = cx + mod_w_ft / 2
    m_y1 = cy + mod_h_ft / 2
    for obs in obstructions:
        h_x0 = obs.x_ft - obs.setback_ft
        h_y0 = obs.y_ft - obs.setback_ft
        h_x1 = obs.x_ft + obs.width_ft + obs.setback_ft
        h_y1 = obs.y_ft + obs.height_ft + obs.setback_ft
        # Overlapping rectangles: any axis where they DON'T overlap → no overlap
        if m_x1 > h_x0 and m_x0 < h_x1 and m_y1 > h_y0 and m_y0 < h_y1:
            return True
    return False
