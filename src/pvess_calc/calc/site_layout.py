"""Stage B — auto-derive `site_anchor` for RoofSections without
explicit anchors.

K.11 schema gates real-coord site-plan rendering on each RoofSection
having `site_anchor_x_ft / _y_ft / _azimuth_deg` set explicitly. This
module fills those in for legacy yamls (Austin, Phoenix, etc.) using
a per-orientation auto-layout heuristic so the EE-4 page can show
multi-face geometry without forcing every yaml to declare anchors.

Convention (matches K.11 hand-edited yaml):
    - South face: anchor SW corner, eave east, ridge north  (az=0)
    - East  face: anchor SE corner, eave north, ridge west  (az=90)
    - North face: anchor NE corner, eave west, ridge south  (az=180)
    - West  face: anchor NW corner, eave south, ridge east  (az=270)

When multiple faces share a wall they pack head-to-tail with a small
gap (`gap_ft`, default 1 ft). Faces may overflow past the wall ends
— a 38 ft section on a 35 ft wall extends 3 ft past the house corner,
which is the right visual cue that the face data is bigger than its
supporting wall (designer should review before AHJ submittal).

Sections with `site_anchor_x_ft` already set (explicit yaml input)
are pass-through — they keep their declared values and are NOT
included in the returned dict.
"""

from __future__ import annotations

from ..schema import RoofSection, Site


def _classify_orientation(azimuth_deg: float) -> str:
    """Bucket a roof azimuth into one of 4 compass quadrants.

    azimuth_deg follows residential PV convention: 0 = north,
    180 = south (the face POINTS south, water drains south).
    Quadrant boundaries straddle the cardinal points symmetrically.
    """
    az = azimuth_deg % 360.0
    if 45 <= az < 135:
        return "east"
    if 135 <= az < 225:
        return "south"
    if 225 <= az < 315:
        return "west"
    return "north"


_ORIENT_ANCHOR_AZ: dict[str, float] = {
    "south": 0.0,
    "east":  90.0,
    "north": 180.0,
    "west":  270.0,
}


def house_bbox(site: Site) -> tuple[float, float, float, float]:
    """Return `(x_min, y_min, x_max, y_max)` of the house footprint.

    Uses `house_outline_vertices` when populated (real L/T polygons),
    otherwise the centred `house_width_ft × house_depth_ft` rectangle
    inside the lot.
    """
    if site.house_outline_vertices:
        xs = [v[0] for v in site.house_outline_vertices]
        ys = [v[1] for v in site.house_outline_vertices]
        return (min(xs), min(ys), max(xs), max(ys))
    cx = site.lot_width_ft / 2
    cy = site.lot_depth_ft / 2
    hw = site.house_width_ft
    hd = site.house_depth_ft
    return (cx - hw / 2, cy - hd / 2, cx + hw / 2, cy + hd / 2)


def auto_anchor_sections(
    site: Site,
    *,
    gap_ft: float = 1.0,
) -> dict[str, tuple[float, float, float]]:
    """Compute auto-anchor `(x, y, azimuth)` for each RoofSection
    that doesn't have explicit anchors.

    Determinism: same input → same output. Iterates `roof_sections`
    in their declared order; within a wall, faces stack in that
    same order (no internal re-sort).

    **K.13.1 P2 — corner-inset packing.** Each cursor's starting
    corner is inset by the perpendicular orientation's max H_ft so
    adjacent walls don't double-claim the same corner region. For
    a house with both south- and west-facing roofs, the south
    cursor starts at `x_min + max_height(west)` so the SW corner
    is left to the west faces' eastward inset. This eliminates
    the visible corner overlap on Phoenix-style 2-face yamls.

    When the inset would push the cursor past the wall's other end
    (i.e., the orthogonal orientation claims the entire wall), the
    cursor falls back to `x_min` (no inset) and faces overlap as
    they did pre-K.13.1 — the data is over-packed and the
    overlap is the right visual signal for the designer.

    Args:
        site: full Site object (reads roof_sections, lot/house dims,
            house_outline_vertices).
        gap_ft: spacing between adjacent same-wall faces.

    Returns:
        dict {section.name → (anchor_x_ft, anchor_y_ft, anchor_azimuth_deg)}.
        Only faces that received an auto-anchor are included; faces
        with explicit yaml anchors are absent.
    """
    x_min, y_min, x_max, y_max = house_bbox(site)
    house_w = x_max - x_min
    house_h = y_max - y_min

    # K.13.1 P2 — compute max height per orientation across only the
    # sections we're about to auto-anchor (explicit-anchor sections
    # are user-claimed and don't reserve corner space).
    max_h: dict[str, float] = {"south": 0.0, "east": 0.0,
                               "north": 0.0, "west": 0.0}
    for section in site.roof_sections:
        if section.site_anchor_x_ft is not None:
            continue
        orient = _classify_orientation(section.azimuth_deg)
        max_h[orient] = max(max_h[orient], section.height_ft)

    # Apply inset only if it doesn't consume more than half the wall —
    # else fall back to flush-corner placement (overlap is the right
    # visual signal that the roof data is over-packed for the house).
    def _inset_or_zero(perp_h: float, wall_len: float) -> float:
        return perp_h if perp_h < wall_len * 0.5 else 0.0

    cursors = {
        # South wall runs along x; west's eastward extent claims SW
        # corner so south cursor starts past it.
        "south": x_min + _inset_or_zero(max_h["west"], house_w),
        # East wall runs along y; south's northward extent claims SE
        # corner so east cursor starts past it.
        "east":  y_min + _inset_or_zero(max_h["south"], house_h),
        # North wall runs along x (descending); east's westward
        # extent claims NE corner.
        "north": x_max - _inset_or_zero(max_h["east"], house_w),
        # West wall runs along y (descending); north's southward
        # extent claims NW corner.
        "west":  y_max - _inset_or_zero(max_h["north"], house_h),
    }

    out: dict[str, tuple[float, float, float]] = {}
    for section in site.roof_sections:
        if (section.site_anchor_x_ft is not None
                and section.site_anchor_y_ft is not None):
            continue
        orient = _classify_orientation(section.azimuth_deg)
        az = _ORIENT_ANCHOR_AZ[orient]
        w = section.width_ft

        if orient == "south":
            ax, ay = cursors["south"], y_min
            cursors["south"] += w + gap_ft
        elif orient == "east":
            ax, ay = x_max, cursors["east"]
            cursors["east"] += w + gap_ft
        elif orient == "north":
            ax, ay = cursors["north"], y_max
            cursors["north"] -= w + gap_ft
        else:
            ax, ay = x_min, cursors["west"]
            cursors["west"] -= w + gap_ft

        out[section.name] = (ax, ay, az)

    return out


def apply_auto_anchors(
    site: Site,
    anchors: dict[str, tuple[float, float, float]],
) -> Site:
    """Return a deep-copy of `site` with `anchors` written into each
    matching RoofSection's `site_anchor_*` fields.

    Sections with explicit anchors (or absent from the `anchors` dict)
    are untouched. Original `site` is never mutated.
    """
    if not anchors:
        return site
    patched = site.model_copy(deep=True)
    for section in patched.roof_sections:
        anchor = anchors.get(section.name)
        if anchor is None:
            continue
        if section.site_anchor_x_ft is None:
            section.site_anchor_x_ft = anchor[0]
            section.site_anchor_y_ft = anchor[1]
            section.site_anchor_azimuth_deg = anchor[2]
    return patched
