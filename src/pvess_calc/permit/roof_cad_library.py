"""Reusable CAD-style roof plan symbols for permit sheets.

The drawings here are intentionally generated primitives, not copied DWG
content.  They provide a small local library of the common roof-plan marks
used across PV-2/PV-4: module rectangles, fire-path hatches, keepout hatches,
roof penetrations, roof linework, and compact facet tags.
"""
from __future__ import annotations

from reportlab.lib import colors


CAD_BLACK = colors.HexColor("#111111")
CAD_GRAY = colors.HexColor("#6B7280")
PV_BLUE = colors.HexColor("#155EEF")
PV_FILL = colors.HexColor("#F8FBFF")
FIRE_ORANGE = colors.HexColor("#EA580C")
FIRE_FILL = colors.HexColor("#FFF7ED")
KEEP_OUT_ORANGE = colors.HexColor("#B45309")
KEEP_OUT_FILL = colors.HexColor("#FFEDD5")

ROOF_CAD_SYMBOL_KINDS = (
    "roof_vent",
    "plumbing",
    "ac",
    "satellite",
    "mast",
    "chimney",
    "fire",
    "no_panel",
)


def draw_closed_polygon(
    c,
    pts: list[tuple[float, float]],
    *,
    stroke=CAD_BLACK,
    fill=None,
    width: float = 0.55,
) -> None:
    if len(pts) < 3:
        return
    c.setStrokeColor(stroke)
    if fill is not None:
        c.setFillColor(fill)
    c.setLineWidth(width)
    c.setDash()
    path = c.beginPath()
    path.moveTo(*pts[0])
    for pt in pts[1:]:
        path.lineTo(*pt)
    path.close()
    c.drawPath(path, stroke=1, fill=1 if fill is not None else 0)
    c.setStrokeColor(CAD_BLACK)
    c.setFillColor(CAD_BLACK)


def draw_open_polyline(
    c,
    pts: list[tuple[float, float]],
    *,
    stroke=CAD_BLACK,
    width: float = 0.50,
    dash: tuple[float, float] | None = None,
) -> None:
    if len(pts) < 2:
        return
    c.setStrokeColor(stroke)
    c.setLineWidth(width)
    if dash is not None:
        c.setDash(*dash)
    else:
        c.setDash()
    path = c.beginPath()
    path.moveTo(*pts[0])
    for pt in pts[1:]:
        path.lineTo(*pt)
    c.drawPath(path, stroke=1, fill=0)
    if dash is not None:
        c.setDash()
    c.setStrokeColor(CAD_BLACK)


def draw_roof_outline(c, pts: list[tuple[float, float]], *, fill=False) -> None:
    draw_closed_polygon(
        c,
        pts,
        stroke=CAD_BLACK,
        fill=colors.white if fill else None,
        width=0.82,
    )


def draw_roof_facet(c, pts: list[tuple[float, float]]) -> None:
    draw_closed_polygon(c, pts, stroke=CAD_BLACK, fill=None, width=0.50)


def draw_roof_line(
    c,
    pts: list[tuple[float, float]],
    *,
    kind: str = "edge",
) -> None:
    width_by_kind = {
        "ridge": 0.68,
        "hip": 0.55,
        "valley": 0.62,
        "eave": 0.48,
        "edge": 0.45,
        "dormer": 0.50,
    }
    draw_open_polyline(
        c,
        pts,
        stroke=CAD_BLACK,
        width=width_by_kind.get(kind, 0.50),
    )


def draw_pv_module(c, pts: list[tuple[float, float]], *, width: float = 0.50) -> None:
    draw_closed_polygon(c, pts, stroke=PV_BLUE, fill=PV_FILL, width=width)


def draw_fire_pathway(c, pts: list[tuple[float, float]]) -> None:
    if len(pts) < 3:
        return
    draw_closed_polygon(c, pts, stroke=FIRE_ORANGE, fill=FIRE_FILL, width=0.38)
    draw_triangle_hatch(c, pts, stroke=colors.HexColor("#F97316"), step=8.0)
    draw_closed_polygon(c, pts, stroke=FIRE_ORANGE, fill=None, width=0.38)


def draw_keepout_area(c, pts: list[tuple[float, float]]) -> None:
    if len(pts) < 3:
        return
    draw_closed_polygon(c, pts, stroke=KEEP_OUT_ORANGE, fill=KEEP_OUT_FILL, width=0.35)
    draw_triangle_hatch(c, pts, stroke=colors.HexColor("#F97316"), step=6.8, size=3.0)
    draw_closed_polygon(c, pts, stroke=KEEP_OUT_ORANGE, fill=None, width=0.35)


