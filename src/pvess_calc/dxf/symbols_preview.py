"""Symbol swatch sheet — every icon glyph on one page for visual review.

This is a DEV TOOL, not part of the AHJ submittal pipeline. Goal:
collapse the iteration loop on per-icon visuals from
    edit symbols.py → run full pvess-review → flip to EE-1 → find icon
down to
    edit symbols.py → run pvess-symbols-preview → see all icons side by side

Output:
    A single ANSI B (17×11") landscape PDF with a grid of cells, one
    per symbol. Each cell shows:
      - The icon rendered at its production size (same w/h render.py uses)
      - The functional name underneath
      - The size annotation (e.g. "1.60" × 0.90"")

Add a new symbol: append to `SWATCH_ENTRIES` and it shows up. The
swatch ALWAYS uses the same icon-dispatch path as production
(`sym.ICON_DISPATCH`), so what you see here = what shows up on EE-1.
"""
from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment

from . import symbols as sym
from .render import (
    LAYERS, MARGIN, SHEET_H, SHEET_W,
    _configure_text_style,
)
from .strokes import STROKE_THIN  # noqa: F401


# (display label, dispatch key, w, h, draw_outline)
#
# Sizes mirror the actual sizes used in render.py — change them here only
# if production sizes change. The swatch always shows what the diagram
# will use.
SWATCH_ENTRIES: list[tuple[str, str, float, float, bool]] = [
    ("PV STRING",         "PV",       0.70, 0.50, True),
    ("DC COMBINER",       "COMB",     0.75, 0.70, True),
    ("RSD (NEC 690.12)",  "RSD",      0.75, 0.70, True),
    ("HYBRID INVERTER",   "INV",      1.60, 0.90, True),
    ("ESS / BATTERY",     "ESS",      1.20, 0.70, True),
    ("AC DISCONNECT",     "AC DISC",  0.85, 0.85, True),
    ("MSP — 200A",        "MSP",      1.00, 1.60, True),
    ("SUB PANEL — 200A",  "SUB",      1.00, 1.40, True),
    ("UTILITY METER",     "M",        0.55, 0.55, False),
    ("OPTIMIZER (MLPE)",  "MLPE",     0.50, 0.30, True),
]


# Grid layout — ANSI B sheet, 4 columns × 3 rows of cells with breathing room
COLS = 4
CELL_W = 3.6
CELL_H = 2.4


# Swatch typography — a one-page DEV TOOL has different presentation needs
# from the production EE-1 / EE-2 sheets (much sparser layout, fewer
# elements per cell), so it uses its own 4 named heights rather than the
# production TEXT_* tiers. Defined here as module-local constants so the
# closing-standard "no height=0.XXX literal" rule still holds.
SWATCH_PAGE_TITLE = 0.22   # top "PVESS · SYMBOL SWATCH" banner
SWATCH_LABEL     = 0.12    # per-cell device name (e.g. "PV STRING")
SWATCH_SUBTITLE  = 0.10    # under-banner one-liner + footer count
SWATCH_ANNOT     = 0.07    # per-cell size + dispatch-key annotation


def _draw_swatch_frame(msp) -> None:
    """Light page border + title strip at the top."""
    # Page border
    msp.add_lwpolyline(
        [
            (MARGIN, MARGIN),
            (SHEET_W - MARGIN, MARGIN),
            (SHEET_W - MARGIN, SHEET_H - MARGIN),
            (MARGIN, SHEET_H - MARGIN),
            (MARGIN, MARGIN),
        ],
        close=True,
        dxfattribs={"layer": "BORDER"},
    )
    # Title — large, centered
    msp.add_text(
        "PVESS · SYMBOL SWATCH",
        height=SWATCH_PAGE_TITLE,
        dxfattribs={"layer": "TITLE_BLOCK"},
    ).set_placement(
        (SHEET_W / 2, SHEET_H - MARGIN - 0.45),
        align=TextEntityAlignment.MIDDLE_CENTER,
    )
    # Subtitle — small, italic-ish note
    msp.add_text(
        "Each cell shows the icon at the size used by render.py · iterate here",
        height=SWATCH_SUBTITLE,
        dxfattribs={"layer": "ANNOTATION"},
    ).set_placement(
        (SHEET_W / 2, SHEET_H - MARGIN - 0.72),
        align=TextEntityAlignment.MIDDLE_CENTER,
    )


