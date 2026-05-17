"""EE-2 sheet: grounding & bonding diagram (NEC 250 + 690.41–50).

Layout mirrors EE-1 (ANSI B 17×11"): notes on top-left, equipment-grounding
schedule top-right, full title block bottom-right, main grounding diagram in
the center. The diagram is intentionally schematic (single-line representation
of the grounding tree) — its job is to communicate intent, not to substitute
for a site survey.
"""
from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment

from ..calc.engine import CalculationResult
from ._textfit import fit_dxf
from .render import (
    LAYERS, MARGIN, NOTES_H, RIGHT_X0, RIGHT_X1,
    SCHEDULE_H, SCHED_Y0, SCHED_Y1,
    SCHEMATIC_X0, SCHEMATIC_X1, SCHEMATIC_Y0, SCHEMATIC_Y1,
    SHEET_H, SHEET_W, TITLE_BLOCK_H, TB_Y0, TB_Y1,
    TEXT_TITLE, TEXT_HEADER, TEXT_BODY, TEXT_CAPTION,
    _configure_text_style, _draw_frame,
)
from .strokes import STROKE_THIN, STROKE_MED, STROKE_HEAVY  # noqa: F401


def _draw_notes(msp, result: CalculationResult) -> None:
    """K.6 (E) polish: NOTES strip uses TEXT_HEADER (slightly larger than
    pre-K.6 TEXT_BODY-ish call) + relaxed line spacing 0.16 → 0.20 so
    the four lines no longer compete with the equipment-stub labels
    underneath. Total strip height grows by ~0.16" which we recover by
    bumping the bus_y a tiny bit lower (handled in _draw_grounding_diagram
    via the existing SCHEMATIC_Y1 - 1.9 offset; total page layout
    unchanged since the bus had spare clearance below)."""
    notes = [
        "GROUNDING & BONDING — NEC 250 + 690.41–50.",
        "ALL EXPOSED NON-CURRENT-CARRYING METAL TO BE BONDED TO THE EQUIPMENT GROUNDING BUS.",
        "GEC TO BE CONTINUOUS COPPER, WITHOUT SPLICE EXCEPT AT IRREVERSIBLE CONNECTIONS (250.64(C)).",
        "DRIVEN GROUND ROD: 8 FT MIN, 5/8\" DIA COPPER-CLAD STEEL (250.52(A)(5), 250.53).",
    ]
    y = SHEET_H - MARGIN - 0.25
    for line in notes:
        msp.add_text(
            line, height=TEXT_HEADER,
            dxfattribs={"layer": "NOTES"},
        ).set_placement((MARGIN + 0.2, y), align=TextEntityAlignment.LEFT)
        y -= 0.20


def _draw_title_block(msp, result: CalculationResult) -> None:
    """EE-2 title block — same shape as EE-1 with the sheet ID swapped."""
    i = result.inputs
    eng = i.design_engineer
    inst = i.installer
    n_inv = i.inverter.count(i.battery.quantity)
    dc_kw = i.pv_array.modules * i.pv_array.module.power_w / 1000.0
    ac_kw = i.inverter.ac_output_v * i.inverter.ac_output_a * n_inv / 1000.0

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
            "SHEET: EE-2  ·  GROUNDING & BONDING",
            f"NEC: {i.project.nec_edition}    PROJECT ID: {i.project.id}",
            f"REV: {i.project.revision}"
                + (f"    DATE: {i.project.initial_design_date}"
                   if i.project.initial_design_date else "")
                + (f"    DRAWN: {i.project.drawn_by}" if i.project.drawn_by else ""),
            f"DC SIZE: {dc_kw:.2f} kW    AC SIZE: {ac_kw:.2f} kW",
        ]),
    ]

    sect_h = TITLE_BLOCK_H / len(sections)
    for idx, (header, body) in enumerate(sections):
        sect_top = TB_Y1 - idx * sect_h
        sect_bot = sect_top - sect_h
        if idx > 0:
            msp.add_line(
                (RIGHT_X0, sect_top), (RIGHT_X1, sect_top),
                dxfattribs={"layer": "TITLE_BLOCK"},
            )
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
                break


