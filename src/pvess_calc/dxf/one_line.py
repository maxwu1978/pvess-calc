"""DXF renderer for EE-2.1 one-line diagram."""
from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment
from ezdxf.layouts import Modelspace

from ..calc.engine import CalculationResult
from ..electrical.topology import (
    ConductorScheduleRow,
    ElectricalNode,
    build_electrical_topology,
)
from . import symbols as sym
from ._textfit import fit_dxf
from .render import (
    LAYERS,
    MARGIN,
    RIGHT_X0,
    RIGHT_X1,
    SCHED_Y1,
    SHEET_H,
    DeviceSpec,
    _add_device,
    _auto_breakers_msp,
    _bottom_mid,
    _configure_text_style,
    _draw_frame,
    _draw_internal_breakers,
    _draw_title_block,
    _left_mid,
    _right_mid,
    _top_mid,
)
from .strokes import STROKE_HEAVY, STROKE_MED
from .typography import TEXT_BODY, TEXT_CAPTION, TEXT_HEADER, TEXT_TITLE


MAIN_X0 = MARGIN + 0.25
MAIN_X1 = RIGHT_X0 - 0.25


def _spec_for(node: ElectricalNode) -> DeviceSpec:
    sizes = {
        "pv_array": (1.05, 0.70),
        "mlpe_rsd": (0.85, 0.55),
        "dc_ocpd": (1.05, 0.70),
        "inverter": (1.65, 0.95),
        "ac_disconnect": (0.90, 0.85),
        "interconnection": (0.95, 0.72),
        "service_panel": (1.05, 1.45),
        "meter": (0.60, 0.60),
        "utility": (0.95, 0.76),
        "ess": (1.20, 0.70),
    }
    w, h = sizes.get(node.kind, (0.95, 0.65))
    return DeviceSpec(
        tag=node.tag,
        label=node.icon,
        desc1="",
        desc2="",
        w=w,
        h=h,
    )


def _add_header(msp: Modelspace, x: float, y: float, spec: DeviceSpec,
                title: str, subtitle: str = "") -> None:
    msp.add_text(
        fit_dxf(title, spec.w + 0.35, TEXT_BODY),
        height=TEXT_BODY,
        dxfattribs={"layer": "EQUIPMENT_TEXT"},
    ).set_placement(
        (x + spec.w / 2, y + spec.h + 0.18),
        align=TextEntityAlignment.MIDDLE_CENTER,
    )
    if subtitle:
        msp.add_text(
            fit_dxf(subtitle, spec.w + 0.45, TEXT_CAPTION),
            height=TEXT_CAPTION,
            dxfattribs={"layer": "EQUIPMENT_TEXT"},
        ).set_placement(
            (x + spec.w / 2, y + spec.h + 0.06),
            align=TextEntityAlignment.MIDDLE_CENTER,
        )


def _add_footer(msp: Modelspace, x: float, y: float, spec: DeviceSpec,
                title: str, subtitle: str = "") -> None:
    """Place a compact device label below the box.

    Used for ESS because its branch conductor exits upward; top labels would
    sit directly in that wire corridor.
    """
    msp.add_text(
        fit_dxf(title, spec.w + 0.35, TEXT_BODY),
        height=TEXT_BODY,
        dxfattribs={"layer": "EQUIPMENT_TEXT"},
    ).set_placement(
        (x + spec.w / 2, y - 0.13),
        align=TextEntityAlignment.MIDDLE_CENTER,
    )
    if subtitle:
        msp.add_text(
            fit_dxf(subtitle, spec.w + 0.45, TEXT_CAPTION),
            height=TEXT_CAPTION,
            dxfattribs={"layer": "EQUIPMENT_TEXT"},
        ).set_placement(
            (x + spec.w / 2, y - 0.25),
            align=TextEntityAlignment.MIDDLE_CENTER,
        )


def _node_specs(nodes: tuple[ElectricalNode, ...]) -> dict[str, DeviceSpec]:
    return {node.id: _spec_for(node) for node in nodes}


def _node_map(nodes: tuple[ElectricalNode, ...]) -> dict[str, ElectricalNode]:
    return {node.id: node for node in nodes}


