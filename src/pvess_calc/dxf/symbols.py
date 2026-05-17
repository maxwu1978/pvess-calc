"""Wyssling-style DXF device-icon geometry library.

This module replaces the lightweight per-device glyphs that used to live
inline in `render.py` with **product-accurate** geometry matching the
visual conventions of a Wyssling-style three-line residential permit
planset. Each function draws into a `BlockLayout` (the inside of an
ezdxf BLOCK definition); `render.py` wraps each in a BLOCK and INSERTs
it on the modelspace.

Why a separate module:
- Easier to iterate on per-device geometry without touching the layout
  / wiring / schedule code in render.py.
- The functions are pure geometry — they take `(blk, w, h)` and draw
  lines/polylines/text only. No layout decisions, no DeviceSpec reads.
- New devices = one new function here + one entry in render.py's
  `_ICON_DISPATCH`. Per DESIGN.md §2 / §9 single-source rule.

Symbol style — IEEE 315 / Wyssling residential:
- Inverter: product-accurate rectangle with internal GEN/LOAD/GRID
  bays, DC input ladder on the left, AC terminal block on the right.
  Not an abstract sine/square wave.
- Disconnect (AC DISC, RSD): rectangle with **knife switch** drawn at
  the wire crossing — angled line breaking the conductor path.
- Panel (MSP, SUB): tall outline with internal breaker bars rendered by
  `render._draw_internal_breakers` (icon function just paints the
  device header bar at the top so MAIN BREAKER / model text is
  visually grouped).
- PV string: chevron-arrow pointing right with module count "10" in
  the body — matches Wyssling's per-string symbol.
- Battery (ESS): standard battery-cell pattern (alternating long/short
  vertical lines).
- Meter: circle with "M" centered (kept from previous lib — already
  industry-standard).

Origin / size contract:
- The block's coordinate system has (0,0) at the bottom-left of the
  device outline. The outline itself (rectangle) is drawn by render.py
  before the icon function runs.
- Functions assume the outline is `w` wide × `h` tall and stay inside
  it (with small inset padding for stroke clearance).
- Text inside the icon is drawn on `EQUIPMENT_TEXT` layer; geometry
  on `EQUIPMENT`. Sub-rectangles use thin stroke (default lineweight).
"""
from __future__ import annotations

from typing import Callable

from ezdxf.enums import TextEntityAlignment
from ezdxf.layouts import BlockLayout

# Design tokens — typography + stroke tiers from dedicated single-source
# modules. See `.typography` and `.strokes` for tier definitions.
from .typography import TEXT_TITLE, TEXT_HEADER, TEXT_BODY, TEXT_CAPTION  # noqa: F401
from .strokes import STROKE_THIN, STROKE_MED, STROKE_HEAVY  # noqa: F401


# ─────────────────────────────────────────────────────────────────────────────
# Stroke weight tier — three explicit levels for clarity.
#
#   thin (default ~25): device outline rectangles, fine annotations
#   medium (lineweight 35): internal icon geometry (PV chevron, knife
#       lever, terminal-block outline, battery cells, …) — these read
#       as the "content" of each box and should be one tier above the
#       outline so they're noticeable but not heavy.
#   heavy (lineweight 50): main DC/AC trunk lines + meter circle
#       (drawn by render.py / draw_meter_icon, not by icon helpers here).
#
# Using consistent tiers makes the diagram read like a published planset
# instead of a school project — the eye groups elements by stroke weight
# rather than getting equal-weight noise.
# ─────────────────────────────────────────────────────────────────────────────
_EQ = {"layer": "EQUIPMENT"}
_EQ_TEXT = {"layer": "EQUIPMENT_TEXT"}
_EQ_MED = {"layer": "EQUIPMENT", "lineweight": STROKE_MED}
_EQ_HEAVY = {"layer": "EQUIPMENT", "lineweight": STROKE_HEAVY}


def _text_centered(blk: BlockLayout, x: float, y: float,
                   text: str, height: float = 0.10) -> None:
    """Place a centered text label at (x, y) inside the block."""
    blk.add_text(text, height=height, dxfattribs=_EQ_TEXT).set_placement(
        (x, y), align=TextEntityAlignment.MIDDLE_CENTER)


