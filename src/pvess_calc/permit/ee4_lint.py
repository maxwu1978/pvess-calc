"""Stage 9.4 — lightweight visual lint for EE-4 previews."""
from __future__ import annotations

from dataclasses import dataclass

from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics

from ..calc.engine import CalculationResult
from ..calc.polygon import point_in_polygon, polygon_area
from ..calc.wire_routing import _face_local_to_site
from .site_plan import (
    _ee4_36_fire_offset_label_position,
    _ee4_drawing_bounds,
    _ee4_equipment_items,
    _ee4_equipment_label_layout,
    _ee4_equipment_leader_label,
    _ee4_trace_active,
)


@dataclass(frozen=True)
class EE4LintResult:
    name: str
    status: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status in ("PASS", "WARN")


def lint_ee4_preview(result: CalculationResult) -> list[EE4LintResult]:
    """Run visual-risk checks that can be evaluated without OCR."""
    return [
        _lint_module_rectangles_no_overlap(result),
        _lint_module_rectangles_clear_fire_pathway(result),
        _lint_modules_inside_trace_roof(result),
        _lint_modules_clear_fire_pathway(result),
        _lint_fire_pathway_inside_roof(result),
        _lint_equipment_leaders_in_frame(result),
        _lint_optimizer_callout_in_frame(result),
        _lint_fire_offset_labels_in_frame(result),
        _lint_drawing_scale_readable(result),
    ]


def _lint_module_rectangles_no_overlap(
    result: CalculationResult,
) -> EE4LintResult:
    name = "ee4_module_rectangles_no_overlap"
    modules = _module_polygons(result)
    overlaps: list[str] = []
    for idx, (label_a, poly_a) in enumerate(modules):
        for label_b, poly_b in modules[idx + 1:]:
            area = _convex_intersection_area(poly_a, poly_b)
            if area > 0.05:
                overlaps.append(f"{label_a}<>{label_b} ({area:.1f} sqft)")
    if overlaps:
        return EE4LintResult(
            name, "WARN",
            f"{len(overlaps)} module rectangle overlap(s): "
            + "; ".join(overlaps[:5]),
        )
    return EE4LintResult(
        name, "PASS",
        f"{len(modules)} module rectangle(s) have no area overlap",
    )


def _lint_module_rectangles_clear_fire_pathway(
    result: CalculationResult,
) -> EE4LintResult:
    name = "ee4_module_rectangles_clear_fire_pathway"
    trace = result.inputs.site.ee4_trace
    if not _ee4_trace_active(result.inputs.site) or not trace.fire_pathways:
        return EE4LintResult(name, "PASS", "no traced fire pathway active")

    hits: list[str] = []
    for label, module_poly in _module_polygons(result):
        if any(_polygons_overlap(module_poly, fire.vertices)
               for fire in trace.fire_pathways):
            hits.append(label)
    if hits:
        return EE4LintResult(
            name, "WARN",
            f"{len(hits)} module rectangle(s) overlap fire pathway: "
            + ", ".join(hits[:8]),
        )
    return EE4LintResult(
        name, "PASS",
        "module rectangles are clear of traced fire pathway polygons",
    )


def _lint_modules_inside_trace_roof(
    result: CalculationResult,
) -> EE4LintResult:
    name = "ee4_modules_inside_trace_roof"
    trace = result.inputs.site.ee4_trace
    if not _ee4_trace_active(result.inputs.site) or trace.roof_outline is None:
        return EE4LintResult(name, "PASS", "trace roof outline not active")

    outside = [
        label for label, poly in _module_polygons(result)
        if any(
            not _point_in_or_on_polygon(corner, trace.roof_outline.vertices)
            for corner in poly
        )
    ]
    if outside:
        return EE4LintResult(
            name, "WARN",
            f"{len(outside)} module rectangle(s) outside traced roof outline: "
            + ", ".join(outside[:6]),
        )
    return EE4LintResult(
        name, "PASS",
        "all module rectangles are inside traced roof outline",
    )


def _lint_modules_clear_fire_pathway(
    result: CalculationResult,
) -> EE4LintResult:
    name = "ee4_modules_clear_fire_pathway"
    trace = result.inputs.site.ee4_trace
    if not _ee4_trace_active(result.inputs.site) or not trace.fire_pathways:
        return EE4LintResult(name, "PASS", "no traced fire pathway active")

    hits: list[str] = []
    for label, center in _module_centers(result):
        if any(point_in_polygon(center, poly.vertices)
               for poly in trace.fire_pathways):
            hits.append(label)
    if hits:
        return EE4LintResult(
            name, "WARN",
            f"{len(hits)} module center(s) fall inside fire pathway: "
            + ", ".join(hits[:6]),
        )
    return EE4LintResult(
        name, "PASS",
        "module centers are clear of traced fire pathway polygons",
    )