def _draw_top_notes(msp: Modelspace, result: CalculationResult) -> None:
    i = result.inputs
    topo = build_electrical_topology(result)
    rows = [
        ("SHEET:", "EE-2.1 - ONE LINE DIAGRAM"),
        ("SYSTEM:", f"DC {topo.system_dc_kw:.2f} kW    AC {topo.system_ac_kw:.2f} kW"),
        ("PV ARRAY:", f"({i.pv_array.modules}) {i.pv_array.module.brand} {i.pv_array.module.model}"),
        ("INVERTER:", f"({i.inverter.count(i.battery.quantity)}) {i.inverter.brand} {i.inverter.model}"),
        ("INTERCONNECT:", f"{topo.interconnection_method} PER NEC 705.11"),
    ]
    y = SHEET_H - MARGIN - 0.20
    for label, value in rows:
        msp.add_text(label, height=TEXT_HEADER, dxfattribs={"layer": "NOTES"}).set_placement(
            (MAIN_X0, y), align=TextEntityAlignment.LEFT
        )
        msp.add_text(value, height=TEXT_HEADER, dxfattribs={"layer": "NOTES"}).set_placement(
            (MAIN_X0 + 1.15, y), align=TextEntityAlignment.LEFT
        )
        y -= 0.16


def _draw_conductor_schedule(
    msp: Modelspace,
    rows: tuple[ConductorScheduleRow, ...],
) -> None:
    def raceway_label(row: ConductorScheduleRow) -> str:
        if row.fill_pct is None:
            return row.conduit
        return f"{row.conduit} {row.fill_pct:.0f}%"

    hb_h = 0.30
    msp.add_lwpolyline(
        [(RIGHT_X0, SCHED_Y1 - hb_h), (RIGHT_X1, SCHED_Y1 - hb_h)],
        dxfattribs={"layer": "SCHEDULE"},
    )
    msp.add_text(
        "CONDUCTOR / OCPD SCHEDULE",
        height=TEXT_TITLE,
        dxfattribs={"layer": "SCHEDULE"},
    ).set_placement(
        ((RIGHT_X0 + RIGHT_X1) / 2, SCHED_Y1 - hb_h / 2),
        align=TextEntityAlignment.MIDDLE_CENTER,
    )

    cols = [
        ("TAG", 0.07, 0.24),
        ("CIRCUIT", 0.36, 0.78),
        ("WIRES", 1.14, 0.36),
        ("SIZE", 1.52, 0.44),
        ("TYPE", 2.00, 0.58),
        ("GND", 2.62, 0.42),
        ("RACEWAY", 3.10, 0.64),
        ("OCPD", 3.84, 0.42),
    ]
    y = SCHED_Y1 - hb_h - 0.20
    for title, x0, _w in cols:
        msp.add_text(title, height=TEXT_BODY, dxfattribs={"layer": "SCHEDULE"}).set_placement(
            (RIGHT_X0 + x0, y), align=TextEntityAlignment.LEFT
        )
    msp.add_line((RIGHT_X0, y - 0.05), (RIGHT_X1, y - 0.05), dxfattribs={"layer": "SCHEDULE"})

    y -= 0.20
    for row in rows:
        values = [
            row.tag,
            row.circuit,
            row.wires,
            row.size,
            row.conductor_type,
            row.ground,
            raceway_label(row),
            f"{row.ocpd_a}A",
        ]
        for (title, x0, width), value in zip(cols, values):
            del title
            msp.add_text(
                fit_dxf(value, width, TEXT_BODY),
                height=TEXT_BODY,
                dxfattribs={"layer": "SCHEDULE"},
            ).set_placement((RIGHT_X0 + x0, y), align=TextEntityAlignment.LEFT)
        y -= 0.18


