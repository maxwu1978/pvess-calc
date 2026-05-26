"""Convert CAD-reviewed roof DXF geometry into PVESS YAML snippets."""
from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
import math
from pathlib import Path
import re
from typing import Any, Iterable

import ezdxf
import yaml
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import Polygon

from ..calc.polygon import polygon_area
from ..schema import (
    EE4Trace,
    EE4TraceLine,
    EE4TracePolygon,
    EE4TraceSymbol,
    RoofObstruction,
    RoofSection,
    Site,
    Inputs,
)
from .cad_layers import (
    FIRE_SETBACK,
    REQUIRED_IMPORT_LAYERS,
    ROOF_FACET,
    ROOF_LINE_KIND_BY_LAYER,
    ROOF_OBSTRUCTION,
    ROOF_OUTLINE,
    TEXT_ROOF_LABEL,
    PV_MODULE_ZONE,
)
from .qa import RoofReviewImportError, RoofReviewQA


Point = tuple[float, float]


@dataclass(frozen=True)
class Label:
    text: str
    point: Point


@dataclass
class ImportedRoof:
    qa: RoofReviewQA
    yaml_payload: dict[str, Any]
    site: Site

    @property
    def status(self) -> str:
        return self.qa.status

    def yaml_text(self) -> str:
        return yaml.safe_dump(
            self.yaml_payload,
            sort_keys=False,
            allow_unicode=False,
        )


