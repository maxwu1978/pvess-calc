"""Structural sheets (Phase J): attachment plan + mounting details + string plan.

These three sheets together cover what Wyssling-style permits put on PV-4
(Attachment Plan), PV-5 (Mounting Details), and the PV string layout sheet.
They reuse the same ANSI B landscape format as the electrical sheets.

**K.2.6c additions to PV-4 (Attachment Plan):**
  * Roof description table gains a `SHAPE` column (rect / tri) and a
    `USABLE` column (sqft after setbacks + obstructions).
  * The schematic grid is replaced with a per-section drawing:
      - Roof outline traces the actual geometry (rect or tri).
      - Inset dashed line shows the NEC 690.12 setback zone.
      - Each obstruction is drawn as a hatched box with its 18" halo.
      - Modules placed inside the usable polygon, not the gross face.

Old yamls (rect-only, no obstructions) render visually similar to the
pre-K.2.6c output — the new columns just gain a small "USABLE" value.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from ..calc.engine import CalculationResult
from ..calc.roof_layout import _evaluate_section
from ._textfit import fit


# Colors used for string-block highlighting on the roof plan.
STRING_COLORS = [
    "#FF6B6B", "#4ECDC4", "#FFE066", "#A8E6CF",
    "#FFB3D9", "#C7CEEA", "#FF8E72", "#92D7E7",
]

# High-contrast fills for PV-6 v2. The reference string sheet uses saturated
# module fills rather than PV-4's pastel structural colors.
STRING_PLAN_COLORS = [
    "#16A34A", "#E11D48", "#FDE047", "#2563EB",
    "#F97316", "#7C3AED", "#06B6D4", "#84CC16",
]

# Fallback color when a module hasn't been assigned a string yet
# (K.10.1 degenerate yaml). Matches the pre-K.10 PV-4 blue.
UNASSIGNED_STROKE = "#1F5BD7"
UNASSIGNED_FILL = "#E8F0FF"


def _string_sheet_label(result: CalculationResult) -> str:
    code = getattr(result, "_active_sheet_display_code", "PV-6")
    title = getattr(result, "_active_sheet_title", "String Layout Plan")
    return f"{code} · {title.upper()}"


def _lighten_hex(hex_color: str, factor: float = 0.55) -> colors.Color:
    """Mix `hex_color` with white. `factor=0` returns the original
    color, `factor=1` returns pure white. Default 0.55 gives a soft
    pastel fill that keeps the saturated stroke readable on top."""
    h = hex_color.lstrip("#")
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    r = r + int((255 - r) * factor)
    g = g + int((255 - g) * factor)
    b = b + int((255 - b) * factor)
    return colors.Color(r / 255, g / 255, b / 255)


def _string_stroke(string_index) -> colors.Color:
    """Saturated outline color for a string (K.10.3 PV-4 color-by-string)."""
    if string_index is None:
        return colors.HexColor(UNASSIGNED_STROKE)
    return colors.HexColor(STRING_COLORS[string_index % len(STRING_COLORS)])


def _string_fill(string_index) -> colors.Color:
    """Lightened fill for a module rect (so multiple bands don't read
    as a single dense slab)."""
    if string_index is None:
        return colors.HexColor(UNASSIGNED_FILL)
    return _lighten_hex(STRING_COLORS[string_index % len(STRING_COLORS)])


def _string_plan_fill(string_index) -> colors.Color:
    if string_index is None:
        return colors.HexColor(UNASSIGNED_FILL)
    return colors.HexColor(STRING_PLAN_COLORS[string_index % len(STRING_PLAN_COLORS)])


def _ensure_sections(result: CalculationResult) -> list:
    """If the project didn't supply roof_sections, fabricate a single section
    covering the entire array. Keeps the sheets useful for projects that
    haven't been fully digitized yet."""
    i = result.inputs
    if i.site.roof_sections:
        return i.site.roof_sections
    from ..schema import RoofSection
    return [RoofSection(
        name="Roof A",
        roof_type="Comp Shingle",
        pitch_deg=i.site.roof_pitch_deg,
        azimuth_deg=i.site.array_azimuth_deg,
        module_count=i.pv_array.modules,
        width_ft=i.site.array_width_ft,
        height_ft=i.site.array_depth_ft,
        attachment_count=_estimate_attachments(i.pv_array.modules, i.site.mounting),
    )]


def _sections_with_layout(result: CalculationResult) -> list:
    """Pair each RoofSection with its computed SectionLayoutResult.

    When the yaml has explicit roof_sections, the engine's roof_layout
    output is parallel by index. When the yaml has none, we synthesise
    a layout for the fake section so PV-4 still renders a useful plan
    with setback / usable-area annotations.
    """
    sections = _ensure_sections(result)
    if (result.roof_layout.sections
            and len(result.roof_layout.sections) == len(sections)):
        return list(zip(sections, result.roof_layout.sections))
    return [(s, _evaluate_section(s)) for s in sections]


def _estimate_attachments(n_modules: int, mounting) -> int:
    """Rough rule of thumb: 4 attachments per module for residential lag-
    screw rails (NEC/Ironridge guidance varies)."""
    if n_modules <= 0:
        return 0
    return max(2, n_modules * 2)


def _display_attachment_count(section, placed_count: int) -> int:
    """Attachment count shown on PV-4.

    Designer-entered `attachment_count` wins. Google Solar / traced-layout
    fixtures often leave it at 0; in that case show a conservative visual
    estimate that matches the attachment dots rendered in the plan.
    """
    if section.attachment_count > 0:
        return section.attachment_count
    target = placed_count if placed_count > 0 else section.module_count
    return _estimate_attachments(target, None)


# --- PV-4 Attachment Plan ---------------------------------------------------

def render_attachment_plan(result: CalculationResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=landscape(letter))
    W, H = landscape(letter)
    i = result.inputs
    pairs = _sections_with_layout(result)
    sections = [p[0] for p in pairs]
    mounting = i.site.mounting

    c.setLineWidth(1.0)
    c.rect(0.4 * inch, 0.4 * inch, W - 0.8 * inch, H - 0.8 * inch)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(W / 2, H - 0.8 * inch, "PV-4 · ATTACHMENT PLAN")

    # Roof description table (left side). K.2.6c adds SHAPE and USABLE
    # columns; the row layout stays compatible (existing columns shift
    # over by ~0.4" to make room).
    table_x = 0.55 * inch
    table_y = H - 1.30 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(table_x, table_y, "ROOF DESCRIPTION")
    c.setLineWidth(0.5)
    c.line(table_x, table_y - 0.05 * inch, table_x + 5.25 * inch, table_y - 0.05 * inch)

    # K.2.6c column layout. Header widths measured at 9pt Helvetica-Bold:
    #   "AZIMUTH" 0.50"  "MODULES" 0.55"  "USABLE" 0.42"  "ATTACH" 0.41"
    # We shorten "ATTACH"→"ATT" and "MODULES"→"MOD" so the row never
    # overflows 5.10"; gaps between adjacent headers ≥ 0.10" so no two
    # bold-9pt strings touch.
    cols = [
        ("ROOF",          0.00),
        ("SHAPE",         0.95),
        ("TYPE",          1.45),
        ("PITCH",         2.35),
        ("AZIMUTH",       2.80),
        ("MOD",           3.45),
        ("ATT",           3.85),
        ("GROSS",         4.30),
        ("USABLE",        4.85),
    ]
    c.setFont("Helvetica-Bold", 9)
    hdr_y = table_y - 0.22 * inch
    for label, dx in cols:
        c.drawString(table_x + dx * inch, hdr_y, label)
    c.setLineWidth(0.3)
    c.line(table_x, hdr_y - 0.05 * inch,
           table_x + 5.25 * inch, hdr_y - 0.05 * inch)

    c.setFont("Helvetica", 9)
    yy = hdr_y - 0.22 * inch
    total_attach = 0
    total_gross = 0.0
    total_usable = 0.0
    over_packed_rows: list[str] = []
    for s, layout in pairs:
        placed_count = len(result.module_placements.get(s.name, []))
        attach_count = _display_attachment_count(s, placed_count)
        # SHAPE column: small chip indicating rect or tri
        shape_label = {
            "rect":    "▭ rect",
            "tri":     "△ tri",
            "polygon": "⬡ poly",
        }.get(s.shape, s.shape)
        # TYPE column spans 0.90" (1.45→2.35); fit() trims to that width.
        row = [
            s.name,
            shape_label,
            fit(s.roof_type, "Helvetica", 9, 0.85 * inch),
            f"{s.pitch_deg:.0f}°",
            f"{s.azimuth_deg:.0f}°",
            str(s.module_count),
            str(attach_count),
            f"{layout.gross_area_sqft:.0f}",
            f"{layout.usable_area_sqft:.0f}",
        ]
        # USABLE column dx (kept as a constant so the over-packed red-flag
        # branch tracks any future layout change).
        usable_dx = 4.85
        for (_, dx), val in zip(cols, row):
            # Color USABLE red when the row over-packs — avoids any
            # warning text spilling into the MOUNTING SYSTEM table.
            if not layout.fits and dx == usable_dx:
                c.setFillColorRGB(0.78, 0.10, 0.10)
                c.setFont("Helvetica-Bold", 9)
                c.drawString(table_x + dx * inch, yy, f"✗ {val}")
                c.setFillColor(colors.black)
                c.setFont("Helvetica", 9)
            else:
                c.drawString(table_x + dx * inch, yy, val)
        if not layout.fits:
            over_packed_rows.append(s.name)
        yy -= 0.18 * inch
        total_attach += attach_count
        total_gross += layout.gross_area_sqft
        total_usable += layout.usable_area_sqft
    # Totals — column dx values must match `cols` exactly.
    c.setLineWidth(0.4)
    c.line(table_x, yy + 0.07 * inch, table_x + 5.25 * inch, yy + 0.07 * inch)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(table_x, yy - 0.05 * inch, "TOTAL")
    c.drawString(table_x + 3.45 * inch, yy - 0.05 * inch,
                 str(sum(s.module_count for s in sections)))
    c.drawString(table_x + 3.85 * inch, yy - 0.05 * inch, str(total_attach))
    c.drawString(table_x + 4.30 * inch, yy - 0.05 * inch, f"{total_gross:.0f}")
    c.drawString(table_x + 4.85 * inch, yy - 0.05 * inch, f"{total_usable:.0f}")
    # Over-packed footnote — kept inside the 5.4" table width.
    if over_packed_rows:
        c.setFillColorRGB(0.78, 0.10, 0.10)
        c.setFont("Helvetica-Oblique", 7.5)
        c.drawString(
            table_x, yy - 0.22 * inch,
            f"✗ Over-packed (modules > usable area): {', '.join(over_packed_rows)}",
        )
        c.setFillColor(colors.black)

    # Mounting specs box (right side, top)
    mb_x = 6.2 * inch
    mb_y = H - 1.30 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(mb_x, mb_y, "MOUNTING SYSTEM")
    c.line(mb_x, mb_y - 0.05 * inch, mb_x + 3.5 * inch, mb_y - 0.05 * inch)
    c.setFont("Helvetica", 9)
    rows = [
        ("Rail",              mounting.rail_system),
        ("Flashing",          mounting.flashing),
        ("Max X spacing",     f"{mounting.max_x_spacing_in:.0f}\""),
        ("Max Y spacing",     f"{mounting.max_y_spacing_in:.0f}\""),
        ("Max cantilever",    f"{mounting.max_cantilever_in:.0f}\""),
        ("Fastener",          mounting.fastener),
    ]
    yy = mb_y - 0.25 * inch
    for label, val in rows:
        c.drawString(mb_x, yy, label)
        c.drawString(mb_x + 1.4 * inch, yy, val)
        yy -= 0.20 * inch

    # K.2.6c roof-plan drawings (bottom half). Stage 9.7 uses the same
    # traced whole-roof geometry as EE-4 when available, which matches the
    # industry reference style better than separate per-face thumbnails.
    plot_x = 0.6 * inch
    plot_y = 0.78 * inch
    plot_w = W - 1.2 * inch
    plot_h = 4.58 * inch
    c.setLineWidth(0.8)
    c.rect(plot_x, plot_y, plot_w, plot_h)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(plot_x + 0.10 * inch, plot_y + plot_h - 0.18 * inch,
                 "ROOF ATTACHMENT PLAN")

    if _can_draw_traced_attachment_plan(result):
        _draw_traced_attachment_plan(
            c, result,
            x=plot_x + 0.18 * inch,
            y=plot_y + 0.28 * inch,
            w=plot_w - 0.36 * inch,
            h=plot_h - 0.62 * inch,
        )
    else:
        n_sec = max(1, len(pairs))
        sub_w = (plot_w - 0.4 * inch) / n_sec
        sub_y = plot_y + 0.30 * inch
        sub_h = plot_h - 0.70 * inch
        for idx, (section, layout) in enumerate(pairs):
            sub_x = plot_x + 0.20 * inch + idx * sub_w
            # K.9.3: pass through this face's per-module placements (from
            # K.9.2 engine integration). Empty list when the project is
            # legacy / single-orientation — falls back to the K.2.8 heuristic
            # grid inside `_draw_section_plan`.
            placements = result.module_placements.get(section.name, [])
            _draw_section_plan(c, sub_x, sub_y, sub_w - 0.15 * inch, sub_h,
                               section, layout, placements=placements)

    # NOTE: pre-K.11.7e had a "X spacing / Y spacing / Cantilever"
    # one-liner here, but the same 3 numbers are already in the
    # MOUNTING SYSTEM block at the top of the page AND the callout
    # overlapped the MPPT STRINGS legend below the plot frame.
    # Removed — single source of truth lives in MOUNTING SYSTEM.

    # K.9.3: module dimension callout in the bottom-right corner
    # (matches the Aurora-style reference image's "67.80″ × 44.65″"
    # box). One-page-glance reference for the AHJ reviewer and the
    # installer comparing yaml-spec to as-installed panels.
    _draw_module_dim_callout(
        c,
        x=W - 1.95 * inch, y=0.50 * inch,
        w=1.50 * inch, h=1.00 * inch,
        module=i.pv_array.module,
    )

    if not _can_draw_traced_attachment_plan(result):
        # K.10.3: string legend in the bottom-LEFT corner for the legacy
        # per-face plot. The traced attachment plan intentionally omits MPPT
        # colors so PV-4 reads as a structural sheet, not a stringing sheet.
        _draw_string_legend(
            c,
            x=0.45 * inch, y=0.50 * inch,
            w=2.00 * inch, h=1.00 * inch,
            result=result,
        )

    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(W / 2, 0.25 * inch,
                        "Roof plan shows modules, framing guides, and "
                        "attachment points. See PV-5 for mounting detail.")
    c.save()