def _draw_summary(msp: Modelspace, result: CalculationResult) -> None:
    x0 = MAIN_X0
    y0 = MARGIN + 0.55
    w = MAIN_X1 - MAIN_X0
    h = 1.00
    msp.add_lwpolyline(
        [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h), (x0, y0)],
        close=True,
        dxfattribs={"layer": "NOTES", "lineweight": STROKE_MED},
    )
    msp.add_text("LINE-SIDE TAP NOTES", height=TEXT_HEADER, dxfattribs={"layer": "NOTES"}).set_placement(
        (x0 + 0.10, y0 + h - 0.18), align=TextEntityAlignment.LEFT
    )
    notes = [
        "1. Supply-side connection shall be made ahead of the main service disconnect per NEC 705.11.",
        "2. Field verify utility meter/service conductor tap point before installation.",
        f"3. AIC available {result.aic.available_fault_current_ka:.2f} kA; equipment rating per schedule and listing.",
        f"4. GEC #{result.grounding.ac_gec_size} AWG CU to existing grounding electrode system.",
    ]
    y = y0 + h - 0.36
    for note in notes:
        msp.add_text(
            fit_dxf(note, w - 0.20, TEXT_BODY),
            height=TEXT_BODY,
            dxfattribs={"layer": "NOTES"},
        ).set_placement((x0 + 0.10, y), align=TextEntityAlignment.LEFT)
        y -= 0.16


def _draw_ground(msp: Modelspace, x: float, y: float, text: str) -> None:
    msp.add_line((x, y + 0.35), (x, y + 0.16), dxfattribs={"layer": "WIRE_GROUND"})
    msp.add_line((x - 0.16, y + 0.16), (x + 0.16, y + 0.16), dxfattribs={"layer": "WIRE_GROUND"})
    msp.add_line((x - 0.11, y + 0.08), (x + 0.11, y + 0.08), dxfattribs={"layer": "WIRE_GROUND"})
    msp.add_line((x - 0.06, y), (x + 0.06, y), dxfattribs={"layer": "WIRE_GROUND"})
    msp.add_text(text, height=TEXT_BODY, dxfattribs={"layer": "ANNOTATION"}).set_placement(
        (x + 0.22, y + 0.04), align=TextEntityAlignment.LEFT
    )


def _single_wire(
    msp: Modelspace,
    src: tuple[float, float],
    dst: tuple[float, float],
    *,
    tag: str = "",
) -> None:
    """Draw one graphic line for a one-line diagram conductor path.

    The conductor count and phase information belongs in the schedule; the
    one-line sheet itself must not draw parallel L1/L2/N or +/- conductors.
    """
    msp.add_lwpolyline(
        [src, dst],
        dxfattribs={"layer": "WIRE_ONE_LINE", "lineweight": STROKE_HEAVY},
    )
    if not tag:
        return
    mx, my = (src[0] + dst[0]) / 2, (src[1] + dst[1]) / 2
    horizontal = abs(dst[0] - src[0]) >= abs(dst[1] - src[1])
    callout = (mx, my + 0.18) if horizontal else (mx + 0.18, my)
    sym.draw_callout_circle(msp, callout[0], callout[1], tag)