def import_reviewed_dxf(
    dxf_path: Path,
    *,
    default_pitch_deg: float = 22.0,
    default_azimuth_deg: float = 180.0,
    containment_tolerance_ft: float = 0.5,
    strict: bool = True,
) -> ImportedRoof:
    """Read a reviewed CAD DXF and return a paste-ready `site` YAML block."""
    qa = RoofReviewQA()
    dxf_path = Path(dxf_path)
    if not dxf_path.exists():
        qa.add("FAIL", f"DXF not found: {dxf_path}")
        raise RoofReviewImportError(f"DXF not found: {dxf_path}", qa=qa)

    try:
        doc = ezdxf.readfile(str(dxf_path))
    except Exception as exc:  # pragma: no cover - ezdxf error variety
        qa.add("FAIL", f"Could not read DXF: {exc}")
        raise RoofReviewImportError(f"Could not read DXF: {exc}", qa=qa) from exc

    msp = doc.modelspace()
    layer_names = {entity.dxf.layer for entity in msp}
    for layer in sorted(REQUIRED_IMPORT_LAYERS):
        if layer not in layer_names:
            qa.add("FAIL", f"Required layer {layer} is missing.", layer=layer)

    outline_polys = _closed_polygons(msp, ROOF_OUTLINE, qa)
    facet_polys = _closed_polygons(msp, ROOF_FACET, qa)
    obstruction_polys = _closed_polygons(msp, ROOF_OBSTRUCTION, qa, required=False)
    fire_polys = _closed_polygons(msp, FIRE_SETBACK, qa, required=False)
    pv_zone_polys = _closed_polygons(msp, PV_MODULE_ZONE, qa, required=False)
    labels = _labels(msp)

    if not outline_polys:
        qa.add(
            "FAIL",
            "Draw one closed polyline on ROOF_OUTLINE before import.",
            layer=ROOF_OUTLINE,
        )
    if not facet_polys:
        qa.add(
            "FAIL",
            "Draw at least one closed polyline on ROOF_FACET before import.",
            layer=ROOF_FACET,
        )

    if qa.failures:
        if strict:
            qa.raise_if_failed()
        raise RoofReviewImportError("Reviewed DXF failed roof QA.", qa=qa)

    outline = _largest_polygon(outline_polys)
    outline_shape = Polygon(outline)
    if not outline_shape.is_valid or outline_shape.area <= 0:
        qa.add("FAIL", "ROOF_OUTLINE polygon is invalid or zero-area.", layer=ROOF_OUTLINE)
    for idx, pts in enumerate(obstruction_polys, start=1):
        obstruction_shape = Polygon(pts)
        if not outline_shape.buffer(containment_tolerance_ft).covers(obstruction_shape):
            qa.add(
                "FAIL",
                (
                    f"ROOF_OBSTRUCTION polyline #{idx} is outside the "
                    "reviewed roof outline."
                ),
                layer=ROOF_OBSTRUCTION,
                entity=f"polyline #{idx}",
            )
    for idx, pts in enumerate(pv_zone_polys, start=1):
        zone_shape = Polygon(pts)
        if not outline_shape.buffer(containment_tolerance_ft).covers(zone_shape):
            qa.add(
                "FAIL",
                f"PV_MODULE_ZONE polyline #{idx} is outside the reviewed roof outline.",
                layer=PV_MODULE_ZONE,
                entity=f"polyline #{idx}",
            )

    facets: list[list[Point]] = []
    for idx, pts in enumerate(facet_polys, start=1):
        facet_shape = Polygon(pts)
        if not facet_shape.is_valid or facet_shape.area <= 0:
            qa.add(
                "FAIL",
                f"ROOF_FACET polyline #{idx} is invalid or zero-area.",
                layer=ROOF_FACET,
            )
            continue
        if not outline_shape.buffer(containment_tolerance_ft).covers(facet_shape):
            qa.add(
                "FAIL",
                f"ROOF_FACET polyline #{idx} is outside the reviewed roof outline.",
                layer=ROOF_FACET,
            )
            continue
        facets.append(pts)

    if len(facets) < len(facet_polys):
        if strict:
            qa.raise_if_failed()
        raise RoofReviewImportError("Reviewed DXF failed roof QA.", qa=qa)

    _qa_facet_overlaps(qa, facets)
    if qa.failures:
        if strict:
            qa.raise_if_failed()
        raise RoofReviewImportError("Reviewed DXF failed roof QA.", qa=qa)

    facet_area = sum(abs(polygon_area(pts)) for pts in facets)
    outline_area = abs(polygon_area(outline))
    if outline_area > 0:
        ratio = facet_area / outline_area
        if ratio < 0.35:
            qa.add(
                "WARN",
                f"Facet area is only {ratio:.0%} of outline area; check missing faces.",
                layer=ROOF_FACET,
            )
        elif ratio > 1.08:
            qa.add(
                "WARN",
                f"Facet area is {ratio:.0%} of outline area; check overlapping faces.",
                layer=ROOF_FACET,
            )

    roof_facets: list[EE4TracePolygon] = []
    roof_sections: list[RoofSection] = []
    facet_meta: list[tuple[list[Point], dict[str, str | float | bool]]] = []
    for idx, pts in enumerate(facets, start=1):
        label = _label_for_polygon(labels, pts)
        meta = _parse_label(label.text if label else "")
        facet_meta.append((pts, meta))
        name = meta.get("name") or f"Roof Face {idx}"
        pitch = float(meta.get("pitch_deg", default_pitch_deg))
        azimuth = float(meta.get("azimuth_deg", default_azimuth_deg)) % 360.0
        module_count = int(meta.get("module_count", 0))
        x0, y0, x1, y1 = _bbox(pts)
        local_vertices = [
            _clean_point((x - x0, y - y0))
            for x, y in pts
        ]
        obstructions = _obstructions_for_facet(
            obstruction_polys,
            pts,
            origin=(x0, y0),
        )
        roof_facets.append(EE4TracePolygon(name=name, vertices=pts))
        if meta.get("pv_area") is False:
            continue
        roof_sections.append(RoofSection(
            name=name,
            pitch_deg=round(pitch, 1),
            azimuth_deg=round(azimuth, 1),
            width_ft=round(max(x1 - x0, 0.1), 2),
            height_ft=round(max(y1 - y0, 0.1), 2),
            shape="polygon",
            vertices=local_vertices,
            module_count=max(0, module_count),
            obstructions=obstructions,
            site_anchor_x_ft=round(x0, 2),
            site_anchor_y_ft=round(y0, 2),
            site_anchor_azimuth_deg=0.0,
        ))
    _qa_pv_module_zones(
        qa,
        pv_zone_polys=pv_zone_polys,
        obstruction_polys=obstruction_polys,
        facet_meta=facet_meta,
        default_azimuth_deg=default_azimuth_deg,
    )
    if qa.failures:
        if strict:
            qa.raise_if_failed()
        raise RoofReviewImportError("Reviewed DXF failed roof QA.", qa=qa)

    roof_lines = _roof_lines(msp, qa)
    fire_pathways = [
        EE4TracePolygon(name=f"Fire pathway {idx}", vertices=pts)
        for idx, pts in enumerate(fire_polys, start=1)
    ]
    symbols = _trace_symbols(obstruction_polys)
    trace = EE4Trace(
        enabled=True,
        roof_outline=EE4TracePolygon(
            name="CAD reviewed roof outline",
            vertices=outline,
        ),
        roof_facets=roof_facets,
        roof_lines=roof_lines,
        fire_pathways=fire_pathways,
        symbols=symbols,
    )
    payload = {
        "site": {
            "roof_sections": [
                section.model_dump(mode="json", exclude_none=True)
                for section in roof_sections
            ],
            "ee4_trace": trace.model_dump(mode="json", exclude_none=True),
        }
    }
    site = Site.model_validate(payload["site"])
    return ImportedRoof(qa=qa, yaml_payload=payload, site=site)