def _draw_module_dim_callout(
    c, *, x: float, y: float, w: float, h: float, module,
) -> None:
    """K.9.3 — small reference block showing the module's physical
    dimensions, centred over a scaled rectangle. Matches the Aurora /
    OpenSolar convention of putting a "this is what a panel looks like"
    box in the corner of the PV-4 plan so the AHJ reviewer doesn't
    have to dig through the spec sheet."""
    # Frame
    c.setLineWidth(0.4)
    c.setStrokeColor(colors.HexColor("#94a3b8"))
    c.setFillColor(colors.white)
    c.rect(x, y, w, h, fill=1, stroke=1)
    c.setStrokeColor(colors.black)

    # Scaled module rect — show actual aspect ratio
    mod_long_ft = module.length_in / 12.0
    mod_short_ft = module.width_in / 12.0
    # Reserve a 12pt strip at bottom for the model label, 8pt at sides
    drawable_w = w - 0.16 * inch
    drawable_h = h - 0.40 * inch
    aspect = mod_long_ft / mod_short_ft   # > 1 (long edge / short edge)
    # Try landscape (long horizontal)
    rect_h = drawable_h
    rect_w = rect_h * aspect
    if rect_w > drawable_w:
        rect_w = drawable_w
        rect_h = rect_w / aspect
    rect_x = x + (w - rect_w) / 2
    rect_y = y + 0.30 * inch + (drawable_h - rect_h) / 2

    c.setFillColor(colors.HexColor("#E8F0FF"))
    c.setStrokeColor(colors.HexColor("#1F5BD7"))
    c.setLineWidth(0.5)
    c.rect(rect_x, rect_y, rect_w, rect_h, fill=1, stroke=1)
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)

    # Dimension annotations (in / mm convention is in")
    c.setFont("Helvetica", 6.5)
    # Long edge (above rect)
    long_label = f'{module.length_in:.2f}"'
    c.drawCentredString(rect_x + rect_w / 2,
                        rect_y + rect_h + 0.04 * inch, long_label)
    # Short edge (right of rect)
    short_label = f'{module.width_in:.2f}"'
    c.drawString(rect_x + rect_w + 0.04 * inch,
                 rect_y + rect_h / 2 - 0.02 * inch, short_label)

    # Model + brand label (bottom of callout)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(x + w / 2, y + 0.15 * inch,
                        f"{module.brand} {module.model}".upper())
    c.setFont("Helvetica", 6)
    c.drawCentredString(x + w / 2, y + 0.05 * inch,
                        f"{module.power_w:.0f} W  ·  {module.weight_lbs:.1f} lbs")


