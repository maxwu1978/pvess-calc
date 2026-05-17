"""K.2.6c — roof usable-area engine unit tests.

Locks the math contracts:
  * Rectangle inset: exact subtraction per edge.
  * Triangle inset: inradius-shrink formula.
  * Obstruction subtraction: AABB w/ halo, capped at usable polygon.
  * Module-fit check: 22 sqft/module + spacing overhead.
  * Backward compat: legacy yaml (no obstructions, no shape) behaves
    identically to the rectangle path with default 1.5 ft setbacks.
"""
from __future__ import annotations

import math

import pytest

from pvess_calc.calc.engine import run
from pvess_calc.calc.roof_layout import (
    MODULE_FOOTPRINT_SQFT,
    compute_roof_layout,
)
from pvess_calc.schema import (
    EdgeSetback,
    Inputs,
    RoofObstruction,
    RoofSection,
    Site,
)
from tests.conftest import make_inputs


def _with_roof(inputs: Inputs, *roof_sections: RoofSection) -> Inputs:
    """Helper: drop the roof_sections list onto a make_inputs() Inputs."""
    inputs.site = Site(
        roof_pitch_deg=22.0,
        array_azimuth_deg=180.0,
        roof_sections=list(roof_sections),
    )
    return inputs


# ─── Rectangle math ────────────────────────────────────────────────────


def test_rect_default_setback_shrinks_by_1p5_ft_on_each_edge():
    """24 × 16 ft rectangle with default 1.5 ft setbacks:
       usable = (24 - 2×1.5) × (16 - 2×1.5) = 21 × 13 = 273 sqft
       gross = 384 sqft; setback loss = 111 sqft.
    """
    inputs = make_inputs()
    _with_roof(inputs, RoofSection(
        name="South", shape="rect", width_ft=24, height_ft=16,
        module_count=0,
    ))
    [s] = compute_roof_layout(inputs).sections
    assert s.gross_area_sqft == pytest.approx(384.0)
    assert s.usable_area_sqft == pytest.approx(273.0)
    assert s.setback_loss_sqft == pytest.approx(111.0)


def test_rect_explicit_per_edge_setbacks():
    """Override per-edge setbacks individually."""
    inputs = make_inputs()
    _with_roof(inputs, RoofSection(
        name="South", shape="rect", width_ft=30, height_ft=20,
        edge_setbacks=[
            EdgeSetback(edge_type="eave",  setback_ft=3.0),
            EdgeSetback(edge_type="ridge", setback_ft=1.5),
            EdgeSetback(edge_type="rake",  setback_ft=2.0),
        ],
    ))
    [s] = compute_roof_layout(inputs).sections
    # usable_w = 30 - 2×2 = 26;  usable_h = 20 - 3 - 1.5 = 15.5
    assert s.usable_area_sqft == pytest.approx(26 * 15.5)


def test_rect_oversize_setbacks_consume_entire_face():
    """If setbacks > face dimensions → usable_area = 0 (no negative)."""
    inputs = make_inputs()
    _with_roof(inputs, RoofSection(
        name="Tiny", shape="rect", width_ft=4, height_ft=4,
        default_setback_ft=3.0,
    ))
    [s] = compute_roof_layout(inputs).sections
    assert s.usable_area_sqft == 0.0


# ─── Triangle math ─────────────────────────────────────────────────────


def test_tri_gross_area_is_half_base_times_height():
    inputs = make_inputs()
    _with_roof(inputs, RoofSection(
        name="Hip", shape="tri", width_ft=20, height_ft=10,
    ))
    [s] = compute_roof_layout(inputs).sections
    assert s.gross_area_sqft == pytest.approx(0.5 * 20 * 10)


def test_tri_inradius_shrink_isosceles_24x16_at_1p5_setback():
    """Isosceles tri base=24, height=16:
       A = ½ × 24 × 16 = 192
       slant = √(12² + 16²) = 20  →  P = 24 + 20 + 20 = 64
       r = 2A/P = 384/64 = 6 ft
       d = 1.5  →  r' = 4.5
       A' = 192 × (4.5/6)² = 192 × 0.5625 = 108 sqft
    """
    inputs = make_inputs()
    _with_roof(inputs, RoofSection(
        name="Hip", shape="tri", width_ft=24, height_ft=16,
        apex_x_ratio=0.5,
    ))
    [s] = compute_roof_layout(inputs).sections
    assert s.gross_area_sqft == pytest.approx(192.0)
    assert s.usable_area_sqft == pytest.approx(108.0, abs=0.1)


