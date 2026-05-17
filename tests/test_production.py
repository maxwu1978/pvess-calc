"""K.8 — per-face production aggregator.

Locks the contract on `customer.production.compute_annual_production`:

  * No roof_sections → legacy single-aggregate path (bit-identical to
    pre-K.8 projects).
  * roof_sections all module_count=0 → same fallback (engineer forgot
    to fill in counts; don't punish them).
  * pv_array.modules=0 → zero production regardless of stale section
    data (avoids the "modules=0 but yaml has roof_sections" trap that
    the no-savings test originally tripped over).
  * Multi-face → sum of face_kw × baseline × orientation × shading,
    with a blended_derate that's weighted by face capacity.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pvess_calc.customer.production import (
    FaceProduction,
    ProductionResult,
    compute_annual_production,
)
from pvess_calc.schema import Inputs


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHOENIX_YAML = PROJECT_ROOT / "projects" / "002-phoenix-25kw" / "inputs.yaml"
AUSTIN_YAML = PROJECT_ROOT / "projects" / "001-demo-austin" / "inputs.yaml"


# ─── Legacy / fallback paths ───────────────────────────────────────────


def test_production_single_orientation_falls_back_to_legacy_math():
    """Project with no `site.roof_sections` (Phase 0 yaml) uses the
    legacy `baseline × system_kw_dc` formula. Bit-identical to pre-K.8.
    """
    inputs = Inputs.from_yaml(AUSTIN_YAML)
    assert not inputs.site.roof_sections, "Austin demo should be single-orientation"

    result = compute_annual_production(
        inputs, baseline_kwh_per_kw=1500.0, baseline_method="nrel-pvwatts",
    )
    system_kw = inputs.pv_array.modules * inputs.pv_array.module.power_w / 1000.0
    assert result.method == "system_aggregate"
    assert result.faces == []
    assert result.annual_production_kwh == pytest.approx(1500.0 * system_kw, rel=1e-9)
    assert result.blended_derate is None


def test_production_zero_modules_short_circuits_to_zero():
    """`pv_array.modules = 0` means no array — production must be 0 even
    when yaml has stale section.module_count > 0 (the bug that the
    no-savings customer test exposed pre-fix)."""
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.pv_array.modules = 0
    inputs.pv_array.strings = 0
    inputs.pv_array.modules_per_string = 0
    # Note: sections still carry module_count=30 each — exactly the trap.
    assert sum(s.module_count for s in inputs.site.roof_sections) > 0

    result = compute_annual_production(
        inputs, baseline_kwh_per_kw=1500.0, baseline_method="us-average-fallback",
    )
    assert result.annual_production_kwh == 0.0
    assert result.faces == []
    assert result.method == "system_aggregate"


def test_production_sections_with_zero_modules_auto_distributes():
    """K.8.1 — when sections exist (e.g., from K.3c Google Solar lookup)
    but every section.module_count = 0 (designer hasn't distributed yet),
    auto-spread `pv_array.modules` across faces proportionally to area.

    Why: the pre-K.8.1 behavior was to fall back to single-orientation
    system_aggregate, which over-promises ~5-10 % in the customer-summary
    PDF for multi-face projects. The auto-distribute path forces per-face
    derate even at the "fresh-from-init" stage.

    Phoenix has 2 equal-area faces (S + W, 38 × 24 ft each). 60 modules
    should split exactly 30 / 30, matching the explicit yaml.
    """
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    for s in inputs.site.roof_sections:
        s.module_count = 0   # K.3c init state

    result = compute_annual_production(
        inputs, baseline_kwh_per_kw=1600.0, baseline_method="latitude-fallback",
    )
    assert result.method == "per_face_auto_distributed"
    assert len(result.faces) == 2
    # Equal-area faces → equal 30-module split
    for f in result.faces:
        # 30 modules × 0.42 kW = 12.6 kW DC per face
        assert f.kw_dc == pytest.approx(12.6, abs=0.05)
    # And the total matches the explicit-distribution path
    assert result.annual_production_kwh == pytest.approx(36_900, rel=0.02)


# ─── Per-face aggregation ──────────────────────────────────────────────


def test_production_per_face_phoenix_south_plus_west():
    """Phoenix has S + W roofs, 30 modules each. The S face takes 1.00,
    the W face takes ~0.86 derate. Both contribute to the total."""
    inputs = Inputs.from_yaml(PHOENIX_YAML)
    result = compute_annual_production(
        inputs, baseline_kwh_per_kw=1600.0, baseline_method="latitude-fallback",
    )
    assert result.method == "per_face"
    assert len(result.faces) == 2

    by_name = {f.name: f for f in result.faces}
    south = by_name["South Roof"]
    west = by_name["West Roof"]

    # Each face has 30 modules × 0.42 kW = 12.6 kW DC
    assert south.kw_dc == pytest.approx(12.6, abs=0.05)
    assert west.kw_dc == pytest.approx(12.6, abs=0.05)

    # South @ 22° tilt → close to 1.00; West @ 22°/270° → lower
    assert south.orientation_derate > west.orientation_derate
    assert south.orientation_derate > 0.95
    assert 0.80 < west.orientation_derate < 0.92

    # Aggregate sanity: ~1600 × 25.2 × 0.92 ≈ 37k
    assert 35_000 < result.annual_production_kwh < 40_000


def test_production_blended_derate_is_capacity_weighted():
    """blended_derate = Σ(kw_i × derate_i × shading_i) / Σ(kw_i).

    Build a synthetic 2-face result: 10 kW S (derate 1.00, shading 1.0)
    + 5 kW E (derate 0.50, shading 0.8). Expected blended =
    (10 × 1.00 × 1.0 + 5 × 0.50 × 0.8) / 15 = (10 + 2) / 15 = 0.80.
    """
    r = ProductionResult(
        annual_production_kwh=18_000.0,   # not asserted here
        baseline_kwh_per_kw=1500.0,
        method="per_face",
        faces=[
            FaceProduction(
                name="S", kw_dc=10.0, azimuth_deg=180, tilt_deg=20,
                orientation_derate=1.00, shading_factor=1.00,
                annual_production_kwh=15_000.0,
            ),
            FaceProduction(
                name="E", kw_dc=5.0, azimuth_deg=90, tilt_deg=20,
                orientation_derate=0.50, shading_factor=0.80,
                annual_production_kwh=3_000.0,
            ),
        ],
    )
    assert r.blended_derate == pytest.approx(0.80, abs=0.001)


def test_production_blended_derate_none_when_no_faces():
    """No faces → blended_derate is None (caller hides the metric)."""
    r = ProductionResult(
        annual_production_kwh=10_000.0,
        baseline_kwh_per_kw=1500.0,
        method="system_aggregate",
        faces=[],
    )
    assert r.blended_derate is None


def test_production_urban_density_default_applies_when_shading_unset():
    """Phoenix site_density defaults to 'unknown' (shading 1.00). Bump
    it to 'urban' and the per-face shading drops to 0.90, scaling
    every face's production down."""
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    # All faces leave shading_factor at default 1.0
    assert all(s.shading_factor == 1.0 for s in inputs.site.roof_sections)

    inputs.site.urban_density = "rural"
    rural = compute_annual_production(
        inputs, baseline_kwh_per_kw=1600.0, baseline_method="latitude-fallback",
    )

    inputs.site.urban_density = "urban"
    urban = compute_annual_production(
        inputs, baseline_kwh_per_kw=1600.0, baseline_method="latitude-fallback",
    )

    # Urban (0.90 shading) ≈ rural × 0.90
    assert urban.annual_production_kwh == pytest.approx(
        rural.annual_production_kwh * 0.90, rel=0.01,
    )
    for f in urban.faces:
        assert f.shading_factor == pytest.approx(0.90)


def test_production_face_shading_factor_overrides_density():
    """An engineer-set face shading_factor (e.g., 0.75 for a partially
    shaded face) overrides the site-density default."""
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.site.urban_density = "urban"   # would default everything to 0.90
    inputs.site.roof_sections[1].shading_factor = 0.75   # West face, measured

    result = compute_annual_production(
        inputs, baseline_kwh_per_kw=1600.0, baseline_method="latitude-fallback",
    )
    by_name = {f.name: f for f in result.faces}
    assert by_name["South Roof"].shading_factor == pytest.approx(0.90)   # density default
    assert by_name["West Roof"].shading_factor == pytest.approx(0.75)    # explicit


def test_production_face_kwh_consistent_with_face_inputs():
    """Each face's annual_production_kwh must equal
    baseline × face_kw × orientation_derate × shading_factor.
    Catches order-of-operations bugs in the aggregator."""
    inputs = Inputs.from_yaml(PHOENIX_YAML)
    baseline = 1500.0
    result = compute_annual_production(
        inputs, baseline_kwh_per_kw=baseline, baseline_method="nrel-pvwatts",
    )
    for f in result.faces:
        expected = baseline * f.kw_dc * f.orientation_derate * f.shading_factor
        assert f.annual_production_kwh == pytest.approx(expected, rel=1e-9)


def test_production_total_matches_face_sum():
    """`annual_production_kwh` must be exactly the sum of face kWh —
    no rounding loss, no double-count."""
    inputs = Inputs.from_yaml(PHOENIX_YAML)
    result = compute_annual_production(
        inputs, baseline_kwh_per_kw=1700.0, baseline_method="nrel-pvwatts",
    )
    expected_sum = sum(f.annual_production_kwh for f in result.faces)
    assert result.annual_production_kwh == pytest.approx(expected_sum, rel=1e-9)


# ─── K.8.1 auto-distribution (K.3c handoff) ─────────────────────────────


def test_production_auto_distribute_proportional_to_unequal_areas():
    """K.8.1 — when face areas differ, modules distribute proportionally.

    Synthesise a 60-module project on 4 faces with areas matching a
    realistic Frisco-style roof (Google Solar response):
      S = 415 ft², N = 380 ft², E = 145 ft², W = 145 ft² (Σ = 1,085)
    Expected distribution (60 × area / Σ):
      S: round(60 × 415/1085) = 23
      N: round(60 × 380/1085) = 21
      E: round(60 × 145/1085) =  8
      W: last face = 60 − (23+21+8) = 8
    """
    from pvess_calc.schema import RoofSection
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.pv_array.modules = 60
    inputs.site.roof_sections = [
        RoofSection(name="South", azimuth_deg=180, pitch_deg=22,
                    width_ft=20.4, height_ft=20.4, module_count=0),  # 415 ft²
        RoofSection(name="North", azimuth_deg=0, pitch_deg=22,
                    width_ft=19.5, height_ft=19.5, module_count=0),  # 380 ft²
        RoofSection(name="East", azimuth_deg=90, pitch_deg=22,
                    width_ft=12.0, height_ft=12.0, module_count=0),  # 144 ft²
        RoofSection(name="West", azimuth_deg=270, pitch_deg=22,
                    width_ft=12.0, height_ft=12.0, module_count=0),  # 144 ft²
    ]

    result = compute_annual_production(
        inputs, baseline_kwh_per_kw=1535.0, baseline_method="nrel-pvwatts",
    )
    assert result.method == "per_face_auto_distributed"
    assert len(result.faces) == 4

    # face_kw = module_count × 0.42 kW → reverse out the distribution
    module_w = inputs.pv_array.module.power_w
    distributed = [round(f.kw_dc * 1000 / module_w) for f in result.faces]
    assert distributed == [23, 21, 8, 8]


def test_production_auto_distribute_preserves_total_modules():
    """K.8.1 conservation: Σ face_module_count == pv_array.modules.
    Rounding errors can leak / steal one module per face; the
    last-face-remainder rule must hold the total exact for any
    `pv_array.modules` value."""
    from pvess_calc.schema import RoofSection
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    # 3 faces with awkward area ratios → rounding will round-up some
    # and round-down others; conservation must still hold.
    inputs.site.roof_sections = [
        RoofSection(name="A", azimuth_deg=180, pitch_deg=22,
                    width_ft=10, height_ft=7, module_count=0),    # 70 ft²
        RoofSection(name="B", azimuth_deg=270, pitch_deg=22,
                    width_ft=8, height_ft=9, module_count=0),     # 72 ft²
        RoofSection(name="C", azimuth_deg=90, pitch_deg=22,
                    width_ft=11, height_ft=6, module_count=0),    # 66 ft²
    ]
    module_w = inputs.pv_array.module.power_w

    # Try several total-module counts that are prone to rounding error
    for total in (7, 11, 13, 19, 23, 31, 47):
        inputs.pv_array.modules = total
        result = compute_annual_production(
            inputs, baseline_kwh_per_kw=1500.0, baseline_method="nrel",
        )
        assert result.method == "per_face_auto_distributed"
        face_modules = [round(f.kw_dc * 1000 / module_w) for f in result.faces]
        assert sum(face_modules) == total, (
            f"conservation broken for total={total}: faces={face_modules}"
        )


def test_production_auto_distribute_no_face_unjustly_zeroed():
    """K.8.1-v2 regression-bait: the Frisco E2E test (13 faces, 32
    modules) revealed the original "last-face-remainder" algorithm
    zeroed the last face when cumulative rounding consumed the budget,
    even though that face's area-proportional share was > 0.5
    (deserved 1 module).

    The Largest Remainder Method (Hamilton apportionment) replaces
    last-face-remainder. Property under test: every face whose fair
    share `total × area/Σ` ≥ 0.5 MUST receive ≥ 1 module.

    Uses the exact 13-face Frisco geometry from the 2026-05-17 E2E
    run so a regression to the old algorithm fails here, not on the
    next live `pvess-doctor` invocation.
    """
    from pvess_calc.schema import RoofSection

    # Same 13-section list as the Frisco project (area-significant
    # subset — sqrt areas correspond to the K.3c response).
    frisco_areas = [
        ("South Roof",     25.5),    # 650 ft²
        ("North Roof",     20.9),    # 437 ft²
        ("South Roof #2",  20.3),    # 412 ft²
        ("West Roof",      19.7),    # 388 ft²
        ("East Roof",      14.2),    # 202 ft²
        ("West Roof #2",   13.2),    # 174 ft²
        ("North Roof #2",  12.8),    # 164 ft²
        ("East Roof #2",   11.7),    # 137 ft²
        ("East Roof #3",   10.3),    # 106 ft²
        ("South Roof #3",  12.3),    # 151 ft²
        ("North Roof #3",  11.8),    # 139 ft²
        ("Northwest Roof",  8.2),    # 67 ft²
        ("North Roof #4",   8.3),    # 69 ft²   ← was zeroed pre-v2
    ]
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.pv_array.modules = 32
    inputs.site.roof_sections = [
        RoofSection(
            name=name, azimuth_deg=180, pitch_deg=22,
            width_ft=side, height_ft=side, module_count=0,
        )
        for name, side in frisco_areas
    ]

    result = compute_annual_production(
        inputs, baseline_kwh_per_kw=1535.0, baseline_method="nrel",
    )
    module_w = inputs.pv_array.module.power_w

    # Conservation (was already enforced; double-check)
    face_modules = [round(f.kw_dc * 1000 / module_w) for f in result.faces]
    assert sum(face_modules) == 32, (
        f"conservation broken: {face_modules}"
    )

    # Every face whose fair share is ≥ 0.5 must be allocated ≥ 1.
    total_area = sum(side * side for _, side in frisco_areas)
    expected_min_one = {
        name for name, side in frisco_areas
        if 32 * (side * side) / total_area >= 0.5
    }
    got_some = {f.name for f in result.faces}
    missing = expected_min_one - got_some
    assert not missing, (
        f"faces with fair_share ≥ 0.5 got zero modules (LRM regressed): "
        f"{missing}"
    )

    # Specifically: the "North Roof #4" face (was the v1 victim) gets
    # exactly 1 in the LRM output. Locks the v2 contract.
    assert "North Roof #4" in got_some, (
        "regression: 'North Roof #4' was zeroed (the original v1 bug)"
    )


def test_production_auto_distribute_falls_back_when_areas_zero():
    """K.8.1 edge case: if every section has gross_area_sqft = 0
    (degenerate yaml — width=0 or height=0), don't crash on /0 — fall
    back to legacy system_aggregate so the customer summary still
    renders (with a single-orientation number)."""
    from pvess_calc.schema import RoofSection
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.site.roof_sections = [
        RoofSection(name="degenerate", azimuth_deg=180, pitch_deg=22,
                    width_ft=0, height_ft=0, module_count=0),
    ]
    result = compute_annual_production(
        inputs, baseline_kwh_per_kw=1500.0, baseline_method="nrel",
    )
    assert result.method == "system_aggregate"
    assert result.faces == []


def test_production_method_string_is_per_face_for_both_paths():
    """ProductionResult.is_per_face must be True for both the manual
    distribution AND the auto-distribution path — downstream consumers
    (PDF, doctor) don't need to special-case them."""
    from pvess_calc.schema import RoofSection
    # Manual distribution
    inputs = Inputs.from_yaml(PHOENIX_YAML)
    r1 = compute_annual_production(inputs, baseline_kwh_per_kw=1500, baseline_method="nrel")
    assert r1.is_per_face is True
    assert r1.method == "per_face"

    # Auto distribution
    inputs2 = inputs.model_copy(deep=True)
    for s in inputs2.site.roof_sections:
        s.module_count = 0
    r2 = compute_annual_production(inputs2, baseline_kwh_per_kw=1500, baseline_method="nrel")
    assert r2.is_per_face is True
    assert r2.method == "per_face_auto_distributed"