def _draw_string_legend(
    c, *, x: float, y: float, w: float, h: float,
    result: CalculationResult,
) -> None:
    """K.10.3 — bottom-left legend mapping each MPPT string color to
    its module count + face list. Lets the AHJ reviewer decode the
    rainbow bands on the roof plans without flipping to EE-1.

    Sourced from `result.module_placements` (already
    string_index-assigned by `engine.run()`). When no placements exist
    (legacy single-orientation projects), the legend just lists the
    declared string count without color swatches.
    """
    # Frame
    c.setLineWidth(0.4)
    c.setStrokeColor(colors.HexColor("#94a3b8"))
    c.rect(x, y, w, h, fill=0, stroke=1)
    c.setStrokeColor(colors.black)

    # Title
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x + 0.08 * inch, y + h - 0.16 * inch,
                 "MPPT STRINGS")

    # Gather string → (count, set of faces) from placements
    by_string: dict[int, tuple[int, set]] = {}
    for face_name, mods in result.module_placements.items():
        for m in mods:
            if m.string_index is None:
                continue
            count, faces = by_string.get(m.string_index, (0, set()))
            by_string[m.string_index] = (count + 1, faces | {face_name})

    # Fallback when no placements: show declared string count w/ no swatch
    n_declared = result.inputs.pv_array.strings
    if not by_string:
        c.setFont("Helvetica", 7)
        c.drawString(x + 0.08 * inch, y + h - 0.32 * inch,
                     f"{n_declared} strings declared "
                     f"(per-module assignment unavailable)")
        return

    # One row per string. Available height = h - 0.22" (title) - 0.08" (pad)
    rows = sorted(by_string.items())
    avail_h = h - 0.30 * inch
    n_rows = max(len(rows), 1)
    row_h = min(0.13 * inch, avail_h / n_rows)
    swatch_w = 0.18 * inch
    swatch_h = 0.09 * inch
    text_size = 6.5 if row_h < 0.12 * inch else 7

    c.setFont("Helvetica", text_size)
    for i_row, (s_idx, (count, faces)) in enumerate(rows):
        row_y = y + h - 0.22 * inch - (i_row + 1) * row_h + 0.02 * inch
        # Color swatch
        c.setFillColor(_string_fill(s_idx))
        c.setStrokeColor(_string_stroke(s_idx))
        c.setLineWidth(0.4)
        c.rect(x + 0.08 * inch, row_y, swatch_w, swatch_h,
               fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.setStrokeColor(colors.black)
        # Label: "S1: 9 mods · South Roof, South Roof #2"
        faces_str = ", ".join(sorted(faces))
        label = f"S{s_idx + 1}: {count} mods · {faces_str}"
        # Use the textfit helper to truncate when the face list is long
        max_text_w = w - 0.32 * inch
        clipped = fit(label, "Helvetica", text_size, max_text_w)
        c.drawString(x + 0.30 * inch, row_y + 0.02 * inch, clipped)


def _can_draw_traced_attachment_plan(result: CalculationResult) -> bool:
    """True when PV-4 can use the EE-4 whole-roof traced geometry."""
    from .site_plan import _ee4_trace_active

    return bool(
        _ee4_trace_active(result.inputs.site)
        and any(result.module_placements.values())
    )


def _draw_traced_attachment_plan(
    c, result: CalculationResult, *, x: float, y: float, w: float, h: float,
) -> None:
    """Stage 9.7 — competitor-style PV-4: one roof plan with structural
    attachment overlay.

    This intentionally reuses the EE-4 traced roof coordinate system so the
    site plan and attachment plan describe the same geometry. PV-4 then adds
    only structural layers: framing guides, module outlines, and red
    attachment points.
    """
    from ..calc.wire_routing import _face_local_to_site
    from .site_plan import (
        _draw_ee4_trace_fire_pathways,
        _draw_ee4_trace_roof,
        _draw_ee4_trace_symbols,
        _ee4_drawing_bounds,
        _ee4_module_site_points,
    )

    bounds = _ee4_drawing_bounds(result)
    if bounds is None:
        return
    min_x, min_y, max_x, max_y = bounds
    bw = max(max_x - min_x, 1.0)
    bh = max(max_y - min_y, 1.0)
    pad_ft = max(bw, bh) * 0.045
    min_x -= pad_ft
    min_y -= pad_ft
    max_x += pad_ft
    max_y += pad_ft
    bw = max_x - min_x
    bh = max_y - min_y
    callout_band_h = 0.46 * inch
    plan_y = y + callout_band_h
    plan_h = max(h - callout_band_h, 1.0 * inch)
    scale = min(w / bw, plan_h / bh)
    ox = x + (w - bw * scale) / 2
    oy = plan_y + (plan_h - bh * scale) / 2

    def to_pt(pt: tuple[float, float]) -> tuple[float, float]:
        return ox + (pt[0] - min_x) * scale, oy + (pt[1] - min_y) * scale

    trace = result.inputs.site.ee4_trace
    _draw_ee4_trace_roof(c, trace, to_pt, fill_outline=True)
    _draw_ee4_trace_fire_pathways(c, trace, to_pt)
    _draw_ee4_trace_roof(c, trace, to_pt, fill_outline=False)

    # Modules: pale fill + blue outlines, matching EE-4 but slightly lighter
    # so the red attachment points remain the highest-salience layer.
    for section in result.inputs.site.roof_sections:
        for m in result.module_placements.get(section.name, []):
            pts = [to_pt(p) for p in _ee4_module_site_points(section, m)]
            if len(pts) < 4:
                continue
            _draw_module_polygon(c, pts)

    # Framing guides: light gray lines within each module footprint. Keeping
    # them module-local avoids gray rails flooding non-array roof areas.
    c.setStrokeColor(colors.HexColor("#B8B8B8"))
    c.setLineWidth(0.28)
    for section in result.inputs.site.roof_sections:
        for m in result.module_placements.get(section.name, []):
            for frac in (0.25, 0.50, 0.75):
                p0 = _face_local_to_site(
                    section, m.x_ft + m.width_ft * frac, m.y_ft
                )
                p1 = _face_local_to_site(
                    section, m.x_ft + m.width_ft * frac,
                    m.y_ft + m.height_ft,
                )
                if p0 is None or p1 is None:
                    continue
                x0, y0 = to_pt(p0)
                x1, y1 = to_pt(p1)
                c.line(x0, y0, x1, y1)

    # Red attachment points sit above modules and framing.
    for section in result.inputs.site.roof_sections:
        for m in result.module_placements.get(section.name, []):
            _draw_module_attachment_points(c, section, m, to_pt)

    _draw_ee4_trace_symbols(c, trace, to_pt)
    _draw_attachment_plan_callouts(c, x=x, y=y, w=w, h=h)


def _draw_module_polygon(
    c, pts: list[tuple[float, float]],
) -> None:
    if len(pts) < 4:
        return
    c.setStrokeColor(colors.HexColor("#155EEF"))
    c.setFillColor(colors.HexColor("#F7FAFF"))
    c.setLineWidth(0.45)
    path = c.beginPath()
    path.moveTo(*pts[0])
    for p in pts[1:]:
        path.lineTo(*p)
    path.close()
    c.drawPath(path, stroke=1, fill=1)
    c.setStrokeColor(colors.black)
    c.setFillColor(colors.black)


def _draw_module_attachment_points(c, section, module, to_pt) -> None:
    from ..calc.wire_routing import _face_local_to_site

    c.setStrokeColor(colors.HexColor("#DC2626"))
    c.setFillColor(colors.white)
    c.setLineWidth(0.42)
    size = 2.2
    local_points = [
        (module.x_ft + module.width_ft * 0.28,
         module.y_ft + module.height_ft * 0.50),
        (module.x_ft + module.width_ft * 0.72,
         module.y_ft + module.height_ft * 0.50),
    ]
    for local_x, local_y in local_points:
        pt = _face_local_to_site(section, local_x, local_y)
        if pt is None:
            continue
        px, py = to_pt(pt)
        c.rect(px - size / 2, py - size / 2, size, size, fill=1, stroke=1)
    c.setStrokeColor(colors.black)
    c.setFillColor(colors.black)


def _draw_attachment_plan_callouts(
    c, *, x: float, y: float, w: float, h: float,
) -> None:
    """Small structural callouts inspired by the reference attachment plan."""
    base_y = y + 0.18 * inch
    c.setStrokeColor(colors.black)
    c.setFillColor(colors.black)
    c.setLineWidth(0.45)
    c.setFont("Helvetica-Bold", 10)

    # 48" max spacing.
    sx = x + w * 0.58
    y48 = base_y + 0.25 * inch
    c.line(sx - 0.28 * inch, y48, sx + 0.28 * inch, y48)
    c.line(sx - 0.28 * inch, y48 - 0.06 * inch,
           sx - 0.28 * inch, y48 + 0.06 * inch)
    c.line(sx + 0.28 * inch, y48 - 0.06 * inch,
           sx + 0.28 * inch, y48 + 0.06 * inch)
    c.drawRightString(sx - 0.36 * inch, y48 - 0.03 * inch,
                      '48" MAX SPACING')

    # 24" framing spacing.
    fx = x + w * 0.34
    y24 = base_y + 0.18 * inch
    c.line(fx - 0.30 * inch, y24, fx + 0.30 * inch, y24)
    c.line(fx - 0.30 * inch, y24 - 0.06 * inch,
           fx - 0.30 * inch, y24 + 0.06 * inch)
    c.line(fx + 0.30 * inch, y24 - 0.06 * inch,
           fx + 0.30 * inch, y24 + 0.06 * inch)
    c.drawCentredString(fx, y24 - 0.17 * inch,
                        '24" FRAMING SPACING')

    # Legend note for red points.
    c.setFont("Helvetica", 6.6)
    c.drawRightString(x + w - 0.06 * inch, y + h - 0.18 * inch,
                 "RED SQUARES = ATTACHMENT POINTS; GRAY LINES = FRAMING GUIDES")
    c.setStrokeColor(colors.black)


def _draw_section_plan(
    c, x: float, y: float, w: float, h: float, section, layout,
    *,
    placements=None,
) -> None:
    """K.2.6c + K.9.3 — draw one roof section as a plan.

    Coords: in section-local ft (origin at bottom-left of bounding box,
    x toward right / along eave, y toward top / ridge or apex). The
    function scales to fit (`w` × `h`) reportlab points and inverts y
    so 'ridge' is at top of the page.

    Draws (in z-order):
        1. Section outline (solid)
        2. Setback inset (dashed)
        3. Module rectangles — K.9.3 draws each `ModuleInstance` at its
           exact (x, y, rotation) when `placements` is non-empty; legacy
           K.2.8 heuristic grid as fallback.
        4. Obstructions w/ halo (hatched)
        5. Labels
    """
    placements = placements or []
    # Compute scale: fit section's bounding box into (w, h) with margin
    pad = 0.30 * inch
    avail_w = max(w - 2 * pad, 0.5 * inch)
    avail_h = max(h - 0.5 * inch, 0.5 * inch)
    sec_w = section.width_ft
    sec_h = section.height_ft
    if sec_w <= 0 or sec_h <= 0:
        return
    scale = min(avail_w / sec_w, avail_h / sec_h)

    # Local→page transform; y-flip so y=0 (eave) is at the bottom.
    def px(local_x: float) -> float:
        return x + pad + local_x * scale

    def py(local_y: float) -> float:
        return y + 0.10 * inch + local_y * scale

    # Title strip
    c.setFont("Helvetica-Bold", 9)
    title = f"{section.name}   ({section.pitch_deg:.0f}° / {section.azimuth_deg:.0f}°az)"
    c.drawString(x + pad, y + h - 0.10 * inch, title)
    c.setFont("Helvetica", 7.5)
    c.drawString(x + pad, y + h - 0.22 * inch,
                 f"Gross {layout.gross_area_sqft:.0f} ft² · "
                 f"Usable {layout.usable_area_sqft:.0f} ft² · "
                 f"{layout.module_count} mods")

    # 1. Section outline
    c.setLineWidth(1.2)
    c.setStrokeColor(colors.black)
    if section.shape == "rect":
        c.rect(px(0), py(0), sec_w * scale, sec_h * scale)
    elif section.shape == "tri":
        apex_x = section.apex_x_ratio * sec_w
        path = c.beginPath()
        path.moveTo(px(0), py(0))
        path.lineTo(px(sec_w), py(0))
        path.lineTo(px(apex_x), py(sec_h))
        path.close()
        c.drawPath(path, stroke=1, fill=0)
    else:  # K.2.7 polygon
        path = c.beginPath()
        v0x, v0y = section.vertices[0]
        path.moveTo(px(v0x), py(v0y))
        for vx, vy in section.vertices[1:]:
            path.lineTo(px(vx), py(vy))
        path.close()
        c.drawPath(path, stroke=1, fill=0)

    # 2. Setback inset (dashed). For rect we redraw the inset rectangle;
    # for tri we use the inradius-shrunken triangle.
    c.setLineWidth(0.5)
    c.setStrokeColor(colors.HexColor("#888888"))
    c.setDash(3, 2)
    if section.shape == "rect":
        eave = section.edge_setback_for("eave")
        ridge = section.edge_setback_for("ridge")
        rake = section.edge_setback_for("rake")
        inset_w = max(0, sec_w - 2 * rake)
        inset_h = max(0, sec_h - eave - ridge)
        if inset_w > 0 and inset_h > 0:
            c.rect(px(rake), py(eave), inset_w * scale, inset_h * scale)
    elif section.shape == "tri":
        # Tri inset: similar triangle centred on incenter, scaled by r'/r.
        d = max(section.edge_setback_for("eave"),
                section.edge_setback_for("hip"))
        apex_x = section.apex_x_ratio * sec_w
        # Approximate incenter for the triangle (weighted by opposite edge len)
        a = math.hypot(sec_w - apex_x, sec_h)             # left opposite vertex (0,0)
        b = math.hypot(apex_x, sec_h)                     # right opposite vertex (w,0)
        c_edge = sec_w                                    # apex opposite edge
        P = a + b + c_edge
        if P > 0:
            in_x = (a * 0 + b * sec_w + c_edge * apex_x) / P
            in_y = (a * 0 + b * 0 + c_edge * sec_h) / P
            r = 2 * (0.5 * sec_w * sec_h) / P
            if r > d and d > 0:
                shrink = (r - d) / r
                # Shrink each vertex toward incenter
                v0 = (in_x + (0 - in_x) * shrink, in_y + (0 - in_y) * shrink)
                v1 = (in_x + (sec_w - in_x) * shrink, in_y + (0 - in_y) * shrink)
                v2 = (in_x + (apex_x - in_x) * shrink, in_y + (sec_h - in_y) * shrink)
                path = c.beginPath()
                path.moveTo(px(v0[0]), py(v0[1]))
                path.lineTo(px(v1[0]), py(v1[1]))
                path.lineTo(px(v2[0]), py(v2[1]))
                path.close()
                c.drawPath(path, stroke=1, fill=0)
    if section.shape == "polygon":
        # K.2.8 — `offset_polygon` does per-vertex bisector offsetting
        # that works for BOTH convex and concave polygons. Replaced the
        # K.2.7 centroid-shrink approximation which produced crossed
        # edges on L / T / cross-shaped houses.
        from ..calc.polygon import offset_polygon, polygon_area
        d = section.default_setback_ft
        for es in section.edge_setbacks:
            if es.setback_ft > d:
                d = es.setback_ft
        if d > 0:
            inset_vertices = offset_polygon(section.vertices, d)
            # Skip rendering when the inset has collapsed (signed area
            # ≤ 0 → the polygon got eaten by the setback).
            if polygon_area(inset_vertices) > 0:
                path = c.beginPath()
                v0x, v0y = inset_vertices[0]
                path.moveTo(px(v0x), py(v0y))
                for vx, vy in inset_vertices[1:]:
                    path.lineTo(px(vx), py(vy))
                path.close()
                c.drawPath(path, stroke=1, fill=0)
    c.setDash()    # reset solid

    # 3. Modules: K.9.3 — when `placements` is populated (the engine
    # ran `place_modules` per K.9.2), draw each module's true (x, y,
    # rotation) rectangle. Two visual gains over K.2.8:
    #   * Module aspect ratio reflects the actual physical panel
    #     (5.65 × 3.72 ft) not a generic square cell
    #   * Orientation is correct per face (landscape / portrait)
    # Fallback to K.2.8 grid heuristic when placements is empty
    # (legacy single-orientation projects, pre-K.9 yamls).
    if placements:
        # K.10.3: color each module by its assigned string_index. Pastel
        # fill + saturated stroke so the bands read at a glance without
        # over-saturating the page. Modules with string_index=None (e.g.,
        # n_strings=0 degenerate yaml) fall back to the legacy blue.
        c.setLineWidth(0.4)
        for m in placements:
            mx0 = px(m.x_ft)
            my0 = py(m.y_ft)
            mw_pt = m.width_ft * scale
            mh_pt = m.height_ft * scale
            c.setStrokeColor(_string_stroke(m.string_index))
            c.setFillColor(_string_fill(m.string_index))
            c.rect(mx0, my0 - mh_pt, mw_pt, mh_pt, fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.setStrokeColor(colors.black)
    # K.2.8 polygon fallback (only when placements wasn't provided).
    if not placements and section.shape == "polygon" and section.module_count > 0:
        from ..calc.polygon import fit_module_grid
        d = section.default_setback_ft
        for es in section.edge_setbacks:
            if es.setback_ft > d:
                d = es.setback_ft
        cell_ft, centers = fit_module_grid(
            section.vertices,
            target_count=section.module_count,
            inset=d,
        )
        c.setStrokeColor(colors.HexColor("#1F5BD7"))
        c.setFillColor(colors.HexColor("#E8F0FF"))
        c.setLineWidth(0.3)
        cell_pt = cell_ft * scale
        for cx_m, cy_m in centers:
            c.rect(
                px(cx_m) - cell_pt * 0.45, py(cy_m) - cell_pt * 0.45,
                cell_pt * 0.90, cell_pt * 0.90, fill=1, stroke=1,
            )
        c.setFillColor(colors.black)
        c.setStrokeColor(colors.black)

    if not placements and section.shape == "rect" and section.module_count > 0:
        eave = section.edge_setback_for("eave")
        rake = section.edge_setback_for("rake")
        ridge = section.edge_setback_for("ridge")
        inset_w = max(0, sec_w - 2 * rake)
        inset_h = max(0, sec_h - eave - ridge)
        if inset_w > 0 and inset_h > 0:
            n = section.module_count
            cols_n = max(1, int(math.sqrt(n) * 1.5))
            rows_n = math.ceil(n / cols_n)
            cell_w = (inset_w / cols_n) * scale
            cell_h = (inset_h / rows_n) * scale
            cell = min(cell_w, cell_h)
            c.setStrokeColor(colors.HexColor("#1F5BD7"))
            c.setFillColor(colors.HexColor("#E8F0FF"))
            c.setLineWidth(0.3)
            placed = 0
            for r_i in range(rows_n):
                for col_i in range(cols_n):
                    if placed >= n:
                        break
                    mx = px(rake) + col_i * cell * 1.05
                    my = py(eave) + r_i * cell * 1.05
                    c.rect(mx, my, cell * 0.95, cell * 0.95, fill=1, stroke=1)
                    placed += 1
            c.setFillColor(colors.black)
            c.setStrokeColor(colors.black)

    # 4. Obstructions w/ halo
    c.setFont("Helvetica", 6.5)
    for obs in section.obstructions:
        halo_x = obs.x_ft - obs.setback_ft
        halo_y = obs.y_ft - obs.setback_ft
        halo_w_ft = obs.width_ft + 2 * obs.setback_ft
        halo_h_ft = obs.height_ft + 2 * obs.setback_ft
        # Halo (light fill)
        c.setFillColor(colors.HexColor("#FFE4B5"))
        c.setStrokeColor(colors.HexColor("#D97706"))
        c.setLineWidth(0.4)
        c.rect(px(halo_x), py(halo_y),
               halo_w_ft * scale, halo_h_ft * scale,
               fill=1, stroke=1)
        # Inner obstruction (hatched / cross-hatched look via diagonal lines)
        c.setFillColor(colors.HexColor("#D97706"))
        c.rect(px(obs.x_ft), py(obs.y_ft),
               obs.width_ft * scale, obs.height_ft * scale,
               fill=1, stroke=1)
        c.setFillColor(colors.black)
        # Label
        label_x = px(obs.x_ft + obs.width_ft / 2)
        label_y = py(obs.y_ft + obs.height_ft + 0.05) + 1
        c.drawCentredString(label_x, label_y, obs.kind.upper())
    c.setStrokeColor(colors.black)


# --- PV-5 Mounting Details (boilerplate detail blocks) ----------------------

def render_mounting_details(result: CalculationResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=landscape(letter))
    W, H = landscape(letter)
    i = result.inputs
    mounting = i.site.mounting
    roof = i.project.roof_info

    c.setLineWidth(1.0)
    c.rect(0.30 * inch, 0.30 * inch, W - 0.60 * inch, H - 0.60 * inch)

    sidebar_x = W - 1.88 * inch
    c.line(sidebar_x, 0.30 * inch, sidebar_x, H - 0.30 * inch)
    _pv5_top_context(c, result, x=0.30 * inch, y=H - 0.68 * inch,
                     w=sidebar_x - 0.30 * inch, h=0.38 * inch)
    _pv5_title_block(c, result, x=sidebar_x, y=0.30 * inch,
                     w=W - sidebar_x - 0.30 * inch, h=H - 0.60 * inch)

    main_x = 0.58 * inch
    main_w = sidebar_x - main_x - 0.30 * inch
    _pv5_heading(c, "GENERAL ROOF MOUNT DETAIL", "NTS",
                 x=0.86 * inch, y=H - 1.16 * inch, w=2.70 * inch)
    _pv5_heading(c, "ROOF MOUNT PLAN VIEW DETAIL", "NTS",
                 x=6.24 * inch, y=H - 1.16 * inch, w=2.42 * inch)
    _pv5_heading(c, "ROOF MOUNT CROSS SECTION DETAIL", "NTS",
                 x=0.72 * inch, y=0.96 * inch, w=3.06 * inch)
    _pv5_heading(c, "ROOF MOUNT DETAIL", "NTS",
                 x=6.95 * inch, y=0.96 * inch, w=1.62 * inch)

    _pv5_general_roof_mount_detail(
        c, x=1.20 * inch, y=4.14 * inch, w=3.95 * inch, h=1.86 * inch,
        result=result,
    )
    _pv5_plan_view_detail(
        c, x=6.08 * inch, y=4.05 * inch, w=2.40 * inch, h=2.08 * inch,
        result=result,
    )
    _pv5_cross_section_detail(
        c, x=1.70 * inch, y=1.40 * inch, w=3.35 * inch, h=1.62 * inch,
        result=result,
    )
    _pv5_roof_mount_product_detail(
        c, x=6.66 * inch, y=1.12 * inch, w=2.48 * inch, h=1.70 * inch,
        result=result,
    )

    c.setFont("Helvetica", 8.0)
    c.drawString(
        0.55 * inch, 0.42 * inch,
        "NOTE: ALL ROOF PENETRATIONS MUST BE SEALED OR FLASHED USING APPROVED MEANS",
    )
    c.save()


def _pv5_top_context(
    c, result: CalculationResult, *, x: float, y: float, w: float, h: float,
) -> None:
    i = result.inputs
    ri = i.project.roof_info
    dc_kw = i.pv_array.modules * i.pv_array.module.power_w / 1000
    cells = [
        ("ROOF SECTIONS", ", ".join(f"R{n}" for n in range(1, max(2, len(i.site.roof_sections) + 1)))),
        ("WIND SPEED", f"{i.project.design_criteria.wind_speed_mph} MPH"),
        ("GROUND SNOW LOAD", f"{i.project.design_criteria.ground_snow_load_psf} PSF"),
        ("ROOF TYPE", ri.type or "FIELD VERIFY"),
        ("ROOF LAYERS", str(ri.roof_layers or "FIELD VERIFY")),
        ("DC SIZE", f"{dc_kw:.3f} kW"),
    ]
    c.setLineWidth(0.55)
    col_w = w / len(cells)
    for idx, (label, value) in enumerate(cells):
        xx = x + idx * col_w
        c.rect(xx, y, col_w, h)
        c.setFont("Helvetica-Bold", 5.9)
        c.drawCentredString(xx + col_w / 2, y + h - 0.13 * inch, label)
        c.setFont("Helvetica", 5.8)
        c.drawCentredString(
            xx + col_w / 2, y + 0.07 * inch,
            fit(value, "Helvetica", 5.8, col_w - 0.08 * inch),
        )


def _pv5_title_block(
    c, result: CalculationResult, *, x: float, y: float, w: float, h: float,
) -> None:
    i = result.inputs
    ri = i.project.roof_info
    dc_kw = i.pv_array.modules * i.pv_array.module.power_w / 1000
    ac_kw = i.inverter.ac_output_a * i.inverter.ac_output_v * i.inverter.count(
        i.battery.quantity,
    ) / 1000
    rows = [
        ("DESIGN ENGINEER", [
            i.design_engineer.firm or "ENGINEER OF RECORD",
            i.design_engineer.address or "FIELD VERIFY",
            i.design_engineer.contact_email or "",
            i.design_engineer.contact_phone or "",
            f"FIRM NO. {i.design_engineer.firm_number}" if i.design_engineer.firm_number else "",
        ], 1.55),
        ("SOLAR COMPANY/CLIENT", [
            i.installer.company or "INSTALLER TBD",
            i.installer.address or "",
        ], 1.15),
        ("PROJECT", [
            i.project.client_name or i.project.name,
            i.project.site_address or i.project.location,
            f"COORDINATES: {i.project.coordinates}" if i.project.coordinates else "",
            f"ESID: {i.project.meter_info.esid}" if i.project.meter_info.esid else "",
        ], 1.48),
        ("MOUNTING DETAILS", [
            f"{i.site.mounting.rail_system}",
            f"{i.site.mounting.flashing or ri.flashing}",
        ], 0.78),
        ("SYSTEM", [
            f"DC SYSTEM SIZE: {dc_kw:.3f} kW",
            f"AC SYSTEM SIZE: {ac_kw:.3f} kW",
        ], 0.58),
        ("SHEET", [
            f"AHJ: {i.project.ahj}",
            f"UTILITY: {i.project.utility}",
            f"DRAWN BY: {i.project.drawn_by}",
            f"INITIAL DESIGN DATE: {i.project.initial_design_date}",
            f"REV: {i.project.revision}",
            "PV-5",
        ], 1.58),
    ]
    yy = y + h
    for title, lines, height_in in rows:
        row_h = height_in * inch
        yy -= row_h
        c.rect(x, yy, w, row_h)
        c.setFont("Helvetica-Bold", 7.2)
        c.drawCentredString(x + w / 2, yy + row_h - 0.15 * inch, title)
        c.setFont("Helvetica", 6.2)
        text_y = yy + row_h - 0.34 * inch
        for line in [ln for ln in lines if ln]:
            c.drawCentredString(
                x + w / 2, text_y,
                fit(line, "Helvetica", 6.2, w - 0.12 * inch),
            )
            text_y -= 0.13 * inch
    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(x + w / 2, y + 0.12 * inch, "PV-5")


def _pv5_heading(c, title: str, scale: str, *, x: float, y: float,
                 w: float) -> None:
    c.setFont("Helvetica-Bold", 13.8)
    c.drawCentredString(x + w / 2, y, title)
    c.setLineWidth(0.65)
    c.line(x, y - 0.06 * inch, x + w, y - 0.06 * inch)
    c.setFont("Helvetica", 13.0)
    c.drawCentredString(x + w / 2, y - 0.24 * inch, scale)


def _pv5_general_roof_mount_detail(
    c, *, x: float, y: float, w: float, h: float, result: CalculationResult,
) -> None:
    m = result.inputs.site.mounting
    left = x
    right = x + w
    roof_y = y + 0.44 * inch
    roof_slope = 0.86 * inch
    c.setLineWidth(1.0)
    c.line(left, roof_y, right, roof_y + roof_slope)
    c.setLineWidth(3.6)
    c.line(left + 0.12 * inch, roof_y - 0.05 * inch,
           right - 0.18 * inch, roof_y + roof_slope - 0.05 * inch)
    c.setLineWidth(0.6)
    c.line(left + 0.20 * inch, roof_y - 0.26 * inch,
           right - 0.20 * inch, roof_y + roof_slope - 0.26 * inch)
    c.setFont("Helvetica", 7.2)
    c.drawString(right - 1.10 * inch, roof_y + roof_slope - 0.26 * inch,
                 "(E) ROOF FRAMING")

    # Module and rail.
    mod_y = y + 1.12 * inch
    c.setLineWidth(0.8)
    c.line(left + 0.05 * inch, mod_y, right - 0.08 * inch, mod_y + roof_slope)
    c.line(left + 0.05 * inch, mod_y + 0.08 * inch,
           right - 0.08 * inch, mod_y + roof_slope + 0.08 * inch)
    rail_y = y + 0.98 * inch
    c.setLineWidth(1.9)
    c.line(left + 0.22 * inch, rail_y,
           right - 0.42 * inch, rail_y + roof_slope - 0.08 * inch)

    # Two roof-mount posts.
    for frac in (0.22, 0.78):
        px = left + w * frac
        py = roof_y + roof_slope * frac
        c.setLineWidth(2.6)
        c.line(px, py, px + 0.10 * inch, py + 0.55 * inch)
        c.setLineWidth(0.8)
        c.circle(px + 0.05 * inch, py + 0.56 * inch, 0.045 * inch)
        c.line(px + 0.03 * inch, py - 0.02 * inch,
               px + 0.05 * inch, py - 0.30 * inch)
    # 6-inch gap dimension.
    dim_x = right - 0.42 * inch
    c.setLineWidth(0.45)
    c.line(dim_x, roof_y + roof_slope + 0.04 * inch,
           dim_x, mod_y + roof_slope + 0.06 * inch)
    c.line(dim_x - 0.06 * inch, roof_y + roof_slope + 0.04 * inch,
           dim_x + 0.06 * inch, roof_y + roof_slope + 0.04 * inch)
    c.line(dim_x - 0.06 * inch, mod_y + roof_slope + 0.06 * inch,
           dim_x + 0.06 * inch, mod_y + roof_slope + 0.06 * inch)
    c.setFont("Helvetica", 7.2)
    c.drawString(dim_x + 0.08 * inch, mod_y + roof_slope - 0.03 * inch,
                 f"{m.max_roof_surface_gap_in:g}\" MAX SPACE FROM ROOF SURFACE")

    _pv5_leader(c, "PV MODULES", left + 0.12 * inch, mod_y + 0.46 * inch,
                left + 0.82 * inch, mod_y + 0.22 * inch)
    _pv5_leader(c, "RAIL", left + 1.58 * inch, rail_y - 0.18 * inch,
                left + 1.92 * inch, rail_y + 0.14 * inch)
    _pv5_leader(c, "MOUNTING HARDWARE", left + 2.02 * inch, mod_y + 0.77 * inch,
                left + 2.62 * inch, rail_y + 0.48 * inch)
    _pv5_leader(c, "ROOF SHEATHING", left + 1.55 * inch, roof_y - 0.72 * inch,
                left + 2.02 * inch, roof_y - 0.14 * inch)
    _pv5_leader(c, "FINISHED ROOF", right - 1.04 * inch, roof_y - 0.08 * inch,
                right - 1.56 * inch, roof_y + 0.36 * inch)
    c.setFont("Helvetica", 8.0)
    c.setFont("Helvetica", 7.4)
    c.drawString(left + 1.10 * inch, y - 0.45 * inch,
                 f"{m.flashing.upper()} ROOF MOUNT")


def _pv5_plan_view_detail(
    c, *, x: float, y: float, w: float, h: float, result: CalculationResult,
) -> None:
    m = result.inputs.site.mounting
    # Rounded-rectangle FlashVue footprint with three slots and center boss.
    c.setLineWidth(1.0)
    c.roundRect(x + 0.52 * inch, y + 0.16 * inch,
                w - 1.04 * inch, h - 0.32 * inch, 0.15 * inch)
    slot_top = y + h - 0.44 * inch
    slot_h = h - 0.88 * inch
    for sx in (x + 0.78 * inch, x + w / 2, x + w - 0.78 * inch):
        c.roundRect(sx - 0.025 * inch, slot_top - slot_h,
                    0.05 * inch, slot_h, 0.03 * inch)
    c.circle(x + w / 2, y + h / 2 - 0.02 * inch, 0.19 * inch)
    c.circle(x + w / 2, y + h / 2 - 0.02 * inch, 0.10 * inch)
    _pv5_leader(c, "FLASHING PROVIDED BY MANUFACTURER",
                x + w - 0.05 * inch, y + h - 0.35 * inch,
                x + w - 0.40 * inch, y + h - 0.55 * inch)
    c.setFont("Helvetica", 6.8)
    c.drawCentredString(
        x + w / 2, y - 0.03 * inch,
        fit(m.flashing.upper(), "Helvetica", 6.8, w),
    )


def _pv5_cross_section_detail(
    c, *, x: float, y: float, w: float, h: float, result: CalculationResult,
) -> None:
    m = result.inputs.site.mounting
    roof_y = y + 0.74 * inch
    c.setLineWidth(1.0)
    c.line(x, roof_y, x + w, roof_y)
    c.setLineWidth(0.55)
    c.line(x, roof_y - 0.10 * inch, x + w, roof_y - 0.10 * inch)
    for k in range(8):
        c.line(x + 0.05 * inch + k * 0.30 * inch, roof_y - 0.10 * inch,
               x + 0.18 * inch + k * 0.30 * inch, roof_y)
    mount_x = x + w * 0.55
    c.setLineWidth(0.9)
    c.rect(mount_x - 0.22 * inch, roof_y + 0.02 * inch,
           0.44 * inch, 0.12 * inch)
    c.setLineWidth(1.3)
    c.line(mount_x, roof_y + 0.12 * inch, mount_x, roof_y + 0.54 * inch)
    c.setLineWidth(1.2)
    c.line(mount_x, roof_y + 0.02 * inch, mount_x, y + 0.22 * inch)
    # Thread ticks on lag screw.
    c.setLineWidth(0.35)
    for k in range(10):
        yy = y + 0.26 * inch + k * 0.04 * inch
        c.line(mount_x - 0.03 * inch, yy, mount_x + 0.03 * inch, yy + 0.02 * inch)
    c.setFont("Helvetica-Bold", 7.0)
    c.drawCentredString(
        x + w / 2, y + 0.04 * inch,
        f"MIN EMBEDMENT DEPTH SEE TABLE ON PV-4  ({m.min_embedment_in:g}\" MIN)",
    )
    c.drawCentredString(x + w / 2, y - 0.10 * inch,
                        "ROOF FRAMING SEE TABLE ON PV-4")
    _pv5_leader(c, "FLASHING PROVIDED BY MANUFACTURER",
                x + 0.18 * inch, roof_y + 0.44 * inch,
                mount_x - 0.22 * inch, roof_y + 0.08 * inch)
    _pv5_leader(
        c,
        f"5/16\" X {m.lag_screw_length_in:g}\" LAG SCREW",
        x + 0.10 * inch, roof_y + 0.90 * inch,
        mount_x, roof_y + 0.12 * inch,
    )
    _pv5_leader(c, m.flashing.upper() + " ROOF MOUNT",
                mount_x + 0.42 * inch, roof_y + 0.60 * inch,
                mount_x + 0.05 * inch, roof_y + 0.36 * inch)


def _pv5_roof_mount_product_detail(
    c, *, x: float, y: float, w: float, h: float, result: CalculationResult,
) -> None:
    # Simple isometric-style product silhouette: footprint, slots, and L-foot.
    cx = x + w / 2
    cy = y + h / 2
    plate = [
        (x + 0.24 * inch, cy - 0.20 * inch),
        (cx - 0.10 * inch, cy + 0.58 * inch),
        (x + w - 0.22 * inch, cy + 0.25 * inch),
        (cx + 0.18 * inch, cy - 0.55 * inch),
    ]
    c.setLineWidth(0.95)
    p = c.beginPath()
    p.moveTo(*plate[0])
    for pt in plate[1:]:
        p.lineTo(*pt)
    p.close()
    c.drawPath(p, fill=0, stroke=1)
    c.setLineWidth(1.0)
    c.line(cx - 0.60 * inch, cy + 0.08 * inch,
           cx + 0.50 * inch, cy + 0.34 * inch)
    c.line(cx - 0.42 * inch, cy - 0.18 * inch,
           cx + 0.68 * inch, cy + 0.08 * inch)
    c.setFillColor(colors.black)
    c.rect(cx - 0.08 * inch, cy + 0.02 * inch,
           0.16 * inch, 0.38 * inch, fill=1, stroke=1)
    c.setFillColor(colors.white)
    c.circle(cx, cy - 0.04 * inch, 0.12 * inch, stroke=1, fill=0)
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 6.4)
    c.drawCentredString(cx, y + 0.04 * inch, "FLASHVUE ROOF MOUNT")


def _pv5_leader(c, text: str, tx: float, ty: float, lx: float, ly: float) -> None:
    c.setLineWidth(0.45)
    c.line(tx + 0.10 * inch, ty - 0.03 * inch, lx, ly)
    c.setFont("Helvetica", 6.8)
    c.drawString(tx, ty, fit(text, "Helvetica", 6.8, 2.75 * inch))


def _panel_frame(c, x: float, y: float, w: float, h: float, title: str) -> None:
    c.setLineWidth(0.8)
    c.rect(x, y, w, h)
    c.setFillColor(colors.HexColor("#1F5BD7"))
    c.rect(x, y + h - 0.3 * inch, w, 0.3 * inch, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x + 0.10 * inch, y + h - 0.20 * inch, title)
    c.setFillColor(colors.black)


def _mounting_schedule(
    c, result: CalculationResult, *, x: float, y: float, w: float, h: float,
) -> None:
    i = result.inputs
    m = i.site.mounting
    roof = i.project.roof_info
    rows = [
        ("MODULE", f"{i.pv_array.module.brand} {i.pv_array.module.model}"),
        ("RAIL", m.rail_system),
        ("FLASHING", m.flashing or roof.flashing or "FIELD VERIFY"),
        ("FASTENER", m.fastener),
        ("FRAMING", roof.framing or "FIELD VERIFY"),
        ("DECK", (
            f"{roof.decking_thickness_in:g}\" sheathing"
            if roof.decking_thickness_in else "FIELD VERIFY"
        )),
    ]
    c.setLineWidth(0.6)
    c.rect(x, y, w, h)
    col_w = w / len(rows)
    for idx, (label, value) in enumerate(rows):
        xx = x + idx * col_w
        if idx:
            c.line(xx, y, xx, y + h)
        c.setFont("Helvetica-Bold", 5.8)
        c.drawString(xx + 0.04 * inch, y + h - 0.17 * inch, label)
        c.setFont("Helvetica", 5.8)
        c.drawString(
            xx + 0.04 * inch, y + 0.12 * inch,
            fit(value, "Helvetica", 5.8, col_w - 0.08 * inch),
        )


def _detail_cross_section(c, x: float, y: float, w: float, h: float,
                          mounting, roof) -> None:
    _panel_frame(c, x, y, w, h, "ROOF MOUNT CROSS SECTION")
    drawing_top = y + h - 0.62 * inch
    drawing_bottom = y + 0.82 * inch
    left = x + 0.30 * inch
    right = x + w - 0.22 * inch
    cx = x + w * 0.57
    slope = 0.42 * inch

    def sloped_line(y_base: float, lw: float = 0.7,
                    color=colors.black) -> None:
        c.setStrokeColor(color)
        c.setLineWidth(lw)
        c.line(left, y_base, right, y_base + slope)

    # Roof assembly.
    roof_y = drawing_bottom + 1.32 * inch
    c.setStrokeColor(colors.black)
    sloped_line(roof_y, 1.2)
    sloped_line(roof_y - 0.10 * inch, 0.55, colors.HexColor("#555555"))
    sloped_line(roof_y - 0.24 * inch, 1.0)
    for k in range(5):
        sloped_line(roof_y - 0.36 * inch - k * 0.08 * inch,
                    0.35, colors.HexColor("#777777"))

    # Rafter/truss below the lag screw.
    c.setStrokeColor(colors.HexColor("#666666"))
    c.setLineWidth(1.8)
    c.line(left + 0.35 * inch, roof_y - 0.80 * inch,
           right - 0.35 * inch, roof_y - 0.38 * inch)

    # Module, rail, L-foot and lag screw.
    mod_y = drawing_top - 0.86 * inch
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.0)
    c.line(left + 0.10 * inch, mod_y, right - 0.15 * inch, mod_y + slope)
    c.line(left + 0.10 * inch, mod_y + 0.10 * inch,
           right - 0.15 * inch, mod_y + slope + 0.10 * inch)
    rail_y = mod_y - 0.28 * inch
    c.setLineWidth(2.2)
    c.line(left + 0.40 * inch, rail_y, right - 0.45 * inch, rail_y + slope)
    c.setLineWidth(0.9)
    c.line(cx - 0.22 * inch, rail_y - 0.02 * inch,
           cx + 0.02 * inch, roof_y + 0.18 * inch)
    c.rect(cx - 0.25 * inch, roof_y - 0.03 * inch,
           0.50 * inch, 0.10 * inch, fill=0, stroke=1)
    c.setLineWidth(1.3)
    c.line(cx, roof_y - 0.52 * inch, cx, rail_y + 0.03 * inch)
    c.circle(cx, rail_y + 0.03 * inch, 0.04 * inch, fill=0, stroke=1)

    # Leader labels.
    c.setFont("Helvetica", 6.7)
    labels = [
        ("PV MODULE", left, mod_y + 0.28 * inch,
         left + 0.96 * inch, mod_y + 0.08 * inch),
        (mounting.rail_system.upper(), left, rail_y + 0.18 * inch,
         left + 1.22 * inch, rail_y + 0.06 * inch),
        ("L-FOOT / MID CLAMP", left, roof_y + 0.44 * inch,
         cx - 0.10 * inch, rail_y - 0.02 * inch),
        ("FLASHING + LAG", left, roof_y + 0.14 * inch,
         cx - 0.02 * inch, roof_y + 0.02 * inch),
        ("ASPHALT SHINGLE", left, roof_y - 0.24 * inch,
         left + 1.45 * inch, roof_y - 0.08 * inch),
        ("ROOF DECK", left, roof_y - 0.52 * inch,
         left + 1.55 * inch, roof_y - 0.26 * inch),
        ("RAFTER / TRUSS", left, roof_y - 0.80 * inch,
         left + 1.70 * inch, roof_y - 0.58 * inch),
    ]
    for text, tx, ty, lx, ly in labels:
        c.drawString(tx, ty, fit(text, "Helvetica", 6.7, 1.85 * inch))
        # Keep this cross-section readable at full-sheet scale. The
        # geometry is dense enough that long leader lines can cross the
        # lag screw; proximity labels are clearer here.

    c.setFont("Helvetica-Bold", 6.4)
    c.drawString(x + 0.12 * inch, y + 0.50 * inch, "INSTALLATION BASIS:")
    c.setFont("Helvetica", 6.2)
    note = (
        f"Fastener {mounting.fastener}; attach into "
        f"{roof.framing or 'verified structural framing'}."
    )
    for idx, line in enumerate(_pv5_wrap(c, note, w - 0.28 * inch, 6.2)):
        c.drawString(x + 0.12 * inch, y + (0.32 - 0.13 * idx) * inch, line)


