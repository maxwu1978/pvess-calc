"""Generate CAD roof-review DXF packages."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

import ezdxf
from ezdxf import units
from ezdxf.enums import TextEntityAlignment
from PIL import Image

from ..calc.engine import CalculationResult
from ..permit.ee4_trace import build_ee4_trace_skeleton
from ..schema import EE4Trace, RoofSection
from .cad_layers import (
    ALL_LAYER_SPECS,
    REFERENCE_CANDIDATE,
    REFERENCE_EXCLUSION,
    REFERENCE_FACE_PRIORITY,
    REFERENCE_FRAME,
    REFERENCE_TEXT,
    REFERENCE_UNDERLAY,
    ROOF_FACET,
    ROOF_LINE_KIND_BY_LAYER,
    ROOF_OUTLINE,
    TEXT_ROOF_LABEL,
    configure_layers,
)


Point = tuple[float, float]


def render_roof_review_dxf(
    result: CalculationResult,
    output_path: Path,
    *,
    lookup_roof_sections: Iterable[dict] | None = None,
    candidate_trace: EE4Trace | None = None,
    roof_line_candidates: dict[str, Any] | None = None,
    face_priorities: list[dict[str, Any]] | None = None,
    obstruction_zones: list[dict[str, Any]] | None = None,
    underlay_image_path: Path | None = None,
    underlay_placement: dict[str, Any] | None = None,
    source_note: str = "",
) -> Path:
    """Write an editable DXF template for CAD roof review."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = ezdxf.new("R2018", setup=True)
    doc.units = units.FT
    configure_layers(doc)
    msp = doc.modelspace()

    layout = _reference_layout(underlay_placement)
    _draw_reference_frame(msp, result, source_note=source_note, layout=layout)
    if underlay_image_path is not None and underlay_placement:
        _add_underlay_image(
            doc,
            msp,
            underlay_image_path,
            underlay_placement,
        )
    trace = candidate_trace or _candidate_trace(
        result, lookup_roof_sections=lookup_roof_sections
    )
    if trace and trace.has_geometry:
        _draw_trace_candidate(msp, trace)
    else:
        _draw_blank_instructions(msp)
    if roof_line_candidates:
        _draw_roof_line_candidates(msp, roof_line_candidates, layout=layout)
    if obstruction_zones:
        _draw_obstruction_zones(msp, obstruction_zones)
        _draw_obstruction_board(
            msp,
            obstruction_zones,
            x=layout["board_x"],
            y=layout["board_y"] - 50.0,
        )
    if face_priorities:
        _draw_face_priority_board(
            msp,
            face_priorities,
            x=layout["board_x"],
            y=layout["board_y"] - 28.0,
        )
    doc.saveas(output_path)
    return output_path


def _candidate_trace(
    result: CalculationResult,
    *,
    lookup_roof_sections: Iterable[dict] | None,
) -> EE4Trace | None:
    site = result.inputs.site
    if site.ee4_trace.has_geometry:
        return site.ee4_trace
    if lookup_roof_sections:
        sections = []
        for raw in lookup_roof_sections:
            try:
                sections.append(RoofSection(**raw))
            except Exception:
                continue
        if sections:
            copied = result.inputs.model_copy(deep=True)
            copied.site.roof_sections = sections
            return build_ee4_trace_skeleton(replace(result, inputs=copied))
    if site.roof_sections:
        return build_ee4_trace_skeleton(result)
    return None


def _draw_trace_candidate(msp, trace: EE4Trace) -> None:
    if trace.roof_outline is not None:
        _add_closed_polyline(
            msp,
            trace.roof_outline.vertices,
            layer=REFERENCE_CANDIDATE,
        )
    for facet in trace.roof_facets:
        _add_closed_polyline(msp, facet.vertices, layer=REFERENCE_CANDIDATE)
    for line in trace.roof_lines:
        layer = _layer_for_trace_kind(line.kind)
        if layer:
            msp.add_lwpolyline(
                line.points, dxfattribs={"layer": REFERENCE_CANDIDATE}
            )
    msp.add_text(
        "Review/edit these layers in CAD before running pvess roof-import.",
        dxfattribs={"layer": REFERENCE_TEXT, "height": 1.2},
        ).set_placement((0, -8), align=TextEntityAlignment.LEFT)