def _lint_fire_pathway_inside_roof(
    result: CalculationResult,
) -> EE4LintResult:
    name = "ee4_fire_pathway_inside_roof"
    trace = result.inputs.site.ee4_trace
    if (
        not _ee4_trace_active(result.inputs.site)
        or trace.roof_outline is None
        or not trace.fire_pathways
    ):
        return EE4LintResult(name, "PASS", "trace roof/fire pathway not active")

    outside = 0
    total = 0
    for poly in trace.fire_pathways:
        for vertex in poly.vertices:
            total += 1
            if not _point_in_or_on_polygon(vertex, trace.roof_outline.vertices):
                outside += 1
    if outside:
        return EE4LintResult(
            name, "WARN",
            f"{outside}/{total} fire-pathway vertices are outside traced roof",
        )
    return EE4LintResult(
        name, "PASS",
        "fire-pathway vertices are inside traced roof outline",
    )


def _lint_equipment_leaders_in_frame(
    result: CalculationResult,
) -> EE4LintResult:
    name = "ee4_equipment_leaders_in_frame"
    layout = _layout()
    items = _ee4_equipment_items(result.inputs.site.equipment_locations)
    if not items:
        return EE4LintResult(name, "PASS", "no equipment leader labels")

    frame = layout["frame"]
    label_x, label_y, row_h = _ee4_equipment_label_layout(
        layout["drawing_x"],
        layout["drawing_y"],
        layout["drawing_w"],
        layout["drawing_h"],
    )
    bboxes = []
    items = sorted(items, key=lambda it: -it[2])
    for idx, (label, _fx, _fy, mark) in enumerate(items):
        ty = label_y + (len(items) - 1 - idx) * row_h
        label_text = f"{mark} {_ee4_equipment_leader_label(label)}"
        bboxes.append(_text_bbox(label_x, ty, label_text, 7.0))
    bboxes.append(_text_bbox(label_x, label_y - 0.18 * inch,
                            "FIRE DEPARTMENT ACCESS", 7.0))

    return _bbox_check(
        name,
        bboxes,
        frame,
        pass_detail=f"{len(items)} equipment leader label(s) fit in frame",
        warn_detail="equipment leader label text is too close to / outside frame",
    )


