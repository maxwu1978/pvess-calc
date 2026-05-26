"""EE-4 site plan — top-down view: lot, house, PV array footprint, equipment.

K.6 upgrades:
  * Setback dimensioning: extension lines + numeric distance from
    house exterior to each lot edge (front / rear / left / right).
  * Electrical route: dashed line connecting MSP → AC-DISC → ESS along
    the east wall of the house.
  * Scale bar bottom-left of the drawing area.
  * North arrow upgraded to a filled triangle with bold "N".

Backward compat: every upgrade reads from existing `site` fields; no
new yaml fields required.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from ..calc.engine import CalculationResult
from ._textfit import fit
from .ee4_trace_modules import ee4_module_geometries
from .roof_cad_library import (
    CAD_BLACK,
    FIRE_ORANGE,
    draw_closed_polygon,
    draw_facet_tag,
    draw_fire_pathway,
    draw_fire_swatch,
    draw_keepout_area,
    draw_keepout_swatch,
    draw_pv_module,
    draw_roof_facet,
    draw_roof_line,
    draw_roof_outline,
    draw_roof_symbol,
)


# Visual token: dimension line / extension line styling.
_DIM_COLOR = colors.HexColor("#666666")
_ROUTE_COLOR = colors.HexColor("#D97706")    # warm orange = electrical route
_PV_COLOR = colors.HexColor("#FFE680")
_HOUSE_COLOR = colors.HexColor("#E8E8E8")
_FACE_PRIORITY_COLORS = [
    ("#16A34A", "#ECFDF5"),  # preferred PV face
    ("#2563EB", "#EFF6FF"),
    ("#F59E0B", "#FFFBEB"),
    ("#7C3AED", "#F5F3FF"),
]


@dataclass(frozen=True)
class EE4FaceAllocation:
    section_name: str
    section_names: tuple[str, ...]
    direction: str
    azimuth_deg: float
    pitch_deg: float
    modules: int
    priority: int
    stroke_hex: str
    fill_hex: str


@dataclass(frozen=True)
class EE4TraceFacetDisplay:
    tag: str
    name: str
    vertices: list[tuple[float, float]]
    modules: int
    direction: str
    priority: int | None
    stroke_hex: str
    fill_hex: str


def _sheet_label(result: CalculationResult, default_code: str = "EE-4") -> str:
    code = getattr(result, "_active_sheet_display_code", default_code)
    title = getattr(result, "_active_sheet_title", "Site Plan")
    return f"{code} · {title.upper()}"


def render_site_plan(result: CalculationResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=landscape(letter))
    W, H = landscape(letter)
    i = result.inputs
    site = i.site

    # Stage 2 — projects with real roof_sections now render as a
    # permit-style EE-4 sheet (left schedules + large roof plan). The
    # legacy lot/setback schematic below remains the fallback for old
    # yamls that do not carry roof geometry yet.
    if site.roof_sections or site.ee4_trace.enabled:
        _render_permit_style_site_plan(c, result, W, H)
        c.save()
        return

    c.setLineWidth(1.0)
    c.rect(0.4 * inch, 0.4 * inch, W - 0.8 * inch, H - 0.8 * inch)

    # Title strip — baseline 0.70" below the page top so that an 18pt
    # bold cap-height (~0.20") clears the outer frame line at H-0.40"
    # with ~0.10" of breathing room. Pre-K.11.7b polish had the title
    # at H-0.55", which let the ascenders cross the frame border.
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(W / 2, H - 0.70 * inch, _sheet_label(result))
    if i.project.site_address:
        c.setFont("Helvetica", 9)
        c.drawCentredString(W / 2, H - 0.90 * inch,
                            i.project.site_address.upper())

    # Drawing area — bigger margins on the right for SITE INFORMATION
    # and outside the lot dashed box for setback labels.
    da_x = 1.1 * inch
    da_y = 1.2 * inch       # extra room for scale bar at the bottom
    da_w = W - 4.6 * inch
    da_h = H - 2.4 * inch

    # Scale: fit lot in drawing area (with margin for dim lines outside).
    margin_ft = 0.0     # dim lines drawn outside the lot polygon
    fit_w = da_w * 0.85
    fit_h = da_h * 0.85
    scale = min(fit_w / site.lot_width_ft, fit_h / site.lot_depth_ft)
    px_per_ft = scale

    def ft_to_pt(ft: float) -> float:
        return ft * px_per_ft

    # Lot outline (property line, dashed) — centered in drawing area
    lot_w_pt = ft_to_pt(site.lot_width_ft)
    lot_h_pt = ft_to_pt(site.lot_depth_ft)
    lot_x = da_x + (da_w - lot_w_pt) / 2
    lot_y = da_y + (da_h - lot_h_pt) / 2

    c.setLineWidth(0.8)
    c.setStrokeColor(colors.black)
    c.setDash(8, 4)
    c.rect(lot_x, lot_y, lot_w_pt, lot_h_pt)
    c.setDash()  # reset
    # K.13.1 P3 — PROPERTY LINE label on the LEFT side of the lot's
    # top frame, inset slightly to the right of the rotated address
    # column. The rotated address is centred vertically on the LEFT
    # property line (so the top-left CORNER of the lot is clear);
    # the routed legend banner at +0.22" above the lot lives at the
    # right side. This top-left placement avoids the bottom-margin
    # zone where leader callouts + setback dim lines compete.
    c.setFont("Helvetica-Oblique", 7)
    c.setFillColor(colors.HexColor("#475569"))
    c.drawString(lot_x + 0.04 * inch,
                 lot_y + lot_h_pt + 0.06 * inch,
                 "PROPERTY LINE (dashed)")
    c.setFillColor(colors.black)

    # K.11.7f — rotated address along the LEFT property line (90° CCW).
    # Matches the Wyssling reference image style: street name vertical
    # outside the lot's street-facing edge. Stage C bumps the offset
    # from 0.30" to 0.50" so the label clears any drawing-area
    # rendering (was visually pressed against the lot line).
    if i.project.site_address:
        c.saveState()
        c.setFillColor(colors.HexColor("#1F2937"))
        c.setFont("Helvetica-Bold", 11)
        addr_x = lot_x - 0.50 * inch
        addr_y = lot_y + lot_h_pt / 2
        c.translate(addr_x, addr_y)
        c.rotate(90)
        c.drawCentredString(0, 0, i.project.site_address.upper())
        c.restoreState()
        c.setFillColor(colors.black)

    # K.11.7f — house outline: polygon when site.house_outline_vertices
    # is populated (real L/T/irregular footprint), else fall back to the
    # centered rectangle (legacy default for simple residential plans).
    c.setFillColor(_HOUSE_COLOR)
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.0)
    if site.house_outline_vertices:
        # Polygon coordinates are in site ft from lot front-left.
        # Compute its bbox so we have something to anchor the
        # RESIDENCE label + roof penetrations against (substitutes
        # the legacy `house_x/y/w/h` for downstream code).
        xs = [v[0] for v in site.house_outline_vertices]
        ys = [v[1] for v in site.house_outline_vertices]
        house_x_ft, house_y_ft = min(xs), min(ys)
        house_w_ft = max(xs) - min(xs)
        house_h_ft = max(ys) - min(ys)
        house_x = lot_x + house_x_ft * px_per_ft
        house_y = lot_y + house_y_ft * px_per_ft
        house_w_pt = house_w_ft * px_per_ft
        house_h_pt = house_h_ft * px_per_ft
        path = c.beginPath()
        v0 = site.house_outline_vertices[0]
        path.moveTo(lot_x + v0[0] * px_per_ft,
                    lot_y + v0[1] * px_per_ft)
        for vx, vy in site.house_outline_vertices[1:]:
            path.lineTo(lot_x + vx * px_per_ft, lot_y + vy * px_per_ft)
        path.close()
        c.drawPath(path, fill=1, stroke=1)
    else:
        house_w_pt = ft_to_pt(site.house_width_ft)
        house_h_pt = ft_to_pt(site.house_depth_ft)
        house_x = lot_x + (lot_w_pt - house_w_pt) / 2
        house_y = lot_y + (lot_h_pt - house_h_pt) / 2
        c.rect(house_x, house_y, house_w_pt, house_h_pt, fill=1)

    # K.11.7e + Stage B — three visual states:
    #   * `routed`           : full K.11 wire-trunk routing active
    #                           → real modules + conduit + leader callouts
    #   * `has_face_anchors` : anchors set (explicit or auto-derived),
    #                           but no equipment_locations
    #                           → real modules + per-face setbacks only
    #   * neither            : legacy abstract grid path
    routed = result.wire_routing is not None and result.wire_routing.routed
    has_face_anchors = any(
        s.site_anchor_x_ft is not None for s in i.site.roof_sections
    )

    # Stage D — incompleteness warning for pure-legacy mode. The
    # K.13 cleanup deleted the synthetic abstract-grid render, so
    # this strip is now the ONLY signal that EE-4 has no array data
    # for this project. Wording is explicit: EE-4 doesn't draw PV
    # geometry here; PV-4 does.
    if not routed and not has_face_anchors:
        c.saveState()
        c.setFillColor(colors.HexColor("#FFFBEB"))
        c.setStrokeColor(colors.HexColor("#F59E0B"))
        c.setLineWidth(0.5)
        strip_h = 0.22 * inch
        strip_y = H - 1.18 * inch
        strip_x = 0.6 * inch
        strip_w = W - 1.2 * inch
        c.rect(strip_x, strip_y, strip_w, strip_h, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#92400E"))
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(
            W / 2, strip_y + 0.07 * inch,
            "NOTE — PV array geometry omitted from EE-4 (no "
            "site.roof_sections in yaml). See PV-4 for module "
            "attachment plan. EE-4 shows lot + setbacks + equipment.",
        )
        c.setFillColor(colors.black)
        c.setStrokeColor(colors.black)
        c.restoreState()

    # RESIDENCE label — always present (centered in house body)
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    c.drawCentredString(house_x + house_w_pt / 2,
                        house_y + house_h_pt * 0.30, "RESIDENCE")

    # Stage D / K.13 — EE-4 is now a SITE plan, not a PV-array plan.
    #
    # The pre-K.13 code had a "legacy abstract grid" path here that
    # painted a yellow PV ARRAY rectangle + a synthetic N×M module
    # grid on top of the house when no per-face geometry was
    # available. That was redundant with PV-4 (the canonical
    # attachment plan) and consistently confused AHJ reviewers
    # because the grid wasn't at real coordinates.
    #
    # In K.13 we delete that path entirely:
    #   * routed / has_face_anchors → real K.9.1 modules drawn at
    #     site coords by `_draw_conduit_overlay` below
    #   * neither                   → no PV drawn on EE-4; the warning
    #     strip already routes users to PV-4 for array geometry

    # ── K.6 setback dimensioning ─────────────────────────────────────────
    # Front yard (top of lot → top of house)
    front_yard_ft = (lot_y + lot_h_pt - (house_y + house_h_pt)) / px_per_ft
    rear_yard_ft  = (house_y - lot_y) / px_per_ft
    left_yard_ft  = (house_x - lot_x) / px_per_ft
    right_yard_ft = (lot_x + lot_w_pt - (house_x + house_w_pt)) / px_per_ft

    # Top (front) dimension line — outside lot, above
    _dim_line_vertical(
        c, x=lot_x - 0.30 * inch,
        y0=house_y + house_h_pt, y1=lot_y + lot_h_pt,
        label=f"{front_yard_ft:.0f}'", side="left",
    )
    # Bottom (rear)
    _dim_line_vertical(
        c, x=lot_x - 0.30 * inch,
        y0=lot_y, y1=house_y,
        label=f"{rear_yard_ft:.0f}'", side="left",
    )
    # Left
    _dim_line_horizontal(
        c, y=lot_y - 0.30 * inch,
        x0=lot_x, x1=house_x,
        label=f"{left_yard_ft:.0f}'", side="below",
    )
    # Right
    _dim_line_horizontal(
        c, y=lot_y - 0.30 * inch,
        x0=house_x + house_w_pt, x1=lot_x + lot_w_pt,
        label=f"{right_yard_ft:.0f}'", side="below",
    )

    # ── K.6 equipment markers + dashed route along east wall ─────────────
    # ONLY drawn in pure-legacy mode (no auto/explicit anchors AND no
    # routing). When anchors exist the per-face geometry overlay shows
    # the real layout; when fully routed the conduit polyline + leader
    # callouts in _draw_conduit_overlay take over.
    if not routed and not has_face_anchors:
        eq_x = house_x + house_w_pt + 0.18 * inch
        eq_y_base = house_y + house_h_pt - 0.30 * inch
        equipment = [
            ("MSP", "Main panel + utility meter"),
            ("AC-DISC", "AC disconnect"),
            ("ESS", f"({i.battery.quantity}) × {i.battery.brand} {i.battery.model}"),
        ]
        eq_boxes: list[tuple[float, float]] = []
        c.setFont("Helvetica", 8)
        for idx, (label, desc) in enumerate(equipment):
            yy = eq_y_base - idx * 0.45 * inch
            c.setFillColor(colors.HexColor("#1F5BD7"))
            c.setStrokeColor(colors.HexColor("#1F5BD7"))
            c.rect(eq_x, yy, 0.55 * inch, 0.28 * inch, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 8)
            c.drawCentredString(eq_x + 0.275 * inch, yy + 0.09 * inch, label)
            c.setFillColor(colors.black)
            c.setFont("Helvetica", 7.5)
            c.drawString(eq_x + 0.60 * inch, yy + 0.09 * inch,
                         fit(desc, "Helvetica", 7.5, 2.6 * inch))
            eq_boxes.append((eq_x, yy + 0.14 * inch))

        # Electrical route — orange dashed line MSP → AC-DISC → ESS.
        if len(eq_boxes) >= 2:
            c.setStrokeColor(_ROUTE_COLOR)
            c.setLineWidth(1.2)
            c.setDash(4, 2)
            for (x0, y0), (x1, y1) in zip(eq_boxes, eq_boxes[1:]):
                c.line(x0, y0, x1, y1)
            c.setDash()
            c.setLineWidth(1.0)
            c.setFillColor(_ROUTE_COLOR)
            c.setFont("Helvetica", 7)
            legend_y = eq_boxes[-1][1] - 0.35 * inch
            c.line(eq_x - 0.10 * inch, legend_y, eq_x - 0.02 * inch, legend_y)
            c.setFillColor(colors.black)
            c.drawString(eq_x + 0.00 * inch, legend_y - 2,
                         "— equipment route (electrical)")
            c.setStrokeColor(colors.black)

    # ── K.6 north arrow — bigger filled triangle ─────────────────────────
    arrow_x = lot_x + lot_w_pt + 0.30 * inch
    arrow_y = lot_y + lot_h_pt - 0.90 * inch
    c.setLineWidth(1.0)
    # Vertical line
    c.line(arrow_x, arrow_y, arrow_x, arrow_y + 0.60 * inch)
    # Filled triangle head
    path = c.beginPath()
    path.moveTo(arrow_x, arrow_y + 0.80 * inch)
    path.lineTo(arrow_x - 0.14 * inch, arrow_y + 0.55 * inch)
    path.lineTo(arrow_x + 0.14 * inch, arrow_y + 0.55 * inch)
    path.close()
    c.setFillColor(colors.black)
    c.drawPath(path, stroke=0, fill=1)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(arrow_x, arrow_y + 0.90 * inch, "N")

    # ── K.6 scale bar — bottom-left of drawing area ──────────────────────
    bar_x = da_x + 0.05 * inch
    bar_y = da_y - 0.60 * inch
    _draw_scale_bar(c, bar_x, bar_y, px_per_ft)

    # Right column: site stats (unchanged from pre-K.6 baseline)
    info_x = W - 3.4 * inch
    info_y = H - 1.5 * inch
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(info_x, info_y, "SITE INFORMATION")
    c.line(info_x, info_y - 0.05 * inch, info_x + 2.5 * inch, info_y - 0.05 * inch)
    rows = [
        ("Lot dimensions",     f"{site.lot_width_ft:.0f}' × {site.lot_depth_ft:.0f}'"),
        ("Residence footprint", f"{site.house_width_ft:.0f}' × {site.house_depth_ft:.0f}'"),
        ("PV array footprint", f"{site.array_width_ft:.0f}' × {site.array_depth_ft:.0f}'"),
        ("Array azimuth",      f"{site.array_azimuth_deg:.0f}° (180=S)"),
        ("Roof pitch",         f"{site.roof_pitch_deg:.0f}°"),
        # K.6: setback values exposed in the side column too — gives the
        # AHJ reviewer one place to verify everything quickly.
        ("Front yard setback", f"{front_yard_ft:.0f}'"),
        ("Rear yard setback",  f"{rear_yard_ft:.0f}'"),
        ("Side yard setback",  f"{min(left_yard_ft, right_yard_ft):.0f}'"),
        ("",                   ""),
        ("Coordinates",        i.project.coordinates or "—"),
        ("APN",                i.project.apn or "—"),
    ]
    c.setFont("Helvetica", 9.5)
    yy = info_y - 0.25 * inch
    for k, v in rows:
        if not k and not v:
            yy -= 0.10 * inch
            continue
        c.drawString(info_x, yy, k)
        c.drawString(info_x + 1.6 * inch, yy, v)
        yy -= 0.19 * inch

    # K.11.7 + Stage D — aerial roof inset below SITE INFORMATION.
    # K.13 bumps the size 2.5×2.2 → 3.0×2.6 because EE-4 no longer
    # draws the legacy abstract PV box; the right column has extra
    # space below the SITE INFORMATION table. The aerial is the
    # single most informative drawing on EE-4 (real photo of the
    # actual roof), so giving it more room matches the Wyssling
    # reference layout.
    _draw_aerial_inset(
        c, result,
        x=info_x, y=yy - 2.80 * inch,
        w=3.0 * inch, h=2.6 * inch,
    )

    # K.11 — conduit overlay: when site.equipment_locations is populated
    # AND the engine produced auto-routed wire lengths, draw the real
    # 2D conduit polyline + equipment dots ON TOP of the legacy layout.
    # Legacy yamls (`wire_routing.routed=False`) keep the K.6 east-wall
    # column drawn above, bit-identical to pre-K.11.
    _draw_conduit_overlay(
        c, result,
        lot_x=lot_x, lot_y=lot_y,
        lot_w_pt=lot_w_pt, lot_h_pt=lot_h_pt,
        page_w=W,
        px_per_ft=px_per_ft,
    )

    # Footer
    c.setFont("Helvetica-Oblique", 8)
    footer = ("Site plan is schematic — verify all dimensions and "
              "setbacks against AHJ requirements.")
    if result.wire_routing is not None and result.wire_routing.routed:
        footer = ("Conduit run + equipment locations auto-routed from "
                  "site.equipment_locations (K.11). Verify against "
                  "site survey before bid.")
    c.drawString(0.5 * inch, 0.25 * inch, footer)
    c.save()


def _render_permit_style_site_plan(
    c: canvas.Canvas,
    result: CalculationResult,
    W: float,
    H: float,
) -> None:
    """Stage 2 — Wyssling-style EE-4 composition.

    This path intentionally frames the roof/equipment geometry, not the
    full lot rectangle. The full lot fallback is still useful when a
    project has no roof_sections, but once roof data exists reviewers
    need a large array/site-plan drawing plus the familiar schedules,
    legends, notes, and module dimension callout.
    """
    margin = 0.28 * inch
    left_x = 0.32 * inch
    left_w = 2.18 * inch
    drawing_x = 2.85 * inch
    drawing_y = 1.72 * inch
    drawing_w = W - drawing_x - 0.38 * inch
    drawing_h = H - drawing_y - 0.55 * inch

    c.setLineWidth(0.8)
    c.setStrokeColor(colors.black)
    c.rect(margin, margin, W - 2 * margin, H - 2 * margin)

    _draw_ee4_left_column(c, result, left_x, H - 0.36 * inch, left_w)
    _draw_ee4_roof_plan(
        c, result,
        x=drawing_x, y=drawing_y, w=drawing_w, h=drawing_h,
    )
    _draw_ee4_site_notes(c, result, x=0.32 * inch, y=0.36 * inch,
                         w=7.25 * inch, h=1.12 * inch)
    _draw_ee4_module_callout(
        c, result,
        x=W - 1.22 * inch, y=0.62 * inch,
        w=0.90 * inch, h=0.86 * inch,
    )

    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8)
    c.drawCentredString(W * 0.73, 0.44 * inch, 'SCALE: 3/32" = 1\'-0"')
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(W - 0.38 * inch, 0.30 * inch, _sheet_label(result))


def _draw_ee4_left_column(
    c: canvas.Canvas,
    result: CalculationResult,
    x: float,
    top_y: float,
    w: float,
) -> None:
    i = result.inputs
    pv = i.pv_array
    mod = pv.module
    inv_count = i.inverter.count(i.battery.quantity)
    opt_count = (
        i.optimizer.effective_count(pv.modules, pv.strings)
        if i.optimizer.brand else 0
    )
    mod_area_sqft = (mod.length_in * mod.width_in) / 144.0
    weight_psf = mod.weight_lbs / mod_area_sqft if mod_area_sqft else 0.0

    rows = [
        ("MODULE\nCOUNT/TYPE",
         f"({pv.modules}) {mod.brand.upper()} {mod.model}"),
        ("INVERTER\nCOUNT/TYPE",
         f"({inv_count}) {i.inverter.brand.upper()} {i.inverter.model}"),
        ("MODULE\nWEIGHT", f"{mod.weight_lbs:.2f} LBS"),
        ("MODULE\nDIMENSIONS", f'{mod.length_in:.2f}" x {mod.width_in:.2f}"'),
        ("UNIT WEIGHT\nOF ARRAY", f"{weight_psf:.2f} PSF"),
    ]
    y = top_y - 1.62 * inch
    _draw_key_value_table(c, x, y, w, 1.62 * inch, rows)

    legend_top = y - 0.34 * inch
    _draw_ee4_legend(c, x, legend_top, w)

    summary_top = legend_top - 2.22 * inch
    _draw_ee4_equipment_summary(
        c, result, x, summary_top, w,
        optimizer_count=opt_count,
    )
    _draw_ee4_face_allocation_table(
        c, result,
        x=x,
        top_y=summary_top - 1.42 * inch,
        w=w,
    )

    c.setFillColor(colors.black)
    c.setFont("Helvetica", 7.2)
    footer_y = 1.60 * inch
    c.drawString(x, footer_y,
                 f"MODULE: ({pv.modules}) {mod.brand.upper()} {mod.model}")
    c.drawString(x, footer_y - 0.12 * inch,
                 f"INVERTER: ({inv_count}) {i.inverter.brand.upper()} "
                 f"{i.inverter.model}")


def _draw_key_value_table(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    rows: list[tuple[str, str]],
) -> None:
    left_w = 0.72 * inch
    row_h = h / len(rows)
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.55)
    c.rect(x, y, w, h)
    c.line(x + left_w, y, x + left_w, y + h)
    for idx in range(1, len(rows)):
        yy = y + idx * row_h
        c.line(x, yy, x + w, yy)

    for idx, (label, value) in enumerate(rows):
        row_y = y + h - (idx + 1) * row_h
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 7.0)
        lines = label.split("\n")
        for line_idx, line in enumerate(lines):
            c.drawCentredString(
                x + left_w / 2,
                row_y + row_h / 2 + (len(lines) - 1) * 4
                - line_idx * 8 - 2,
                line,
            )
        c.setFont("Helvetica", 7.2)
        c.drawCentredString(
            x + left_w + (w - left_w) / 2,
            row_y + row_h / 2 - 2,
            fit(value, "Helvetica", 7.2, w - left_w - 0.08 * inch),
        )


def _draw_ee4_legend(
    c: canvas.Canvas,
    x: float,
    top_y: float,
    w: float,
) -> None:
    rows = [
        ("LEGEND", ""),
        ("ROOF VENT (TYP.)", "roof_vent"),
        ("PLUMBING VENT (TYP.)", "plumbing"),
        ("A/C UNIT", "ac"),
        ("SATELLITE DISH", "satellite"),
        ("ELECTRICAL MAST", "mast"),
        ("CHIMNEY", "chimney"),
        ("NO-PV AREA", "no_panel"),
        ("FIRECODE PATHWAY", "fire"),
    ]
    row_h = 0.18 * inch
    h = len(rows) * row_h
    y = top_y - h
    sym_w = 0.70 * inch
    c.setLineWidth(0.55)
    c.rect(x, y, w, h)
    c.line(x + w - sym_w, y, x + w - sym_w, y + h - row_h)
    for idx in range(1, len(rows)):
        yy = y + idx * row_h
        c.line(x, yy, x + w, yy)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawCentredString(x + w / 2, y + h - row_h + 0.055 * inch, "LEGEND")
    c.setFont("Helvetica", 7.1)
    for idx, (label, kind) in enumerate(rows[1:], 1):
        cy = y + h - (idx + 0.5) * row_h
        c.drawCentredString(x + (w - sym_w) / 2, cy - 2, label)
        _draw_ee4_legend_symbol(c, x + w - sym_w / 2, cy, kind)


def _draw_ee4_legend_symbol(
    c: canvas.Canvas,
    cx: float,
    cy: float,
    kind: str,
) -> None:
    if kind == "fire":
        draw_fire_swatch(c, cx, cy)
    elif kind == "no_panel":
        draw_keepout_swatch(c, cx, cy, label="NP")
    else:
        draw_roof_symbol(c, cx, cy, kind, size=8.0)
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)


def _draw_ee4_equipment_summary(
    c: canvas.Canvas,
    result: CalculationResult,
    x: float,
    top_y: float,
    w: float,
    *,
    optimizer_count: int,
) -> None:
    i = result.inputs
    inv_count = i.inverter.count(i.battery.quantity)
    lines = [
        "EQUIPMENT SUMMARY:",
        f"PV MODULE: ({i.pv_array.modules}) {i.pv_array.module.brand.upper()} "
        f"{i.pv_array.module.model}",
        f"INVERTER: ({inv_count}) {i.inverter.brand.upper()} {i.inverter.model}",
    ]
    if i.optimizer.brand:
        lines.append(
            f"OPTIMIZER: ({optimizer_count}) {i.optimizer.brand.upper()} "
            f"{i.optimizer.model}"
        )
    if i.service.sub_panels:
        lines.append(
            "CONTROL PANEL: "
            + ", ".join(sp.name.upper() for sp in i.service.sub_panels[:2])
        )
    meter = i.project.meter_info
    lines += [
        "",
        f"UTILITY: {i.project.utility or '—'}",
        f"ONCOR METER NUMBER: {meter.number or '—'}",
        f"ESID: {meter.esid or '—'}",
    ]

    h = 1.30 * inch
    y = top_y - h
    c.setLineWidth(0.55)
    c.rect(x, y, w, h)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7.5)
    yy = top_y - 0.13 * inch
    for idx, line in enumerate(lines):
        if not line:
            yy -= 0.08 * inch
            continue
        c.setFont("Helvetica-Bold" if idx == 0 else "Helvetica", 7.0)
        c.drawString(x + 0.04 * inch, yy,
                     fit(line, "Helvetica", 7.0, w - 0.08 * inch))
        yy -= 0.12 * inch


def _ee4_face_direction_label(azimuth_deg: float) -> str:
    """Return a human roof-face direction from PV azimuth degrees."""
    az = azimuth_deg % 360.0
    sectors = [
        ("NORTH", 337.5, 360.0),
        ("NORTH", 0.0, 22.5),
        ("NORTHEAST", 22.5, 67.5),
        ("EAST", 67.5, 112.5),
        ("SOUTHEAST", 112.5, 157.5),
        ("SOUTH", 157.5, 202.5),
        ("SOUTHWEST", 202.5, 247.5),
        ("WEST", 247.5, 292.5),
        ("NORTHWEST", 292.5, 337.5),
    ]
    for label, lo, hi in sectors:
        if lo <= az < hi:
            return label
    return "NORTH"


def _ee4_direction_preference(direction: str) -> int:
    """Lower is better for the current residential PV placement heuristic.

    The order matches the project's design rule: use southwest first when it
    exists, then east, then south/west shoulders, and keep north-facing faces
    at the end unless an engineer explicitly assigns modules there.
    """
    return {
        "SOUTHWEST": 0,
        "EAST": 1,
        "SOUTH": 2,
        "WEST": 3,
        "SOUTHEAST": 4,
        "NORTHWEST": 7,
        "NORTHEAST": 8,
        "NORTH": 9,
    }.get(direction, 6)


def _ee4_face_allocation_rows(
    result: CalculationResult,
) -> list[EE4FaceAllocation]:
    """Active roof-face rows grouped by orientation for annotations."""
    groups: dict[str, dict[str, object]] = {}
    for original_idx, section in enumerate(result.inputs.site.roof_sections):
        placed_count = len(result.module_placements.get(section.name, []))
        modules = placed_count if placed_count > 0 else section.module_count
        if modules <= 0:
            continue
        direction = _ee4_face_direction_label(section.azimuth_deg)
        group = groups.setdefault(direction, {
            "direction": direction,
            "modules": 0,
            "weighted_azimuth": 0.0,
            "weighted_pitch": 0.0,
            "section_names": [],
            "first_idx": original_idx,
        })
        group["modules"] = int(group["modules"]) + modules
        group["weighted_azimuth"] = (
            float(group["weighted_azimuth"]) + section.azimuth_deg * modules
        )
        group["weighted_pitch"] = (
            float(group["weighted_pitch"]) + section.pitch_deg * modules
        )
        group["section_names"] = list(group["section_names"]) + [section.name]
        group["first_idx"] = min(int(group["first_idx"]), original_idx)

    rows: list[EE4FaceAllocation] = []
    sort_rows = sorted(
        groups.values(),
        key=lambda g: (
            _ee4_direction_preference(str(g["direction"])),
            -int(g["modules"]),
            int(g["first_idx"]),
        ),
    )
    for rank, group in enumerate(
        sort_rows, 1,
    ):
        direction = str(group["direction"])
        modules = int(group["modules"])
        stroke_hex, fill_hex = _FACE_PRIORITY_COLORS[
            (rank - 1) % len(_FACE_PRIORITY_COLORS)
        ]
        rows.append(EE4FaceAllocation(
            section_name=direction,
            section_names=tuple(str(n) for n in group["section_names"]),
            direction=direction,
            azimuth_deg=float(group["weighted_azimuth"]) / modules,
            pitch_deg=float(group["weighted_pitch"]) / modules,
            modules=modules,
            priority=rank,
            stroke_hex=stroke_hex,
            fill_hex=fill_hex,
        ))
    return rows


def _ee4_trace_facet_displays(
    result: CalculationResult,
) -> list[EE4TraceFacetDisplay]:
    """Trace roof facets with F# tags and PV allocation metadata."""
    trace = result.inputs.site.ee4_trace
    if not _ee4_trace_active(result.inputs.site) or not trace.roof_facets:
        return []

    sections_by_name = {
        section.name.lower(): section
        for section in result.inputs.site.roof_sections
    }
    allocation_by_direction = {
        row.direction: row
        for row in _ee4_face_allocation_rows(result)
    }
    displays: list[EE4TraceFacetDisplay] = []
    for idx, facet in enumerate(trace.roof_facets, 1):
        section = sections_by_name.get((facet.name or "").lower())
        modules = 0
        direction = "NO PV"
        priority = None
        stroke_hex = "#64748B"
        fill_hex = "#F8FAFC"
        if section is not None:
            modules = len(result.module_placements.get(section.name, []))
            if modules <= 0:
                modules = section.module_count
            direction = _ee4_face_direction_label(section.azimuth_deg)
            row = allocation_by_direction.get(direction)
            if row is not None:
                priority = row.priority
                stroke_hex = row.stroke_hex
                fill_hex = row.fill_hex
        displays.append(EE4TraceFacetDisplay(
            tag=f"F{idx}",
            name=facet.name or f"Roof facet {idx}",
            vertices=list(facet.vertices),
            modules=modules,
            direction=direction,
            priority=priority,
            stroke_hex=stroke_hex,
            fill_hex=fill_hex,
        ))
    return displays


