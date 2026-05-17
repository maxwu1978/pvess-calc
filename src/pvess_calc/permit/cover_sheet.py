"""K.12.4 — Industry-standard PV-1 cover page (Wyssling-style).

12-block layout matching the AHJ-submittal convention used by major
US residential installers:

  ┌────────────────────────────────────────────────────────────────┐
  │  TITLE STRIP    (big headline + system size + address + ESID)  │
  ├─────────┬─────────┬────────────────────────────────────────────┤
  │  AERIAL │VICINITY │  SHEET INDEX  ·  SCOPE OF WORK             │
  │   MAP   │   MAP   │                                            │
  ├─────────┴─────────┼────────────────────────────────────────────┤
  │  GOVERNING CODES  │  DESIGN CRITERIA  ·  ROOF INFO             │
  ├───────────────────┴────────────────────────────────────────────┤
  │  INTERCONNECTION  ·  ARRAYS TABLE  ·  METER INFO               │
  ├──────────────────────────────────┬─────────────────────────────┤
  │  REVISION HISTORY                │  PE STAMP PLACEHOLDER       │
  └──────────────────────────────────┴─────────────────────────────┘

Every block reads from `result.inputs.project.*` and falls back to "—"
when a field is at its default — pre-K.12 yamls still render a
sensible cover with the legacy info, just without the new blocks
populated.

Maps are network-gated: aerial uses `PVESS_GOOGLE_SOLAR_KEY`,
vicinity uses `PVESS_MAPBOX_TOKEN`. When either is missing, the
corresponding panel shows a placeholder.
"""
from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from ..calc.engine import CalculationResult
from .cover_maps import (
    coordinates_to_lat_lng,
    fetch_aerial_map_png,
    fetch_vicinity_map_png,
)
from .sheet_registry import cover_index_rows


# ─── Public entry ──────────────────────────────────────────────────────