def test_tri_uses_largest_setback_when_eave_and_hip_differ():
    """Per-edge setback override on a triangle: implementation picks
    max(eave, hip) as the uniform inset — safer than weighted average."""
    inputs = make_inputs()
    _with_roof(inputs, RoofSection(
        name="Hip", shape="tri", width_ft=24, height_ft=16,
        edge_setbacks=[
            EdgeSetback(edge_type="eave", setback_ft=1.5),
            EdgeSetback(edge_type="hip",  setback_ft=3.0),   # bigger
        ],
    ))
    [s] = compute_roof_layout(inputs).sections
    # d = 3.0 (max), so r' = 6 - 3 = 3, A' = 192 × (3/6)² = 48 sqft
    assert s.usable_area_sqft == pytest.approx(48.0, abs=0.1)


def test_tri_oversize_inradius_consumes_entire_face():
    inputs = make_inputs()
    _with_roof(inputs, RoofSection(
        name="Hip", shape="tri", width_ft=10, height_ft=5,
        default_setback_ft=5.0,
    ))
    [s] = compute_roof_layout(inputs).sections
    assert s.usable_area_sqft == 0.0


# ─── Obstructions ──────────────────────────────────────────────────────


def test_rect_with_chimney_subtracts_halo_box():
    """24×16 face, 1.5 ft setbacks (usable = 273 sqft).
       Chimney 3×3 ft at (10, 6) with default 1.5 ft halo → halo box
       6×6 = 36 sqft loss → usable = 237 sqft.
    """
    inputs = make_inputs()
    _with_roof(inputs, RoofSection(
        name="South", shape="rect", width_ft=24, height_ft=16,
        obstructions=[RoofObstruction(
            kind="chimney", x_ft=10, y_ft=6,
            width_ft=3, height_ft=3, setback_ft=1.5,
        )],
    ))
    [s] = compute_roof_layout(inputs).sections
    assert s.obstruction_loss_sqft == pytest.approx(36.0)
    assert s.usable_area_sqft == pytest.approx(273.0 - 36.0)


def test_obstruction_outside_section_is_flagged_and_skipped():
    """Yaml-input error: obstruction located outside the section's
    bounding box. The engine must flag it (so the user fixes the
    coords) but not subtract a phantom area."""
    inputs = make_inputs()
    _with_roof(inputs, RoofSection(
        name="South", shape="rect", width_ft=24, height_ft=16,
        obstructions=[RoofObstruction(
            kind="skylight", x_ft=30, y_ft=20,    # outside
            width_ft=3, height_ft=3,
        )],
    ))
    [s] = compute_roof_layout(inputs).sections
    assert s.obstruction_loss_sqft == 0.0
    assert len(s.obstructions_outside_usable_area) == 1
    assert "skylight" in s.obstructions_outside_usable_area[0]


# ─── Module-fit check ──────────────────────────────────────────────────


def test_module_count_within_usable_area_fits():
    """273 sqft usable / 22 sqft per module = 12.4 → 12 modules fit."""
    inputs = make_inputs()
    _with_roof(inputs, RoofSection(
        name="South", shape="rect", width_ft=24, height_ft=16,
        module_count=12,
    ))
    [s] = compute_roof_layout(inputs).sections
    assert s.fits is True
    assert s.module_demand_sqft == 12 * MODULE_FOOTPRINT_SQFT


def test_module_count_exceeds_usable_area_fails():
    inputs = make_inputs()
    _with_roof(inputs, RoofSection(
        name="South", shape="rect", width_ft=24, height_ft=16,
        module_count=20,        # 20 × 22 = 440 sqft > 273 usable
    ))
    [s] = compute_roof_layout(inputs).sections
    assert s.fits is False


