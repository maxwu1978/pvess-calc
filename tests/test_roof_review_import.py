"""CAD-reviewed roof DXF import tests."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pvess_calc.calc.engine import run
from pvess_calc.permit.site_plan import render_site_plan
from pvess_calc.permit.structural import render_attachment_plan
from pvess_calc.roof_review.dxf_import import import_reviewed_dxf
from pvess_calc.schema import Site
from tests.conftest import make_inputs


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "roof_review"


@pytest.mark.parametrize(
    "fixture_name,expected_faces",
    [
        ("simple_gable.dxf", 2),
        ("l_cross_gable.dxf", 3),
        ("hip_valley_obstruction.dxf", 4),
    ],
)
def test_roof_review_fixture_imports_to_schema(fixture_name: str, expected_faces: int):
    imported = import_reviewed_dxf(FIXTURE_DIR / fixture_name)

    assert imported.status in {"PASS", "WARN"}
    assert len(imported.site.roof_sections) == expected_faces
    assert imported.site.ee4_trace.enabled is True
    assert imported.site.ee4_trace.roof_outline is not None
    assert len(imported.site.ee4_trace.roof_facets) == expected_faces

    payload = yaml.safe_load(imported.yaml_text())
    assert Site.model_validate(payload["site"]).ee4_trace.enabled is True


def test_roof_review_import_maps_obstructions_to_roof_sections():
    imported = import_reviewed_dxf(FIXTURE_DIR / "hip_valley_obstruction.dxf")

    assert imported.site.ee4_trace.symbols
    assert sum(len(section.obstructions) for section in imported.site.roof_sections) == 1


def test_roof_review_import_parses_label_metadata_cleanly():
    imported = import_reviewed_dxf(FIXTURE_DIR / "simple_gable.dxf")

    assert imported.site.roof_sections[0].name == "South Gable"
    assert imported.site.roof_sections[0].pitch_deg == 24.0
    assert imported.site.roof_sections[0].azimuth_deg == 180.0
    assert imported.site.roof_sections[1].name == "North Gable"


def test_roof_review_import_parses_label_module_count(tmp_path: Path):
    import ezdxf
    from pvess_calc.roof_review.cad_layers import (
        ROOF_FACET,
        ROOF_OUTLINE,
        TEXT_ROOF_LABEL,
    )

    dxf_path = tmp_path / "modules-label.dxf"
    doc = ezdxf.new("R2018", setup=True)
    for layer in (ROOF_OUTLINE, ROOF_FACET, TEXT_ROOF_LABEL):
        doc.layers.add(layer)
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(0, 0), (30, 0), (30, 15), (0, 15)],
        close=True,
        dxfattribs={"layer": ROOF_OUTLINE},
    )
    msp.add_lwpolyline(
        [(0, 0), (30, 0), (30, 15), (0, 15)],
        close=True,
        dxfattribs={"layer": ROOF_FACET},
    )
    msp.add_text(
        "NAME=SW Face PITCH=22 AZ=225 MODULES=7",
        dxfattribs={"layer": TEXT_ROOF_LABEL, "height": 1},
    ).set_placement((15, 7))
    doc.saveas(dxf_path)

    imported = import_reviewed_dxf(dxf_path)

    assert imported.site.roof_sections[0].module_count == 7
    assert imported.site.roof_sections[0].azimuth_deg == 225.0


def test_roof_review_import_keeps_non_pv_context_facets_out_of_sections(
    tmp_path: Path,
):
    import ezdxf
    from pvess_calc.roof_review.cad_layers import (
        ROOF_FACET,
        ROOF_OUTLINE,
        TEXT_ROOF_LABEL,
    )

    dxf_path = tmp_path / "context-facet.dxf"
    doc = ezdxf.new("R2018", setup=True)
    for layer in (ROOF_OUTLINE, ROOF_FACET, TEXT_ROOF_LABEL):
        doc.layers.add(layer)
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(0, 0), (40, 0), (40, 20), (0, 20)],
        close=True,
        dxfattribs={"layer": ROOF_OUTLINE},
    )
    msp.add_lwpolyline(
        [(0, 0), (20, 0), (20, 20), (0, 20)],
        close=True,
        dxfattribs={"layer": ROOF_FACET},
    )
    msp.add_lwpolyline(
        [(20, 0), (40, 0), (40, 20), (20, 20)],
        close=True,
        dxfattribs={"layer": ROOF_FACET},
    )
    msp.add_text(
        "NAME=Non-PV Roof Context PV=NO",
        dxfattribs={"layer": TEXT_ROOF_LABEL, "height": 1},
    ).set_placement((10, 10))
    msp.add_text(
        "NAME=South PV Area PITCH=22 AZ=180 MODULES=4",
        dxfattribs={"layer": TEXT_ROOF_LABEL, "height": 1},
    ).set_placement((30, 10))
    doc.saveas(dxf_path)

    imported = import_reviewed_dxf(dxf_path)

    assert len(imported.site.ee4_trace.roof_facets) == 2
    assert [section.name for section in imported.site.roof_sections] == [
        "South PV Area",
    ]
    assert imported.site.roof_sections[0].module_count == 4


def test_imported_geometry_runs_calc_and_ee4_pv4_render_paths(tmp_path: Path):
    imported = import_reviewed_dxf(FIXTURE_DIR / "simple_gable.dxf")
    inputs = make_inputs(modules=8, strings=2).model_copy(
        update={"site": imported.site},
    )

    result = run(inputs)
    assert sum(len(mods) for mods in result.module_placements.values()) == 8

    ee4 = tmp_path / "ee4.pdf"
    pv4 = tmp_path / "pv4.pdf"
    render_site_plan(result, ee4)
    render_attachment_plan(result, pv4)
    assert ee4.stat().st_size > 1000
    assert pv4.stat().st_size > 1000
