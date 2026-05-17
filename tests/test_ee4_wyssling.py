"""K.11.7f — EE-4 Wyssling-style polish visual contract.

Locks the 6 layer-level upgrades that close the gap between the
legacy painted-rectangle EE-4 and the industry-standard residential
PV site plan (7652 Glasshouse Walk reference, 2026-05-17):

  A — Optional `Site.house_outline_vertices` polygon (L/T/irregular)
  B — Real K.9.1 modules at site-plan scale (single light-blue outline)
  C — Fire-offset hatch band + "FIRE OFFSET (NEC 690.12)" label
  D — Equipment leader-line callouts (already locked separately)
  E — Rotated address along property side (90° CCW)
  F — Optimizer annotation when inputs.optimizer is set

Backwards-compat path stays untested-here-but-tested-globally — the
existing 576 tests cover legacy yamls (Austin / Phoenix without
equipment_locations).
"""
from __future__ import annotations

from pathlib import Path

import pypdf
import pytest

from pvess_calc.calc.engine import run
from pvess_calc.permit.site_plan import render_site_plan
from pvess_calc.schema import (
    EquipmentLocation,
    EquipmentLocations,
    Inputs,
    Optimizer,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHOENIX = PROJECT_ROOT / "projects" / "002-phoenix-25kw" / "inputs.yaml"


def _phoenix_routed_inputs() -> Inputs:
    """Phoenix yaml + full K.11 equipment_locations + site_anchors."""
    inputs = Inputs.from_yaml(PHOENIX).model_copy(deep=True)
    for section in inputs.site.roof_sections:
        section.site_anchor_x_ft = 16.0
        section.site_anchor_y_ft = 45.0
        section.site_anchor_azimuth_deg = 0.0
    inputs.site.equipment_locations = EquipmentLocations(
        msp=EquipmentLocation(label="MAIN SERVICE PANEL", x_ft=55, y_ft=43),
        ac_disconnect=EquipmentLocation(label="AC DISCONNECT",
                                        x_ft=52, y_ft=43),
        inverters=[EquipmentLocation(label="INVERTER #1",
                                     x_ft=48, y_ft=43)],
        sub_panels=[EquipmentLocation(label="SUB PANEL #1",
                                      x_ft=44, y_ft=43)],
        ess_units=[EquipmentLocation(label="ESS #1",
                                     x_ft=40, y_ft=43)],
        attic_drop_x_ft=48.0, attic_drop_y_ft=44.0,
    )
    return inputs


def _ee4_text(tmp_path: Path, inputs: Inputs) -> str:
    out = tmp_path / "ee4.pdf"
    render_site_plan(run(inputs), out)
    return "\n".join(p.extract_text() or ""
                     for p in pypdf.PdfReader(str(out)).pages)


# ─── A — house polygon outline ─────────────────────────────────────


def test_house_outline_polygon_renders(tmp_path: Path):
    """L-shaped house polygon validates + renders without crashing.
    The output is necessarily byte-different from the rect fallback
    because the underlying SVG path is different."""
    inputs = _phoenix_routed_inputs()
    # L-shape: 50' × 35' bounding box with a 20' × 15' notch in the
    # bottom-right corner. Polygon must be CCW + simple.
    inputs.site.house_outline_vertices = [
        (15.0, 42.5), (65.0, 42.5),
        (65.0, 57.5), (45.0, 57.5),
        (45.0, 77.5), (15.0, 77.5),
    ]
    text = _ee4_text(tmp_path, inputs)
    # Just verify the title strip is still rendered (no crash + no
    # rendering-pipeline corruption from the new polygon path)
    assert "EE-4 · SITE PLAN" in text


def test_house_outline_polygon_validator_rejects_self_intersecting():
    """Bow-tie polygon must FAIL validation, mirroring the K.2.7
    RoofSection polygon rule. Validator only fires on construction,
    so we need a fresh Site instance — mutating an existing one
    silently passes."""
    from pydantic import ValidationError
    from pvess_calc.schema import Site
    with pytest.raises(ValidationError, match="self-intersect"):
        Site(house_outline_vertices=[
            (0.0, 0.0), (10.0, 10.0), (10.0, 0.0), (0.0, 10.0),
        ])


# ─── B — real modules at site-plan scale ───────────────────────────


def test_real_modules_drawn_in_routed_mode(tmp_path: Path):
    """When `routed=True` the EE-4 renderer draws real K.9.1 modules
    at site coordinates (not the abstract 10×6 fallback grid). The
    legacy "10×6 grid" caption should NOT appear in routed mode."""
    inputs = _phoenix_routed_inputs()
    text = _ee4_text(tmp_path, inputs)
    # Routed mode should NOT print the abstract-grid caption
    assert "10×6 grid" not in text
    # And SHOULD print the real-modules caption
    assert "60 MODULES" in text
    assert "25.20" in text   # kW DC


def test_legacy_yaml_keeps_abstract_grid(tmp_path: Path):
    """Pre-K.11 yaml without equipment_locations stays on the
    legacy abstract-grid path (zero visual regression)."""
    inputs = Inputs.from_yaml(PHOENIX)
    text = _ee4_text(tmp_path, inputs)
    # Legacy mode: abstract-grid caption is present
    assert "10×6 grid" in text or "grid" in text.lower()


# ─── C — fire-offset hatch + label ─────────────────────────────────


def test_fire_offset_label_appears_in_routed_mode(tmp_path: Path):
    """When routing is active AND roof_sections have site_anchor, the
    EE-4 renderer hatches the band between section outline and module
    bbox + emits a "FIRE OFFSET" caption with NEC 690.12 reference."""
    inputs = _phoenix_routed_inputs()
    text = _ee4_text(tmp_path, inputs)
    assert "FIRE OFFSET" in text
    assert "NEC 690.12" in text


# ─── D — equipment leader-line callouts ────────────────────────────


def test_equipment_labels_use_ne_convention(tmp_path: Path):
    """K.11.7 — each equipment label uses (N) / (E) convention,
    uppercase, with the equipment label in human-readable form
    (not the SLD short code like INV-1)."""
    inputs = _phoenix_routed_inputs()
    text = _ee4_text(tmp_path, inputs)
    assert "(N) MAIN SERVICE PANEL" in text
    assert "(N) INVERTER #1" in text
    assert "(N) SUB PANEL #1" in text
    assert "(N) ESS #1" in text


# ─── E — rotated address ───────────────────────────────────────────


def test_rotated_address_along_property_side(tmp_path: Path):
    """K.11.7f — the project's site_address renders BOTH centered
    under the title strip AND as a rotated label along the lot's
    left property line. pypdf flattens rotation, so we just verify
    the address text appears in the extracted text — the rotation
    itself is a visual-spec implementation detail."""
    inputs = _phoenix_routed_inputs().model_copy(deep=True)
    inputs.project.site_address = "1234 Camelback Rd, Phoenix, AZ 85016"
    text = _ee4_text(tmp_path, inputs)
    # Uppercase variant (the renderer uppercases the address)
    assert "CAMELBACK RD" in text.upper()


# ─── F — optimizer annotation ──────────────────────────────────────


def test_optimizer_annotation_when_optimizer_configured(tmp_path: Path):
    """K.11.7f — when inputs.optimizer.brand is non-empty, EE-4 draws
    a leader line from one module out to a "(N) PV MODULE EQUIPPED W/
    (N) OPTIMIZER PER (N) MODULES" caption."""
    inputs = _phoenix_routed_inputs().model_copy(deep=True)
    inputs.optimizer = Optimizer(
        brand="Tigo", model="TS4-A-O",
        type="pass_through", count="per_module",
    )
    text = _ee4_text(tmp_path, inputs)
    assert "PV MODULE EQUIPPED" in text
    assert "OPTIMIZER" in text


def test_no_optimizer_annotation_when_optimizer_empty(tmp_path: Path):
    """When inputs.optimizer.brand is empty, EE-4 skips the annotation
    (the legacy clean look stays for projects without optimizers).
    Phoenix yaml has optimizer_ref preset, so we explicitly clear
    brand to test the empty-optimizer path."""
    inputs = _phoenix_routed_inputs().model_copy(deep=True)
    inputs.optimizer = Optimizer()    # default brand=""
    text = _ee4_text(tmp_path, inputs)
    assert "PV MODULE EQUIPPED" not in text