# ─── Backward compat ────────────────────────────────────────────────────


def test_legacy_yaml_no_shape_field_defaults_to_rect():
    """A roof_section yaml without explicit `shape` field still
    behaves as a rectangle (the K.2.6c additive-compat contract)."""
    rs = RoofSection(name="L", width_ft=20, height_ft=10)
    assert rs.shape == "rect"
    assert rs.gross_area_sqft == 200.0


def test_engine_populates_roof_layout_for_default_yaml():
    """End-to-end: even a yaml with NO roof_sections (legacy Smith
    Residence) gets a roof_layout result — empty list, no crash."""
    inputs = make_inputs()    # default has no roof_sections
    result = run(inputs)
    assert result.roof_layout.sections == []
    assert result.roof_layout.total_gross_sqft == 0.0
    assert result.roof_layout.all_fit is True   # vacuous truth


# ─── K.2.7 polygon roof face ─────────────────────────────────────────


def test_polygon_shape_l_house_300_sqft():
    """L-shaped roof face (300 sqft gross). 1.5 ft setback shrinks
    perimeter substantially; Minkowski formula:
       A = 300, P = 80, d = 1.5
       A' = 300 - 1.5×80 + π×2.25 ≈ 300 - 120 + 7.07 ≈ 187 sqft
    Compared to a rect 20×15 (300 sqft, P=70), the L's longer
    perimeter (80 vs 70) makes the inset bite harder — visible in
    the result.
    """
    inputs = make_inputs()
    _with_roof(inputs, RoofSection(
        name="South L", shape="polygon",
        # L: 20×10 main + 10×10 east arm, CCW from origin
        vertices=[(0, 0), (10, 0), (10, 10), (20, 10),
                  (20, 20), (0, 20)],
        width_ft=20, height_ft=20,
        module_count=8,
    ))
    [s] = compute_roof_layout(inputs).sections
    assert s.gross_area_sqft == pytest.approx(300.0)
    # Usable area after 1.5 ft inset ≈ 187 sqft (Minkowski)
    assert 180 < s.usable_area_sqft < 195


def test_polygon_shape_plus_500_sqft():
    """Plus / cross shape (500 sqft gross). Perimeter is 30×4 = 120 ft
    (4 outer corners contribute 10ft+10ft each), so inset eats more.
    A' = 500 - 1.5×120 + π×2.25 ≈ 500 - 180 + 7 = 327 sqft.
    """
    inputs = make_inputs()
    _with_roof(inputs, RoofSection(
        name="Plus Wing", shape="polygon",
        vertices=[
            (10, 0), (20, 0), (20, 10), (30, 10),
            (30, 20), (20, 20), (20, 30), (10, 30),
            (10, 20), (0, 20), (0, 10), (10, 10),
        ],
        width_ft=30, height_ft=30,
        module_count=12,
    ))
    [s] = compute_roof_layout(inputs).sections
    assert s.gross_area_sqft == pytest.approx(500.0)
    assert 320 < s.usable_area_sqft < 340


def test_polygon_shape_legacy_rect_yaml_unchanged():
    """Pre-K.2.7 yaml with `shape='rect'` produces bit-identical usable
    area — the polygon branch is opt-in."""
    inputs = make_inputs()
    _with_roof(inputs, RoofSection(
        name="South Roof", shape="rect",
        width_ft=24, height_ft=16,
        module_count=10,
    ))
    [s] = compute_roof_layout(inputs).sections
    assert s.shape == "rect"
    assert s.usable_area_sqft == pytest.approx(273.0)   # 21 × 13 inset


def test_polygon_oversize_setback_yields_zero_usable():
    """Inset bigger than the polygon's effective inradius → 0 usable
    area, no negative number leaks through."""
    inputs = make_inputs()
    _with_roof(inputs, RoofSection(
        name="Tiny L", shape="polygon",
        vertices=[(0, 0), (2, 0), (2, 1), (3, 1), (3, 3), (0, 3)],
        width_ft=3, height_ft=3,
        default_setback_ft=5.0,    # way larger than inradius
    ))
    [s] = compute_roof_layout(inputs).sections
    assert s.usable_area_sqft == 0.0
