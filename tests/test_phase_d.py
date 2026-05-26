"""Phase D regression tests: voltage drop / AIC / device library / 310.15(B)
derating / NEC 2020 dispatch.

Each test maps back to a specific acceptance criterion in PHASE_D.md so a
single failure points at the spec line it broke.
"""
from __future__ import annotations

import pytest

from pvess_calc.calc.aic import available_fault_current, compute_aic
from pvess_calc.calc.engine import run
from pvess_calc.calc.voltage_drop import (
    LIMIT_AC_PCT, LIMIT_DC_PCT, compute_voltage_drop,
)
from pvess_calc.devices import (
    BATTERIES, INVERTERS, MODULES,
    get_battery, get_inverter, get_module,
)
from pvess_calc.nec import get_rules
from pvess_calc.nec.tables import (
    conduit_fill_adjustment, temperature_correction_75c,
)
from pvess_calc.schema import WireLengths
from tests.conftest import make_inputs


# --- §1: Voltage drop ------------------------------------------------------

def test_vd_short_runs_pass_per_nec_limits():
    """Short wire runs should keep all segments under their NEC limits."""
    inputs = make_inputs()
    inputs.wire_lengths = WireLengths(
        pv_string_one_way_ft=20,
        pv_to_combiner_ft=15,
        combiner_to_inverter_ft=10,
        inverter_to_ac_disc_ft=15,
        ac_disc_to_msp_ft=10,
        ess_to_inverter_ft=8,
    )
    result = run(inputs)
    vd = result.voltage_drop_analysis
    assert vd.overall_status == "PASS"
    for seg in vd.segments:
        assert seg.drop_pct <= seg.limit_pct, f"{seg.label} drop {seg.drop_pct}% > {seg.limit_pct}%"


def test_vd_per_subpanel_chain_expands_ac_trunk():
    """K.2.6a — when sub_panels carry distance_to_msp_ft, the AC trunk
    expands into a CHAIN of segments matching the wire path:
        AC-DISC →(25 ft)→ Sub#A →(35 ft)→ Sub#B →(15 ft global)→ MSP

    Each hop contributes its own drop. Total AC drop = sum of per-hop
    drops. Without K.2.6a the engine would have treated only the 15 ft
    final hop, silently under-reporting the trunk loss by ~80%.
    """
    inputs = make_inputs(
        sub_panels=[
            {"name": "Sub #A", "rating_a": 200, "busbar_a": 200,
             "distance_to_msp_ft": 25.0},
            {"name": "Sub #B", "rating_a": 200, "busbar_a": 200,
             "distance_to_msp_ft": 35.0},
        ],
    )
    inputs.wire_lengths = WireLengths(
        pv_string_one_way_ft=20,
        pv_to_combiner_ft=15,
        combiner_to_inverter_ft=10,
        inverter_to_ac_disc_ft=15,
        ac_disc_to_msp_ft=15,    # final Sub#B → MSP hop
    )
    result = run(inputs)
    vd = result.voltage_drop_analysis

    # The trunk has THREE segments now (D1 / D2 / D3), not one "D"
    trunk_segs = [s for s in vd.segments
                  if s.kind == "AC" and "→" in s.label
                  and not s.label.startswith("C")]
    assert len(trunk_segs) == 3
    labels = [s.label for s in trunk_segs]
    assert labels[0].startswith("D1") and "AC-DISC" in labels[0] and "Sub #A" in labels[0]
    assert labels[1].startswith("D2") and "Sub #A" in labels[1] and "Sub #B" in labels[1]
    assert labels[2].startswith("D3") and "Sub #B" in labels[2] and "MSP" in labels[2]
    assert trunk_segs[0].one_way_ft == 25.0
    assert trunk_segs[1].one_way_ft == 35.0
    assert trunk_segs[2].one_way_ft == 15.0