def _ee4_facet_tag_for_sections(
    result: CalculationResult,
    section_names: tuple[str, ...],
) -> str:
    names = {name.lower() for name in section_names}
    for facet in _ee4_trace_facet_displays(result):
        if facet.name.lower() in names:
            return facet.tag
    return ""


def _draw_ee4_face_allocation_table(
    c: canvas.Canvas,
    result: CalculationResult,
    *,
    x: float,
    top_y: float,
    w: float,
    max_rows: int = 4,
) -> None:
    rows = _ee4_face_allocation_rows(result)
    if not rows:
        return

    visible = rows[:max_rows]
    row_h = 0.145 * inch
    h = row_h * (len(visible) + 1)
    y = top_y - h
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.55)
    c.rect(x, y, w, h, fill=1, stroke=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7.1)
    c.drawCentredString(x + w / 2, top_y - row_h + 0.045 * inch,
                        "FACE ALLOCATION")
    c.setLineWidth(0.35)
    c.line(x, top_y - row_h, x + w, top_y - row_h)

    yy = top_y - row_h * 1.70
    for row in visible:
        c.setFillColor(colors.HexColor(row.fill_hex))
        c.setStrokeColor(colors.HexColor(row.stroke_hex))
        c.setLineWidth(0.55)
        c.rect(x + 0.05 * inch, yy - 0.03 * inch,
               0.17 * inch, 0.10 * inch, fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.setStrokeColor(colors.black)
        c.setFont("Helvetica", 6.6)
        facet_tag = _ee4_facet_tag_for_sections(result, row.section_names)
        prefix = f"{facet_tag} " if facet_tag else ""
        line = (
            f"{prefix}P{row.priority} {row.direction}  "
            f"AZ {row.azimuth_deg:.0f}  {row.modules} MOD"
        )
        c.drawString(
            x + 0.27 * inch, yy - 0.005 * inch,
            fit(line, "Helvetica", 6.6, w - 0.33 * inch),
        )
        yy -= row_h


def _ee4_face_allocation_caption(result: CalculationResult) -> str:
    rows = _ee4_face_allocation_rows(result)
    if not rows:
        return ""
    return "FACE ALLOCATION: " + "; ".join(
        f"P{row.priority} {row.direction} {row.modules} MOD"
        for row in rows
    )


def _draw_ee4_site_notes(
    c: canvas.Canvas,
    result: CalculationResult,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
) -> None:
    i = result.inputs
    from ..calc.site_layout import house_bbox

    hx0, hy0, hx1, hy1 = house_bbox(i.site)
    front_ft = max(0.0, i.site.lot_depth_ft - hy1)
    rear_ft = max(0.0, hy0)
    side_ft = max(0.0, min(hx0, i.site.lot_width_ft - hx1))

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, y + h - 0.18 * inch, "SITE PLAN NOTES")
    c.setFont("Helvetica", 7.0)
    notes = [
        "ALL OBSTRUCTIONS MUST BE VERIFIED BEFORE WORK COMMENCES",
        "CONDUIT TO BE RUN IN ATTIC IF POSSIBLE",
        "VISIBLE / LOCKABLE / LABELED UTILITY AC DISCONNECT WILL BE INSTALLED",
        "AC DISCONNECT SHALL BE READILY ACCESSIBLE 24/7",
        "REQUIRED ELECTRICAL CLEARANCE TO BE MAINTAINED",
        "METER / SERVICE PANEL LOCATION TO BE FIELD VERIFIED",
        f"Front yard setback {front_ft:.0f}' / Rear yard setback "
        f"{rear_ft:.0f}' / Side yard setback {side_ft:.0f}'",
    ]
    yy = y + h - 0.33 * inch
    for idx, note in enumerate(notes, 1):
        c.drawString(x + 0.08 * inch, yy, f"{idx}.")
        c.drawString(x + 0.27 * inch, yy,
                     fit(note, "Helvetica", 7.0, w - 0.35 * inch))
        yy -= 0.105 * inch
    c.setFont("Helvetica-Oblique", 6.6)
    c.drawString(
        x, y + 0.02 * inch,
        "NOTE: EQUIPMENT LOCATIONS ARE DEFINED BUT MAY BE APPROXIMATE "
        "DUE TO EXISTING CONDITIONS",
    )