def _text_left(blk: BlockLayout, x: float, y: float,
               text: str, height: float = 0.085) -> None:
    """Place a left-aligned text label at (x, y) inside the block."""
    blk.add_text(text, height=height, dxfattribs=_EQ_TEXT).set_placement(
        (x, y), align=TextEntityAlignment.LEFT)


# ─────────────────────────────────────────────────────────────────────────────
# Inverter — Wyssling-style product-accurate rectangle
# ─────────────────────────────────────────────────────────────────────────────


def draw_inverter_icon(blk: BlockLayout, w: float, h: float) -> None:
    """Hybrid inverter, product-accurate but minimalist.

    Layout inside the box (assumes w ≥ 1.4, h ≥ 0.9):

        ┌─────────────────────────────────────┐
        │  ─  ┌────┐ ┌────┐ ┌────┐            │
        │  ─  │GEN │ │LOAD│ │GRID│            │  ← top half: bays
        │  ─  └────┘ └────┘ └────┘            │
        │  ─   ▌ ▌    ▌ ▌    ▌ ▌              │  ← terminal blocks (2 pins)
        └─────────────────────────────────────┘

    Compared to the previous version: 4 DC ladder bars (was 5), thinner
    stroke; bay rectangles in default weight (was medium); only 2 pin
    marks per terminal block (was 3). Net effect: same conceptual
    information, less visual clutter.
    """
    inset = 0.05
    # DC input ladder on the left — 4 short horizontal bars at medium weight
    ladder_x0 = inset
    ladder_x1 = inset + 0.12
    n_bars = 4
    bar_pitch = (h - 2 * inset) / (n_bars + 1)
    for k in range(n_bars):
        ly = inset + (k + 1) * bar_pitch
        blk.add_line(
            (ladder_x0, ly), (ladder_x1, ly),
            dxfattribs=_EQ_MED,
        )
    # Vertical separator between DC ladder and bays (thin)
    blk.add_line(
        (ladder_x1 + 0.04, inset),
        (ladder_x1 + 0.04, h - inset),
        dxfattribs=_EQ,
    )

    # Three bays: GEN / LOAD / GRID across the right portion
    bays_x0 = ladder_x1 + 0.10
    bays_x1 = w - inset
    bays_w = bays_x1 - bays_x0
    bay_w = (bays_w - 0.10) / 3   # 0.10 = gap budget between bays (4 gaps)
    bay_h = h * 0.38
    bay_y = h - inset - bay_h - 0.02
    bay_gap = (bays_w - 3 * bay_w) / 4

    for k, label in enumerate(["GEN", "LOAD", "GRID"]):
        bx = bays_x0 + bay_gap + k * (bay_w + bay_gap)
        blk.add_lwpolyline(
            [(bx, bay_y), (bx + bay_w, bay_y),
             (bx + bay_w, bay_y + bay_h), (bx, bay_y + bay_h),
             (bx, bay_y)],
            close=True, dxfattribs=_EQ,
        )
        _text_centered(blk, bx + bay_w / 2, bay_y + bay_h / 2 - 0.025,
                       label, height=TEXT_BODY)

    # Terminal blocks below each bay — slim rectangles with 2 pin marks
    # (cleaner than the previous 3-pin pattern).
    term_h = h * 0.18
    term_y = bay_y - term_h - 0.05
    for k in range(3):
        bx = bays_x0 + bay_gap + k * (bay_w + bay_gap)
        blk.add_lwpolyline(
            [(bx, term_y), (bx + bay_w, term_y),
             (bx + bay_w, term_y + term_h), (bx, term_y + term_h),
             (bx, term_y)],
            close=True, dxfattribs=_EQ,
        )
        # 2 pin marks inside, evenly spaced
        for i in (1, 2):
            px = bx + i * bay_w / 3
            blk.add_line(
                (px, term_y + 0.02),
                (px, term_y + term_h - 0.02),
                dxfattribs=_EQ,
            )


# ─────────────────────────────────────────────────────────────────────────────
# PV string — Wyssling chevron with module count
# ─────────────────────────────────────────────────────────────────────────────


