"""Trace-aware EE-4 module geometry helpers.

When a reviewed/satellite ``site.ee4_trace`` is active, the permit site
plan should be driven by that traced roof outline.  Google Solar
``roof_sections`` are still useful for sizing, but their segment boxes can
be in a different coordinate frame from the satellite mask.  This module
keeps EE-4 drawing and linting on the same geometry by falling back to a
simple trace-constrained module grid when the normal section placements do
not fit inside the traced outline.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..calc.engine import CalculationResult
from ..calc.polygon import bounding_box, point_in_polygon
from ..calc.wire_routing import _face_local_to_site


Point = tuple[float, float]


@dataclass(frozen=True)
class EE4ModuleGeometry:
    label: str
    corners: list[Point]

    @property
    def center(self) -> Point:
        return (
            sum(p[0] for p in self.corners) / len(self.corners),
            sum(p[1] for p in self.corners) / len(self.corners),
        )


def ee4_module_geometries(result: CalculationResult) -> list[EE4ModuleGeometry]:
    """Return module rectangles in EE-4 site coordinates.

    Normal projects use the K.9 per-section placements.  If a traced roof
    outline is active and those placements fall outside that outline, derive
    a trace-constrained grid instead.  The derived grid is used only when it
    can place the full project module count; otherwise we preserve the
    original geometry so the lint checks continue to expose the mismatch.
    """
    native = _native_module_geometries(result)
    trace = result.inputs.site.ee4_trace
    outline = trace.roof_outline.vertices if trace.enabled and trace.roof_outline else []
    target = int(result.inputs.pv_array.modules)
    if not outline or target <= 0:
        return native
    if not _satellite_trace_outline(trace):
        return native

    if (
        len(native) == target
        and _all_inside_outline(native, outline)
        and _all_clear_fire_pathways(native, trace.fire_pathways)
    ):
        return native

    traced = _trace_grid_module_geometries(result, outline)
    if len(traced) == target:
        return traced
    return native


def _satellite_trace_outline(trace) -> bool:
    outline = getattr(trace, "roof_outline", None)
    name = str(getattr(outline, "name", "") or "").lower()
    return "satellite" in name and "outline" in name


def ee4_module_count(result: CalculationResult) -> int:
    return len(ee4_module_geometries(result))


def _native_module_geometries(
    result: CalculationResult,
) -> list[EE4ModuleGeometry]:
    modules: list[EE4ModuleGeometry] = []
    for section in result.inputs.site.roof_sections:
        for idx, module in enumerate(
            result.module_placements.get(section.name, []),
            1,
        ):
            corners_local = [
                (module.x_ft, module.y_ft),
                (module.x_ft + module.width_ft, module.y_ft),
                (module.x_ft + module.width_ft, module.y_ft + module.height_ft),
                (module.x_ft, module.y_ft + module.height_ft),
            ]
            corners = [
                _face_local_to_site(section, px, py)
                for px, py in corners_local
            ]
            points = [p for p in corners if p is not None]
            if len(points) == 4:
                modules.append(EE4ModuleGeometry(
                    label=f"{section.name}#{idx}",
                    corners=points,
                ))
    return modules


def _trace_grid_module_geometries(
    result: CalculationResult,
    outline: list[Point],
) -> list[EE4ModuleGeometry]:
    target = int(result.inputs.pv_array.modules)
    module = result.inputs.pv_array.module
    long_ft = float(module.length_in) / 12.0
    short_ft = float(module.width_in) / 12.0
    gap_ft = 0.5 / 12.0
    options = [
        _pack_trace_grid(result, outline, long_ft, short_ft, gap_ft),
        _pack_trace_grid(result, outline, short_ft, long_ft, gap_ft),
    ]
    options.sort(key=lambda items: len(items), reverse=True)
    return options[0][:target] if options else []


def _pack_trace_grid(
    result: CalculationResult,
    outline: list[Point],
    width_ft: float,
    height_ft: float,
    gap_ft: float,
) -> list[EE4ModuleGeometry]:
    if width_ft <= 0 or height_ft <= 0:
        return []
    x0, y0, x1, y1 = bounding_box(outline)
    step_x = width_ft + gap_ft
    step_y = height_ft + gap_ft
    modules: list[EE4ModuleGeometry] = []
    idx = 1
    y = y1 - height_ft
    while y >= y0 - 1e-9:
        x = x0
        while x <= x1 - width_ft + 1e-9:
            corners = [
                (x, y),
                (x + width_ft, y),
                (x + width_ft, y + height_ft),
                (x, y + height_ft),
            ]
            candidate = EE4ModuleGeometry(
                label=f"Trace roof#{idx}",
                corners=corners,
            )
            if (
                _all_corners_inside(corners, outline)
                and _all_clear_fire_pathways(
                    [candidate],
                    result.inputs.site.ee4_trace.fire_pathways,
                )
            ):
                modules.append(candidate)
                idx += 1
            x += step_x
        y -= step_y
    return modules


def _all_inside_outline(
    modules: list[EE4ModuleGeometry],
    outline: list[Point],
) -> bool:
    return all(_all_corners_inside(module.corners, outline) for module in modules)


def _all_corners_inside(corners: list[Point], outline: list[Point]) -> bool:
    return all(_point_in_or_on_polygon(point, outline) for point in corners)


def _all_clear_fire_pathways(modules, fire_pathways) -> bool:
    if not fire_pathways:
        return True
    for module in modules:
        for fire in fire_pathways:
            if _polygons_touch_or_overlap(module.corners, fire.vertices):
                return False
    return True


def _polygons_touch_or_overlap(a: list[Point], b: list[Point]) -> bool:
    return (
        any(_point_in_or_on_polygon(point, b) for point in a)
        or any(_point_in_or_on_polygon(point, a) for point in b)
        or _edges_intersect(a, b)
    )


def _edges_intersect(a: list[Point], b: list[Point]) -> bool:
    for idx, a0 in enumerate(a):
        a1 = a[(idx + 1) % len(a)]
        for jdx, b0 in enumerate(b):
            b1 = b[(jdx + 1) % len(b)]
            if _segments_intersect(a0, a1, b0, b1):
                return True
    return False


def _segments_intersect(a0: Point, a1: Point, b0: Point, b1: Point) -> bool:
    def orient(p: Point, q: Point, r: Point) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1 = orient(a0, a1, b0)
    o2 = orient(a0, a1, b1)
    o3 = orient(b0, b1, a0)
    o4 = orient(b0, b1, a1)
    if o1 == o2 == o3 == o4 == 0:
        return (
            _point_on_segment(a0, b0, a1, tol=1e-6)
            or _point_on_segment(a0, b1, a1, tol=1e-6)
            or _point_on_segment(b0, a0, b1, tol=1e-6)
            or _point_on_segment(b0, a1, b1, tol=1e-6)
        )
    return (o1 * o2 <= 0) and (o3 * o4 <= 0)


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
