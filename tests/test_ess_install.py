"""K.2.6b — NEC 706.10 + IRC R328 ESS install-location compliance.

What this test file enforces:

  * Unknown install location → WARN (data missing, not FAIL).
  * Indoor / garage installs FAIL when setbacks < 3 ft.
  * Indoor / garage installs FAIL when total kWh > 40 (IRC R328.4 2021).
  * Outdoor installs skip IRC R328 entirely; report PASS with a
    NEC 706.10 reminder note.
  * Engine integration: `CalculationResult.ess_install` is always
    populated (additive — old yamls get WARN, not crash).
"""
from __future__ import annotations

from pvess_calc.calc.engine import run
from pvess_calc.calc.ess_install import (
    MAX_INDOOR_CAPACITY_KWH,
    MIN_SETBACK_FT,
    evaluate_ess_install,
)
from tests.conftest import make_inputs


def _set_install(inputs, *, location, doorway=0.0, window=0.0, egress=0.0):
    """Helper — set install_location + 3 setback fields."""
    inputs.battery.install_location = location
    inputs.battery.distance_to_doorway_ft = doorway
    inputs.battery.distance_to_window_ft = window
    inputs.battery.distance_to_egress_ft = egress


# ─── unknown / default behavior ────────────────────────────────────────


def test_unknown_install_location_warns_not_fails():
    """Legacy yaml (no install_location set) defaults to 'unknown' —
    the check returns a WARN status with a guidance note. Crucial for
    additive compatibility."""
    inputs = make_inputs()
    # default-construction: install_location should be 'unknown'
    assert inputs.battery.install_location == "unknown"

    result = evaluate_ess_install(inputs)
    assert result.overall_status == "WARN"
    assert len(result.checks) == 1
    assert result.checks[0].status == "WARN"
    assert "not specified" in result.checks[0].detail


def test_engine_populates_ess_install_for_default_yaml():
    """Engine integration — ess_install must be present even when the
    yaml carries no install_location data."""
    inputs = make_inputs()
    result = run(inputs)
    assert result.ess_install.overall_status == "WARN"
    assert result.ess_install.install_location == "unknown"


# ─── setback FAIL cases ────────────────────────────────────────────────


def test_indoor_install_fails_when_doorway_too_close():
    inputs = make_inputs()
    _set_install(inputs, location="indoor",
                 doorway=2.0, window=5.0, egress=5.0)
    r = evaluate_ess_install(inputs)
    assert r.overall_status == "FAIL"
    bad = [c for c in r.checks if c.status == "FAIL"]
    assert any(c.name == "doorway_setback" for c in bad)
    assert any("doorways" in c.detail and "< required" in c.detail
               for c in bad)


def test_garage_install_passes_with_all_setbacks_at_3ft():
    inputs = make_inputs()
    _set_install(inputs, location="garage",
                 doorway=3.0, window=3.0, egress=3.0)
    r = evaluate_ess_install(inputs)
    assert r.overall_status == "PASS"


def test_indoor_install_warns_on_unmeasured_setback():
    """Setback distance = 0.0 → WARN (not FAIL) — code calls out
    'missing measurement' distinctly from 'measured & non-compliant'."""
    inputs = make_inputs()
    _set_install(inputs, location="indoor",
                 doorway=5.0, window=0.0, egress=5.0)
    r = evaluate_ess_install(inputs)
    assert r.overall_status == "WARN"
    window_check = next(c for c in r.checks if c.name == "window_setback")
    assert window_check.status == "WARN"
    assert "not measured" in window_check.detail


# ─── capacity ceiling ──────────────────────────────────────────────────


def test_indoor_install_fails_when_capacity_exceeds_40kwh():
    """41 kWh ESS indoors exceeds IRC R328.4 (2021) 40 kWh ceiling."""
    inputs = make_inputs(battery_qty=3)        # 3 × 13.5 = 40.5 kWh
    _set_install(inputs, location="indoor",
                 doorway=5.0, window=5.0, egress=5.0)
    r = evaluate_ess_install(inputs)
    cap = next(c for c in r.checks if c.name == "capacity_ceiling")
    assert cap.status == "FAIL"
    assert "40 kWh" in cap.detail


def test_garage_install_passes_with_27kwh_under_ceiling():
    inputs = make_inputs(battery_qty=2)        # 2 × 13.5 = 27 kWh
    _set_install(inputs, location="garage",
                 doorway=4.0, window=4.0, egress=4.0)
    r = evaluate_ess_install(inputs)
    cap = next(c for c in r.checks if c.name == "capacity_ceiling")
    assert cap.status == "PASS"


# ─── outdoor: IRC R328 doesn't apply ─────────────────────────────────


def test_outdoor_install_skips_irc_r328_passes():
    """Outdoor — IRC R328 setbacks and capacity ceiling don't apply.
    Result is PASS with a NEC 706.10 reminder."""
    inputs = make_inputs(battery_qty=4)        # 54 kWh — would FAIL indoor
    _set_install(inputs, location="outdoor")   # no setbacks needed
    r = evaluate_ess_install(inputs)
    assert r.overall_status == "PASS"
    assert any("706.10" in c.code_ref for c in r.checks)


def test_outdoor_protected_treated_as_outdoor():
    """NEMA 3R outdoor enclosure with thermal mgmt — same code path."""
    inputs = make_inputs(battery_qty=4)
    _set_install(inputs, location="outdoor_protected")
    r = evaluate_ess_install(inputs)
    assert r.overall_status == "PASS"


# ─── module-level constants (closing standard contract) ────────────────


def test_setback_constant_locked_at_3ft():
    """Closing standard: the 3 ft IRC R328.5 minimum is a constant.
    Anyone changing it must update this test on purpose."""
    assert MIN_SETBACK_FT == 3.0


def test_capacity_ceiling_locked_at_40kwh():
    """IRC R328.4 (2021) 40 kWh — same protection as above."""
    assert MAX_INDOOR_CAPACITY_KWH == 40.0