def draw_pv_string_icon(blk: BlockLayout, w: float, h: float) -> None:
    """Per-string PV symbol: right-pointing chevron at the box's right edge.

         ┌────────────┐╲
         │            │ ╲
         │            │  ▶
         │            │ ╱
         └────────────┘╱

    Minimalist: just the chevron, no internal slashes or marks. The
    module count and tag are rendered as ATTDEFs below the box by
    render.py — those carry the data, the icon is purely identifying.
    Cleaner than the previous "chevron + diagonal slash" combo.
    """
    cy = h / 2
    blk.add_lwpolyline(
        [(w * 0.78, cy + h * 0.42),   # upper-left of chevron
         (w * 0.98, cy),                # tip
         (w * 0.78, cy - h * 0.42)],    # lower-left of chevron
        dxfattribs=_EQ_MED,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Disconnect (AC DISC + RSD share this geometry)
# ─────────────────────────────────────────────────────────────────────────────


def draw_disconnect_icon(blk: BlockLayout, w: float, h: float) -> None:
    """Knife-switch disconnect: open switch lever angled up between two
    terminal posts (IEEE 315 §10.10 convention).

    Trimmed from the previous version: smaller terminal dots, medium
    stroke instead of heavy, no extra wire stubs (the wires in render.py
    already terminate at the box edges so the stubs were redundant).
    """
    cy = h * 0.60
    left_x = w * 0.22
    right_x = w * 0.78
    # Terminal dots (smaller, medium-weight)
    blk.add_circle(center=(left_x, cy), radius=0.035,
                   dxfattribs=_EQ_MED)
    blk.add_circle(center=(right_x, cy), radius=0.035,
                   dxfattribs=_EQ_MED)
    # Knife lever rising from left terminal — ends just above the right
    # terminal to show the "open" state
    blk.add_line(
        (left_x + 0.035, cy),
        (right_x - 0.04, cy + h * 0.28),
        dxfattribs=_EQ_MED,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Rapid Shutdown Device
# ─────────────────────────────────────────────────────────────────────────────


def draw_rsd_icon(blk: BlockLayout, w: float, h: float) -> None:
    """RSD: knife switch + 'RSD' tag inside the box.

    Per NEC 690.12 the symbol isn't standardized; industry convention
    (Mike Holt / IAEI examples) is to draw a labeled switch.
    """
    draw_disconnect_icon(blk, w, h)
    # Tag in the lower portion of the box — sized to match other small
    # captions in the diagram (was 0.11, now 0.085).
    _text_centered(blk, w / 2, h * 0.22, "RSD", height=TEXT_BODY)


# ─────────────────────────────────────────────────────────────────────────────
# DC combiner — multi-input bus converging to one output
# ─────────────────────────────────────────────────────────────────────────────


def draw_combiner_icon(blk: BlockLayout, w: float, h: float) -> None:
    """DC combiner / source-circuit combiner: N input ticks on the left
    converge to a single horizontal bus, then a single output on the
    right (Wyssling fan-in convention).

    Trimmed: removed the inline fuse zigzag — the OCPD rating is already
    in the device's DESC1 ATTDEF ("OCPD: 25 A") and on the conductor
    schedule, so the zigzag was redundant + visual noise.
    """
    cy = h * 0.55
    bus_x = w * 0.40
    # Input lines (3 tick marks angling into a center bus point)
    for ty_off in (-h * 0.20, 0, h * 0.20):
        blk.add_line(
            (0, cy + ty_off), (bus_x, cy),
            dxfattribs=_EQ,
        )
    # Output bus line — medium weight
    blk.add_line(
        (bus_x, cy), (w, cy),
        dxfattribs=_EQ_MED,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Battery / ESS — standard cell pattern
# ─────────────────────────────────────────────────────────────────────────────


def draw_battery_icon(blk: BlockLayout, w: float, h: float) -> None:
    """Battery cell pattern: alternating long/short vertical lines
    (IEEE 315 §11.1 convention; long = positive plate, short = negative).

    Tweaks vs previous version: long cells use MEDIUM stroke (was heavy),
    +/- markers slightly smaller — the cell-pattern itself reads as a
    battery, the markers are confirmation, not decoration.
    """
    cy = h * 0.55
    n_cells = 4
    spacing = w * 0.10
    start_x = w / 2 - (n_cells - 1) * spacing / 2
    long_h = h * 0.32
    short_h = h * 0.20
    for i in range(n_cells):
        x = start_x + i * spacing
        if i % 2 == 0:
            blk.add_line(
                (x, cy - long_h / 2), (x, cy + long_h / 2),
                dxfattribs=_EQ_MED,
            )
        else:
            blk.add_line(
                (x, cy - short_h / 2), (x, cy + short_h / 2),
                dxfattribs=_EQ,
            )
    _text_centered(blk, start_x - 0.10, cy + 0.02, "+", height=TEXT_BODY)
    _text_centered(blk, start_x + (n_cells - 1) * spacing + 0.10, cy + 0.02,
                   "−", height=TEXT_BODY)


# ─────────────────────────────────────────────────────────────────────────────
# Meter — circle with M (unchanged, kept for completeness)
# ─────────────────────────────────────────────────────────────────────────────


def draw_meter_icon(blk: BlockLayout, w: float, h: float) -> None:
    """Utility meter: bold circle + M centered inside. The outline
    rectangle is suppressed by render.py for this device kind."""
    cx, cy = w / 2, h / 2
    r = min(w, h) * 0.38
    blk.add_circle(center=(cx, cy), radius=r, dxfattribs=_EQ_HEAVY)
    _text_centered(blk, cx, cy - r * 0.20, "M", height=r * 0.85)


# ─────────────────────────────────────────────────────────────────────────────
# MSP / Sub-panel — header bar (internal breakers drawn by render.py)
# ─────────────────────────────────────────────────────────────────────────────


def draw_panel_header(blk: BlockLayout, w: float, h: float) -> None:
    """Tall-panel header strip — short horizontal accent line near the
    top to visually separate the device-label area from the internal
    breaker rows that render.py draws via `_draw_internal_breakers`.

    Wyssling planset style: panels have a header band at top with the
    panel name, AIC, and location; breakers live below. We're not
    drawing the band itself (the label is added as an ATTDEF outside
    the BLOCK), but adding a thin separator line communicates the
    division clearly.
    """
    # Thin accent line 0.18" from top — matches reportlab panel headers
    sep_y = h - 0.18
    blk.add_line(
        (0.05, sep_y), (w - 0.05, sep_y),
        dxfattribs=_EQ,
    )


def draw_no_icon(blk: BlockLayout, w: float, h: float) -> None:
    """Empty icon — used for devices whose content is rendered outside
    the block (e.g. panels with inline breakers from render.py)."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Optimizer — small box with diagonal slash + callout-style placement
# ─────────────────────────────────────────────────────────────────────────────


def draw_optimizer_icon(blk: BlockLayout, w: float, h: float) -> None:
    """Module-level power electronics (MLPE) optimizer: small box with
    a diagonal slash and "MLPE" tag. Wyssling shows these inline
    between each PV string and the combiner with a callout circle."""
    # Diagonal slash from lower-left to upper-right
    blk.add_line((0.10, 0.15), (w - 0.10, h - 0.15), dxfattribs=_EQ_HEAVY)
    _text_centered(blk, w / 2, h * 0.25, "MLPE", height=TEXT_BODY)


# ─────────────────────────────────────────────────────────────────────────────
# Schedule callout — A/B/C/D circles on conductor wires
# ─────────────────────────────────────────────────────────────────────────────


def draw_callout_circle(msp, x: float, y: float, letter: str,
                        *, radius: float = 0.10) -> None:
    """Draw a small circle with a letter inside, used to mark a conductor
    on the diagram that's detailed in the conductor schedule table.

    Drawn directly on the modelspace (not inside a BLOCK) because each
    callout is unique to its position. Wyssling planset convention.
    """
    msp.add_circle(center=(x, y), radius=radius,
                   dxfattribs={"layer": "ANNOTATION", "lineweight": STROKE_MED})
    msp.add_text(
        letter, height=radius * 1.1,
        dxfattribs={"layer": "ANNOTATION"},
    ).set_placement((x, y - radius * 0.35),
                    align=TextEntityAlignment.MIDDLE_CENTER)


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch table — drop-in replacement for `_ICON_DISPATCH` in render.py
# ─────────────────────────────────────────────────────────────────────────────


ICON_DISPATCH: dict[str, Callable[[BlockLayout, float, float], None]] = {
    "PV":      draw_pv_string_icon,
    "COMB":    draw_combiner_icon,
    "RSD":     draw_rsd_icon,
    "INV":     draw_inverter_icon,
    "ESS":     draw_battery_icon,
    "AC DISC": draw_disconnect_icon,
    "MSP":     draw_no_icon,           # filled with inline breakers
    "M":       draw_meter_icon,
    "SUB":     draw_no_icon,           # filled with inline breakers
    "MLPE":    draw_optimizer_icon,
}
