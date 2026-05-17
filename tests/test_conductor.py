from __future__ import annotations

import math

import pytest

from pvess_calc.calc.conductor import select_copper, voltage_drop_dc
from pvess_calc.nec.tables import next_standard_ocpd


def test_select_copper_by_ampacity_only_picks_12awg_for_21a():
    # 12 AWG @ 75°C = 25 A ≥ 21.6 A — ampacity alone is fine.
    r = select_copper(21.6, insulation="75C")
    assert r.size == "12"
    assert r.ampacity_a == 25


def test_select_copper_with_25a_ocpd_steps_up_to_10awg_per_240_4_d():
    # With 25 A OCPD upstream, 240.4(D) caps 12 AWG at 20 A → must use 10 AWG.
    r = select_copper(21.6, insulation="75C", upstream_ocpd_a=25)
    assert r.size == "10"
    assert r.ampacity_a == 35
    assert r.headroom_a > 0


def test_select_copper_75c_for_50_amps_picks_8awg():
    r = select_copper(50, insulation="75C")
    # 8 AWG @ 75°C = 50 A exactly
    assert r.size == "8"
    assert r.ampacity_a == 50


def test_select_copper_steps_up_when_needed():
    r = select_copper(51, insulation="75C")
    # 51 > 50 (8 AWG), so move to 6 AWG (65 A)
    assert r.size == "6"
    assert r.ampacity_a == 65


def test_voltage_drop_dc_basic():
    # 10 AWG copper, 50 ft one-way, 17.25 A, 600 V nominal
    r = voltage_drop_dc(size="10", one_way_length_ft=50, current_a=17.25, nominal_voltage=600)
    # 2 × 50 × 17.25 × 1.21 / 1000 = 2.087 V
    assert math.isclose(r.drop_volts, 2 * 50 * 17.25 * 1.21 / 1000, abs_tol=1e-3)
    assert r.drop_percent < 1  # under 1% — fine


def test_next_standard_ocpd_rounds_up():
    assert next_standard_ocpd(21.6) == 25
    assert next_standard_ocpd(25) == 25
    assert next_standard_ocpd(26) == 30
    assert next_standard_ocpd(60) == 60


def test_next_standard_ocpd_overflow_raises():
    with pytest.raises(ValueError):
        next_standard_ocpd(10_000)