def _reference_layout(placement: dict[str, Any] | None) -> dict[str, float]:
    if placement:
        insert = placement.get("insert_ft") or []
        size = placement.get("size_ft") or []
        if len(insert) == 2 and len(size) == 2:
            try:
                x = float(insert[0])
                y = float(insert[1])
                w = float(size[0])
                h = float(size[1])
                if w > 0 and h > 0:
                    return {
                        "title_x": x,
                        "title_y": y + h + 10.0,
                        "board_x": x + w + 6.0,
                        "board_y": y + h + 6.0,
                        "below_y": y - 8.0,
                        "scale_x": x,
                        "scale_y": y - 5.0,
                    }
            except (TypeError, ValueError):
                pass
    return {
        "title_x": 0.0,
        "title_y": 68.0,
        "board_x": 72.0,
        "board_y": 58.0,
        "below_y": -8.0,
        "scale_x": 0.0,
        "scale_y": -3.0,
    }


def _add_underlay_image(
    doc,
    msp,
    image_path: Path,
    placement: dict[str, Any],
) -> None:
    try:
        insert = placement.get("insert_ft") or []
        size = placement.get("size_ft") or []
        if len(insert) != 2 or len(size) != 2:
            return
        with Image.open(image_path) as img:
            image_size = img.size
        if image_size[0] <= 0 or image_size[1] <= 0:
            return
        image_def = doc.add_image_def(str(image_path.resolve()), image_size)
        msp.add_image(
            image_def,
            insert=(float(insert[0]), float(insert[1])),
            size_in_units=(float(size[0]), float(size[1])),
            dxfattribs={"layer": REFERENCE_UNDERLAY},
        )
        x, y = float(insert[0]), float(insert[1])
        w, h = float(size[0]), float(size[1])
        msp.add_lwpolyline(
            [(x, y), (x + w, y), (x + w, y + h), (x, y + h)],
            close=True,
            dxfattribs={"layer": REFERENCE_FRAME},
        )
        msp.add_text(
            "SATELLITE UNDERLAY - verify alignment before tracing",
            dxfattribs={"layer": REFERENCE_TEXT, "height": 0.8},
        ).set_placement((x, y + h + 1.0), align=TextEntityAlignment.LEFT)
    except Exception:
        return


def _draw_roof_line_candidates(
    msp,
    payload: dict[str, Any],
    *,
    layout: dict[str, float],
) -> None:
    lines = payload.get("lines") or []
    if not lines:
        return
    for item in lines:
        points = item.get("points") or []
        if len(points) != 2:
            continue
        try:
            a = (float(points[0][0]), float(points[0][1]))
            b = (float(points[1][0]), float(points[1][1]))
        except (TypeError, ValueError, IndexError):
            continue
        msp.add_lwpolyline([a, b], dxfattribs={"layer": REFERENCE_CANDIDATE})
    x = layout["board_x"]
    y = layout["board_y"] - 16.0
    msp.add_text(
        "ROOF LINE CANDIDATES",
        dxfattribs={"layer": REFERENCE_TEXT, "height": 0.85},
    ).set_placement((x, y), align=TextEntityAlignment.LEFT)
    msp.add_text(
        f"{len(lines)} line(s); redraw accepted geometry on ROOF_* layers",
        dxfattribs={"layer": REFERENCE_TEXT, "height": 0.62},
    ).set_placement((x, y - 1.4), align=TextEntityAlignment.LEFT)
    for idx, item in enumerate(lines[:10], start=1):
        label = (
            f"{idx}. {item.get('kind', 'line')} "
            f"{item.get('source', '-')}"
        )
        msp.add_text(
            label[:44],
            dxfattribs={"layer": REFERENCE_TEXT, "height": 0.56},
        ).set_placement((x, y - 2.8 - idx * 1.05),
                        align=TextEntityAlignment.LEFT)


