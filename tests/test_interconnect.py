from __future__ import annotations

from pvess_calc.calc.interconnect import compute_interconnection
from tests.conftest import make_inputs


def _eval_status(result, method):
    return next(e.status for e in result.evaluations if e.method == method)


def test_smith_residence_120_rule_fails_supply_side_recommended():
    # 200 A main + 2 × 30 A backfeed = 260 A vs 200 × 1.2 = 240 → FAIL
    inputs = make_inputs(main_panel_a=200, busbar_a=200, inverter_a=30, battery_qty=2, per_unit=True)
    r = compute_interconnection(inputs)

    assert r.total_backfeed_a == 60
    assert _eval_status(r, "120%_rule") == "FAIL"
    assert _eval_status(r, "sum_rule") == "FAIL"
    assert _eval_status(r, "supply_side_tap") == "PASS"
    assert r.recommended == "supply_side_tap"
    assert r.overall_status == "PASS"


def test_120_rule_passes_when_busbar_upsized_to_225():
    # 200 + 60 = 260 vs 225 × 1.2 = 270 → PASS
    inputs = make_inputs(
        main_panel_a=200, busbar_a=225, inverter_a=30, battery_qty=2,
        per_unit=True,
        interconnection_methods=["120%_rule", "supply_side_tap"],
    )
    r = compute_interconnection(inputs)
    assert _eval_status(r, "120%_rule") == "PASS"
    assert r.recommended == "120%_rule"


def test_sum_rule_passes_when_backfeed_small_enough():
    # main 100 A + backfeed 30 A = 130 A ≤ busbar 200 A → PASS
    inputs = make_inputs(
        main_panel_a=100, busbar_a=200, inverter_a=30, battery_qty=1,
        per_unit=True,
        interconnection_methods=["sum_rule"],
    )
    r = compute_interconnection(inputs)
    assert _eval_status(r, "sum_rule") == "PASS"
    assert r.recommended == "sum_rule"


def test_all_methods_fail_returns_no_recommendation():
    # 200 A main + 200 A backfeed = 400 A on 200 A bus → both rules FAIL,
    # supply_side_tap not in candidate list
    inputs = make_inputs(
        main_panel_a=200, busbar_a=200, inverter_a=200, battery_qty=1,
        per_unit=False,
        interconnection_methods=["120%_rule", "sum_rule"],
    )
    r = compute_interconnection(inputs)
    assert r.recommended is None
    assert r.overall_status == "FAIL"


# ─── K.2.5: multi-existing-PV bus-load principle ──────────────────────────
#
# These tests are the contract: pre-existing PV/ESS already on the bus
# (on MSP or any sub-panel) must enter the 705.12 sum. Missing this term
# is the #1 silent failure mode at AHJ permit review.


def test_existing_solar_msp_enters_sum():
    """K.2.5 golden — MSP 200 A, existing 30 A PV breaker already on MSP,
    adding 60 A new PV → sum rule must add ALL of it:
        200 + 60 + 30 = 290 A > 200 A bus → sum FAIL
        200 + 60 + 30 = 290 A > 200 × 1.20 = 240 → 120% FAIL
    Without the K.2.5 fix the engine would compute 260 A and FALSELY
    PASS 120% (260 ≤ 240 is also FAIL, but the *formula* would be
    wrong and the report would understate the problem)."""
    inputs = make_inputs(
        main_panel_a=200, busbar_a=200,
        inverter_a=30, battery_qty=2, per_unit=True,    # 60 A new backfeed
        existing_solar_breaker_a_msp=30,                # 30 A existing PV
        interconnection_methods=["120%_rule", "sum_rule", "supply_side_tap"],
    )
    r = compute_interconnection(inputs)

    assert r.total_backfeed_a == 60, "new system backfeed must remain 60 A"
    assert r.existing_solar_a == 30
    assert r.combined_backfeed_a == 90
    assert _eval_status(r, "sum_rule") == "FAIL"
    assert _eval_status(r, "120%_rule") == "FAIL"
    # Verify the formula text reflects the existing term:
    bf_120 = next(e for e in r.evaluations if e.method == "120%_rule")
    assert "30 (existing)" in bf_120.explanation
    assert "existing_solar" in bf_120.formula


def test_existing_solar_in_sub_panel_enters_sum():
    """Pre-existing PV on a SUB-panel (not MSP) — must still enter 705.12.
    NEC 705.12(B)(3) applies to whichever bus the new backfeed lands
    on; conservative implementation rolls everything up to a single
    bus-load check."""
    inputs = make_inputs(
        main_panel_a=200, busbar_a=200,
        inverter_a=30, battery_qty=1, per_unit=True,    # 30 A new backfeed
        sub_panels=[{
            "name": "Sub Panel #2", "rating_a": 200, "busbar_a": 200,
            "existing_solar_breaker_a": 40,
        }],
        interconnection_methods=["sum_rule"],
    )
    r = compute_interconnection(inputs)
    # 200 + 30 + 40 = 270 > 200 bus → sum FAIL
    assert r.existing_solar_a == 40
    assert _eval_status(r, "sum_rule") == "FAIL"


def test_existing_solar_zero_keeps_legacy_formula():
    """Regression: when existing_solar = 0 (greenfield install) the
    formula text must NOT mention 'existing_solar' — old reports stay
    bit-identical."""
    inputs = make_inputs(
        main_panel_a=100, busbar_a=200,
        inverter_a=30, battery_qty=1, per_unit=True,
        interconnection_methods=["sum_rule"],
    )
    r = compute_interconnection(inputs)
    sr = next(e for e in r.evaluations if e.method == "sum_rule")
    assert "existing" not in sr.explanation
    assert "existing" not in sr.formula
    assert r.existing_solar_a == 0
    assert r.combined_backfeed_a == r.total_backfeed_a


