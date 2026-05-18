"""Phase H (adjacent calcs) + Phase I (regional) tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from pvess_calc.calc.adjacent import (
    check_dc_afci, check_ground_rods, check_ground_rods_from_inputs,
    plan_surge_protection, select_conduit,
)
from pvess_calc.calc.engine import run
from pvess_calc.nec import get_rules
from pvess_calc.regional.california import check_title_24
from pvess_calc.regional.hawaii import check_rule_14h
from pvess_calc.regional.oncor_form import render_oncor_cover_letter
from tests.conftest import make_inputs


# --- Phase H: AFCI / SPD / ground rod / conduit ---------------------------

def test_dc_afci_pass_for_known_smart_inverter():
    inputs = make_inputs()
    inputs.inverter.brand = "Sol-Ark"
    inputs.inverter.model = "12K-2P-N"
    chk = check_dc_afci(inputs)
    assert chk.status == "PASS"
    assert chk.inverter_has_integrated_afci is True


def test_dc_afci_pass_for_selected_growatt_datasheet_model():
    inputs = make_inputs()
    inputs.inverter.brand = "Growatt"
    inputs.inverter.model = "MIN 11400TL-XH-US"
    chk = check_dc_afci(inputs)
    assert chk.status == "PASS"
    assert chk.inverter_has_integrated_afci is True
    assert "UL 1699B" in chk.evidence


def test_dc_afci_manual_for_unknown_inverter():
    inputs = make_inputs()
    inputs.inverter.brand = "Obscure"
    inputs.inverter.model = "X-1000"
    chk = check_dc_afci(inputs)
    assert chk.status == "MANUAL"
    assert chk.inverter_has_integrated_afci is False


def test_spd_plan_covers_all_locations():
    inputs = make_inputs()
    plan = plan_surge_protection(inputs)
    assert "Main Service Panel" in " ".join(plan.locations) or \
           "MSP" in " ".join(plan.locations)
    assert "PV DC side" in " ".join(plan.locations)
    assert plan.spd_type == "Type 2"
    assert plan.service_spd_required is True


def test_spd_service_requirement_is_nec_2020_plus_only():
    inputs = make_inputs()
    inputs.project.nec_edition = "2017"
    plan = plan_surge_protection(inputs)
    assert plan.service_spd_required is False
    assert not plan.required_locations


def test_ground_rod_pass_with_two_rods_8ft():
    chk = check_ground_rods(n_rods=2, spacing_ft=8.0)
    assert chk.status == "PASS"


def test_ground_rod_spacing_uses_project_survey_text():
    from pvess_calc.schema import GroundRod

    inputs = make_inputs()
    inputs.service.grounding_electrode_system.rods = [
        GroundRod(location="SE corner"),
        GroundRod(location="6 ft NW of rod #1"),
    ]
    chk = check_ground_rods_from_inputs(inputs)
    assert chk.status == "PASS"
    assert chk.spacing_ft == 6.0


def test_ground_rod_manual_for_single_rod():
    chk = check_ground_rods(n_rods=1, spacing_ft=0)
    assert chk.status == "MANUAL"
    assert "field resistance test" in chk.note


def test_conduit_fill_small_dc_circuit_fits_minimum_emt():
    """3 × #10 AWG THWN-2 = 0.063 in² → 1/2\" EMT (0.122 in² cap) fits."""
    result = select_conduit(["10", "10", "10"])
    assert result.selected_conduit == '1/2"'
    assert result.headroom_in2 > 0
    assert 0 < result.fill_pct < 100


def test_conduit_fill_step_up_when_many_conductors():
    """6 × #10 AWG (0.13 in²) needs 3/4\" EMT (0.213 cap) — not 1/2\"."""
    result = select_conduit(["10"] * 6)
    assert result.selected_conduit == '3/4"'


def test_conduit_fill_picks_larger_for_4_aug_conductors():
    """4 × #2/0 + #6 ground = 4 × 0.2223 + 0.0507 ≈ 0.94 in² → needs 1-1/2\" EMT."""
    result = select_conduit(["2/0", "2/0", "2/0", "2/0", "6"])
    assert result.selected_conduit in ('1-1/2"', '2"')


def test_conduit_fill_rejects_unknown_conductor_size():
    with pytest.raises(ValueError, match="Unknown THWN-2 conductor"):
        select_conduit(["10", "bogus"])


def test_engine_populates_adjacent_field():
    """End-to-end: run() includes the adjacent block."""
    result = run(make_inputs())
    assert result.adjacent.dc_afci is not None
    assert result.adjacent.pv_conduit.selected_conduit
    assert result.adjacent.ac_conduit.selected_conduit
    assert result.adjacent.surge.spd_type == "Type 2"
    assert result.adjacent.pv_conduit.fill_pct > 0


# --- Phase I: NEC 2017 / California / Hawaii / Oncor ----------------------

def test_nec_2017_module_loads():
    rules = get_rules("2017")
    assert rules.EDITION == "2017"
    # 2017 still allows sum_rule
    assert "sum_rule" not in rules.DISALLOWED_INTERCONNECT_METHODS


def test_nec_2017_rsd_threshold_is_80v():
    """The 2017 cycle uses 80V for array-boundary RSD (vs 30V in 2020+)."""
    rules = get_rules("2017")
    assert rules.RSD_BOUNDARY_VOLTAGE_LIMIT == 80.0


def test_california_title_24_flags_undersized_pv():
    """A tiny PV system should fail T24 sizing for a typical 6500 kWh/yr home."""
    inputs = make_inputs(modules=4)  # tiny array
    inputs.pv_array.modules_per_string = 4
    inputs.pv_array.strings = 1
    result = run(inputs)
    t24 = check_title_24(result, climate_zone=10, annual_load_kwh=6500)
    assert t24.pv_meets_t24 is False
    assert t24.pv_provided_kw < t24.pv_sizing_min_kw


def test_california_battery_storage_ready_detected():
    """A project with a battery should be flagged storage-ready."""
    inputs = make_inputs(battery_qty=2)
    result = run(inputs)
    t24 = check_title_24(result)
    assert t24.battery_storage_ready is True


def test_hawaii_rule_14h_residential_passes_fast_track():
    """A 6 kW residential system fits inside the 10 kW fast-track limit."""
    inputs = make_inputs(inverter_a=25, battery_qty=1, per_unit=False)
    inputs.inverter.quantity = 1
    result = run(inputs)
    chk = check_rule_14h(result)
    assert chk.fast_track_eligible is True


def test_hawaii_rule_14h_large_system_flagged():
    """A 25kW × 3 system blows past 10kW residential fast-track."""
    inputs = make_inputs(inverter_a=33, battery_qty=8, per_unit=False)
    inputs.inverter.quantity = 3
    result = run(inputs)
    chk = check_rule_14h(result)
    assert chk.fast_track_eligible is False


def test_oncor_cover_letter_renders_pdf(tmp_path: Path):
    result = run(make_inputs())
    out = tmp_path / "oncor.pdf"
    render_oncor_cover_letter(result, out)
    assert out.exists()
    assert out.read_bytes()[:4] == b"%PDF"
