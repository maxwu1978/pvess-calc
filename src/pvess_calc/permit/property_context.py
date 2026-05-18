"""EE-4A property context plan.

Stage 9.8 separates the property-line / driveway / fence context from the
EE-4 array sheet. EE-4 remains the clean roof-array plan; EE-4A carries the
permit context graphics inspired by contractor site plans.
"""
from __future__ import annotations

import math
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from ..calc.engine import CalculationResult
from ._textfit import fit


def _sheet_label(result: CalculationResult) -> str:
    code = getattr(result, "_active_sheet_display_code", "EE-4A")
    title = getattr(result, "_active_sheet_title", "Property Context Plan")
    return f"{code} · {title.upper()}"


def render_property_context_plan(
    result: CalculationResult,
    out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=landscape(letter))
    W, H = landscape(letter)

    c.setLineWidth(0.9)
    c.rect(0.32 * inch, 0.32 * inch, W - 0.64 * inch, H - 0.64 * inch)
    _draw_north_arrow(c, x=0.42 * inch, y=H - 1.18 * inch)
    _draw_equipment_summary(c, result, x=W - 3.42 * inch, y=H - 1.30 * inch)

    plot = (0.95 * inch, 0.94 * inch, W - 1.80 * inch, H - 2.62 * inch)
    _draw_context(c, result, plot)

    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(W - 0.40 * inch, 0.44 * inch, _sheet_label(result))
    c.save()


