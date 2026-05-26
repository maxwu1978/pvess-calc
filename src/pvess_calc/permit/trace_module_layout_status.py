"""Trace-aware module layout readiness for AHJ review."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..calc.engine import CalculationResult
from .ee4_lint import lint_ee4_preview
from .ee4_trace_modules import ee4_module_count
from .site_plan import _ee4_trace_active


BLOCKING_LINTS = {
    "ee4_module_rectangles_no_overlap",
    "ee4_module_count_matches_face_allocation",
    "ee4_module_rectangles_inside_assigned_faces",
    "ee4_module_rectangles_clear_fire_pathway",
    "ee4_modules_inside_trace_roof",
    "ee4_modules_clear_fire_pathway",
    "ee4_fire_pathway_inside_roof",
}


def assess_trace_module_layout_status(
    result: CalculationResult,
) -> dict[str, Any]:
    """Return AHJ-gate status for modules placed on traced roof geometry."""
    trace_active = _ee4_trace_active(result.inputs.site)
    target = int(result.inputs.pv_array.modules)
    placed = (
        ee4_module_count(result)
        if trace_active
        else sum(len(modules) for modules in result.module_placements.values())
    )
    if not trace_active:
        return {
            "status": "WARN",
            "mode": "waiting_for_trace",
            "label": "Trace module layout not active",
            "can_ahj_ready": False,
            "target_modules": target,
            "placed_modules": placed,
            "detail": (
                "Module placement has not been checked against a traced roof "
                "outline because site.ee4_trace is not active."
            ),
            "required_action": (
                "Accept or manually enter site.ee4_trace before AHJ-ready "
                "module layout review."
            ),
            "blocking_lints": [],
            "warning_lints": [],
        }

    lint_results = lint_ee4_preview(result)
    lint_payload = [
        {
            "name": lint.name,
            "status": lint.status,
            "detail": lint.detail,
        }
        for lint in lint_results
    ]
    blocking = [
        item for item in lint_payload
        if item["name"] in BLOCKING_LINTS and item["status"] != "PASS"
    ]
    warnings = [
        item for item in lint_payload
        if item["name"] not in BLOCKING_LINTS and item["status"] != "PASS"
    ]
    if placed != target:
        blocking.append({
            "name": "ee4_module_count_matches_project",
            "status": "FAIL",
            "detail": f"{placed}/{target} module rectangle(s) placed.",
        })

    if blocking:
        detail = "; ".join(
            f"{item['name']}: {item['detail']}" for item in blocking[:4]
        )
        return {
            "status": "FAIL",
            "mode": "traced_layout_blocked",
            "label": "Trace module layout needs revision",
            "can_ahj_ready": False,
            "target_modules": target,
            "placed_modules": placed,
            "detail": detail,
            "required_action": (
                "Revise roof trace, fire pathways, obstructions, or module "
                "count until every module is inside the traced roof, clear of "
                "fire pathways, non-overlapping, and count-matched."
            ),
            "blocking_lints": blocking,
            "warning_lints": warnings,
        }

    return {
        "status": "PASS" if not warnings else "WARN",
        "mode": "traced_layout",
        "label": "Trace module layout verified",
        "can_ahj_ready": True,
        "target_modules": target,
        "placed_modules": placed,
        "detail": (
            f"{placed}/{target} module rectangle(s) are inside traced roof "
            "geometry, inside their assigned roof faces, clear of fire "
            "pathways, count-matched, and non-overlapping."
        ),
        "required_action": (
            "Review any non-blocking layout warnings before final drafting."
            if warnings else ""
        ),
        "blocking_lints": [],
        "warning_lints": warnings,
    }


def write_trace_module_layout_artifacts(
    result: CalculationResult,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    status = assess_trace_module_layout_status(result)

    status_json = output_dir / "trace-module-layout-status.json"
    status_json.write_text(
        json.dumps(status, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    status_md = output_dir / "trace-module-layout-status.md"
    status_md.write_text(
        format_trace_module_layout_status_markdown(status),
        encoding="utf-8",
    )
    return {
        "status": status,
        "status_json": status_json,
        "status_markdown": status_md,
    }


def format_trace_module_layout_status_markdown(
    status: dict[str, Any],
) -> str:
    lines = [
        "# Trace Module Layout Readiness",
        "",
        f"- Status: **{status.get('status', 'UNKNOWN')}**",
        f"- Mode: `{status.get('mode', '')}`",
        f"- AHJ-ready: {'yes' if status.get('can_ahj_ready') else 'no'}",
        (
            f"- Modules: {status.get('placed_modules', 0)} / "
            f"{status.get('target_modules', 0)}"
        ),
        "",
        "## Detail",
        "",
        str(status.get("detail") or "No detail."),
    ]
    action = str(status.get("required_action") or "").strip()
    if action:
        lines.extend(["", "## Required Action", "", action])
    blockers = status.get("blocking_lints") or []
    if blockers:
        lines.extend(["", "## Blocking Layout Checks", ""])
        for item in blockers:
            lines.append(
                f"- `{item.get('name')}`: {item.get('detail', '')}"
            )
    warnings = status.get("warning_lints") or []
    if warnings:
        lines.extend(["", "## Non-Blocking Layout Warnings", ""])
        for item in warnings:
            lines.append(
                f"- `{item.get('name')}`: {item.get('detail', '')}"
            )
    lines.append("")
    return "\n".join(lines)
