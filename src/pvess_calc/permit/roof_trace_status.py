"""Roof trace readiness helpers for permit and web review flows."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..calc.engine import CalculationResult
from .ee4_trace import write_ee4_trace_skeleton


def assess_roof_trace_status(result: CalculationResult) -> dict[str, Any]:
    """Return a small, UI-friendly roof geometry readiness object.

    `site.roof_sections` from lookup providers are useful for sizing and
    production estimates, but they are not always a true plan-view roof
    outline. AHJ-ready packages require a reviewed `site.ee4_trace` layer.
    """
    site = result.inputs.site
    trace = site.ee4_trace
    sections = list(site.roof_sections or [])
    section_count = len(sections)
    has_section_vertices = any(bool(section.vertices) for section in sections)
    has_house_outline = bool(site.house_outline_vertices)

    missing_trace_layers: list[str] = []
    if trace.enabled:
        if trace.roof_outline is None:
            missing_trace_layers.append("roof_outline")
        if not trace.roof_facets and not trace.roof_lines:
            missing_trace_layers.append("roof_facets or roof_lines")
        if not trace.fire_pathways:
            missing_trace_layers.append("fire_pathways")
        if not missing_trace_layers:
            return {
                "status": "PASS",
                "mode": "traced",
                "label": "Traced roof geometry",
                "can_ahj_ready": True,
                "section_count": section_count,
                "source": "site.ee4_trace",
                "detail": (
                    f"Trace active with outline, {len(trace.roof_facets)} "
                    f"facet(s), {len(trace.roof_lines)} roof line(s), and "
                    f"{len(trace.fire_pathways)} fire-pathway polygon(s)."
                ),
                "required_action": "",
                "missing_layers": [],
            }
        return {
            "status": "WARN",
            "mode": "partial_trace",
            "label": "Partial roof trace",
            "can_ahj_ready": False,
            "section_count": section_count,
            "source": "site.ee4_trace",
            "detail": (
                "Trace mode is enabled, but required layers are missing: "
                + ", ".join(missing_trace_layers)
                + "."
            ),
            "required_action": "Complete the missing trace layers before AHJ-ready review.",
            "missing_layers": missing_trace_layers,
        }

    if _untraced_many_segments(
        section_count=section_count,
        has_house_outline=has_house_outline,
        has_section_vertices=has_section_vertices,
    ):
        return {
            "status": "WARN",
            "mode": "schematic_segments",
            "label": "Schematic roof segments",
            "can_ahj_ready": False,
            "section_count": section_count,
            "source": "Google Solar roofSegmentStats / lookup roof_sections",
            "detail": (
                "The package has many roof segment boxes but no traced house "
                "roof outline. The PV pages are schematic and may not match "
                "the actual roof shape."
            ),
            "required_action": (
                "Accept a satellite/mask trace or manually trace the roof "
                "outline before AHJ-ready review."
            ),
            "missing_layers": ["site.ee4_trace"],
        }

    if section_count:
        return {
            "status": "WARN",
            "mode": "coarse_roof_sections",
            "label": "Coarse roof sections",
            "can_ahj_ready": False,
            "section_count": section_count,
            "source": "site.roof_sections",
            "detail": (
                "Roof sections are available for sizing, but no reviewed "
                "EE-4 trace is active."
            ),
            "required_action": (
                "Trace or verify the roof outline before AHJ-ready review."
            ),
            "missing_layers": ["site.ee4_trace"],
        }

    return {
        "status": "WARN",
        "mode": "missing_roof_geometry",
        "label": "Roof geometry missing",
        "can_ahj_ready": False,
        "section_count": 0,
        "source": "",
        "detail": "No roof_sections or EE-4 trace are available.",
        "required_action": (
            "Run address lookup, upload roof evidence, or manually enter roof "
            "geometry before engineering review."
        ),
        "missing_layers": ["site.roof_sections", "site.ee4_trace"],
    }


def write_roof_trace_artifacts(
    result: CalculationResult,
    output_dir: Path,
) -> dict[str, Path | dict[str, Any]]:
    """Write roof trace status files and an editable trace draft YAML."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    status = assess_roof_trace_status(result)

    status_json = output_dir / "roof-trace-status.json"
    status_json.write_text(
        json.dumps(status, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    status_md = output_dir / "roof-trace-status.md"
    status_md.write_text(format_roof_trace_status_markdown(status), encoding="utf-8")

    draft_yaml = output_dir / "ee4-trace-draft.yaml"
    write_ee4_trace_skeleton(result, draft_yaml)

    return {
        "status": status,
        "status_json": status_json,
        "status_markdown": status_md,
        "draft_yaml": draft_yaml,
    }


def format_roof_trace_status_markdown(status: dict[str, Any]) -> str:
    lines = [
        "# Roof Trace Readiness",
        "",
        f"- Status: {status.get('status', 'WARN')}",
        f"- Mode: {status.get('mode', '-')}",
        f"- Label: {status.get('label', '-')}",
        f"- AHJ-ready geometry: {'yes' if status.get('can_ahj_ready') else 'no'}",
        f"- Source: {status.get('source') or '-'}",
        f"- Roof section count: {status.get('section_count', 0)}",
        "",
        "## Detail",
        "",
        str(status.get("detail") or "-"),
        "",
        "## Required action",
        "",
        str(status.get("required_action") or "No action required."),
        "",
    ]
    missing = status.get("missing_layers") or []
    if missing:
        lines.extend([
            "## Missing trace layers",
            "",
            *[f"- {item}" for item in missing],
            "",
        ])
    return "\n".join(lines)


def _untraced_many_segments(
    *,
    section_count: int,
    has_house_outline: bool,
    has_section_vertices: bool,
) -> bool:
    return section_count > 8 and not has_house_outline and not has_section_vertices