def _draw_ee4_module_callout(
    c: canvas.Canvas,
    result: CalculationResult,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
) -> None:
    mod = result.inputs.pv_array.module
    c.setStrokeColor(colors.HexColor("#1F5BD7"))
    c.setLineWidth(0.8)
    box_w = min(w * 0.58, 0.40 * inch)
    box_h = min(h * 0.78, 0.64 * inch)
    bx = x + w - box_w - 0.02 * inch
    by = y + 0.10 * inch
    c.rect(bx, by, box_w, box_h)
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.55)
    # Dimension ticks.
    c.line(bx, by + box_h + 0.10 * inch, bx + box_w, by + box_h + 0.10 * inch)
    c.line(bx, by + box_h + 0.05 * inch, bx, by + box_h + 0.15 * inch)
    c.line(bx + box_w, by + box_h + 0.05 * inch,
           bx + box_w, by + box_h + 0.15 * inch)
    c.line(bx - 0.13 * inch, by, bx - 0.13 * inch, by + box_h)
    c.line(bx - 0.18 * inch, by, bx - 0.08 * inch, by)
    c.line(bx - 0.18 * inch, by + box_h, bx - 0.08 * inch, by + box_h)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 6.6)
    c.drawCentredString(bx + box_w / 2, by + box_h + 0.16 * inch,
                        f'{mod.width_in:.2f}"')
    c.saveState()
    c.translate(bx - 0.19 * inch, by + box_h / 2)
    c.rotate(90)
    c.drawCentredString(0, 0, f'{mod.length_in:.2f}"')
    c.restoreState()
    c.drawCentredString(x + w / 2, y - 0.02 * inch,
                        f"{mod.brand.upper()} {mod.model}")
    c.drawCentredString(x + w / 2, y - 0.13 * inch, "MODULES")
    c.setStrokeColor(colors.black)


