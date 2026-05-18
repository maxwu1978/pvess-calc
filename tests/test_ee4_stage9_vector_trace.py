"""Stage 9 — EE-4 vector-traced roof plan layer."""
from __future__ import annotations

from pathlib import Path
import shutil

import pypdf
import pytest
import yaml
from click.testing import CliRunner

from pvess_calc.calc.engine import run
from pvess_calc.cli_root import pvess
from pvess_calc.permit.ee4_lint import lint_ee4_preview
from pvess_calc.permit.ee4_review import render_ee4_review
from pvess_calc.permit.ee4_trace import build_ee4_trace_skeleton, ee4_trace_yaml
from pvess_calc.permit.site_plan import _ee4_drawing_bounds, render_site_plan
from pvess_calc.schema import EE4Trace, EE4TracePolygon, Inputs


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRISCO = PROJECT_ROOT / "projects" / "003-frisco-glasshouse" / "inputs.yaml"
FRISCO_PROJECT = FRISCO.parent


def _ee4_text(tmp_path: Path, inputs: Inputs) -> str:
    out = tmp_path / "ee4.pdf"
    render_site_plan(run(inputs), out)
    return "\n".join(p.extract_text() or ""
                     for p in pypdf.PdfReader(str(out)).pages)


def test_frisco_stage9_trace_schema_loads():
    inputs = Inputs.from_yaml(FRISCO)
    trace = inputs.site.ee4_trace
    assert trace.enabled is True
    assert trace.roof_outline is not None
    assert len(trace.roof_outline.vertices) >= 12
    assert trace.fire_pathways
    assert trace.roof_lines


def test_stage9_trace_polygon_rejects_self_intersecting():
    with pytest.raises(ValueError, match="self-intersects"):
        EE4TracePolygon(
            name="bad bowtie",
            vertices=[
                (0.0, 0.0), (10.0, 10.0),
                (10.0, 0.0), (0.0, 10.0),
            ],
        )


def test_stage9_trace_extents_drive_ee4_drawing_bounds():
    result = run(Inputs.from_yaml(FRISCO))
    bounds = _ee4_drawing_bounds(result)
    assert bounds is not None
    min_x, _min_y, max_x, _max_y = bounds
    assert min_x <= 0.0
    assert max_x >= 98.0


def test_stage91_frisco_reference_like_array_and_equipment_positions():
    """Stage 9.1 polish: Frisco should read as left small array +
    right main array with equipment on the right edge, matching the
    permit-reference composition."""
    from pvess_calc.calc.wire_routing import _face_local_to_site

    result = run(Inputs.from_yaml(FRISCO))
    centers: list[tuple[float, float]] = []
    for section in result.inputs.site.roof_sections:
        for module in result.module_placements.get(section.name, []):
            pt = _face_local_to_site(
                section,
                module.x_ft + module.width_ft / 2,
                module.y_ft + module.height_ft / 2,
            )
            if pt is not None:
                centers.append(pt)

    assert len(centers) == result.inputs.pv_array.modules
    assert sum(1 for x, _y in centers if x >= 50.0) >= 25
    assert result.inputs.site.equipment_locations.msp.x_ft >= 90.0


def test_stage9_default_render_is_pure_vector_not_satellite(
    monkeypatch, tmp_path: Path,
):
    from pvess_calc.permit import cover_maps

    def _fail(*args, **kwargs):
        raise AssertionError("Stage 9 default render should not fetch aerial")

    monkeypatch.delenv("PVESS_EE4_SATELLITE", raising=False)
    monkeypatch.delenv("PVESS_ALLOW_PAID_RENDERS", raising=False)
    monkeypatch.setattr(cover_maps, "fetch_aerial_map_png", _fail)
    monkeypatch.setattr(cover_maps, "fetch_satellite_assets_cached", _fail)

    text = _ee4_text(tmp_path, Inputs.from_yaml(FRISCO))
    assert "SATELLITE UNDERLAY" not in text
    assert "MASK CONTOUR CANDIDATE" not in text
    assert "FIRE OFFSET" in text
    assert "PV ARRAY" in text


def test_stage92_trace_skeleton_generation_outputs_paste_ready_yaml():
    result = run(Inputs.from_yaml(FRISCO))
    trace = build_ee4_trace_skeleton(result)
    assert trace.enabled is True
    assert trace.roof_outline is not None
    assert trace.roof_facets
    assert trace.roof_lines
    assert trace.fire_pathways

    text = ee4_trace_yaml(trace)
    payload = yaml.safe_load(text)
    parsed = EE4Trace.model_validate(payload["site"]["ee4_trace"])
    assert parsed.enabled is True
    assert parsed.roof_outline is not None


def test_stage92_cli_writes_trace_skeleton(tmp_path: Path):
    project_dir = tmp_path / "frisco"
    shutil.copytree(FRISCO_PROJECT, project_dir)
    out = tmp_path / "ee4-trace.yaml"

    result = CliRunner().invoke(pvess, [
        "ee4-trace", str(project_dir), "--output", str(out),
    ])
    assert result.exit_code == 0, result.output
    assert out.exists()
    payload = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert EE4Trace.model_validate(payload["site"]["ee4_trace"]).enabled
    assert "paste the `site.ee4_trace` block" in result.output