def draw_triangle_hatch(
    c,
    pts: list[tuple[float, float]],
    *,
    stroke=FIRE_ORANGE,
    step: float = 8.0,
    size: float = 3.4,
) -> None:
    """Clip small outline triangles to a polygon.

    The triangle texture reads closer to common solar permit fire-pathway
    hatching than diagonal construction-detail hatch lines.
    """
    if len(pts) < 3:
        return
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    if max_x <= min_x or max_y <= min_y:
        return

    c.saveState()
    clip = c.beginPath()
    clip.moveTo(*pts[0])
    for pt in pts[1:]:
        clip.lineTo(*pt)
    clip.close()
    c.clipPath(clip, stroke=0, fill=0)
    c.setStrokeColor(stroke)
    c.setLineWidth(0.32)
    y = min_y - step
    row = 0
    while y <= max_y + step:
        x = min_x - step + (row % 2) * step * 0.5
        while x <= max_x + step:
            _draw_tiny_triangle(c, x, y, size)
            x += step
        row += 1
        y += step * 0.78
    c.restoreState()
    c.setStrokeColor(CAD_BLACK)


def _draw_tiny_triangle(c, cx: float, cy: float, size: float) -> None:
    h = size * 0.86
    path = c.beginPath()
    path.moveTo(cx - size / 2, cy + h / 3)
    path.lineTo(cx, cy - h * 2 / 3)
    path.lineTo(cx + size / 2, cy + h / 3)
    path.close()
    c.drawPath(path, stroke=1, fill=0)


def draw_roof_symbol(c, cx: float, cy: float, kind: str, *, size: float = 7.0) -> None:
    """Draw a common roof-plan symbol centered at ``cx, cy``."""
    c.setStrokeColor(CAD_BLACK)
    c.setFillColor(colors.white)
    c.setLineWidth(0.55)
    half = size / 2
    if kind == "roof_vent":
        c.rect(cx - half, cy - half, size, size, fill=0, stroke=1)
        c.line(cx - half + 1.5, cy - half + 1.5, cx + half - 1.5, cy + half - 1.5)
    elif kind == "plumbing":
        c.circle(cx, cy, half * 0.82, fill=0, stroke=1)
    elif kind == "ac":
        c.rect(cx - half * 1.45, cy - half, size * 1.45, size, fill=0, stroke=1)
        c.circle(cx, cy, half * 0.45, fill=0, stroke=1)
        c.line(cx - half * 0.55, cy, cx + half * 0.55, cy)
        c.line(cx, cy - half * 0.55, cx, cy + half * 0.55)
    elif kind == "satellite":
        c.arc(cx - size, cy - half, cx + size, cy + half, 200, 140)
        c.line(cx, cy - half * 0.45, cx, cy - size * 0.95)
        c.line(cx - half * 0.60, cy - size * 0.72, cx + half * 0.60, cy - size * 0.72)
    elif kind == "mast":
        c.rect(cx - half * 0.35, cy - half, half * 0.70, size * 0.90, fill=0, stroke=1)
        c.line(cx - half * 0.95, cy + half, cx + half * 0.95, cy + half)
    elif kind == "chimney":
        c.rect(cx - size * 0.75, cy - half, size * 1.50, size, fill=0, stroke=1)
        c.circle(cx, cy, max(1.2, size * 0.16), fill=0, stroke=1)
    else:
        c.rect(cx - half, cy - half, size, size, fill=0, stroke=1)
        c.circle(cx, cy, max(1.0, size * 0.16), fill=0, stroke=1)
    c.setStrokeColor(CAD_BLACK)
    c.setFillColor(CAD_BLACK)


def draw_facet_tag(
    c,
    x: float,
    y: float,
    label: str,
    *,
    font: str = "Helvetica-Bold",
    size: float = 5.4,
) -> None:
    text_w = c.stringWidth(label, font, size)
    pad_x = 2.0
    pad_y = 1.5
    c.setFillColor(colors.white)
    c.setStrokeColor(CAD_BLACK)
    c.setLineWidth(0.32)
    c.rect(x - pad_x, y - pad_y, text_w + pad_x * 2, size + pad_y * 2, fill=1, stroke=1)
    c.setFillColor(CAD_BLACK)
    c.setFont(font, size)
    c.drawString(x, y, label)
    c.setStrokeColor(CAD_BLACK)


def draw_keepout_swatch(c, cx: float, cy: float, *, label: str | None = None) -> None:
    pts = [
        (cx - 7, cy - 6),
        (cx + 7, cy - 6),
        (cx + 7, cy + 6),
        (cx - 7, cy + 6),
    ]
    draw_keepout_area(c, pts)
    if label:
        c.setFillColor(colors.white)
        c.rect(cx - 5.0, cy - 3.9, 10.0, 7.8, fill=1, stroke=0)
        c.setFillColor(KEEP_OUT_ORANGE)
        c.setFont("Helvetica-Bold", 4.8)
        c.drawCentredString(cx, cy - 1.7, label)


def draw_fire_swatch(c, cx: float, cy: float) -> None:
    pts = [
        (cx - 7, cy - 6),
        (cx + 7, cy - 6),
        (cx + 7, cy + 6),
        (cx - 7, cy + 6),
    ]
    draw_fire_pathway(c, pts)