def render_cover_sheet(result: CalculationResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=landscape(letter))
    W, H = landscape(letter)
    i = result.inputs

    # Outer frame
    c.setLineWidth(1.0)
    c.rect(0.4 * inch, 0.4 * inch, W - 0.8 * inch, H - 0.8 * inch)

    # ── Title strip ────────────────────────────────────────────────
    _draw_title_strip(c, W, H, result)

    # ── Maps (left side, below title) ──────────────────────────────
    map_top_y = H - 1.5 * inch
    map_height = 2.0 * inch
    _draw_aerial_map(c,
                     x=0.6 * inch, y=map_top_y - map_height,
                     w=2.5 * inch, h=map_height,
                     coordinates=i.project.coordinates)
    _draw_vicinity_map(c,
                       x=3.3 * inch, y=map_top_y - map_height,
                       w=2.5 * inch, h=map_height,
                       coordinates=i.project.coordinates)

    # ── Sheet index + scope of work (right of maps) ────────────────
    # 2026-05-17 fix: scope-of-work needs ≥ 2.4" to fit
    # "14.94 kW DC  /  10.99 kW AC" without ellipsis. Sheet index needs
    # only ~1.6" (codes are short like "PV-1"). Reallocate.
    right_top_x = 6.1 * inch
    right_top_y = map_top_y
    sheet_w = 1.6 * inch
    _draw_sheet_index(c,
                      x=right_top_x, y=right_top_y,
                      w=sheet_w, h=map_height)
    _draw_scope_of_work(c,
                        x=right_top_x + sheet_w + 0.20 * inch,
                        y=right_top_y,
                        w=W - (right_top_x + sheet_w + 0.20 * inch)
                          - 0.5 * inch,
                        h=map_height, result=result)

    # ── Middle row: codes + design + roof ──────────────────────────
    # Geometry budget (8.5" landscape Letter):
    #   0.40"  bottom margin
    #   0.30"  footer text
    #   1.00"  bot row (revisions / PE stamp)         → y 0.50 - 1.50
    #   0.15"  gap
    #   1.20"  lower-middle row (interco / arrays / meter) → y 1.65 - 2.85
    #   0.15"  gap
    #   1.50"  middle row (codes / design / roof)     → y 3.00 - 4.50
    #   0.50"  gap
    #   2.00"  maps row                               → y 5.00 - 7.00
    #   0.10"  gap
    #   1.40"  title strip                            → y 7.10 - 8.50
    # ────────────────────────────────────────────────────────────────
    # 2026-05-17 bug fix: the old layout used mid_h=1.7 / low_h=1.7 /
    # bot_h=1.5 which together exceeded available vertical space — the
    # lower-middle row and the bottom row overlapped 1.3", causing
    # REVISION HISTORY headers to bleed into INTERCONNECTION and PE STAMP
    # to crash into METER INFO. New band heights leave ≥ 0.15" gap
    # between every adjacent pair.

    mid_y = H - 4.0 * inch       # top of codes/design/roof band = 4.5"
    mid_h = 1.5 * inch           # block: 3.00 to 4.50
    _draw_governing_codes(c,
                          x=0.6 * inch, y=mid_y - mid_h,
                          w=2.5 * inch, h=mid_h,
                          inputs=i)
    _draw_design_criteria(c,
                          x=3.3 * inch, y=mid_y - mid_h,
                          w=2.6 * inch, h=mid_h,
                          inputs=i)
    _draw_roof_info(c,
                    x=6.1 * inch, y=mid_y - mid_h,
                    w=W - 6.1 * inch - 0.5 * inch, h=mid_h,
                    inputs=i)

    # ── Lower-middle row: interconnect + arrays + meter ────────────
    low_y = H - 5.65 * inch      # top of band = 2.85"
    low_h = 1.20 * inch          # block: 1.65 to 2.85, gap above = 0.15
    _draw_interconnection(c,
                          x=0.6 * inch, y=low_y - low_h,
                          w=2.5 * inch, h=low_h,
                          result=result)
    _draw_arrays_table(c,
                       x=3.3 * inch, y=low_y - low_h,
                       w=3.4 * inch, h=low_h,
                       inputs=i)
    _draw_meter_info(c,
                     x=6.9 * inch, y=low_y - low_h,
                     w=W - 6.9 * inch - 0.5 * inch, h=low_h,
                     inputs=i)

    # ── Bottom: revisions + PE stamp placeholder ───────────────────
    bot_h = 1.00 * inch          # block: 0.50 to 1.50, gap above = 0.15
    _draw_revision_history(c,
                           x=0.6 * inch, y=0.5 * inch,
                           w=6.0 * inch, h=bot_h,
                           inputs=i)
    _draw_pe_stamp(c,
                   x=7.0 * inch, y=0.5 * inch,
                   w=W - 7.0 * inch - 0.5 * inch, h=bot_h)

    # ── Footer ─────────────────────────────────────────────────────
    c.setFont("Helvetica-Oblique", 7)
    c.setFillColor(colors.HexColor("#6B7280"))
    c.drawString(
        0.5 * inch, 0.30 * inch,
        f"Generated by pvess-calc · Project ID: {i.project.id} · "
        f"REV {i.project.revision}",
    )
    c.setFillColor(colors.black)

    c.save()


# ─── Block renderers ───────────────────────────────────────────────────


