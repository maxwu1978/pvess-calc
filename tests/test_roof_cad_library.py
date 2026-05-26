"""Permit roof-plan CAD symbol library contracts."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from pvess_calc.permit.roof_cad_library import (
    ROOF_CAD_SYMBOL_KINDS,
    draw_fire_pathway,
    draw_keepout_area,
    draw_pv_module,
    draw_roof_symbol,
)


def test_roof_cad_library_contains_required_plan_symbols():
    assert {
        "roof_vent",
        "plumbing",
        "ac",
        "satellite",
        "mast",
        "chimney",
        "fire",
        "no_panel",
    }.issubset(set(ROOF_CAD_SYMBOL_KINDS))


def test_roof_cad_library_draws_vector_primitives(tmp_path: Path):
    out = tmp_path / "roof-cad-library.pdf"
    c = canvas.Canvas(str(out), pagesize=letter)

    draw_fire_pathway(c, [(40, 650), (220, 650), (220, 690), (40, 690)])
    draw_keepout_area(c, [(40, 590), (120, 590), (120, 635), (40, 635)])
    draw_pv_module(c, [(150, 590), (205, 590), (205, 635), (150, 635)])
    for idx, kind in enumerate(ROOF_CAD_SYMBOL_KINDS[:6]):
        draw_roof_symbol(c, 55 + idx * 32, 545, kind, size=10)

    c.save()

    assert out.exists()
    assert out.stat().st_size > 1_500