def _draw_ee4_roof_plan(
    c: canvas.Canvas,
    result: CalculationResult,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
) -> None:
    from ..calc.site_layout import house_bbox
    from ..calc.wire_routing import _face_local_to_site

    i = result.inputs
    sections = i.site.roof_sections
    bounds = _ee4_drawing_bounds(result)
    if bounds is None:
        return
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
    scale = min(w / bw, h / bh)
    ox = x + (w - bw * scale) / 2
    oy = y + (h - bh * scale) / 2

    def to_pt(pt: tuple[float, float]) -> tuple[float, float]:
        return (ox + (pt[0] - min_x) * scale,
                oy + (pt[1] - min_y) * scale)

    trace_active = _ee4_trace_active(i.site)
    trace = i.site.ee4_trace
    satellite_drawn, mask_candidate = _draw_ee4_satellite_underlay(
        c, result, to_pt, clip_rect=(x, y, w, h),
    )
    if mask_candidate is not None:
        _draw_ee4_mask_contour_candidate(
            c, mask_candidate,
            to_pt=to_pt,
            clip_rect=(x, y, w, h),
            label_x=x + 0.08 * inch,
            label_y=y + h - 0.41 * inch,
            draw_label=False,
        )

    # Light house footprint context, cropped to the roof/equipment view.
    hx0, hy0, hx1, hy1 = house_bbox(i.site)
    if not trace_active:
        c.setFillColor(colors.white)
        c.setStrokeColor(colors.HexColor("#CBD5E1"))
        c.setLineWidth(0.35)
        if i.site.house_outline_vertices:
            path = c.beginPath()
            p0 = to_pt(i.site.house_outline_vertices[0])
            path.moveTo(*p0)
            for p in i.site.house_outline_vertices[1:]:
                path.lineTo(*to_pt(p))
            path.close()
            c.drawPath(path, stroke=1, fill=0 if satellite_drawn else 1)
        else:
            p0 = to_pt((hx0, hy0))
            p1 = to_pt((hx1, hy1))
            c.rect(p0[0], p0[1], p1[0] - p0[0], p1[1] - p0[1],
                   stroke=1, fill=0 if satellite_drawn else 1)

    # Small property-line cue, enough for plan semantics without letting
    # the full lot rectangle dominate the page. The main drawing is
    # cropped to roof/equipment extents, so drawing the true 90x125 ft
    # lot box here would spill off the sheet.
    c.setDash(5, 3)
    c.setStrokeColor(colors.HexColor("#94A3B8"))
    c.line(x + 0.08 * inch, y + h - 0.16 * inch,
           x + 1.55 * inch, y + h - 0.16 * inch)
    c.setDash()
    c.setFillColor(colors.HexColor("#475569"))
    c.setFont("Helvetica-Oblique", 6.6)
    c.drawString(x + 0.08 * inch, y + h - 0.10 * inch,
                 "PROPERTY LINE (dashed)")

    # Street/address label along the left property edge.
    if i.project.site_address:
        c.saveState()
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 11)
        c.translate(x - 0.14 * inch, y + h * 0.52)
        c.rotate(90)
        c.drawCentredString(0, 0, i.project.site_address.upper())
        c.restoreState()

    if trace_active:
        _draw_ee4_trace_roof(c, trace, to_pt, fill_outline=True)
        _draw_ee4_face_allocation_overlay(
            c, result, to_pt,
            draw_fill=False,
            draw_labels=False,
            line_width=0.85,
        )
        _draw_ee4_trace_fire_pathways(c, trace, to_pt)
        _draw_ee4_trace_roof(c, trace, to_pt, fill_outline=False)
        _draw_ee4_face_allocation_overlay(
            c, result, to_pt,
            draw_fill=False,
            draw_labels=False,
            line_width=1.05,
            label_size=5.7,
        )
        _draw_ee4_obstruction_halos(c, result, to_pt)
    else:
        # Fire offset bands under roof outlines.
        for section in sections:
            if section.site_anchor_x_ft is None or section.shape != "rect":
                continue
            outer = _ee4_section_points(section)
            if len(outer) < 4:
                continue
            eave = section.edge_setback_for("eave")
            ridge = section.edge_setback_for("ridge")
            rake = section.edge_setback_for("rake")
            inset_w = section.width_ft - 2 * rake
            inset_h = section.height_ft - eave - ridge
            if inset_w <= 0 or inset_h <= 0:
                continue
            inner_local = [
                (rake, eave),
                (rake + inset_w, eave),
                (rake + inset_w, eave + inset_h),
                (rake, eave + inset_h),
            ]
            inner = [
                _face_local_to_site(section, px, py)
                for px, py in inner_local
            ]
            inner = [p for p in inner if p is not None]
            _draw_fire_path_band(
                c,
                [to_pt(p) for p in outer],
                [to_pt(p) for p in inner],
            )

        # Roof outlines + simple hip/ridge facets.
        for section in sections:
            pts = _ee4_section_points(section)
            if len(pts) < 3:
                continue
            pt_pts = [to_pt(p) for p in pts]
            _draw_poly(c, pt_pts, stroke=colors.black, fill=None, width=0.75)
            cx = sum(p[0] for p in pt_pts) / len(pt_pts)
            cy = sum(p[1] for p in pt_pts) / len(pt_pts)
            c.setStrokeColor(colors.black)
            c.setLineWidth(0.45)
            for px, py in pt_pts:
                c.line(cx, cy, px, py)
        if not _ee4_untraced_roof_segment_schematic(i.site):
            _draw_ee4_face_allocation_overlay(
                c, result, to_pt,
                draw_fill=False,
                draw_labels=False,
                line_width=1.0,
                label_size=5.7,
            )

    # Real modules.  When a reviewed trace is active, this helper keeps
    # the drawn rectangles in the traced roof coordinate frame instead of
    # the coarse Google Solar segment-box frame.
    module_bounds: list[tuple[float, float, float, float]] = []
    c.setStrokeColor(colors.HexColor("#1F5BD7"))
    c.setFillColor(colors.HexColor("#EEF4FF"))
    c.setLineWidth(0.55)
    for module in ee4_module_geometries(result):
        pts = [to_pt(p) for p in module.corners]
        draw_pv_module(c, pts, width=0.55)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        module_bounds.append((min(xs), min(ys), max(xs), max(ys)))

    if trace_active:
        _draw_ee4_trace_symbols(c, trace, to_pt)
        _draw_ee4_trace_facet_identifiers(
            c, result, to_pt,
            draw_labels=True,
            line_width=0.82,
        )
    else:
        # Common rooftop obstruction symbols. These are schematic, but the
        # legend now has matching shapes and the plan no longer looks empty.
        _draw_ee4_roof_symbols(c, result, to_pt)

    if mask_candidate is not None:
        _draw_ee4_mask_contour_candidate(
            c, mask_candidate,
            to_pt=to_pt,
            clip_rect=(x, y, w, h),
            label_x=x + 0.08 * inch,
            label_y=y + h - 0.41 * inch,
            satellite_label=_ee4_satellite_underlay_label(
                result.inputs.site.satellite_alignment.mode
            ),
            draw_path=False,
        )

    # Fire offset labels.
    many_schematic_faces = len(sections) > 8 and not trace_active
    label_section = next((s for s in sections if s.site_anchor_x_ft is not None),
                         None)
    if many_schematic_faces:
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.white)
        c.setStrokeColor(colors.white)
        label = '18" FIRE OFFSET (NEC 690.12)'
        label_x = x + w * 0.48
        label_y = y + h - 0.42 * inch
        c.rect(label_x - 0.04 * inch, label_y - 0.045 * inch,
               c.stringWidth(label, "Helvetica", 7) + 0.08 * inch,
               0.13 * inch, fill=1, stroke=0)
        c.setFillColor(colors.black)
        c.setStrokeColor(colors.black)
        c.drawString(label_x, label_y, label)
    elif label_section is not None:
        start = to_pt((
            label_section.site_anchor_x_ft + label_section.width_ft * 0.55,
            label_section.site_anchor_y_ft + label_section.height_ft + 0.7,
        ))
        end = (start[0] + 0.55 * inch, start[1] + 0.62 * inch)
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.45)
        c.line(start[0], start[1], start[0], end[1])
        c.line(start[0], end[1], end[0], end[1])
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.white)
        c.setStrokeColor(colors.white)
        c.rect(end[0] + 0.01 * inch, end[1] - 0.045 * inch,
               1.24 * inch, 0.13 * inch, fill=1, stroke=0)
        c.setFillColor(colors.black)
        c.drawString(end[0] + 0.02 * inch, end[1] - 2,
                     '18" FIRE OFFSET (NEC 690.12)')

    c.setFont("Helvetica", 7)
    label36_x, label36_y = _ee4_36_fire_offset_label_position(x, y, w, h)
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.white)
    c.rect(label36_x - 0.04 * inch, label36_y - 0.045 * inch,
           0.92 * inch, 0.13 * inch, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)
    c.drawString(label36_x, label36_y, '36" FIRE OFFSET')
    c.line(label36_x - 0.18 * inch, label36_y + 2,
           label36_x - 0.02 * inch, label36_y + 2)

    # Routed conduit overlay.
    wr = result.wire_routing
    if wr is not None and wr.routed:
        c.setStrokeColor(colors.HexColor("#EA580C"))
        c.setLineWidth(1.4)
        c.setDash(5, 3)
        for seg in wr.segments:
            if len(seg.waypoints_ft) < 2 or seg.label.startswith("A "):
                continue
            pts = _decompose_manhattan(seg.waypoints_ft)
            path = c.beginPath()
            path.moveTo(*to_pt(pts[0]))
            for p in pts[1:]:
                path.lineTo(*to_pt(p))
            c.drawPath(path, stroke=1, fill=0)
        c.setDash()
        c.setStrokeColor(colors.black)

    _draw_ee4_equipment_leaders(c, result, to_pt, x, y, w, h)
    _draw_ee4_optimizer_callout(c, result, module_bounds, x, y, w, h)
    if _ee4_untraced_roof_segment_schematic(i.site):
        _draw_ee4_roof_geometry_warning(c, x, y, w, h)

    # PV array caption.
    kw_dc = i.pv_array.modules * i.pv_array.module.power_w / 1000.0
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 8)
    caption = (f"PV ARRAY · {i.pv_array.modules} MODULES · "
               f"{kw_dc:.2f} kW DC")
    if _ee4_untraced_roof_segment_schematic(i.site):
        caption += " · SCHEMATIC ROOF GEOMETRY"
    c.drawString(x + 0.10 * inch, y + 0.08 * inch, caption)


def _ee4_drawing_bounds(
    result: CalculationResult,
) -> Optional[tuple[float, float, float, float]]:
    pts: list[tuple[float, float]] = []
    trace = result.inputs.site.ee4_trace
    if _ee4_trace_active(result.inputs.site):
        if trace.roof_outline is not None:
            pts.extend(trace.roof_outline.vertices)
        for poly in trace.roof_facets:
            pts.extend(poly.vertices)
        for poly in trace.fire_pathways:
            pts.extend(poly.vertices)
        for line in trace.roof_lines:
            pts.extend(line.points)
        for symbol in trace.symbols:
            pts.append((symbol.x_ft, symbol.y_ft))
        for module in ee4_module_geometries(result):
            pts.extend(module.corners)
    else:
        for section in result.inputs.site.roof_sections:
            pts.extend(_ee4_section_points(section))
            for m in result.module_placements.get(section.name, []):
                pts.extend(_ee4_module_site_points(section, m))
    el = result.inputs.site.equipment_locations
    for item in _ee4_equipment_items(el):
        pts.append((item[1], item[2]))
    if el.attic_drop_x_ft is not None and el.attic_drop_y_ft is not None:
        pts.append((el.attic_drop_x_ft, el.attic_drop_y_ft))
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _ee4_trace_active(site) -> bool:
    trace = getattr(site, "ee4_trace", None)
    return bool(trace is not None and trace.enabled and trace.has_geometry)


def _ee4_untraced_roof_segment_schematic(site) -> bool:
    """True when EE-4 is showing Google Solar-style segment boxes.

    `roof_sections` from Google Solar buildingInsights include pitch,
    azimuth, and rough area, but not the actual house roof outline or the
    relative vertices of each plane. With many untraced square segments, the
    renderer can only produce a capacity/layout schematic. That state must be
    visibly marked so it is not mistaken for AHJ-ready roof geometry.
    """
    if _ee4_trace_active(site):
        return False
    sections = list(getattr(site, "roof_sections", []) or [])
    if len(sections) <= 8:
        return False
    if getattr(site, "house_outline_vertices", None):
        return False
    if any(getattr(section, "vertices", None) for section in sections):
        return False
    return True


