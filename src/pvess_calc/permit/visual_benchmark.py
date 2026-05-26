"""R9 — visual benchmark loop for roof/PV permit-plan sheets."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageChops, ImageOps

from ..calc.engine import run
from ..schema import Inputs
from .builder import _render_sheet, build_permit_package
from .panel_placement_qa import (
    assess_panel_placement_qa,
    write_panel_placement_qa,
)
from .sheet_registry import by_code, cover_index_rows


SHEET_TO_CODE = {
    "PV-2": "ee-4",
    "PV-4": "pv-4",
    "EE-1": "pv-6",
}

BENCHMARK_THRESHOLDS = {
    "overall_score": 85,
    "roof_facet_clarity_score": 90,
    "panel_layout_regularity_score": 85,
    "annotation_cleanliness_score": 90,
}


@dataclass(frozen=True)
class BenchmarkPaths:
    output_dir: Path
    metrics_json: Path
    comparison_md: Path
    permit_pdf: Path


def run_visual_benchmark(
    project_dir: Path,
    target: Path,
    *,
    sheet: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Generate sheet crops, overlay diffs, metrics, and comparison.md."""
    project_dir = Path(project_dir)
    target = Path(target)
    selected = _normalize_sheet(sheet)
    out_dir = output_dir or project_dir / "output" / "visual-benchmark"
    out_dir.mkdir(parents=True, exist_ok=True)

    inputs = Inputs.from_yaml(project_dir / "inputs.yaml")
    result = run(inputs)
    profile = inputs.project.permit_profile

    permit_pdf = (
        project_dir / "output" / f"permit-package-{inputs.project.id}.pdf"
    )
    build_permit_package(
        result,
        permit_pdf,
        package_profile=profile,
        project_dir=project_dir,
    )

    qa_artifacts = write_panel_placement_qa(
        result,
        project_dir / "output" / "roof-review",
    )
    rendered = _render_current_sheet_crops(
        result,
        profile=profile,
        out_dir=out_dir,
        sheets=selected,
    )
    target_crop = _target_crop(target)
    target_crop_path = out_dir / "target-crop.png"
    target_crop.save(target_crop_path)

    metrics = _benchmark_metrics(
        result,
        qa_artifacts["report"],
        target_crop,
        rendered,
    )
    metrics.update({
        "project_id": inputs.project.id,
        "target": str(target),
        "sheet": sheet or "ALL",
        "permit_pdf": str(permit_pdf),
        "qa_report_json": str(qa_artifacts["json"]),
        "qa_report_markdown": str(qa_artifacts["markdown"]),
    })

    for sheet_name, current_crop in rendered.items():
        slug = _sheet_slug(sheet_name)
        current_path = out_dir / f"current-{slug}-crop.png"
        current_crop.save(current_path)
        overlay = _overlay_diff(target_crop, current_crop)
        overlay.save(out_dir / f"overlay-diff-{slug}.png")

    side_by_side = _side_by_side(target_crop, rendered)
    side_by_side.save(out_dir / "side-by-side.png")

    metrics_json = out_dir / "metrics.json"
    metrics_json.write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    comparison_md = out_dir / "comparison.md"
    comparison_md.write_text(
        format_visual_comparison_markdown(metrics, qa_artifacts["report"]),
        encoding="utf-8",
    )

    return {
        "metrics": metrics,
        "paths": BenchmarkPaths(
            output_dir=out_dir,
            metrics_json=metrics_json,
            comparison_md=comparison_md,
            permit_pdf=permit_pdf,
        ),
        "qa": qa_artifacts["report"],
    }


def run_visual_iteration(
    project_dir: Path,
    target: Path,
    *,
    max_rounds: int = 3,
) -> dict[str, Any]:
    """Run bounded benchmark rounds and write per-round summaries."""
    project_dir = Path(project_dir)
    root = project_dir / "output" / "visual-iterations"
    root.mkdir(parents=True, exist_ok=True)
    rounds: list[dict[str, Any]] = []
    previous_crop: Path | None = None

    for idx in range(1, max(1, int(max_rounds)) + 1):
        round_dir = root / f"round-{idx:02d}"
        result = run_visual_benchmark(
            project_dir,
            target,
            output_dir=round_dir,
        )
        metrics = result["metrics"]
        current_crop = round_dir / "current-pv2-crop.png"
        if previous_crop and previous_crop.exists():
            shutil.copyfile(previous_crop, round_dir / "before.png")
        elif current_crop.exists():
            shutil.copyfile(current_crop, round_dir / "before.png")
        if current_crop.exists():
            shutil.copyfile(current_crop, round_dir / "after.png")
            previous_crop = current_crop
        overlay = round_dir / "overlay-diff-pv2.png"
        if overlay.exists():
            shutil.copyfile(overlay, round_dir / "overlay-diff.png")

        rounds.append({
            "round": idx,
            "metrics": metrics,
            "comparison": str(round_dir / "comparison.md"),
            "passed": _passes_thresholds(metrics),
        })
        if rounds[-1]["passed"]:
            break

    summary = {
        "status": "PASS" if rounds and rounds[-1]["passed"] else "BLOCKED",
        "rounds": rounds,
        "next_actions": _next_actions(rounds[-1]["metrics"] if rounds else {}),
    }
    final_md = root / "final-summary.md"
    final_md.write_text(_format_iteration_summary(summary), encoding="utf-8")
    summary["final_summary"] = str(final_md)
    return summary