def write_import_outputs(
    dxf_path: Path,
    output_dir: Path,
    *,
    original_inputs_path: Path | None = None,
    default_pitch_deg: float = 22.0,
    default_azimuth_deg: float = 180.0,
) -> dict[str, Path]:
    """Import a reviewed DXF and write YAML + PNG preview artifacts."""
    from .preview import write_import_preview
    from .qa import write_qa_report

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    imported = import_reviewed_dxf(
        dxf_path,
        default_pitch_deg=default_pitch_deg,
        default_azimuth_deg=default_azimuth_deg,
    )
    yaml_path = output_dir / "imported-roof.yaml"
    preview_path = output_dir / "import-preview.png"
    qa_report_path = output_dir / "roof-qa-report.md"
    yaml_path.write_text(imported.yaml_text(), encoding="utf-8")
    write_import_preview(imported, preview_path)
    write_qa_report(imported.qa, qa_report_path, dxf_path=Path(dxf_path))
    artifacts = {
        "yaml": yaml_path,
        "preview": preview_path,
        "qa_report": qa_report_path,
    }
    if original_inputs_path is not None:
        artifacts.update(_write_merge_artifacts(
            imported,
            Path(original_inputs_path),
            output_dir,
        ))
    return artifacts


def _closed_polygons(
    msp,
    layer: str,
    qa: RoofReviewQA,
    *,
    required: bool = True,
) -> list[list[Point]]:
    polys: list[list[Point]] = []
    found = False
    entity_index = 0
    for entity in msp:
        if entity.dxf.layer != layer:
            continue
        if entity.dxftype() not in {"LWPOLYLINE", "POLYLINE"}:
            continue
        found = True
        entity_index += 1
        entity_ref = _entity_ref(entity, entity_index)
        closed = _entity_closed(entity)
        pts = _polyline_points(entity)
        if len(pts) >= 2 and _same_point(pts[0], pts[-1]):
            closed = True
            pts = pts[:-1]
        if not closed:
            qa.add(
                "FAIL",
                f"{layer} polyline #{entity_index} is not closed.",
                layer=layer,
                entity=entity_ref,
            )
            continue
        clean = _normalize_polygon(
            pts,
            qa,
            layer=layer,
            entity_ref=entity_ref,
            entity_index=entity_index,
        )
        if clean:
            polys.append(clean)
    if required and not found:
        qa.add("FAIL", f"No closed polylines found on {layer}.", layer=layer)
    return polys