def _draw_ee4_roof_geometry_warning(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
) -> None:
    """Draw a visible but compact warning for untraced roof geometry."""
    box_x = x + 0.10 * inch
    box_y = y + h - 0.50 * inch
    box_w = min(w - 0.20 * inch, 4.65 * inch)
    box_h = 0.36 * inch
    c.setFillColor(colors.HexColor("#FFF7ED"))
    c.setStrokeColor(colors.HexColor("#EA580C"))
    c.setLineWidth(0.75)
    c.roundRect(box_x, box_y, box_w, box_h, 6, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#C2410C"))
    c.setFont("Helvetica-Bold", 7.4)
    c.drawString(box_x + 0.08 * inch, box_y + 0.22 * inch,
                 "DRAFT ROOF GEOMETRY - SCHEMATIC ROOF SEGMENTS")
    c.setFillColor(colors.HexColor("#7C2D12"))
    c.setFont("Helvetica", 6.2)
    c.drawString(
        box_x + 0.08 * inch,
        box_y + 0.09 * inch,
        "Actual roof outline is not traced; verify with satellite or field "
        "survey before AHJ submittal.",
    )


def _draw_ee4_trace_roof(
    c: canvas.Canvas,
    trace,
    to_pt,
    *,
    fill_outline: bool,
) -> None:
    """Draw Stage 9 permit-style traced roof linework."""
    if trace.roof_outline is not None:
        draw_roof_outline(
            c,
            [to_pt(p) for p in trace.roof_outline.vertices],
            fill=fill_outline,
        )
    for facet in trace.roof_facets:
        draw_roof_facet(c, [to_pt(p) for p in facet.vertices])
    for line in trace.roof_lines:
        pts = [to_pt(p) for p in line.points]
        if len(pts) < 2:
            continue
        draw_roof_line(c, pts, kind=line.kind)


def _draw_ee4_trace_fire_pathways(
    c: canvas.Canvas,
    trace,
    to_pt,
) -> None:
    for poly in trace.fire_pathways:
        draw_fire_pathway(c, [to_pt(p) for p in poly.vertices])


def _draw_ee4_obstruction_halos(
    c: canvas.Canvas,
    result: CalculationResult,
    to_pt,
) -> None:
    """Draw no-panel obstruction areas on traced roof sheets.

    `ee4_trace.symbols` marks the obstruction center.  The engineering
    keepout, however, lives on `site.roof_sections[].obstructions` in local
    roof-face coordinates.  Rendering that halo on the traced plan makes the
    CAD-reviewed no-panel areas visible on both PV-2 and PV-4.
    """
    from ..calc.wire_routing import _face_local_to_site

    for section in result.inputs.site.roof_sections:
        for obs in section.obstructions:
            halo = [
                (obs.x_ft - obs.setback_ft, obs.y_ft - obs.setback_ft),
                (
                    obs.x_ft + obs.width_ft + obs.setback_ft,
                    obs.y_ft - obs.setback_ft,
                ),
                (
                    obs.x_ft + obs.width_ft + obs.setback_ft,
                    obs.y_ft + obs.height_ft + obs.setback_ft,
                ),
                (
                    obs.x_ft - obs.setback_ft,
                    obs.y_ft + obs.height_ft + obs.setback_ft,
                ),
            ]
            inner = [
                (obs.x_ft, obs.y_ft),
                (obs.x_ft + obs.width_ft, obs.y_ft),
                (obs.x_ft + obs.width_ft, obs.y_ft + obs.height_ft),
                (obs.x_ft, obs.y_ft + obs.height_ft),
            ]
            halo_site = [
                _face_local_to_site(section, px, py)
                for px, py in halo
            ]
            inner_site = [
                _face_local_to_site(section, px, py)
                for px, py in inner
            ]
            if any(p is None for p in halo_site + inner_site):
                continue
            halo_pts = [to_pt(p) for p in halo_site if p is not None]
            inner_pts = [to_pt(p) for p in inner_site if p is not None]
            _draw_hatched_keepout(c, halo_pts)
            _draw_poly(
                c,
                inner_pts,
                stroke=colors.HexColor("#92400E"),
                fill=colors.white,
                width=0.45,
            )
            _draw_keepout_label(c, halo_pts, "NP")


def _draw_ee4_face_allocation_overlay(
    c: canvas.Canvas,
    result: CalculationResult,
    to_pt,
    *,
    draw_fill: bool = True,
    draw_labels: bool = True,
    line_width: float = 1.15,
    label_size: float = 5.8,
) -> None:
    """Color-code active roof faces and annotate their module allocation."""
    rows = _ee4_face_allocation_rows(result)
    if not rows:
        return
    by_direction = {row.direction: row for row in rows}

    for section in result.inputs.site.roof_sections:
        direction = _ee4_face_direction_label(section.azimuth_deg)
        row = by_direction.get(direction)
        if row is None:
            continue
        pts = _ee4_section_points(section)
        if len(pts) < 3:
            continue
        pt_pts = [to_pt(p) for p in pts]
        if draw_fill:
            _draw_poly(
                c,
                pt_pts,
                stroke=colors.HexColor(row.stroke_hex),
                fill=colors.HexColor(row.fill_hex),
                width=0.35,
            )
        stroke = colors.HexColor(row.stroke_hex) if draw_labels else CAD_BLACK
        stroke_width = line_width if draw_labels else min(line_width, 0.62)
        _draw_poly(
            c,
            pt_pts,
            stroke=stroke,
            fill=None,
            width=stroke_width,
        )
        if draw_labels:
            _draw_ee4_face_allocation_label(
                c,
                row,
                pt_pts,
                label_size=label_size,
            )
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)


def _draw_ee4_trace_facet_identifiers(
    c: canvas.Canvas,
    result: CalculationResult,
    to_pt,
    *,
    draw_labels: bool = True,
    line_width: float = 0.75,
) -> None:
    """Mark each traced roof facet boundary with an F# identifier."""
    for facet in _ee4_trace_facet_displays(result):
        pt_pts = [to_pt(p) for p in facet.vertices]
        if len(pt_pts) < 3:
            continue
        _draw_poly(
            c,
            pt_pts,
            stroke=CAD_BLACK,
            fill=None,
            width=line_width,
        )
        if draw_labels:
            _draw_ee4_trace_facet_tag(c, facet, pt_pts)
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)


def _draw_ee4_trace_facet_tag(
    c: canvas.Canvas,
    facet: EE4TraceFacetDisplay,
    pts: list[tuple[float, float]],
) -> None:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    width = max(x1 - x0, 1.0)
    height = max(y1 - y0, 1.0)
    if facet.priority is not None:
        label = f"{facet.tag}/P{facet.priority}"
    else:
        label = f"{facet.tag} NO PV"
    font = "Helvetica-Bold"
    size = 5.4 if facet.modules else 5.1
    # Place active PV facet tags near the upper-left edge where the reviewed
    # Frisco plan has fire-path space; non-PV context uses a lower-left tag.
    if facet.direction == "SOUTH":
        bx = x0 + min(width * 0.12, 0.24 * inch)
        by = y0 + min(height * 0.18, 0.30 * inch)
    elif facet.modules:
        bx = x0 + min(width * 0.10, 0.18 * inch)
        by = y1 - min(height * 0.18, 0.20 * inch) - size
    else:
        bx = x0 + min(width * 0.16, 0.25 * inch)
        by = y0 + min(height * 0.38, 0.46 * inch)
    by = max(y0 + 2.0, min(by, y1 - size - 2.0))
    draw_facet_tag(c, bx, by, label, font=font, size=size)


def _draw_ee4_face_allocation_label(
    c: canvas.Canvas,
    row: EE4FaceAllocation,
    pts: list[tuple[float, float]],
    *,
    label_size: float,
) -> None:
    if len(pts) < 3:
        return
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    width = max(x1 - x0, 1.0)
    height = max(y1 - y0, 1.0)
    label = f"P{row.priority} {row.direction} | {row.modules} MOD"
    font = "Helvetica-Bold"
    text_w = c.stringWidth(label, font, label_size)
    label_w = min(text_w, max(0.72 * inch, width * 0.84))
    label = fit(label, font, label_size, label_w)
    text_w = c.stringWidth(label, font, label_size)
    bx = x0 + min(width * 0.10, 0.20 * inch)
    by = y1 - min(height * 0.18, 0.22 * inch) - label_size - 2.2
    if by < y0 + 2.0:
        by = y0 + 2.0
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.HexColor(row.stroke_hex))
    c.setLineWidth(0.35)
    c.rect(bx - 2.2, by - 1.8, text_w + 4.4, label_size + 3.8,
           fill=1, stroke=1)
    c.setFillColor(colors.HexColor(row.stroke_hex))
    c.setFont(font, label_size)
    c.drawString(bx, by, label)
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)


def _draw_hatched_keepout(
    c: canvas.Canvas,
    pts: list[tuple[float, float]],
) -> None:
    if len(pts) < 3:
        return
    draw_keepout_area(c, pts)


def _draw_keepout_label(
    c: canvas.Canvas,
    pts: list[tuple[float, float]],
    label: str,
) -> None:
    if len(pts) < 3:
        return
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    size = 4.8
    text_w = c.stringWidth(label, "Helvetica-Bold", size)
    if width < text_w + 4.0 or height < size + 3.0:
        return
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)
    x0 = cx - text_w / 2 - 1.8
    y0 = cy - size / 2 - 1.2
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.white)
    c.rect(x0, y0, text_w + 3.6, size + 2.4, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#92400E"))
    c.setFont("Helvetica-Bold", size)
    c.drawCentredString(cx, cy - size * 0.35, label)


def _draw_ee4_trace_symbols(
    c: canvas.Canvas,
    trace,
    to_pt,
) -> None:
    for symbol in trace.symbols:
        px, py = to_pt((symbol.x_ft, symbol.y_ft))
        draw_roof_symbol(c, px, py, symbol.kind, size=6.4)


def _ee4_section_points(section) -> list[tuple[float, float]]:
    from ..calc.wire_routing import _face_local_to_site

    if section.site_anchor_x_ft is None:
        return []
    if section.shape == "polygon":
        local = section.vertices
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


def _ee4_module_site_points(section, module) -> list[tuple[float, float]]:
    from ..calc.wire_routing import _face_local_to_site

    local = [
        (module.x_ft, module.y_ft),
        (module.x_ft + module.width_ft, module.y_ft),
        (module.x_ft + module.width_ft, module.y_ft + module.height_ft),
        (module.x_ft, module.y_ft + module.height_ft),
    ]
    pts = [_face_local_to_site(section, px, py) for px, py in local]
    return [p for p in pts if p is not None]


def _draw_poly(
    c: canvas.Canvas,
    pts: list[tuple[float, float]],
    *,
    stroke,
    fill,
    width: float,
) -> None:
    if len(pts) < 3:
        return
    c.setStrokeColor(stroke)
    if fill is not None:
        c.setFillColor(fill)
    c.setLineWidth(width)
    path = c.beginPath()
    path.moveTo(*pts[0])
    for pt in pts[1:]:
        path.lineTo(*pt)
    path.close()
    c.drawPath(path, stroke=1, fill=1 if fill is not None else 0)
    c.setStrokeColor(colors.black)
    c.setFillColor(colors.black)


def _truthy_env(name: str) -> bool:
    import os
    return os.environ.get(name, "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _draw_ee4_satellite_underlay(
    c: canvas.Canvas,
    result: CalculationResult,
    to_pt,
    *,
    clip_rect: tuple[float, float, float, float],
) -> tuple[bool, object | None]:
    """Stage 6 — optional Google Solar aerial underlay for EE-4.

    Gate behaviour:
      * `PVESS_EE4_SATELLITE=1` opts the sheet into satellite drawing.
      * `PVESS_ALLOW_PAID_RENDERS=1` allows a dataLayers network call
        when the aerial PNG is not already cached.
      * Without the paid gate, this reads cache only and silently skips.

    The placement is an approximate north-up calibration overlay:
    Google Solar dataLayers returns a square centred on the project
    lat/lng; we align that centre to the house bbox centre in the EE-4
    site coordinate frame. Stage 7 can replace this with mask-derived
    georeferencing / vector extraction.
    """
    if not _truthy_env("PVESS_EE4_SATELLITE"):
        return False, None

    from .cover_maps import (
        coordinates_to_lat_lng,
        fetch_aerial_map_png,
        fetch_satellite_assets_cached,
    )
    from ..calc.site_layout import house_bbox

    lat_lng = coordinates_to_lat_lng(result.inputs.project.coordinates)
    if lat_lng is None:
        return False, None

    radius_m = 35.0
    allow_network = _truthy_env("PVESS_ALLOW_PAID_RENDERS")
    assets = fetch_satellite_assets_cached(
        *lat_lng,
        radius_m=radius_m,
        cache=True,
        allow_network=allow_network,
    )
    if assets is not None:
        png_bytes = _rgb_array_to_png_bytes(assets.rgb)
    else:
        png_bytes = fetch_aerial_map_png(
            *lat_lng,
            radius_m=radius_m,
            cache=True,
            allow_network=allow_network,
        )
    if png_bytes is None:
        return False, None

    try:
        from reportlab.lib.utils import ImageReader
        import io

        faded = _fade_png_bytes(png_bytes)
        reader = ImageReader(io.BytesIO(faded))
    except Exception:
        return False, None

    hx0, hy0, hx1, hy1 = house_bbox(result.inputs.site)
    cx = (hx0 + hx1) / 2
    cy = (hy0 + hy1) / 2
    alignment = result.inputs.site.satellite_alignment
    center_site_ft = (
        alignment.center_x_ft if alignment.center_x_ft is not None else cx,
        alignment.center_y_ft if alignment.center_y_ft is not None else cy,
    )
    radius_ft = radius_m * 3.28084
    p0 = to_pt((cx - radius_ft, cy - radius_ft))
    p1 = to_pt((cx + radius_ft, cy + radius_ft))
    img_x = min(p0[0], p1[0])
    img_y = min(p0[1], p1[1])
    img_w = abs(p1[0] - p0[0])
    img_h = abs(p1[1] - p0[1])
    if img_w <= 0 or img_h <= 0:
        return False, None

    clip_x, clip_y, clip_w, clip_h = clip_rect
    c.saveState()
    clip = c.beginPath()
    clip.rect(clip_x, clip_y, clip_w, clip_h)
    c.clipPath(clip, stroke=0, fill=0)
    c.drawImage(reader, img_x, img_y, width=img_w, height=img_h,
                preserveAspectRatio=False, mask="auto")
    c.setStrokeColor(colors.HexColor("#94A3B8"))
    c.setLineWidth(0.35)
    c.rect(img_x, img_y, img_w, img_h, stroke=1, fill=0)
    mask_candidate = None
    if assets is not None:
        from ..calc.mask_contour import contour_from_mask
        from ..customer.roof_satellite import target_component_from_mask

        target_component = target_component_from_mask(
            assets.mask,
            assets.target_px,
        )
        contour_mask = (
            target_component.mask if target_component is not None
            else assets.mask
        )
        mask_candidate = contour_from_mask(
            contour_mask,
            radius_m=radius_m,
            center_site_ft=center_site_ft,
            simplify_ft=alignment.contour_simplify_ft,
            max_vertices=alignment.contour_max_vertices,
        )
        mask_candidate = _apply_ee4_mask_alignment(
            mask_candidate,
            house_bbox_ft=(hx0, hy0, hx1, hy1),
            center_site_ft=center_site_ft,
            alignment=alignment,
        )
    if mask_candidate is None:
        label = _ee4_satellite_underlay_label(alignment.mode)
        c.setFont("Helvetica-Oblique", 6.5)
        _draw_white_text_backdrop(c, clip_x + 0.08 * inch,
                                  clip_y + clip_h - 0.28 * inch,
                                  label, font="Helvetica-Oblique", size=6.5)
        c.drawString(clip_x + 0.08 * inch, clip_y + clip_h - 0.28 * inch,
                     label)
    c.restoreState()
    return True, mask_candidate


def _apply_ee4_mask_alignment(
    candidate,
    *,
    house_bbox_ft: tuple[float, float, float, float],
    center_site_ft: tuple[float, float],
    alignment,
):
    if candidate is None:
        return None

    from ..calc.mask_contour import (
        fit_candidate_to_bbox,
        transform_candidate,
    )

    origin = center_site_ft
    if alignment.mode == "fit_house_bbox":
        candidate = fit_candidate_to_bbox(
            candidate,
            house_bbox_ft,
            preserve_aspect=False,
            source_suffix="fit_house_bbox",
        )
        x0, y0, x1, y1 = house_bbox_ft
        origin = ((x0 + x1) / 2, (y0 + y1) / 2)

    needs_manual_transform = (
        alignment.mode == "manual"
        or abs(alignment.scale_x - 1.0) > 1e-9
        or abs(alignment.scale_y - 1.0) > 1e-9
        or abs(alignment.rotation_deg) > 1e-9
        or abs(alignment.x_offset_ft) > 1e-9
        or abs(alignment.y_offset_ft) > 1e-9
    )
    if needs_manual_transform:
        candidate = transform_candidate(
            candidate,
            origin_ft=origin,
            scale_x=alignment.scale_x,
            scale_y=alignment.scale_y,
            rotation_deg=alignment.rotation_deg,
            offset_ft=(alignment.x_offset_ft, alignment.y_offset_ft),
            source_suffix="manual",
        )
    return candidate


def _ee4_satellite_underlay_label(mode: str) -> str:
    if mode == "fit_house_bbox":
        return "SATELLITE UNDERLAY (APPROX., FIT HOUSE BBOX)"
    if mode == "manual":
        return "SATELLITE UNDERLAY (APPROX., MANUAL ALIGN)"
    return "SATELLITE UNDERLAY (APPROX., NORTH-UP)"


def _rgb_array_to_png_bytes(rgb) -> bytes:
    import io
    from PIL import Image

    img = Image.fromarray(rgb.astype("uint8"), mode="RGB")
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _draw_ee4_mask_contour_candidate(
    c: canvas.Canvas,
    candidate,
    *,
    to_pt,
    align_center_ft: tuple[float, float] | None = None,
    clip_rect: tuple[float, float, float, float] | None = None,
    label_x: float,
    label_y: float,
    satellite_label: str = "",
    draw_path: bool = True,
    draw_label: bool = True,
) -> bool:
    """Draw Stage 7 review-only roof contour from the Solar mask."""
    if candidate is None or candidate.vertex_count < 3:
        return False

    vertices = list(candidate.site_vertices_ft)
    if align_center_ft is not None:
        xs = [p[0] for p in vertices]
        ys = [p[1] for p in vertices]
        bbox_cx = (min(xs) + max(xs)) / 2
        bbox_cy = (min(ys) + max(ys)) / 2
        dx = align_center_ft[0] - bbox_cx
        dy = align_center_ft[1] - bbox_cy
        vertices = [(px + dx, py + dy) for px, py in vertices]

    if draw_path:
        pts = [to_pt(p) for p in vertices]
        if clip_rect is not None:
            clip_x, clip_y, clip_w, clip_h = clip_rect
            c.saveState()
            clip = c.beginPath()
            clip.rect(clip_x, clip_y, clip_w, clip_h)
            c.clipPath(clip, stroke=0, fill=0)

        c.setStrokeColor(colors.HexColor("#16A34A"))
        c.setLineWidth(0.85)
        c.setDash(4, 2)
        path = c.beginPath()
        path.moveTo(*pts[0])
        for p in pts[1:]:
            path.lineTo(*p)
        path.close()
        c.drawPath(path, stroke=1, fill=0)
        c.setDash()
        if clip_rect is not None:
            c.restoreState()

    if not draw_label:
        return True

    if satellite_label:
        c.setFont("Helvetica-Oblique", 6.5)
        _draw_white_text_backdrop(
            c, label_x, label_y + 0.13 * inch, satellite_label,
            font="Helvetica-Oblique", size=6.5,
        )
        c.setFillColor(colors.black)
        c.drawString(label_x, label_y + 0.13 * inch, satellite_label)

    label = (
        f"MASK CONTOUR CANDIDATE - REVIEW "
        f"({_ee4_candidate_source_label(candidate.source)}, "
        f"{candidate.vertex_count} VERTICES, {candidate.area_sqft:.0f} SQFT)"
    )
    c.setFont("Helvetica-Oblique", 6.5)
    _draw_white_text_backdrop(
        c, label_x, label_y, label,
        font="Helvetica-Oblique", size=6.5,
    )
    c.setFillColor(colors.HexColor("#166534"))
    c.drawString(label_x, label_y, label)
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)
    return True