def _draw_title_strip(c, W: float, H: float, result: CalculationResult) -> None:
    """Top headline: project name + client name + system size + address + ESID.

    Vertical stack at top of page:
      1. "NEW PV SYSTEM DESIGN"        (22 pt bold)  ← AHJ-standard heading
      2. <client_name>                 (14 pt)       ← doctor expects this
      3. <N modules / DC kW / AC kW>   (11 pt)
      4. <site address>  ·  ESID       (10 pt)
    """
    i = result.inputs
    n_inv = i.inverter.count(i.battery.quantity)
    dc_kw = i.pv_array.modules * i.pv_array.module.power_w / 1000.0
    ac_kw = i.inverter.ac_output_v * i.inverter.ac_output_a * n_inv / 1000.0

    # Big title — single line dominating the top band
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(W / 2, H - 0.65 * inch, "NEW PV SYSTEM DESIGN")

    # Client / project name (doctor pdf_text_searchable check needs this
    # in the extracted PDF text)
    c.setFont("Helvetica-Bold", 14)
    client_or_project = i.project.client_name or i.project.name
    c.drawCentredString(W / 2, H - 0.92 * inch, client_or_project)

    # System size sub-headline
    c.setFont("Helvetica", 11)
    size_line = (
        f"{i.pv_array.modules} MODULES  ·  {dc_kw:.2f} kW DC  ·  "
        f"{ac_kw:.2f} kW AC SYSTEM SIZE"
    )
    c.drawCentredString(W / 2, H - 1.12 * inch, size_line)

    # Address + ESID line (smaller)
    c.setFont("Helvetica", 9.5)
    addr = i.project.site_address or i.project.location
    esid = i.project.meter_info.esid
    addr_line = addr
    if esid:
        addr_line += f"    ·    ESID: {esid}"
    c.drawCentredString(W / 2, H - 1.30 * inch, addr_line)


def _draw_section_box(
    c, x: float, y: float, w: float, h: float, title: str,
) -> None:
    """Standard block frame: thin border + bold underlined title at top."""
    c.setLineWidth(0.5)
    c.setStrokeColor(colors.HexColor("#94a3b8"))
    c.rect(x, y, w, h, fill=0, stroke=1)
    c.setStrokeColor(colors.black)
    # Title bar at top
    c.setFillColor(colors.HexColor("#1F2937"))
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(x + 0.10 * inch, y + h - 0.18 * inch, title)
    c.setLineWidth(0.4)
    c.setStrokeColor(colors.HexColor("#cbd5e1"))
    c.line(x + 0.10 * inch, y + h - 0.22 * inch,
           x + w - 0.10 * inch, y + h - 0.22 * inch)
    c.setStrokeColor(colors.black)
    c.setFillColor(colors.black)


def _draw_kv_rows(
    c, x: float, y: float, w: float, rows: list[tuple[str, str]], *,
    label_col_w: float = 1.4 * inch,
    row_h: float = 0.16 * inch,
    font_size: float = 8.5,
) -> None:
    """Key-value rows in a 2-column layout. Truncates with "…" via
    `stringWidth` measurement (NOT a char-count heuristic — the
    2026-05-17 "AC bleeds past frame" bug was caused by a wrong
    1.6× multiplier in the old char-count formula).

    Right-column budget = `w - label_col_w - 2 × pad`, where the pad
    is 0.10" left of the label-col and 0.10" right of the value-col
    (we already account for the left pad via the caller passing
    `x + 0.10 * inch`).
    """
    c.setFont("Helvetica", font_size)
    # Account for the value column's right-side padding (~0.10" inside
    # the block edge). x is the block's left content edge already.
    value_x = x + label_col_w
    value_max_pt = (w - label_col_w) - 0.20 * inch    # right pad
    for k, v in rows:
        c.setFillColor(colors.HexColor("#475569"))
        c.drawString(x, y, k)
        c.setFillColor(colors.black)
        v_str = str(v) if v else "—"
        # Truncate by REAL stringWidth, ellipsis-aware.
        if c.stringWidth(v_str, "Helvetica", font_size) > value_max_pt:
            ellipsis = "…"
            ell_w = c.stringWidth(ellipsis, "Helvetica", font_size)
            # Drop characters one at a time until value + ellipsis fits
            while v_str and (
                c.stringWidth(v_str, "Helvetica", font_size) + ell_w
                > value_max_pt
            ):
                v_str = v_str[:-1]
            v_str = v_str.rstrip() + ellipsis
        c.drawString(value_x, y, v_str)
        y -= row_h