def _ensure_swatch_block(doc, name: str, w: float, h: float,
                         icon_key: str, outline: bool) -> None:
    """Build one swatch block: outline rect + icon geometry.

    Uses the EXACT same `sym.ICON_DISPATCH` path that render.py uses, so
    what you see in the swatch is bit-for-bit what shows up on EE-1.
    """
    if name in doc.blocks:
        return
    blk = doc.blocks.new(name)
    if outline:
        blk.add_lwpolyline(
            [(0, 0), (w, 0), (w, h), (0, h), (0, 0)],
            close=True,
            dxfattribs={"layer": "EQUIPMENT"},
        )
    geom = sym.ICON_DISPATCH.get(icon_key)
    if geom:
        geom(blk, w, h)


def render_swatch(out_path: Path) -> None:
    """Build the symbol swatch DXF.

    Use `pvess-symbols-preview` from the CLI to also render to PDF.
    """
    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = 1   # inches
    _configure_text_style(doc)
    for layer_name, (color, _desc) in LAYERS.items():
        doc.layers.add(layer_name, color=color)

    msp = doc.modelspace()
    _draw_swatch_frame(msp)

    # Grid origin: just below the title block.
    grid_left = MARGIN + 0.4
    grid_top = SHEET_H - MARGIN - 1.10

    for idx, (label, key, w, h, outline) in enumerate(SWATCH_ENTRIES):
        col = idx % COLS
        row = idx // COLS
        cell_x0 = grid_left + col * CELL_W
        cell_y1 = grid_top - row * CELL_H            # top of cell
        cell_y0 = cell_y1 - CELL_H                    # bottom of cell

        # Cell boundary — light dashed rectangle so cells feel discrete
        msp.add_lwpolyline(
            [(cell_x0, cell_y0), (cell_x0 + CELL_W, cell_y0),
             (cell_x0 + CELL_W, cell_y1), (cell_x0, cell_y1),
             (cell_x0, cell_y0)],
            close=True,
            dxfattribs={"layer": "ANNOTATION", "lineweight": STROKE_THIN},
        )

        # Icon insertion point — centered horizontally; vertically
        # positioned so the icon sits in the upper portion, leaving room
        # for two-line label below.
        icon_x = cell_x0 + (CELL_W - w) / 2
        label_band_h = 0.55
        icon_band_y_center = cell_y0 + label_band_h + (CELL_H - label_band_h) / 2
        icon_y = icon_band_y_center - h / 2

        block_name = f"SWATCH_{key.replace(' ', '_').replace('/', '_')}"
        _ensure_swatch_block(doc, block_name, w, h, key, outline)
        msp.add_blockref(block_name, insert=(icon_x, icon_y))

        # Functional name (large)
        msp.add_text(
            label,
            height=SWATCH_LABEL,
            dxfattribs={"layer": "EQUIPMENT_TEXT"},
        ).set_placement(
            (cell_x0 + CELL_W / 2, cell_y0 + 0.35),
            align=TextEntityAlignment.MIDDLE_CENTER,
        )
        # Size annotation (small)
        msp.add_text(
            f'{w:.2f}" × {h:.2f}"   ·   dispatch key: "{key}"',
            height=SWATCH_ANNOT,
            dxfattribs={"layer": "ANNOTATION"},
        ).set_placement(
            (cell_x0 + CELL_W / 2, cell_y0 + 0.16),
            align=TextEntityAlignment.MIDDLE_CENTER,
        )

    # Footer with summary
    msp.add_text(
        f"{len(SWATCH_ENTRIES)} icons · src/pvess_calc/dxf/symbols.py",
        height=SWATCH_SUBTITLE,
        dxfattribs={"layer": "ANNOTATION"},
    ).set_placement(
        (SHEET_W / 2, MARGIN + 0.18),
        align=TextEntityAlignment.MIDDLE_CENTER,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(out_path))