def _draw_grounding_schedule(msp, result: CalculationResult) -> None:
    """Tabulate every EGC / GEC size that lives in the diagram."""
    g = result.grounding
    n_inv = result.inputs.inverter.count(result.inputs.battery.quantity)

    # CONDUCTOR labels keep AC GEC / DC GEC for emphasis (those are the
    # main grounding-electrode conductors) and drop the verbose "EGC:"
    # prefix on the equipment-ground rows (the column header already
    # says CONDUCTOR; the clause column distinguishes by NEC reference).
    # SIZE drops "CU" because the top notes strip already declares
    # "GEC TO BE CONTINUOUS COPPER" (NEC 250.64(C)).
    # RUN keeps the short directional arrow but uses MSP/INV/COMB/ESS
    # tags instead of full English to fit the column width.
    rows: list[tuple[str, str, str, str]] = [
        ("AC GEC",
         f"250.66 (from {g.service_conductor_size} AWG SE)",
         f"{g.ac_gec_size} AWG",
         "MSP → GES"),
        ("DC GEC",
         "250.166 / 690.47",
         f"{g.dc_gec_size} AWG",
         "PV equip → GEC"),
        ("PV source",
         "250.122 / 690.45",
         f"{g.egc_pv_source} AWG",
         "Modules → COMB"),
        (f"INV AC (×{n_inv})" if n_inv > 1 else "INV AC",
         "250.122",
         f"{g.egc_inverter_ac} AWG",
         "INV → AC trunk"),
        ("AC trunk",
         "250.122",
         f"{g.egc_aggregate_ac} AWG",
         "AC DISC → MSP"),
        ("ESS",
         "250.122 / 706.7",
         f"{g.egc_ess} AWG",
         "ESS → AC DISC"),
    ]

    hb_h = 0.30
    msp.add_lwpolyline(
        [(RIGHT_X0, SCHED_Y1 - hb_h), (RIGHT_X1, SCHED_Y1 - hb_h)],
        dxfattribs={"layer": "SCHEDULE"},
    )
    msp.add_text(
        "GROUNDING & BONDING SCHEDULE",
        height=TEXT_TITLE,
        dxfattribs={"layer": "SCHEDULE"},
    ).set_placement(
        ((RIGHT_X0 + RIGHT_X1) / 2, SCHED_Y1 - hb_h / 2),
        align=TextEntityAlignment.MIDDLE_CENTER,
    )

    # Column X offsets from RIGHT_X0 (schedule box left edge).
    # Total schedule width = RIGHT_X1 - RIGHT_X0 = TITLE_BLOCK_W (4.5").
    # Re-allocated for the shortened content (see row defs above):
    #   CONDUCTOR ~1.0"  · NEC ~1.3"  · SIZE ~0.55"  · RUN gets the rest (1.4")
    # Column headers render at TEXT_BODY (same as data) — matches the
    # EE-1 conductor schedule for visual consistency.
    cols = [
        ("CONDUCTOR", 0.07),
        ("NEC",       1.10),
        ("SIZE",      2.45),
        ("RUN",       3.05),
    ]
    SCHEDULE_INNER_PAD = 0.07
    col_right_edges = [
        cols[i + 1][1] if i + 1 < len(cols) else (RIGHT_X1 - RIGHT_X0)
        for i in range(len(cols))
    ]

    col_y = SCHED_Y1 - hb_h - 0.20
    for name, x0 in cols:
        msp.add_text(
            name, height=TEXT_BODY,
            dxfattribs={"layer": "SCHEDULE"},
        ).set_placement(
            (RIGHT_X0 + x0, col_y), align=TextEntityAlignment.LEFT,
        )

    msp.add_line(
        (RIGHT_X0, col_y - 0.05),
        (RIGHT_X1, col_y - 0.05),
        dxfattribs={"layer": "SCHEDULE"},
    )

    y = col_y - 0.22
    row_h = TEXT_BODY     # schedule data rows in body tier
    for row in rows:
        for (_, x0), val, right_edge in zip(cols, row, col_right_edges):
            # Available width for this cell, with inner pad on right.
            max_w = right_edge - x0 - SCHEDULE_INNER_PAD
            msp.add_text(
                fit_dxf(val, max_w, row_h), height=row_h,
                dxfattribs={"layer": "SCHEDULE"},
            ).set_placement(
                (RIGHT_X0 + x0, y), align=TextEntityAlignment.LEFT,
            )
        y -= 0.22


