"""R9.1 — roof facet clarity and F# schedule contracts."""
from __future__ import annotations

from pathlib import Path

from pvess_calc.calc.engine import run
from pvess_calc.permit.panel_placement_qa import (
    AHJ_REDO_MESSAGE,
    assess_panel_placement_qa,
    build_roof_facet_schedule,
)
from pvess_calc.schema import Inputs


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRISCO_MERGED = (
    PROJECT_ROOT
    / "projects"
    / "003-frisco-glasshouse-roof-merged"
    / "inputs.yaml"
)


def test_roof_facet_schedule_contains_f_tags_pv_status_and_modules():
    result = run(Inputs.from_yaml(FRISCO_MERGED))

    schedule = build_roof_facet_schedule(result)

    assert [(row["tag"], row["pv"], row["modules_assigned"]) for row in schedule] == [
        ("F1", "NO PV", 0),
        ("F2", "PV", 8),
        ("F3", "PV", 28),
    ]
    assert schedule[1]["azimuth_deg"] == 268.1
    assert schedule[2]["pitch_deg"] == 35.0


def test_roof_facet_under_modeling_emits_actionable_warning():
    inputs = Inputs.from_yaml(FRISCO_MERGED).model_copy(deep=True)
    inputs.site.ee4_trace.roof_facets = inputs.site.ee4_trace.roof_facets[:1]

    report = assess_panel_placement_qa(run(inputs))
    check = next(
        item for item in report["checks"]
        if item["name"] == "roof_facets_complete_enough_for_ahj"
    )

    assert check["status"] == "WARN"
    assert AHJ_REDO_MESSAGE in check["detail"]