def _draw_context(
    c: canvas.Canvas,
    result: CalculationResult,
    plot: tuple[float, float, float, float],
) -> None:
    x, y, w, h = plot
    bounds = _context_bounds(result)
    min_x, min_y, max_x, max_y = bounds
    bw = max(max_x - min_x, 1.0)
    bh = max(max_y - min_y, 1.0)
    scale = min(w / bw, h / bh)
    ox = x + (w - bw * scale) / 2
    oy = y + (h - bh * scale) / 2

    def to_pt(pt: tuple[float, float]) -> tuple[float, float]:
        return ox + (pt[0] - min_x) * scale, oy + (pt[1] - min_y) * scale

    site = result.inputs.site
    context = site.property_context
    fallback_prop_pts = [
        (min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y),
    ]
    prop_pts = context.lot_outline or fallback_prop_pts
    _draw_property_line(c, [to_pt(p) for p in prop_pts])
    if context.property_dimensions:
        for dim in context.property_dimensions:
            _draw_survey_dimension(c, dim, to_pt, scale)
    else:
        _draw_dimensions(c, [to_pt(p) for p in fallback_prop_pts], bw, bh)
    if context.driveway_polygon:
        driveway_label = _draw_driveway_polygon(
            c, [to_pt(p) for p in context.driveway_polygon]
        )
    else:
        driveway_label = _draw_driveway(
            c, to_pt, min_x=min_x, max_x=max_x, min_y=min_y, max_y=max_y
        )
    if context.fence_lines:
        _draw_fence_lines(c, context.fence_lines, to_pt)
    else:
        _draw_fence_label(c, to_pt, min_x=min_x, max_x=max_x, max_y=max_y)

    trace = site.ee4_trace
    if trace.enabled and trace.has_geometry:
        from .site_plan import (
            _draw_ee4_trace_fire_pathways,
            _draw_ee4_trace_roof,
            _draw_ee4_trace_symbols,
        )

        _draw_ee4_trace_roof(c, trace, to_pt, fill_outline=True)
        _draw_ee4_trace_fire_pathways(c, trace, to_pt)
        _draw_ee4_trace_roof(c, trace, to_pt, fill_outline=False)
        _draw_modules(c, result, to_pt)
        _draw_ee4_trace_symbols(c, trace, to_pt)
    else:
        _draw_simple_house(c, result, to_pt)
    _draw_driveway_label(c, driveway_label)

    cx = min_x + (max_x - min_x) * 0.50
    cy = min_y + (max_y - min_y) * 0.74
    c.setFont("Helvetica", 12)
    c.setFillColor(colors.black)
    px, py = to_pt((cx, cy))
    c.setFillColor(colors.white)
    tw = c.stringWidth("MAIN HOUSE", "Helvetica", 12)
    c.rect(px - tw / 2 - 4, py - 4, tw + 8, 12, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.drawCentredString(px, py, "MAIN HOUSE")


def _context_bounds(result: CalculationResult) -> tuple[float, float, float, float]:
    site = result.inputs.site
    pts: list[tuple[float, float]] = []
    context = site.property_context
    pts.extend(context.lot_outline)
    pts.extend(context.driveway_polygon)
    for line in context.fence_lines:
        pts.extend(line.points)
    for dim in context.property_dimensions:
        pts.extend([dim.start, dim.end])
    trace = site.ee4_trace
    if trace.enabled and trace.has_geometry:
        if trace.roof_outline is not None:
            pts.extend(trace.roof_outline.vertices)
        for poly in trace.roof_facets + trace.fire_pathways:
            pts.extend(poly.vertices)
        for line in trace.roof_lines:
            pts.extend(line.points)
    if site.house_outline_vertices:
        pts.extend(site.house_outline_vertices)
    else:
        hx0 = max(0.0, (site.lot_width_ft - site.house_width_ft) / 2)
        hy0 = max(0.0, (site.lot_depth_ft - site.house_depth_ft) / 2)
        pts.extend([
            (hx0, hy0), (hx0 + site.house_width_ft, hy0),
            (hx0 + site.house_width_ft, hy0 + site.house_depth_ft),
            (hx0, hy0 + site.house_depth_ft),
        ])
    for section in site.roof_sections:
        from .site_plan import _ee4_section_points
        pts.extend(_ee4_section_points(section))

    if not pts:
        return 0.0, 0.0, site.lot_width_ft, site.lot_depth_ft
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    pad_x = max(5.0, width * 0.08)
    pad_y = max(5.0, height * 0.14)
    return min(xs) - pad_x, min(ys) - pad_y, max(xs) + pad_x, max(ys) + pad_y


def _draw_property_line(c: canvas.Canvas, pts: list[tuple[float, float]]) -> None:
    c.setDash(7, 4)
    c.setStrokeColor(colors.HexColor("#334155"))
    c.setLineWidth(0.65)
    path = c.beginPath()
    path.moveTo(*pts[0])
    for p in pts[1:]:
        path.lineTo(*p)
    path.close()
    c.drawPath(path, stroke=1, fill=0)
    c.setDash()
    c.setStrokeColor(colors.black)
    top_mid_x = (pts[2][0] + pts[3][0]) / 2
    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(top_mid_x, pts[2][1] + 0.20 * inch, "PROPERTY LINE")


def _draw_dimensions(
    c: canvas.Canvas,
    pts: list[tuple[float, float]],
    width_ft: float,
    height_ft: float,
) -> tuple[float, float]:
    x0, y0 = pts[0]
    x1, y1 = pts[2]
    top_y = y1 + 0.46 * inch
    right_x = x1 + 0.32 * inch
    c.setStrokeColor(colors.black)
    c.setFillColor(colors.black)
    c.setLineWidth(0.45)
    c.line(x0, top_y, x1, top_y)
    c.line(x0, top_y - 0.06 * inch, x0, top_y + 0.06 * inch)
    c.line(x1, top_y - 0.06 * inch, x1, top_y + 0.06 * inch)
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.white)
    label = _feet_label(width_ft)
    tw = c.stringWidth(label, "Helvetica-Bold", 10)
    c.rect((x0 + x1) / 2 - tw / 2 - 4, top_y - 5, tw + 8, 11,
           fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.drawCentredString((x0 + x1) / 2, top_y - 3, label)

    c.line(right_x, y0, right_x, y1)
    c.line(right_x - 0.06 * inch, y0, right_x + 0.06 * inch, y0)
    c.line(right_x - 0.06 * inch, y1, right_x + 0.06 * inch, y1)
    c.saveState()
    c.translate(right_x + 0.10 * inch, (y0 + y1) / 2)
    c.rotate(90)
    c.drawCentredString(0, 0, _feet_label(height_ft))
    c.restoreState()


def _draw_survey_dimension(
    c: canvas.Canvas,
    dim,
    to_pt,
    scale: float,
) -> None:
    sx, sy = dim.start
    ex, ey = dim.end
    dx = ex - sx
    dy = ey - sy
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 0.01:
        return
    nx = -dy / length
    ny = dx / length
    offset = dim.offset_ft
    a = (sx + nx * offset, sy + ny * offset)
    b = (ex + nx * offset, ey + ny * offset)
    p0 = to_pt(dim.start)
    p1 = to_pt(dim.end)
    q0 = to_pt(a)
    q1 = to_pt(b)

    c.setStrokeColor(colors.black)
    c.setFillColor(colors.black)
    c.setLineWidth(0.45)
    c.line(q0[0], q0[1], q1[0], q1[1])
    c.line(p0[0], p0[1], q0[0], q0[1])
    c.line(p1[0], p1[1], q1[0], q1[1])

    tick = min(0.07 * inch, max(2.5, 0.35 * scale))
    tx = dx / length
    ty = dy / length
    for q in (q0, q1):
        c.line(q[0] - tx * tick, q[1] - ty * tick,
               q[0] + tx * tick, q[1] + ty * tick)

    label = dim.label or _feet_label(length)
    mx = (q0[0] + q1[0]) / 2
    my = (q0[1] + q1[1]) / 2
    angle = math.degrees(math.atan2(q1[1] - q0[1], q1[0] - q0[0]))
    if angle > 90:
        angle -= 180
    if angle < -90:
        angle += 180
    font = "Helvetica-Bold"
    size = 10
    tw = c.stringWidth(label, font, size)
    c.saveState()
    c.translate(mx, my)
    c.rotate(angle)
    c.setFillColor(colors.white)
    c.rect(-tw / 2 - 4, -5, tw + 8, 11, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setFont(font, size)
    c.drawCentredString(0, -3, label)
    c.restoreState()


def _draw_driveway(
    c: canvas.Canvas,
    to_pt,
    *,
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
) -> None:
    driveway_w = max(16.0, (max_x - min_x) * 0.13)
    x0 = max_x - driveway_w
    pts = [
        (x0, min_y), (max_x, min_y), (max_x, max_y), (x0, max_y),
    ]
    page_pts = [to_pt(p) for p in pts]
    c.setFillColor(colors.HexColor("#F8FAFC"))
    c.setStrokeColor(colors.HexColor("#94A3B8"))
    c.setLineWidth(0.35)
    path = c.beginPath()
    path.moveTo(*page_pts[0])
    for p in page_pts[1:]:
        path.lineTo(*p)
    path.close()
    c.drawPath(path, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#64748B"))
    for idx in range(28):
        px = page_pts[0][0] + 7 + (idx * 17) % max(10, int(page_pts[1][0] - page_pts[0][0] - 10))
        py = page_pts[0][1] + 7 + (idx * 23) % max(10, int(page_pts[2][1] - page_pts[0][1] - 10))
        c.circle(px, py, 0.8, fill=1, stroke=0)
    return (
        (page_pts[0][0] + page_pts[1][0]) / 2,
        (page_pts[0][1] + page_pts[2][1]) / 2,
    )


def _draw_driveway_polygon(
    c: canvas.Canvas,
    page_pts: list[tuple[float, float]],
) -> tuple[float, float]:
    c.setFillColor(colors.HexColor("#F8FAFC"))
    c.setStrokeColor(colors.HexColor("#94A3B8"))
    c.setLineWidth(0.35)
    path = c.beginPath()
    path.moveTo(*page_pts[0])
    for p in page_pts[1:]:
        path.lineTo(*p)
    path.close()
    c.drawPath(path, fill=1, stroke=1)

    min_x = min(p[0] for p in page_pts)
    max_x = max(p[0] for p in page_pts)
    min_y = min(p[1] for p in page_pts)
    max_y = max(p[1] for p in page_pts)
    c.setFillColor(colors.HexColor("#64748B"))
    width = max(10, int(max_x - min_x - 10))
    height = max(10, int(max_y - min_y - 10))
    for idx in range(28):
        px = min_x + 7 + (idx * 17) % width
        py = min_y + 7 + (idx * 23) % height
        c.circle(px, py, 0.8, fill=1, stroke=0)
    return (sum(p[0] for p in page_pts) / len(page_pts),
            sum(p[1] for p in page_pts) / len(page_pts))


def _draw_driveway_label(c: canvas.Canvas, center: tuple[float, float]) -> None:
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10)
    label = "DRIVEWAY"
    tw = c.stringWidth(label, "Helvetica-Bold", 10)
    c.setFillColor(colors.white)
    c.rect(center[0] - tw / 2 - 3, center[1] - 5, tw + 6, 12, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.drawCentredString(center[0], center[1] - 2, label)


def _draw_fence_label(
    c: canvas.Canvas,
    to_pt,
    *,
    min_x: float,
    max_x: float,
    max_y: float,
) -> None:
    sx, sy = to_pt((max_x - 22.0, max_y))
    ex, ey = to_pt((max_x - 2.0, max_y))
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.45)
    c.line(sx, sy, ex, ey)
    c.line(sx, sy, sx - 0.14 * inch, sy - 0.30 * inch)
    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString((sx + ex) / 2, sy + 0.24 * inch, "FENCE")


def _draw_fence_lines(c: canvas.Canvas, lines, to_pt) -> None:
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.55)
    for line in lines:
        pts = [to_pt(p) for p in line.points]
        path = c.beginPath()
        path.moveTo(*pts[0])
        for p in pts[1:]:
            path.lineTo(*p)
        c.drawPath(path, stroke=1, fill=0)

        label = line.label or ("FENCE" if line.kind == "fence" else line.kind.upper())
        mx = sum(p[0] for p in pts) / len(pts)
        my = sum(p[1] for p in pts) / len(pts)
        c.setFont("Helvetica-Bold", 15 if label == "FENCE" else 8)
        c.setFillColor(colors.HexColor("#64748B") if label == "FENCE" else colors.black)
        c.drawCentredString(mx, my + 0.18 * inch, label)
    c.setFillColor(colors.black)


def _draw_modules(c: canvas.Canvas, result: CalculationResult, to_pt) -> None:
    from .site_plan import _ee4_module_site_points

    c.setStrokeColor(colors.HexColor("#155EEF"))
    c.setFillColor(colors.HexColor("#EEF4FF"))
    c.setLineWidth(0.42)
    for section in result.inputs.site.roof_sections:
        for module in result.module_placements.get(section.name, []):
            pts = [to_pt(p) for p in _ee4_module_site_points(section, module)]
            if len(pts) < 4:
                continue
            path = c.beginPath()
            path.moveTo(*pts[0])
            for p in pts[1:]:
                path.lineTo(*p)
            path.close()
            c.drawPath(path, fill=1, stroke=1)
    c.setStrokeColor(colors.black)
    c.setFillColor(colors.black)


def _draw_simple_house(c: canvas.Canvas, result: CalculationResult, to_pt) -> None:
    site = result.inputs.site
    hx0 = max(0.0, (site.lot_width_ft - site.house_width_ft) / 2)
    hy0 = max(0.0, (site.lot_depth_ft - site.house_depth_ft) / 2)
    p0 = to_pt((hx0, hy0))
    p1 = to_pt((hx0 + site.house_width_ft, hy0 + site.house_depth_ft))
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.black)
    c.rect(p0[0], p0[1], p1[0] - p0[0], p1[1] - p0[1], fill=1, stroke=1)