def _ee4_candidate_source_label(source: str) -> str:
    if "fit_house_bbox" in source:
        return "FIT HOUSE BBOX"
    if "manual" in source:
        return "MANUAL ALIGN"
    return "RAW MASK"


def _fade_png_bytes(png_bytes: bytes) -> bytes:
    """Blend an aerial PNG toward white so vector lines stay dominant."""
    import io
    from PIL import Image

    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    white = Image.new("RGB", img.size, "white")
    # 62% white keeps aerial context visible without competing with CAD
    # linework and blue module outlines.
    faded = Image.blend(img, white, 0.62)
    out = io.BytesIO()
    faded.save(out, format="PNG")
    return out.getvalue()


def _draw_white_text_backdrop(
    c: canvas.Canvas,
    x: float,
    y: float,
    text: str,
    *,
    font: str = "Helvetica",
    size: float = 7.0,
    pad_x: float = 2.0,
    pad_y: float = 1.2,
) -> None:
    width = c.stringWidth(text, font, size)
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.white)
    c.rect(x - pad_x, y - pad_y, width + pad_x * 2,
           size + pad_y * 2, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)


def _draw_fire_path_band(
    c: canvas.Canvas,
    outer_pts: list[tuple[float, float]],
    inner_pts: list[tuple[float, float]],
) -> None:
    """Draw EE-4 fire-access pathway as pale fill plus orange hatch.

    The earlier Stage 2 path used a solid orange band. That was readable
    but visually heavier than the Wyssling-style reference, where the
    firecode pathway is an orange hatch texture over a light background.
    """
    if len(outer_pts) < 3 or len(inner_pts) < 3:
        return
    draw_fire_pathway(c, outer_pts)
    draw_closed_polygon(
        c,
        inner_pts,
        stroke=FIRE_ORANGE,
        fill=colors.white,
        width=0.25,
    )


def _draw_fire_path_polygon(
    c: canvas.Canvas,
    pts: list[tuple[float, float]],
) -> None:
    """Draw a Stage 9 hand-traced fire pathway polygon with hatch."""
    if len(pts) < 3:
        return
    draw_fire_pathway(c, pts)


def _draw_ee4_roof_symbols(
    c: canvas.Canvas,
    result: CalculationResult,
    to_pt,
) -> None:
    sections = [s for s in result.inputs.site.roof_sections
                if s.site_anchor_x_ft is not None]
    if not sections:
        return
    s = sections[0]
    symbols = [
        ("roof_vent", s.site_anchor_x_ft + s.width_ft * 0.30,
         s.site_anchor_y_ft + s.height_ft * 0.58),
        ("plumbing", s.site_anchor_x_ft + s.width_ft * 0.58,
         s.site_anchor_y_ft + s.height_ft * 0.46),
        ("chimney", s.site_anchor_x_ft + s.width_ft * 0.70,
         s.site_anchor_y_ft + s.height_ft * 0.70),
        ("satellite", s.site_anchor_x_ft + s.width_ft * 0.50,
         s.site_anchor_y_ft + s.height_ft * 0.88),
    ]
    for kind, fx, fy in symbols:
        px, py = to_pt((fx, fy))
        draw_roof_symbol(c, px, py, kind, size=6.4)


def _ee4_equipment_items(el) -> list[tuple[str, float, float, str]]:
    items: list[tuple[str, float, float, str]] = []
    if el.msp is not None:
        items.append((el.msp.label or "MAIN SERVICE PANEL",
                      el.msp.x_ft, el.msp.y_ft, "(N)"))
    if el.ac_disconnect is not None:
        items.append((el.ac_disconnect.label or "AC DISCONNECT",
                      el.ac_disconnect.x_ft, el.ac_disconnect.y_ft, "(N)"))
    for idx, inv in enumerate(el.inverters, 1):
        items.append((inv.label or f"INVERTER #{idx}",
                      inv.x_ft, inv.y_ft, "(N)"))
    for idx, sp in enumerate(el.sub_panels, 1):
        items.append((sp.label or f"SUB PANEL #{idx}",
                      sp.x_ft, sp.y_ft, "(N)"))
    for idx, ess in enumerate(el.ess_units, 1):
        items.append((ess.label or f"ESS #{idx}",
                      ess.x_ft, ess.y_ft, "(N)"))
    return items


def _draw_ee4_equipment_leaders(
    c: canvas.Canvas,
    result: CalculationResult,
    to_pt,
    x: float,
    y: float,
    w: float,
    h: float,
) -> None:
    items = _ee4_equipment_items(result.inputs.site.equipment_locations)
    if not items:
        return
    items = sorted(items, key=lambda it: -it[2])
    label_x, label_y, row_h = _ee4_equipment_label_layout(x, y, w, h)
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.45)
    c.setFont("Helvetica", 7.0)
    for idx, (label, fx, fy, mark) in enumerate(items):
        px, py = to_pt((fx, fy))
        c.rect(px - 3.5, py - 3.5, 7, 7, fill=1, stroke=1)
        tx = label_x
        ty = label_y + (len(items) - 1 - idx) * row_h
        label_text = f"{mark} {_ee4_equipment_leader_label(label)}"
        c.line(px, py - 3.5, px, ty + 0.08 * inch)
        c.line(px, ty + 0.08 * inch, tx - 0.04 * inch, ty + 0.08 * inch)
        _draw_white_text_backdrop(c, tx, ty, label_text, size=7.0)
        c.drawString(tx, ty, label_text)

    c.setFont("Helvetica", 7.0)
    access = "FIRE DEPARTMENT ACCESS"
    access_y = label_y - 0.18 * inch
    _draw_white_text_backdrop(c, label_x, access_y, access, size=7.0)
    c.drawString(label_x, access_y, access)


def _ee4_equipment_label_layout(
    x: float,
    y: float,
    w: float,
    h: float,
) -> tuple[float, float, float]:
    """Return the right-side equipment label stack origin.

    Stage 9.5: keep labels near the lower roof edge instead of down at
    the title-block footer. This shortens leaders while preserving clear
    separation from the 36" fire-offset callout and module dimension box.
    """
    del h
    return (x + w - 1.32 * inch, y + 0.62 * inch, 0.13 * inch)


def _ee4_equipment_leader_label(label: str) -> str:
    """Return concise permit-style equipment text for leader callouts."""
    upper = (label or "").upper().strip()
    if upper == "MSP":
        return "MAIN SERVICE PANEL"
    if upper.startswith("INV-"):
        ident = upper.split()[0].replace("INV-", "").strip("-")
        if ident:
            return f"INVERTER #{ident}"
        return "INVERTER"
    if upper.startswith("AC DISC"):
        return "AC DISCONNECT"
    return upper


def _ee4_36_fire_offset_label_position(
    x: float,
    y: float,
    w: float,
    h: float,
) -> tuple[float, float]:
    """Return the 36" fire-offset label position for traced EE-4 sheets."""
    del h
    return (x + w - 1.24 * inch, y + 1.18 * inch)