def _draw_one_line(msp: Modelspace, doc, result: CalculationResult) -> None:
    topo = build_electrical_topology(result)
    nodes = _node_map(topo.nodes)
    specs = _node_specs(topo.nodes)

    y_pv = 4.55
    y_service = 7.25
    positions = {
        "pv": (0.95, y_pv),
        "mlpe": (2.35, y_pv + 0.07),
        "dc_ocpd": (3.62, y_pv),
        "inverter": (5.15, y_pv - 0.12),
        "ac_disc": (7.18, y_pv - 0.02),
        "tap": (8.72, y_service - 0.38),
        "msp": (6.28, y_service - 0.55),
        "meter": (9.92, y_service - 0.20),
        "utility": (10.92, y_service - 0.28),
    }
    if "ess" in specs:
        positions["ess"] = (5.38, y_pv - 1.55)

    for node_id, (x, y) in positions.items():
        spec = specs[node_id]
        _add_device(msp, doc, x, y, spec)
        node = nodes[node_id]
        if node_id in {"msp"}:
            _draw_internal_breakers(
                msp,
                x,
                y,
                spec.w,
                spec.h,
                _auto_breakers_msp(
                    result.inputs.service,
                    total_backfeed_a=result.interconnect.total_backfeed_a,
                    pv_ocpd_for_backfeed=result.ess.ac_disconnect_ocpd_a,
                ),
            )
        subtitle = node.desc2 if node_id in {"pv", "inverter", "msp", "meter"} else node.desc1
        if node_id == "ess":
            _add_footer(msp, x, y, spec, node.label, subtitle)
        else:
            _add_header(msp, x, y, spec, node.label, subtitle)

    # PV/DC path.
    _single_wire(
        msp,
        _right_mid(*positions["pv"], specs["pv"]),
        _left_mid(*positions["mlpe"], specs["mlpe"]),
    )
    _single_wire(
        msp,
        _right_mid(*positions["mlpe"], specs["mlpe"]),
        _left_mid(*positions["dc_ocpd"], specs["dc_ocpd"]),
        tag="A",
    )
    _single_wire(
        msp,
        _right_mid(*positions["dc_ocpd"], specs["dc_ocpd"]),
        _left_mid(*positions["inverter"], specs["inverter"]),
        tag="B",
    )

    # Inverter AC to AC disconnect.
    c_tag = next(row.tag for row in topo.schedule if row.circuit == "INVERTER AC")
    _single_wire(
        msp,
        _right_mid(*positions["inverter"], specs["inverter"]),
        _left_mid(*positions["ac_disc"], specs["ac_disc"]),
        tag=c_tag,
    )

    # AC disconnect to line-side tap, routed orthogonally.
    ac_right = _right_mid(*positions["ac_disc"], specs["ac_disc"])
    tap_bottom = _bottom_mid(*positions["tap"], specs["tap"])
    riser = (tap_bottom[0], ac_right[1])
    _single_wire(msp, ac_right, riser, tag="D")
    _single_wire(msp, riser, tap_bottom)

    # Service path: utility -> meter -> line-side tap -> MSP.
    _single_wire(
        msp,
        _left_mid(*positions["utility"], specs["utility"]),
        _right_mid(*positions["meter"], specs["meter"]),
    )
    _single_wire(
        msp,
        _left_mid(*positions["meter"], specs["meter"]),
        _right_mid(*positions["tap"], specs["tap"]),
    )
    _single_wire(
        msp,
        _left_mid(*positions["tap"], specs["tap"]),
        _right_mid(*positions["msp"], specs["msp"]),
    )

    # Optional ESS branch.
    if "ess" in specs:
        ess_right = _right_mid(*positions["ess"], specs["ess"])
        inv_bottom = _bottom_mid(*positions["inverter"], specs["inverter"])
        ess_elbow = (inv_bottom[0], ess_right[1])
        _single_wire(msp, ess_right, ess_elbow)
        _single_wire(msp, ess_elbow, inv_bottom)

    msp_pos = positions["msp"]
    _draw_ground(
        msp,
        msp_pos[0] + specs["msp"].w / 2,
        msp_pos[1] - 0.62,
        f"GEC #{result.grounding.ac_gec_size} AWG CU TO GES",
    )

    msp.add_text(
        "SUPPLY-SIDE CONNECTION AHEAD OF MAIN SERVICE DISCONNECT",
        height=TEXT_BODY,
        dxfattribs={"layer": "ANNOTATION"},
    ).set_placement((7.15, y_service + 0.88), align=TextEntityAlignment.LEFT)


def render_one_line_dxf(result: CalculationResult, out_path: Path) -> None:
    """Generate EE-2.1 as a CAD/DXF one-line diagram."""
    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = 1
    _configure_text_style(doc)
    for name, (color, _desc) in LAYERS.items():
        doc.layers.add(name, color=color)
    doc.layers.add("WIRE_ONE_LINE", color=7)

    msp = doc.modelspace()
    _draw_frame(msp)
    _draw_top_notes(msp, result)
    topo = build_electrical_topology(result)
    _draw_one_line(msp, doc, result)
    _draw_conductor_schedule(msp, topo.schedule)
    _draw_summary(msp, result)

    sentinel = object()
    old_code = getattr(result, "_active_sheet_display_code", sentinel)
    old_title = getattr(result, "_active_sheet_title", sentinel)
    result._active_sheet_display_code = "EE-2.1"
    result._active_sheet_title = "One Line Diagram"
    try:
        _draw_title_block(msp, result)
    finally:
        if old_code is sentinel:
            delattr(result, "_active_sheet_display_code")
        else:
            result._active_sheet_display_code = old_code
        if old_title is sentinel:
            delattr(result, "_active_sheet_title")
        else:
            result._active_sheet_title = old_title

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(out_path))
