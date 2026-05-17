"""EE-3 panel schedule — per-panel breaker position table."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from ..calc.engine import CalculationResult
from ._textfit import fit


def render_panel_schedule(result: CalculationResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=landscape(letter))
    W, H = landscape(letter)
    i = result.inputs

    c.setLineWidth(1.0)
    c.rect(0.4 * inch, 0.4 * inch, W - 0.8 * inch, H - 0.8 * inch)

    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(W / 2, H - 0.8 * inch, "EE-3 · PANEL SCHEDULES")

    # Build per-panel breaker lists
    panels: list[tuple[str, str, list[tuple[str, str, str]]]] = []
    # (panel name, panel rating, [(position, breaker, description)])

    # Main Service Panel
    msp_breakers: list[tuple[str, str, str]] = [
        ("MAIN", f"{int(i.service.main_panel_a)}A 2P", "Service entrance"),
        ("01-02", f"{result.ess.ac_disconnect_ocpd_a}A 2P",
         "PV+ESS backfeed (per NEC 705.12)"),
    ]
    # Add some typical loads
    if i.loads.critical_subpanel_a:
        msp_breakers.append(
            ("03-04", f"{int(i.loads.critical_subpanel_a)}A 2P", "Critical subpanel feeder")
        )
    msp_breakers.extend([
        ("05-06", "20A 1P", "Kitchen GFCI (typical)"),
        ("07-08", "30A 2P", "Range / oven (typical)"),
    ])
    panels.append(("MSP — Main Service Panel",
                   f"{int(i.service.main_panel_a)}A · "
                   f"{int(i.service.busbar_a)}A bus · {i.service.voltage}",
                   msp_breakers))

    # Sub-panels (each gets a feeder breaker entry)
    n_inv = i.inverter.count(i.battery.quantity)
    per_inv_a = int(i.inverter.ac_output_a * 1.25)
    for k, sp in enumerate(i.service.sub_panels):
        sp_breakers = [
            ("MAIN", f"{int(sp.rating_a)}A 2P", f"Feeder from upstream panel"),
        ]
        if k == 0:
            # First sub-panel typically has per-inverter feedins
            for inv_k in range(n_inv):
                pos = f"{2 * inv_k + 1:02d}-{2 * inv_k + 2:02d}"
                sp_breakers.append(
                    (pos, f"{per_inv_a}A 2P", f"INV-{inv_k + 1} backfeed")
                )
        panels.append((sp.name,
                       f"{int(sp.rating_a)}A · {int(sp.busbar_a)}A bus  "
                       f"({sp.location})" if sp.location else
                       f"{int(sp.rating_a)}A · {int(sp.busbar_a)}A bus",
                       sp_breakers))

    # K.6 (B): 2-column grid with K.6 polish:
    #   * Tighter top margin (panels start 1.1" from top, was 1.4").
    #   * Tighter inter-row gap (0.20", was 0.25").
    #   * **Orphan rows are centered** — when an odd panel count leaves
    #     the last row with only one panel (e.g. 3 panels total = row 0
    #     full, row 1 single), the single panel is centered horizontally
    #     rather than left-aligned. Avoids the previous "huge whitespace
    #     to the right of Sub Panel #1" look.
    cell_w = (W - 1.2 * inch) / 2
    row_gap = 0.20 * inch          # tighter row spacing
    col_gap = 0.20 * inch

    # Pair panels by row, compute each row's height = max of the pair.
    row_heights: list[float] = []
    n_panels = len(panels)
    for r in range(0, n_panels, 2):
        pair = panels[r:r + 2]
        row_heights.append(max(_content_h(len(b)) for _, _, b in pair))

    y_cursor = H - 1.1 * inch
    for idx, (name, rating, breakers) in enumerate(panels):
        col = idx % 2
        row = idx // 2
        if col == 0 and idx > 0:
            y_cursor -= row_heights[row - 1] + row_gap
        # Detect orphan single-panel row: this is the last row AND it
        # contains only one panel.
        is_orphan_row = (row == (n_panels - 1) // 2
                         and (n_panels - row * 2) == 1)
        if is_orphan_row:
            x0 = (W - cell_w) / 2
        else:
            x0 = 0.5 * inch + col * (cell_w + col_gap)
        y0 = y_cursor - row_heights[row]
        _draw_panel(c, x0, y0, cell_w, row_heights[row], name, rating, breakers)

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(0.5 * inch, 0.25 * inch,
                 "Breaker positions and ratings are typical; verify against "
                 "as-installed configuration before energization.")
    c.save()


# ─── Panel layout constants (DESIGN.md §3: keep magic numbers at top) ────
# Vertical distances from the top of the panel rectangle, in points.
# `_draw_panel` and `_content_h` both consume these — change once, propagates
# everywhere. 8pt Helvetica capital height ≈ 0.083"; gaps below are tuned
# so blue header bar never clips the subtitle.
HEADER_H        = 0.35 * inch    # blue bar
SUBTITLE_GAP    = 0.17 * inch    # blue bar bottom → subtitle baseline
COL_HDR_GAP     = 0.30 * inch    # subtitle baseline → column header baseline
FIRST_ROW_GAP   = 0.24 * inch    # column header baseline → first data row
ROW_SPACING     = 0.18 * inch    # data row to data row
BOTTOM_PAD      = 0.18 * inch    # last data row → panel bottom


def _content_h(n_rows: int) -> float:
    """Minimum panel height to fit `n_rows` data rows without clipping.
    Used by the layout step to size each row of the grid."""
    return (HEADER_H + SUBTITLE_GAP + COL_HDR_GAP + FIRST_ROW_GAP
            + max(0, n_rows - 1) * ROW_SPACING + BOTTOM_PAD)


def _draw_panel(c, x: float, y: float, w: float, h: float,
                name: str, rating: str, breakers: list[tuple[str, str, str]]) -> None:
    # Blue header bar
    c.setFillColor(colors.HexColor("#1F5BD7"))
    c.rect(x, y + h - HEADER_H, w, HEADER_H, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x + 0.10 * inch, y + h - 0.22 * inch, name)

    # Rating subtitle — drawn BELOW the blue bar with clearance
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8)
    subtitle_y = y + h - HEADER_H - SUBTITLE_GAP
    c.drawString(x + 0.10 * inch, subtitle_y, rating)

    # Outer box
    c.setLineWidth(0.5)
    c.rect(x, y, w, h)

    # Columns
    col_pos_w = 0.7 * inch
    col_brk_w = 0.9 * inch
    col_desc_w = w - col_pos_w - col_brk_w - 0.2 * inch

    # Column headers
    hdr_y = subtitle_y - COL_HDR_GAP
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x + 0.10 * inch, hdr_y, "POS")
    c.drawString(x + 0.10 * inch + col_pos_w, hdr_y, "BREAKER")
    c.drawString(x + 0.10 * inch + col_pos_w + col_brk_w, hdr_y, "DESCRIPTION")
    c.setLineWidth(0.3)
    c.line(x + 0.05 * inch, hdr_y - 0.05 * inch,
           x + w - 0.05 * inch, hdr_y - 0.05 * inch)

    # Data rows
    c.setFont("Helvetica", 8.5)
    yy = hdr_y - FIRST_ROW_GAP
    for pos, brk, desc in breakers:
        if yy < y + 0.10 * inch:
            break
        c.drawString(x + 0.10 * inch, yy, pos)
        c.drawString(x + 0.10 * inch + col_pos_w, yy, brk)
        c.drawString(x + 0.10 * inch + col_pos_w + col_brk_w, yy,
                     fit(desc, "Helvetica", 8.5, col_desc_w))
        yy -= ROW_SPACING