def _write_merge_artifacts(
    imported: ImportedRoof,
    original_inputs_path: Path,
    output_dir: Path,
) -> dict[str, Path]:
    original_data = yaml.safe_load(
        original_inputs_path.read_text(encoding="utf-8")
    ) or {}
    merged_data = deepcopy(original_data)
    site_data = merged_data.setdefault("site", {})
    imported_site = imported.yaml_payload["site"]
    old_sections = list(site_data.get("roof_sections") or [])
    old_trace = site_data.get("ee4_trace") or {}
    site_data["roof_sections"] = imported_site.get("roof_sections", [])
    site_data["ee4_trace"] = imported_site.get("ee4_trace", {})

    merged_inputs_path = output_dir / "inputs.roof-merged.yaml"
    merge_preview_path = output_dir / "roof-merge-preview.md"
    validation_path = output_dir / "roof-import-validation.md"
    merged_inputs_path.write_text(
        yaml.safe_dump(
            merged_data,
            sort_keys=False,
            allow_unicode=False,
        ),
        encoding="utf-8",
    )
    merge_preview_path.write_text(
        _merge_preview_markdown(
            old_sections=old_sections,
            old_trace=old_trace,
            imported=imported,
            merged_inputs_path=merged_inputs_path,
        ),
        encoding="utf-8",
    )
    validation_path.write_text(
        _validation_markdown(merged_data, merged_inputs_path),
        encoding="utf-8",
    )
    return {
        "merged_inputs": merged_inputs_path,
        "merge_preview": merge_preview_path,
        "validation": validation_path,
    }


def _merge_preview_markdown(
    *,
    old_sections: list,
    old_trace: dict,
    imported: ImportedRoof,
    merged_inputs_path: Path,
) -> str:
    trace = imported.site.ee4_trace
    old_trace_facets = len((old_trace or {}).get("roof_facets") or [])
    old_trace_lines = len((old_trace or {}).get("roof_lines") or [])
    lines = [
        "# Roof Import Merge Preview",
        "",
        "This is a dry-run merge. The project inputs.yaml was not modified.",
        "",
        f"- Merged copy: {merged_inputs_path}",
        "- Replaced path: site.roof_sections",
        "- Replaced path: site.ee4_trace",
        "",
        "## Before",
        "",
        f"- roof_sections: {len(old_sections)}",
        f"- ee4_trace.roof_facets: {old_trace_facets}",
        f"- ee4_trace.roof_lines: {old_trace_lines}",
        "",
        "## After",
        "",
        f"- roof_sections: {len(imported.site.roof_sections)}",
        f"- ee4_trace.roof_facets: {len(trace.roof_facets)}",
        f"- ee4_trace.roof_lines: {len(trace.roof_lines)}",
        f"- ee4_trace.symbols: {len(trace.symbols)}",
        "",
        "## Next Step",
        "",
        "Review the merged file. If engineering accepts it, copy its site block into inputs.yaml or replace inputs.yaml intentionally.",
    ]
    return "\n".join(lines) + "\n"


def _validation_markdown(
    merged_data: dict[str, Any],
    merged_inputs_path: Path,
) -> str:
    from ..calc.engine import run

    lines = [
        "# Roof Import Validation",
        "",
        f"- Merged inputs: {merged_inputs_path}",
        "",
    ]
    try:
        inputs = Inputs.model_validate(merged_data)
        lines.append("- schema: PASS")
    except Exception as exc:
        lines.extend([
            "- schema: FAIL",
            f"- detail: {exc}",
        ])
        return "\n".join(lines) + "\n"
    try:
        result = run(inputs)
        placed_modules = sum(
            len(modules) for modules in result.module_placements.values()
        )
        declared_modules = result.inputs.pv_array.modules
        lines.extend([
            "- calc_engine: PASS",
            f"- roof_sections: {len(inputs.site.roof_sections)}",
            f"- ee4_trace.roof_facets: {len(inputs.site.ee4_trace.roof_facets)}",
            f"- pv_modules_declared: {declared_modules}",
            f"- pv_modules_placed: {placed_modules}",
        ])
        if declared_modules > 0 and placed_modules < declared_modules:
            lines.append(
                "- module_placement: WARN "
                f"{placed_modules}/{declared_modules} placed after setbacks, "
                "obstruction clearances, and overlap checks"
            )
        else:
            lines.append("- module_placement: PASS")
    except Exception as exc:
        lines.extend([
            "- calc_engine: FAIL",
            f"- detail: {exc}",
        ])
    return "\n".join(lines) + "\n"


