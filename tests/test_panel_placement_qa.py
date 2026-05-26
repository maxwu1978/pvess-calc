"""R9.4 — formal panel-placement QA report."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from pvess_calc.calc.engine import run
from pvess_calc.permit.panel_placement_qa import (
    assess_panel_placement_qa,
    write_panel_placement_qa,
)
from pvess_calc.schema import Inputs


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRISCO_MERGED = (
    PROJECT_ROOT
    / "projects"
    / "003-frisco-glasshouse-roof-merged"
    / "inputs.yaml"
)


def test_panel_placement_qa_current_frisco_generates_36_of_36_pass(
    tmp_path: Path,
):
    result = run(Inputs.from_yaml(FRISCO_MERGED))

    artifacts = write_panel_placement_qa(result, tmp_path)
    report = artifacts["report"]

    assert report["status"] == "PASS"
    assert report["qa_constraints_pass"] is True
    assert report["placed_modules"] == 36
    assert report["target_modules"] == 36
    south_capacity = next(
        row for row in report["face_capacity"]
        if row["name"] == "South PV Area"
    )
    assert south_capacity["candidate_capacity"] == 42
    assert south_capacity["assigned_modules"] == 28
    assert south_capacity["unused_candidate_slots"] == 14
    assert south_capacity["eave_area_used"] is True
    assert artifacts["json"].exists()
    assert artifacts["markdown"].exists()
    assert "Panel Placement QA" in artifacts["markdown"].read_text()


def test_panel_selection_uses_south_eave_triangle_candidates():
    result = run(Inputs.from_yaml(FRISCO_MERGED))
    south_modules = result.module_placements["South PV Area"]

    assert {module.rotation_deg for module in south_modules} == {0.0}
    assert min(round(module.y_ft, 1) for module in south_modules) == 3.9
    assert any(
        round(module.x_ft, 1) <= 10.5
        and round(module.y_ft, 1) == 3.9
        and module.rotation_deg == 0
        for module in south_modules
    )


def test_panel_placement_qa_detects_panel_outside_assigned_face():
    result = run(Inputs.from_yaml(FRISCO_MERGED))
    face = "South PV Area"
    first = result.module_placements[face][0]
    result.module_placements[face][0] = replace(first, x_ft=-8.0)

    report = assess_panel_placement_qa(result)
    check = _check(report, "module_inside_assigned_face")

    assert report["qa_constraints_pass"] is False
    assert check["status"] == "FAIL"
    assert "outside assigned roof face" in check["detail"]


def test_panel_placement_qa_detects_obstruction_halo_conflict():
    result = run(Inputs.from_yaml(FRISCO_MERGED))
    face = "West PV Area"
    first = result.module_placements[face][0]
    result.module_placements[face][0] = replace(
        first,
        x_ft=8.0,
        y_ft=11.2,
    )

    report = assess_panel_placement_qa(result)
    check = _check(report, "module_clear_obstruction_halo")

    assert report["qa_constraints_pass"] is False
    assert check["status"] == "FAIL"
    assert "obstruction halo" in check["detail"]


def _check(report: dict, name: str) -> dict:
    return next(item for item in report["checks"] if item["name"] == name)