def test_vd_legacy_yaml_without_subpanel_distance_keeps_single_d_segment():
    """K.2.6a backward compat: when no sub-panel has distance_to_msp_ft,
    output exactly matches the pre-K.2.6 single-segment behaviour. This
    guards 4 years of existing golden-file outputs."""
    inputs = make_inputs(
        sub_panels=[
            {"name": "Sub #1", "rating_a": 200, "busbar_a": 200},
            # distance_to_msp_ft NOT set → defaults to 0.0
        ],
    )
    inputs.wire_lengths = WireLengths(
        pv_string_one_way_ft=20, pv_to_combiner_ft=15,
        combiner_to_inverter_ft=10, inverter_to_ac_disc_ft=15,
        ac_disc_to_msp_ft=10,
    )
    result = run(inputs)
    trunk_segs = [s for s in result.voltage_drop_analysis.segments
                  if s.label.startswith("D")]
    assert len(trunk_segs) == 1
    assert trunk_segs[0].label == "D · AC-DISC→MSP"


def test_vd_long_pv_run_fails_2_percent_limit():
    """A very long PV source run forces the segment past 2% DC limit.

    For the default 644V Voc string at 17 A on 10 AWG, ~500 ft is needed to
    exceed 2%. (PV's high DC voltage gives it a lot of headroom — this is
    the right behavior.)
    """
    inputs = make_inputs()
    inputs.wire_lengths = WireLengths(
        pv_string_one_way_ft=500,
        pv_to_combiner_ft=10,
        combiner_to_inverter_ft=10,
        inverter_to_ac_disc_ft=10,
        ac_disc_to_msp_ft=10,
    )
    result = run(inputs)
    pv_seg = next(s for s in result.voltage_drop_analysis.segments if s.label.startswith("A"))
    assert pv_seg.drop_pct > LIMIT_DC_PCT
    assert pv_seg.status == "FAIL"
    assert result.voltage_drop_analysis.overall_status == "FAIL"


def test_vd_default_fallback_when_yaml_missing_lengths():
    """If inputs.wire_lengths is empty, every segment should be DEFAULT."""
    inputs = make_inputs()
    # Leave wire_lengths at zeros (default)
    result = run(inputs)
    assert all(s.status == "DEFAULT" for s in result.voltage_drop_analysis.segments)
    assert result.voltage_drop_analysis.overall_status == "DEFAULT"


def test_vd_end_to_end_sums_dc_and_ac():
    """Total end-to-end = DC total + AC total."""
    inputs = make_inputs()
    inputs.wire_lengths = WireLengths(
        pv_string_one_way_ft=30, pv_to_combiner_ft=15,
        combiner_to_inverter_ft=15, inverter_to_ac_disc_ft=20,
        ac_disc_to_msp_ft=10,
    )
    result = run(inputs)
    vd = result.voltage_drop_analysis
    assert vd.total_end_to_end_pct == pytest.approx(vd.total_dc_pct + vd.total_ac_pct)


# --- §2: Device library ----------------------------------------------------

def test_module_library_has_required_brands():
    assert "talesun_tp7g54m_415" in MODULES
    assert "canadian_solar_hiku7_595" in MODULES
    assert "rec_alpha_pure_410" in MODULES


def test_inverter_library_has_required_brands():
    assert "sol_ark_12k" in INVERTERS
    assert "megarevo_r8klna" in INVERTERS
    assert "tesla_powerwall_3" in INVERTERS


def test_battery_library_has_required_brands():
    assert "tesla_powerwall_3" in BATTERIES
    assert "eg4_lifepower4_v2" in BATTERIES
    assert "franklinwh_apower" in BATTERIES


# ─── K.4.6.2 — DFW installer stack additions ────────────────────────────


def test_inverter_library_has_dfw_installer_us_stack():
    """K.4.6.2: the Frisco analysis uses the installer-carried US model
    families. Verify each exposed web option is registered, priced, and
    resolvable through get_inverter."""
    from pvess_calc.devices import INVERTER_PRICES_USD, get_inverter

    for ref in ("megarevo_r10klna",
                "growatt_min11400tl_xh_us",
                "hoymiles_hys_11_5lv_usg1"):
        assert ref in INVERTERS, f"missing inverter ref {ref!r}"
        assert ref in INVERTER_PRICES_USD, f"missing price for {ref!r}"
        inv = get_inverter(ref)
        # All three are 10-11.5 kW @ 240 V class.
        ac_kw = inv.ac_output_v * inv.ac_output_a / 1000.0
        assert 9.5 < ac_kw < 12.0, (
            f"{ref}: AC kW {ac_kw:.2f} out of expected US hybrid band"
        )