def _draw_ee4_optimizer_callout(
    c: canvas.Canvas,
    result: CalculationResult,
    module_bounds: list[tuple[float, float, float, float]],
    x: float,
    y: float,
    w: float,
    h: float,
) -> None:
    optimizer = result.inputs.optimizer
    if not optimizer.brand or not module_bounds:
        return
    if _ee4_trace_active(result.inputs.site):
        # Stage 9.1: traced EE-4 sheets use the highest module as the
        # MLPE leader target. Picking the rightmost module produced a
        # long diagonal across the equipment column after the Frisco
        # array was shifted into a permit-style main cluster.
        target = max(module_bounds, key=lambda b: (b[3], -b[0]))
    else:
        target = max(module_bounds, key=lambda b: b[2] + b[3])
    tx = (target[0] + target[2]) / 2
    ty = (target[1] + target[3]) / 2
    end_x = x + w - 1.68 * inch
    end_y = y + h - 0.45 * inch
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.45)
    if _ee4_trace_active(result.inputs.site):
        elbow_y = end_y - 0.08 * inch
        c.line(tx, ty, tx, elbow_y)
        c.line(tx, elbow_y, end_x, elbow_y)
    else:
        c.line(tx, ty, end_x - 0.16 * inch, end_y)
        c.line(end_x - 0.16 * inch, end_y, end_x, end_y)
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 7.0)
    n_opt = optimizer.effective_count(
        result.inputs.pv_array.modules,
        result.inputs.pv_array.strings,
    )
    ratio = 1
    if n_opt > 0:
        ratio = max(1, result.inputs.pv_array.modules // n_opt)
    line1 = "(N) PV MODULE EQUIPPED W/ (1)"
    line2 = f"OPTIMIZER PER ({ratio}) MODULES"
    _draw_white_text_backdrop(c, end_x, end_y + 0.02 * inch, line1, size=7.0)
    c.drawString(end_x, end_y + 0.02 * inch, line1)
    _draw_white_text_backdrop(c, end_x, end_y - 0.10 * inch, line2, size=7.0)
    c.drawString(end_x, end_y - 0.10 * inch, line2)


def _draw_conduit_overlay(
    c, result, *,
    lot_x: float, lot_y: float,
    lot_w_pt: float, lot_h_pt: float,
    page_w: float,
    px_per_ft: float,
) -> None:
    """K.11 + K.11.7 + Stage B — overlay per-face roof geometry, real
    K.9.1 modules, and (when wire routing is active) the auto-routed
    conduit polyline + equipment leader callouts.

    Two activation gates:
      * `has_face_anchors` (any site_anchor set) →
        fire-offset hatch + real module rects + array caption.
        Available whenever the engine successfully auto-anchored OR
        the yaml provides explicit anchors.
      * `routed` (wire_routing.routed=True) →
        conduit polyline + equipment leader-line callouts + legend
        strip + optimizer annotation. Requires equipment_locations
        in the yaml.

    Returns early (no-op) when neither gate is open — legacy yamls
    keep the K.6 painted PV-box + east-wall column drawn earlier.
    """
    wr = result.wire_routing
    sections = result.inputs.site.roof_sections
    has_face_anchors = any(
        s.site_anchor_x_ft is not None for s in sections
    )
    routed = wr is not None and wr.routed
    if not has_face_anchors and not routed:
        return
    el = result.inputs.site.equipment_locations

    def ft_to_pt(xy: tuple[float, float]) -> tuple[float, float]:
        return (lot_x + xy[0] * px_per_ft, lot_y + xy[1] * px_per_ft)

    # K.11.7f — Wyssling-style site-plan overlay. Layer order:
    #   0. Per-face setback band + fire-offset hatch (background)
    #   1. Real K.9.1 modules in single light-blue outline (no
    #      K.10 string colors; that detail lives on PV-4)
    #   2. Module count caption + "FIRE OFFSET" callouts
    #   3. Conduit polyline (true Manhattan dog-legs)
    #   4. Equipment leader-line callouts
    #   5. Optimizer annotation (when inputs.optimizer is populated)
    from ..calc.wire_routing import _face_local_to_site

    # ── Layer 0: per-face fire-offset hatch ──────────────────────────
    # For each roof_section with a site_anchor, draw the band BETWEEN
    # the section outline and its inset (= setback distance shrunk).
    # Use orange diagonal hatch at 45° to match the Wyssling reference.
    has_fire_offset = False
    for section in sections:
        if section.site_anchor_x_ft is None:
            continue
        if section.shape != "rect":
            # Non-rect faces fall back to no fire-offset band on EE-4;
            # PV-4 has the per-face geometry drawn properly.
            continue
        # Section outer outline (transformed to site)
        outer_local = [(0.0, 0.0), (section.width_ft, 0.0),
                       (section.width_ft, section.height_ft),
                       (0.0, section.height_ft)]
        outer_site = [_face_local_to_site(section, x, y)
                      for x, y in outer_local]
        outer_site = [p for p in outer_site if p is not None]
        if len(outer_site) < 4:
            continue
        # Inner outline = inset by max edge_setback
        eave_sb = section.edge_setback_for("eave")
        ridge_sb = section.edge_setback_for("ridge")
        rake_sb = section.edge_setback_for("rake")
        inset_w = section.width_ft - 2 * rake_sb
        inset_h = section.height_ft - eave_sb - ridge_sb
        if inset_w <= 0 or inset_h <= 0:
            continue
        inner_local = [(rake_sb, eave_sb),
                       (rake_sb + inset_w, eave_sb),
                       (rake_sb + inset_w, eave_sb + inset_h),
                       (rake_sb, eave_sb + inset_h)]
        inner_site = [_face_local_to_site(section, x, y)
                      for x, y in inner_local]

        # Draw the outer rect with hatch fill, then overlay the inner
        # rect in white to "erase" the inside — gives us the band.
        c.setStrokeColor(colors.HexColor("#D97706"))
        c.setLineWidth(0.4)
        c.setFillColor(colors.HexColor("#FFE4B5"))
        outer_path = c.beginPath()
        x0, y0 = ft_to_pt(outer_site[0])
        outer_path.moveTo(x0, y0)
        for sp in outer_site[1:]:
            xx, yy = ft_to_pt(sp)
            outer_path.lineTo(xx, yy)
        outer_path.close()
        c.drawPath(outer_path, fill=1, stroke=1)
        # Knock out the inner rect with white fill
        c.setFillColor(colors.white)
        c.setStrokeColor(colors.HexColor("#D97706"))
        c.setLineWidth(0.3)
        # Reportlab doesn't support hole punching cleanly; draw inner
        # as a SOLID white rect over the hatch (works for axis-aligned
        # rectangles where azimuth is 0 — the common case).
        if section.site_anchor_azimuth_deg == 0.0:
            ix, iy = ft_to_pt(inner_site[0])
            iw = inset_w * px_per_ft
            ih = inset_h * px_per_ft
            c.rect(ix, iy, iw, ih, fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.setStrokeColor(colors.black)
        has_fire_offset = True

    # "FIRE OFFSET" label — small caption near the array, only when
    # we actually drew at least one hatch band.
    if has_fire_offset and sections:
        # Pull the first section's eave setback for the label number.
        s0 = next((s for s in sections
                   if s.site_anchor_x_ft is not None), None)
        if s0 is not None:
            eave_in = s0.edge_setback_for("eave") * 12
            c.setFont("Helvetica", 7)
            c.setFillColor(colors.HexColor("#92400E"))
            label_pt = ft_to_pt((
                s0.site_anchor_x_ft + s0.width_ft / 2,
                s0.site_anchor_y_ft + s0.height_ft + 0.5,
            ))
            c.drawCentredString(label_pt[0], label_pt[1],
                                f'{eave_in:.0f}" FIRE OFFSET '
                                f'(NEC 690.12)')
            c.setFillColor(colors.black)

    # ── Layer 1: real K.9.1 modules at site-plan scale ───────────────
    c.setFillColor(colors.HexColor("#DCE7FF"))
    c.setStrokeColor(colors.HexColor("#1F5BD7"))
    c.setLineWidth(0.35)
    module_corners_all: list[tuple[float, float, float, float]] = []
    for section in sections:
        if section.site_anchor_x_ft is None:
            continue
        for m in result.module_placements.get(section.name, []):
            corners_local = [
                (m.x_ft,              m.y_ft),
                (m.x_ft + m.width_ft, m.y_ft),
                (m.x_ft + m.width_ft, m.y_ft + m.height_ft),
                (m.x_ft,              m.y_ft + m.height_ft),
            ]
            corners_site = [_face_local_to_site(section, x, y)
                            for x, y in corners_local]
            corners_site = [p for p in corners_site if p is not None]
            if len(corners_site) < 4:
                continue
            path = c.beginPath()
            x0, y0 = ft_to_pt(corners_site[0])
            path.moveTo(x0, y0)
            for sp in corners_site[1:]:
                xx, yy = ft_to_pt(sp)
                path.lineTo(xx, yy)
            path.close()
            c.drawPath(path, stroke=1, fill=1)
            module_corners_all.append((
                corners_site[0][0], corners_site[0][1],
                corners_site[2][0], corners_site[2][1],
            ))
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)

    # ── Layer 2: PV array caption (banner above the lot) ─────────────
    # K.13.1 P1 — moved from bottom margin to TOP banner. Pre-K.13.1
    # the caption sat at `lot_y - 0.48"` and collided with the leader-
    # callout column when stacked_below=True (3+ equipment chips
    # stack horizontally below the lot). The top banner area shares
    # space only with the conduit legend chip (when routed), and
    # those are arranged left-vs-right to avoid overlap.
    if module_corners_all:
        n_mods = result.inputs.pv_array.modules
        kw_dc = n_mods * result.inputs.pv_array.module.power_w / 1000.0
        caption_text = f"PV ARRAY · {n_mods} MODULES · {kw_dc:.2f} kW DC"
        # Banner y just above the lot frame
        caption_y = lot_y + lot_h_pt + 0.22 * inch
        # Anchor on the left side of the banner; conduit legend
        # (Layer 4 below) renders centred / right of this when routed.
        caption_x = lot_x + 0.10 * inch
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(colors.HexColor("#1F2937"))
        c.drawString(caption_x, caption_y - 2, caption_text)
        c.setFillColor(colors.black)

    # ── Layer 3: true-Manhattan conduit polyline (routed only) ───────
    # The wire_routing waypoints are KEY POINTS, not orthogonal
    # decomposition — at this layer we insert an L-shaped dog-leg
    # between each consecutive pair (horizontal-first heuristic, so
    # the run hugs the eave/wall before turning toward equipment).
    if routed:
        c.setStrokeColor(colors.HexColor("#EA580C"))   # ROUTE_COLOR
        c.setLineWidth(1.6)
        c.setDash(5, 3)
        for seg in wr.segments:
            if len(seg.waypoints_ft) < 2:
                continue
            if seg.label.startswith("A "):    # on-roof segment, skip
                continue
            manhattan_pts = _decompose_manhattan(seg.waypoints_ft)
            path = c.beginPath()
            x0, y0 = ft_to_pt(manhattan_pts[0])
            path.moveTo(x0, y0)
            for sp in manhattan_pts[1:]:
                xx, yy = ft_to_pt(sp)
                path.lineTo(xx, yy)
            c.drawPath(path, stroke=1, fill=0)
        c.setDash()
        c.setLineWidth(1.0)
        c.setStrokeColor(colors.black)

    # ── Layer 4: Wyssling-style equipment leader-line callouts ───────
    # Industry-standard residential PV site plan convention:
    #   * Each equipment piece is a SMALL filled black rectangle (the
    #     wall-mounted cabinet) drawn at its real (x, y) on the house
    #     wall.
    #   * From each rectangle a THIN black leader line extends down
    #     (or sideways) to a text label OUTSIDE the house.
    #   * Labels follow the "(N) INVERTER #1" / "(E) ONCOR METER"
    #     convention: (N) = new, (E) = existing.
    #   * All text labels are left-aligned in a column for readability.
    # This replaces the old K.11.7c colored chip stack which violated
    # site-plan conventions (chips were too prominent and used color
    # to distinguish equipment that should just be marked with text).

    # Collect the equipment items in physical-position order (south →
    # north along the wall) for clean leader stacking.
    eq_items = []   # list of (label, x_ft, y_ft, ne_marker)
    if routed and el.msp is not None:
        eq_items.append((el.msp.label or "MAIN SERVICE PANEL",
                         el.msp.x_ft, el.msp.y_ft, "(N)"))
    if routed and el.ac_disconnect is not None:
        eq_items.append((el.ac_disconnect.label or "AC DISCONNECT",
                         el.ac_disconnect.x_ft,
                         el.ac_disconnect.y_ft, "(N)"))
    if routed:
        for idx, inv in enumerate(el.inverters, 1):
            lbl = inv.label or f"INVERTER #{idx}"
            eq_items.append((lbl, inv.x_ft, inv.y_ft, "(N)"))
        for idx, sp in enumerate(el.sub_panels, 1):
            lbl = sp.label or f"SUB PANEL #{idx}"
            eq_items.append((lbl, sp.x_ft, sp.y_ft, "(N)"))
        for idx, ess in enumerate(el.ess_units, 1):
            lbl = ess.label or f"ESS #{idx}"
            eq_items.append((lbl, ess.x_ft, ess.y_ft, "(N)"))

    if eq_items:
        # Tiny wall-mounted box per equipment, in site coords
        BOX_W_FT = 1.2
        BOX_H_FT = 1.2
        c.setFillColor(colors.HexColor("#1F2937"))
        c.setStrokeColor(colors.HexColor("#1F2937"))
        c.setLineWidth(0.4)
        for label, fx, fy, _ in eq_items:
            box_pt = ft_to_pt((fx - BOX_W_FT / 2, fy - BOX_H_FT / 2))
            c.rect(*box_pt,
                   BOX_W_FT * px_per_ft, BOX_H_FT * px_per_ft,
                   fill=1, stroke=1)

        # Text column: label stack BELOW the page-frame footer, with
        # one leader line per equipment from its rect to its label.
        # We anchor the column at a fixed x just outside the lot
        # bottom so the labels read like a "schedule" off the drawing.
        label_col_x = lot_x + lot_w_pt + 0.20 * inch
        # If the right column would overrun the page edge, fall back
        # to BELOW the lot (label column horizontal at lot_y - …).
        if label_col_x + 1.8 * inch > page_w - 3.4 * inch:
            # Stack labels BELOW the lot, equipment leaders go down
            label_col_x = lot_x + 0.30 * inch
            label_col_y_top = lot_y - 0.40 * inch
            stacked_below = True
        else:
            label_col_y_top = (lot_y + lot_h_pt
                               - 0.20 * inch)   # start near top of lot
            stacked_below = False

        c.setFont("Helvetica", 7)
        c.setFillColor(colors.black)
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.4)
        row_h = 0.14 * inch
        for i_eq, (label, fx, fy, ne) in enumerate(eq_items):
            label_text = f"{ne} {label.upper()}"
            if stacked_below:
                lx = label_col_x + i_eq * 1.6 * inch
                ly = label_col_y_top - 0.06 * inch
                c.drawString(lx, ly, label_text)
                # Vertical leader from label up to box
                box_x_pt, box_y_pt = ft_to_pt((fx, fy - BOX_H_FT / 2))
                c.line(lx + 0.05 * inch, ly + 0.10 * inch,
                       lx + 0.05 * inch, box_y_pt)
                c.line(lx + 0.05 * inch, box_y_pt, box_x_pt, box_y_pt)
            else:
                ly = label_col_y_top - i_eq * row_h
                c.drawString(label_col_x + 0.08 * inch, ly, label_text)
                # Leader: from rect's right edge → horizontal segment →
                # short kick to label start
                box_right_pt = ft_to_pt((fx + BOX_W_FT / 2, fy))
                bend_x = label_col_x
                c.line(box_right_pt[0], box_right_pt[1],
                       bend_x, box_right_pt[1])
                c.line(bend_x, box_right_pt[1],
                       bend_x + 0.06 * inch, ly + 0.03 * inch)

    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)

    # ── Legend strip (RIGHT side of top banner) ──────────────────────
    # K.13.1 P1 — right-anchored. Pre-K.13.1 the conduit legend was
    # centered across the top banner; with the PV ARRAY caption now
    # also on this banner (left-anchored), the legend moved right.
    # Only rendered when routing is active (the legend describes the
    # orange conduit line which only exists in routed mode).
    if routed:
        legend_y = lot_y + lot_h_pt + 0.22 * inch
        info_x_pt = page_w - 3.4 * inch
        legend_right = info_x_pt - 0.20 * inch
        conduit_label = "conduit (auto-routed, Manhattan)"
        c.setFont("Helvetica", 7)
        conduit_text_w = c.stringWidth(conduit_label, "Helvetica", 7)
        total_w = 0.30 * inch + conduit_text_w
        row_left = legend_right - total_w
        c.setStrokeColor(colors.HexColor("#EA580C"))
        c.setLineWidth(1.4)
        c.setDash(5, 3)
        c.line(row_left, legend_y, row_left + 0.24 * inch, legend_y)
        c.setDash()
        c.setStrokeColor(colors.black)
        c.drawString(row_left + 0.30 * inch, legend_y - 2, conduit_label)

    # ── Layer 5: optimizer annotation ────────────────────────────────
    # K.13.1 P0 — relocated INSIDE the lot's upper-right (back-yard)
    # area, away from the SITE INFORMATION column. Pre-K.13.1 the
    # endpoint was at `lot_x + lot_w_pt + 0.20 inch` which sat
    # exactly on top of the right-column "Lot dimensions" row.
    #
    # New placement: above the array bbox, inside the lot. Lots are
    # always tall enough (back-yard area > 30 ft) to accommodate the
    # 2-line label without overlapping the modules below.
    optimizer = result.inputs.optimizer
    if (optimizer is not None and optimizer.brand
            and module_corners_all):
        target = max(module_corners_all,
                     key=lambda c_: c_[0] + (c_[3] - c_[1]))
        tx_pt = (target[0] + target[2]) / 2
        ty_pt = (target[1] + target[3]) / 2

        # Endpoint: top-right inside the lot.
        # Width budget: "(N) PV MODULE EQUIPPED W/" ≈ 1.5" at 7pt.
        # Reserve 1.7" from the right lot edge for the text + leader bend.
        end_x = lot_x + lot_w_pt - 1.70 * inch
        end_y = lot_y + lot_h_pt - 0.45 * inch

        c.setStrokeColor(colors.HexColor("#1F2937"))
        c.setLineWidth(0.5)
        # Two-segment leader: target module → vertical exit upward
        # → horizontal to text. Vertical-first keeps the leader from
        # crossing other module rows in the array.
        c.line(tx_pt, ty_pt, tx_pt, end_y)
        c.line(tx_pt, end_y, end_x - 0.04 * inch, end_y)
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.HexColor("#1F2937"))
        n_opt = optimizer.effective_count(
            result.inputs.pv_array.modules,
            result.inputs.pv_array.strings,
        )
        n_mods = result.inputs.pv_array.modules
        ratio = (f"{n_opt} OPTIMIZER PER {n_mods // n_opt or 1} MODULES"
                 if n_opt > 0 else "OPTIMIZER")
        c.drawString(end_x, end_y - 2,
                     "(N) PV MODULE EQUIPPED W/")
        c.drawString(end_x, end_y - 11, ratio.upper())
        c.setFillColor(colors.black)
        c.setStrokeColor(colors.black)