def _ground_symbol(msp, x: float, y: float, kind: str, line1: str, line2: str) -> None:
    """Draw an electrode symbol below the (x, y) anchor and tag it on two lines.

    kind:
        "rod"   — ground rod (vertical line + IEEE earth-ground symbol)
        "water" — metal water pipe (horizontal pipe segment)
        "ufer"  — concrete-encased electrode (rebar in slab)
    """
    if kind == "rod":
        msp.add_line((x, y), (x, y - 0.4), dxfattribs={"layer": "WIRE_GROUND"})
        for k, w in enumerate([0.30, 0.20, 0.10]):
            yy = y - 0.40 - 0.07 * k
            msp.add_line((x - w / 2, yy), (x + w / 2, yy),
                         dxfattribs={"layer": "WIRE_GROUND"})
        sym_bot = y - 0.55
    elif kind == "water":
        msp.add_line((x, y), (x, y - 0.3), dxfattribs={"layer": "WIRE_GROUND"})
        msp.add_lwpolyline(
            [(x - 0.20, y - 0.3), (x + 0.20, y - 0.3)],
            dxfattribs={"layer": "WIRE_GROUND", "lineweight": STROKE_HEAVY},
        )
        msp.add_lwpolyline(
            [(x - 0.20, y - 0.4), (x + 0.20, y - 0.4)],
            dxfattribs={"layer": "WIRE_GROUND", "lineweight": STROKE_HEAVY},
        )
        sym_bot = y - 0.45
    elif kind == "ufer":
        msp.add_line((x, y), (x, y - 0.3), dxfattribs={"layer": "WIRE_GROUND"})
        msp.add_lwpolyline(
            [(x - 0.30, y - 0.30), (x + 0.30, y - 0.30),
             (x + 0.30, y - 0.50), (x - 0.30, y - 0.50),
             (x - 0.30, y - 0.30)],
            close=True,
            dxfattribs={"layer": "WIRE_GROUND"},
        )
        msp.add_lwpolyline(
            [(x - 0.25, y - 0.42), (x - 0.10, y - 0.38),
             (x + 0.05, y - 0.42), (x + 0.20, y - 0.38), (x + 0.25, y - 0.42)],
            dxfattribs={"layer": "WIRE_GROUND"},
        )
        sym_bot = y - 0.55
    else:
        sym_bot = y

    # Two-line caption (DXF TEXT entities don't honor \n).
    msp.add_text(
        line1, height=TEXT_BODY, dxfattribs={"layer": "ANNOTATION"},
    ).set_placement((x, sym_bot - 0.10), align=TextEntityAlignment.MIDDLE_CENTER)
    msp.add_text(
        line2, height=TEXT_CAPTION, dxfattribs={"layer": "ANNOTATION"},
    ).set_placement((x, sym_bot - 0.22), align=TextEntityAlignment.MIDDLE_CENTER)


