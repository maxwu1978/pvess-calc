"""Stage C — EE-4 visual-density polish.

Locks the 5 layout adjustments that fix overlap + missing-data
signalling on the EE-4 page:

  1. Aerial inset radius bumped 25 m → 35 m (neighbour context)
  2. Rotated address pushed further from lot edge (0.30" → 0.50")
  3. PROPERTY LINE label moved top-left → bottom-right outside lot
  4. PV array caption relocated to bottom margin (was bb_y_bot - 0.16",
     which fell BELOW the lot frame for arrays on the south wall)
  5. "NOTE — Array shown schematically" warning strip when neither
     `routed` nor `has_face_anchors` is active (pure-legacy fallback)
"""
from __future__ import annotations

from pathlib import Path

import pypdf

from pvess_calc.calc.engine import run
from pvess_calc.permit.site_plan import render_site_plan
from pvess_calc.schema import (
    EquipmentLocation,
    EquipmentLocations,
    Inputs,
    RoofSection,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUSTIN = PROJECT_ROOT / "projects" / "001-demo-austin" / "inputs.yaml"
PHOENIX = PROJECT_ROOT / "projects" / "002-phoenix-25kw" / "inputs.yaml"
FRISCO = PROJECT_ROOT / "projects" / "003-frisco-glasshouse" / "inputs.yaml"


def _ee4_text(tmp_path: Path, inputs: Inputs) -> str:
    out = tmp_path / "ee4.pdf"
    render_site_plan(run(inputs), out)
    return "\n".join(p.extract_text() or ""
                     for p in pypdf.PdfReader(str(out)).pages)


# ─── #5 warning strip ────────────────────────────────────────────────────


def test_warning_strip_shows_when_no_roof_sections(tmp_path: Path):
    """Austin yaml has no roof_sections → legacy fallback path →
    NOTE strip must be visible. Stage D revised the wording from
    'Array shown schematically' to 'PV array geometry omitted' to
    match the K.13 contract (EE-4 no longer paints an abstract
    array; it omits one entirely)."""
    text = _ee4_text(tmp_path, Inputs.from_yaml(AUSTIN))
    assert "PV array geometry omitted" in text
    assert "site.roof_sections" in text


def test_no_warning_strip_when_anchors_present(tmp_path: Path):
    """Phoenix has roof_sections → Stage B auto-anchors → real
    per-face render → NO warning strip needed."""
    text = _ee4_text(tmp_path, Inputs.from_yaml(PHOENIX))
    assert "PV array geometry omitted" not in text


def test_no_warning_strip_when_fully_routed(tmp_path: Path):
    """Frisco has explicit anchors + equipment_locations → routed
    path → no warning."""
    text = _ee4_text(tmp_path, Inputs.from_yaml(FRISCO))
    assert "PV array geometry omitted" not in text


# ─── #3 property-line label position ────────────────────────────────────


def test_property_line_label_still_present(tmp_path: Path):
    """Label text unchanged; only its position moved."""
    text = _ee4_text(tmp_path, Inputs.from_yaml(FRISCO))
    assert "PROPERTY LINE" in text


# ─── #4 array caption no longer overlaps lot bottom ─────────────────────


def test_array_caption_present_in_bottom_margin(tmp_path: Path):
    """When routed/anchored, the PV ARRAY caption renders in the
    bottom-margin band between the lot frame and the scale bar."""
    text = _ee4_text(tmp_path, Inputs.from_yaml(PHOENIX))
    # Caption must appear (60 modules · 25.20 kW DC for Phoenix)
    assert "PV ARRAY" in text
    assert "MODULES" in text
    assert "25.20" in text


# ─── #1 aerial inset radius bumped to 35 m ──────────────────────────────


def test_aerial_inset_radius_is_35m():
    """Confirm the source code calls fetch_aerial_map_png with 35 m
    (not the legacy 25 m). Locked as a source-string check because
    the actual aerial fetch needs PVESS_GOOGLE_SOLAR_KEY env var."""
    src = (PROJECT_ROOT / "src" / "pvess_calc" / "permit"
           / "site_plan.py").read_text()
    assert "radius_m=35.0" in src
    # And the old 25 m default must not linger
    assert "radius_m=25.0" not in src


# ─── #2 rotated address pushed further from lot edge ────────────────────


def test_rotated_address_offset_is_0_50_inch():
    """Source-string check on the new offset (visual position is
    hard to assert from PDF text alone)."""
    src = (PROJECT_ROOT / "src" / "pvess_calc" / "permit"
           / "site_plan.py").read_text()
    assert "addr_x = lot_x - 0.50 * inch" in src
    assert "addr_x = lot_x - 0.30 * inch" not in src


# ─── End-to-end smoke check ─────────────────────────────────────────────


def test_all_three_projects_render_after_polish(tmp_path: Path):
    """Stage C polish must not crash any of the 3 sample projects."""
    for yaml_path in (AUSTIN, PHOENIX, FRISCO):
        out = tmp_path / f"ee4-{yaml_path.parent.name}.pdf"
        render_site_plan(run(Inputs.from_yaml(yaml_path)), out)
        assert out.stat().st_size > 2_000
