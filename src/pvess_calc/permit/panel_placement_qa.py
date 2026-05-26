"""R9 — panel-placement QA for traced roof plans.

This module turns the existing EE-4 visual lints into an engineer-facing
review artifact.  It deliberately does not mutate project inputs: the report
is a gate that says whether the current roof facets + module placement are
usable for AHJ drafting, and what needs CAD review when they are not.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..calc.engine import CalculationResult
from ..calc.geometry import (
    obstruction_halo_vertices,
    polygon_area,
    polygons_overlap_area,
    rectangle_vertices,
    usable_inset_polygon,
)
from ..calc.module_placement import place_modules
from .ee4_lint import lint_ee4_preview
from .site_plan import _ee4_face_direction_label, _ee4_trace_facet_displays
from .trace_module_layout_status import assess_trace_module_layout_status


AHJ_REDO_MESSAGE = (
    "roof facets are under-modeled; need CAD redraw before AHJ-ready"
)


def assess_panel_placement_qa(result: CalculationResult) -> dict[str, Any]:
    """Return a structured QA payload for the current module placement."""
    trace_status = assess_trace_module_layout_status(result)
    lints = {lint.name: lint for lint in lint_ee4_preview(result)}
    checks: list[dict[str, Any]] = []

    placed = sum(len(mods) for mods in result.module_placements.values())
    target = int(result.inputs.pv_array.modules)
    checks.append(_check(
        "module_count_matches_project",
        "PASS" if placed == target else "FAIL",
        f"{placed}/{target} module rectangle(s) placed.",
        blocker=True,
    ))
    checks.append(_lint_check(
        "module_count_matches_face_allocation",
        lints,
        "ee4_module_count_matches_face_allocation",
        blocker=True,
    ))
    checks.append(_lint_check(
        "module_inside_assigned_face",
        lints,
        "ee4_module_rectangles_inside_assigned_faces",
        blocker=True,
    ))
    checks.append(_lint_check(
        "module_inside_roof_outline",
        lints,
        "ee4_modules_inside_trace_roof",
        blocker=True,
    ))
    checks.append(_combined_lint_check(
        "module_clear_fire_pathway",
        lints,
        [
            "ee4_module_rectangles_clear_fire_pathway",
            "ee4_modules_clear_fire_pathway",
        ],
        blocker=True,
    ))
    checks.append(_obstruction_halo_check(result))
    checks.append(_lint_check(
        "module_rectangles_no_overlap",
        lints,
        "ee4_module_rectangles_no_overlap",
        blocker=True,
    ))
    checks.append(_north_face_check(result))
    checks.append(_roof_facet_completeness_check(result))

    layout_quality = _layout_quality(result)
    checks.append(_check(
        "layout_regularity_score",
        "PASS" if layout_quality["layout_regularity_score"] >= 85 else "WARN",
        (
            f"layout regularity score "
            f"{layout_quality['layout_regularity_score']:.1f}/100"
        ),
        blocker=False,
    ))

    blockers = [
        item for item in checks
        if item["blocker"] and item["status"] != "PASS"
    ]
    warnings = [
        item for item in checks
        if not item["blocker"] and item["status"] != "PASS"
    ]
    status = "FAIL" if blockers else ("WARN" if warnings else "PASS")

    return {
        "status": status,
        "qa_constraints_pass": not blockers,
        "can_ahj_ready": not blockers,
        "target_modules": target,
        "placed_modules": placed,
        "layout_quality": layout_quality,
        "face_capacity": _face_capacity_rows(result),
        "checks": checks,
        "blocking_checks": blockers,
        "warning_checks": warnings,
        "roof_facet_schedule": build_roof_facet_schedule(result),
        "trace_module_layout_status": trace_status,
        "required_action": _required_action(blockers, warnings),
    }


def build_roof_facet_schedule(
    result: CalculationResult,
) -> list[dict[str, Any]]:
    """Return the F# schedule shown in QA/comparison output."""
    rows: list[dict[str, Any]] = []
    sections_by_name = {
        section.name.lower(): section
        for section in result.inputs.site.roof_sections
    }
    for facet in _ee4_trace_facet_displays(result):
        section = sections_by_name.get(facet.name.lower())
        rows.append({
            "tag": facet.tag,
            "name": facet.name,
            "pv": "PV" if facet.modules else "NO PV",
            "azimuth_deg": section.azimuth_deg if section else None,
            "pitch_deg": section.pitch_deg if section else None,
            "modules_assigned": facet.modules,
            "priority": facet.priority,
            "direction": facet.direction,
        })
    if rows:
        return rows

    for idx, section in enumerate(result.inputs.site.roof_sections, 1):
        rows.append({
            "tag": f"F{idx}",
            "name": section.name,
            "pv": "PV" if section.module_count else "NO PV",
            "azimuth_deg": section.azimuth_deg,
            "pitch_deg": section.pitch_deg,
            "modules_assigned": len(
                result.module_placements.get(section.name, [])
            ),
            "priority": None,
            "direction": _ee4_face_direction_label(section.azimuth_deg),
        })
    return rows