def format_visual_comparison_markdown(
    metrics: dict[str, Any],
    qa_report: dict[str, Any],
) -> str:
    lines = [
        "# Visual Benchmark Comparison",
        "",
        f"- Overall score: **{metrics.get('overall_score', 0):.1f}**",
        (
            "- QA constraints pass: "
            f"{'yes' if metrics.get('qa_constraints_pass') else 'no'}"
        ),
        "",
        "## Metrics",
        "",
        "| Metric | Score | Target |",
        "|---|---:|---:|",
    ]
    for key in [
        "roof_line_density_score",
        "roof_facet_clarity_score",
        "panel_layout_regularity_score",
        "annotation_cleanliness_score",
        "fire_path_visibility_score",
        "equipment_leader_similarity_score",
        "overall_score",
    ]:
        target = BENCHMARK_THRESHOLDS.get(key, "")
        target_text = str(target) if target != "" else ""
        lines.append(
            f"| `{key}` | {float(metrics.get(key, 0)):.1f} | {target_text} |"
        )

    lines.extend([
        "",
        "## Roof Facet Schedule",
        "",
        "| F# | Name | PV | Azimuth | Pitch | Modules |",
        "|---:|---|---:|---:|---:|---:|",
    ])
    for row in qa_report.get("roof_facet_schedule", []):
        lines.append(
            f"| {row.get('tag', '')} | {row.get('name', '')} | "
            f"{row.get('pv', '')} | {_metric_num(row.get('azimuth_deg'))} | "
            f"{_metric_num(row.get('pitch_deg'))} | "
            f"{row.get('modules_assigned', 0)} |"
        )

    capacity_rows = qa_report.get("face_capacity") or []
    if capacity_rows:
        lines.extend([
            "",
            "## Face Capacity / Unused Area",
            "",
            "| Face | Candidate Capacity | Assigned | Unused Slots | Eave Area Used | Low-left Area Used |",
            "|---|---:|---:|---:|---:|---:|",
        ])
        for row in capacity_rows:
            lines.append(
                f"| {row.get('name', '')} | "
                f"{row.get('candidate_capacity', 0)} | "
                f"{row.get('assigned_modules', 0)} | "
                f"{row.get('unused_candidate_slots', 0)} | "
                f"{'yes' if row.get('eave_area_used') else 'no'} | "
                f"{'yes' if row.get('low_left_area_used') else 'no'} |"
            )

    actions = _next_actions(metrics)
    if actions:
        lines.extend(["", "## Next Improvement Actions", ""])
        for action in actions:
            lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def _render_current_sheet_crops(
    result,
    *,
    profile: str,
    out_dir: Path,
    sheets: list[str],
) -> dict[str, Image.Image]:
    rows = cover_index_rows(profile)
    rendered: dict[str, Image.Image] = {}
    with TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for sheet_name in sheets:
            spec = by_code(SHEET_TO_CODE[sheet_name], profile)
            slug = _sheet_slug(sheet_name)
            pdf_path = tmp_dir / f"{slug}.pdf"
            _render_sheet(result, spec, pdf_path, sheet_rows=rows)
            png = _rasterize_first_page(pdf_path)
            png.save(out_dir / f"current-{slug}-page.png")
            rendered[sheet_name] = _crop_roof_plan(png, sheet_name)
    return rendered