def _entity_closed(entity) -> bool:
    closed = getattr(entity, "closed", False)
    if callable(closed):
        closed = closed()
    is_closed = getattr(entity, "is_closed", False)
    if callable(is_closed):
        is_closed = is_closed()
    return bool(closed or is_closed)


def _normalize_polygon(
    pts: list[Point],
    qa: RoofReviewQA,
    *,
    layer: str,
    entity_ref: str,
    entity_index: int,
) -> list[Point] | None:
    pts = _dedupe_consecutive(pts)
    if len(pts) < 3:
        qa.add(
            "FAIL",
            f"{layer} polygon #{entity_index} needs at least 3 vertices.",
            layer=layer,
            entity=entity_ref,
        )
        return None
    shape = Polygon(pts)
    if not shape.is_valid:
        qa.add(
            "FAIL",
            f"{layer} polygon #{entity_index} self-intersects or is invalid.",
            layer=layer,
            entity=entity_ref,
        )
        return None
    area = polygon_area(pts)
    if math.isclose(area, 0.0, abs_tol=1e-6):
        qa.add(
            "FAIL",
            f"{layer} polygon #{entity_index} has zero area.",
            layer=layer,
            entity=entity_ref,
        )
        return None
    if area < 0:
        pts = list(reversed(pts))
        qa.add(
            "WARN",
            f"{layer} polygon #{entity_index} was clockwise; reversed to CCW.",
            layer=layer,
            entity=entity_ref,
        )
    return [_clean_point(pt) for pt in pts]


def _qa_pv_module_zones(
    qa: RoofReviewQA,
    *,
    pv_zone_polys: list[list[Point]],
    obstruction_polys: list[list[Point]],
    facet_meta: list[tuple[list[Point], dict[str, str | float | bool]]],
    default_azimuth_deg: float,
) -> None:
    if not pv_zone_polys:
        return
    obstruction_shapes = [Polygon(pts) for pts in obstruction_polys]
    facet_shapes = [
        (Polygon(pts), meta)
        for pts, meta in facet_meta
    ]
    for zone_idx, zone in enumerate(pv_zone_polys, start=1):
        zone_shape = Polygon(zone)
        for obs_idx, obstruction_shape in enumerate(obstruction_shapes, start=1):
            overlap_area = zone_shape.intersection(obstruction_shape).area
            if overlap_area > 1e-4:
                qa.add(
                    "FAIL",
                    (
                        f"PV_MODULE_ZONE polyline #{zone_idx} overlaps "
                        f"ROOF_OBSTRUCTION polyline #{obs_idx}; mark this as "
                        "no-panel area or move the PV zone."
                    ),
                    layer=PV_MODULE_ZONE,
                    entity=f"polyline #{zone_idx}",
                )

        best_meta: dict[str, str | float | bool] | None = None
        best_area = 0.0
        for facet_shape, meta in facet_shapes:
            area = zone_shape.intersection(facet_shape).area
            if area > best_area:
                best_area = area
                best_meta = meta
        if best_area <= 1e-4:
            qa.add(
                "WARN",
                (
                    f"PV_MODULE_ZONE polyline #{zone_idx} is not clearly "
                    "inside any ROOF_FACET."
                ),
                layer=PV_MODULE_ZONE,
                entity=f"polyline #{zone_idx}",
            )
            continue
        azimuth = float(
            (best_meta or {}).get("azimuth_deg", default_azimuth_deg)
        ) % 360.0
        if _is_north_azimuth(azimuth):
            qa.add(
                "WARN",
                (
                    f"PV_MODULE_ZONE polyline #{zone_idx} is on a north-facing "
                    f"facet (AZ={azimuth:.0f}); avoid north faces unless "
                    "engineering explicitly approves."
                ),
                layer=PV_MODULE_ZONE,
                entity=f"polyline #{zone_idx}",
            )


