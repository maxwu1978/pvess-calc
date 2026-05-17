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
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from ..calc.engine import CalculationResult
from ._textfit import fit


# Visual token: dimension line / extension line styling.
_DIM_COLOR = colors.HexColor("#666666")
_ROUTE_COLOR = colors.HexColor("#D97706")    # warm orange = electrical route
_PV_COLOR = colors.HexColor("#FFE680")
_HOUSE_COLOR = colors.HexColor("#E8E8E8")


def render_site_plan(result: CalculationResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=landscape(letter))
    W, H = landscape(letter)
    i = result.inputs
    site = i.site

    c.setLineWidth(1.0)
    c.rect(0.4 * inch, 0.4 * inch, W - 0.8 * inch, H - 0.8 * inch)

    # Title strip — baseline 0.70" below the page top so that an 18pt
    # bold cap-height (~0.20") clears the outer frame line at H-0.40"
    # with ~0.10" of breathing room. Pre-K.11.7b polish had the title
    # at H-0.55", which let the ascenders cross the frame border.
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(W / 2, H - 0.70 * inch, "EE-4 · SITE PLAN")
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
    # K.11.7 — explicit "PROPERTY LINE" label so AHJ doesn't have to
    # infer it from the dashed style alone. Placed at the TOP-LEFT
    # corner OUTSIDE the lot so it doesn't collide with the legend
    # strip immediately below it.
    c.setFont("Helvetica-Oblique", 7)
    c.setFillColor(colors.HexColor("#475569"))
    c.drawString(lot_x - 0.08 * inch, lot_y + lot_h_pt + 0.04 * inch,
                 "PROPERTY LINE (dashed)")
    c.setFillColor(colors.black)

    # K.11.7f — rotated address along the LEFT property line (90° CCW).
    # Matches the Wyssling reference image style: street name vertical
    # outside the lot's street-facing edge. We treat the lot's
    # +y direction (toward back of property) as "street → house",
    # so the address sits on the lot's LEFT edge reading bottom-to-top.
    if i.project.site_address:
        c.saveState()
        c.setFillColor(colors.HexColor("#1F2937"))
        c.setFont("Helvetica-Bold", 11)
        # Anchor: just outside lot's left edge, centered vertically
        addr_x = lot_x - 0.30 * inch
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

    # K.11.7e — decide visual mode for K.11 overlay only. The PV array
    # box itself is now ALWAYS drawn as a single stylized rectangle
    # centered on the house (industry-standard site-plan convention).
    # Per-module / per-string detail belongs on PV-4 (attachment plan),
    # NOT on the site plan. Putting both detail levels in one drawing
    # leaks PV-4's content into EE-4 and makes the site-plan unreadable.
    routed = result.wire_routing is not None and result.wire_routing.routed

    # RESIDENCE label — always present (centered in house body)
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    c.drawCentredString(house_x + house_w_pt / 2,
                        house_y + house_h_pt * 0.30, "RESIDENCE")

    # K.11.7f — PV array rendering split path:
    #   * `routed=True` (full site geometry): draw REAL K.9.1 modules
    #     at site-plan scale via site_anchor transforms. Single light-
    #     blue outline per module (no K.10 string colors — that's PV-4).
    #     Per-roof-section setback bands + fire-offset hatching are
    #     drawn first as background, then modules on top. This matches
    #     the Wyssling-style residential site-plan convention.
    #   * `routed=False` (legacy yamls without site_anchor): keep the
    #     stylized PV ARRAY box + abstract module-count grid centered
    #     on the house roof (no real coordinates to use).
    pv = i.pv_array
    kw_dc = pv.modules * pv.module.power_w / 1000.0

    if not routed:
        # Legacy abstract grid (count-accurate but not at real coords)
        ax_w = ft_to_pt(site.array_width_ft)
        ax_h = ft_to_pt(site.array_depth_ft)
        array_x = house_x + (house_w_pt - ax_w) / 2
        array_y = house_y + house_h_pt - ax_h - 1 * px_per_ft
        c.setFillColor(_PV_COLOR)
        c.setStrokeColor(colors.HexColor("#1F5BD7"))
        c.setLineWidth(1.0)
        c.rect(array_x, array_y, ax_w, ax_h, fill=1, stroke=1)
        box_aspect = (ax_w / ax_h) if ax_h > 0 else 1.0
        n_cols, n_rows = _pick_module_grid(pv.modules, box_aspect)
        cell_w_pt = ax_w / n_cols
        cell_h_pt = ax_h / n_rows
        gap_pt = min(cell_w_pt, cell_h_pt) * 0.10
        c.setFillColor(colors.HexColor("#FCE96A"))
        c.setStrokeColor(colors.HexColor("#94B0E0"))
        c.setLineWidth(0.3)
        drawn = 0
        for r in range(n_rows):
            y = array_y + (n_rows - 1 - r) * cell_h_pt + gap_pt / 2
            for k in range(n_cols):
                if drawn >= pv.modules:
                    break
                x = array_x + k * cell_w_pt + gap_pt / 2
                c.rect(x, y, cell_w_pt - gap_pt, cell_h_pt - gap_pt,
                       fill=1, stroke=1)
                drawn += 1
        c.setFillColor(colors.HexColor("#1F2937"))
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(
            array_x + ax_w / 2, array_y - 0.18 * inch,
            f"PV ARRAY · {pv.modules} MODULES · {kw_dc:.2f} kW DC",
        )
        c.setFont("Helvetica-Oblique", 6.5)
        c.setFillColor(colors.HexColor("#475569"))
        c.drawCentredString(
            array_x + ax_w / 2, array_y - 0.30 * inch,
            f"{site.array_width_ft:.0f}' × {site.array_depth_ft:.0f}' · "
            f"{n_cols}×{n_rows} grid · see PV-4 for string assignment",
        )
        c.setFillColor(colors.black)
        c.setStrokeColor(colors.black)
    # Routed mode: real modules + fire-offset hatching are drawn by
    # _draw_conduit_overlay() below.

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
    # ONLY drawn in legacy mode — when K.11 is active the real equipment
    # dots + auto-routed conduit overlay take over (see _draw_conduit_overlay
    # at the bottom of render_site_plan).
    if not routed:
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
    info_x = W - 3.2 * inch
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

    # K.11.7 — aerial roof inset below SITE INFORMATION (right column).
    # Uses Google Solar dataLayers when PVESS_GOOGLE_SOLAR_KEY is set;
    # otherwise renders a "no aerial available" placeholder.
    _draw_aerial_inset(
        c, result,
        x=info_x, y=yy - 2.40 * inch,
        w=2.5 * inch, h=2.2 * inch,
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


def _draw_conduit_overlay(
    c, result, *,
    lot_x: float, lot_y: float,
    lot_w_pt: float, lot_h_pt: float,
    page_w: float,
    px_per_ft: float,
) -> None:
    """K.11 + K.11.7 — overlay real K.9.1 module rectangles + auto-
    routed conduit polyline + equipment chips on the EE-4 site plan.
    No-op when wire_routing.routed=False (legacy yamls keep the K.6
    painted PV-box + east-wall column drawn earlier in render_site_plan).

    Three layers (z-order from bottom up):
      1. Per-face roof outline (light fill) at its site_anchor position
      2. Each K.9.1 ModuleInstance as a tiny rect colored by string
         (K.10 palette — same as PV-4)
      3. True-Manhattan conduit polyline (orange dashed, orthogonal
         dog-legs) connecting roof penetration → attic drop →
         equipment chain → MSP
      4. Equipment chips (filled rounded rectangles with the label)
    """
    wr = result.wire_routing
    if wr is None or not wr.routed:
        return
    el = result.inputs.site.equipment_locations
    sections = result.inputs.site.roof_sections

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

    # ── Layer 2: PV array caption (under the array bbox) ─────────────
    if module_corners_all:
        all_xs = [c_[0] for c_ in module_corners_all] + [c_[2] for c_ in module_corners_all]
        all_ys = [c_[1] for c_ in module_corners_all] + [c_[3] for c_ in module_corners_all]
        bb_cx = (min(all_xs) + max(all_xs)) / 2
        bb_y_bot = min(all_ys)
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.HexColor("#1F2937"))
        c.drawCentredString(bb_cx, bb_y_bot - 0.16 * inch,
                            f"PV ARRAY · {result.inputs.pv_array.modules} "
                            f"MODULES · "
                            f"{result.inputs.pv_array.modules * result.inputs.pv_array.module.power_w / 1000:.2f} "
                            f"kW DC")
        c.setFont("Helvetica-Oblique", 6.5)
        c.setFillColor(colors.HexColor("#475569"))
        c.drawCentredString(bb_cx, bb_y_bot - 0.27 * inch,
                            "see PV-4 for per-module string assignment")
        c.setFillColor(colors.black)

    # ── Layer 3: true-Manhattan conduit polyline ─────────────────────
    # The wire_routing waypoints are KEY POINTS, not orthogonal
    # decomposition — at this layer we insert an L-shaped dog-leg
    # between each consecutive pair (horizontal-first heuristic, so
    # the run hugs the eave/wall before turning toward equipment).
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
    if el.msp is not None:
        eq_items.append((el.msp.label or "MAIN SERVICE PANEL",
                         el.msp.x_ft, el.msp.y_ft, "(N)"))
    if el.ac_disconnect is not None:
        eq_items.append((el.ac_disconnect.label or "AC DISCONNECT",
                         el.ac_disconnect.x_ft,
                         el.ac_disconnect.y_ft, "(N)"))
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

    # ── Legend strip (ABOVE the lot, under the title) ────────────────
    # K.11.7e — single conduit item now (no per-module legend; modules
    # aren't drawn on EE-4 anymore). Right-anchored against the SITE
    # INFORMATION column to guarantee no horizontal overlap.
    legend_y = lot_y + lot_h_pt + 0.22 * inch
    info_x_pt = page_w - 3.2 * inch
    legend_left  = lot_x + 0.10 * inch
    legend_right = info_x_pt - 0.20 * inch
    conduit_label = "conduit (auto-routed, Manhattan)"
    c.setFont("Helvetica", 7)
    conduit_text_w = c.stringWidth(conduit_label, "Helvetica", 7)
    total_w = 0.30 * inch + conduit_text_w
    row_left = legend_left + (legend_right - legend_left - total_w) / 2
    if row_left < legend_left:
        row_left = legend_left
    c.setStrokeColor(colors.HexColor("#EA580C"))
    c.setLineWidth(1.4)
    c.setDash(5, 3)
    c.line(row_left, legend_y, row_left + 0.24 * inch, legend_y)
    c.setDash()
    c.setStrokeColor(colors.black)
    c.drawString(row_left + 0.30 * inch, legend_y - 2, conduit_label)

    # ── Layer 5: optimizer annotation ────────────────────────────────
    # When inputs.optimizer is configured, annotate a single module
    # with a leader line out to "(N) PV MODULE EQUIPPED W/ (N)
    # OPTIMIZERS PER (N) MODULES" — matches the Wyssling reference.
    # Skipped when optimizer brand is empty (the schema default).
    optimizer = result.inputs.optimizer
    if (optimizer is not None and optimizer.brand
            and module_corners_all):
        # Pick a target module — top-right of the array bbox so the
        # leader can reach the upper-right margin without crossing
        # the conduit polyline.
        # module_corners_all entries are (x0, y0, x1, y1)
        target = max(module_corners_all,
                     key=lambda c_: c_[0] + (c_[3] - c_[1]))
        tx_pt = (target[0] + target[2]) / 2
        ty_pt = (target[1] + target[3]) / 2

        # Leader endpoint: top-right area outside the lot
        end_x = lot_x + lot_w_pt + 0.20 * inch
        end_y = lot_y + lot_h_pt - 0.30 * inch

        c.setStrokeColor(colors.HexColor("#1F2937"))
        c.setLineWidth(0.5)
        # Two-segment leader: module → horizontal exit → end
        bend_x = end_x - 0.15 * inch
        c.line(tx_pt, ty_pt, bend_x, ty_pt)
        c.line(bend_x, ty_pt, end_x - 0.04 * inch, end_y - 2)
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.HexColor("#1F2937"))
        # Optimizer count math: "1 per module" is the most common
        # K.10.1 install path. Use `effective_count` for accuracy.
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