def _draw_aerial_map(c, *, x: float, y: float, w: float, h: float,
                     coordinates: str) -> None:
    """K.12.2 — embed aerial RGB from Google Solar dataLayers. When the
    key isn't set OR Google returns nothing, render a placeholder
    with a centred "Aerial map unavailable" notice."""
    _draw_section_box(c, x, y, w, h, "AERIAL MAP")
    img_area_y = y + 0.15 * inch
    img_area_h = h - 0.40 * inch

    lat_lng = coordinates_to_lat_lng(coordinates)
    png_bytes = None
    if lat_lng:
        png_bytes = fetch_aerial_map_png(lat_lng[0], lat_lng[1])

    if png_bytes:
        try:
            img = ImageReader(io.BytesIO(png_bytes))
            c.drawImage(
                img,
                x + 0.10 * inch, img_area_y,
                width=w - 0.20 * inch, height=img_area_h,
                preserveAspectRatio=True, anchor="c",
            )
        except Exception:
            _draw_map_placeholder(c, x, img_area_y, w, img_area_h,
                                  "Aerial render failed")
    else:
        _draw_map_placeholder(c, x, img_area_y, w, img_area_h,
                              "PVESS_GOOGLE_SOLAR_KEY required")


def _draw_vicinity_map(c, *, x: float, y: float, w: float, h: float,
                       coordinates: str) -> None:
    """K.12.3 — embed Mapbox Static Images vicinity map. Missing key →
    placeholder."""
    _draw_section_box(c, x, y, w, h, "VICINITY MAP")
    img_area_y = y + 0.15 * inch
    img_area_h = h - 0.40 * inch

    lat_lng = coordinates_to_lat_lng(coordinates)
    png_bytes = None
    if lat_lng:
        png_bytes = fetch_vicinity_map_png(lat_lng[0], lat_lng[1])

    if png_bytes:
        try:
            img = ImageReader(io.BytesIO(png_bytes))
            c.drawImage(
                img,
                x + 0.10 * inch, img_area_y,
                width=w - 0.20 * inch, height=img_area_h,
                preserveAspectRatio=True, anchor="c",
            )
        except Exception:
            _draw_map_placeholder(c, x, img_area_y, w, img_area_h,
                                  "Vicinity render failed")
    else:
        _draw_map_placeholder(c, x, img_area_y, w, img_area_h,
                              "PVESS_MAPBOX_TOKEN required")