def _draw_aerial_inset(
    c, result, *,
    x: float, y: float, w: float, h: float,
) -> None:
    """K.11.7 — render a top-down aerial photo of the roof under the
    SITE INFORMATION column. Pulls Google Solar dataLayers when
    `PVESS_GOOGLE_SOLAR_KEY` is set. Graceful placeholder otherwise.

    Coordinates: `(x, y)` is the bottom-left corner of the inset box;
    `w` × `h` is the box size in reportlab points.
    """
    from .cover_maps import coordinates_to_lat_lng, fetch_aerial_map_png

    # Frame + title strip
    c.setLineWidth(0.6)
    c.setStrokeColor(colors.HexColor("#94a3b8"))
    c.rect(x, y, w, h, fill=0, stroke=1)
    c.setStrokeColor(colors.HexColor("#1F5BD7"))
    c.setFillColor(colors.HexColor("#1F5BD7"))
    title_h = 0.20 * inch
    c.rect(x, y + h - title_h, w, title_h, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x + 0.08 * inch, y + h - title_h + 0.06 * inch, "AERIAL VIEW")
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)

    # Inner image area
    img_pad = 0.08 * inch
    img_x = x + img_pad
    img_y = y + img_pad
    img_w = w - 2 * img_pad
    img_h = h - title_h - 2 * img_pad

    lat_lng = coordinates_to_lat_lng(result.inputs.project.coordinates)
    png_bytes: Optional[bytes] = None
    if lat_lng is not None:
        try:
            # Stage C: bump radius 25 → 35 m so the neighbour-lot
            # context shows up alongside the subject building.
            # 25 m crops too tight on suburban lots ≥ 80 ft wide.
            png_bytes = fetch_aerial_map_png(*lat_lng, radius_m=35.0)
        except Exception:
            png_bytes = None

    if png_bytes is None:
        # Placeholder — light fill + explanation
        c.setFillColor(colors.HexColor("#F1F5F9"))
        c.setStrokeColor(colors.HexColor("#cbd5e1"))
        c.rect(img_x, img_y, img_w, img_h, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#64748b"))
        c.setFont("Helvetica", 8)
        msg_lines = ["PVESS_GOOGLE_SOLAR_KEY",
                     "not set — set the env var",
                     "to display aerial imagery."]
        for k, line in enumerate(msg_lines):
            c.drawCentredString(
                img_x + img_w / 2,
                img_y + img_h / 2 + (1 - k) * 0.14 * inch, line,
            )
        c.setFillColor(colors.black)
        c.setStrokeColor(colors.black)
        return

    # Got real PNG — draw via reportlab ImageReader
    try:
        from reportlab.lib.utils import ImageReader
        import io
        reader = ImageReader(io.BytesIO(png_bytes))
        c.drawImage(reader, img_x, img_y, width=img_w, height=img_h,
                    preserveAspectRatio=True, anchor="c", mask="auto")
        # Imagery date caption at the bottom
        c.setFont("Helvetica-Oblique", 6.5)
        c.setFillColor(colors.HexColor("#475569"))
        c.drawString(img_x, img_y - 0.02 * inch,
                     "Google Solar dataLayers · 25 m radius")
        c.setFillColor(colors.black)
    except Exception:
        # PNG decode failed — fall back to placeholder
        c.setFillColor(colors.HexColor("#F1F5F9"))
        c.rect(img_x, img_y, img_w, img_h, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#64748b"))
        c.setFont("Helvetica", 8)
        c.drawCentredString(img_x + img_w / 2, img_y + img_h / 2,
                            "image decode failed")
        c.setFillColor(colors.black)


def _draw_equipment_chip(
    c, center_pt: tuple[float, float],
    label: str, fill_hex: str,
    *, height_pt: float = 13.0,
) -> None:
    """Draw a single filled rounded chip centred on `center_pt`. Auto-
    sizes width to the label. Used by both the singleton path AND the
    multi-chip stack path so the visual is consistent."""
    px_, py_ = center_pt
    text_w = c.stringWidth(label, "Helvetica-Bold", 8)
    chip_w = max(text_w + 8, 30)
    c.setFillColor(colors.HexColor(fill_hex))
    c.setStrokeColor(colors.HexColor(fill_hex))
    c.setLineWidth(0.5)
    c.roundRect(
        px_ - chip_w / 2, py_ - height_pt / 2,
        chip_w, height_pt, 2, fill=1, stroke=1,
    )
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(px_, py_ - 2.5, label)


def _decompose_manhattan(
    waypoints: tuple,
) -> list[tuple[float, float]]:
    """Turn a list of key points into an orthogonal polyline.

    Between each consecutive pair (a, b) insert an L-bend at
    (b.x, a.y) so the run goes HORIZONTAL first, then VERTICAL.
    This matches typical install practice: hug the eave / ridge,
    then drop down the wall.

    If a → b is already orthogonal (same x or same y), no bend is
    inserted. Co-linear consecutive bends are merged.
    """
    if len(waypoints) < 2:
        return list(waypoints)
    out: list[tuple[float, float]] = [waypoints[0]]
    for prev, curr in zip(waypoints, waypoints[1:]):
        same_x = abs(curr[0] - prev[0]) < 1e-6
        same_y = abs(curr[1] - prev[1]) < 1e-6
        if not (same_x or same_y):
            bend = (curr[0], prev[1])
            out.append(bend)
        out.append(curr)
    return out


# ─── Dimension-line + scale-bar helpers ─────────────────────────────────


def _dim_line_vertical(
    c, *, x: float, y0: float, y1: float, label: str, side: str,
) -> None:
    """Draw a vertical dimension line with tick marks at both ends and a
    centered numeric label. `side='left'` puts the label to the left of
    the line; `side='right'` to the right."""
    if abs(y1 - y0) < 6:    # too short to label cleanly
        return
    c.setStrokeColor(_DIM_COLOR)
    c.setFillColor(_DIM_COLOR)
    c.setLineWidth(0.5)
    c.line(x, y0, x, y1)
    # Tick marks (5pt cross at each endpoint)
    for y in (y0, y1):
        c.line(x - 2.5, y, x + 2.5, y)
    # Label rotated 90° so it reads upward, centered vertically
    c.saveState()
    cy = (y0 + y1) / 2
    if side == "left":
        c.translate(x - 6, cy)
        c.rotate(90)
    else:
        c.translate(x + 6, cy)
        c.rotate(90)
    c.setFont("Helvetica", 7.5)
    c.drawCentredString(0, 0, label)
    c.restoreState()
    c.setStrokeColor(colors.black)
    c.setFillColor(colors.black)


def _dim_line_horizontal(
    c, *, y: float, x0: float, x1: float, label: str, side: str,
) -> None:
    """Horizontal dimension line + centered label below (or above)."""
    if abs(x1 - x0) < 6:
        return
    c.setStrokeColor(_DIM_COLOR)
    c.setFillColor(_DIM_COLOR)
    c.setLineWidth(0.5)
    c.line(x0, y, x1, y)
    for x in (x0, x1):
        c.line(x, y - 2.5, x, y + 2.5)
    cx = (x0 + x1) / 2
    c.setFont("Helvetica", 7.5)
    if side == "below":
        c.drawCentredString(cx, y - 9, label)
    else:
        c.drawCentredString(cx, y + 4, label)
    c.setStrokeColor(colors.black)
    c.setFillColor(colors.black)


def _draw_scale_bar(c, x: float, y: float, px_per_ft: float) -> None:
    """Scale bar with 4 segments at the largest 'nice' length that fits
    in ~1.6". The bar alternates filled / hollow blocks (architectural
    convention) and labels each tick mark in feet.

    Picks `nice_step` from a list of [5, 10, 20, 25, 50, 100] so the
    total bar length is ≤ 1.6". For typical residential lots (60-100
    ft wide) the 4-segment step lands at 5 or 10 ft.
    """
    bar_max_pt = 1.6 * inch
    nice_steps = [1, 2, 5, 10, 20, 25, 50, 100]
    # Pick the largest step that keeps total ≤ bar_max_pt
    step_ft = 5
    for s in nice_steps:
        if 4 * s * px_per_ft <= bar_max_pt:
            step_ft = s
    seg_w = step_ft * px_per_ft
    bar_h = 0.10 * inch
    c.setStrokeColor(colors.black)
    c.setFillColor(colors.black)
    c.setLineWidth(0.6)
    for k in range(4):
        bx = x + k * seg_w
        c.rect(bx, y, seg_w, bar_h, fill=(k % 2 == 0))
    # Tick labels: 0 step 2step 3step 4step
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 7)
    for k in range(5):
        bx = x + k * seg_w
        c.drawCentredString(bx, y - 9, f"{k * step_ft}")
    # Caption
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x, y + bar_h + 4, "SCALE (ft)")