def _lint_optimizer_callout_in_frame(
    result: CalculationResult,
) -> EE4LintResult:
    name = "ee4_optimizer_callout_in_frame"
    optimizer = result.inputs.optimizer
    if not optimizer.brand:
        return EE4LintResult(name, "PASS", "no optimizer callout")

    layout = _layout()
    end_x = layout["drawing_x"] + layout["drawing_w"] - 1.68 * inch
    end_y = layout["drawing_y"] + layout["drawing_h"] - 0.45 * inch
    n_opt = optimizer.effective_count(
        result.inputs.pv_array.modules,
        result.inputs.pv_array.strings,
    )
    ratio = max(1, result.inputs.pv_array.modules // n_opt) if n_opt else 1
    bboxes = [
        _text_bbox(end_x, end_y + 0.02 * inch,
                   "(N) PV MODULE EQUIPPED W/ (1)", 7.0),
        _text_bbox(end_x, end_y - 0.10 * inch,
                   f"OPTIMIZER PER ({ratio}) MODULES", 7.0),
    ]
    return _bbox_check(
        name,
        bboxes,
        layout["frame"],
        pass_detail="optimizer callout fits in frame",
        warn_detail="optimizer callout text is too close to / outside frame",
    )


def _lint_fire_offset_labels_in_frame(
    result: CalculationResult,
) -> EE4LintResult:
    name = "ee4_fire_offset_labels_in_frame"
    transform = _drawing_transform(result)
    if transform is None:
        return EE4LintResult(name, "PASS", "no EE-4 drawing bounds")
    layout, to_pt = transform

    bboxes = []
    label36_x, label36_y = _ee4_36_fire_offset_label_position(
        layout["drawing_x"],
        layout["drawing_y"],
        layout["drawing_w"],
        layout["drawing_h"],
    )
    bboxes.append(_text_bbox(label36_x, label36_y, '36" FIRE OFFSET', 7.0))

    label_section = next(
        (s for s in result.inputs.site.roof_sections
         if s.site_anchor_x_ft is not None),
        None,
    )
    if label_section is not None:
        start = to_pt((
            label_section.site_anchor_x_ft + label_section.width_ft * 0.55,
            label_section.site_anchor_y_ft + label_section.height_ft + 0.7,
        ))
        end = (start[0] + 0.55 * inch, start[1] + 0.62 * inch)
        bboxes.append(_text_bbox(
            end[0] + 0.02 * inch,
            end[1] - 2,
            '18" FIRE OFFSET (NEC 690.12)',
            7.0,
        ))

    return _bbox_check(
        name,
        bboxes,
        layout["frame"],
        pass_detail="fire offset labels fit in frame",
        warn_detail="fire offset label text is too close to / outside frame",
    )


def _lint_drawing_scale_readable(
    result: CalculationResult,
) -> EE4LintResult:
    name = "ee4_drawing_scale_readable"
    transform = _drawing_transform(result)
    if transform is None:
        return EE4LintResult(name, "WARN", "no EE-4 drawing bounds")
    layout, _to_pt = transform
    bounds = _ee4_drawing_bounds(result)
    assert bounds is not None
    min_x, min_y, max_x, max_y = bounds
    bw = max(max_x - min_x, 1.0)
    bh = max(max_y - min_y, 1.0)
    pad_ft = max(bw, bh) * 0.08
    scale = min(
        layout["drawing_w"] / (bw + 2 * pad_ft),
        layout["drawing_h"] / (bh + 2 * pad_ft),
    )
    if scale < 3.0:
        return EE4LintResult(
            name, "WARN",
            f"scale is {scale:.2f} pt/ft; roof/equipment may be too dense",
        )
    return EE4LintResult(
        name, "PASS",
        f"scale is {scale:.2f} pt/ft",
    )


def _module_centers(
    result: CalculationResult,
) -> list[tuple[str, tuple[float, float]]]:
    centers: list[tuple[str, tuple[float, float]]] = []
    for section in result.inputs.site.roof_sections:
        for idx, module in enumerate(
            result.module_placements.get(section.name, []),
            1,
        ):
            center = _face_local_to_site(
                section,
                module.x_ft + module.width_ft / 2,
                module.y_ft + module.height_ft / 2,
            )
            if center is not None:
                centers.append((f"{section.name}#{idx}", center))
    return centers


def _module_polygons(
    result: CalculationResult,
) -> list[tuple[str, list[tuple[float, float]]]]:
    modules: list[tuple[str, list[tuple[float, float]]]] = []
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
            corners = [p for p in corners if p is not None]
            if len(corners) == 4:
                modules.append((f"{section.name}#{idx}", corners))
    return modules


def _point_in_or_on_polygon(
    point: tuple[float, float],
    vertices: list[tuple[float, float]],
    *,
    tol: float = 1e-6,
) -> bool:
    if point_in_polygon(point, vertices):
        return True
    return any(
        _point_on_segment(point, vertices[idx], vertices[(idx + 1) % len(vertices)],
                          tol=tol)
        for idx in range(len(vertices))
    )


def _point_on_segment(
    point: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
    *,
    tol: float,
) -> bool:
    px, py = point
    ax, ay = a
    bx, by = b
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    if abs(cross) > tol:
        return False
    dot = (px - ax) * (bx - ax) + (py - ay) * (by - ay)
    if dot < -tol:
        return False
    length_sq = (bx - ax) ** 2 + (by - ay) ** 2
    return dot <= length_sq + tol


def _convex_intersection_area(
    subject: list[tuple[float, float]],
    clip: list[tuple[float, float]],
) -> float:
    """Return area of intersection for two CCW convex polygons."""
    if len(subject) < 3 or len(clip) < 3:
        return 0.0
    if not _bbox_overlaps(subject, clip):
        return 0.0
    output = list(subject)
    for idx in range(len(clip)):
        a = clip[idx]
        b = clip[(idx + 1) % len(clip)]
        if not output:
            return 0.0
        input_pts = output
        output = []
        prev = input_pts[-1]
        prev_inside = _is_left_of_edge(prev, a, b)
        for cur in input_pts:
            cur_inside = _is_left_of_edge(cur, a, b)
            if cur_inside:
                if not prev_inside:
                    inter = _line_intersection(prev, cur, a, b)
                    if inter is not None:
                        output.append(inter)
                output.append(cur)
            elif prev_inside:
                inter = _line_intersection(prev, cur, a, b)
                if inter is not None:
                    output.append(inter)
            prev = cur
            prev_inside = cur_inside
    return abs(polygon_area(output)) if len(output) >= 3 else 0.0


def _is_left_of_edge(
    point: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
    *,
    tol: float = 1e-9,
) -> bool:
    return ((b[0] - a[0]) * (point[1] - a[1])
            - (b[1] - a[1]) * (point[0] - a[0])) >= -tol


def _line_intersection(
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    p4: tuple[float, float],
) -> tuple[float, float] | None:
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-12:
        return None
    px = ((x1 * y2 - y1 * x2) * (x3 - x4)
          - (x1 - x2) * (x3 * y4 - y3 * x4)) / denom
    py = ((x1 * y2 - y1 * x2) * (y3 - y4)
          - (y1 - y2) * (x3 * y4 - y3 * x4)) / denom
    return (px, py)


def _polygons_overlap(
    a: list[tuple[float, float]],
    b: list[tuple[float, float]],
) -> bool:
    if len(a) < 3 or len(b) < 3:
        return False
    if not _bbox_overlaps(a, b):
        return False
    if any(point_in_polygon(p, b) for p in a):
        return True
    if any(point_in_polygon(p, a) for p in b):
        return True
    return any(
        _segments_properly_intersect(a0, a1, b0, b1)
        for a0, a1 in _segments(a)
        for b0, b1 in _segments(b)
    )


def _bbox_overlaps(
    a: list[tuple[float, float]],
    b: list[tuple[float, float]],
) -> bool:
    ax = [p[0] for p in a]
    ay = [p[1] for p in a]
    bx = [p[0] for p in b]
    by = [p[1] for p in b]
    return not (
        max(ax) <= min(bx) or max(bx) <= min(ax)
        or max(ay) <= min(by) or max(by) <= min(ay)
    )


def _segments(
    poly: list[tuple[float, float]],
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    return [
        (poly[idx], poly[(idx + 1) % len(poly)])
        for idx in range(len(poly))
    ]


def _segments_properly_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
    *,
    tol: float = 1e-9,
) -> bool:
    def orient(p, q, r) -> float:
        return ((q[0] - p[0]) * (r[1] - p[1])
                - (q[1] - p[1]) * (r[0] - p[0]))

    o1 = orient(a, b, c)
    o2 = orient(a, b, d)
    o3 = orient(c, d, a)
    o4 = orient(c, d, b)
    return (
        o1 * o2 < -tol
        and o3 * o4 < -tol
    )


def _drawing_transform(result: CalculationResult):
    bounds = _ee4_drawing_bounds(result)
    if bounds is None:
        return None

    layout = _layout()
    min_x, min_y, max_x, max_y = bounds
    bw = max(max_x - min_x, 1.0)
    bh = max(max_y - min_y, 1.0)
    pad_ft = max(bw, bh) * 0.08
    min_x -= pad_ft
    min_y -= pad_ft
    max_x += pad_ft
    max_y += pad_ft
    bw = max_x - min_x
    bh = max_y - min_y
    scale = min(layout["drawing_w"] / bw, layout["drawing_h"] / bh)
    ox = layout["drawing_x"] + (layout["drawing_w"] - bw * scale) / 2
    oy = layout["drawing_y"] + (layout["drawing_h"] - bh * scale) / 2

    def to_pt(pt: tuple[float, float]) -> tuple[float, float]:
        return (
            ox + (pt[0] - min_x) * scale,
            oy + (pt[1] - min_y) * scale,
        )

    return layout, to_pt


def _layout() -> dict[str, float | tuple[float, float, float, float]]:
    width, height = landscape(letter)
    margin = 0.28 * inch
    drawing_x = 2.85 * inch
    drawing_y = 1.72 * inch
    drawing_w = width - drawing_x - 0.38 * inch
    drawing_h = height - drawing_y - 0.55 * inch
    return {
        "width": width,
        "height": height,
        "frame": (margin, margin, width - margin, height - margin),
        "drawing_x": drawing_x,
        "drawing_y": drawing_y,
        "drawing_w": drawing_w,
        "drawing_h": drawing_h,
    }


def _text_bbox(
    x: float,
    y: float,
    text: str,
    size: float,
    *,
    font: str = "Helvetica",
) -> tuple[float, float, float, float]:
    width = pdfmetrics.stringWidth(text, font, size)
    return (x - 2.0, y - 2.0, x + width + 2.0, y + size + 2.0)


def _bbox_check(
    name: str,
    bboxes: list[tuple[float, float, float, float]],
    frame: tuple[float, float, float, float],
    *,
    pass_detail: str,
    warn_detail: str,
) -> EE4LintResult:
    if not bboxes:
        return EE4LintResult(name, "PASS", "nothing to check")
    x0, y0, x1, y1 = frame
    pad = 0.04 * inch
    bad = [
        box for box in bboxes
        if box[0] < x0 + pad or box[1] < y0 + pad
        or box[2] > x1 - pad or box[3] > y1 - pad
    ]
    if bad:
        return EE4LintResult(name, "WARN", f"{warn_detail} ({len(bad)} item(s))")
    return EE4LintResult(name, "PASS", pass_detail)