def _qa_facet_overlaps(
    qa: RoofReviewQA,
    facets: list[list[Point]],
    *,
    min_area_sqft: float = 0.5,
) -> None:
    shapes = [Polygon(pts) for pts in facets]
    for i, a_shape in enumerate(shapes):
        for j, b_shape in enumerate(shapes[i + 1:], start=i + 1):
            overlap_area = a_shape.intersection(b_shape).area
            if overlap_area <= min_area_sqft:
                continue
            qa.add(
                "FAIL",
                (
                    f"ROOF_FACET polyline #{i + 1} overlaps polyline "
                    f"#{j + 1} by {overlap_area:.1f} sqft. Roof facets "
                    "must share edges only; overlapping faces cause duplicate "
                    "module placement."
                ),
                layer=ROOF_FACET,
                entity=f"polyline #{i + 1}/#{j + 1}",
            )


def _polyline_points(entity) -> list[Point]:
    if entity.dxftype() == "LWPOLYLINE":
        return [(float(x), float(y)) for x, y in entity.get_points("xy")]
    points: list[Point] = []
    for vertex in entity.vertices:
        loc = vertex.dxf.location
        points.append((float(loc.x), float(loc.y)))
    return points


def _roof_lines(msp, qa: RoofReviewQA) -> list[EE4TraceLine]:
    lines: list[EE4TraceLine] = []
    for entity in msp:
        layer = entity.dxf.layer
        if layer not in ROOF_LINE_KIND_BY_LAYER:
            continue
        pts = _line_points(entity)
        if len(pts) < 2:
            qa.add("WARN", f"{layer} entity has fewer than 2 points.", layer=layer)
            continue
        lines.append(EE4TraceLine(
            kind=ROOF_LINE_KIND_BY_LAYER[layer],
            points=[_clean_point(pt) for pt in pts],
        ))
    return lines


def _line_points(entity) -> list[Point]:
    kind = entity.dxftype()
    if kind == "LINE":
        s = entity.dxf.start
        e = entity.dxf.end
        return [(float(s.x), float(s.y)), (float(e.x), float(e.y))]
    if kind == "LWPOLYLINE":
        return [(float(x), float(y)) for x, y in entity.get_points("xy")]
    if kind == "POLYLINE":
        return _polyline_points(entity)
    return []


def _labels(msp) -> list[Label]:
    labels: list[Label] = []
    for entity in msp:
        if entity.dxf.layer != TEXT_ROOF_LABEL:
            continue
        if entity.dxftype() == "TEXT":
            text = entity.dxf.text
            loc = entity.dxf.insert
        elif entity.dxftype() == "MTEXT":
            text = entity.plain_text()
            loc = entity.dxf.insert
        else:
            continue
        labels.append(Label(text=str(text), point=(float(loc.x), float(loc.y))))
    return labels