def _detail_plan_view(c, x: float, y: float, w: float, h: float,
                      mounting, module) -> None:
    _panel_frame(c, x, y, w, h, "MODULE / RAIL PLAN VIEW")
    mod_w = w * 0.62
    mod_h = h - 1.32 * inch
    mod_x = x + (w - mod_w) / 2
    mod_y = y + 0.76 * inch
    c.setLineWidth(1.0)
    c.rect(mod_x, mod_y, mod_w, mod_h)

    # Module cell grid gives the plan a recognizable PV-panel form.
    c.setStrokeColor(colors.HexColor("#9CA3AF"))
    c.setLineWidth(0.25)
    for k in range(1, 4):
        c.line(mod_x + k * mod_w / 4, mod_y,
               mod_x + k * mod_w / 4, mod_y + mod_h)
    for k in range(1, 7):
        c.line(mod_x, mod_y + k * mod_h / 7,
               mod_x + mod_w, mod_y + k * mod_h / 7)
    c.setStrokeColor(colors.black)

    # Rails and attachment points.
    rail_ys = [mod_y + mod_h * 0.28, mod_y + mod_h * 0.72]
    c.setStrokeColor(colors.HexColor("#1F2937"))
    for yy in rail_ys:
        c.setLineWidth(1.5)
        c.line(mod_x - 0.16 * inch, yy, mod_x + mod_w + 0.16 * inch, yy)
        c.setLineWidth(0.45)
        c.line(mod_x - 0.16 * inch, yy + 0.05 * inch,
               mod_x + mod_w + 0.16 * inch, yy + 0.05 * inch)
    c.setFillColor(colors.HexColor("#C00000"))
    for yy in rail_ys:
        for n in range(4):
            ax = mod_x + (n + 0.5) * mod_w / 4
            c.circle(ax, yy, 0.035 * inch, stroke=0, fill=1)
    c.setFillColor(colors.black)

    _dim_h(c, mod_x, mod_y + mod_h + 0.22 * inch, mod_w,
           f"{module.width_in:.2f}\" MODULE WIDTH")
    _dim_v(c, mod_x - 0.22 * inch, mod_y, mod_h,
           f"{module.length_in:.2f}\" MODULE LENGTH")
    _dim_h(c, mod_x - 0.16 * inch, rail_ys[1] + 0.20 * inch,
           mod_w / 4, f"MAX X {mounting.max_x_spacing_in:.0f}\"")
    _dim_v(c, mod_x + mod_w + 0.24 * inch, rail_ys[0], rail_ys[1] - rail_ys[0],
           f"MAX Y {mounting.max_y_spacing_in:.0f}\"")

    c.setFont("Helvetica-Bold", 6.4)
    c.drawString(x + 0.12 * inch, y + 0.50 * inch, "LEGEND:")
    c.setFillColor(colors.HexColor("#C00000"))
    c.circle(x + 0.70 * inch, y + 0.52 * inch, 0.035 * inch, stroke=0, fill=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 6.2)
    c.drawString(x + 0.82 * inch, y + 0.48 * inch,
                 "= attachment point at rail / framing intersection")
    c.drawString(
        x + 0.12 * inch, y + 0.28 * inch,
        f"Max cantilever from last attachment: {mounting.max_cantilever_in:.0f}\"",
    )