def _draw_map_placeholder(c, x: float, y: float, w: float, h: float,
                          message: str) -> None:
    """Grey hatched box with centred notice."""
    c.setFillColor(colors.HexColor("#f1f5f9"))
    c.rect(x + 0.10 * inch, y, w - 0.20 * inch, h, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#94a3b8"))
    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(x + w / 2, y + h / 2, message)
    c.setFillColor(colors.black)


def _draw_sheet_index(c, *, x: float, y: float, w: float, h: float) -> None:
    """Sheet codes + titles from SHEET_REGISTRY."""
    _draw_section_box(c, x, y - h, w, h, "SHEET INDEX")
    sheets = cover_index_rows()
    n = max(1, len(sheets))
    row_h = min(0.13 * inch, (h - 0.4 * inch) / n)
    c.setFont("Helvetica", 7)
    yy = y - 0.35 * inch
    for code, title in sheets:
        c.drawString(x + 0.12 * inch, yy, code)
        # Truncate title to fit
        title_max = max(8, int((w - 0.95 * inch) / 4.0))
        t = title if len(title) <= title_max else title[: title_max - 1] + "…"
        c.drawString(x + 0.75 * inch, yy, t)
        yy -= row_h
        if yy < y - h + 0.15 * inch:
            break


def _draw_scope_of_work(c, *, x: float, y: float, w: float, h: float,
                        result: CalculationResult) -> None:
    """System equipment summary: module × N, inverter × N, optimizer,
    control panel."""
    _draw_section_box(c, x, y - h, w, h, "SCOPE OF WORK")
    i = result.inputs
    n_inv = i.inverter.count(i.battery.quantity)
    dc_kw = i.pv_array.modules * i.pv_array.module.power_w / 1000.0
    ac_kw = i.inverter.ac_output_v * i.inverter.ac_output_a * n_inv / 1000.0

    rows = [
        ("System size:", f"{dc_kw:.2f} kW DC  /  {ac_kw:.2f} kW AC"),
        ("PV module:",
         f"({i.pv_array.modules}) {i.pv_array.module.brand} "
         f"{i.pv_array.module.model}"),
        ("Inverter:",
         f"({n_inv}) {i.inverter.brand} {i.inverter.model}"),
    ]
    if i.battery.installed:
        rows.append(
            ("Battery:",
             f"({i.battery.quantity}) {i.battery.brand} {i.battery.model} "
             f"= {i.battery.total_kwh:.1f} kWh"),
        )
    else:
        rows.append(("Battery:", "— (PV-only, grid-tied)"))
    # Optimizer (Tigo TS4-A-O per K.7 standard)
    opt_ref = getattr(i.optimizer, "ref", "") or ""
    if opt_ref:
        rows.append(("Optimizer:",
                     f"({i.pv_array.modules}) {opt_ref}"))

    _draw_kv_rows(
        c, x + 0.10 * inch, y - 0.35 * inch, w, rows,
        label_col_w=0.95 * inch,
    )


def _draw_governing_codes(c, *, x: float, y: float, w: float, h: float,
                          inputs) -> None:
    """NEC + IBC + IRC + IFC + IFGC + IEBC + IECC + IMC + IPC."""
    _draw_section_box(c, x, y, w, h, "GOVERNING CODES")
    bc = inputs.project.building_codes
    rows = [
        ("NEC:",  f"{inputs.project.nec_edition} NEC"),
        ("IBC:",  bc.ibc),
        ("IRC:",  bc.irc),
        ("IFC:",  bc.ifc),
        ("IFGC:", bc.ifgc),
        ("IEBC:", bc.iebc),
        ("IECC:", bc.iecc),
        ("IMC:",  bc.imc),
        ("IPC:",  bc.ipc),
    ]
    _draw_kv_rows(
        c, x + 0.10 * inch, y + h - 0.40 * inch, w, rows,
        label_col_w=0.55 * inch, row_h=0.13 * inch, font_size=7.5,
    )


def _draw_design_criteria(c, *, x: float, y: float, w: float, h: float,
                          inputs) -> None:
    """Wind / snow / ASCE / exposure / occupancy / construction / sprinklers."""
    _draw_section_box(c, x, y, w, h, "DESIGN CRITERIA")
    d = inputs.project.design_criteria
    rows = [
        ("Wind speed:",        f"{d.wind_speed_mph} mph (3-sec gust)"),
        ("Ground snow load:",  f"{d.ground_snow_load_psf} psf"),
        ("ASCE:",              d.asce_version),
        ("Exposure category:", d.exposure_category),
        ("Occupancy:",         d.occupancy),
        ("Construction type:", d.construction_type),
        ("Sprinklers:",        "Yes" if d.sprinklers else "No"),
    ]
    _draw_kv_rows(
        c, x + 0.10 * inch, y + h - 0.40 * inch, w, rows,
        label_col_w=1.10 * inch, row_h=0.16 * inch, font_size=8,
    )


def _draw_roof_info(c, *, x: float, y: float, w: float, h: float,
                    inputs) -> None:
    """Stories / type / mounting / flashing / replacement / condition /
    height / construction."""
    _draw_section_box(c, x, y, w, h, "ROOF INFO")
    ri = inputs.project.roof_info
    mounting = inputs.site.mounting
    rows = [
        ("Stories:",         f"{ri.stories}"),
        ("Type:",            ri.type or "—"),
        ("Mounting:",        mounting.rail_system or "—"),
        ("Flashing:",        ri.flashing or mounting.flashing or "—"),
        ("Being replaced:",  "Yes" if ri.being_replaced else "No"),
        ("Condition:",       ri.condition.capitalize() if ri.condition else "—"),
        ("Height:",          f"{ri.height_ft:.0f} ft" if ri.height_ft > 0 else "—"),
        ("Construction:",    ri.construction or "—"),
    ]
    _draw_kv_rows(
        c, x + 0.10 * inch, y + h - 0.40 * inch, w, rows,
        label_col_w=1.15 * inch, row_h=0.155 * inch, font_size=8,
    )


def _draw_interconnection(c, *, x: float, y: float, w: float, h: float,
                          result: CalculationResult) -> None:
    """Method + MSP rating + busbar + sub-panel breakdown.

    Tight row spacing (0.14") to fit 5 rows in the K.12 1.20" lower-
    middle row alongside the 0.30" header strip."""
    _draw_section_box(c, x, y, w, h, "INTERCONNECTION")
    i = result.inputs
    method = result.interconnect.recommended or "FAIL"
    pretty_method = {
        "supply_side_tap": "Supply-side tap (705.11)",
        "120%_rule": "120% rule (705.12(B)(3)(2))",
        "sum_rule":  "Sum rule (705.12(B)(3)(1))",
    }.get(method, method)
    rows = [
        ("Method:",   pretty_method),
        ("MSP:",      f"{i.service.main_panel_a:.0f} A"),
        ("Busbar:",   f"{i.service.busbar_a:.0f} A ({i.service.busbar_source})"),
        ("Voltage:",  i.service.voltage or "120/240 V split-phase"),
    ]
    if i.service.sub_panels:
        rows.append(
            ("Sub-panels:",
             f"({len(i.service.sub_panels)}) — see EE-3"),
        )
    _draw_kv_rows(
        c, x + 0.10 * inch, y + h - 0.32 * inch, w, rows,
        label_col_w=0.90 * inch, row_h=0.14 * inch, font_size=7.5,
    )


def _draw_arrays_table(c, *, x: float, y: float, w: float, h: float,
                       inputs) -> None:
    """ARR / TILT / AZIMUTH / MODULES per sub-array. Reads
    `site.roof_sections` (K.2.6c) so each face is its own row."""
    _draw_section_box(c, x, y, w, h, "ARRAYS")
    sections = inputs.site.roof_sections
    # Header row
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.HexColor("#475569"))
    header_y = y + h - 0.32 * inch
    cols_x = [
        x + 0.15 * inch,                 # ARR
        x + 0.55 * inch,                 # TILT
        x + 1.10 * inch,                 # AZIMUTH
        x + 1.85 * inch,                 # MODULES
    ]
    for cx, label in zip(cols_x, ("ARR", "TILT", "AZIMUTH", "MODULES")):
        c.drawString(cx, header_y, label)
    c.setFillColor(colors.black)
    c.setLineWidth(0.3)
    c.line(x + 0.10 * inch, header_y - 0.05 * inch,
           x + w - 0.10 * inch, header_y - 0.05 * inch)

    c.setFont("Helvetica", 7)
    yy = header_y - 0.16 * inch
    if not sections:
        c.setFillColor(colors.HexColor("#94a3b8"))
        c.drawString(
            x + 0.15 * inch, yy,
            "Single orientation — see PV-2 site plan",
        )
        c.setFillColor(colors.black)
        return
    for idx, s in enumerate(sections, start=1):
        if yy < y + 0.10 * inch:
            break
        c.drawString(cols_x[0], yy, str(idx))
        c.drawString(cols_x[1], yy, f"{s.pitch_deg:.0f}°")
        c.drawString(cols_x[2], yy, f"{s.azimuth_deg:.0f}°")
        c.drawString(cols_x[3], yy, str(s.module_count))
        yy -= 0.115 * inch