def test_inverter_wholesale_prices_distinct_from_retail_tier():
    """Closing standard: Chinese-OEM wholesale entries cost much less
    than the retail-resellable brands (Tesla / Sol-Ark). Guard against
    accidentally pricing Megarevo at Tesla MSRP, which would tank the
    K.4.6.3 cost-override math."""
    from pvess_calc.devices import INVERTER_PRICES_USD as P
    # Wholesale tier: ≤ $3,000 for any 8-12 kW hybrid
    for wholesale in ("megarevo_r8klna", "megarevo_r10klna",
                      "growatt_min11400tl_xh_us",
                      "hoymiles_hys_11_5lv_usg1"):
        assert P[wholesale] < 3000, (
            f"{wholesale} wholesale price ${P[wholesale]} crept into "
            "retail-tier range"
        )
    # Retail tier: ≥ $5,000
    for retail in ("sol_ark_12k", "tesla_powerwall_3"):
        assert P[retail] >= 5000, (
            f"{retail} retail price ${P[retail]} dropped below retail-tier"
        )


def test_battery_library_has_dfw_installer_hv_stack():
    """K.4.6.2: the user's actual battery offerings — 16 kWh in-house
    HV stack and 20 kWh Growatt APX HV. Both designed to pair with
    DC-coupled HV-input hybrid inverters (Megarevo R-series etc.)."""
    from pvess_calc.devices import BATTERY_PRICES_USD, get_battery

    for ref, expected_kwh in (("pytes_v16", 16.0),
                              ("hoymiles_hbx_10lv_usg1", 10.0),
                              ("growatt_apx_20kwh", 20.0)):
        assert ref in BATTERIES, f"missing battery ref {ref!r}"
        assert ref in BATTERY_PRICES_USD, f"missing price for {ref!r}"
        b = get_battery(ref)
        assert b.capacity_kwh_each == expected_kwh


def test_pytes_v16_battery_priced_below_retail_tier_per_kwh():
    """Sales-critical contract: the Pytes V16 battery costs
    materially less per kWh than Tesla PW3 (the retail reference).
    This is the user's main competitive advantage in TX — locking it
    here prevents a future "matched-to-MSRP" pricing regression."""
    from pvess_calc.devices import BATTERY_PRICES_USD as P
    pytes_per_kwh = P["pytes_v16"] / BATTERIES["pytes_v16"]["capacity_kwh_each"]
    tesla_per_kwh = P["tesla_powerwall_3"] / BATTERIES["tesla_powerwall_3"]["capacity_kwh_each"]
    # Pytes V16 should be <= 60% of Tesla per kWh (currently $375 vs $689)
    assert pytes_per_kwh < 0.60 * tesla_per_kwh, (
        f"Pytes V16 ${pytes_per_kwh:.0f}/kWh not significantly cheaper "
        f"than Tesla ${tesla_per_kwh:.0f}/kWh — sales advantage eroded"
    )


def test_get_inverter_unknown_ref_raises_keyerror():
    """Closing standard: unknown refs MUST raise a KeyError with the
    available-list in the message — silent fallbacks would let typos
    ship into customer PDFs."""
    from pvess_calc.devices import get_inverter
    with pytest.raises(KeyError, match="megarevo_r11klna"):
        # Misspelling — message lists available so we can spot the fix
        get_inverter("megaverso_r11klna")


def test_get_battery_unknown_ref_raises_keyerror():
    from pvess_calc.devices import get_battery
    with pytest.raises(KeyError, match="pytes_v16"):
        get_battery("pytes_16")    # wrong model key


def test_get_module_resolves_real_datasheet():
    m = get_module("talesun_tp7g54m_415")
    assert m.brand == "Talesun"
    assert 400 <= m.power_w <= 430
    assert m.voc_temp_coeff_pct_per_c is not None