def test_stage92_doctor_trace_completeness_passes_for_frisco():
    from pvess_calc.doctor import _check_ee4_trace_ready_for_review

    result = run(Inputs.from_yaml(FRISCO))
    [check] = _check_ee4_trace_ready_for_review(result)
    assert check.status == "PASS", check.detail


def test_stage92_doctor_warns_on_enabled_but_empty_trace():
    from pvess_calc.doctor import _check_ee4_trace_ready_for_review

    inputs = Inputs.from_yaml(FRISCO)
    inputs.site.ee4_trace = EE4Trace(enabled=True)
    [check] = _check_ee4_trace_ready_for_review(run(inputs))
    assert check.status == "WARN"
    assert "pvess ee4-trace" in check.detail


def test_stage93_render_ee4_review_writes_single_page_pdf(tmp_path: Path):
    result = run(Inputs.from_yaml(FRISCO))
    pdf_path = tmp_path / "ee4-preview.pdf"
    artifacts = render_ee4_review(result, pdf_path, png_path=None)
    assert artifacts.pdf_path == pdf_path
    assert artifacts.png_path is None
    assert pdf_path.stat().st_size > 5_000
    reader = pypdf.PdfReader(str(pdf_path))
    assert len(reader.pages) == 1
    assert "SITE PLAN" in (reader.pages[0].extract_text() or "")


def test_stage93_cli_writes_ee4_preview_pdf_without_png_dependency(
    tmp_path: Path,
):
    project_dir = tmp_path / "frisco"
    shutil.copytree(FRISCO_PROJECT, project_dir)
    pdf_path = tmp_path / "ee4-preview.pdf"
    png_path = tmp_path / "ee4-preview.png"

    result = CliRunner().invoke(pvess, [
        "ee4-preview", str(project_dir),
        "--pdf-output", str(pdf_path),
        "--png-output", str(png_path),
        "--no-png",
    ])
    assert result.exit_code == 0, result.output
    assert "trace-check: PASS" in result.output
    assert "visual-lint: PASS" in result.output
    assert pdf_path.stat().st_size > 5_000
    assert not png_path.exists()


def test_stage94_visual_lint_passes_for_frisco_trace():
    results = lint_ee4_preview(run(Inputs.from_yaml(FRISCO)))
    assert results
    assert all(r.status == "PASS" for r in results), results


def test_stage94_visual_lint_warns_when_modules_leave_roof_outline():
    inputs = Inputs.from_yaml(FRISCO)
    inputs.site.ee4_trace.roof_outline = EE4TracePolygon(
        name="too small",
        vertices=[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)],
    )
    results = lint_ee4_preview(run(inputs))
    by_name = {r.name: r for r in results}
    assert by_name["ee4_modules_inside_trace_roof"].status == "WARN"


def test_stage96_visual_lint_warns_when_module_corner_leaves_roof_outline():
    inputs = Inputs.from_yaml(FRISCO)
    for section in inputs.site.roof_sections:
        if section.name == "South Roof #3":
            section.module_count = 2
            section.site_anchor_x_ft = 83.0
            section.site_anchor_y_ft = 31.0

    results = lint_ee4_preview(run(inputs))
    by_name = {r.name: r for r in results}
    check = by_name["ee4_modules_inside_trace_roof"]
    assert check.status == "WARN"
    assert "rectangle" in check.detail


def test_stage96_visual_lint_warns_on_module_rectangle_overlap():
    inputs = Inputs.from_yaml(FRISCO)
    for section in inputs.site.roof_sections:
        if section.name == "South Roof #2":
            section.site_anchor_x_ft = 67.0
    results = lint_ee4_preview(run(inputs))
    by_name = {r.name: r for r in results}
    assert by_name["ee4_module_rectangles_no_overlap"].status == "WARN"


def test_stage96_visual_lint_warns_on_module_fire_pathway_overlap():
    inputs = Inputs.from_yaml(FRISCO)
    inputs.site.ee4_trace.fire_pathways = [
        EE4TracePolygon(
            name="bad module overlap",
            vertices=[
                (50.0, 40.0), (84.0, 40.0),
                (84.0, 58.0), (50.0, 58.0),
            ],
        )
    ]
    results = lint_ee4_preview(run(inputs))
    by_name = {r.name: r for r in results}
    assert by_name["ee4_module_rectangles_clear_fire_pathway"].status == "WARN"


def test_stage94_doctor_visual_lint_passes_for_frisco():
    from pvess_calc.doctor import _check_ee4_preview_visual_lint

    [check] = _check_ee4_preview_visual_lint(run(Inputs.from_yaml(FRISCO)))
    assert check.status == "PASS", check.detail


def test_stage95_equipment_leader_labels_are_concise():
    from pvess_calc.permit.site_plan import _ee4_equipment_leader_label

    assert _ee4_equipment_leader_label("INV-1 - MEGAREVO R11KLNA") == "INVERTER #1"
    assert _ee4_equipment_leader_label("MSP") == "MAIN SERVICE PANEL"
    assert _ee4_equipment_leader_label("AC DISCONNECT") == "AC DISCONNECT"
