from __future__ import annotations

import math

import pytest

from pvess_calc.calc.pv_string import compute_pv_string
from pvess_calc.nec.tables import table_690_7_factor
from tests.conftest import make_inputs


def test_voc_correction_uses_datasheet_beta_when_present():
    inputs = make_inputs(voc_temp_coeff=-0.28, design_low_c=-5.0)
    r = compute_pv_string(inputs.pv_array)
    # 1 + (-0.0028) × (-5 - 25) = 1 + 0.084 = 1.084
    assert r.voc_correction_method == "datasheet_beta"
    assert math.isclose(r.voc_correction_factor, 1.084, abs_tol=1e-6)
    assert math.isclose(r.voc_cold_per_module, 49.5 * 1.084, abs_tol=1e-3)
    # string Voc = 49.5 × 1.084 × 12 modules
    assert math.isclose(r.string_voc_cold, 49.5 * 1.084 * 12, abs_tol=1e-2)
    # 49.5 × 1.084 × 12 ≈ 644 V > 600 V dwelling cap → flag should fire
    assert r.exceeds_max_system_voltage is True


def test_voc_correction_falls_back_to_table_690_7():
    inputs = make_inputs(voc_temp_coeff=None, design_low_c=-5.0)
    r = compute_pv_string(inputs.pv_array)
    assert r.voc_correction_method == "table_690_7"
    assert math.isclose(r.voc_correction_factor, table_690_7_factor(-5.0))


def test_dwelling_600v_limit_flag_when_exceeded():
    # 12 modules × 49.5 × 1.14 = 677 V, exceeds 600 V dwelling cap.
    inputs = make_inputs(voc_temp_coeff=None, design_low_c=-10.0)
    r = compute_pv_string(inputs.pv_array)
    assert r.string_voc_cold > 600
    assert r.exceeds_max_system_voltage is True


def test_isc_690_8_a_applies_125_percent():
    inputs = make_inputs()
    r = compute_pv_string(inputs.pv_array)
    assert math.isclose(r.isc_690_8_a, 13.8 * 1.25)


def test_conductor_and_ocpd_both_apply_another_125_percent():
    inputs = make_inputs()
    r = compute_pv_string(inputs.pv_array)
    # 13.8 × 1.25 × 1.25 = 21.5625
    assert math.isclose(r.conductor_required_a, 13.8 * 1.25 * 1.25)
    assert math.isclose(r.ocpd_minimum_a, 13.8 * 1.25 * 1.25)


def test_invalid_module_count_rejected():
    with pytest.raises(ValueError, match="modules"):
        make_inputs(modules=25)  # 25 != 2 × 12