def test_get_unknown_ref_raises_with_options():
    with pytest.raises(KeyError, match="Unknown PV module"):
        get_module("does_not_exist")


# --- §3: AIC ---------------------------------------------------------------

def test_available_fault_current_basic_formula():
    """25 kVA @ 2% Z, 240 V → 5208 A (typical residential pole-mount)."""
    isc = available_fault_current(kva=25, z_pct=2.0, v_secondary=240)
    assert isc == pytest.approx(5208, abs=1)


def test_aic_pass_with_default_residential_xfmr():
    """Default 25 kVA / 2% / 240V → ~5.2 kA; default 10 kAIC OCPDs → PASS."""
    inputs = make_inputs()
    result = run(inputs)
    assert result.aic.overall_status == "PASS"
    assert all(c.margin_ka > 0 for c in result.aic.ocpd_checks)


def test_aic_fails_with_large_transformer():
    """100 kVA @ 1.5% Z gives ~28 kA — well over a 10 kAIC residential breaker."""
    inputs = make_inputs()
    inputs.service.utility_transformer.kva = 100
    inputs.service.utility_transformer.impedance_pct = 1.5
    result = run(inputs)
    assert result.aic.overall_status == "FAIL"
    assert any(c.status == "FAIL" for c in result.aic.ocpd_checks)


# --- §4: NEC 310.15(B) derating --------------------------------------------

def test_temperature_correction_table_endpoints():
    assert temperature_correction_75c(25) == 1.05
    assert temperature_correction_75c(30) == 1.00
    assert temperature_correction_75c(45) == 0.82
    assert temperature_correction_75c(60) == 0.58


def test_conduit_fill_table_endpoints():
    assert conduit_fill_adjustment(3) == 1.00
    assert conduit_fill_adjustment(6) == 0.80
    assert conduit_fill_adjustment(9) == 0.70
    assert conduit_fill_adjustment(20) == 0.50


def test_derating_lowers_conductor_ampacity():
    """At 45°C ambient with 6 conductors, the combined factor is 0.82 × 0.80 = 0.656."""
    inputs = make_inputs()
    inputs.routing.ambient_temp_c = 45
    inputs.routing.pv_conduit_fill_count = 6
    inputs.routing.ac_conduit_fill_count = 6
    result = run(inputs)
    assert result.pv_derating_factor == pytest.approx(0.82 * 0.80, abs=1e-3)
    # PV conductor ampacity (derated) should be lower than the 75°C nominal.
    # 10 AWG @ 75°C nominal = 35 A; derated to 35 × 0.656 ≈ 23 A.
    assert result.pv_conductor.ampacity_a < 35


def test_default_routing_means_no_derating():
    inputs = make_inputs()
    # Defaults: 30°C, 3 conductors → factor = 1.0
    result = run(inputs)
    assert result.pv_derating_factor == 1.0
    assert result.ac_derating_factor == 1.0


# --- §5: NEC 2020 dispatch -------------------------------------------------

def test_nec_dispatch_returns_correct_version():
    assert get_rules("2023").EDITION == "2023"
    assert get_rules("2020").EDITION == "2020"
    # Unknown falls back to 2023
    assert get_rules("9999").EDITION == "2023"


def test_nec_2020_skips_sum_rule():
    """sum_rule is removed in NEC 2020; interconnect engine should mark it N/A."""
    inputs = make_inputs()
    inputs.project.nec_edition = "2020"
    result = run(inputs)
    sum_eval = next(
        e for e in result.interconnect.evaluations if e.method == "sum_rule"
    )
    assert sum_eval.status == "N/A"
    assert "2020" in sum_eval.formula or "2020" in sum_eval.explanation


def test_nec_2023_keeps_sum_rule_active():
    inputs = make_inputs()
    inputs.project.nec_edition = "2023"
    result = run(inputs)
    sum_eval = next(
        e for e in result.interconnect.evaluations if e.method == "sum_rule"
    )
    # PASS or FAIL — but not "N/A · removed"
    assert sum_eval.status in ("PASS", "FAIL")
