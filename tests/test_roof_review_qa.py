"""QA checks for CAD roof-review DXF files."""
from __future__ import annotations

from pathlib import Path

import ezdxf
import yaml
from click.testing import CliRunner

from pvess_calc.cli_root import pvess
from pvess_calc.roof_review.cad_layers import (
    PV_MODULE_ZONE,
    ROOF_FACET,
    ROOF_OBSTRUCTION,
    ROOF_OUTLINE,
    TEXT_ROOF_LABEL,
)
from pvess_calc.roof_review.dxf_import import import_reviewed_dxf
from pvess_calc.roof_review.qa import qa_reviewed_dxf
from tests.conftest import make_inputs


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "roof_review"


def _write_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    data = make_inputs(modules=8, strings=2).model_dump(mode="json")
    (project_dir / "inputs.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False),
        encoding="utf-8",
    )
    return project_dir


def test_roof_review_qa_reports_missing_required_facet_layer(tmp_path: Path):
    dxf_path = tmp_path / "missing-facet.dxf"
    doc = ezdxf.new("R2018", setup=True)
    doc.layers.add(ROOF_OUTLINE, color=1)
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(0, 0), (20, 0), (20, 10), (0, 10)],
        close=True,
        dxfattribs={"layer": ROOF_OUTLINE},
    )
    doc.saveas(dxf_path)

    qa = qa_reviewed_dxf(dxf_path)

    assert qa.status == "FAIL"
    assert any("ROOF_FACET" in issue.message for issue in qa.failures)


def test_roof_review_qa_accepts_simple_fixture():
    qa = qa_reviewed_dxf(FIXTURE_DIR / "simple_gable.dxf")

    assert qa.status in {"PASS", "WARN"}
    assert not qa.failures


def test_roof_import_cli_writes_yaml_and_preview(tmp_path: Path):
    project_dir = _write_project(tmp_path)
    fixture = FIXTURE_DIR / "simple_gable.dxf"

    result = CliRunner().invoke(
        pvess,
        ["roof-import", str(project_dir), str(fixture)],
    )

    assert result.exit_code == 0, result.output
    out_dir = project_dir / "output" / "roof-review"
    yaml_path = out_dir / "imported-roof.yaml"
    assert yaml_path.exists()
    assert (out_dir / "import-preview.png").exists()
    assert (out_dir / "roof-qa-report.md").exists()
    assert (out_dir / "roof-merge-preview.md").exists()
    assert (out_dir / "inputs.roof-merged.yaml").exists()
    assert (out_dir / "roof-import-validation.md").exists()
    assert import_reviewed_dxf(fixture).site.ee4_trace.enabled is True


def test_roof_review_qa_reports_pv_zone_conflicts_and_north_face(
    tmp_path: Path,
):
    dxf_path = tmp_path / "pv-zone-conflict.dxf"
    doc = ezdxf.new("R2018", setup=True)
    for layer in (
        ROOF_OUTLINE,
        ROOF_FACET,
        ROOF_OBSTRUCTION,
        PV_MODULE_ZONE,
        TEXT_ROOF_LABEL,
    ):
        doc.layers.add(layer)
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(0, 0), (40, 0), (40, 20), (0, 20)],
        close=True,
        dxfattribs={"layer": ROOF_OUTLINE},
    )
    msp.add_lwpolyline(
        [(0, 0), (40, 0), (40, 20), (0, 20)],
        close=True,
        dxfattribs={"layer": ROOF_FACET},
    )
    msp.add_text(
        "NAME=North Face PITCH=22 AZ=0",
        dxfattribs={"layer": TEXT_ROOF_LABEL, "height": 1.0},
    ).set_placement((20, 10))
    msp.add_lwpolyline(
        [(12, 8), (16, 8), (16, 12), (12, 12)],
        close=True,
        dxfattribs={"layer": ROOF_OBSTRUCTION},
    )
    msp.add_lwpolyline(
        [(10, 6), (22, 6), (22, 14), (10, 14)],
        close=True,
        dxfattribs={"layer": PV_MODULE_ZONE},
    )
    doc.saveas(dxf_path)

    qa = qa_reviewed_dxf(dxf_path)
    report = qa.as_markdown(dxf_path=dxf_path)

    assert qa.status == "FAIL"
    assert any("overlaps ROOF_OBSTRUCTION" in issue.message for issue in qa.failures)
    assert any("north-facing" in issue.message for issue in qa.warnings)
    assert "PV_MODULE_ZONE" in report


def test_roof_review_qa_fails_overlapping_roof_facets(tmp_path: Path):
    dxf_path = tmp_path / "overlapping-facets.dxf"
    doc = ezdxf.new("R2018", setup=True)
    for layer in (ROOF_OUTLINE, ROOF_FACET):
        doc.layers.add(layer)
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(0, 0), (40, 0), (40, 24), (0, 24)],
        close=True,
        dxfattribs={"layer": ROOF_OUTLINE},
    )
    msp.add_lwpolyline(
        [(0, 0), (24, 0), (24, 20), (0, 20)],
        close=True,
        dxfattribs={"layer": ROOF_FACET},
    )
    msp.add_lwpolyline(
        [(16, 0), (40, 0), (40, 20), (16, 20)],
        close=True,
        dxfattribs={"layer": ROOF_FACET},
    )
    doc.saveas(dxf_path)

    qa = qa_reviewed_dxf(dxf_path)

    assert qa.status == "FAIL"
    assert any("overlaps polyline" in issue.message for issue in qa.failures)