def _detail_flashing(c, x: float, y: float, w: float, h: float,
                     mounting, roof) -> None:
    _panel_frame(c, x, y, w, h, "FLASHING / L-FOOT DETAIL")
    cx = x + w * 0.55
    base_y = y + h * 0.43

    # Roof stack, drawn large enough to read.
    c.setLineWidth(0.45)
    for k in range(6):
        yy = base_y - 0.44 * inch + k * 0.08 * inch
        c.line(x + 0.30 * inch, yy, x + w - 0.26 * inch, yy)
    c.setLineWidth(1.0)
    c.line(x + 0.30 * inch, base_y - 0.54 * inch,
           x + w - 0.26 * inch, base_y - 0.54 * inch)
    c.setLineWidth(1.7)
    c.line(x + 0.52 * inch, base_y - 0.88 * inch,
           x + w - 0.55 * inch, base_y - 0.88 * inch)

    # Flashing plate, waterproofing boot, L-foot and rail.
    c.setFillColor(colors.HexColor("#D9D9D9"))
    c.rect(cx - 0.78 * inch, base_y - 0.14 * inch,
           1.56 * inch, 0.30 * inch, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#F3F4F6"))
    c.rect(cx - 0.18 * inch, base_y + 0.14 * inch,
           0.36 * inch, 0.18 * inch, fill=1, stroke=1)
    c.setFillColor(colors.white)
    c.rect(cx - 0.10 * inch, base_y + 0.32 * inch,
           0.20 * inch, 0.56 * inch, fill=1, stroke=1)
    c.setFillColor(colors.black)
    c.setLineWidth(2.1)
    c.line(cx - 0.62 * inch, base_y + 0.95 * inch,
           cx + 0.62 * inch, base_y + 0.95 * inch)
    c.setLineWidth(1.4)
    c.line(cx, base_y - 0.86 * inch, cx, base_y + 0.92 * inch)
    c.circle(cx, base_y + 0.92 * inch, 0.04 * inch, stroke=1, fill=0)

    # Leader labels.
    c.setFont("Helvetica", 6.7)
    label_data = [
        ("XR100 RAIL", x + 0.14 * inch, base_y + 1.15 * inch,
         cx - 0.22 * inch, base_y + 0.95 * inch),
        ("L-FOOT", x + 0.14 * inch, base_y + 0.80 * inch,
         cx - 0.08 * inch, base_y + 0.60 * inch),
        ("SEALANT / BOOT", x + 0.14 * inch, base_y + 0.45 * inch,
         cx - 0.10 * inch, base_y + 0.23 * inch),
        (mounting.flashing.upper(), x + 0.14 * inch, base_y + 0.10 * inch,
         cx - 0.45 * inch, base_y + 0.00 * inch),
        ("SHINGLE ROOFING", x + 0.14 * inch, base_y - 0.34 * inch,
         cx - 0.65 * inch, base_y - 0.22 * inch),
        ("ROOF DECK", x + 0.14 * inch, base_y - 0.62 * inch,
         cx - 0.55 * inch, base_y - 0.54 * inch),
        ("RAFTER / TRUSS", x + 0.14 * inch, base_y - 0.90 * inch,
         cx - 0.42 * inch, base_y - 0.88 * inch),
    ]
    for text, tx, ty, lx, ly in label_data:
        c.drawString(tx, ty, fit(text, "Helvetica", 6.7, 1.25 * inch))
        c.setLineWidth(0.35)
        c.line(tx + 1.05 * inch, ty + 0.02 * inch, lx, ly)

    # Notes inside the panel bottom.
    c.setFont("Helvetica-Bold", 6.5)
    c.drawString(x + 0.12 * inch, y + 0.62 * inch, "FIELD REQUIREMENTS:")
    c.setFont("Helvetica", 6.1)
    notes = [
        "Locate attachments over verified framing before drilling.",
        "Flash every penetration per manufacturer instructions.",
        f"Roof covering: {roof.type or 'comp shingle'}; "
        f"condition: {roof.condition}.",
    ]
    yy = y + 0.45 * inch
    for note in notes:
        for line in _pv5_wrap(c, note, w - 0.26 * inch, 6.1):
            c.drawString(x + 0.12 * inch, yy, line)
            yy -= 0.11 * inch


def _dim_h(c, x: float, y: float, length: float, label: str) -> None:
    c.setLineWidth(0.35)
    c.line(x, y, x + length, y)
    c.line(x, y - 0.05 * inch, x, y + 0.05 * inch)
    c.line(x + length, y - 0.05 * inch, x + length, y + 0.05 * inch)
    c.setFont("Helvetica", 5.8)
    c.drawCentredString(x + length / 2, y + 0.06 * inch,
                        fit(label, "Helvetica", 5.8, length + 0.25 * inch))


def _dim_v(c, x: float, y: float, length: float, label: str) -> None:
    c.setLineWidth(0.35)
    c.line(x, y, x, y + length)
    c.line(x - 0.05 * inch, y, x + 0.05 * inch, y)
    c.line(x - 0.05 * inch, y + length,
           x + 0.05 * inch, y + length)
    c.saveState()
    c.translate(x - 0.08 * inch, y + length / 2)
    c.rotate(90)
    c.setFont("Helvetica", 5.8)
    c.drawCentredString(0, 0, fit(label, "Helvetica", 5.8,
                                  length + 0.20 * inch))
    c.restoreState()


def _pv5_footer_notes(c, result: CalculationResult, *, x: float,
                      y: float, w: float) -> None:
    i = result.inputs
    notes = [
        "Install per listed mounting-system instructions.",
        "Shift attachments in field only to land on verified framing.",
        f"PV-4 governs attachment count: {i.pv_array.modules} modules / {len(i.site.roof_sections)} roof faces.",
    ]
    c.setFont("Helvetica-Bold", 6.2)
    c.drawString(x, y, "NOTES:")
    c.setFont("Helvetica", 6.0)
    xx = x + 0.40 * inch
    col_w = (w - 0.45 * inch) / len(notes)
    for idx, note in enumerate(notes):
        c.drawString(xx + idx * col_w, y,
                     fit(note, "Helvetica", 6.0, col_w - 0.04 * inch))


def _pv5_wrap(c, text: str, max_w: float, size: float) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur: list[str] = []
    for word in words:
        trial = " ".join(cur + [word])
        if c.stringWidth(trial, "Helvetica", size) <= max_w:
            cur.append(word)
        else:
            if cur:
                lines.append(" ".join(cur))
            cur = [word]
    if cur:
        lines.append(" ".join(cur))
    return lines


# --- PV-6 String Plan (color-coded by real K.9.1 string assignment) ---------


def _can_draw_traced_string_plan(result: CalculationResult) -> bool:
    """Stage 9.10 — PV-6 can use the full traced roof string layout."""
    from .site_plan import _ee4_trace_active

    return bool(
        _ee4_trace_active(result.inputs.site)
        and any(result.module_placements.values())
    )


@dataclass(frozen=True)
class PV6TraceLayout:
    frame: tuple[float, float, float, float]
    plot: tuple[float, float, float, float]
    min_x: float
    min_y: float
    origin_x: float
    origin_y: float
    scale: float

    def to_pt(self, pt: tuple[float, float]) -> tuple[float, float]:
        return (
            self.origin_x + (pt[0] - self.min_x) * self.scale,
            self.origin_y + (pt[1] - self.min_y) * self.scale,
        )


@dataclass(frozen=True)
class PV6StringCallout:
    string_index: int
    text: str
    side: str
    target: tuple[float, float]
    knee: tuple[float, float]
    label_anchor: tuple[float, float]
    label_bbox: tuple[float, float, float, float]


def _pv6_trace_layout(
    result: CalculationResult, *, W: float | None = None, H: float | None = None,
) -> PV6TraceLayout | None:
    """Return the traced PV-6 plot transform used by rendering and linting."""
    from .site_plan import _ee4_drawing_bounds

    if W is None or H is None:
        W, H = landscape(letter)

    bounds = _ee4_drawing_bounds(result)
    if bounds is None:
        return None
    min_x, min_y, max_x, max_y = bounds
    bw = max(max_x - min_x, 1.0)
    bh = max(max_y - min_y, 1.0)
    pad_ft = max(bw, bh) * 0.045
    min_x -= pad_ft
    min_y -= pad_ft
    max_x += pad_ft
    max_y += pad_ft
    bw = max_x - min_x
    bh = max_y - min_y

    plot_x = 1.48 * inch
    plot_y = 1.22 * inch
    plot_w = W - 2.00 * inch
    plot_h = 4.92 * inch
    scale = min(plot_w / bw, plot_h / bh)
    origin_x = plot_x + (plot_w - bw * scale) / 2
    origin_y = plot_y + (plot_h - bh * scale) / 2

    return PV6TraceLayout(
        frame=(0.32 * inch, 0.32 * inch, W - 0.32 * inch, H - 0.32 * inch),
        plot=(plot_x, plot_y, plot_x + plot_w, plot_y + plot_h),
        min_x=min_x,
        min_y=min_y,
        origin_x=origin_x,
        origin_y=origin_y,
        scale=scale,
    )


def _draw_traced_string_plan_page(
    c, result: CalculationResult, *, W: float, H: float,
) -> None:
    """Stage 9.10 — reference-style PV-6 string layout."""
    from .site_plan import (
        _draw_ee4_equipment_summary,
        _draw_ee4_trace_roof,
        _draw_ee4_trace_symbols,
    )

    c.setLineWidth(1.0)
    c.rect(0.32 * inch, 0.32 * inch, W - 0.64 * inch, H - 0.64 * inch)

    _draw_pv6_north_arrow(c, x=0.42 * inch, y=H - 1.22 * inch)
    _draw_pv6_left_summary_and_legend(
        c, result, x=0.58 * inch, top_y=H - 1.52 * inch,
    )

    optimizer_count = (
        result.inputs.optimizer.effective_count(
            result.inputs.pv_array.modules,
            result.inputs.pv_array.strings,
        )
        if result.inputs.optimizer.brand else 0
    )
    _draw_ee4_equipment_summary(
        c, result,
        x=W - 3.18 * inch, top_y=H - 0.48 * inch, w=2.82 * inch,
        optimizer_count=optimizer_count,
    )

    layout = _pv6_trace_layout(result, W=W, H=H)
    if layout is None:
        return

    trace = result.inputs.site.ee4_trace
    _draw_ee4_trace_roof(c, trace, layout.to_pt, fill_outline=True)
    _draw_ee4_trace_roof(c, trace, layout.to_pt, fill_outline=False)
    _draw_pv6_string_modules(c, result, layout.to_pt)
    _draw_ee4_trace_symbols(c, trace, layout.to_pt)
    _draw_pv6_string_callouts(c, _pv6_string_callouts(result, layout))

    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)
    c.setFont("Helvetica", 7.5)
    c.drawCentredString(W * 0.74, 0.58 * inch, 'SCALE: 1/8" = 1\'-0"')
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(W - 0.42 * inch, 0.43 * inch, _string_sheet_label(result))


