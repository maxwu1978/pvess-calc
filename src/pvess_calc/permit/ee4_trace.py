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
from ..calc.polygon import polygon_area
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

    fire_pathways: list[EE4TracePolygon] = []
    module_pts = _module_site_points(result)
    if module_pts:
        fire_pathways.append(EE4TracePolygon(
            name="Module field fire pathway candidate",
            vertices=_bbox_polygon(_padded_bbox(module_pts, pad_ft=3.0)),
        ))

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


def _module_site_points(result: CalculationResult) -> list[Point]:
    pts: list[Point] = []
    for section in result.inputs.site.roof_sections:
        for module in result.module_placements.get(section.name, []):
            corners = [
                (module.x_ft, module.y_ft),
                (module.x_ft + module.width_ft, module.y_ft),
                (module.x_ft + module.width_ft, module.y_ft + module.height_ft),
                (module.x_ft, module.y_ft + module.height_ft),
            ]
            for px, py in corners:
                pt = _face_local_to_site(section, px, py)
                if pt is not None:
                    pts.append(pt)
    return pts


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
