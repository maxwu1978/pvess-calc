"""Tests for pvess-doctor structural checks.

Two kinds of tests here:

1. *Contract tests* — verify each check correctly reports PASS on a valid
   fixture (Phoenix project), so that future refactors don't accidentally
   break the check itself. These run the doctor against `projects/002-phoenix-25kw/`.

2. *Regression-bait tests* — temporarily mutate state to simulate a known
   bug class (unknown sheet code in AHJ profile, missing display code in
   cover, fixed-width truncation slice) and verify the doctor catches it.
   These prove the doctor would have flagged the Phase J cover-index drift.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pvess_calc.doctor import (
    CheckResult,
    _check_ahj_profile_codes,
    _check_calc_engine,
    _check_cover_lists_all_sheets,
    _check_dxf_text_no_overflow,
    _check_dxf_wire_text_no_overlap,
    _check_inputs_load,
    _check_label_set_codes,
    _check_no_fixed_width_truncation_markers,
    _check_pv5_text_no_overlap,
    run_doctor,
)
from pvess_calc.permit.sheet_registry import SHEET_REGISTRY, codes


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHOENIX = PROJECT_ROOT / "projects" / "002-phoenix-25kw"
FRISCO = PROJECT_ROOT / "projects" / "003-frisco-glasshouse"


# ─── Contract tests on Phoenix ────────────────────────────────────────────


def test_inputs_load_passes_on_phoenix():
    [r] = _check_inputs_load(PHOENIX)
    assert r.status == "PASS", r.detail


def test_inputs_load_fails_on_missing_file(tmp_path: Path):
    [r] = _check_inputs_load(tmp_path)
    assert r.status == "FAIL"
    assert "not found" in r.detail


def test_ahj_profile_codes_all_pass():
    results = _check_ahj_profile_codes()
    fails = [r for r in results if r.status == "FAIL"]
    assert not fails, "AHJ profiles reference unknown sheet codes: " + str(fails)


def test_label_set_codes_all_pass():
    results = _check_label_set_codes()
    fails = [r for r in results if r.status == "FAIL"]
    assert not fails, "AHJ profiles reference unknown label codes: " + str(fails)


def test_no_truncation_slices_in_render_code():
    """DESIGN.md §7 — no fixed-width string slicing in permit/ or dxf/."""
    [r] = _check_no_fixed_width_truncation_markers(PHOENIX)
    assert r.status == "PASS", r.detail


def test_full_doctor_on_phoenix_all_pass():
    """End-to-end: every check passes on the Phoenix fixture.

    This is the single assertion that future PRs run before merging anything
    that touches permit/, dxf/, or qet/.
    """
    results = run_doctor(PHOENIX)
    fails = [r for r in results if r.status == "FAIL"]
    assert not fails, (
        f"pvess-doctor surfaced regressions on Phoenix:\n  "
        + "\n  ".join(f"{r.name}: {r.detail}" for r in fails)
    )


# ─── Regression-bait tests ────────────────────────────────────────────────


def test_unknown_sheet_code_in_ahj_profile_is_caught(tmp_path: Path,
                                                    monkeypatch):
    """Simulating Phase G regression: someone added a code to an AHJ
    profile YAML but never wired it into the registry."""
    from pvess_calc.ahj import profile as ahj_mod

    # Point the loader at a temp dir with one bogus profile.
    fake_dir = tmp_path / "profiles"
    fake_dir.mkdir()
    (fake_dir / "test_bogus.yaml").write_text(
        "name: Test\n"
        "required_sheets:\n"
        "  - cover\n"
        "  - ee-99-not-real\n"
    )
    monkeypatch.setattr(ahj_mod, "PROFILES_DIR", fake_dir)

    results = _check_ahj_profile_codes()
    fails = [r for r in results if r.status == "FAIL"]
    assert any("ee-99-not-real" in r.detail for r in fails), \
        "doctor should have flagged the bogus sheet code"


def test_cover_missing_a_display_code_is_caught(monkeypatch):
    """Simulating Phase J regression: builder emits PV-4 but cover's
    SHEET INDEX block doesn't print it.

    After the Sheet Registry refactor cover.py reads from
    `cover_index_rows()`, so the simulation strategy is to make that
    helper *short-return* a subset (mimicking the old hardcoded-list bug)
    while the registry — and therefore the doctor's source of truth —
    still contains the full list. The doctor must flag the gap.
    """
    import pvess_calc.permit.cover_sheet as cover_mod

    # Cover's helper returns everything except the last two registered
    # sheets — i.e. the cover "forgets" to print PV-N and EE-6.
    full_rows = [(s.display_code, s.title) for s in SHEET_REGISTRY]
    truncated_rows = full_rows[:-2]
    monkeypatch.setattr(cover_mod, "cover_index_rows",
                        lambda: truncated_rows)

    from pvess_calc.calc.engine import run
    from pvess_calc.schema import Inputs

    result = run(Inputs.from_yaml(PHOENIX / "inputs.yaml"))
    [r] = _check_cover_lists_all_sheets(result, PHOENIX)
    assert r.status == "FAIL"
    # The last two display codes (PV-N, EE-6) should be the ones flagged.
    for code, _title in full_rows[-2:]:
        assert code in r.detail, \
            f"doctor should have flagged missing {code}, got: {r.detail}"


def test_calc_engine_check_handles_none():
    [r] = _check_calc_engine(None)
    assert r.status == "FAIL"
    assert "None" in r.detail


# ─── Phase H adjacent NEC protections ─────────────────────────────────────


def test_phase_h_adjacent_guard_passes_on_frisco():
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_phase_h_adjacent_calcs_complete
    from pvess_calc.schema import Inputs

    result = run(Inputs.from_yaml(FRISCO / "inputs.yaml"))
    [r] = _check_phase_h_adjacent_calcs_complete(result)
    assert r.status == "PASS", r.detail
    assert "AFCI=PASS" in r.detail


def test_phase_h_adjacent_guard_warns_on_unconfirmed_afci():
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_phase_h_adjacent_calcs_complete
    from pvess_calc.schema import Inputs

    result = run(Inputs.from_yaml(PHOENIX / "inputs.yaml"))
    [r] = _check_phase_h_adjacent_calcs_complete(result)
    assert r.status == "WARN"
    assert "DC AFCI listing not confirmed" in r.detail


def test_phase_h_adjacent_guard_fails_on_overfilled_conduit():
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_phase_h_adjacent_calcs_complete
    from pvess_calc.schema import Inputs

    result = run(Inputs.from_yaml(FRISCO / "inputs.yaml"))
    result.adjacent.pv_conduit.fill_pct = 101.0
    [r] = _check_phase_h_adjacent_calcs_complete(result)
    assert r.status == "FAIL"
    assert "PV conduit fill" in r.detail


# ─── K.2.5 subpanel_slots_sufficient ──────────────────────────────────────


def test_subpanel_slots_sufficient_skipped_when_unknown():
    """Contract: when no panel has `available_slots` populated, the
    check passes with an explicit 'skipped' note — doesn't false-alarm
    on legacy yaml that pre-dates K.2.5."""
    from pvess_calc.doctor import _check_subpanel_slots_sufficient
    from pvess_calc.schema import Inputs
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml")
    [r] = _check_subpanel_slots_sufficient(inputs)
    assert r.status == "PASS"
    assert "skipped" in r.detail


def test_subpanel_slots_sufficient_catches_full_msp():
    """Regression-bait: synthesize an MSP at full capacity → check FAILS
    with a 'panel swap required' message."""
    from pvess_calc.doctor import _check_subpanel_slots_sufficient
    from pvess_calc.schema import Inputs
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    # 30-slot MSP, 30 used → 0 free → can't fit a 2-pole breaker
    inputs.service.msp_available_slots = 30
    inputs.service.msp_used_slots = 30
    [r] = _check_subpanel_slots_sufficient(inputs)
    assert r.status == "FAIL"
    assert "MSP" in r.detail
    assert "panel swap" in r.detail


def test_subpanel_slots_sufficient_catches_full_subpanel():
    """Regression-bait: a sub-panel at full capacity must also fail."""
    from pvess_calc.doctor import _check_subpanel_slots_sufficient
    from pvess_calc.schema import Inputs, SubPanel
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    inputs.service.sub_panels = [SubPanel(
        name="Garage Sub", rating_a=100, busbar_a=100,
        available_slots=16, used_slots=16,
    )]
    [r] = _check_subpanel_slots_sufficient(inputs)
    assert r.status == "FAIL"
    assert "Garage Sub" in r.detail


def test_ges_compliant_passes_when_no_ges_data():
    """K.5 backward-compat: legacy yaml without GES content → PASS
    with 'no GES data' note (don't false-alarm)."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_grounding_electrode_system_compliant
    from pvess_calc.schema import Inputs
    result = run(Inputs.from_yaml(PHOENIX / "inputs.yaml"))
    [r] = _check_grounding_electrode_system_compliant(result)
    assert r.status == "PASS"
    assert "no GES data" in r.detail


def test_ges_compliant_catches_undersized_gec():
    """Regression-bait: existing #8 AWG GEC on a 200 A service →
    UNDERSIZED → FAIL."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_grounding_electrode_system_compliant
    from pvess_calc.schema import GroundRod, Inputs
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    inputs.service.grounding_electrode_system.gec_main_size_awg = "8"
    inputs.service.grounding_electrode_system.rods = [GroundRod(), GroundRod()]
    inputs.service.grounding_electrode_system.bonded_to_neutral_at_service = "yes"
    result = run(inputs)
    [r] = _check_grounding_electrode_system_compliant(result)
    assert r.status == "FAIL"
    assert "UNDERSIZED" in r.detail or "#8" in r.detail


def test_ges_compliant_catches_single_rod_without_supplement():
    """Regression-bait: only 1 rod and no water-pipe / Ufer → fails
    NEC 250.53(A)(2) (2 rods or ≤25 Ω test)."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_grounding_electrode_system_compliant
    from pvess_calc.schema import GroundRod, Inputs
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    inputs.service.grounding_electrode_system.rods = [GroundRod()]
    inputs.service.grounding_electrode_system.gec_main_size_awg = "4"
    inputs.service.grounding_electrode_system.bonded_to_neutral_at_service = "yes"
    result = run(inputs)
    [r] = _check_grounding_electrode_system_compliant(result)
    assert r.status == "FAIL"
    assert "single rod" in r.detail


def test_ges_compliant_catches_missing_main_bonding_jumper():
    """Regression-bait: bonded_to_neutral_at_service='no' → FAIL."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_grounding_electrode_system_compliant
    from pvess_calc.schema import GroundRod, Inputs, UferElectrode
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    inputs.service.grounding_electrode_system.rods = [GroundRod(), GroundRod()]
    inputs.service.grounding_electrode_system.ufer = UferElectrode()
    inputs.service.grounding_electrode_system.gec_main_size_awg = "4"
    inputs.service.grounding_electrode_system.bonded_to_neutral_at_service = "no"
    result = run(inputs)
    [r] = _check_grounding_electrode_system_compliant(result)
    assert r.status == "FAIL"
    assert "bonding jumper" in r.detail


# ─── K.7 final 4 checks ──────────────────────────────────────────────


def test_export_tariff_matches_state_passes_for_az_default():
    """K.7 [2/4] guard: AZ project on default 1to1_nem → PASS (no
    mandatory successor tariff)."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_export_tariff_matches_state
    from pvess_calc.schema import Inputs
    result = run(Inputs.from_yaml(PHOENIX / "inputs.yaml"))
    [r] = _check_export_tariff_matches_state(result)
    assert r.status == "PASS"


def test_export_tariff_matches_state_fails_ca_with_1to1():
    """K.7 [2/4] regression-bait: CA project with 1to1_nem must FAIL —
    NEM 3.0 is mandatory for new applicants since 2023-04. Forgetting
    to flip the tariff model means K.4 ROI overstates by 40%."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_export_tariff_matches_state
    from pvess_calc.schema import Inputs
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    inputs.project.location = "Los Angeles, CA"
    # Keep loads.export_tariff_model at default "1to1_nem"
    result = run(inputs)
    [r] = _check_export_tariff_matches_state(result)
    assert r.status == "FAIL"
    assert "CA" in r.detail
    assert "ca_nem3" in r.detail


def test_export_tariff_matches_state_passes_ca_with_nem3():
    """When the engineer correctly sets the tariff, the check passes."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_export_tariff_matches_state
    from pvess_calc.schema import Inputs
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    inputs.project.location = "San Diego, CA"
    inputs.loads.export_tariff_model = "ca_nem3"
    result = run(inputs)
    [r] = _check_export_tariff_matches_state(result)
    assert r.status == "PASS"
    assert "CA" in r.detail


def test_export_tariff_matches_state_fails_hi_with_1to1():
    """HI closed NEM in 2015 — 1to1 default must FAIL on HI projects."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_export_tariff_matches_state
    from pvess_calc.schema import Inputs
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    inputs.project.location = "Honolulu, HI"
    result = run(inputs)
    [r] = _check_export_tariff_matches_state(result)
    assert r.status == "FAIL"
    assert "hi_self_consumption" in r.detail


def test_rsd_label_substitution_wired_passes_in_current_codebase():
    """K.7 [1/4] sanity: the RSD label IS wired correctly today,
    so the check passes. Drift sentry — drop the {{RSD_BOUNDARY_V}}
    placeholder or break build_substitutions and this fails."""
    from pvess_calc.doctor import _check_rsd_label_substitution_wired
    [r] = _check_rsd_label_substitution_wired()
    assert r.status == "PASS"
    assert "2017→80V" in r.detail
    assert "2020→30V" in r.detail


def test_tx_rep_plan_check_skips_non_tx_project():
    """K.4.6.6 [1/2]: Phoenix (AZ) → skipped with PASS. Check doesn't
    have an opinion outside TX; this is the negative control."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_tx_rep_plan_explicitly_chosen
    from pvess_calc.schema import Inputs
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml")
    [r] = _check_tx_rep_plan_explicitly_chosen(run(inputs))
    assert r.status == "PASS"
    assert "non-TX" in r.detail


def test_tx_rep_plan_check_warns_on_tx_default_1to1():
    """K.4.6.6 [1/2] regression-bait: a TX project on the generic
    `1to1_nem` tariff (Austin, Houston, Dallas) is leaving money on
    the table — fires WARN with REP-switch hint + dollar magnitude."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_tx_rep_plan_explicitly_chosen
    from pvess_calc.schema import Inputs
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    inputs.project.location = "Austin, TX"
    inputs.loads.export_tariff_model = "1to1_nem"   # the generic default
    [r] = _check_tx_rep_plan_explicitly_chosen(run(inputs))
    assert r.status == "WARN"
    assert "TX" in r.detail
    assert "1to1_nem" in r.detail
    # Hint must mention the REP-switch alternatives
    assert "tx_" in r.detail or "REP" in r.detail


def test_tx_rep_plan_check_passes_on_tx_preset():
    """K.4.6.6 [1/2]: TX project on a tx_* preset → PASS, plan name
    surfaces in detail."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_tx_rep_plan_explicitly_chosen
    from pvess_calc.schema import Inputs
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    inputs.project.location = "Frisco, TX"
    inputs.loads.export_tariff_model = "tx_green_mountain"
    [r] = _check_tx_rep_plan_explicitly_chosen(run(inputs))
    assert r.status == "PASS"
    assert "tx_green_mountain" in r.detail


def test_tx_rep_plan_check_passes_with_explicit_ratio_override():
    """K.4.6.6 [1/2]: explicit rep_buyback_ratio (K.4.6.4 escape hatch)
    counts as 'plan chosen explicitly' — no WARN even if the named
    tariff is still '1to1_nem'."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_tx_rep_plan_explicitly_chosen
    from pvess_calc.schema import Inputs
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    inputs.project.location = "Houston, TX"
    inputs.loads.export_tariff_model = "1to1_nem"   # legacy field
    inputs.loads.rep_buyback_ratio = 0.85           # but explicit override
    [r] = _check_tx_rep_plan_explicitly_chosen(run(inputs))
    assert r.status == "PASS"
    assert "0.85" in r.detail


def test_self_consumption_check_warns_on_sub_1to1_with_passive_self_cons():
    """K.4.6.6 [2/2] regression-bait: sub-1:1 REP plan + passive
    self_consumption (0.30 default) + no battery → WARN with
    SMT-load-shifting hint + estimated $/yr left on the table."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_self_consumption_realistic_for_rep_plan
    from pvess_calc.schema import Inputs
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    inputs.project.location = "Dallas, TX"
    inputs.loads.export_tariff_model = "tx_default_oncor"   # 0.50× ratio
    inputs.loads.self_consumption_fraction = 0.30           # passive baseline
    inputs.battery.quantity = 0                             # PV-only
    [r] = _check_self_consumption_realistic_for_rep_plan(run(inputs))
    assert r.status == "WARN"
    assert "Smart Meter Texas" in r.detail
    assert "load-shift" in r.detail or "shifted" in r.detail


def test_self_consumption_check_passes_on_1to1_plan():
    """K.4.6.6 [2/2]: 1:1 REP plan → math collapses (self_cons
    irrelevant), so no opinion offered. This is the Frisco baseline."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_self_consumption_realistic_for_rep_plan
    from pvess_calc.schema import Inputs
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    inputs.loads.export_tariff_model = "tx_green_mountain"  # 1:1
    inputs.loads.self_consumption_fraction = 0.30            # would WARN on sub-1:1
    [r] = _check_self_consumption_realistic_for_rep_plan(run(inputs))
    assert r.status == "PASS"
    assert "1:1" in r.detail or "collapses" in r.detail


def test_self_consumption_check_passes_when_battery_installed():
    """K.4.6.6 [2/2]: battery → time-shifting handled at ESS layer,
    not at load-scheduling layer. SMT hint doesn't apply when there's
    a real battery already."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_self_consumption_realistic_for_rep_plan
    from pvess_calc.schema import Inputs
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    inputs.loads.export_tariff_model = "tx_default_oncor"
    inputs.loads.self_consumption_fraction = 0.30
    assert inputs.battery.installed is True   # Phoenix yaml has battery
    [r] = _check_self_consumption_realistic_for_rep_plan(run(inputs))
    assert r.status == "PASS"
    assert "battery" in r.detail.lower() or "ESS" in r.detail


def test_self_consumption_check_passes_when_already_aggressive():
    """K.4.6.6 [2/2]: project that's already declared self_cons ≥ 0.40
    has explicitly accepted the load-shifting reality — no nag."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_self_consumption_realistic_for_rep_plan
    from pvess_calc.schema import Inputs
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    inputs.loads.export_tariff_model = "tx_default_oncor"
    inputs.loads.self_consumption_fraction = 0.55            # active shifting
    inputs.battery.quantity = 0
    [r] = _check_self_consumption_realistic_for_rep_plan(run(inputs))
    assert r.status == "PASS"
    assert "load-shifted" in r.detail or "0.55" in r.detail or "0.5" in r.detail


def test_compare_pdf_renderable_passes_for_phoenix():
    """K.7 [4/4] guard: the Phoenix scenarios → comparison.pdf round-trip
    works. Runs in tmp dir so we don't touch project artifacts."""
    from pvess_calc.doctor import _check_compare_pdf_renderable
    [r] = _check_compare_pdf_renderable()
    assert r.status == "PASS"
    assert "rendered" in r.detail


def test_nec_edition_artifacts_consistent_passes_when_no_artifacts():
    """K.7 [1/4] guard: when `pvess calc` hasn't run yet (no
    output/report.md), the check passes with a 'no artifacts' note —
    doesn't fail just because the project is brand new."""
    import tempfile
    import shutil
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_nec_edition_artifacts_consistent
    from pvess_calc.schema import Inputs
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        shutil.copy(PHOENIX / "inputs.yaml", td_path / "inputs.yaml")
        result = run(Inputs.from_yaml(td_path / "inputs.yaml"))
        [r] = _check_nec_edition_artifacts_consistent(result, td_path)
        assert r.status == "PASS"
        assert "no artifacts" in r.detail


def test_ges_compliant_warns_on_unknown_bonding_but_otherwise_passes():
    """Bonding 'unknown' is WARN-but-PASS (don't block; ask engineer)."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_grounding_electrode_system_compliant
    from pvess_calc.schema import GroundRod, Inputs, UferElectrode
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    inputs.service.grounding_electrode_system.rods = [GroundRod(), GroundRod()]
    inputs.service.grounding_electrode_system.ufer = UferElectrode()
    inputs.service.grounding_electrode_system.gec_main_size_awg = "4"
    inputs.service.grounding_electrode_system.bonded_to_neutral_at_service = "unknown"
    result = run(inputs)
    [r] = _check_grounding_electrode_system_compliant(result)
    assert r.status == "PASS"
    assert "WARN" in r.detail and "bonding" in r.detail


def test_roof_usable_area_sufficient_skipped_when_no_roof_sections():
    """K.2.6c — when the yaml has no roof_sections (legacy Smith
    Residence, scenario yamls), the check passes with a 'skipped' note
    — no false alarm on projects that pre-date K.2.6c."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_roof_usable_area_sufficient
    from pvess_calc.schema import Inputs
    # Use Austin yaml — known to have 0 roof_sections
    result = run(Inputs.from_yaml(
        PROJECT_ROOT / "projects" / "001-demo-austin" / "inputs.yaml"
    ))
    [r] = _check_roof_usable_area_sufficient(result)
    assert r.status == "PASS"
    assert "skipped" in r.detail


def test_roof_usable_area_sufficient_catches_over_packed_section():
    """Regression-bait: synthesize a section over-packed beyond its
    usable area → check FAILS with the offending section named."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_roof_usable_area_sufficient
    from pvess_calc.schema import Inputs, RoofSection
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml")
    inputs = inputs.model_copy(deep=True)
    inputs.site.roof_sections = [RoofSection(
        name="Cramped Roof", shape="rect",
        width_ft=20, height_ft=10,        # gross 200, usable ~119 after 1.5ft
        module_count=20,                  # 20 × 22 = 440 sqft > 119
    )]
    result = run(inputs)
    [r] = _check_roof_usable_area_sufficient(result)
    assert r.status == "FAIL"
    assert "Cramped Roof" in r.detail
    assert "over-packed" in r.detail


def test_roof_usable_area_sufficient_warns_on_obstruction_outside_bounds():
    """Regression-bait: obstruction at (30, 20) on a 20×10 roof is
    outside the bounding box — doctor PASSes but surfaces a WARN note."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_roof_usable_area_sufficient
    from pvess_calc.schema import Inputs, RoofObstruction, RoofSection
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    inputs.site.roof_sections = [RoofSection(
        name="South", shape="rect",
        width_ft=20, height_ft=10, module_count=4,
        obstructions=[RoofObstruction(
            kind="skylight", x_ft=30, y_ft=20,
            width_ft=3, height_ft=3,
        )],
    )]
    result = run(inputs)
    [r] = _check_roof_usable_area_sufficient(result)
    assert r.status == "PASS"
    assert "outside section bounds" in r.detail
    assert "South" in r.detail


def test_subpanel_slots_sufficient_passes_with_room():
    """Positive guard: panels with explicit headroom pass."""
    from pvess_calc.doctor import _check_subpanel_slots_sufficient
    from pvess_calc.schema import Inputs
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    inputs.service.msp_available_slots = 42
    inputs.service.msp_used_slots = 30          # 12 free
    [r] = _check_subpanel_slots_sufficient(inputs)
    assert r.status == "PASS"
    assert "1 panel" in r.detail or "1 panels" in r.detail


def test_dxf_text_no_overflow_passes_on_phoenix():
    """Contract test: after fit_dxf landed, Phoenix EE-2 schedule must be
    overflow-free."""
    from pvess_calc.calc.engine import run
    from pvess_calc.schema import Inputs
    result = run(Inputs.from_yaml(PHOENIX / "inputs.yaml"))
    [r] = _check_dxf_text_no_overflow(result)
    assert r.status == "PASS", r.detail


def test_dxf_wire_text_no_overlap_passes_on_active_fixtures():
    """Positive guard: EE-2/EE-2.1 conductors must clear visible labels."""
    from pvess_calc.calc.engine import run
    from pvess_calc.schema import Inputs

    for project in (PHOENIX, FRISCO):
        result = run(Inputs.from_yaml(project / "inputs.yaml"))
        [r] = _check_dxf_wire_text_no_overlap(result)
        assert r.status == "PASS", f"{project.name}: {r.detail}"


def test_dxf_wire_text_no_overlap_catches_crossed_text(monkeypatch):
    """Regression-bait: a conductor crossing a visible label must fail."""
    import ezdxf
    import pvess_calc.dxf.render as render_mod
    from pvess_calc.calc.engine import run
    from pvess_calc.schema import Inputs

    original = render_mod.render_dxf

    def crossed_label(result, out_path):
        original(result, out_path)
        doc = ezdxf.readfile(str(out_path))
        msp = doc.modelspace()
        msp.add_text(
            "REGRESSION LABEL",
            height=0.10,
            dxfattribs={"layer": "EQUIPMENT_TEXT"},
        ).set_placement((2.0, 7.0))
        msp.add_lwpolyline(
            [(2.30, 6.80), (2.30, 7.25)],
            dxfattribs={"layer": "WIRE_DC_POS"},
        )
        doc.saveas(str(out_path))

    monkeypatch.setattr(render_mod, "render_dxf", crossed_label)

    result = run(Inputs.from_yaml(FRISCO / "inputs.yaml"))
    [r] = _check_dxf_wire_text_no_overlap(result)
    assert r.status == "FAIL"
    assert "REGRESSION LABEL" in r.detail


def test_dxf_wire_text_no_overlap_catches_visible_attrib(monkeypatch):
    """Regression-bait: ACADE ATTRIB text is visible text, not metadata only."""
    import ezdxf
    import pvess_calc.dxf.render as render_mod
    from pvess_calc.calc.engine import run
    from pvess_calc.schema import Inputs

    original = render_mod.render_dxf

    def crossed_attrib(result, out_path):
        original(result, out_path)
        doc = ezdxf.readfile(str(out_path))
        block = doc.blocks.new("REGRESSION_ATTR_BLOCK")
        block.add_attdef(
            "TAG1",
            insert=(0, 0),
            dxfattribs={"layer": "ANNOTATION", "height": 0.10},
        )
        ins = doc.modelspace().add_blockref(
            "REGRESSION_ATTR_BLOCK",
            insert=(2.0, 7.0),
            dxfattribs={"layer": "EQUIPMENT"},
        )
        ins.add_auto_attribs({"TAG1": "VISIBLE ATTR"})
        doc.modelspace().add_lwpolyline(
            [(2.25, 6.80), (2.25, 7.25)],
            dxfattribs={"layer": "WIRE_DC_POS"},
        )
        doc.saveas(str(out_path))

    monkeypatch.setattr(render_mod, "render_dxf", crossed_attrib)

    result = run(Inputs.from_yaml(FRISCO / "inputs.yaml"))
    [r] = _check_dxf_wire_text_no_overlap(result)
    assert r.status == "FAIL"
    assert "VISIBLE ATTR" in r.detail


def test_pv5_text_no_overlap_passes_on_frisco():
    """Positive guard: reference PV-5 callout labels do not collide."""
    from pvess_calc.calc.engine import run
    from pvess_calc.schema import Inputs

    result = run(Inputs.from_yaml(FRISCO / "inputs.yaml"))
    [r] = _check_pv5_text_no_overlap(result)
    assert r.status == "PASS", r.detail


def test_pv5_text_no_overlap_catches_collided_callouts(monkeypatch):
    """Regression-bait: PV-5 text fragments at the same position fail."""
    import pvess_calc.permit.structural as structural_mod
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.pdfgen import canvas
    from pvess_calc.calc.engine import run
    from pvess_calc.schema import Inputs

    def overlapping_text(_result, out_path):
        c = canvas.Canvas(str(out_path), pagesize=landscape(letter))
        c.setFont("Helvetica", 10)
        c.drawString(100, 100, "OVERLAP A")
        c.drawString(102, 102, "OVERLAP B")
        c.save()

    monkeypatch.setattr(structural_mod, "render_mounting_details", overlapping_text)

    result = run(Inputs.from_yaml(FRISCO / "inputs.yaml"))
    [r] = _check_pv5_text_no_overlap(result)
    assert r.status == "FAIL"
    assert "OVERLAP A" in r.detail


def test_grounding_schedule_rows_fit_without_fit_dxf(monkeypatch):
    """Positive guard: every RUN string in the GROUNDING & BONDING
    SCHEDULE is short enough to fit its column without relying on
    `fit_dxf` to truncate at runtime.

    Previously (Phase J → 2026-05-13) the schedule had "MSP →
    grounding electrode system" and similar 30+ char RUN strings that
    only fit because fit_dxf chopped them with ellipses. On 2026-05-14
    we shortened the strings to fit by design (MSP → GES, etc.).

    This test disables fit_dxf and verifies the check still passes —
    so if someone re-introduces a long RUN string, this test fails
    immediately rather than letting fit_dxf silently truncate.
    """
    import pvess_calc.dxf.grounding_sheet as gs_mod
    monkeypatch.setattr(gs_mod, "fit_dxf",
                        lambda text, _max_w, _h: text)

    from pvess_calc.calc.engine import run
    from pvess_calc.schema import Inputs
    result = run(Inputs.from_yaml(PHOENIX / "inputs.yaml"))
    [r] = _check_dxf_text_no_overflow(result)
    assert r.status == "PASS", \
        f"a schedule RUN string is too long for its column even without "\
        f"fit_dxf — shorten the source string instead. detail: {r.detail}"


# ─── Registry self-consistency ────────────────────────────────────────────


def test_registry_codes_are_unique():
    cs = codes()
    assert len(set(cs)) == len(cs), \
        f"duplicate codes in SHEET_REGISTRY: {cs}"


def test_registry_display_codes_are_unique():
    ds = [s.display_code for s in SHEET_REGISTRY]
    assert len(set(ds)) == len(ds), \
        f"duplicate display codes in SHEET_REGISTRY: {ds}"


def test_registry_renderer_paths_are_resolvable():
    """Every renderer path must point to an importable callable."""
    import importlib
    for spec in SHEET_REGISTRY:
        module_name, _, callable_name = spec.renderer.partition(":")
        assert module_name and callable_name, \
            f"bad renderer path: {spec.renderer}"
        mod = importlib.import_module(module_name)
        assert hasattr(mod, callable_name), \
            f"{module_name} has no callable {callable_name!r}"


def test_registry_output_kinds_are_known():
    valid = {"pdf", "dxf", "labels"}
    for spec in SHEET_REGISTRY:
        assert spec.output_kind in valid, \
            f"sheet {spec.code}: unknown output_kind {spec.output_kind!r}"


# ─── K.8 production_breakdown_per_face check ────────────────────────────


def test_production_breakdown_per_face_passes_for_phoenix():
    """K.8 positive guard: Phoenix (S + W roofs, 30 modules each)
    must produce a 2-face breakdown with derate between 80%-95%."""
    from pvess_calc.doctor import _check_production_breakdown_per_face
    from pvess_calc.schema import Inputs
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml")
    [r] = _check_production_breakdown_per_face(inputs)
    assert r.status == "PASS"
    assert "2 face" in r.detail
    # Phoenix S+W blended derate is ~92%
    assert "9" in r.detail   # 9x%


def test_production_breakdown_per_face_skipped_for_single_orientation():
    """K.8 positive guard: a yaml with no roof_sections (Austin demo,
    Smith Residence) returns PASS-with-skip note — not a false alarm."""
    from pvess_calc.doctor import _check_production_breakdown_per_face
    from pvess_calc.schema import Inputs
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    inputs.site.roof_sections = []
    [r] = _check_production_breakdown_per_face(inputs)
    assert r.status == "PASS"
    assert "skipped" in r.detail


def test_production_breakdown_per_face_handles_k3c_init_state():
    """K.8.1 regression-bait: a project FRESH FROM `pvess init --address`
    has roof_sections from Google Solar but every section.module_count = 0
    (designer hasn't distributed yet). Pre-K.8.1 the doctor wrongly said
    'single-orientation skipped'; post-K.8.1 it must PASS the project
    AND flag that auto-distribution happened so the designer reviews."""
    from pvess_calc.doctor import _check_production_breakdown_per_face
    from pvess_calc.schema import Inputs
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    # Phoenix has 2 roof sections — keep them but zero the module counts.
    # This is exactly the K.3c-init state.
    for s in inputs.site.roof_sections:
        s.module_count = 0
    assert inputs.pv_array.modules > 0   # pre-condition

    [r] = _check_production_breakdown_per_face(inputs)
    assert r.status == "PASS"
    # Must NOT report "single-orientation" anymore — those have no sections.
    assert "single-orientation" not in r.detail
    # Must surface that auto-distribution happened so the engineer
    # remembers to commit a real distribution before AHJ submit.
    assert "auto-distributed" in r.detail
    assert "2 face" in r.detail


def test_production_breakdown_per_face_skipped_when_no_pv_declared():
    """K.8.1: if `pv_array.modules = 0` (test fixture for no-system
    edge cases), the check must PASS-skip cleanly even when sections
    exist — production is 0 by definition, no breakdown to validate."""
    from pvess_calc.doctor import _check_production_breakdown_per_face
    from pvess_calc.schema import Inputs
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    inputs.pv_array.modules = 0
    inputs.pv_array.strings = 0
    inputs.pv_array.modules_per_string = 0
    [r] = _check_production_breakdown_per_face(inputs)
    assert r.status == "PASS"
    assert "no PV declared" in r.detail or "skipped" in r.detail


def test_production_breakdown_per_face_fails_with_invalid_derate():
    """K.8 regression-bait: simulate the bug class "blended_derate
    out of range" by injecting impossibly steep tilts into the yaml.
    The orientation_derate table caps at 60° tilt → an out-of-range
    azimuth/tilt combo can drive derate < 0, which the check rejects.

    We synthesize the failure by monkey-patching `compute_economics`
    to return a bad blended_derate — proves the check actually
    inspects the field rather than blindly passing.
    """
    from unittest.mock import patch
    from pvess_calc.customer.economics import EconomicsResult
    from pvess_calc.customer.production import FaceProduction
    from pvess_calc.doctor import _check_production_breakdown_per_face
    from pvess_calc.schema import Inputs

    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml")
    bad = EconomicsResult(
        system_kw_dc=25.2, battery_kwh_total=41.0,
        annual_production_kwh=40000, production_source="nrel-pvwatts",
        utility_rate_usd_per_kwh=0.131, rate_source="lookup-utility-rate",
        monthly_bill_savings_usd=400, annual_bill_savings_usd=4800,
        annual_household_kwh=None, offset_pct=None,
        export_tariff_model="1to1_nem", export_tariff_label="x",
        self_consumption_fraction=0.5, export_ratio_applied=1.0,
        installed_cost_usd=100_000, cost_source="benchmark-estimate",
        payback_period_years=20.0,
        cost_after_itc_usd=70_000, payback_after_itc_years=14.0,
        itc_rate_used=0.30,
        production_breakdown=[
            FaceProduction(
                name="South", kw_dc=12.6, azimuth_deg=180, tilt_deg=22,
                orientation_derate=0.97, shading_factor=1.00,
                annual_production_kwh=21_400,
            ),
            FaceProduction(
                name="Broken", kw_dc=12.6, azimuth_deg=270, tilt_deg=22,
                orientation_derate=1.50,    # impossible, >1.0
                shading_factor=1.00, annual_production_kwh=33_000,
            ),
        ],
        production_blended_derate=0.92,    # valid (count + blended both OK)
    )
    with patch(
        "pvess_calc.customer.economics.compute_economics",
        return_value=bad,
    ):
        [r] = _check_production_breakdown_per_face(inputs)
    assert r.status == "FAIL"
    assert "out of range" in r.detail or "out of (0, 1]" in r.detail


# ─── K.8.2 — face_value_score_distinguishes_east_west doctor check ─────


def test_face_value_score_check_passes_with_current_math():
    """K.8.2 positive guard: the value-weighted math currently produces
    a ~12% E/W spread on 0.50× REP plans and collapses cleanly on 1:1.
    Drift sentry — break the SC pattern or the cos_incidence math and
    this fails before the next live `pvess-doctor` invocation."""
    from pvess_calc.doctor import _check_face_value_score_distinguishes_east_west
    [r] = _check_face_value_score_distinguishes_east_west()
    assert r.status == "PASS"
    assert "spread" in r.detail
    assert "0.50" in r.detail or "0.5" in r.detail


def test_face_value_score_check_fails_when_sc_pattern_is_flat(monkeypatch):
    """K.8.2 regression-bait: if someone "simplifies" the DFW SC
    pattern to a flat 0.50 (losing the AM/PM distinction), the
    West-vs-East spread collapses to 0 and the doctor catches it.
    Patch the default pattern, verify FAIL."""
    flat_pattern = (0.50,) * 24
    monkeypatch.setattr(
        "pvess_calc.calc.value_weighted.DEFAULT_DFW_SELF_CONSUMPTION_PATTERN",
        flat_pattern,
    )
    from pvess_calc.doctor import _check_face_value_score_distinguishes_east_west
    [r] = _check_face_value_score_distinguishes_east_west()
    assert r.status == "FAIL"
    assert "spread" in r.detail
    assert "AM/PM asymmetry" in r.detail or "0.08" in r.detail


# ─── K.9.5 — pv4_module_count_matches_yaml ──────────────────────────────


def test_pv4_module_count_check_passes_for_phoenix():
    """K.9.5 contract test: Phoenix has 60 modules across 2 explicit
    faces — placement should hit or near-hit the target. PASS."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_pv4_module_count_matches_yaml
    from pvess_calc.schema import Inputs
    result = run(Inputs.from_yaml(PHOENIX / "inputs.yaml"))
    [r] = _check_pv4_module_count_matches_yaml(result)
    assert r.status == "PASS"


def test_pv4_module_count_check_skips_austin_legacy():
    """Austin demo has no roof_sections → PASS-skip."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_pv4_module_count_matches_yaml
    from pvess_calc.schema import Inputs
    project_root = Path(__file__).resolve().parents[1]
    austin = project_root / "projects" / "001-demo-austin" / "inputs.yaml"
    result = run(Inputs.from_yaml(austin))
    [r] = _check_pv4_module_count_matches_yaml(result)
    assert r.status == "PASS"
    assert "single-orientation" in r.detail


def test_pv4_module_count_check_warns_on_significant_shortfall(monkeypatch):
    """Regression-bait: synthesise a 50-module array on 1 tiny face that
    can fit only ~5 → 90% shortfall → FAIL with redesign hint."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_pv4_module_count_matches_yaml
    from pvess_calc.schema import Inputs, RoofSection
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    inputs.pv_array.modules = 50
    inputs.pv_array.strings = 5
    inputs.pv_array.modules_per_string = 10
    # One small face — can fit maybe 5-6 modules max
    inputs.site.roof_sections = [
        RoofSection(name="Tiny", shape="rect",
                    width_ft=12, height_ft=12,
                    module_count=50),    # asks for 50
    ]
    result = run(inputs)
    [r] = _check_pv4_module_count_matches_yaml(result)
    assert r.status == "FAIL"
    assert "redesign" in r.detail.lower() or "over-designed" in r.detail


# ─── K.10.5: string balance within target ─────────────────────────────


def test_doctor_string_balance_passes_on_phoenix():
    """K.10.5 contract: Phoenix has 60 modules / 6 strings × 10. After
    K.10.1 face-coupled assignment every string holds exactly 10 →
    spread = 0, PASS."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_string_balance_within_target
    from pvess_calc.schema import Inputs
    result = run(Inputs.from_yaml(PHOENIX / "inputs.yaml"))
    [r] = _check_string_balance_within_target(result)
    assert r.status == "PASS"
    assert "spread=0" in r.detail


def test_doctor_string_balance_passes_on_frisco_shortfall():
    """K.10.5 positive guard for the live Frisco shape: 34 modules
    across 4 strings × 9 → [9, 9, 8, 8] → spread = 1, still PASS.

    This locks in the K.10.1 balanced-shortfall fix: a stray algorithm
    revert that re-introduces [9, 9, 9, 7] (spread = 2) would FAIL
    here even though doctor would still WARN-not-FAIL — the assertion
    on `spread=1` catches the regression precisely."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_string_balance_within_target
    from pvess_calc.schema import Inputs
    project_root = Path(__file__).resolve().parents[1]
    frisco = project_root / "projects" / "003-frisco-glasshouse" / "inputs.yaml"
    result = run(Inputs.from_yaml(frisco))
    [r] = _check_string_balance_within_target(result)
    assert r.status == "PASS"
    assert "spread=1" in r.detail or "spread=0" in r.detail


def test_doctor_string_balance_skips_legacy_austin():
    """Austin demo has no roof_sections (legacy) → no per-module
    placements → PASS-skip."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_string_balance_within_target
    from pvess_calc.schema import Inputs
    project_root = Path(__file__).resolve().parents[1]
    austin = project_root / "projects" / "001-demo-austin" / "inputs.yaml"
    result = run(Inputs.from_yaml(austin))
    [r] = _check_string_balance_within_target(result)
    assert r.status == "PASS"
    assert "legacy" in r.detail or "single-orientation" in r.detail


def test_doctor_string_balance_fails_on_drifted_allocation(monkeypatch):
    """K.10.5 regression-bait: monkey-patch the engine output so one
    string holds 12 modules and another holds 6 (spread=6). The check
    must FAIL with the K.10.1 algorithm-bug hint."""
    from dataclasses import replace
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_string_balance_within_target
    from pvess_calc.schema import Inputs
    result = run(Inputs.from_yaml(PHOENIX / "inputs.yaml"))

    # Synthesise a drifted allocation: re-bucket all modules into just
    # 2 string_indexes with deliberately unbalanced counts (12 vs 6).
    all_mods = [
        m for face_list in result.module_placements.values()
        for m in face_list
    ]
    assert len(all_mods) >= 18, "test fixture needs ≥ 18 placed modules"

    drifted = []
    for i, m in enumerate(all_mods):
        # First 12 → S0, next 6 → S1, rest → S2 (still ≤ target 10)
        if i < 12:
            new_s = 0
        elif i < 18:
            new_s = 1
        else:
            new_s = 2 + (i - 18) // 10
        drifted.append(replace(m, string_index=new_s))

    # Re-bucket into result.module_placements by face
    drifted_by_face = {}
    for m in drifted:
        drifted_by_face.setdefault(m.face_name, []).append(m)
    object.__setattr__(result, "module_placements", drifted_by_face)

    [r] = _check_string_balance_within_target(result)
    assert r.status == "FAIL"
    # The bug hint should mention the algorithm or the spread
    assert "exceed" in r.detail.lower() or "drift" in r.detail.lower() \
        or "spread" in r.detail.lower()


# ─── K.11.5: auto-routed wire lengths sanity ──────────────────────────


def test_doctor_auto_routed_lengths_skips_when_not_routed():
    """K.11.5 — Phoenix legacy yaml has no equipment_locations, so
    wire_routing.routed=False → PASS-skip with explanation."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_auto_routed_lengths_sane
    from pvess_calc.schema import Inputs
    result = run(Inputs.from_yaml(PHOENIX / "inputs.yaml"))
    [r] = _check_auto_routed_lengths_sane(result)
    assert r.status == "PASS"
    assert "legacy" in r.detail or "skipped" in r.detail


def test_doctor_auto_routed_lengths_passes_on_sane_geometry():
    """K.11.5 positive guard: realistic Phoenix-shaped equipment
    placement produces segment lengths well under 200 ft → PASS."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_auto_routed_lengths_sane
    from pvess_calc.schema import (
        EquipmentLocation, EquipmentLocations, Inputs,
    )
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    for section in inputs.site.roof_sections:
        section.site_anchor_x_ft = 20.0
        section.site_anchor_y_ft = 50.0
        section.site_anchor_azimuth_deg = 0.0
    inputs.site.equipment_locations = EquipmentLocations(
        msp=EquipmentLocation(label="MSP", x_ft=55, y_ft=42),
        inverters=[EquipmentLocation(label="INV-1", x_ft=55, y_ft=48)],
        ac_disconnect=EquipmentLocation(label="AC-DISC", x_ft=55, y_ft=46),
        ess_units=[EquipmentLocation(label="ESS-1", x_ft=55, y_ft=50)],
    )
    result = run(inputs)
    [r] = _check_auto_routed_lengths_sane(result)
    assert r.status == "PASS"
    assert "200 ft envelope" in r.detail


def test_doctor_auto_routed_lengths_fails_when_segment_exceeds_envelope():
    """K.11.5 regression-bait: equipment placed at absurd 500 ft away
    (likely unit / frame mismatch) → FAIL with frame-hint message."""
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_auto_routed_lengths_sane
    from pvess_calc.schema import (
        EquipmentLocation, EquipmentLocations, Inputs,
    )
    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml").model_copy(deep=True)
    for section in inputs.site.roof_sections:
        section.site_anchor_x_ft = 20.0
        section.site_anchor_y_ft = 50.0
        section.site_anchor_azimuth_deg = 0.0
    inputs.site.equipment_locations = EquipmentLocations(
        msp=EquipmentLocation(label="MSP", x_ft=500, y_ft=500),
        inverters=[EquipmentLocation(label="INV-1", x_ft=500, y_ft=500)],
    )
    result = run(inputs)
    [r] = _check_auto_routed_lengths_sane(result)
    assert r.status == "FAIL"
    assert "exceeds" in r.detail
    # The hint should mention the underlying frame issue
    assert "frame" in r.detail.lower() or "coords" in r.detail.lower()


# ─── Stage 9.9: EE-4A property-context data path ───────────────────────


def test_doctor_ee4a_property_context_passes_on_frisco():
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_ee4a_property_context_data_driven
    from pvess_calc.schema import Inputs

    result = run(Inputs.from_yaml(FRISCO / "inputs.yaml"))
    [r] = _check_ee4a_property_context_data_driven(result)
    assert r.status == "PASS", r.detail
    assert "dimension" in r.detail


def test_doctor_ee4a_property_context_skips_legacy_context():
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_ee4a_property_context_data_driven
    from pvess_calc.schema import Inputs

    inputs = Inputs.from_yaml(PHOENIX / "inputs.yaml")
    result = run(inputs)
    [r] = _check_ee4a_property_context_data_driven(result)
    assert r.status == "PASS"
    assert "fallback" in r.detail