def _benchmark_metrics(
    result,
    qa_report: dict[str, Any],
    target_crop: Image.Image,
    rendered: dict[str, Image.Image],
) -> dict[str, Any]:
    primary = rendered.get("PV-2") or next(iter(rendered.values()))
    line_score = _density_similarity_score(
        _black_density(primary),
        _black_density(target_crop),
        scale=850,
    )
    clarity = _roof_facet_clarity_score(result, qa_report)
    regularity = float(
        (qa_report.get("layout_quality") or {}).get(
            "layout_regularity_score", 0.0,
        )
    )
    annotation = _annotation_score(qa_report)
    fire = _fire_path_score(result, rendered)
    equipment = _equipment_similarity_score(result)
    qa_pass = bool(qa_report.get("qa_constraints_pass"))
    overall = (
        line_score * 0.12
        + clarity * 0.22
        + regularity * 0.24
        + annotation * 0.18
        + fire * 0.14
        + equipment * 0.10
    )
    if not qa_pass:
        overall = min(overall, 74.0)

    return {
        "roof_line_density_score": round(line_score, 1),
        "roof_facet_clarity_score": round(clarity, 1),
        "panel_layout_regularity_score": round(regularity, 1),
        "annotation_cleanliness_score": round(annotation, 1),
        "fire_path_visibility_score": round(fire, 1),
        "equipment_leader_similarity_score": round(equipment, 1),
        "qa_constraints_pass": qa_pass,
        "overall_score": round(overall, 1),
    }


def _normalize_sheet(sheet: str | None) -> list[str]:
    if not sheet:
        return ["PV-2", "PV-4", "EE-1"]
    normalized = sheet.upper()
    if normalized not in SHEET_TO_CODE:
        raise ValueError(
            f"unsupported sheet {sheet!r}; expected PV-2, PV-4, or EE-1"
        )
    return [normalized]


def _sheet_slug(sheet: str) -> str:
    return sheet.lower().replace("-", "")


def _rasterize_first_page(pdf_path: Path) -> Image.Image:
    with fitz.open(str(pdf_path)) as doc:
        page = doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        mode = "RGB"
        return Image.frombytes(mode, (pix.width, pix.height), pix.samples)


def _crop_roof_plan(image: Image.Image, sheet: str) -> Image.Image:
    w, h = image.size
    fractions = {
        "PV-2": (0.18, 0.08, 0.98, 0.82),
        "PV-4": (0.03, 0.28, 0.96, 0.90),
        "EE-1": (0.05, 0.20, 0.97, 0.88),
    }[sheet]
    crop = image.crop((
        int(w * fractions[0]),
        int(h * fractions[1]),
        int(w * fractions[2]),
        int(h * fractions[3]),
    ))
    return _trim_to_content(crop, pad=24)


def _target_crop(target: Path) -> Image.Image:
    image = Image.open(target).convert("RGB")
    return _trim_to_content(image, pad=20)


def _trim_to_content(image: Image.Image, *, pad: int) -> Image.Image:
    gray = ImageOps.grayscale(image)
    arr = np.asarray(gray)
    mask = arr < 245
    if not mask.any():
        return image
    ys, xs = np.where(mask)
    x0 = max(0, int(xs.min()) - pad)
    y0 = max(0, int(ys.min()) - pad)
    x1 = min(image.size[0], int(xs.max()) + pad)
    y1 = min(image.size[1], int(ys.max()) + pad)
    if x1 <= x0 or y1 <= y0:
        return image
    return image.crop((x0, y0, x1, y1))


def _overlay_diff(target: Image.Image, current: Image.Image) -> Image.Image:
    current_rgb = current.convert("RGB")
    target_rgb = target.convert("RGB").resize(current_rgb.size)
    diff = ImageChops.difference(current_rgb, target_rgb)
    return Image.blend(current_rgb, ImageOps.colorize(
        ImageOps.grayscale(diff), "#FFFFFF", "#DC2626",
    ), 0.38)


def _side_by_side(
    target: Image.Image,
    rendered: dict[str, Image.Image],
) -> Image.Image:
    panels = [("TARGET", target)] + list(rendered.items())
    height = max(img.height for _label, img in panels)
    normalized: list[Image.Image] = []
    for _label, img in panels:
        scale = height / img.height
        normalized.append(img.resize((max(1, int(img.width * scale)), height)))
    width = sum(img.width for img in normalized)
    canvas = Image.new("RGB", (width, height), "white")
    x = 0
    for img in normalized:
        canvas.paste(img, (x, 0))
        x += img.width
    return canvas


def _black_density(image: Image.Image) -> float:
    arr = np.asarray(image.convert("RGB"))
    dark = (arr[:, :, 0] < 80) & (arr[:, :, 1] < 80) & (arr[:, :, 2] < 80)
    return float(dark.mean())


def _orange_density(image: Image.Image) -> float:
    arr = np.asarray(image.convert("RGB"))
    orange = (
        (arr[:, :, 0] > 180)
        & (arr[:, :, 1] > 80)
        & (arr[:, :, 1] < 190)
        & (arr[:, :, 2] < 90)
    )
    return float(orange.mean())


