"""K.8.2 — value-weighted orientation derate tests.

Three layers:
  1. **Hourly profile** — locks the AM/PM asymmetry math (East peaks
     morning, West peaks afternoon, South peaks noon, North weakest
     all day).
  2. **Hourly value factor** — math-collapse property (1:1 plan →
     constant 1.0 across all hours) + sub-1:1 weighting.
  3. **Single derate scalar** — `face_value_weighted_derate` produces
     West > East on sub-1:1 plans, West == East on 1:1 plans.
  4. **LRM integration** — `compute_annual_production` distribution
     changes when `use_value_weighted_distribution=True` AND
     latitude is available; bit-identical to K.8.1 area-only when
     the flag is off.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pvess_calc.calc.value_weighted import (
    DEFAULT_AVERAGE_LATITUDE_DEG,
    DEFAULT_DFW_SELF_CONSUMPTION_PATTERN,
    face_value_weighted_derate,
    hourly_face_profile,
    hourly_value_factor,
)
from pvess_calc.customer.production import compute_annual_production
from pvess_calc.schema import BackupOption, Inputs, RoofSection


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHOENIX_YAML = PROJECT_ROOT / "projects" / "002-phoenix-25kw" / "inputs.yaml"


# ─── Hourly production profile ──────────────────────────────────────────


def test_hourly_profile_south_peaks_at_solar_noon():
    """South-facing 30° tilt at 33°N: peak production at h=12. Both
    h=11 and h=13 must be lower than h=12 (symmetric, by equinox)."""
    p = hourly_face_profile(180.0, 30.0, 33.0)
    assert p[12] > p[11]
    assert p[12] > p[13]
    # And symmetric — h=11 ≈ h=13 (equinox model)
    assert abs(p[11] - p[13]) < 0.02


def test_hourly_profile_west_peaks_afternoon():
    """West-facing 30° tilt: peak production around h=14-15, NOT noon.
    This is the asymmetry the Sandia annual table flattens — the
    whole point of K.8.2."""
    p = hourly_face_profile(270.0, 30.0, 33.0)
    # PM peak must be in 13-16, NOT at noon
    pm_peak_hour = max(range(13, 17), key=lambda h: p[h])
    assert pm_peak_hour >= 14, f"west peak at h={pm_peak_hour}, expected ≥ 14"
    # And the PM peak must beat noon
    assert p[pm_peak_hour] > p[12]


def test_hourly_profile_east_west_are_mirror_symmetric():
    """Equinox model: East and West are mirror images about solar noon.
    `west[h] == east[24 - h]` (modulo float noise). Catches sign
    errors in the azimuth formula."""
    e = hourly_face_profile(90.0, 30.0, 33.0)
    w = hourly_face_profile(270.0, 30.0, 33.0)
    for h in range(6, 12):
        mirror = 24 - h
        assert abs(e[h] - w[mirror]) < 0.02, (
            f"E[{h}]={e[h]:.3f} vs W[{mirror}]={w[mirror]:.3f}"
        )


def test_hourly_profile_north_is_weakest_overall():
    """North-facing 30° tilt at 33°N: daily total must be the lowest
    of the 4 cardinal directions. Gates against sign confusion."""
    s = sum(hourly_face_profile(180, 30, 33))
    n = sum(hourly_face_profile(0, 30, 33))
    e = sum(hourly_face_profile(90, 30, 33))
    w = sum(hourly_face_profile(270, 30, 33))
    assert n < e
    assert n < w
    assert n < s
    assert n < 0.5 * s   # north 30° at 33° lat ≈ 45% of south output


# ─── Hourly value factor ────────────────────────────────────────────────


def test_value_factor_collapses_to_constant_on_1to1():
    """**Math-collapse property** — on a 1:1 REP plan (ratio=1.0), the
    value factor is 1.0 at every hour regardless of self-consumption.
    This is what guarantees zero regression from K.8.1 on 1:1 projects."""
    factors = hourly_value_factor(rep_buyback_ratio=1.00)
    assert all(abs(f - 1.0) < 1e-9 for f in factors)


def test_value_factor_low_buyback_dips_in_low_sc_hours():
    """On a 0.50× REP plan, the value factor must DIP during low-self-
    consumption hours (empty house mid-morning) and stay HIGH during
    peak afternoon. This drives the East-vs-West asymmetry."""
    factors = hourly_value_factor(rep_buyback_ratio=0.50)
    # Mid-morning (h=10, sc=0.25 → value = 0.25 + 0.75 × 0.50 = 0.625)
    assert factors[10] == pytest.approx(0.625, abs=0.01)
    # Evening peak (h=18, sc=0.95 → value = 0.95 + 0.05 × 0.50 = 0.975)
    assert factors[18] == pytest.approx(0.975, abs=0.01)
    # And the evening must beat the morning by ≥ 30%
    assert factors[18] > factors[10] + 0.30


def test_value_factor_24_length_validator():
    """Schema-level guard: custom self_consumption_pattern must be
    exactly 24 hours. Catches yaml off-by-one errors (12-hour list
    of monthly_kwh accidentally passed in)."""
    with pytest.raises(ValueError, match="24 hours"):
        hourly_value_factor(0.50, self_consumption_pattern=(0.5,) * 23)
    with pytest.raises(ValueError, match="24 hours"):
        hourly_value_factor(0.50, self_consumption_pattern=(0.5,) * 12)


# ─── Single value-weighted derate scalar ────────────────────────────────


def test_face_derate_south_normalizes_to_one():
    """The reference face is south, 30°. By construction the derate
    for south-30 against itself must be 1.000 exactly, on every REP
    ratio (the reference scales out)."""
    for ratio in (0.50, 0.95, 1.00):
        d = face_value_weighted_derate(180.0, 30.0, 33.0, ratio)
        assert d == pytest.approx(1.000, abs=0.001)


def test_face_derate_equals_sandia_on_1to1_plan():
    """**Math-collapse contract**: when REP ratio = 1.0, value-weighted
    derate == annual-kWh derate. West and East faces at 33°N are
    mirror-symmetric → value-weighted derate also equal."""
    w = face_value_weighted_derate(270.0, 30.0, 33.0, 1.00)
    e = face_value_weighted_derate(90.0, 30.0, 33.0, 1.00)
    assert w == pytest.approx(e, abs=0.005), (
        f"on 1:1 plan, W ({w:.3f}) and E ({e:.3f}) must match (math collapse)"
    )


def test_face_derate_west_beats_east_on_sub_1to1():
    """Core K.8.2 contract: on sub-1:1 REP plan, West-facing kWh are
    worth more than East-facing kWh of equal annual production.
    Spread must be ≥ 0.08 (8%) at 0.50× ratio with DFW DFW SC pattern."""
    w = face_value_weighted_derate(270.0, 30.0, 33.0, 0.50)
    e = face_value_weighted_derate(90.0, 30.0, 33.0, 0.50)
    spread = w - e
    assert spread > 0.08, (
        f"value-weighted W ({w:.3f}) - E ({e:.3f}) spread = {spread:.3f}; "
        "expected ≥ 0.08 on a 0.50× REP plan with DFW SC pattern"
    )


def test_face_derate_sw_beats_pure_south_on_sub_1to1():
    """SW-quadrant insight (the user's 2026-05-17 correction): on
    sub-1:1 plans, SW (between south and west) actually beats pure
    south because afternoon-peak production is worth more than
    noon-peak. Locks this in as the value-weighted algorithm's
    signature property."""
    s = face_value_weighted_derate(180.0, 30.0, 33.0, 0.50)
    sw = face_value_weighted_derate(225.0, 30.0, 33.0, 0.50)
    assert sw > s, (
        f"on 0.50× plan, SW-30° ({sw:.3f}) should beat pure S-30° ({s:.3f})"
    )


def test_face_derate_north_stays_bad_on_all_plans():
    """North-facing faces are bad regardless of REP plan (no afternoon
    boost can salvage poor annual kWh). Must score below 0.55 on
    every plan."""
    for ratio in (0.30, 0.50, 0.95, 1.00):
        d = face_value_weighted_derate(0.0, 30.0, 33.0, ratio)
        assert d < 0.55, f"N-30° on {ratio:.2f}× plan = {d:.3f} (≥ 0.55)"


# ─── LRM integration — distribution changes with the flag ──────────────


def _synthesize_se_sw_inputs(*, value_flag: bool, ratio_preset: str):
    """Build a project with an equal-area E + W face pair so the
    distribution shift between K.8.1 area-only and K.8.2 value-weighted
    is unambiguous."""
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.pv_array.modules = 20
    inputs.pv_array.strings = 4
    inputs.pv_array.modules_per_string = 5
    inputs.project.coordinates = "33.0, -96.0"   # Frisco lat for testing
    inputs.loads.export_tariff_model = ratio_preset
    inputs.loads.use_value_weighted_distribution = value_flag
    inputs.site.roof_sections = [
        RoofSection(name="East",  azimuth_deg=90,  pitch_deg=30,
                    width_ft=20, height_ft=20, module_count=0),
        RoofSection(name="West",  azimuth_deg=270, pitch_deg=30,
                    width_ft=20, height_ft=20, module_count=0),
    ]
    return inputs


def test_lrm_area_only_when_flag_off_gives_equal_split():
    """K.8.1 baseline: equal-area E + W faces, flag off → 10/10 split
    (area-proportional). Backward-compat guard."""
    inputs = _synthesize_se_sw_inputs(value_flag=False,
                                       ratio_preset="tx_default_oncor")
    result = compute_annual_production(
        inputs, baseline_kwh_per_kw=1500.0, baseline_method="nrel",
        latitude_deg=33.0,
    )
    assert result.method == "per_face_auto_distributed"
    assert len(result.faces) == 2
    e_face = next(f for f in result.faces if f.name == "East")
    w_face = next(f for f in result.faces if f.name == "West")
    e_modules = round(e_face.kw_dc * 1000 / inputs.pv_array.module.power_w)
    w_modules = round(w_face.kw_dc * 1000 / inputs.pv_array.module.power_w)
    assert e_modules == w_modules == 10


def test_lrm_value_weighted_shifts_modules_east_to_west_on_sub_1to1():
    """K.8.2 contract: same equal-area E + W faces, flag ON, sub-1:1
    plan → West gets MORE modules than East. Algorithm automates
    the "skip East" decision without yaml face-pruning."""
    inputs = _synthesize_se_sw_inputs(value_flag=True,
                                       ratio_preset="tx_default_oncor")
    result = compute_annual_production(
        inputs, baseline_kwh_per_kw=1500.0, baseline_method="nrel",
        latitude_deg=33.0,
    )
    assert result.method == "per_face_auto_distributed_value_weighted"
    e_face = next(f for f in result.faces if f.name == "East")
    w_face = next(f for f in result.faces if f.name == "West")
    e_modules = round(e_face.kw_dc * 1000 / inputs.pv_array.module.power_w)
    w_modules = round(w_face.kw_dc * 1000 / inputs.pv_array.module.power_w)
    assert w_modules > e_modules, (
        f"E={e_modules}, W={w_modules}; West should get more on 0.50× plan"
    )
    # Total conservation still holds
    assert e_modules + w_modules == 20


def test_lrm_value_weighted_keeps_equal_split_on_1to1_plan():
    """**Math-collapse contract at the integration layer**: when the
    REP plan is 1:1 (Green Mountain), value-weighted reduces to
    area-only weighting → equal split preserved. So Frisco on GME
    sees zero distribution change vs K.8.1 baseline."""
    inputs = _synthesize_se_sw_inputs(value_flag=True,
                                       ratio_preset="tx_green_mountain")
    result = compute_annual_production(
        inputs, baseline_kwh_per_kw=1500.0, baseline_method="nrel",
        latitude_deg=33.0,
    )
    e_face = next(f for f in result.faces if f.name == "East")
    w_face = next(f for f in result.faces if f.name == "West")
    e_modules = round(e_face.kw_dc * 1000 / inputs.pv_array.module.power_w)
    w_modules = round(w_face.kw_dc * 1000 / inputs.pv_array.module.power_w)
    # On 1:1 plan, value-weighted == area-weighted for equal-Sandia faces
    assert abs(e_modules - w_modules) <= 1, (
        f"E={e_modules}, W={w_modules}; on 1:1 plan should be ~equal"
    )


def test_lrm_value_weighted_falls_back_to_area_only_when_no_latitude():
    """Closing standard: the value-weighted code path needs latitude.
    When lat is None (no Mapbox + no project.coordinates), the LRM
    must fall back to area-only — NOT crash, NOT silently use a
    misleading default like lat=35.0."""
    inputs = _synthesize_se_sw_inputs(value_flag=True,
                                       ratio_preset="tx_default_oncor")
    inputs.project.coordinates = ""
    result = compute_annual_production(
        inputs, baseline_kwh_per_kw=1500.0, baseline_method="nrel",
        latitude_deg=None,
    )
    # Method falls back to the K.8.1 string
    assert result.method == "per_face_auto_distributed"
    e_face = next(f for f in result.faces if f.name == "East")
    w_face = next(f for f in result.faces if f.name == "West")
    e_modules = round(e_face.kw_dc * 1000 / inputs.pv_array.module.power_w)
    w_modules = round(w_face.kw_dc * 1000 / inputs.pv_array.module.power_w)
    assert e_modules == w_modules == 10   # K.8.1 area-only baseline


def test_production_result_is_per_face_includes_value_weighted_method():
    """Downstream contract: the new method name must register as a
    per-face method so the customer PDF + doctor check treat it the
    same as the original two."""
    from pvess_calc.customer.production import ProductionResult
    r = ProductionResult(
        annual_production_kwh=1000, baseline_kwh_per_kw=1500,
        method="per_face_auto_distributed_value_weighted",
    )
    assert r.is_per_face is True