def _draw_grounding_diagram(msp, result: CalculationResult) -> None:
    """Equipment ground bus + GEC + electrode system + per-circuit EGC stubs."""
    g = result.grounding
    n_inv = result.inputs.inverter.count(result.inputs.battery.quantity)

    # --- Equipment ground bus (horizontal bar in upper third of schematic area) ---
    # bus_y was -1.5 originally; lowered to -1.9 so the equipment-label row
    # (drawn 0.85" above the bus) clears the 4-line notes strip at the top.
    bus_y = SCHEMATIC_Y1 - 1.9
    bus_x0 = SCHEMATIC_X0 + 0.5
    bus_x1 = SCHEMATIC_X1 - 0.5
    msp.add_lwpolyline(
        [(bus_x0, bus_y), (bus_x1, bus_y)],
        dxfattribs={"layer": "WIRE_GROUND", "lineweight": STROKE_HEAVY},
    )
    msp.add_text(
        "EQUIPMENT GROUNDING BUS (at MSP)",
        height=TEXT_TITLE, dxfattribs={"layer": "ANNOTATION"},
    ).set_placement((bus_x0, bus_y - 0.20), align=TextEntityAlignment.LEFT)

    # --- Equipment stubs upward into the bus ---
    # Stub height kept short so labels sit below the notes strip.
    bus_w = bus_x1 - bus_x0
    stubs = [
        ("PV ARRAY",                      g.egc_pv_source, "F"),
        ("DC COMBINER",                   g.egc_pv_source, "F"),
        ("RAPID SHUTDOWN",                g.egc_pv_source, "F"),
        ("INVERTER" + (f" × {n_inv}" if n_inv > 1 else ""),
                                          g.egc_inverter_ac, "G"),
        ("ESS UNIT",                      g.egc_ess, "H"),
        ("AC DISCONNECT",                 g.egc_aggregate_ac, "I"),
        ("MSP CHASSIS",                   g.egc_aggregate_ac, "I"),
    ]
    n = len(stubs)
    stub_top = bus_y + 0.7
    label_y = stub_top + 0.15
    for k, (label, size, tag) in enumerate(stubs):
        x = bus_x0 + (k + 0.5) * (bus_w / n)
        # Vertical EGC line
        msp.add_line(
            (x, bus_y), (x, stub_top),
            dxfattribs={"layer": "WIRE_GROUND"},
        )
        # Equipment label
        msp.add_text(
            label, height=TEXT_HEADER,
            dxfattribs={"layer": "EQUIPMENT_TEXT"},
        ).set_placement((x, label_y), align=TextEntityAlignment.MIDDLE_CENTER)
        # EGC size tag near the wire midpoint
        msp.add_text(
            f"#{size} EGC ({tag})", height=TEXT_BODY,
            dxfattribs={"layer": "ANNOTATION"},
        ).set_placement(
            (x + 0.05, (bus_y + stub_top) / 2),
            align=TextEntityAlignment.LEFT,
        )

    # --- GEC: bus → ground electrode system ---
    gec_x = (bus_x0 + bus_x1) / 2
    gec_top = bus_y
    gec_bot = bus_y - 2.5
    msp.add_line(
        (gec_x, gec_top), (gec_x, gec_bot),
        dxfattribs={"layer": "WIRE_GROUND", "lineweight": STROKE_HEAVY},
    )
    # GEC tag — K.5 also surfaces actual vs required when the comparison
    # says UNDERSIZED, so the EE-2 reader sees the upsizing requirement
    # right next to the GEC label.
    ac_gec_text = f"AC GEC: #{g.ac_gec_size} AWG CU  (NEC 250.66)"
    if g.gec_comparison is not None and g.gec_comparison.status == "UNDERSIZED":
        ac_gec_text = (
            f"AC GEC: existing #{g.gec_comparison.actual_size} AWG  "
            f"⚠ UNDERSIZED — NEC 250.66 requires "
            f"#{g.gec_comparison.required_size} AWG CU"
        )
    elif g.gec_comparison is not None and g.gec_comparison.status == "PASS":
        ac_gec_text = (
            f"AC GEC: existing #{g.gec_comparison.actual_size} AWG ✓  "
            f"(NEC 250.66 ≥ #{g.gec_comparison.required_size} AWG)"
        )
    msp.add_text(
        ac_gec_text,
        height=TEXT_BODY, dxfattribs={"layer": "ANNOTATION"},
    ).set_placement(
        (gec_x + 0.10, gec_top - 0.7),
        align=TextEntityAlignment.LEFT,
    )
    msp.add_text(
        f"DC GEC: #{g.dc_gec_size} AWG CU  (NEC 250.166 / 690.47)",
        height=TEXT_BODY, dxfattribs={"layer": "ANNOTATION"},
    ).set_placement(
        (gec_x + 0.10, gec_top - 0.9),
        align=TextEntityAlignment.LEFT,
    )

    # --- Grounding electrode system: render ACTUAL electrodes when the
    # yaml declared them; fall back to the legacy 3-electrode assumed
    # combo so old yaml stays bit-identical. PEX-replaced water pipes
    # are silently skipped here (the schedule still calls them out).
    ges_y = gec_bot
    msp.add_text(
        "GROUNDING ELECTRODE SYSTEM (NEC 250.50)",
        height=TEXT_TITLE, dxfattribs={"layer": "ANNOTATION"},
    ).set_placement((gec_x, ges_y + 0.18), align=TextEntityAlignment.MIDDLE_CENTER)

    electrodes = _resolve_electrodes(result.inputs.service.grounding_electrode_system)
    if not electrodes:
        return   # No qualifying electrodes (e.g. PEX-only water pipe) →
                 # we already showed the schedule warning; nothing to draw.

    # Tie GEC to each electrode via a horizontal "ground bus" run.
    # Spacing adapts: 1 electrode at center, 2 at ±1.5, 3 at ±2.2, more
    # at ±2.2 with reduced inter-electrode gap.
    n = len(electrodes)
    spread = min(2.2, 2.5 - 0.05 * (n - 3) if n > 3 else 2.2 * (n - 1) / max(1, n - 1))
    half_span = 2.2 if n >= 3 else (1.5 if n == 2 else 0.0)
    sys_bus_y = ges_y - 0.15
    msp.add_line(
        (gec_x - half_span - 0.3, sys_bus_y),
        (gec_x + half_span + 0.3, sys_bus_y),
        dxfattribs={"layer": "WIRE_GROUND"},
    )
    msp.add_line(
        (gec_x, ges_y), (gec_x, sys_bus_y),
        dxfattribs={"layer": "WIRE_GROUND"},
    )
    if n == 1:
        positions = [0.0]
    elif n == 2:
        positions = [-1.5, 1.5]
    else:
        # Spread evenly across ±2.2 for 3+ electrodes
        step = 4.4 / (n - 1)
        positions = [-2.2 + i * step for i in range(n)]
    for dx, (kind, line1, line2) in zip(positions, electrodes):
        _ground_symbol(msp, gec_x + dx, sys_bus_y, kind, line1, line2)