def _density_similarity_score(current: float, target: float, *, scale: float) -> float:
    return max(0.0, min(100.0, 100.0 - abs(current - target) * scale))


def _roof_facet_clarity_score(result, qa_report: dict[str, Any]) -> float:
    schedule = qa_report.get("roof_facet_schedule") or []
    facet_check = next(
        (
            item for item in qa_report.get("checks", [])
            if item.get("name") == "roof_facets_complete_enough_for_ahj"
        ),
        {},
    )
    if facet_check.get("status") != "PASS":
        return 72.0
    trace = result.inputs.site.ee4_trace
    roof_lines = len(trace.roof_lines) if trace.enabled else 0
    active_facets = sum(1 for row in schedule if row.get("pv") == "PV")
    score = 86.0 + min(8.0, roof_lines * 0.8) + min(6.0, active_facets * 2.0)
    return min(100.0, score)


def _annotation_score(qa_report: dict[str, Any]) -> float:
    warnings = qa_report.get("warning_checks") or []
    blockers = qa_report.get("blocking_checks") or []
    score = 94.0 - len(warnings) * 3.0 - len(blockers) * 12.0
    return max(50.0, min(100.0, score))


def _fire_path_score(result, rendered: dict[str, Image.Image]) -> float:
    if not result.inputs.site.ee4_trace.fire_pathways:
        return 75.0
    densities = [_orange_density(img) for img in rendered.values()]
    visible = max(densities) if densities else 0.0
    if visible >= 0.003:
        return 94.0
    if visible >= 0.001:
        return 86.0
    return 68.0


def _equipment_similarity_score(result) -> float:
    equipment = result.inputs.site.equipment_locations
    items = [
        equipment.msp,
        equipment.ac_disconnect,
    ]
    items.extend(equipment.inverters)
    items.extend(equipment.ess_units)
    present = [
        item for item in items
        if item is not None and item.x_ft is not None and item.y_ft is not None
    ]
    if len(present) >= 3:
        return 92.0
    if present:
        return 84.0
    return 72.0


def _passes_thresholds(metrics: dict[str, Any]) -> bool:
    if not metrics.get("qa_constraints_pass"):
        return False
    return all(
        float(metrics.get(key, 0.0)) >= threshold
        for key, threshold in BENCHMARK_THRESHOLDS.items()
    )


def _next_actions(metrics: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    if not metrics.get("qa_constraints_pass"):
        actions.append(
            "Fix panel-placement QA blockers before visual polish; current "
            "geometry cannot be AHJ-ready."
        )
    if float(metrics.get("roof_facet_clarity_score", 0)) < 90:
        actions.append(
            "Add or redraw CAD roof facets and ridge/hip/valley linework; "
            "avoid relying on colored fill as the primary face boundary."
        )
    if float(metrics.get("panel_layout_regularity_score", 0)) < 85:
        actions.append(
            "Re-pack modules into continuous rectangular rows/columns, or "
            "lower module count if fire/obstruction clearances make that impossible."
        )
    if float(metrics.get("annotation_cleanliness_score", 0)) < 90:
        actions.append(
            "Move QA labels and fire/equipment callouts outside the roof plan; "
            "roof interior should keep only linework, hatch, panels, obstruction "
            "symbols, and minimal F# tags."
        )
    if float(metrics.get("overall_score", 0)) < 85 and not actions:
        actions.append("Review overlay diff and tune sheet crop/linework density.")
    return actions


def _format_iteration_summary(summary: dict[str, Any]) -> str:
    lines = [
        "# Visual Iteration Summary",
        "",
        f"- Status: **{summary.get('status', 'UNKNOWN')}**",
        "",
        "| Round | Overall | Facets | Panels | Annotations | QA |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summary.get("rounds", []):
        metrics = item.get("metrics", {})
        lines.append(
            f"| {item.get('round')} | "
            f"{float(metrics.get('overall_score', 0)):.1f} | "
            f"{float(metrics.get('roof_facet_clarity_score', 0)):.1f} | "
            f"{float(metrics.get('panel_layout_regularity_score', 0)):.1f} | "
            f"{float(metrics.get('annotation_cleanliness_score', 0)):.1f} | "
            f"{'PASS' if metrics.get('qa_constraints_pass') else 'FAIL'} |"
        )
    actions = summary.get("next_actions") or []
    if actions:
        lines.extend(["", "## Blockers / Next Actions", ""])
        for action in actions:
            lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def _metric_num(value: Any) -> str:
    if value is None:
        return ""
    return f"{float(value):.1f}"
