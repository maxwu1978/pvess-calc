"""Render an ACADE-friendly DXF schematic for permit submittal.

Sheet: ANSI B (17" × 11") landscape, drawing units = inches.

Layout (drawing area, after 0.5" border):
    +------------------------------------+--------------------+
    | Notes                              |  Conductor         |
    |                                    |  Schedule          |
    | Main schematic                     |                    |
    |  PV → COMB → RSD → INV → AC → MSP  |                    |
    |                       ↑            +--------------------+
    |                      ESS           |  Title block       |
    +------------------------------------+--------------------+

DXF is portable AutoCAD format. Equipment blocks ship with TAG1 / DESC1 /
DESC2 / MFG / CAT attributes so ACADE recognizes them as components on open.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import ezdxf
from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment
from ezdxf.layouts import Modelspace

from ..calc.conductor import select_copper
from ..calc.engine import CalculationResult
from ..calc.ocpd import select_ocpd
from ..schema import InternalBreaker, SubPanel
from . import symbols as sym

# --- Layer definitions ------------------------------------------------------
# AutoCAD Color Index (ACI) palette; works in any DXF viewer.
#   1 red, 2 yellow, 3 green, 4 cyan, 5 blue, 6 magenta, 7 white/black

LAYERS: dict[str, tuple[int, str]] = {
    # name           : (aci color, description)
    "BORDER":         (7,  "Sheet border + title block frame"),
    "TITLE_BLOCK":    (7,  "Title block fields"),
    "EQUIPMENT":      (7,  "Device outlines"),
    "EQUIPMENT_TEXT": (7,  "Device labels / specs (inside box)"),
    # Generic wire layers (kept for legacy / single-line use)
    "WIRE_DC":        (1,  "DC PV source / DC ESS conductors"),
    "WIRE_AC":        (2,  "AC conductors L1/L2/N"),
    # Phase-specific layers (Phase A): industry color convention for
    # residential 120/240V split-phase + DC polarity.
    "WIRE_DC_POS":    (1,  "DC positive conductor (red)"),
    "WIRE_DC_NEG":    (7,  "DC negative conductor (black)"),
    "WIRE_AC_L1":     (7,  "AC L1 hot (black)"),
    "WIRE_AC_L2":     (1,  "AC L2 hot (red)"),
    "WIRE_AC_N":      (8,  "AC neutral (white → rendered as gray)"),
    "WIRE_GROUND":    (3,  "Equipment grounding conductor (green)"),
    "ANNOTATION":     (7,  "Wire tags, callouts, conduit labels"),
    "SCHEDULE":       (7,  "Conductor schedule table"),
    "NOTES":          (7,  "General notes block"),
}

# Per-phase layer assignment when drawing multi-conductor buses.
DC_PHASE_LAYERS = ["WIRE_DC_POS", "WIRE_DC_NEG"]
AC_PHASE_LAYERS = ["WIRE_AC_L1", "WIRE_AC_L2", "WIRE_AC_N"]

# --- Sheet geometry (inches) -----------------------------------------------

SHEET_W = 17.0
SHEET_H = 11.0
MARGIN = 0.5

# Typography tiers — one source of truth in `.typography`. Re-imported
# here as module-level names so existing code paths keep working without
# the qualifier prefix.
from .typography import TEXT_TITLE, TEXT_HEADER, TEXT_BODY, TEXT_CAPTION  # noqa: F401, E402
from .strokes import STROKE_THIN, STROKE_MED, STROKE_HEAVY  # noqa: F401, E402

TITLE_BLOCK_W = 4.5
TITLE_BLOCK_H = 3.5
SCHEDULE_W = 4.5
# Schedule height sized for 4 data rows + header + footer margin; leaves the
# upper-right area free for notes/airy whitespace instead of an empty box.
SCHEDULE_H = 2.4
NOTES_H = 1.0

# Main schematic area (left side)
SCHEMATIC_X0 = MARGIN + 0.2
SCHEMATIC_Y0 = MARGIN + 0.2 + NOTES_H
SCHEMATIC_X1 = SHEET_W - MARGIN - TITLE_BLOCK_W - 0.2
SCHEMATIC_Y1 = SHEET_H - MARGIN - 0.2

# Right column (schedule on top, title block on bottom)
RIGHT_X0 = SHEET_W - MARGIN - TITLE_BLOCK_W
RIGHT_X1 = SHEET_W - MARGIN
TB_Y0 = MARGIN
TB_Y1 = MARGIN + TITLE_BLOCK_H
SCHED_Y0 = TB_Y1 + 0.1
SCHED_Y1 = SCHED_Y0 + SCHEDULE_H


# --- Device block factory ---------------------------------------------------

@dataclass
class DeviceSpec:
    tag: str            # e.g. "PV-1"
    label: str          # short icon text inside box (e.g. "PV")
    desc1: str          # spec line 1
    desc2: str = ""     # spec line 2 (optional)
    mfg: str = ""
    cat: str = ""       # catalog / model
    w: float = 1.0
    h: float = 0.7


# Icon geometry now lives entirely in `symbols.py` (per the Phase A
# refactor). The legacy `_draw_*_icon` helpers that used to live here —
# parallel slats for PV, sine + square wave for INV, lightning bolt for
# RSD — were dead code after `_ICON_DISPATCH` switched to
# `sym.ICON_DISPATCH`. Removing them also drops several stray
# `lineweight=N` literals that were left over from the pre-strokes era.


# Wyssling-style icons live in `symbols.py`. The dispatch here is the
# public binding from device "label" string → icon-draw function.
# Keeping the dispatch table at this level (rather than just using
# `sym.ICON_DISPATCH` directly) lets render.py override individual
# entries for special cases without editing symbols.py.
_ICON_DISPATCH: dict[str, callable] = dict(sym.ICON_DISPATCH)


def _ensure_device_block(doc: Drawing, name: str, w: float, h: float, icon: str) -> None:
    """Create a reusable device block: outline rect + icon glyph + ATTDEFs.

    The `icon` string selects geometry from `_ICON_DISPATCH`. Falls back to a
    plain centered text label if no geometry is registered.

    Attributes (visible when ACADE opens this file as a component):
        TAG1, DESC1, DESC2, MFG, CAT
    """
    if name in doc.blocks:
        return
    blk = doc.blocks.new(name)
    # Outline (skip for meter — its circle stands alone)
    if icon != "M":
        blk.add_lwpolyline(
            [(0, 0), (w, 0), (w, h), (0, h), (0, 0)],
            close=True,
            dxfattribs={"layer": "EQUIPMENT"},
        )

    # Icon geometry
    geom = _ICON_DISPATCH.get(icon)
    if geom:
        geom(blk, w, h)
    # Always include the short text caption near the bottom of the box so the
    # device type is unambiguous even if a CAD viewer skips custom geometry.
    # No centered caption inside the box. Each device is identified by
    # three layers of information:
    #   1. Its icon function's geometry (chevron, knife switch,
    #      GEN/LOAD/GRID bays, battery cells, ...).
    #   2. The TAG1 ATTDEF below the box ("PV-S1", "INV-1", ...).
    #   3. For inverters and panels: a Wyssling-style header line drawn
    #      ABOVE the box by render.py.
    # A centered caption inside the box was the source of multiple
    # collision classes — RSD doubled (icon also draws "RSD"), INV grazed
    # the terminal-block lower edge, and the PV chevron was visually
    # cluttered. Removing it cleans every device at once.
    # Icon functions that need their own internal label (RSD, +/- on ESS)
    # draw it themselves; this factory stays neutral.
    # Attribute definitions, anchored below the box with enough clearance so
    # the text baseline doesn't overlap the bottom edge of the outline.
    # Hierarchy: TAG1 (device identifier) at HEADER tier, supporting
    # description lines at BODY tier — gives the eye an anchor when
    # scanning a row of devices.
    # For MSP and inverter blocks, DESC1/DESC2/MFG/CAT ATTDEFs render
    # below the box in the same corridor used by vertical conductors
    # (critical-loads riser for MSP; ESS/battery drop for inverter).
    # Wyssling-style headers drawn ABOVE the box carry the human-readable
    # information, so we hide those duplicate ATTRIBs visually but keep
    # them present in the block (flag=1 = invisible per DXF spec).
    # AutoCAD attribute queries still return the data; only the rendered
    # output drops the collision-prone duplicate text. TAG1 stays visible.
    HIDE_FOR = {"MSP", "INV"}
    for tag, dy in [
        ("TAG1",  0.18 + 0.14 * 0),
        ("DESC1", 0.18 + 0.14 * 1),
        ("DESC2", 0.18 + 0.14 * 2),
        ("MFG",   0.18 + 0.14 * 3),
        ("CAT",   0.18 + 0.14 * 4),
    ]:
        attdef = blk.add_attdef(
            tag,
            insert=(0, -dy),
            dxfattribs={"layer": "ANNOTATION", "height": TEXT_BODY},
        )
        if tag == "TAG1":
            attdef.dxf.height = TEXT_HEADER
        if icon in HIDE_FOR and tag != "TAG1":
            attdef.dxf.flags = 1   # invisible — data preserved for ACADE


def _add_device(msp: Modelspace, doc: Drawing, x: float, y: float, spec: DeviceSpec) -> tuple[float, float]:
    """Insert a device block at (x,y) and fill attributes. Returns the right-
    middle terminal point for wiring."""
    block_name = f"DEV_{spec.label.upper().replace(' ', '_')}"
    _ensure_device_block(doc, block_name, spec.w, spec.h, spec.label)

    ins = msp.add_blockref(
        block_name,
        insert=(x, y),
        dxfattribs={"layer": "EQUIPMENT"},
    )
    ins.add_auto_attribs({
        "TAG1":  spec.tag,
        "DESC1": spec.desc1,
        "DESC2": spec.desc2,
        "MFG":   spec.mfg,
        "CAT":   spec.cat,
    })
    # Return terminal points: left-mid, right-mid, top-mid, bottom-mid
    return x, y  # caller uses helper below for terminals


def _left_mid(x, y, spec): return (x, y + spec.h / 2)
def _right_mid(x, y, spec): return (x + spec.w, y + spec.h / 2)
def _top_mid(x, y, spec): return (x + spec.w / 2, y + spec.h)
def _bottom_mid(x, y, spec): return (x + spec.w / 2, y)


# --- Wire helpers -----------------------------------------------------------

def _auto_breakers_subpanel(
    sub: SubPanel, *, per_inverter_ocpd: int, n_inverters: int,
) -> list[InternalBreaker]:
    """Auto-derive a sensible breaker list when sub.breakers is empty."""
    if sub.breakers:
        return sub.breakers
    if sub.role == "pv_aggregation":
        return [
            InternalBreaker(
                rating_a=int(sub.backfeed_breaker_a or per_inverter_ocpd * n_inverters),
                poles=2, label="FEEDER", kind="main",
            ),
        ] + [
            InternalBreaker(rating_a=per_inverter_ocpd, poles=2,
                            label=f"INV-{k + 1}", kind="backfeed")
            for k in range(n_inverters)
        ]
    # critical_loads
    # All labels uppercase + short (≤6 chars) so they fit in the breaker
    # row's left budget at the current internal-breaker font (0.055").
    # "Lighting" was 8 chars and overflowed; "LIGHTS" reads the same and fits.
    return [
        InternalBreaker(
            rating_a=int(sub.backfeed_breaker_a or sub.rating_a),
            poles=2, label="MAIN", kind="main",
        ),
        InternalBreaker(rating_a=30, poles=2, label="HVAC", kind="branch"),
        InternalBreaker(rating_a=20, poles=1, label="LIGHTS", kind="branch"),
    ]


def _auto_breakers_msp(
    service, total_backfeed_a: float, pv_ocpd_for_backfeed: int,
) -> list[InternalBreaker]:
    return [
        InternalBreaker(
            rating_a=int(service.main_panel_a), poles=2,
            label="MAIN", kind="main",
        ),
        InternalBreaker(
            rating_a=pv_ocpd_for_backfeed, poles=2,
            label="PV/ESS", kind="backfeed",
        ),
    ]


def _draw_internal_breakers(
    msp: Modelspace,
    x: float, y: float, w: float, h: float,
    breakers: list,    # list[InternalBreaker]
) -> None:
    """Draw N breaker rows inside a panel box.

    Wyssling-style row layout:

        ┌──────────────────────────────────┐
        │  (N) 2P-50A    ┃═══┃             │   ← label (right-aligned) + notch
        │  (N) 2P-50A    ┃═/═┃             │   ← diagonal slash = breaker symbol
        │  (N) 2P-50A    ┃═══┃             │
        │  (N) 2P-150A   ┃═══┃   (FEEDER)  │   ← optional kind tag for clarity
        └──────────────────────────────────┘

    The notch is drawn as a small rectangle with an internal diagonal
    slash (IEEE 315 "breaker open contact"). FEEDER / MAIN breakers get
    a small tag next to the notch so the inspector can see which row is
    the upstream feed at a glance.
    """
    if not breakers:
        return
    # Inset margins inside the panel outline
    pad_x = 0.08
    pad_y_top = 0.20    # leave room for the panel's centered "SUB"/"MSP" label
    pad_y_bot = 0.12
    inner_w = w - 2 * pad_x
    inner_h = h - pad_y_top - pad_y_bot
    n = len(breakers)
    if n == 0:
        return

    # Notch occupies right ~30% of the row; label takes the rest.
    notch_w = min(0.18, inner_w * 0.30)
    notch_h = 0.06
    row_pitch = inner_h / n

    for k, brk in enumerate(breakers):
        row_y = y + pad_y_bot + (k + 0.5) * row_pitch
        # Notch right-aligned inside the row
        notch_x1 = x + w - pad_x
        notch_x0 = notch_x1 - notch_w

        # Notch rectangle (the breaker housing)
        msp.add_lwpolyline(
            [(notch_x0, row_y - notch_h / 2),
             (notch_x1, row_y - notch_h / 2),
             (notch_x1, row_y + notch_h / 2),
             (notch_x0, row_y + notch_h / 2),
             (notch_x0, row_y - notch_h / 2)],
            close=True,
            dxfattribs={"layer": "EQUIPMENT", "lineweight": STROKE_MED},
        )
        # Diagonal slash inside (IEEE 315 open-contact convention)
        msp.add_line(
            (notch_x0 + 0.012, row_y - notch_h / 2 + 0.012),
            (notch_x1 - 0.012, row_y + notch_h / 2 - 0.012),
            dxfattribs={"layer": "EQUIPMENT"},
        )

        # Two text fields per row, Wyssling style:
        #
        #   [FUNCTION_LABEL]  ……………  [2P-XXA]  ━━╱━━
        #   ↑                          ↑
        #   left-aligned, panel start  right-aligned at notch
        #
        # The "(N)" / "(E)" prefix is NOT repeated on every breaker row —
        # the panel's own header already declares whether the panel + its
        # contents are new or existing ("(N) SUB PANEL #2", etc.). Stripping
        # (N) from each row saves ~4 chars of width and leaves room for the
        # function label (FEEDER / INV-1 / MAIN / PV/ESS / HVAC / LIGHTS).
        font_h = TEXT_CAPTION
        rating = f"{brk.poles}P-{brk.rating_a}A"
        msp.add_text(
            rating, height=font_h,
            dxfattribs={"layer": "ANNOTATION"},
        ).set_placement(
            (notch_x0 - 0.04, row_y - 0.025),
            align=TextEntityAlignment.RIGHT,
        )
        if brk.label:
            from ._textfit import fit_dxf, estimate_text_width
            # Width budget = panel start → (rating left edge − 0.08" gap).
            # Generous gap because matplotlib backend renders ~10% wider
            # than our CHAR_WIDTH_RATIO=0.6 estimate; the visual gap then
            # remains clearly readable rather than crunched.
            rating_w = estimate_text_width(rating, font_h)
            max_fn_w = (notch_x0 - 0.04 - rating_w - 0.08) - (x + pad_x)
            fn_text = fit_dxf(brk.label, max_fn_w, font_h)
            msp.add_text(
                fn_text, height=font_h,
                dxfattribs={"layer": "ANNOTATION"},
            ).set_placement(
                (x + pad_x, row_y - 0.025),
                align=TextEntityAlignment.LEFT,
            )


def _wire(msp: Modelspace, layer: str, *pts: tuple[float, float], tag: str = "") -> None:
    """Draw a polyline (orthogonal routing assumed); optionally label with a wire tag."""
    msp.add_lwpolyline(pts, dxfattribs={"layer": layer})
    if tag:
        x1, y1 = pts[0]
        x2, y2 = pts[1]
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        msp.add_text(
            tag,
            height=TEXT_HEADER,
            dxfattribs={"layer": "ANNOTATION"},
        ).set_placement((mx, my + 0.08), align=TextEntityAlignment.MIDDLE_CENTER)


def _breaker_symbol(
    msp: Modelspace,
    x: float, y: float, *,
    rating_a: int,
    n_poles: int = 2,
    horizontal_wire: bool = True,
) -> None:
    """Inline circuit-breaker symbol: small open-switch rectangle on the wire
    with a "<poles>P-<rating>A" caption underneath.

    Placed at the entry of each backfed panel / inverter AC output. Symbol
    semantics: rectangle = the breaker housing; internal slash = open contact.
    """
    w, h = 0.16, 0.11
    if horizontal_wire:
        box = [
            (x - w / 2, y - h / 2),
            (x + w / 2, y - h / 2),
            (x + w / 2, y + h / 2),
            (x - w / 2, y + h / 2),
            (x - w / 2, y - h / 2),
        ]
        slash = [(x - w / 2 + 0.02, y - h / 2 + 0.02),
                 (x + w / 2 - 0.02, y + h / 2 - 0.02)]
        label_pos = (x, y - h / 2 - 0.10)
    else:
        # Vertical-wire orientation: rotate the box 90°
        box = [
            (x - h / 2, y - w / 2),
            (x + h / 2, y - w / 2),
            (x + h / 2, y + w / 2),
            (x - h / 2, y + w / 2),
            (x - h / 2, y - w / 2),
        ]
        slash = [(x - h / 2 + 0.02, y - w / 2 + 0.02),
                 (x + h / 2 - 0.02, y + w / 2 - 0.02)]
        label_pos = (x + h / 2 + 0.05, y)
    msp.add_lwpolyline(
        box, close=True,
        dxfattribs={"layer": "EQUIPMENT", "lineweight": STROKE_MED},
    )
    msp.add_line(slash[0], slash[1], dxfattribs={"layer": "EQUIPMENT"})
    msp.add_text(
        f"{n_poles}P-{rating_a}A",
        height=TEXT_CAPTION,
        dxfattribs={"layer": "ANNOTATION"},
    ).set_placement(
        label_pos,
        align=TextEntityAlignment.MIDDLE_CENTER if horizontal_wire
            else TextEntityAlignment.LEFT,
    )


# Multi-conductor wire bundle: spread N parallel lines perpendicular to the
# wire direction so the schematic communicates polarity / phase count without
# a separate three-line section. AC = 3 lines (L1/L2/N), DC = 2 (+/−).
PHASE_SPACING = 0.04
GROUND_GAP = 0.05


def _wire_bus(
    msp: Modelspace,
    src: tuple[float, float],
    dst: tuple[float, float],
    *,
    kind: str,           # "DC" or "AC"
    tag: str = "",
    show_ground: bool = True,
) -> None:
    """Render a multi-conductor bus between two axis-aligned points.

    Each conductor is on its own phase-specific layer so colors match the
    industry convention (DC+ red, DC− black, L1 black, L2 red, N gray, G green).

    `kind="AC"` → L1/L2/N parallel lines.
    `kind="DC"` → +/− parallel lines.
    Optional grounding conductor on WIRE_GROUND.
    """
    if kind == "DC":
        phase_layers = DC_PHASE_LAYERS
    elif kind == "AC":
        phase_layers = AC_PHASE_LAYERS
    else:
        msp.add_lwpolyline([src, dst], dxfattribs={"layer": kind})
        return
    n = len(phase_layers)

    dx, dy = dst[0] - src[0], dst[1] - src[1]
    horizontal = abs(dx) >= abs(dy)

    def offset_pt(pt, axis_offset):
        # axis_offset is perpendicular to wire direction
        return (pt[0], pt[1] + axis_offset) if horizontal else (pt[0] + axis_offset, pt[1])

    # Phase lines on their own colored layers
    for i, layer in enumerate(phase_layers):
        off = (i - (n - 1) / 2) * PHASE_SPACING
        msp.add_lwpolyline(
            [offset_pt(src, off), offset_pt(dst, off)],
            dxfattribs={"layer": layer},
        )

    # Ground line: offset further on the "negative" side of the bundle
    if show_ground:
        g_off = -((n - 1) / 2) * PHASE_SPACING - GROUND_GAP
        msp.add_lwpolyline(
            [offset_pt(src, g_off), offset_pt(dst, g_off)],
            dxfattribs={"layer": "WIRE_GROUND"},
        )

    if tag:
        mx, my = (src[0] + dst[0]) / 2, (src[1] + dst[1]) / 2
        # Place tag well clear of the bundle
        label_y_off = ((n - 1) / 2) * PHASE_SPACING + 0.18
        callout_pos = (
            (mx, my + label_y_off) if horizontal else (mx + label_y_off, my)
        )
        # Wyssling-style callout: letter inside a circle. Single-letter tags
        # ("A"/"B"/"C"/"D") get the standard callout; longer tags (e.g.
        # "C×3" — used when annotating per-inverter parallel runs) fall
        # back to plain text since they don't fit in a 0.10" circle.
        if len(tag) <= 2:
            sym.draw_callout_circle(msp, callout_pos[0], callout_pos[1], tag)
        else:
            msp.add_text(
                tag,
                height=TEXT_HEADER,
                dxfattribs={"layer": "ANNOTATION"},
            ).set_placement(
                callout_pos,
                align=TextEntityAlignment.MIDDLE_CENTER,
            )


# --- Sheet frame / title block / schedule ----------------------------------

def _draw_frame(msp: Modelspace) -> None:
    """Drawing border + title block frame + schedule frame."""
    # Outer border
    msp.add_lwpolyline(
        [
            (MARGIN, MARGIN),
            (SHEET_W - MARGIN, MARGIN),
            (SHEET_W - MARGIN, SHEET_H - MARGIN),
            (MARGIN, SHEET_H - MARGIN),
            (MARGIN, MARGIN),
        ],
        close=True,
        dxfattribs={"layer": "BORDER", "lineweight": STROKE_HEAVY},
    )

    # Title block frame
    msp.add_lwpolyline(
        [
            (RIGHT_X0, TB_Y0),
            (RIGHT_X1, TB_Y0),
            (RIGHT_X1, TB_Y1),
            (RIGHT_X0, TB_Y1),
            (RIGHT_X0, TB_Y0),
        ],
        close=True,
        dxfattribs={"layer": "TITLE_BLOCK", "lineweight": STROKE_MED},
    )
    # Schedule frame
    msp.add_lwpolyline(
        [
            (RIGHT_X0, SCHED_Y0),
            (RIGHT_X1, SCHED_Y0),
            (RIGHT_X1, SCHED_Y1),
            (RIGHT_X0, SCHED_Y1),
            (RIGHT_X0, SCHED_Y0),
        ],
        close=True,
        dxfattribs={"layer": "SCHEDULE", "lineweight": STROKE_MED},
    )


def _draw_title_block(msp: Modelspace, result: CalculationResult) -> None:
    """Stacked title block: ENGINEER / INSTALLER / CLIENT-SITE / DRAWING.

    Each section is bordered for visual separation and matches the layout
    convention of professional permit drawings (firm-of-record on top, install
    company next, project/client info, then the sheet metadata at the bottom).
    """
    i = result.inputs
    eng = i.design_engineer
    inst = i.installer
    n_inv = i.inverter.count(i.battery.quantity)
    dc_kw = i.pv_array.modules * i.pv_array.module.power_w / 1000.0
    ac_kw = i.inverter.ac_output_v * i.inverter.ac_output_a * n_inv / 1000.0

    sheet_code = getattr(result, "_active_sheet_display_code", "EE-1")
    sheet_title = getattr(result, "_active_sheet_title", "Three-Line Diagram").upper()

    sections: list[tuple[str, list[str]]] = [
        ("DESIGN ENGINEER", [
            eng.firm or "—",
            eng.address or "",
            (eng.contact_email + ("  ·  " + eng.contact_phone if eng.contact_phone else ""))
                if eng.contact_email else (eng.contact_phone or ""),
            (f"FIRM #: {eng.firm_number}" if eng.firm_number else ""),
        ]),
        ("INSTALLER / SOLAR COMPANY", [
            inst.company or "—",
            inst.address or "",
        ]),
        ("CLIENT / SITE", [
            i.project.client_name or i.project.name,
            i.project.site_address or i.project.location,
            (f"APN: {i.project.apn}" if i.project.apn else "")
                + ("    " + i.project.coordinates if i.project.coordinates else ""),
            f"AHJ: {i.project.ahj}"
                + (f"    UTILITY: {i.project.utility}" if i.project.utility else ""),
        ]),
        ("DRAWING", [
            f"SHEET: {sheet_code}  ·  {sheet_title}",
            f"NEC: {i.project.nec_edition}    PROJECT ID: {i.project.id}",
            f"REV: {i.project.revision}"
                + (f"    DATE: {i.project.initial_design_date}"
                   if i.project.initial_design_date else "")
                + (f"    DRAWN: {i.project.drawn_by}" if i.project.drawn_by else ""),
            f"DC SIZE: {dc_kw:.2f} kW    AC SIZE: {ac_kw:.2f} kW",
        ]),
    ]

    # Divide TB area evenly among sections (top → bottom).
    sect_h = TITLE_BLOCK_H / len(sections)
    for idx, (header, body) in enumerate(sections):
        # `idx=0` is the top section (highest y).
        sect_top = TB_Y1 - idx * sect_h
        sect_bot = sect_top - sect_h
        # Divider line above each section (skip the top border, that's the frame)
        if idx > 0:
            msp.add_line(
                (RIGHT_X0, sect_top), (RIGHT_X1, sect_top),
                dxfattribs={"layer": "TITLE_BLOCK"},
            )
        # Header strip (shaded bar)
        hb_h = 0.22
        msp.add_lwpolyline(
            [(RIGHT_X0, sect_top - hb_h), (RIGHT_X1, sect_top - hb_h)],
            dxfattribs={"layer": "TITLE_BLOCK"},
        )
        msp.add_text(
            header, height=TEXT_HEADER,
            dxfattribs={"layer": "TITLE_BLOCK"},
        ).set_placement(
            ((RIGHT_X0 + RIGHT_X1) / 2, sect_top - hb_h / 2 - 0.03),
            align=TextEntityAlignment.MIDDLE_CENTER,
        )
        # Body lines (tight spacing so 4–5 lines fit per section)
        y = sect_top - hb_h - 0.14
        for line in body:
            if not line:
                continue
            msp.add_text(
                line, height=TEXT_BODY,
                dxfattribs={"layer": "TITLE_BLOCK"},
            ).set_placement(
                (RIGHT_X0 + 0.10, y), align=TextEntityAlignment.LEFT,
            )
            y -= 0.14
            if y <= sect_bot + 0.03:
                break  # overflow guard


def _per_inverter_ac_spec(result: CalculationResult) -> tuple[int, "ConductorResult"]:
    """Per-inverter AC OCPD + conductor sizing (continuous load × 1.25).

    Apply the SAME NEC 310.15(B) environmental derating (ambient
    temperature + conduit fill) as the aggregate AC trunk uses. Before
    2026-05-14 this helper passed `derating_factor=1.0`, which silently
    undersized per-inverter conductors in hot-ambient projects
    (e.g. Phoenix: nominal 50 A × 0.82 actually = 41 A, just below the
    41.25 A requirement, forcing the next size up).

    For Phoenix 3 × 8 kW @ 33 A each: 33 × 1.25 = 41.25 → 45 A OCPD.
    With ac_derating 0.82, the smallest copper at 75°C is 6 AWG
    (65 × 0.82 = 53 A, headroom 11.75 A).
    """
    from ..calc.conductor import ConductorResult  # local for forward type ref
    inv = result.inputs.inverter
    min_a = inv.ac_output_a * 1.25
    ocpd = select_ocpd(min_a)
    cond = select_copper(
        min_a, "75C",
        upstream_ocpd_a=ocpd,
        derating_factor=result.ac_derating_factor,
    )
    return ocpd, cond


def _draw_conductor_schedule(msp: Modelspace, result: CalculationResult) -> None:
    """Tagged conductor schedule — 9 columns, AHJ permit convention.

    Each row corresponds to a callout (A/B/C/D) on the EE-1 SLD. Columns:

        TAG · WIRES · SIZE · TYPE · GND · CONDUIT · AMPS · AMPCY · OCPD

    GND and CONDUIT are computed from `result.grounding` and
    `result.adjacent` respectively (NOT hardcoded — earlier version
    embedded literals that happened to match the Phoenix fixture but
    silently lied for any other project). AMPS = base current per NEC
    690.8(A) / 215.2; AMPCY = conductor's effective ampacity after
    310.15 derating; OCPD = NEC 240.6 next-standard ≥ AMPS × 1.25.

    The previous "×1.25" column was dropped — it's the trivial product
    of AMPS × 1.25, recoverable by anyone reading the table.
    """
    i = result.inputs
    cond = result.pv_conductor
    ess_cond = result.ess_conductor
    g = result.grounding
    adj = result.adjacent
    per_inv_ocpd, per_inv_cond = _per_inverter_ac_spec(result)
    n_inv = i.inverter.count(i.battery.quantity)

    # Base currents (BEFORE the conductor/OCPD 1.25× multiplier).
    pv_base   = result.pv_string.isc_690_8_a            # Isc × 1.25 (690.8(A)(1))
    pi_base   = i.inverter.ac_output_a                  # per-inverter continuous
    bf_base   = result.interconnect.total_backfeed_a    # aggregate continuous

    c_tag = "C" + (f"×{n_inv}" if n_inv > 1 else "")

    # Conduit strings. PV Row A is "FREE AIR" because module-to-combiner
    # USE-2 jumpers run exposed on the roof (NEC 690.31(C) exception).
    # All other paths are EMT sized from `adj.*.selected_conduit`, which
    # already carries the trade-size inch mark (e.g. '1-1/2"').
    pv_emt  = f"{adj.pv_conduit.selected_conduit} EMT"
    ac_emt  = f"{adj.ac_conduit.selected_conduit} EMT"

    # (tag, wires, size, type, ground, conduit, amps, ampacity, ocpd)
    rows: list[tuple[str, ...]] = [
        ("A", "2+G", f"{cond.size} AWG", "THWN-2 CU",
         f"{g.egc_pv_source} AWG", "FREE AIR",
         f"{pv_base:.1f}", f"{cond.ampacity_a}", f"{result.pv_ocpd_a}"),
        ("B", "2+G", f"{cond.size} AWG", "THWN-2 CU",
         f"{g.egc_pv_source} AWG", pv_emt,
         f"{pv_base:.1f}", f"{cond.ampacity_a}", f"{result.pv_ocpd_a}"),
        (c_tag, "3+G", f"{per_inv_cond.size} AWG", "THWN-2 CU",
         f"{g.egc_inverter_ac} AWG", ac_emt,
         f"{pi_base:.1f}", f"{per_inv_cond.ampacity_a}", f"{per_inv_ocpd}"),
        ("D", "3+G", f"{ess_cond.size} AWG", "THWN-2 CU",
         f"{g.egc_aggregate_ac} AWG", ac_emt,
         f"{bf_base:.1f}", f"{ess_cond.ampacity_a}",
         f"{result.ess.ac_disconnect_ocpd_a}"),
    ]

    # Header bar
    hb_h = 0.30
    msp.add_lwpolyline(
        [(RIGHT_X0, SCHED_Y1 - hb_h), (RIGHT_X1, SCHED_Y1 - hb_h)],
        dxfattribs={"layer": "SCHEDULE"},
    )
    msp.add_text(
        "CONDUCTOR SCHEDULE",
        height=TEXT_TITLE,
        dxfattribs={"layer": "SCHEDULE"},
    ).set_placement(((RIGHT_X0 + RIGHT_X1) / 2, SCHED_Y1 - hb_h / 2),
                    align=TextEntityAlignment.MIDDLE_CENTER)

    # Column layout: 9 columns (×1.25 dropped — see docstring).
    # Width budget: 4.5" frame; offsets tuned so each column has at
    # least ~0.07" of clearance from its right neighbor at production
    # text widths.  Column headers render at TEXT_BODY (NOT _HEADER) —
    # the TITLE bar carries the table's visual prominence, and same-
    # size header/data with an underline is more conventional table
    # typography than oversized headers crashing into each other.
    cols = [
        ("TAG",       0.07),
        ("WIRES",     0.34),
        ("SIZE",      0.74),
        ("TYPE",      1.27),
        ("GND",       1.95),
        ("CONDUIT",   2.42),
        ("AMPS",      3.13),
        ("AMPCY",     3.52),
        ("OCPD",      3.96),
    ]
    col_y = SCHED_Y1 - hb_h - 0.20
    for name, x0 in cols:
        msp.add_text(
            name, height=TEXT_BODY,
            dxfattribs={"layer": "SCHEDULE"},
        ).set_placement((RIGHT_X0 + x0, col_y), align=TextEntityAlignment.LEFT)

    # Header underline
    msp.add_line(
        (RIGHT_X0, col_y - 0.05),
        (RIGHT_X1, col_y - 0.05),
        dxfattribs={"layer": "SCHEDULE"},
    )

    # Rows
    y = col_y - 0.20
    for row in rows:
        for (_, x0), val in zip(cols, row):
            msp.add_text(
                val, height=TEXT_BODY,
                dxfattribs={"layer": "SCHEDULE"},
            ).set_placement((RIGHT_X0 + x0, y), align=TextEntityAlignment.LEFT)
        y -= 0.18


def _draw_notes(msp: Modelspace, result: CalculationResult) -> None:
    """General notes strip across the top-left.

    Layout: bold section labels left, values right, one fact per line. Easier
    to scan than the previous comma-soup format.
    """
    i = result.inputs
    n_inv = i.inverter.count(i.battery.quantity)
    dc_kw = i.pv_array.modules * i.pv_array.module.power_w / 1000.0
    ac_kw = i.inverter.ac_output_v * i.inverter.ac_output_a * n_inv / 1000.0
    total_ac_a = i.inverter.ac_output_a * n_inv

    rows: list[tuple[str, str]] = [
        ("SYSTEM:",
         f"DC {dc_kw:.2f} kW    AC {ac_kw:.2f} kW"),
        ("PV ARRAY:",
         f"({i.pv_array.modules}) {i.pv_array.module.brand} {i.pv_array.module.model} "
         f"— ({i.pv_array.strings}) strings × ({i.pv_array.modules_per_string}) modules"),
    ]
    if i.optimizer.brand:
        opt_n = i.optimizer.effective_count(i.pv_array.modules, i.pv_array.strings)
        rows.append((
            "OPTIMIZER:",
            f"({opt_n}) {i.optimizer.brand} {i.optimizer.model} "
            f"({i.optimizer.type.replace('_', ' ')}, 1 per "
            f"{'module' if i.optimizer.count == 'per_module' else 'string'})"
        ))
    rows.extend([
        ("INVERTER:",
         f"({n_inv}) {i.inverter.brand} {i.inverter.model} — "
         f"{i.inverter.ac_output_a:.0f} A AC each, {total_ac_a:.0f} A total @ {i.inverter.ac_output_v:.0f} V"),
        ("INTERCONNECT:",
         f"{result.interconnect.recommended or 'FAIL'} per NEC 705"),
        ("NOTES:",
         "All equipment shall be installed per manufacturer's listing and AHJ requirements."),
    ])

    y = SHEET_H - MARGIN - 0.22
    for label, value in rows:
        msp.add_text(
            label, height=TEXT_HEADER,
            dxfattribs={"layer": "NOTES"},
        ).set_placement((MARGIN + 0.2, y), align=TextEntityAlignment.LEFT)
        msp.add_text(
            value, height=TEXT_HEADER,
            dxfattribs={"layer": "NOTES"},
        ).set_placement((MARGIN + 1.4, y), align=TextEntityAlignment.LEFT)
        y -= 0.16


# --- Main schematic ---------------------------------------------------------

def _draw_schematic(msp: Modelspace, doc: Drawing, result: CalculationResult) -> None:
    """Render the SLD with N parallel inverters and DC/AC trunk buses.

    Topology (trunk-tap, 3-line style):

        PV ── COMB ── RSD ──┐  DC trunk
                            ├──── INV-1 ──┐  AC trunk
                            ├──── INV-2 ──┤
                            ├──── INV-3 ──┤── AC-DISC ── MSP
                                          │
                            ESS ──────────┘ (battery DC to middle inverter)
    """
    i = result.inputs
    n_inv = i.inverter.count(i.battery.quantity)
    per_inv_ocpd, per_inv_cond = _per_inverter_ac_spec(result)

    # --- Device specs ---
    # Multi-string mode kicks in when the array has >1 source circuits, which
    # is the realistic case for any system above ~5kW. Each string gets its
    # own slim PV symbol, then they fan into the combiner via a vertical bus.
    n_strings = i.pv_array.strings
    multi_string = n_strings > 1
    pv_per_string_w = 0.7 if multi_string else 1.0
    pv_per_string_h = 0.5 if multi_string else 0.7

    # Aggregate spec (used in single-string mode AND as the catalog row).
    pv = DeviceSpec(
        tag="PV-1", label="PV",
        desc1=f"({i.pv_array.modules}) {i.pv_array.module.model}",
        desc2=f"{i.pv_array.strings}S × {i.pv_array.modules_per_string}M = {i.pv_array.modules}",
        mfg=i.pv_array.module.brand,
        cat=f"{i.pv_array.module.power_w:.0f} W",
        w=pv_per_string_w, h=pv_per_string_h,
    )

    # Per-string specs (only used when multi_string=True).
    pv_string_specs = [
        DeviceSpec(
            tag=f"PV-S{k + 1}", label="PV",
            desc1=f"({i.pv_array.modules_per_string}) modules",
            desc2="",
            mfg="", cat="",
            w=pv_per_string_w, h=pv_per_string_h,
        )
        for k in range(n_strings)
    ]
    combiner = DeviceSpec(
        tag="DC-COMB-1", label="COMB",
        desc1=f"OCPD: {result.pv_ocpd_a} A",
        desc2=f"COND: {result.pv_conductor.size} AWG",
        w=1.0, h=0.7,
    )
    rsd = DeviceSpec(
        tag="RSD-1", label="RSD",
        desc1="Per inverter mfr",
        desc2="(NEC 690.12)",
        w=1.0, h=0.7,
    )
    # Inverter box dimensions widened from 1.2×0.7 to 1.6×0.9 so the
    # Wyssling-style product-accurate geometry (DC ladder + 3 bays
    # GEN/LOAD/GRID + terminal blocks) fits without crowding.
    inverter_specs = [
        DeviceSpec(
            tag=f"INV-{k + 1}", label="INV",
            desc1=f"{i.inverter.brand} {i.inverter.model}",
            desc2=f"{i.inverter.ac_output_v:.0f} V / {i.inverter.ac_output_a:.0f} A AC",
            mfg="",  # brand already in DESC1
            cat="",  # model already in DESC1
            w=1.6, h=0.9,
        )
        for k in range(n_inv)
    ]
    ess = DeviceSpec(
        tag="ESS-1", label="ESS",
        desc1=f"{i.battery.brand} {i.battery.model}",
        desc2=f"({i.battery.quantity}) × {i.battery.capacity_kwh_each:.2f} kWh = {i.battery.total_kwh:.1f} kWh",
        mfg="",  # brand already in DESC1
        cat="",  # model already in DESC1
        w=1.2, h=0.7,
    )
    # AC chain after the inverter bus.
    # Sub-panels split by role:
    #   - `pv_aggregation` panels sit in series in the AC chain
    #     (AC-DISC → SUB-N → ... → MSP).
    #   - `critical_loads` panels render as a separate branch *below* the MSP,
    #     out of the PV→grid path (typical residential ESS-backup wiring).
    aggregation_subs = [sp for sp in i.service.sub_panels if sp.role == "pv_aggregation"]
    critical_subs    = [sp for sp in i.service.sub_panels if sp.role == "critical_loads"]
    has_subs = bool(aggregation_subs)   # affects horizontal density
    chain_gap  = 0.45 if has_subs else 0.6

    # Wyssling-style proportions: sub-panels and MSP are TALLER than wide
    # so the breaker stack is clearly readable; AC-DISC stays roughly
    # square because it's a single switch element. Each device type gets
    # its own size — they don't share `chain_h` anymore.
    #
    # Width budget check (with has_subs=True): AC-DISC(0.85) + 0.45 +
    # SUB(1.0) + 0.45 + MSP(1.0) + 0.45 + METER(0.55) = 4.75". Plus
    # x_acdisc offset (~6.65) → chain_end ≈ 11.4. SCHEMATIC_X1 = 11.8,
    # so 0.4" slack remains.
    AC_DISC_W, AC_DISC_H = (0.85, 0.85)
    SUB_W,     SUB_H     = (1.00, 1.40)   # ~1.5× taller than inverter
    MSP_W,     MSP_H     = (1.00, 1.60)   # tallest — main service panel

    ac_disc = DeviceSpec(
        tag="AC-DISC-1", label="AC DISC",
        desc1=f"OCPD: {result.ess.ac_disconnect_ocpd_a} A",
        desc2=f"COND: {result.ess_conductor.size} AWG",
        w=AC_DISC_W, h=AC_DISC_H,
    )

    # Short label forms; full location lives in inputs.yaml, not on the box.
    def _spec_for(sp):
        return DeviceSpec(
            tag=sp.name.replace("Sub Panel ", "SUB-").upper(),
            label="SUB",
            desc1=f"{int(sp.rating_a)}A panel",
            desc2=f"BUS {int(sp.busbar_a)}A",
            mfg=f"BF {int(sp.backfeed_breaker_a)}A" if sp.backfeed_breaker_a else "",
            cat="",
            w=SUB_W, h=SUB_H,
        )
    aggregation_specs = [_spec_for(sp) for sp in aggregation_subs]
    critical_specs    = [_spec_for(sp) for sp in critical_subs]
    # Backwards-compat alias used below
    subpanel_specs = aggregation_specs

    # Short descriptions everywhere — MSP/METER text must not bleed into the
    # conductor schedule. Service voltage / busbar source live in the title
    # block; the device-side caption stays compact.
    msp_desc1 = f"{int(i.service.main_panel_a)}A main"
    msp_desc2 = f"BUS {int(i.service.busbar_a)}A"
    meter_desc1 = i.project.utility or "UTIL"
    meter_desc2 = "240V"

    msp_dev = DeviceSpec(
        tag="MSP", label="MSP",
        desc1=msp_desc1, desc2=msp_desc2,
        w=MSP_W, h=MSP_H,
    )
    meter_dev = DeviceSpec(
        tag="METER",
        label="M",
        desc1=meter_desc1, desc2=meter_desc2,
        w=0.55, h=0.55,
    )

    # --- Layout ---
    # Anchor the top of the inverter stack below the notes strip.
    # NOTES_AREA_H reserves vertical room for the 6-line notes block and
    # the full multi-string PV fan-in bus. It governs how far DOWN the
    # entire schematic column shifts; smaller values let PV-S1/bus geometry
    # cross the INVERTER / INTERCONNECT notes block.
    LABEL_BLOCK = 0.95
    NOTES_AREA_H = 1.85
    inv_pitch = 1.8
    top_inv_y_center = SCHEMATIC_Y1 - NOTES_AREA_H - 0.3 - inverter_specs[0].h / 2
    inv_y_centers = [top_inv_y_center - k * inv_pitch for k in range(n_inv)]
    main_center_y = inv_y_centers[n_inv // 2] if inv_y_centers else top_inv_y_center
    inv_bot_center = inv_y_centers[-1] if inv_y_centers else main_center_y
    inv_top_center = inv_y_centers[0] if inv_y_centers else main_center_y

    def y_for(spec): return main_center_y - spec.h / 2

    # Left-side device sizes shrink when sub-panels add to the chain length,
    # so the whole row still fits inside the schematic area.
    left_dev_w = 0.75 if has_subs else 1.0
    pv.w = combiner.w = rsd.w = left_dev_w

    x_pv       = SCHEMATIC_X0 + (0.3 if has_subs else 0.4)
    x_combiner = x_pv       + pv.w       + chain_gap
    x_rsd      = x_combiner + combiner.w + chain_gap
    dc_trunk_x = x_rsd      + rsd.w      + chain_gap
    trunk_gap  = 0.25 if has_subs else 0.3
    x_inv      = dc_trunk_x + trunk_gap
    inv_w      = inverter_specs[0].w
    inv_h      = inverter_specs[0].h
    ac_trunk_x = x_inv + inv_w + trunk_gap
    x_acdisc   = ac_trunk_x + (0.35 if has_subs else 0.6)
    # Build the right-side device chain: AC-DISC → sub-panels → MSP → METER.
    chain = [(ac_disc, x_acdisc)]
    x_cursor = x_acdisc + ac_disc.w + chain_gap
    for sp_spec in subpanel_specs:
        chain.append((sp_spec, x_cursor))
        x_cursor += sp_spec.w + chain_gap
    chain.append((msp_dev, x_cursor))
    x_cursor += msp_dev.w + chain_gap
    chain.append((meter_dev, x_cursor))
    chain_end_x = x_cursor + meter_dev.w

    # ESS sits below the bottom inverter; leave room for the inverter's
    # 5-line attribute block (~0.95") above the ESS box.
    x_ess = x_inv + (inv_w - ess.w) / 2
    y_ess = inv_bot_center - inv_h / 2 - LABEL_BLOCK - 0.25 - ess.h

    # --- Place critical-loads sub-panels (branch off MSP, not in main chain) ---
    def _place_critical_panels(modelspace, doc_ref, per_inv_ocpd_local, n_inv_local) -> None:
        if not critical_specs:
            return
        msp_spec, msp_x_pos = chain[-2]
        msp_y = y_for(msp_spec)
        msp_bottom = msp_y
        # gap_above: vertical distance from MSP bottom to the critical
        # sub-panel TOP edge. Must clear three stacked items in that
        # corridor: (a) MSP's ATTDEF block (~0.46"), (b) the (E) callout
        # circle on the connecting wire (radius 0.10 + clearance), and
        # (c) the SUB-#1 header text above its top edge (~0.30").
        # 0.8 was tight; 1.2 separates them cleanly.
        gap_above = 1.2
        per_panel_pitch = 0.95 + critical_specs[0].h + 0.10
        for k, spec in enumerate(critical_specs):
            crit_x = msp_x_pos + (msp_spec.w - spec.w) / 2
            crit_y = msp_bottom - gap_above - spec.h - k * per_panel_pitch
            _add_device(modelspace, doc_ref, crit_x, crit_y, spec)
            # Wyssling-style 2-line header — placed to the LEFT of the
            # critical sub-panel, not above, because the connecting wire
            # from MSP comes straight down through the panel's top-center
            # and would otherwise cross the header text mid-letter.
            # Text is right-aligned, ending just left of the panel edge.
            crit_sub = critical_subs[k]
            label_x_right = crit_x - 0.10
            label_y_top = crit_y + spec.h - 0.05    # near panel top
            modelspace.add_text(
                f"(N) {crit_sub.name.upper()}",
                height=TEXT_BODY,
                dxfattribs={"layer": "EQUIPMENT_TEXT"},
            ).set_placement(
                (label_x_right, label_y_top),
                align=TextEntityAlignment.RIGHT,
            )
            modelspace.add_text(
                f"{int(crit_sub.rating_a)}A · 120/240V",
                height=TEXT_CAPTION,
                dxfattribs={"layer": "EQUIPMENT_TEXT"},
            ).set_placement(
                (label_x_right, label_y_top - 0.14),
                align=TextEntityAlignment.RIGHT,
            )
            # Inline breakers inside the critical-loads panel
            breakers = _auto_breakers_subpanel(
                crit_sub,
                per_inverter_ocpd=per_inv_ocpd_local,
                n_inverters=n_inv_local,
            )
            _draw_internal_breakers(modelspace, crit_x, crit_y, spec.w, spec.h, breakers)
            # Tagged AC wire from MSP bottom center to critical panel top
            _wire_bus(
                modelspace,
                (msp_x_pos + msp_spec.w / 2, msp_bottom),
                (crit_x + spec.w / 2, crit_y + spec.h),
                kind="AC",
                show_ground=False,
                tag="E" if k == 0 else "",
            )

    # --- Place static devices ---
    if multi_string:
        # Stack N PV string boxes vertically, centered on the main row. Pitch
        # 0.95" clears box (0.5") + 2-line label block (~0.32") + breathing
        # room (~0.13") so adjacent PV strings don't visually crowd each other.
        pv_pitch = 0.95
        total = (n_strings - 1) * pv_pitch
        pv_y_centers = [main_center_y + total / 2 - k * pv_pitch
                        for k in range(n_strings)]
        for spec, yc in zip(pv_string_specs, pv_y_centers):
            _add_device(msp, doc, x_pv, yc - spec.h / 2, spec)
    else:
        _add_device(msp, doc, x_pv, y_for(pv), pv)

    for spec, x in [(combiner, x_combiner), (rsd, x_rsd)]:
        _add_device(msp, doc, x, y_for(spec), spec)
    # Right-side chain (AC-DISC → aggregation subs → MSP → METER)
    main_backfeed_ocpd = result.ess.ac_disconnect_ocpd_a
    for spec, x in chain:
        _add_device(msp, doc, x, y_for(spec), spec)
        # Wyssling-style 2-line header above each panel-style device.
        # Adjacent panels are only ~1.3" center-to-center so the text must
        # fit within ~0.85" of width — keep lines short (≤17 chars at
        # height 0.075 ≈ 0.7"). The voltage/AIC qualifier sits on its
        # own line just above the box.
        if spec is not meter_dev:
            sp_top = y_for(spec) + spec.h
            if spec in aggregation_specs:
                idx = aggregation_specs.index(spec)
                sub_yaml = aggregation_subs[idx]
                line1 = f"(N) {sub_yaml.name.upper()}"           # e.g. (N) SUB PANEL #2
                line2 = f"{int(sub_yaml.rating_a)}A · 120/240V"
            elif spec is msp_dev:
                line1 = "(E) MAIN SERVICE"
                line2 = f"{int(i.service.main_panel_a)}A · 120/240V"
            else:
                line1 = line2 = ""
            if line1:
                # Top line (higher y) is the main descriptor; lower line
                # carries rating + voltage so the inspector sees both
                # without zooming in.
                msp.add_text(
                    line1,
                    height=TEXT_BODY,
                    dxfattribs={"layer": "EQUIPMENT_TEXT"},
                ).set_placement(
                    (x + spec.w / 2, sp_top + 0.20),
                    align=TextEntityAlignment.MIDDLE_CENTER,
                )
                msp.add_text(
                    line2,
                    height=TEXT_CAPTION,
                    dxfattribs={"layer": "EQUIPMENT_TEXT"},
                ).set_placement(
                    (x + spec.w / 2, sp_top + 0.07),
                    align=TextEntityAlignment.MIDDLE_CENTER,
                )
        # Draw internal breakers inside aggregation sub-panels & MSP
        if spec in aggregation_specs:
            idx = aggregation_specs.index(spec)
            breakers = _auto_breakers_subpanel(
                aggregation_subs[idx],
                per_inverter_ocpd=per_inv_ocpd,
                n_inverters=n_inv,
            )
            _draw_internal_breakers(msp, x, y_for(spec), spec.w, spec.h, breakers)
        elif spec is msp_dev:
            breakers = _auto_breakers_msp(
                i.service,
                total_backfeed_a=result.interconnect.total_backfeed_a,
                pv_ocpd_for_backfeed=main_backfeed_ocpd,
            )
            _draw_internal_breakers(msp, x, y_for(spec), spec.w, spec.h, breakers)
            # Wyssling-style: N-G bond annotation just inside the MSP's
            # bottom-left, calling out the service-entrance neutral-ground
            # bond (NEC 250.24(C)). Small horizontal accent line + label.
            ng_x = x + 0.08
            ng_y = y_for(spec) + 0.08
            msp.add_line(
                (ng_x, ng_y), (ng_x + spec.w * 0.40, ng_y),
                dxfattribs={"layer": "WIRE_GROUND", "lineweight": STROKE_HEAVY},
            )
            msp.add_text(
                "N-G BOND",
                height=TEXT_CAPTION,
                dxfattribs={"layer": "ANNOTATION"},
            ).set_placement(
                (ng_x + spec.w * 0.45, ng_y - 0.04),
                align=TextEntityAlignment.LEFT,
            )
    # Critical-loads sub-panels branch off below MSP
    _place_critical_panels(msp, doc, per_inv_ocpd, n_inv)

    # --- Place inverters ---
    # Wyssling-style: a one-line header sits ABOVE each inverter box
    # ("(N) {brand} {model} INVERTER #k MINIMUM 10KIAC"). The 5-line
    # ATTDEF block below is kept for AutoCAD attribute compatibility,
    # but the header above is what the human reviewer reads first.
    for k, (spec, yc) in enumerate(zip(inverter_specs, inv_y_centers)):
        inv_y = yc - inv_h / 2
        _add_device(msp, doc, x_inv, inv_y, spec)
        msp.add_text(
            f"(N) {i.inverter.brand} {i.inverter.model} INVERTER #{k + 1}",
            height=TEXT_BODY,
            dxfattribs={"layer": "EQUIPMENT_TEXT"},
        ).set_placement(
            (x_inv + inv_w / 2, inv_y + inv_h + 0.08),
            align=TextEntityAlignment.MIDDLE_CENTER,
        )

    # --- Place ESS ---
    _add_device(msp, doc, x_ess, y_ess, ess)

    # --- Wires ---
    cy = main_center_y

    # Main DC path: PV (or PV bus) → COMB → RSD → DC trunk
    if multi_string:
        # PV string fan-in: vertical bus just right of the PV column collects
        # each string's source-circuit conductor, then a single A-tagged run
        # feeds the combiner.
        pv_bus_x = x_pv + pv_per_string_w + 0.25
        msp.add_lwpolyline(
            [(pv_bus_x, pv_y_centers[-1]), (pv_bus_x, pv_y_centers[0])],
            dxfattribs={"layer": "WIRE_DC_POS", "lineweight": STROKE_HEAVY},
        )
        # Tap each string to the bus (no tag — A is reserved for the trunk)
        for yc in pv_y_centers:
            _wire_bus(msp, (x_pv + pv_per_string_w, yc), (pv_bus_x, yc),
                      kind="DC", show_ground=False)
        # Bus → combiner (single A-tagged run; ground accompanies)
        _wire_bus(msp, (pv_bus_x, cy), (x_combiner, cy),
                  kind="DC", tag="A")
    else:
        _wire_bus(msp, (x_pv + pv.w, cy), (x_combiner, cy),
                  kind="DC", tag="A")
    _wire_bus(msp, (x_combiner + combiner.w, cy), (x_rsd, cy),
              kind="DC", tag="B")
    _wire_bus(msp, (x_rsd + rsd.w, cy), (dc_trunk_x, cy),
              kind="DC", show_ground=False)

    # DC trunk (vertical bus); only if multiple inverters
    if n_inv > 1:
        msp.add_lwpolyline(
            [(dc_trunk_x, inv_bot_center), (dc_trunk_x, inv_top_center)],
            dxfattribs={"layer": "WIRE_DC", "lineweight": STROKE_HEAVY},
        )

    # AC trunk (vertical bus); only if multiple inverters
    if n_inv > 1:
        msp.add_lwpolyline(
            [(ac_trunk_x, inv_bot_center), (ac_trunk_x, inv_top_center)],
            dxfattribs={"layer": "WIRE_AC", "lineweight": STROKE_HEAVY},
        )

    # Per-inverter DC tap + AC tap
    # The per-inverter AC OCPD lives at the entry of Sub Panel #2 (or AC trunk
    # in simpler topologies) — show it as an inline breaker between the
    # inverter's right edge and the trunk.
    per_inv_ocpd, _ = _per_inverter_ac_spec(result)
    for k, yc in enumerate(inv_y_centers):
        # DC trunk → INV input
        _wire_bus(msp, (dc_trunk_x, yc), (x_inv, yc),
                  kind="DC", show_ground=False)
        # INV output → AC trunk; tag only the top inverter to avoid clutter
        _wire_bus(msp, (x_inv + inv_w, yc), (ac_trunk_x, yc),
                  kind="AC", show_ground=False,
                  tag="C" if k == 0 else "")
        # Inline 2P-XXA breaker — placed near the inverter side (30% of the
        # tap length) so the C-callout circle at the mid/far end of the wire
        # has clean space and the two glyphs don't visually collide.
        tap_len = ac_trunk_x - (x_inv + inv_w)
        brk_x = (x_inv + inv_w) + 0.30 * tap_len
        _breaker_symbol(msp, brk_x, yc, rating_a=per_inv_ocpd, n_poles=2)

    # AC trunk → AC-DISC
    _wire_bus(msp, (ac_trunk_x, cy), (x_acdisc, cy),
              kind="AC", show_ground=False)

    # Chain: AC-DISC → [sub-panels] → MSP → METER. Tag the first segment "D"
    # (aggregate AC); subsequent segments are continuations of the same bus
    # so they don't carry their own tag.
    main_ocpd = result.ess.ac_disconnect_ocpd_a
    for k in range(len(chain) - 1):
        a_spec, a_x = chain[k]
        b_spec, b_x = chain[k + 1]
        _wire_bus(
            msp,
            (a_x + a_spec.w, cy),
            (b_x, cy),
            kind="AC",
            tag="D" if k == 0 else "",
        )
        # Place a main-feeder breaker on the AC-DISC→Sub#2 segment (or the
        # equivalent first downstream segment when there are no sub-panels):
        # this is the aggregate OCPD that protects the inverter trunk.
        if k == 0:
            brk_x = (a_x + a_spec.w + b_x) / 2
            _breaker_symbol(msp, brk_x, cy, rating_a=main_ocpd, n_poles=2)

    # ESS → BOTTOM inverter battery port. Connecting to the middle inverter
    # makes the wire cross any inverters below it; routing to the bottom one
    # gives a clean straight vertical run.
    bottom_y = inv_y_centers[-1] if inv_y_centers else cy
    ess_top = (x_ess + ess.w / 2, y_ess + ess.h)
    inv_bottom = (x_inv + inv_w / 2, bottom_y - inv_h / 2)
    _wire_bus(msp, ess_top, inv_bottom, kind="DC", show_ground=False)


# --- Top-level entry --------------------------------------------------------

def _configure_text_style(doc: Drawing) -> None:
    """Map the Standard text style to a font every common CAD viewer renders
    cleanly.

    Setting `font = "iso"` (no extension) lets each CAD viewer pick its own
    matching file:
      - LibreCAD → `iso.lff` (bundled, clean ISO 3098 engineering)
      - AutoCAD / DraftSight → `iso.shx` (bundled)
      - FreeCAD → falls back to its system sans-serif

    `iso.shx` with the explicit extension breaks LibreCAD's name lookup
    (its loader matches against bare names only).
    """
    if "Standard" in doc.styles:
        std = doc.styles.get("Standard")
        std.dxf.font = "iso"
        std.dxf.bigfont = ""


def render_dxf(result: CalculationResult, out_path: Path) -> None:
    """Generate a permit-style three-line / single-line DXF for the project."""
    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = 1  # 1 = inches
    _configure_text_style(doc)

    for name, (color, _desc) in LAYERS.items():
        doc.layers.add(name, color=color)

    msp = doc.modelspace()
    _draw_frame(msp)
    _draw_notes(msp, result)
    _draw_schematic(msp, doc, result)
    _draw_conductor_schedule(msp, result)
    _draw_title_block(msp, result)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(out_path))


def render_for_result(result: CalculationResult, out_path: Path) -> int:
    """Convenience wrapper; returns the number of devices placed in the
    schematic: N PV blocks + 6 fixed + N inverters + N sub-panels."""
    render_dxf(result, out_path)
    i = result.inputs
    n_inv = i.inverter.count(i.battery.quantity)
    n_sub = len(i.service.sub_panels)
    n_pv = i.pv_array.strings   # 1 box per source circuit (or 1 aggregate)
    return n_pv + 6 + n_inv + n_sub


def export_preview_png(dxf_path: Path, png_path: Path, dpi: int = 150) -> None:
    """Render a DXF to PNG via ezdxf's matplotlib backend.

    Useful on platforms without a CAD viewer (macOS) for spot-checking the
    output. Imports matplotlib lazily so the core library doesn't pull it in
    unless the user explicitly asks for a preview.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import ezdxf as _ezdxf
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing import config as draw_config
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

    doc = _ezdxf.readfile(str(dxf_path))
    # ACI color 7 reads "black on light background" only when the renderer is
    # told the background is light. Without this, the sheet renders blank.
    cfg = draw_config.Configuration(
        background_policy=draw_config.BackgroundPolicy.WHITE
    )
    fig, ax = plt.subplots(figsize=(SHEET_W, SHEET_H), dpi=dpi)
    ax.set_axis_off()
    Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_layout(
        doc.modelspace(), finalize=True
    )
    png_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(
        str(png_path), dpi=dpi, bbox_inches="tight", pad_inches=0.1,
        facecolor="white",
    )
    plt.close(fig)