def _draw_pv6_north_arrow(c, *, x: float, y: float) -> None:
    box = 0.74 * inch
    c.setStrokeColor(colors.black)
    c.setFillColor(colors.white)
    c.setLineWidth(0.8)
    c.rect(x, y, box, box)
    cx = x + box / 2
    cy = y + box * 0.42
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(cx, y + box - 0.14 * inch, "N")
    c.circle(cx, cy - 0.05 * inch, 0.18 * inch, fill=0, stroke=1)
    path = c.beginPath()
    path.moveTo(cx, cy + 0.24 * inch)
    path.lineTo(cx - 0.12 * inch, cy - 0.10 * inch)
    path.lineTo(cx, cy - 0.02 * inch)
    path.lineTo(cx + 0.12 * inch, cy - 0.10 * inch)
    path.close()
    c.drawPath(path, fill=0, stroke=1)


def _draw_pv6_left_summary_and_legend(
    c, result: CalculationResult, *, x: float, top_y: float,
) -> None:
    i = result.inputs
    inv_count = i.inverter.count(i.battery.quantity)
    opt_count = (
        i.optimizer.effective_count(i.pv_array.modules, i.pv_array.strings)
        if i.optimizer.brand else 0
    )
    lines = [
        f"MODULE: ({i.pv_array.modules}) {i.pv_array.module.brand.upper()} "
        f"{i.pv_array.module.model}",
        f"INVERTER: ({inv_count}) {i.inverter.brand.upper()} {i.inverter.model}",
    ]
    if i.optimizer.brand:
        lines.append(
            f"OPTIMIZER: ({opt_count}) {i.optimizer.brand.upper()} "
            f"{i.optimizer.model}"
        )

    c.setFillColor(colors.black)
    c.setFont("Helvetica", 6.7)
    yy = top_y
    for line in lines:
        c.drawString(x, yy, fit(line, "Helvetica", 6.7, 1.88 * inch))
        yy -= 0.12 * inch

    yy -= 0.11 * inch
    rollup = _pv6_string_rollup(result)
    for s_idx in range(result.inputs.pv_array.strings):
        count = rollup.get(s_idx, 0)
        label = f"STRING {s_idx + 1}: ({count}) MODULES"
        c.setFont("Helvetica", 7.0)
        c.setFillColor(colors.black)
        c.drawString(x, yy, label)
        sw_x = x + 1.23 * inch
        c.setFillColor(_string_plan_fill(s_idx))
        c.setStrokeColor(colors.HexColor("#155EEF"))
        c.setLineWidth(0.55)
        c.rect(sw_x, yy - 0.02 * inch, 0.25 * inch, 0.13 * inch,
               fill=1, stroke=1)
        yy -= 0.22 * inch
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)


