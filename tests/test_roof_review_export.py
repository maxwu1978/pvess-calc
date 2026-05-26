"""CAD roof-review package export tests."""
from __future__ import annotations

from pathlib import Path

import ezdxf
import json
import yaml
from click.testing import CliRunner
from PIL import Image

from pvess_calc.calc.engine import run
from pvess_calc.cli_root import pvess
from pvess_calc.roof_review.candidates import build_roof_line_candidates
from pvess_calc.roof_review.dxf_export import render_roof_review_dxf
from pvess_calc.roof_review.build import build_roof_review_package
from pvess_calc.roof_review.cad_layers import (
    REFERENCE_EXCLUSION,
    REFERENCE_FACE_PRIORITY,
    ROOF_FACET,
    ROOF_OUTLINE,
)
from tests.conftest import make_inputs


def _write_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    inputs = make_inputs(modules=8, strings=2)
    data = inputs.model_dump(mode="json")
    data["project"]["id"] = "roof-review-test"
    data["project"]["name"] = "Roof Review Test"
    (project_dir / "inputs.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False),
        encoding="utf-8",
    )
    return project_dir


def test_roof_review_builds_blank_package_without_google_key(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("PVESS_GOOGLE_SOLAR_KEY", raising=False)
    project_dir = _write_project(tmp_path)

    artifacts = build_roof_review_package(project_dir)

    assert artifacts["review_dxf"].exists()
    assert artifacts["underlay"].exists()
    assert artifacts["candidate_json"].exists()
    assert artifacts["audit_markdown"].exists()
    audit = artifacts["audit_markdown"].read_text(encoding="utf-8")
    assert "roof-line-candidates.json" in audit
    assert "method:" in audit

    doc = ezdxf.readfile(str(artifacts["review_dxf"]))
    layer_names = {layer.dxf.name for layer in doc.layers}
    assert ROOF_OUTLINE in layer_names
    assert ROOF_FACET in layer_names


def test_roof_review_cli_writes_package_without_api_keys(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("PVESS_GOOGLE_SOLAR_KEY", raising=False)
    project_dir = _write_project(tmp_path)

    result = CliRunner().invoke(pvess, ["roof-review", str(project_dir)])

    assert result.exit_code == 0, result.output
    assert (project_dir / "output" / "roof-review" / "roof-review.dxf").exists()
    assert "roof-import" in result.output


def test_roof_review_dxf_can_embed_satellite_underlay_image(tmp_path: Path):
    image_path = tmp_path / "underlay.png"
    Image.new("RGB", (120, 80), (80, 120, 150)).save(image_path)
    out = tmp_path / "roof-review.dxf"

    render_roof_review_dxf(
        run(make_inputs(modules=8, strings=2)),
        out,
        underlay_image_path=image_path,
        underlay_placement={
            "insert_ft": [10.0, 20.0],
            "size_ft": [30.0, 18.0],
        },
    )

    doc = ezdxf.readfile(str(out))
    images = list(doc.modelspace().query("IMAGE"))
    assert len(images) == 1
    assert images[0].dxf.layer == "REFERENCE_UNDERLAY"


def test_roof_review_generates_reference_line_candidates(tmp_path: Path):
    candidate_json = tmp_path / "candidate.json"
    candidate_json.write_text(
        json.dumps({
            "status": "PASS",
            "candidate": {
                "vertices_ft": [
                    [0, 0], [50, 0], [60, 18], [45, 35],
                    [8, 35], [-8, 18],
                ]
            },
        }),
        encoding="utf-8",
    )
    line_json = tmp_path / "line-candidates.json"

    payload = build_roof_line_candidates(candidate_json, line_json)

    assert payload["status"] == "PASS"
    assert 4 <= len(payload["lines"]) <= 16

    out = tmp_path / "roof-review-lines.dxf"
    render_roof_review_dxf(
        run(make_inputs(modules=8, strings=2)),
        out,
        roof_line_candidates=payload,
    )
    doc = ezdxf.readfile(str(out))
    ref_entities = [
        e for e in doc.modelspace()
        if e.dxf.layer == "REFERENCE_CANDIDATE"
    ]
    assert len(ref_entities) >= len(payload["lines"])
    text_values = [e.dxf.text for e in doc.modelspace().query("TEXT")]
    assert not any(text.startswith("C1 ") for text in text_values)


def test_roof_review_line_candidates_use_underlay_edges_when_available(
    tmp_path: Path,
):
    candidate_json = tmp_path / "candidate.json"
    candidate_json.write_text(
        json.dumps({
            "status": "PASS",
            "candidate": {
                "vertices_ft": [
                    [10, 10], [90, 10], [90, 60], [10, 60],
                ]
            },
        }),
        encoding="utf-8",
    )
    underlay = tmp_path / "underlay.png"
    img = Image.new("RGB", (240, 160), (160, 170, 150))
    px = img.load()
    for x in range(40, 205):
        for dy in range(-1, 2):
            px[x, 80 + dy] = (50, 55, 45)
    for i in range(0, 70):
        for dy in range(-1, 2):
            px[55 + i, 118 - i // 2 + dy] = (45, 50, 40)
            px[190 - i, 118 - i // 2 + dy] = (45, 50, 40)
    img.save(underlay)
    output = tmp_path / "line-candidates.json"

    payload = build_roof_line_candidates(
        candidate_json,
        output,
        underlay_path=underlay,
        underlay_placement={
            "insert_ft": [0.0, 0.0],
            "size_ft": [100.0, 70.0],
        },
    )

    assert payload["source"] == "satellite_rgb_edges+mask"
    assert payload["method"] == "satellite_rgb_edge_hough"
    assert payload["image_candidate_count"] >= 3
    assert any(
        line["source"] == "satellite_rgb_edges"
        and line.get("evidence_score", 0) > 0
        for line in payload["lines"]
    )


def test_roof_review_dxf_marks_face_priority_and_no_panel_zones(tmp_path: Path):
    out = tmp_path / "roof-review-guidance.dxf"

    render_roof_review_dxf(
        run(make_inputs(modules=8, strings=2)),
        out,
        face_priorities=[
            {
                "index": 1,
                "name": "SW Face",
                "azimuth_deg": 225.0,
                "pitch_deg": 30.0,
                "priority": {
                    "label": "P1 Southwest target",
                    "dxf_color": 3,
                },
            },
            {
                "index": 2,
                "name": "North Face",
                "azimuth_deg": 0.0,
                "pitch_deg": 30.0,
                "priority": {
                    "label": "P5 North avoid",
                    "dxf_color": 1,
                },
            },
        ],
        obstruction_zones=[
            {
                "kind": "chimney",
                "x_ft": 22.0,
                "y_ft": 18.0,
                "radius_ft": 4.0,
            }
        ],
    )

    doc = ezdxf.readfile(str(out))
    msp = doc.modelspace()
    assert any(e.dxf.layer == REFERENCE_FACE_PRIORITY for e in msp)
    assert any(e.dxf.layer == REFERENCE_EXCLUSION for e in msp)
    text_values = [e.dxf.text for e in msp.query("TEXT")]
    assert any("SW first" in text for text in text_values)
    assert any("ROOF_OBSTRUCTION" in text for text in text_values)