def _parse_label(text: str) -> dict[str, str | float | bool]:
    meta: dict[str, str | float | bool] = {}
    if not text:
        return meta
    name = re.search(
        r"\bNAME\s*[:=]\s*(.*?)(?=\s+(?:PITCH|AZIMUTH|AZ|P|"
        r"MODULES|MODULE_COUNT|MOD|M|PV|PV_AREA|ACTIVE|INSTALL|"
        r"INSTALLABLE)\s*[:=]|[;\n]|$)",
        text,
        flags=re.I,
    )
    if name:
        meta["name"] = name.group(1).strip()
    pitch = re.search(r"\b(?:PITCH|P)\s*[:=]?\s*(-?\d+(?:\.\d+)?)", text, flags=re.I)
    if pitch:
        meta["pitch_deg"] = float(pitch.group(1))
    az = re.search(r"\b(?:AZ|AZIMUTH)\s*[:=]?\s*(-?\d+(?:\.\d+)?)", text, flags=re.I)
    if az:
        meta["azimuth_deg"] = float(az.group(1))
    modules = re.search(
        r"\b(?:MODULES|MODULE_COUNT|MOD|M)\s*[:=]?\s*(\d+)",
        text,
        flags=re.I,
    )
    if modules:
        meta["module_count"] = int(modules.group(1))
    pv_area = re.search(
        r"\b(?:PV|PV_AREA|ACTIVE|INSTALL|INSTALLABLE)\s*[:=]?\s*"
        r"(NO|FALSE|0|N|YES|TRUE|1|Y)\b",
        text,
        flags=re.I,
    )
    if pv_area:
        meta["pv_area"] = pv_area.group(1).upper() in {"YES", "TRUE", "1", "Y"}
    return meta


def _label_for_polygon(labels: Iterable[Label], pts: list[Point]) -> Label | None:
    shape = Polygon(pts)
    centroid = shape.centroid
    inside = [
        label for label in labels
        if shape.buffer(0.25).covers(ShapelyPoint(label.point))
    ]
    if inside:
        return min(
            inside,
            key=lambda label: ShapelyPoint(label.point).distance(centroid),
        )
    return None


def _obstructions_for_facet(
    obstruction_polys: list[list[Point]],
    facet: list[Point],
    *,
    origin: Point = (0.0, 0.0),
) -> list[RoofObstruction]:
    facet_shape = Polygon(facet).buffer(0.25)
    result: list[RoofObstruction] = []
    ox, oy = origin
    for pts in obstruction_polys:
        poly = Polygon(pts)
        if not facet_shape.covers(poly.centroid):
            continue
        x0, y0, x1, y1 = _bbox(pts)
        result.append(RoofObstruction(
            kind="other",
            x_ft=round(x0 - ox, 2),
            y_ft=round(y0 - oy, 2),
            width_ft=round(max(x1 - x0, 0.1), 2),
            height_ft=round(max(y1 - y0, 0.1), 2),
            note="Imported from ROOF_OBSTRUCTION CAD layer.",
        ))
    return result


def _trace_symbols(obstruction_polys: list[list[Point]]) -> list[EE4TraceSymbol]:
    symbols: list[EE4TraceSymbol] = []
    for pts in obstruction_polys:
        centroid = Polygon(pts).centroid
        symbols.append(EE4TraceSymbol(
            kind="roof_vent",
            x_ft=round(float(centroid.x), 2),
            y_ft=round(float(centroid.y), 2),
        ))
    return symbols


def _largest_polygon(polys: list[list[Point]]) -> list[Point]:
    return max(polys, key=lambda pts: abs(polygon_area(pts)))


def _bbox(pts: list[Point]) -> tuple[float, float, float, float]:
    xs = [pt[0] for pt in pts]
    ys = [pt[1] for pt in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _same_point(a: Point, b: Point, tol: float = 1e-6) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def _entity_ref(entity, index: int) -> str:
    handle = getattr(entity.dxf, "handle", "")
    if handle:
        return f"{entity.dxftype()} #{index} handle={handle}"
    return f"{entity.dxftype()} #{index}"


def _is_north_azimuth(azimuth_deg: float) -> bool:
    az = float(azimuth_deg) % 360.0
    return az <= 45.0 or az >= 315.0


def _dedupe_consecutive(pts: list[Point]) -> list[Point]:
    clean: list[Point] = []
    for pt in pts:
        if clean and _same_point(clean[-1], pt):
            continue
        clean.append((float(pt[0]), float(pt[1])))
    if len(clean) > 1 and _same_point(clean[0], clean[-1]):
        clean.pop()
    return clean


def _clean_point(pt: Point) -> Point:
    return (round(float(pt[0]), 3), round(float(pt[1]), 3))