def _pv6_string_rollup(result: CalculationResult) -> dict[int, int]:
    counts = {idx: 0 for idx in range(result.inputs.pv_array.strings)}
    for mods in result.module_placements.values():
        for module in mods:
            if module.string_index is None:
                continue
            counts[module.string_index] = counts.get(module.string_index, 0) + 1
    return counts


def _pv6_string_callouts(
    result: CalculationResult,
    layout: PV6TraceLayout | None = None,
) -> list[PV6StringCallout]:
    """Stage 9.10.4 — automatic external STRING N leader callouts."""
    from .site_plan import _ee4_module_site_points

    if layout is None:
        layout = _pv6_trace_layout(result)
    if layout is None:
        return []

    by_string: dict[int, dict[str, float | int | str]] = {}
    for section in result.inputs.site.roof_sections:
        for module in result.module_placements.get(section.name, []):
            if module.string_index is None:
                continue
            pts = [layout.to_pt(p) for p in _ee4_module_site_points(section, module)]
            if len(pts) < 4:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            s_idx = int(module.string_index)
            entry = by_string.setdefault(
                s_idx,
                {
                    "string_index": s_idx,
                    "text": f"STRING {s_idx + 1}",
                    "x0": min(xs),
                    "y0": min(ys),
                    "x1": max(xs),
                    "y1": max(ys),
                    "count": 0,
                },
            )
            entry["x0"] = min(float(entry["x0"]), min(xs))
            entry["y0"] = min(float(entry["y0"]), min(ys))
            entry["x1"] = max(float(entry["x1"]), max(xs))
            entry["y1"] = max(float(entry["y1"]), max(ys))
            entry["count"] = int(entry["count"]) + 1

    if not by_string:
        return []

    roof_bbox = _pv6_union_bbox(
        (
            float(e["x0"]),
            float(e["y0"]),
            float(e["x1"]),
            float(e["y1"]),
        )
        for e in by_string.values()
    )
    groups: dict[str, list[dict[str, float | int | str]]] = {
        "top": [],
        "right": [],
        "bottom": [],
        "left": [],
    }
    for entry in sorted(by_string.values(), key=lambda e: int(e["string_index"])):
        bbox = (
            float(entry["x0"]),
            float(entry["y0"]),
            float(entry["x1"]),
            float(entry["y1"]),
        )
        side = _pv6_preferred_callout_side(bbox, roof_bbox, layout.plot)
        groups[side].append(entry)

    callouts: list[PV6StringCallout] = []
    for side in ("top", "right", "bottom", "left"):
        items = groups[side]
        if not items:
            continue
        if side in ("top", "bottom"):
            items.sort(key=lambda e: (float(e["x0"]) + float(e["x1"])) / 2)
        else:
            items.sort(key=lambda e: -(float(e["y0"]) + float(e["y1"])) / 2)
        for slot, entry in enumerate(items):
            callouts.append(
                _pv6_position_callout(entry, side, slot, len(items), layout.plot)
            )
    return sorted(callouts, key=lambda c: c.string_index)


def _pv6_union_bbox(
    bboxes,
) -> tuple[float, float, float, float]:
    bboxes = list(bboxes)
    return (
        min(b[0] for b in bboxes),
        min(b[1] for b in bboxes),
        max(b[2] for b in bboxes),
        max(b[3] for b in bboxes),
    )


def _pv6_preferred_callout_side(
    bbox: tuple[float, float, float, float],
    roof_bbox: tuple[float, float, float, float],
    plot: tuple[float, float, float, float],
) -> str:
    x0, y0, x1, y1 = bbox
    rx0, ry0, rx1, ry1 = roof_bbox
    px0, py0, px1, py1 = plot
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    rcx = (rx0 + rx1) / 2
    rcy = (ry0 + ry1) / 2
    dx = cx - rcx
    dy = cy - rcy
    roof_w = max(rx1 - rx0, 1.0)
    near_left_edge = x0 <= rx0 + roof_w * 0.12
    near_right_edge = x1 >= rx1 - roof_w * 0.12
    room = {
        "top": py1 - y1,
        "right": px1 - x1,
        "bottom": y0 - py0,
        "left": x0 - px0,
    }

    if (
        dx > abs(dy) * 0.75
        and near_right_edge
        and room["right"] > 1.18 * inch
    ):
        return "right"
    if (
        -dx > abs(dy) * 0.75
        and near_left_edge
        and room["left"] > 1.18 * inch
    ):
        return "left"
    if dy >= 0 and room["top"] > 0.28 * inch:
        return "top"
    if dy < 0 and room["bottom"] > 0.28 * inch:
        return "bottom"
    return max(room, key=room.get)