def _draw_reference_frame(
    msp,
    result: CalculationResult,
    *,
    source_note: str,
    layout: dict[str, float],
) -> None:
    project = result.inputs.project
    title = f"PVESS ROOF CAD REVIEW - {project.name or project.id}"
    subtitle = project.site_address or project.location or "address not set"
    title_x = layout["title_x"]
    title_y = layout["title_y"]
    msp.add_text(
        title,
        dxfattribs={"layer": REFERENCE_TEXT, "height": 2.0},
    ).set_placement((title_x, title_y), align=TextEntityAlignment.LEFT)
    msp.add_text(
        subtitle,
        dxfattribs={"layer": REFERENCE_TEXT, "height": 1.1},
    ).set_placement((title_x, title_y - 3.0), align=TextEntityAlignment.LEFT)
    if source_note:
        msp.add_text(
            source_note[:180],
            dxfattribs={"layer": REFERENCE_TEXT, "height": 0.9},
        ).set_placement((title_x, title_y - 5.5), align=TextEntityAlignment.LEFT)

    # 10 ft scale bar.
    sx = layout["scale_x"]
    sy = layout["scale_y"]
    msp.add_line((sx, sy), (sx + 10, sy), dxfattribs={"layer": REFERENCE_FRAME})
    for x in (sx, sx + 10):
        msp.add_line((x, sy - 0.6), (x, sy + 0.6),
                     dxfattribs={"layer": REFERENCE_FRAME})
    msp.add_text(
        "10 ft",
        dxfattribs={"layer": REFERENCE_TEXT, "height": 0.8},
    ).set_placement((sx + 5, sy - 1.8), align=TextEntityAlignment.MIDDLE_CENTER)

    # North arrow.
    nx = layout["board_x"]
    ny = layout["board_y"] - 2.0
    msp.add_line((nx, ny - 8), (nx, ny), dxfattribs={"layer": REFERENCE_FRAME})
    msp.add_lwpolyline(
        [(nx, ny), (nx - 1.2, ny - 2.5), (nx + 1.2, ny - 2.5), (nx, ny)],
        dxfattribs={"layer": REFERENCE_FRAME},
        close=True,
    )
    msp.add_text(
        "N",
        dxfattribs={"layer": REFERENCE_TEXT, "height": 1.2},
    ).set_placement((nx, ny + 2.0), align=TextEntityAlignment.MIDDLE_CENTER)
    _draw_layer_legend(msp, x=layout["board_x"] + 5.0, y=layout["board_y"])


def _draw_layer_legend(msp, *, x: float, y: float) -> None:
    msp.add_text(
        "CAD LAYER STANDARD",
        dxfattribs={"layer": REFERENCE_TEXT, "height": 1.0},
    ).set_placement((x, y), align=TextEntityAlignment.LEFT)
    row_y = y - 2.0
    for spec in ALL_LAYER_SPECS:
        if not spec.name.startswith(("ROOF_", "FIRE_", "PV_", "TEXT_")):
            continue
        label = spec.name + ("  REQUIRED" if spec.required_for_import else "")
        msp.add_text(
            label,
            dxfattribs={"layer": REFERENCE_TEXT, "height": 0.65},
        ).set_placement((x, row_y), align=TextEntityAlignment.LEFT)
        row_y -= 1.2


def _draw_blank_instructions(msp) -> None:
    x0, y0, x1, y1 = 0.0, 0.0, 50.0, 35.0
    msp.add_lwpolyline(
        [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)],
        dxfattribs={"layer": REFERENCE_CANDIDATE},
    )
    notes = [
        "No roof geometry candidate was available.",
        "Use an aerial/field reference and draw:",
        "1. one closed ROOF_OUTLINE polyline",
        "2. one or more closed ROOF_FACET polylines",
        "3. ridge/hip/valley linework on matching ROOF_* layers",
        "Optional facet label syntax: NAME=South PITCH=22 AZ=180",
    ]
    for idx, text in enumerate(notes):
        msp.add_text(
            text,
            dxfattribs={"layer": REFERENCE_TEXT, "height": 0.95},
        ).set_placement((2, 32 - idx * 2), align=TextEntityAlignment.LEFT)


def _draw_lookup_section_board(
    msp,
    lookup_roof_sections: Iterable[dict],
    *,
    x: float,
    y: float,
) -> None:
    sections = list(lookup_roof_sections or [])
    if not sections:
        return
    msp.add_text(
        "GOOGLE SOLAR FACE SUMMARY (schematic, not traced geometry)",
        dxfattribs={"layer": REFERENCE_TEXT, "height": 1.0},
    ).set_placement((x, y), align=TextEntityAlignment.LEFT)
    row_y = y - 2.0
    for idx, raw in enumerate(sections[:18], start=1):
        name = str(raw.get("name") or f"Face {idx}")
        pitch = raw.get("pitch_deg", "-")
        az = raw.get("azimuth_deg", "-")
        width = float(raw.get("width_ft") or 6.0)
        height = float(raw.get("height_ft") or width)
        box_w = max(2.5, min(width / 3.0, 8.0))
        box_h = max(1.2, min(height / 3.0, 5.0))
        col = (idx - 1) % 3
        row = (idx - 1) // 3
        bx = x + col * 34.0
        by = row_y - row * 7.0
        msp.add_lwpolyline(
            [(bx, by), (bx + box_w, by), (bx + box_w, by + box_h),
             (bx, by + box_h)],
            close=True,
            dxfattribs={"layer": REFERENCE_CANDIDATE},
        )
        label = f"{idx}. {name}  P={pitch}  AZ={az}"
        msp.add_text(
            label[:52],
            dxfattribs={"layer": REFERENCE_TEXT, "height": 0.65},
        ).set_placement((bx + box_w + 0.8, by + box_h * 0.5),
                        align=TextEntityAlignment.MIDDLE_LEFT)