def test_existing_solar_msp_and_subpanel_combine():
    """Sum both contributions to a single existing_solar_a figure."""
    inputs = make_inputs(
        main_panel_a=200, busbar_a=400,
        inverter_a=30, battery_qty=1, per_unit=True,
        existing_solar_breaker_a_msp=20,
        sub_panels=[{
            "name": "Sub #1", "rating_a": 100, "busbar_a": 100,
            "existing_solar_breaker_a": 15,
        }],
        interconnection_methods=["sum_rule"],
    )
    r = compute_interconnection(inputs)
    assert r.existing_solar_a == 35          # 20 (MSP) + 15 (sub)
    assert r.combined_backfeed_a == 30 + 35
    # 200 + 30 + 35 = 265 ≤ 400 → still PASS, busbar is large enough
    assert _eval_status(r, "sum_rule") == "PASS"


def test_nec_2017_allows_sum_rule_2020_does_not():
    """K.7 NEC 2017 integration contract: same yaml + same backfeed,
    only the NEC edition changes. 2017 must evaluate sum_rule as a
    real PASS/FAIL; 2020 must mark it 'N/A · removed in NEC 2020'.

    Setup: 100 A main + 30 A backfeed = 130 A on a 200 A bus → sum
    rule passes (130 ≤ 200). 2017 reports PASS; 2020 reports N/A.
    """
    # 2017 — sum rule lives, evaluates to PASS
    inputs_2017 = make_inputs(
        main_panel_a=100, busbar_a=200,
        inverter_a=30, battery_qty=1, per_unit=True,
        interconnection_methods=["sum_rule"],
        nec_edition="2017",
    )
    r_2017 = compute_interconnection(inputs_2017)
    sum_eval_2017 = next(e for e in r_2017.evaluations if e.method == "sum_rule")
    assert sum_eval_2017.status == "PASS"
    assert "main + backfeed" in sum_eval_2017.formula

    # 2020 — sum rule deleted, marked N/A even though the math would pass
    inputs_2020 = make_inputs(
        main_panel_a=100, busbar_a=200,
        inverter_a=30, battery_qty=1, per_unit=True,
        interconnection_methods=["sum_rule"],
        nec_edition="2020",
    )
    r_2020 = compute_interconnection(inputs_2020)
    sum_eval_2020 = next(e for e in r_2020.evaluations if e.method == "sum_rule")
    assert sum_eval_2020.status == "N/A"
    assert "removed" in sum_eval_2020.explanation
    assert "NEC 2020" in sum_eval_2020.explanation


def test_nec_edition_dispatches_to_correct_rules_module():
    """K.7 — verify get_rules() really dispatches per edition, no
    silent fallback. The CLAUDE.md previously said 2017 → 2020
    fallback; this test enforces that contract is gone."""
    from pvess_calc.nec import get_rules
    assert get_rules("2017").EDITION == "2017"
    assert get_rules("2020").EDITION == "2020"
    assert get_rules("2023").EDITION == "2023"
    # Unknown editions fall back to 2023 (safest = latest).
    assert get_rules("9999").EDITION == "2023"


def test_rsd_boundary_voltage_differs_by_nec_edition():
    """K.7 — wiring of RSD_BOUNDARY_VOLTAGE_LIMIT: 80 V in 2017,
    30 V in 2020+. Locks the value contract — labels.specs.py reads
    this constant for the RSD label body."""
    from pvess_calc.nec import get_rules
    assert get_rules("2017").RSD_BOUNDARY_VOLTAGE_LIMIT == 80.0
    assert get_rules("2020").RSD_BOUNDARY_VOLTAGE_LIMIT == 30.0
    assert get_rules("2023").RSD_BOUNDARY_VOLTAGE_LIMIT == 30.0


def test_rsd_boundary_voltage_appears_in_label_substitutions():
    """K.7 end-to-end: the label-build substitution pipeline must
    actually consume the rules constant. Verify {{RSD_BOUNDARY_V}}
    resolves to '80 V' for a 2017 project and '30 V' for 2020."""
    from pvess_calc.calc.engine import run
    from pvess_calc.qet.inject import build_substitutions

    inp_2017 = make_inputs(nec_edition="2017")
    subs_2017 = build_substitutions(run(inp_2017))
    assert subs_2017["RSD_BOUNDARY_V"] == "80 V"

    inp_2020 = make_inputs(nec_edition="2020",
                            interconnection_methods=["120%_rule"])
    subs_2020 = build_substitutions(run(inp_2020))
    assert subs_2020["RSD_BOUNDARY_V"] == "30 V"


def test_supply_side_tap_notes_existing_load_side_pv():
    """When pre-existing PV is on the load side and the new system goes
    supply-side, the new tap PASSES — but the engineer must still verify
    the existing PV's 705.12 compliance. The evaluator surfaces this."""
    inputs = make_inputs(
        main_panel_a=200, busbar_a=200,
        inverter_a=200, battery_qty=1, per_unit=False,   # huge new
        existing_solar_breaker_a_msp=40,
        interconnection_methods=["supply_side_tap"],
    )
    r = compute_interconnection(inputs)
    sst = next(e for e in r.evaluations if e.method == "supply_side_tap")
    assert sst.status == "PASS"
    assert "pre-existing PV backfeed (40 A)" in sst.explanation