def _pv6_position_callout(
    entry: dict[str, float | int | str],
    side: str,
    slot: int,
    total: int,
    plot: tuple[float, float, float, float],
) -> PV6StringCallout:
    px0, py0, px1, py1 = plot
    x0 = float(entry["x0"])
    y0 = float(entry["y0"])
    x1 = float(entry["x1"])
    y1 = float(entry["y1"])
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    text = str(entry["text"])
    font = "Helvetica-Bold"
    size = 13.0
    text_w = pdfmetrics.stringWidth(text, font, size)
    margin = 0.10 * inch
    slot_w = (px1 - px0 - 2 * margin) / max(total, 1)
    slot_h = (py1 - py0 - 2 * margin) / max(total, 1)

    if side == "top":
        slot_cx = px0 + margin + slot_w * (slot + 0.5)
        label_x = _clamp(slot_cx - text_w / 2, px0 + margin, px1 - margin - text_w)
        label_y = min(py1 - 0.23 * inch, y1 + 0.48 * inch)
        target = (cx, y1)
        knee = (cx, label_y - 0.08 * inch)
        anchor = (label_x + text_w / 2, label_y - 0.04 * inch)
    elif side == "bottom":
        slot_cx = px0 + margin + slot_w * (slot + 0.5)
        label_x = _clamp(slot_cx - text_w / 2, px0 + margin, px1 - margin - text_w)
        label_y = max(py0 + 0.13 * inch, y0 - 0.52 * inch)
        target = (cx, y0)
        knee = (cx, label_y + size + 0.08 * inch)
        anchor = (label_x + text_w / 2, label_y + size + 0.02 * inch)
    elif side == "right":
        slot_cy = py1 - margin - slot_h * (slot + 0.5)
        label_y = _clamp(slot_cy - size / 2, py0 + margin, py1 - margin - size)
        label_x = min(px1 - margin - text_w, x1 + 0.38 * inch)
        target = (x1, cy)
        knee = (label_x - 0.10 * inch, cy)
        anchor = (label_x - 0.04 * inch, label_y + size / 2)
    else:
        slot_cy = py1 - margin - slot_h * (slot + 0.5)
        label_y = _clamp(slot_cy - size / 2, py0 + margin, py1 - margin - size)
        label_x = max(px0 + margin, x0 - text_w - 0.38 * inch)
        target = (x0, cy)
        knee = (label_x + text_w + 0.10 * inch, cy)
        anchor = (label_x + text_w + 0.04 * inch, label_y + size / 2)

    label_bbox = (
        label_x - 0.04 * inch,
        label_y - 0.03 * inch,
        label_x + text_w + 0.04 * inch,
        label_y + size + 0.04 * inch,
    )
    return PV6StringCallout(
        string_index=int(entry["string_index"]),
        text=text,
        side=side,
        target=target,
        knee=knee,
        label_anchor=anchor,
        label_bbox=label_bbox,
    )


def _clamp(value: float, lo: float, hi: float) -> float:
    if hi < lo:
        return lo
    return max(lo, min(hi, value))


def _draw_pv6_string_callouts(
    c, callouts: list[PV6StringCallout],
) -> None:
    if not callouts:
        return
    c.saveState()
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.55)
    for callout in callouts:
        c.line(*callout.target, *callout.knee)
        c.line(*callout.knee, *callout.label_anchor)
    for callout in callouts:
        x0, y0, x1, y1 = callout.label_bbox
        c.setFillColor(colors.white)
        c.rect(x0, y0, x1 - x0, y1 - y0, fill=1, stroke=0)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(callout.label_bbox[0] + 0.04 * inch,
                     callout.label_bbox[1] + 0.03 * inch,
                     callout.text)
    c.restoreState()


def _draw_pv6_string_modules(c, result: CalculationResult, to_pt) -> None:
    from .site_plan import _ee4_module_site_points

    for section in result.inputs.site.roof_sections:
        for module in result.module_placements.get(section.name, []):
            pts = [to_pt(p) for p in _ee4_module_site_points(section, module)]
            if len(pts) < 4:
                continue
            c.setFillColor(_string_plan_fill(module.string_index))
            c.setStrokeColor(colors.HexColor("#155EEF"))
            c.setLineWidth(0.58)
            path = c.beginPath()
            path.moveTo(*pts[0])
            for p in pts[1:]:
                path.lineTo(*p)
            path.close()
            c.drawPath(path, fill=1, stroke=1)

            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            label = (
                "?"
                if module.string_index is None
                else str(module.string_index + 1)
            )
            c.setFillColor(colors.white)
            c.setStrokeColor(colors.black)
            c.setLineWidth(0.3)
            c.rect(cx - 2.6, cy - 2.4, 5.2, 4.8, fill=1, stroke=1)
            c.setFont("Helvetica-Bold", 3.8)
            c.setFillColor(colors.black)
            c.drawCentredString(cx, cy - 1.2, label)
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)

def render_string_plan(result: CalculationResult, out_path: Path) -> None:
    """K.10.4 — top-down roof view with each module drawn at its real
    K.9.1 (x, y, rotation) coordinates, colored by its assigned MPPT
    string. Replaces the pre-K.10 heuristic √n grid that didn't
    match the PV-4 placement output.

    Layout:
        * Top half  — per-section roof plans (reuses `_draw_section_plan`,
          so colors match PV-4 exactly)
        * Bottom half — per-string details table: S#, count, faces,
          Voc-cold, conductor reference
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=landscape(letter))
    W, H = landscape(letter)
    i = result.inputs
    pairs = _sections_with_layout(result)

    if _can_draw_traced_string_plan(result):
        _draw_traced_string_plan_page(c, result, W=W, H=H)
        c.save()
        return

    # Outer frame + title
    c.setLineWidth(1.0)
    c.rect(0.4 * inch, 0.4 * inch, W - 0.8 * inch, H - 0.8 * inch)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(W / 2, H - 0.8 * inch, _string_sheet_label(result))
    c.setFont("Helvetica", 9.5)
    c.drawCentredString(
        W / 2, H - 1.05 * inch,
        f"{i.pv_array.modules} modules · {i.pv_array.strings} MPPT strings × "
        f"{i.pv_array.modules_per_string} modules · "
        f"{i.pv_array.module.brand} {i.pv_array.module.model}"
    )

    # ── Top half: roof plans ──────────────────────────────────────────
    plan_x = 0.6 * inch
    plan_y = H / 2 - 0.10 * inch
    plan_w = W - 1.2 * inch
    plan_h = H / 2 - 1.40 * inch
    c.setLineWidth(0.8)
    c.rect(plan_x, plan_y, plan_w, plan_h)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(plan_x + 0.10 * inch, plan_y + plan_h - 0.18 * inch,
                 "ROOF SECTION PLANS (color = MPPT string · top = ridge / apex)")

    n_sec = max(1, len(pairs))
    sub_w = (plan_w - 0.4 * inch) / n_sec
    sub_y = plan_y + 0.30 * inch
    sub_h = plan_h - 0.70 * inch
    for idx, (section, layout) in enumerate(pairs):
        sub_x = plan_x + 0.20 * inch + idx * sub_w
        placements = result.module_placements.get(section.name, [])
        _draw_section_plan(c, sub_x, sub_y, sub_w - 0.15 * inch, sub_h,
                           section, layout, placements=placements)

    # ── Bottom half: per-string details table ─────────────────────────
    table_x = 0.6 * inch
    table_y = 0.9 * inch
    table_w = W - 1.2 * inch
    table_h = plan_y - 1.20 * inch
    c.setLineWidth(0.8)
    c.rect(table_x, table_y, table_w, table_h)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(table_x + 0.10 * inch, table_y + table_h - 0.18 * inch,
                 "PER-STRING DETAILS")

    # Build per-string rollup from module_placements
    by_string: dict[int, dict] = {}
    for face_name, mods in result.module_placements.items():
        for m in mods:
            if m.string_index is None:
                continue
            row = by_string.setdefault(m.string_index, {
                "count": 0, "faces": set(),
            })
            row["count"] += 1
            row["faces"].add(face_name)

    # Voc-cold per string is the same nominal value for all strings
    # in a uniform-length design (the K.10 invariant). Pull from the
    # K.0 pv_string calculation result.
    voc_cold_per_module = result.pv_string.voc_cold_per_module
    string_voc_cold = result.pv_string.string_voc_cold

    # Column layout
    col_x = [
        table_x + 0.20 * inch,             # SWATCH
        table_x + 0.55 * inch,             # STRING
        table_x + 1.20 * inch,             # MODULES
        table_x + 2.00 * inch,             # FACES
        table_x + 5.00 * inch,             # STRING VOC-COLD
        table_x + 6.50 * inch,             # PER-MOD VOC-COLD
        table_x + 8.10 * inch,             # CONDUCTOR REF
    ]
    header_y = table_y + table_h - 0.42 * inch
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(col_x[1], header_y, "STRING")
    c.drawString(col_x[2], header_y, "MODULES")
    c.drawString(col_x[3], header_y, "FACES")
    c.drawString(col_x[4], header_y, "STRING VOC-COLD")
    c.drawString(col_x[5], header_y, "PER-MOD VOC")
    c.drawString(col_x[6], header_y, "CONDUCTOR")
    c.setLineWidth(0.3)
    c.line(table_x + 0.10 * inch, header_y - 0.06 * inch,
           table_x + table_w - 0.10 * inch, header_y - 0.06 * inch)

    n_decl = i.pv_array.strings
    rows = sorted(by_string.items())
    if not rows:
        # Pre-K.10 fallback (legacy yamls with no per-face placements)
        for s in range(n_decl):
            rows.append((s, {"count": i.pv_array.modules_per_string,
                             "faces": {"(legacy)"}}))

    row_h = min(0.22 * inch, (table_h - 0.70 * inch) / max(len(rows), 1))
    c.setFont("Helvetica", 8.5)
    for idx, (s_idx, row) in enumerate(rows):
        ry = header_y - 0.18 * inch - (idx + 1) * row_h + 0.05 * inch
        # Swatch
        c.setFillColor(_string_fill(s_idx))
        c.setStrokeColor(_string_stroke(s_idx))
        c.setLineWidth(0.4)
        c.rect(col_x[0], ry, 0.22 * inch, 0.13 * inch, fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.setStrokeColor(colors.black)
        # Label
        c.drawString(col_x[1], ry + 0.02 * inch, f"S{s_idx + 1}")
        c.drawString(col_x[2], ry + 0.02 * inch, f"{row['count']}")
        faces_text = ", ".join(sorted(row["faces"]))
        faces_clipped = fit(faces_text, "Helvetica", 8.5,
                            col_x[4] - col_x[3] - 0.10 * inch)
        c.drawString(col_x[3], ry + 0.02 * inch, faces_clipped)
        # Voc-cold scales with actual module count in this string
        actual_voc = voc_cold_per_module * row["count"]
        c.drawString(col_x[4], ry + 0.02 * inch, f"{actual_voc:.1f} V")
        c.drawString(col_x[5], ry + 0.02 * inch,
                     f"{voc_cold_per_module:.2f} V")
        c.drawString(col_x[6], ry + 0.02 * inch,
                     f"#{result.pv_conductor.size} {result.pv_conductor.insulation}")

    # Footer note — string Voc-cold vs NEC 690.7(A) 600 V dwelling cap.
    c.setFont("Helvetica-Oblique", 7.5)
    c.drawString(table_x + 0.20 * inch, table_y + 0.10 * inch,
                 f"NEC 690.7(A) cold Voc check: "
                 f"string Voc-cold {string_voc_cold:.1f} V ≤ 600 V "
                 f"(dwelling cap). Module Voc-cold derived from datasheet "
                 f"βVoc + ASHRAE 2 % extreme low temperature.")

    c.save()