def _resolve_electrodes(ges) -> list[tuple[str, str, str]]:
    """K.5 — translate a `GroundingElectrodeSystem` into the
    `(symbol_kind, line1, line2)` triples that `_ground_symbol`
    consumes. Returns the legacy 3-electrode default when the yaml
    didn't declare any electrodes (preserves pre-K.5 EE-2 output)."""
    triples: list[tuple[str, str, str]] = []
    if ges is None or ges.electrode_count == 0 and not (
        ges.rods or ges.metal_water_pipe or ges.ufer
    ):
        # Pure-default GES → keep historic 3-electrode rendering.
        return [
            ("rod",   "GROUND ROD",       "(8 FT MIN, 5/8\" CCS)"),
            ("water", "METAL WATER PIPE", "(10 FT MIN UNDERGRD)"),
            ("ufer",  "UFER ELECTRODE",   "(CONCRETE-ENCASED)"),
        ]
    # Explicit yaml — render only the actual components.
    for i, rod in enumerate(ges.rods, 1):
        line1 = f"GROUND ROD #{i}"
        line2 = f"({rod.length_ft:.0f} FT, {rod.diameter_in:.3g}\" {rod.material.upper().replace('_',' ')})"
        triples.append(("rod", line1, line2))
    if ges.metal_water_pipe and ges.metal_water_pipe.confirmed_metal_underground:
        triples.append((
            "water", "METAL WATER PIPE",
            f"({ges.metal_water_pipe.underground_length_ft:.0f} FT UNDERGRD)",
        ))
    if ges.ufer:
        triples.append((
            "ufer", "UFER ELECTRODE",
            f"({ges.ufer.conductor_size.upper()})",
        ))
    return triples


def render_grounding_dxf(result: CalculationResult, out_path: Path) -> None:
    """Phase C deliverable: an EE-2 sheet showing the grounding & bonding
    network plus all NEC 250 conductor sizes resolved from the calc engine."""
    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = 1
    _configure_text_style(doc)

    for name, (color, _desc) in LAYERS.items():
        doc.layers.add(name, color=color)

    msp = doc.modelspace()
    _draw_frame(msp)
    _draw_notes(msp, result)
    _draw_grounding_diagram(msp, result)
    _draw_grounding_schedule(msp, result)
    _draw_title_block(msp, result)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(out_path))


def render_for_result(result: CalculationResult, out_path: Path) -> int:
    render_grounding_dxf(result, out_path)
    # Count: bus + GEC + 3 electrodes + N equipment stubs
    n_inv = result.inputs.inverter.count(result.inputs.battery.quantity)
    return 1 + 1 + 3 + 7  # bus + GEC + electrodes + 7 equipment stubs