def _draw_north_arrow(c: canvas.Canvas, *, x: float, y: float) -> None:
    box = 0.74 * inch
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.8)
    c.rect(x, y, box, box)
    cx = x + box / 2
    cy = y + box * 0.44
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(cx, y + box - 0.16 * inch, "N")
    path = c.beginPath()
    path.moveTo(cx, cy + 0.22 * inch)
    path.lineTo(cx - 0.16 * inch, cy - 0.12 * inch)
    path.lineTo(cx, cy - 0.03 * inch)
    path.lineTo(cx + 0.16 * inch, cy - 0.12 * inch)
    path.close()
    c.drawPath(path, stroke=1, fill=0)
    c.circle(cx, cy - 0.05 * inch, 0.18 * inch, fill=0, stroke=1)


def _draw_equipment_summary(
    c: canvas.Canvas,
    result: CalculationResult,
    *,
    x: float,
    y: float,
) -> None:
    i = result.inputs
    inv_count = i.inverter.count(i.battery.quantity)
    opt_count = (
        i.optimizer.effective_count(i.pv_array.modules, i.pv_array.strings)
        if i.optimizer.brand else 0
    )
    lines = [
        "EQUIPMENT SUMMARY:",
        f"PV MODULE: ({i.pv_array.modules}) {i.pv_array.module.brand.upper()} {i.pv_array.module.model}",
        f"INVERTER: ({inv_count}) {i.inverter.brand.upper()} {i.inverter.model}",
    ]
    if i.optimizer.brand:
        lines.append(f"OPTIMIZER: ({opt_count}) {i.optimizer.brand.upper()} {i.optimizer.model}")
    lines += [
        "",
        f"UTILITY: {i.project.utility or '-'}",
        f"ADDRESS: {i.project.site_address or '-'}",
    ]
    w = 3.05 * inch
    h = 0.92 * inch
    c.setLineWidth(0.55)
    c.rect(x, y, w, h)
    c.setFont("Helvetica-Bold", 6.8)
    yy = y + h - 0.10 * inch
    for idx, line in enumerate(lines):
        if not line:
            yy -= 0.06 * inch
            continue
        font = "Helvetica-Bold" if idx == 0 else "Helvetica"
        c.setFont(font, 6.2)
        c.drawString(x + 0.04 * inch, yy, fit(line, font, 6.2, w - 0.08 * inch))
        yy -= 0.10 * inch


def _feet_label(value: float) -> str:
    whole = int(value)
    inches = int(round((value - whole) * 12))
    if inches == 12:
        whole += 1
        inches = 0
    if inches:
        return f"{whole}'-{inches}\""
    return f"{whole}'"