def _draw_face_priority_board(
    msp,
    face_priorities: list[dict[str, Any]],
    *,
    x: float,
    y: float,
) -> None:
    if not face_priorities:
        return
    msp.add_text(
        "PV FACE PRIORITY (review)",
        dxfattribs={"layer": REFERENCE_TEXT, "height": 0.9},
    ).set_placement((x, y), align=TextEntityAlignment.LEFT)
    msp.add_text(
        "Prefer SW first; east second; avoid north.",
        dxfattribs={"layer": REFERENCE_TEXT, "height": 0.58},
    ).set_placement((x, y - 1.4), align=TextEntityAlignment.LEFT)
    row_y = y - 3.0
    for item in face_priorities[:16]:
        priority = item.get("priority") or {}
        color = int(priority.get("dxf_color") or 8)
        box = [(x, row_y - 0.25), (x + 1.6, row_y - 0.25),
               (x + 1.6, row_y + 0.75), (x, row_y + 0.75)]
        msp.add_lwpolyline(
            box,
            close=True,
            dxfattribs={"layer": REFERENCE_FACE_PRIORITY, "color": color},
        )
        label = (
            f"{item.get('index', '-')}. {item.get('name', 'Face')} "
            f"AZ={item.get('azimuth_deg', '-')} "
            f"{priority.get('label', '-')}"
        )
        msp.add_text(
            label[:58],
            dxfattribs={"layer": REFERENCE_TEXT, "height": 0.54},
        ).set_placement((x + 2.2, row_y + 0.25),
                        align=TextEntityAlignment.MIDDLE_LEFT)
        row_y -= 1.15


def _draw_obstruction_zones(
    msp,
    obstruction_zones: list[dict[str, Any]],
) -> None:
    for zone in obstruction_zones:
        try:
            x = float(zone.get("x_ft"))
            y = float(zone.get("y_ft"))
            radius = max(float(zone.get("radius_ft") or 0.0), 0.5)
        except (TypeError, ValueError):
            continue
        msp.add_circle(
            (x, y),
            radius,
            dxfattribs={"layer": REFERENCE_EXCLUSION, "color": 1},
        )
        msp.add_line(
            (x - radius, y - radius),
            (x + radius, y + radius),
            dxfattribs={"layer": REFERENCE_EXCLUSION, "color": 1},
        )
        msp.add_line(
            (x - radius, y + radius),
            (x + radius, y - radius),
            dxfattribs={"layer": REFERENCE_EXCLUSION, "color": 1},
        )


def _draw_obstruction_board(
    msp,
    obstruction_zones: list[dict[str, Any]],
    *,
    x: float,
    y: float,
) -> None:
    msp.add_text(
        "NO-PANEL ZONES",
        dxfattribs={"layer": REFERENCE_TEXT, "height": 0.85},
    ).set_placement((x, y), align=TextEntityAlignment.LEFT)
    msp.add_text(
        "Verify and redraw accepted objects on ROOF_OBSTRUCTION.",
        dxfattribs={"layer": REFERENCE_TEXT, "height": 0.58},
    ).set_placement((x, y - 1.4), align=TextEntityAlignment.LEFT)
    row_y = y - 3.0
    for idx, zone in enumerate(obstruction_zones[:12], start=1):
        try:
            zx = f"{float(zone.get('x_ft')):.1f}"
            zy = f"{float(zone.get('y_ft')):.1f}"
        except (TypeError, ValueError):
            zx, zy = "-", "-"
        msp.add_text(
            (
                f"{idx}. {zone.get('kind', 'obstruction')} "
                f"R={zone.get('radius_ft', '-')}ft "
                f"({zx},{zy})"
            )[:58],
            dxfattribs={"layer": REFERENCE_TEXT, "height": 0.54},
        ).set_placement((x, row_y), align=TextEntityAlignment.LEFT)
        row_y -= 1.05


def _add_closed_polyline(msp, vertices: Iterable[Point], *, layer: str) -> None:
    pts = list(vertices)
    if len(pts) < 3:
        return
    msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})


def _layer_for_trace_kind(kind: str) -> str | None:
    for layer, mapped in ROOF_LINE_KIND_BY_LAYER.items():
        if mapped == kind:
            return layer
    return None