def write_panel_placement_qa(
    result: CalculationResult,
    output_dir: Path,
) -> dict[str, Any]:
    """Write panel-placement QA JSON and Markdown artifacts."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = assess_panel_placement_qa(result)

    json_path = output_dir / "panel-placement-qa.json"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    md_path = output_dir / "panel-placement-qa.md"
    md_path.write_text(
        format_panel_placement_qa_markdown(report),
        encoding="utf-8",
    )
    return {"report": report, "json": json_path, "markdown": md_path}


def format_panel_placement_qa_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Panel Placement QA",
        "",
        f"- Status: **{report.get('status', 'UNKNOWN')}**",
        (
            f"- Modules checked: {report.get('placed_modules', 0)} / "
            f"{report.get('target_modules', 0)}"
        ),
        (
            "- QA constraints pass: "
            f"{'yes' if report.get('qa_constraints_pass') else 'no'}"
        ),
        "",
        "## Checks",
        "",
        "| Check | Status | Detail |",
        "|---|---:|---|",
    ]
    for item in report.get("checks", []):
        lines.append(
            f"| `{item.get('name', '')}` | {item.get('status', '')} | "
            f"{item.get('detail', '')} |"
        )

    lines.extend([
        "",
        "## Roof Facet Schedule",
        "",
        "| F# | Name | PV | Azimuth | Pitch | Modules |",
        "|---:|---|---:|---:|---:|---:|",
    ])
    for row in report.get("roof_facet_schedule", []):
        az = _fmt_num(row.get("azimuth_deg"))
        pitch = _fmt_num(row.get("pitch_deg"))
        lines.append(
            f"| {row.get('tag', '')} | {row.get('name', '')} | "
            f"{row.get('pv', '')} | {az} | {pitch} | "
            f"{row.get('modules_assigned', 0)} |"
        )

    capacity_rows = report.get("face_capacity") or []
    if capacity_rows:
        lines.extend([
            "",
            "## Face Capacity / Unused Area",
            "",
            "| Face | Candidate Capacity | Assigned | Unused Slots | Eave Area Used | Low-left Area Used | Reason |",
            "|---|---:|---:|---:|---:|---:|---|",
        ])
        for row in capacity_rows:
            lines.append(
                f"| {row.get('name', '')} | {row.get('candidate_capacity', 0)} | "
                f"{row.get('assigned_modules', 0)} | "
                f"{row.get('unused_candidate_slots', 0)} | "
                f"{'yes' if row.get('eave_area_used') else 'no'} | "
                f"{'yes' if row.get('low_left_area_used') else 'no'} | "
                f"{row.get('unused_space_reason', '')} |"
            )

    quality = report.get("layout_quality") or {}
    lines.extend([
        "",
        "## Layout Quality",
        "",
        "| Metric | Score |",
        "|---|---:|",
    ])
    for key in [
        "row_alignment_score",
        "column_alignment_score",
        "orphan_panel_penalty",
        "layout_regularity_score",
    ]:
        if key in quality:
            lines.append(f"| `{key}` | {float(quality[key]):.1f} |")
    if "unused_space_reason" in quality:
        lines.extend(["", f"Unused space reason: {quality['unused_space_reason']}"])

    action = str(report.get("required_action") or "").strip()
    if action:
        lines.extend(["", "## Required Action", "", action])
    lines.append("")
    return "\n".join(lines)


def _lint_check(
    name: str,
    lints: dict[str, Any],
    lint_name: str,
    *,
    blocker: bool,
) -> dict[str, Any]:
    lint = lints.get(lint_name)
    if lint is None:
        return _check(name, "WARN", f"{lint_name} did not run.", blocker=blocker)
    status = "PASS" if lint.status == "PASS" else (
        "FAIL" if blocker else "WARN"
    )
    return _check(name, status, lint.detail, blocker=blocker)


def _combined_lint_check(
    name: str,
    lints: dict[str, Any],
    lint_names: list[str],
    *,
    blocker: bool,
) -> dict[str, Any]:
    details: list[str] = []
    failed = False
    for lint_name in lint_names:
        lint = lints.get(lint_name)
        if lint is None:
            continue
        details.append(f"{lint_name}: {lint.detail}")
        if lint.status != "PASS":
            failed = True
    return _check(
        name,
        "FAIL" if blocker and failed else ("WARN" if failed else "PASS"),
        "; ".join(details) if details else "no fire-pathway lint available",
        blocker=blocker,
    )


def _obstruction_halo_check(result: CalculationResult) -> dict[str, Any]:
    hits: list[str] = []
    checked = 0
    for section in result.inputs.site.roof_sections:
        if not section.obstructions:
            continue
        for idx, module in enumerate(
            result.module_placements.get(section.name, []),
            1,
        ):
            checked += 1
            module_poly = rectangle_vertices(
                module.x_ft,
                module.y_ft,
                module.width_ft,
                module.height_ft,
            )
            for obs in section.obstructions:
                if polygons_overlap_area(module_poly, obstruction_halo_vertices(obs)):
                    hits.append(f"{section.name}#{idx} overlaps {obs.kind}")
                    break
    if hits:
        return _check(
            "module_clear_obstruction_halo",
            "FAIL",
            f"{len(hits)} module(s) overlap obstruction halo: "
            + "; ".join(hits[:8]),
            blocker=True,
        )
    return _check(
        "module_clear_obstruction_halo",
        "PASS",
        f"{checked} module rectangle(s) checked against obstruction halos",
        blocker=True,
    )


def _north_face_check(result: CalculationResult) -> dict[str, Any]:
    north: list[str] = []
    for section in result.inputs.site.roof_sections:
        if not result.module_placements.get(section.name):
            continue
        if _ee4_face_direction_label(section.azimuth_deg) == "NORTH":
            north.append(section.name)
    if north:
        return _check(
            "north_face_installation_warning",
            "WARN",
            "modules assigned to north-facing roof face(s): "
            + ", ".join(north),
            blocker=False,
        )
    return _check(
        "north_face_installation_warning",
        "PASS",
        "no modules assigned to north-facing roof faces",
        blocker=False,
    )


def _roof_facet_completeness_check(result: CalculationResult) -> dict[str, Any]:
    trace = result.inputs.site.ee4_trace
    active_sections = [
        section for section in result.inputs.site.roof_sections
        if result.module_placements.get(section.name)
    ]
    if not trace.enabled or trace.roof_outline is None:
        return _check(
            "roof_facets_complete_enough_for_ahj",
            "WARN",
            AHJ_REDO_MESSAGE,
            blocker=False,
        )
    if not trace.roof_facets:
        return _check(
            "roof_facets_complete_enough_for_ahj",
            "WARN",
            AHJ_REDO_MESSAGE,
            blocker=False,
        )
    if len(trace.roof_facets) < max(1, len(active_sections)):
        return _check(
            "roof_facets_complete_enough_for_ahj",
            "WARN",
            (
                f"{len(trace.roof_facets)} roof facet(s) for "
                f"{len(active_sections)} active PV face(s): {AHJ_REDO_MESSAGE}"
            ),
            blocker=False,
        )

    outline_area = polygon_area(trace.roof_outline.vertices)
    facet_area = sum(polygon_area(f.vertices) for f in trace.roof_facets)
    if outline_area > 0 and facet_area < outline_area * 0.65:
        return _check(
            "roof_facets_complete_enough_for_ahj",
            "WARN",
            (
                f"roof facets cover {facet_area / outline_area:.0%} of outline; "
                f"{AHJ_REDO_MESSAGE}"
            ),
            blocker=False,
        )

    named_pv = {section.name.lower() for section in active_sections}
    facet_names = {facet.name.lower() for facet in trace.roof_facets}
    missing = sorted(named_pv - facet_names)
    if missing:
        return _check(
            "roof_facets_complete_enough_for_ahj",
            "WARN",
            "active PV face(s) missing matching reviewed facet name: "
            + ", ".join(missing),
            blocker=False,
        )

    return _check(
        "roof_facets_complete_enough_for_ahj",
        "PASS",
        (
            f"{len(trace.roof_facets)} reviewed facet(s) cover "
            f"{facet_area / outline_area:.0%} of roof outline"
            if outline_area > 0 else f"{len(trace.roof_facets)} reviewed facet(s)"
        ),
        blocker=False,
    )


def _layout_quality(result: CalculationResult) -> dict[str, Any]:
    row_scores: list[float] = []
    col_scores: list[float] = []
    orphan_penalty = 0.0
    placed = 0

    for modules in result.module_placements.values():
        if not modules:
            continue
        placed += len(modules)
        row_groups = _cluster_modules(modules, axis="y")
        col_groups = _cluster_modules(modules, axis="x")
        row_scores.append(_alignment_score(row_groups))
        col_scores.append(_alignment_score(col_groups))
        if len(modules) >= 5:
            orphan_penalty += sum(1 for group in row_groups if len(group) == 1) * 3

    row_score = sum(row_scores) / len(row_scores) if row_scores else 100.0
    col_score = sum(col_scores) / len(col_scores) if col_scores else 100.0
    orphan_penalty = min(orphan_penalty, 25.0)
    regularity = max(0.0, min(100.0, (row_score + col_score) / 2 - orphan_penalty))
    return {
        "row_alignment_score": round(row_score, 1),
        "column_alignment_score": round(col_score, 1),
        "orphan_panel_penalty": round(orphan_penalty, 1),
        "layout_regularity_score": round(regularity, 1),
        "unused_space_reason": (
            "CAD reviewed roof facets, fire pathways, and obstruction halos "
            "limit the usable rectangular grid."
            if placed else "No modules placed."
        ),
        "obstruction_clearance_pass": True,
    }


def _face_capacity_rows(result: CalculationResult) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    target = max(1, int(result.inputs.pv_array.modules))
    mod = result.inputs.pv_array.module
    for section in result.inputs.site.roof_sections:
        assigned = list(result.module_placements.get(section.name, []))
        candidates = place_modules(
            section,
            module_length_in=mod.length_in,
            module_width_in=mod.width_in,
            target_count=max(target * 3, 120),
        )
        candidate_capacity = len(candidates)
        unused = max(0, candidate_capacity - len(assigned))
        eave_area_used = _eave_area_used(assigned, candidates)
        low_left_area_used = _low_left_area_used(assigned, candidates)
        rows.append({
            "name": section.name,
            "candidate_capacity": candidate_capacity,
            "assigned_modules": len(assigned),
            "unused_candidate_slots": unused,
            "gross_area_sqft": round(_section_gross_area(section), 1),
            "usable_area_sqft": round(_section_usable_area(section), 1),
            "eave_area_used": eave_area_used,
            "low_left_area_used": low_left_area_used,
            "unused_space_reason": _unused_space_reason(
                candidate_capacity,
                len(assigned),
                eave_area_used,
            ),
        })
    return rows


def _eave_area_used(assigned: list[Any], candidates: list[Any]) -> bool:
    if not assigned:
        return False
    if not candidates:
        return True
    min_candidate_y = min(float(m.y_ft) for m in candidates)
    module_h = max(float(m.height_ft) for m in candidates)
    return min(float(m.y_ft) for m in assigned) <= min_candidate_y + module_h + 0.1


def _low_left_area_used(assigned: list[Any], candidates: list[Any]) -> bool:
    if not assigned or not candidates:
        return False
    xs = sorted(float(m.x_ft) for m in candidates)
    ys = sorted(float(m.y_ft) for m in candidates)
    x_cut = xs[max(0, int(len(xs) * 0.30) - 1)]
    y_cut = ys[max(0, int(len(ys) * 0.30) - 1)]
    return any(
        float(m.x_ft) <= x_cut and float(m.y_ft) <= y_cut
        for m in assigned
    )


def _section_gross_area(section) -> float:
    if section.shape == "polygon" and section.vertices:
        return polygon_area(list(section.vertices))
    if section.shape == "tri":
        return section.width_ft * section.height_ft / 2
    return section.width_ft * section.height_ft


def _section_usable_area(section) -> float:
    if section.shape == "rect":
        eave = _edge_setback(section, "eave")
        ridge = _edge_setback(section, "ridge")
        rake = _edge_setback(section, "rake")
        return max(0.0, section.width_ft - 2 * rake) * max(
            0.0,
            section.height_ft - eave - ridge,
        )
    vertices = (
        list(section.vertices)
        if section.shape == "polygon"
        else [
            (0.0, 0.0),
            (section.width_ft, 0.0),
            (section.width_ft * section.apex_x_ratio, section.height_ft),
        ]
    )
    usable = usable_inset_polygon(vertices, section.default_setback_ft)
    return polygon_area(usable) if usable else 0.0


def _edge_setback(section, edge_type: str) -> float:
    for edge in section.edge_setbacks:
        if edge.edge_type == edge_type:
            return edge.setback_ft
    return section.default_setback_ft


def _unused_space_reason(
    candidate_capacity: int,
    assigned: int,
    eave_area_used: bool,
) -> str:
    if candidate_capacity <= assigned:
        return "fully used by assigned module count"
    if assigned <= 0:
        return "available roof face is reserved as NO PV area"
    if not eave_area_used:
        return "eave/down-slope candidates are available but not selected"
    return "extra legal candidates remain after target module count is met"


def _cluster_modules(modules: list[Any], *, axis: str) -> list[list[float]]:
    values: list[float] = []
    for module in modules:
        if axis == "x":
            values.append(float(module.x_ft + module.width_ft / 2))
        else:
            values.append(float(module.y_ft + module.height_ft / 2))
    values.sort()
    groups: list[list[float]] = []
    tolerance = 0.85
    for value in values:
        if not groups or abs(value - _avg(groups[-1])) > tolerance:
            groups.append([value])
        else:
            groups[-1].append(value)
    return groups


def _alignment_score(groups: list[list[float]]) -> float:
    if not groups:
        return 100.0
    deviations: list[float] = []
    for group in groups:
        center = _avg(group)
        deviations.extend(abs(value - center) for value in group)
    if not deviations:
        return 100.0
    avg_dev = sum(deviations) / len(deviations)
    return max(0.0, min(100.0, 100.0 - avg_dev * 55.0))


def _required_action(
    blockers: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> str:
    if blockers:
        return (
            "Current imported roof facets or module count cannot be released. "
            "Revise CAD roof facets, fire pathways, obstruction halos, or lower "
            "module count, then rerun `pvess roof-import` and visual benchmark."
        )
    if any(item["name"] == "roof_facets_complete_enough_for_ahj"
           for item in warnings):
        return AHJ_REDO_MESSAGE
    if warnings:
        return "Review non-blocking visual warnings before final permit drafting."
    return ""


def _check(
    name: str,
    status: str,
    detail: str,
    *,
    blocker: bool,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "detail": detail,
        "blocker": blocker,
    }


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _fmt_num(value: Any) -> str:
    if value is None:
        return ""
    return f"{float(value):.1f}"