def _pick_module_grid(
    n_mods: int, box_aspect: float,
) -> tuple[int, int]:
    """Pick (n_cols, n_rows) such that `n_cols × n_rows ≥ n_mods` and
    the grid aspect ratio is as close to `box_aspect` as possible.

    Strategy:
      1. Compute a target n_cols from `sqrt(n_mods × box_aspect)` —
         this gives a square-ish grid scaled to box aspect.
      2. Sweep ±3 around the target; for each candidate compute
         `n_rows = ceil(n_mods / n_cols)`.
      3. Prefer EXACT-fit grids (no empty cells); among exact, pick
         the one with aspect closest to box_aspect. Fall back to the
         non-exact closest-aspect candidate otherwise.

    Examples (box_aspect = 1.5 — typical "wider than tall" array):
      * 60 mods → (10, 6) exact
      * 36 mods → (8, 5) non-exact (40 cells, 4 empty bottom-right)
      * 34 mods → (8, 5) non-exact (40 cells, 6 empty)
      * 24 mods → (6, 4) exact
    """
    if n_mods <= 0:
        return 1, 1
    import math
    target = math.sqrt(n_mods * max(box_aspect, 0.1))
    candidates: list[tuple[int, int]] = []
    lo = max(1, int(target) - 3)
    hi = max(lo + 1, int(target) + 4)
    for nc in range(lo, hi + 1):
        nr = math.ceil(n_mods / nc)
        if nc * nr < n_mods or nr < 1:
            continue
        candidates.append((nc, nr))
    if not candidates:
        # Defensive fallback — shouldn't trip in practice
        return n_mods, 1

    def score(nc_nr: tuple[int, int]) -> float:
        nc, nr = nc_nr
        grid_aspect = nc / nr
        return abs(grid_aspect - box_aspect) / max(box_aspect, 0.1)

    exact = [(nc, nr) for nc, nr in candidates if nc * nr == n_mods]
    if exact:
        return min(exact, key=score)
    return min(candidates, key=score)


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
            png_bytes = fetch_aerial_map_png(*lat_lng, radius_m=25.0)
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
