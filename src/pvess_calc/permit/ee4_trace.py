"""Stage 9.2 — generate editable EE-4 trace skeletons.

The skeleton is not intended to be a final permit drawing. It gives a
designer a valid `site.ee4_trace` block with roof outline, per-face
facets, rough roof lines, fire-pathway candidate, and obstruction
symbols so the remaining work is point adjustment rather than writing
YAML from scratch.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import yaml

from ..calc.engine import CalculationResult
from ..calc.polygon import polygon_area, point_in_polygon
from ..calc.wire_routing import _face_local_to_site
from ..schema import (
    EE4Trace,
    EE4TraceLine,
    EE4TracePolygon,
    EE4TraceSymbol,
    RoofSection,
)


Point = tuple[float, float]


def build_ee4_trace_skeleton(result: CalculationResult) -> EE4Trace:
    """Build a valid first-pass `EE4Trace` from calculated geometry."""
    site = result.inputs.site
    section_polys: list[tuple[str, list[Point]]] = []
    all_pts: list[Point] = []
    for section in site.roof_sections:
        pts = _section_site_polygon(section)
        if len(pts) < 3:
            continue
        section_polys.append((section.name, pts))
        all_pts.extend(pts)

    if site.house_outline_vertices:
        outline_pts = list(site.house_outline_vertices)
    elif all_pts:
        outline_pts = _bbox_polygon(_padded_bbox(all_pts, pad_ft=2.0))
    else:
        outline_pts = _bbox_polygon((
            0.0, 0.0, site.house_width_ft, site.house_depth_ft,
        ))

    roof_facets = [
        EE4TracePolygon(name=name, vertices=_ensure_ccw(pts))
        for name, pts in section_polys
    ]
    roof_lines: list[EE4TraceLine] = []
    for _name, pts in section_polys:
        roof_lines.extend(_facet_center_lines(pts))

    fire_pathways = _fire_pathway_candidates(outline_pts)

    symbols = _trace_symbols_from_obstructions(site.roof_sections)

    return EE4Trace(
        enabled=True,
        roof_outline=EE4TracePolygon(
            name="Trace skeleton roof outline",
            vertices=_ensure_ccw(outline_pts),
        ),
        roof_facets=roof_facets,
        roof_lines=roof_lines,
        fire_pathways=fire_pathways,
        symbols=symbols,
    )


def complete_ee4_trace_for_review(trace: EE4Trace) -> EE4Trace:
    """Fill review-critical trace layers when a source only has outline.

    Satellite mask candidates intentionally start as a roof outline only.
    Step 2, however, needs to produce a usable topology draft for the
    downstream EE-4 pages.  This helper preserves the reviewed outline and
    adds conservative linework/fire-pathway candidates so the drawing can be
    checked and refined instead of falling back to coarse roof sections.
    """
    if trace.roof_outline is None:
        return trace
    outline = list(trace.roof_outline.vertices)
    updates = {}
    if not trace.roof_lines and not trace.roof_facets:
        updates["roof_lines"] = _facet_center_lines(outline)
    if not trace.fire_pathways:
        updates["fire_pathways"] = _fire_pathway_candidates(outline)
    if not updates:
        return trace
    return trace.model_copy(update=updates)


def ee4_trace_yaml(trace: EE4Trace) -> str:
    """Return a paste-ready YAML snippet under `site.ee4_trace`."""
    payload = {
        "site": {
            "ee4_trace": trace.model_dump(
                mode="json",
                exclude_none=True,
            )
        }
    }
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=False)


def write_ee4_trace_skeleton(
    result: CalculationResult,
    output_path: Path,
) -> Path:
    """Write `site.ee4_trace` skeleton YAML and return the path."""
    trace = build_ee4_trace_skeleton(result)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(ee4_trace_yaml(trace), encoding="utf-8")
    return output_path


def _section_site_polygon(section: RoofSection) -> list[Point]:
    if section.site_anchor_x_ft is None:
        return []
    if section.shape == "polygon":
        local = list(section.vertices)
    elif section.shape == "tri":
        local = [
            (0.0, 0.0),
            (section.width_ft, 0.0),
            (section.width_ft * section.apex_x_ratio, section.height_ft),
        ]
    else:
        local = [
            (0.0, 0.0),
            (section.width_ft, 0.0),
            (section.width_ft, section.height_ft),
            (0.0, section.height_ft),
        ]
    pts = [_face_local_to_site(section, px, py) for px, py in local]
    return [p for p in pts if p is not None]


def _facet_center_lines(points: list[Point]) -> list[EE4TraceLine]:
    if len(points) < 3:
        return []
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    return [
        EE4TraceLine(
            kind="hip",
            points=[_clean_point((cx, cy)), _clean_point(p)],
        )
        for p in points
    ]


def _trace_symbols_from_obstructions(
    sections: Iterable[RoofSection],
) -> list[EE4TraceSymbol]:
    symbols: list[EE4TraceSymbol] = []
    for section in sections:
        for obs in section.obstructions:
            pt = _face_local_to_site(
                section,
                obs.x_ft + obs.width_ft / 2,
                obs.y_ft + obs.height_ft / 2,
            )
            if pt is None:
                continue
            symbols.append(EE4TraceSymbol(
                kind=_trace_symbol_kind(obs.kind),
                x_ft=_clean_number(pt[0]),
                y_ft=_clean_number(pt[1]),
            ))
    return symbols


def _fire_pathway_candidates(outline_pts: list[Point]) -> list[EE4TracePolygon]:
    """Create non-overlapping perimeter strip candidates for trace review.

    Earlier skeletons wrapped the module field in one large bbox, which
    was useful as a visual reminder but made any accepted draft fail the
    R7 module-vs-fire-pathway constraint. These candidates stay along
    the roof perimeter, matching how the final permit hatch is reviewed.
    """
    if len(outline_pts) < 3:
        return []
    x0, y0, x1, y1 = _padded_bbox(outline_pts, pad_ft=0.0)
    width = min(1.0, max((x1 - x0) / 6.0, 0.1), max((y1 - y0) / 6.0, 0.1))
    if x1 - x0 <= width * 2 or y1 - y0 <= width * 2:
        return []
    candidates = [
        EE4TracePolygon(
            name="North roof-edge fire pathway candidate",
            vertices=_bbox_polygon((x0, y1 - width, x1, y1)),
        ),
        EE4TracePolygon(
            name="East roof-edge fire pathway candidate",
            vertices=_bbox_polygon((x1 - width, y0, x1, y1)),
        ),
    ]
    if all(
        _all_vertices_inside(poly.vertices, outline_pts)
        for poly in candidates
    ):
        return candidates
    fallback = _interior_fire_pathway_candidates(outline_pts, width)
    return fallback or candidates


def _interior_fire_pathway_candidates(
    outline_pts: list[Point],
    width: float,
) -> list[EE4TracePolygon]:
    x0, y0, x1, y1 = _padded_bbox(outline_pts, pad_ft=0.0)
    bw = max(x1 - x0, 0.0)
    bh = max(y1 - y0, 0.0)
    if bw <= width * 2 or bh <= width * 2:
        return []

    north = _find_inside_rect(
        outline_pts,
        rect_w=min(max(bw * 0.36, width * 4), bw * 0.72),
        rect_h=width,
        prefer="north",
    )
    east = _find_inside_rect(
        outline_pts,
        rect_w=width,
        rect_h=min(max(bh * 0.36, width * 4), bh * 0.72),
        prefer="east",
    )
    result: list[EE4TracePolygon] = []
    if north is not None:
        result.append(EE4TracePolygon(
            name="North interior fire pathway candidate",
            vertices=_bbox_polygon(north),
        ))
    if east is not None and east != north:
        result.append(EE4TracePolygon(
            name="East interior fire pathway candidate",
            vertices=_bbox_polygon(east),
        ))
    return result


def _find_inside_rect(
    outline_pts: list[Point],
    *,
    rect_w: float,
    rect_h: float,
    prefer: str,
) -> tuple[float, float, float, float] | None:
    x0, y0, x1, y1 = _padded_bbox(outline_pts, pad_ft=0.0)
    step = max(min(rect_w, rect_h) / 2.0, 0.25)
    x_values = _scan_values(x0, x1 - rect_w, step, reverse=(prefer == "east"))
    y_values = _scan_values(y0, y1 - rect_h, step, reverse=(prefer == "north"))
    for y in y_values:
        for x in x_values:
            bbox = (x, y, x + rect_w, y + rect_h)
            if _all_vertices_inside(_bbox_polygon(bbox), outline_pts):
                return bbox
    return None


def _scan_values(
    start: float,
    stop: float,
    step: float,
    *,
    reverse: bool,
) -> list[float]:
    if stop < start:
        return []
    values: list[float] = []
    value = start
    while value <= stop + 1e-9:
        values.append(round(value, 3))
        value += step
    return list(reversed(values)) if reverse else values


def _all_vertices_inside(points: list[Point], outline_pts: list[Point]) -> bool:
    return all(_point_in_or_on_polygon(point, outline_pts) for point in points)


def _point_in_or_on_polygon(
    point: Point,
    vertices: list[Point],
    *,
    tol: float = 1e-6,
) -> bool:
    if point_in_polygon(point, vertices):
        return True
    return any(
        _point_on_segment(point, vertices[idx], vertices[(idx + 1) % len(vertices)], tol=tol)
        for idx in range(len(vertices))
    )


def _point_on_segment(
    point: Point,
    a: Point,
    b: Point,
    *,
    tol: float,
) -> bool:
    px, py = point
    ax, ay = a
    bx, by = b
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    if abs(cross) > tol:
        return False
    dot = (px - ax) * (px - bx) + (py - ay) * (py - by)
    return dot <= tol


def _trace_symbol_kind(kind: str) -> str:
    if kind == "chimney":
        return "chimney"
    if kind == "satellite_dish":
        return "satellite"
    if kind == "hvac_unit":
        return "ac"
    if kind == "vent_pipe":
        return "plumbing"
    return "roof_vent"


def _padded_bbox(
    points: list[Point],
    *,
    pad_ft: float,
) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (
        min(xs) - pad_ft,
        min(ys) - pad_ft,
        max(xs) + pad_ft,
        max(ys) + pad_ft,
    )


def _bbox_polygon(
    bbox: tuple[float, float, float, float],
) -> list[Point]:
    x0, y0, x1, y1 = bbox
    return _clean_points([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def _ensure_ccw(points: list[Point]) -> list[Point]:
    pts = _clean_points(points)
    if polygon_area(pts) < 0:
        return list(reversed(pts))
    return pts


def _clean_points(points: list[Point]) -> list[Point]:
    return [_clean_point(p) for p in points]


def _clean_point(point: Point) -> Point:
    return (_clean_number(point[0]), _clean_number(point[1]))


def _clean_number(value: float) -> float:
    rounded = round(float(value), 3)
    return 0.0 if abs(rounded) < 0.0005 else rounded
