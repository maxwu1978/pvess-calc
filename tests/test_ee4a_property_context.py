"""Stage 9.8 — EE-4A property context plan."""
from __future__ import annotations

from pathlib import Path

import pypdf
import pytest
from pydantic import ValidationError

from pvess_calc.calc.engine import run
from pvess_calc.permit.property_context import render_property_context_plan
from pvess_calc.permit.sheet_registry import by_code
from pvess_calc.schema import Inputs, PropertyContext


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRISCO = PROJECT_ROOT / "projects" / "003-frisco-glasshouse" / "inputs.yaml"


def _pdf_text(path: Path) -> str:
    return "\n".join(p.extract_text() or ""
                     for p in pypdf.PdfReader(str(path)).pages)


def test_stage98_registry_contains_property_context_sheet():
    spec = by_code("ee-4a")
    assert spec.display_code == "EE-4A"
    assert spec.renderer.endswith("property_context:render_property_context_plan")


def test_stage98_property_context_plan_renders_reference_labels(tmp_path: Path):
    out = tmp_path / "ee-4a-property-context.pdf"
    render_property_context_plan(run(Inputs.from_yaml(FRISCO)), out)

    assert out.stat().st_size > 4_000
    text = _pdf_text(out)
    assert "PROPERTY LINE" in text
    assert "DRIVEWAY" in text
    assert "FENCE" in text
    assert "MAIN HOUSE" in text
    assert "EE-4A" in text


def test_stage99_frisco_property_context_is_data_driven():
    pc = Inputs.from_yaml(FRISCO).site.property_context

    assert pc.has_data
    assert len(pc.lot_outline) == 4
    assert len(pc.driveway_polygon) == 4
    assert pc.fence_lines[0].label == "FENCE"
    assert len(pc.property_dimensions) == 2


def test_stage99_property_context_rejects_bad_lot_polygon():
    with pytest.raises(ValidationError, match="lot_outline self-intersects"):
        PropertyContext(
            lot_outline=[(0, 0), (10, 10), (0, 10), (10, 0)]
        )


def test_stage99_property_context_plan_renders_survey_dimensions(tmp_path: Path):
    out = tmp_path / "ee-4a-property-context.pdf"
    render_property_context_plan(run(Inputs.from_yaml(FRISCO)), out)

    text = _pdf_text(out)
    assert "113'" in text
    assert "66'" in text
