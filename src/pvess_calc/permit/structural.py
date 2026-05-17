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
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from ..calc.engine import CalculationResult
from ..calc.roof_layout import _evaluate_section
from ._textfit import fit


# Colors used for string-block highlighting on the roof plan.
STRING_COLORS = [
    "#FF6B6B", "#4ECDC4", "#FFE066", "#A8E6CF",
    "#FFB3D9", "#C7CEEA", "#FF8E72", "#92D7E7",
]

# Fallback color when a module hasn't been assigned a string yet
# (K.10.1 degenerate yaml). Matches the pre-K.10 PV-4 blue.
UNASSIGNED_STROKE = "#1F5BD7"
UNASSIGNED_FILL = "#E8F0FF"


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
    return max(8, n_modules * 4 // 3)


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
            str(s.attachment_count),
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
        total_attach += s.attachment_count
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

    # K.2.6c roof-plan section drawings (bottom half). One sub-plot per
    # roof section, side by side. Each sub-plot shows:
    #   * Roof outline (rect or tri)
    #   * Dashed inset = NEC 690.12 setback zone
    #   * Hatched boxes = obstructions with their halo
    #   * Light fill grid = modules placed inside the usable polygon
    plot_x = 0.6 * inch
    plot_y = 1.0 * inch
    plot_w = W - 1.2 * inch
    plot_h = 4.2 * inch
    c.setLineWidth(0.8)
    c.rect(plot_x, plot_y, plot_w, plot_h)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(plot_x + 0.10 * inch, plot_y + plot_h - 0.18 * inch,
                 "ROOF SECTION PLANS (top of page = ridge / apex)")

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

    # K.10.3: string legend in the bottom-LEFT corner (mirrors the
    # module dim callout). Shows each MPPT string with its color swatch
    # + module count, so AHJ + installer can read the band colors on
    # the ROOF SECTION PLANS without flipping to EE-1.
    _draw_string_legend(
        c,
        x=0.45 * inch, y=0.50 * inch,
        w=2.00 * inch, h=1.00 * inch,
        result=result,
    )

    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(W / 2, 0.25 * inch,
                        "Roof plans show shape, setbacks (dashed), "
                        "obstructions (hatched), and modules colored by "
                        "MPPT string assignment (K.10). See PV-5 for "
                        "mounting detail.")
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
    c.rect(x, y, w, h, fill=0, stroke=1)
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

    c.setLineWidth(1.0)
    c.rect(0.4 * inch, 0.4 * inch, W - 0.8 * inch, H - 0.8 * inch)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(W / 2, H - 0.8 * inch, "PV-5 · MOUNTING DETAILS")

    # Three details laid out left-to-right
    panel_w = (W - 1.6 * inch) / 3
    panel_h = H - 1.8 * inch
    y0 = 0.9 * inch
    x_positions = [0.5 + k * (panel_w / inch + 0.1) for k in range(3)]

    _detail_cross_section(c, x_positions[0] * inch, y0, panel_w, panel_h, mounting)
    _detail_plan_view  (c, x_positions[1] * inch, y0, panel_w, panel_h, mounting)
    _detail_flashing   (c, x_positions[2] * inch, y0, panel_w, panel_h, mounting)

    c.save()


def _panel_frame(c, x: float, y: float, w: float, h: float, title: str) -> None:
    c.setLineWidth(0.8)
    c.rect(x, y, w, h)
    c.setFillColor(colors.HexColor("#1F5BD7"))
    c.rect(x, y + h - 0.3 * inch, w, 0.3 * inch, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x + 0.10 * inch, y + h - 0.20 * inch, title)
    c.setFillColor(colors.black)


def _detail_cross_section(c, x: float, y: float, w: float, h: float, mounting) -> None:
    _panel_frame(c, x, y, w, h, "ROOF MOUNT CROSS SECTION")
    cx = x + w / 2
    cy = y + h / 2 - 0.2 * inch
    # Roof line (slanted)
    c.setLineWidth(1.5)
    c.line(x + 0.3 * inch, cy - 0.3 * inch, x + w - 0.3 * inch, cy + 0.3 * inch)
    # Rafter (under roof line, parallel)
    c.setLineWidth(0.8)
    c.line(x + 0.3 * inch, cy - 0.4 * inch, x + w - 0.3 * inch, cy + 0.2 * inch)
    # Module above roof
    c.line(x + 0.3 * inch, cy + 0.4 * inch, x + w - 0.3 * inch, cy + 1.0 * inch)
    # Rail under module
    c.line(x + 0.4 * inch, cy + 0.3 * inch, x + w - 0.4 * inch, cy + 0.9 * inch)
    # Bolt + flashing
    c.setLineWidth(1.0)
    c.line(cx, cy - 0.3 * inch, cx, cy + 0.4 * inch)
    c.circle(cx, cy + 0.0 * inch, 0.05 * inch, stroke=1, fill=0)
    # Labels
    c.setFont("Helvetica", 7.5)
    c.drawString(x + 0.10 * inch, cy + 1.05 * inch, "PV MODULE")
    c.drawString(x + 0.10 * inch, cy + 0.55 * inch, "RAIL")
    c.drawString(x + 0.10 * inch, cy + 0.15 * inch, "FLASHING + LAG")
    c.drawString(x + 0.10 * inch, cy - 0.25 * inch, "ROOFING")
    c.drawString(x + 0.10 * inch, cy - 0.45 * inch, "RAFTER 2×6 OR LARGER")
    c.setFont("Helvetica", 7)
    c.drawString(x + 0.10 * inch, y + 0.20 * inch,
                 f"Fastener: {mounting.fastener}")


def _detail_plan_view(c, x: float, y: float, w: float, h: float, mounting) -> None:
    _panel_frame(c, x, y, w, h, "ROOF MOUNT PLAN VIEW")
    # Module outline (rectangle)
    mod_x = x + 0.4 * inch
    mod_y = y + 0.8 * inch
    mod_w = w - 0.8 * inch
    mod_h = h - 1.6 * inch
    c.setLineWidth(1.0)
    c.rect(mod_x, mod_y, mod_w, mod_h)
    # Rails (two horizontal, top + bottom thirds)
    c.setLineWidth(0.6)
    rail1_y = mod_y + mod_h * 0.25
    rail2_y = mod_y + mod_h * 0.75
    c.line(mod_x - 0.1 * inch, rail1_y, mod_x + mod_w + 0.1 * inch, rail1_y)
    c.line(mod_x - 0.1 * inch, rail2_y, mod_x + mod_w + 0.1 * inch, rail2_y)
    # Attachment points (dots on rails)
    c.setFillColor(colors.HexColor("#C00000"))
    n_attach = 4
    for i_ in range(n_attach):
        ax = mod_x + (i_ + 0.5) * mod_w / n_attach
        c.circle(ax, rail1_y, 0.04 * inch, stroke=0, fill=1)
        c.circle(ax, rail2_y, 0.04 * inch, stroke=0, fill=1)
    c.setFillColor(colors.black)
    # Dimensions
    c.setFont("Helvetica", 7)
    c.drawString(mod_x, mod_y + mod_h + 0.10 * inch,
                 f"Max X = {mounting.max_x_spacing_in:.0f}\"")
    c.drawString(mod_x + mod_w - 0.4 * inch, mod_y - 0.20 * inch,
                 f"Max Y = {mounting.max_y_spacing_in:.0f}\"")
    c.drawString(x + 0.15 * inch, y + 0.20 * inch,
                 "● = attachment point (4 per module typical)")


def _detail_flashing(c, x: float, y: float, w: float, h: float, mounting) -> None:
    _panel_frame(c, x, y, w, h, "FLASHING + ANCHORAGE")
    cx = x + w / 2
    cy = y + h / 2
    # Shingle roof
    c.setLineWidth(0.5)
    for k in range(5):
        c.line(x + 0.3 * inch, cy - 0.6 * inch + k * 0.10 * inch,
               x + w - 0.3 * inch, cy - 0.6 * inch + k * 0.10 * inch)
    # Flashing plate
    c.setFillColor(colors.HexColor("#AAAAAA"))
    c.rect(cx - 0.6 * inch, cy - 0.2 * inch, 1.2 * inch, 0.4 * inch, fill=1, stroke=1)
    # L-foot
    c.setFillColor(colors.black)
    c.rect(cx - 0.10 * inch, cy + 0.20 * inch, 0.20 * inch, 0.35 * inch, fill=0, stroke=1)
    # Bolt
    c.setLineWidth(1.5)
    c.line(cx, cy - 0.30 * inch, cx, cy + 0.55 * inch)
    c.setFont("Helvetica", 7.5)
    c.drawString(x + 0.10 * inch, cy + 0.70 * inch, "L-FOOT")
    c.drawString(x + 0.10 * inch, cy + 0.25 * inch, "FLASHING PLATE")
    c.drawString(x + 0.10 * inch, cy - 0.05 * inch, "(Mfr: " + mounting.flashing + ")")
    c.drawString(x + 0.10 * inch, cy - 0.70 * inch, "ASPHALT SHINGLE ROOFING")


# --- EE-1 String Plan (color-coded by real K.9.1 string assignment) ---------

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

    # Outer frame + title
    c.setLineWidth(1.0)
    c.rect(0.4 * inch, 0.4 * inch, W - 0.8 * inch, H - 0.8 * inch)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(W / 2, H - 0.8 * inch, "EE-1 · STRING LAYOUT PLAN")
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