def _draw_meter_info(c, *, x: float, y: float, w: float, h: float,
                     inputs) -> None:
    """Utility / meter number / location / ESID.

    Tight row spacing (0.14") to fit 5 rows in the K.12 1.20" lower-
    middle row alongside the 0.30" header strip."""
    _draw_section_box(c, x, y, w, h, "METER INFO")
    mi = inputs.project.meter_info
    rows = [
        ("Utility:",       inputs.project.utility or "—"),
        ("Meter #:",       mi.number or "—"),
        ("Location:",      mi.location or "—"),
        ("ESID:",          mi.esid or "—"),
        ("Service voltage:", inputs.service.voltage or "120/240 V"),
    ]
    _draw_kv_rows(
        c, x + 0.10 * inch, y + h - 0.32 * inch, w, rows,
        label_col_w=0.90 * inch, row_h=0.14 * inch, font_size=7.5,
    )


def _draw_revision_history(c, *, x: float, y: float, w: float, h: float,
                           inputs) -> None:
    """Date / REV letter / comment table."""
    _draw_section_box(c, x, y, w, h, "REVISION HISTORY")
    history = inputs.project.revision_history
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#475569"))
    header_y = y + h - 0.30 * inch
    cols = [
        (x + 0.15 * inch, "DATE"),
        (x + 1.50 * inch, "REV"),
        (x + 2.10 * inch, "COMMENT"),
    ]
    for cx, lbl in cols:
        c.drawString(cx, header_y, lbl)
    c.setFillColor(colors.black)
    c.setLineWidth(0.3)
    c.line(x + 0.10 * inch, header_y - 0.05 * inch,
           x + w - 0.10 * inch, header_y - 0.05 * inch)

    c.setFont("Helvetica", 8)
    yy = header_y - 0.20 * inch
    if not history:
        # Synthesize current entry from `project.revision +
        # initial_design_date` so the table isn't empty.
        c.drawString(x + 0.15 * inch, yy,
                     inputs.project.initial_design_date or "—")
        c.drawString(x + 1.50 * inch, yy, inputs.project.revision or "A")
        c.setFillColor(colors.HexColor("#6B7280"))
        c.drawString(x + 2.10 * inch, yy, "initial design (no history yet)")
        c.setFillColor(colors.black)
        return
    for entry in history:
        if yy < y + 0.10 * inch:
            break
        c.drawString(x + 0.15 * inch, yy, entry.date)
        c.drawString(x + 1.50 * inch, yy, entry.revision)
        # Truncate comment
        max_chars = max(8, int((w - 2.10 * inch) / 4.5))
        comment = entry.comment if len(entry.comment) <= max_chars \
            else entry.comment[: max_chars - 1] + "…"
        c.drawString(x + 2.10 * inch, yy, comment)
        yy -= 0.16 * inch


def _draw_pe_stamp(c, *, x: float, y: float, w: float, h: float) -> None:
    """Reserved area for the engineer's wet stamp + signature."""
    c.setLineWidth(0.8)
    c.setStrokeColor(colors.HexColor("#1F2937"))
    c.rect(x, y, w, h, fill=0, stroke=1)
    c.setStrokeColor(colors.HexColor("#9CA3AF"))
    c.setDash(3, 2)
    c.setLineWidth(0.5)
    c.rect(x + 0.08 * inch, y + 0.08 * inch,
           w - 0.16 * inch, h - 0.16 * inch)
    c.setDash()
    c.setStrokeColor(colors.black)

    cx = x + w / 2
    cy = y + h / 2
    c.setFillColor(colors.HexColor("#6B7280"))
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(cx, cy + 0.15 * inch, "PE STAMP")
    c.drawCentredString(cx, cy + 0.00 * inch, "& SIGNATURE")
    c.setFont("Helvetica-Oblique", 7)
    c.drawCentredString(cx, cy - 0.22 * inch, "(to be affixed by engineer of record)")
    c.setFillColor(colors.black)
