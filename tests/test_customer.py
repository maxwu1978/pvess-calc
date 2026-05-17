"""K.4 tests — customer summary economics / backup / PDF render.

Two layers of test:
  1. **Unit** (economics, backup) — known inputs → known numbers within
     a documented tolerance band. Lock the calc contract.
  2. **Render** (PDF) — both 'full data' and 'degraded' inputs must
     produce a valid non-trivial PDF. Closing standard #3 — additive
     compatibility.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pvess_calc.calc.engine import run
from pvess_calc.customer import (
    DEFAULT_USA_AVG_RATE_USD_PER_KWH,
    compute_backup,
    compute_economics,
)
from pvess_calc.customer.pdf import render_customer_summary
from pvess_calc.schema import Inputs


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHOENIX_YAML = PROJECT_ROOT / "projects" / "002-phoenix-25kw" / "inputs.yaml"


# ─── Economics unit tests ───────────────────────────────────────────────


def test_economics_phoenix_with_nrel_yields_industry_standard_production():
    """Closing standard #2: Phoenix 25 kW system with NREL @ 1757 kWh/kW.

    Pre-K.8: 25.2 kW × 1757 = 44,300 kWh (single-orientation math).
    K.8: Phoenix yaml has 2 roof faces — South @ 180°/22° (derate 0.97)
    and West @ 270°/22° (derate 0.86). Weighted avg ≈ 0.92 → 40,700 kWh.
    Both legitimate; the K.8 number is more honest for this multi-face
    array. Test now accepts the per-face range AND notes the breakdown.
    """
    inputs = Inputs.from_yaml(PHOENIX_YAML)
    lookup = {"annual_energy_kwh_per_kw": 1757.4}
    e = compute_economics(inputs, lookup_fields=lookup)

    assert e.system_kw_dc == pytest.approx(25.2, abs=0.1)
    # K.8 per-face math drops Phoenix from 44k → ~40-41k (S + W roofs).
    assert 39_000 < e.annual_production_kwh < 45_000
    assert e.production_source == "nrel-pvwatts"
    # K.8: multi-face Phoenix project produces a face-by-face breakdown.
    assert len(e.production_breakdown) == 2
    assert e.production_blended_derate is not None
    assert 0.85 < e.production_blended_derate < 0.99


def test_economics_uses_lookup_rate_when_present():
    """A city-specific rate ($0.131 Phoenix APS) overrides the USA avg."""
    inputs = Inputs.from_yaml(PHOENIX_YAML)
    lookup = {
        "annual_energy_kwh_per_kw": 1757.4,
        "avg_residential_rate_usd_per_kwh": 0.131,
    }
    e = compute_economics(inputs, lookup_fields=lookup)
    assert e.utility_rate_usd_per_kwh == pytest.approx(0.131)
    assert e.rate_source == "lookup-utility-rate"


def test_economics_falls_back_to_us_average_when_rate_absent():
    """Closing standard #4: graceful degradation when lookup empty."""
    inputs = Inputs.from_yaml(PHOENIX_YAML)
    e = compute_economics(inputs, lookup_fields={})
    assert e.utility_rate_usd_per_kwh == DEFAULT_USA_AVG_RATE_USD_PER_KWH
    assert e.rate_source == "usa-average"


def test_economics_latitude_fallback_when_no_nrel():
    """Latitude-based production estimate kicks in for projects without
    a NREL API key.

    Pre-K.8 baseline: 25.2 kW × 1600 ≈ 40,300 kWh.
    K.8 per-face: Phoenix has S (derate 0.97) + W (derate 0.86) roofs,
    blended ~0.915 → ~36,900 kWh. The per-face number is the honest one.
    """
    inputs = Inputs.from_yaml(PHOENIX_YAML)
    e = compute_economics(inputs, lookup_fields={"latitude": 33.5})
    assert e.production_source == "latitude-fallback"
    # K.8 per-face math: 1600 × 25.2 × 0.91 ≈ 37k (S+W blended).
    assert 35_000 < e.annual_production_kwh < 40_000


def test_economics_offset_pct_requires_12_months_of_usage():
    """offset_pct only computed when loads.monthly_kwh has 12 values."""
    inputs = Inputs.from_yaml(PHOENIX_YAML)
    e = compute_economics(inputs)
    # Phoenix yaml has no monthly_kwh → offset_pct must be None
    assert e.offset_pct is None

    # Mutate to add 12 months and verify offset_pct computes
    inputs2 = inputs.model_copy(deep=True)
    inputs2.loads.monthly_kwh = [3000] * 12   # 36 MWh/yr — undersized hh
    e2 = compute_economics(inputs2,
                           lookup_fields={"annual_energy_kwh_per_kw": 1757.4})
    assert e2.offset_pct is not None
    assert e2.offset_pct > 100   # 44k production > 36k usage


def test_economics_payback_uses_benchmark_cost_when_unspecified():
    inputs = Inputs.from_yaml(PHOENIX_YAML)
    e = compute_economics(inputs,
                          lookup_fields={"annual_energy_kwh_per_kw": 1757.4,
                                         "avg_residential_rate_usd_per_kwh": 0.131})
    assert e.cost_source == "benchmark-estimate"
    # 25.2 kW × $3.50/W = $88k PV + 41 kWh × $950 = $39k ESS = ~$127k
    assert 120_000 < e.installed_cost_usd < 135_000
    # $5,800/yr → ~22 yr payback before incentives
    assert e.payback_period_years is not None
    assert 20 < e.payback_period_years < 25


# ─── Backup unit tests ──────────────────────────────────────────────────


def test_backup_phoenix_baseline_in_range():
    """100A critical sub-panel × 240V × 0.15 diversity = 3.6 kW baseline.
    With 41 kWh × 0.90 usable = 36.9 kWh → 10.2 h essentials-only."""
    inputs = Inputs.from_yaml(PHOENIX_YAML)
    b = compute_backup(inputs)
    assert 3500 < b.critical_baseline_w < 3700
    assert 9 < b.backup_hours_loads_only < 12


def test_backup_no_critical_panel_uses_minimum_survival_load():
    """When loads.critical_subpanel_a is None, fallback to 500 W
    baseline — fridge + Wi-Fi + lights only."""
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.loads.critical_subpanel_a = None
    b = compute_backup(inputs)
    assert b.critical_baseline_w == 500.0


def test_backup_heat_pump_winter_dominates():
    """Heat-pump house: winter HVAC = 4500 W beats summer 3500 W cooling.
    Winter backup must be shorter than summer."""
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.loads.hvac_type = "heat_pump"
    b = compute_backup(inputs)
    assert b.backup_hours_winter < b.backup_hours_summer


# ─── PDF render — full data & degraded ──────────────────────────────────


def test_render_full_data_pdf(tmp_path: Path):
    """Closing standard #1: PDF renders in <5s; output >= 30 KB."""
    import time
    inputs = Inputs.from_yaml(PHOENIX_YAML)
    result = run(inputs)
    lookup = {
        "annual_energy_kwh_per_kw": 1757.4,
        "avg_residential_rate_usd_per_kwh": 0.131,
        "latitude": 33.45, "longitude": -112.07,
    }
    out = tmp_path / "customer.pdf"
    t0 = time.time()
    render_customer_summary(result, out, lookup_fields=lookup)
    elapsed = time.time() - t0

    assert out.exists()
    assert out.stat().st_size > 30_000
    assert elapsed < 5.0, f"render took {elapsed:.2f}s, expected <5s"


def test_render_degraded_no_lookup_no_monthly_kwh(tmp_path: Path):
    """Closing standard #3: a project with ZERO optional inputs (no
    lookup, no monthly_kwh, no NREL) must still produce a valid PDF.
    This is the additive-compatibility contract — old yamls don't
    break this layer."""
    inputs = Inputs.from_yaml(PHOENIX_YAML)
    result = run(inputs)
    out = tmp_path / "customer-degraded.pdf"
    render_customer_summary(result, out)  # no lookup_fields, no monthly override

    assert out.exists()
    # Still has system specs + savings (USA avg rate) + backup section +
    # production chart (latitude-band fallback), just no offset donut.
    assert out.stat().st_size > 25_000


def test_render_full_data_with_12_month_usage_includes_donut(tmp_path: Path):
    """When loads.monthly_kwh is supplied, offset_pct computes → donut
    chart is rendered (PDF will be larger than the no-usage variant)."""
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.loads.monthly_kwh = [
        1800, 1700, 2200, 2500, 3100, 3800,
        4100, 4000, 3500, 2800, 2000, 1900,
    ]   # ~33.4 MWh/yr — typical Phoenix
    result = run(inputs)
    out = tmp_path / "customer-with-donut.pdf"
    render_customer_summary(
        result, out,
        lookup_fields={"annual_energy_kwh_per_kw": 1757.4,
                       "avg_residential_rate_usd_per_kwh": 0.131},
    )
    assert out.exists()
    # Donut + usage overlay add ~10 KB on top of the no-donut variant.
    assert out.stat().st_size > 50_000


# ─── Design-token discipline ────────────────────────────────────────────


def test_design_tokens_have_documented_color_count():
    """Closing standard #4 (visual): ≤2 active accent colors (primary +
    accent) plus neutrals. Locks the palette so a future drift is
    caught."""
    from pvess_calc.customer import design_tokens as dt
    # The two accent colors:
    accents = {dt.COLOR_PRIMARY.hexval(), dt.COLOR_ACCENT.hexval()}
    assert len(accents) == 2

    # Plus exactly one success color for backup-success indicators.
    assert dt.COLOR_SUCCESS.hexval() not in accents


def test_default_export_tariff_is_1to1_nem():
    """K.7 [2/4] backward-compat: legacy yaml without explicit
    `export_tariff_model` defaults to 1:1 NEM and matches pre-K.7
    savings math exactly (self_cons=0.45 + export=1.0 = effective
    rate = retail, same as old code)."""
    inputs = Inputs.from_yaml(PHOENIX_YAML)
    e = compute_economics(inputs, lookup_fields={
        "annual_energy_kwh_per_kw": 1757.4,
        "avg_residential_rate_usd_per_kwh": 0.131,
    })
    assert e.export_tariff_model == "1to1_nem"
    assert e.export_ratio_applied == 1.0
    # Annual savings = annual production × retail (1:1 NEM):
    assert e.annual_bill_savings_usd == pytest.approx(
        e.annual_production_kwh * 0.131, rel=0.001,
    )


def test_ca_nem3_cuts_savings_by_about_40_percent():
    """K.7 [2/4] core contract: switching from 1:1 NEM to CA NEM 3.0
    at the default 0.45 self-consumption fraction drops annual
    savings ~40%. Locks the math against future drift."""
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)

    # Variant A: 1:1 NEM
    e1 = compute_economics(inputs, lookup_fields={
        "annual_energy_kwh_per_kw": 1500,
        "avg_residential_rate_usd_per_kwh": 0.275,
    })

    # Variant B: same project but NEM 3.0
    inputs.loads.export_tariff_model = "ca_nem3"
    e2 = compute_economics(inputs, lookup_fields={
        "annual_energy_kwh_per_kw": 1500,
        "avg_residential_rate_usd_per_kwh": 0.275,
    })

    assert e2.export_tariff_model == "ca_nem3"
    assert e2.export_ratio_applied == 0.27
    # NEM 3.0 baseline (0.45 self + 0.55 × 0.27 = 0.5985) vs 1:1 (1.00)
    # → ~40% reduction.
    reduction = (e1.annual_bill_savings_usd - e2.annual_bill_savings_usd) \
        / e1.annual_bill_savings_usd
    assert 0.35 < reduction < 0.45, (
        f"expected ~40% savings reduction, got {reduction*100:.0f}%"
    )


def test_smart_ess_scheduling_recovers_most_of_nem3_loss():
    """Closing the K.7 [2/4] story: a homeowner with well-tuned ESS
    (0.80 self-consumption) under NEM 3.0 recovers most of the lost
    savings vs naive 0.45 baseline. Demonstrates the design choice's
    tunable space."""
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.loads.export_tariff_model = "ca_nem3"

    # Naive: 0.45 self-consumption
    inputs.loads.self_consumption_fraction = 0.45
    e_naive = compute_economics(inputs, lookup_fields={
        "annual_energy_kwh_per_kw": 1500,
        "avg_residential_rate_usd_per_kwh": 0.275,
    })

    # Smart ESS: 0.80 self-consumption
    inputs.loads.self_consumption_fraction = 0.80
    e_smart = compute_economics(inputs, lookup_fields={
        "annual_energy_kwh_per_kw": 1500,
        "avg_residential_rate_usd_per_kwh": 0.275,
    })

    assert e_smart.annual_bill_savings_usd > e_naive.annual_bill_savings_usd
    # Smart ESS should recover ≥ 30% of the gap to a 1:1 NEM scenario.
    delta = e_smart.annual_bill_savings_usd - e_naive.annual_bill_savings_usd
    assert delta > 1500    # absolute >$1.5k/year recovery on LA-class project


def test_ca_nem3_disclaimer_appears_in_pdf(tmp_path: Path):
    """K.7 [2/4] PDF contract: a NEM 3.0 project's customer-summary
    must surface the tariff model in the Notes section, not the
    legacy hard-coded '1:1 net-metering' disclaimer."""
    import pypdf
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.loads.export_tariff_model = "ca_nem3"
    inputs.loads.self_consumption_fraction = 0.65

    out = tmp_path / "nem3-customer.pdf"
    render_customer_summary(run(inputs), out, lookup_fields={
        "annual_energy_kwh_per_kw": 1500,
        "avg_residential_rate_usd_per_kwh": 0.275,
    })
    text = "\n".join(
        page.extract_text() or "" for page in pypdf.PdfReader(str(out)).pages
    )
    assert "CA NEM 3.0" in text or "ACC tariff" in text, text[:500]
    # The old hardcoded line should NOT appear when tariff != 1to1_nem
    assert "assume 1:1 net-metering" not in text


def test_design_tokens_chart_kinds_limited_to_two():
    """≤2 chart types in the customer PDF — bar + donut only."""
    from pvess_calc.customer import design_tokens as dt
    assert dt.ALLOWED_CHART_KINDS == frozenset({"bar", "donut"})
    assert len(dt.ALLOWED_CHART_KINDS) == 2


# ─── K.4.5 polish: ITC + degraded layout + HVAC collapse ──────────────


def test_economics_exposes_post_itc_payback():
    """K.4.5 closing standard #3: hero block needs BOTH before-ITC and
    after-30%-ITC payback. The contract lives on the EconomicsResult
    object — verify both fields populate."""
    inputs = Inputs.from_yaml(PHOENIX_YAML)
    e = compute_economics(inputs,
                          lookup_fields={"annual_energy_kwh_per_kw": 1757.4,
                                         "avg_residential_rate_usd_per_kwh": 0.131})
    assert e.payback_period_years is not None
    assert e.payback_after_itc_years is not None
    # After-ITC payback must be 30% shorter (same savings, 70% cost)
    assert e.payback_after_itc_years == pytest.approx(
        e.payback_period_years * 0.70, rel=0.01
    )
    assert e.itc_rate_used == 0.30
    assert e.cost_after_itc_usd == pytest.approx(
        e.installed_cost_usd * 0.70, rel=0.001
    )


def test_economics_payback_after_itc_is_none_when_no_savings():
    """If annual_savings is somehow 0 (e.g., the rate dataset and
    PVWatts both miss), both pre and post ITC payback must be None —
    don't print 'inf years' to a homeowner."""
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.pv_array.modules = 0
    inputs.pv_array.strings = 0
    inputs.pv_array.modules_per_string = 0
    e = compute_economics(inputs)
    assert e.payback_period_years is None
    assert e.payback_after_itc_years is None


def test_render_degraded_omits_donut_block(tmp_path: Path):
    """K.4.5 closing standard #1: when no offset_pct → donut hidden +
    hero expands to full width. Compare file size against the variant
    that includes the donut — the donut is ~10 KB, so a no-donut PDF
    must be ≥15 KB smaller."""
    inputs = Inputs.from_yaml(PHOENIX_YAML)
    result_no_offset = run(inputs)   # no monthly_kwh → no offset

    inputs_with = inputs.model_copy(deep=True)
    inputs_with.loads.monthly_kwh = [3000] * 12
    result_with = run(inputs_with)

    no_donut = tmp_path / "no-donut.pdf"
    with_donut = tmp_path / "with-donut.pdf"
    render_customer_summary(result_no_offset, no_donut,
                            lookup_fields={"annual_energy_kwh_per_kw": 1757.4,
                                           "avg_residential_rate_usd_per_kwh": 0.131})
    render_customer_summary(result_with, with_donut,
                            lookup_fields={"annual_energy_kwh_per_kw": 1757.4,
                                           "avg_residential_rate_usd_per_kwh": 0.131})
    # Donut + 12-month usage overlay together add ~15 KB.
    diff = with_donut.stat().st_size - no_donut.stat().st_size
    assert diff > 15_000, (
        f"donut+overlay should add ≥15 KB; got diff={diff} B "
        f"(no_donut={no_donut.stat().st_size}, with={with_donut.stat().st_size})"
    )


def test_render_unknown_hvac_collapses_to_one_row(tmp_path: Path):
    """K.4.5 closing standard #2: hvac_type='unknown' produces a SINGLE
    'with typical HVAC load' row, not two duplicate-number rows.

    Verify by extracting PDF text and counting how many rows of the
    backup-runtime section appear."""
    import pypdf

    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.loads.hvac_type = "unknown"
    out = tmp_path / "unknown-hvac.pdf"
    render_customer_summary(run(inputs), out)

    text = "\n".join(p.extract_text() or "" for p in
                     pypdf.PdfReader(str(out)).pages)
    # Single combined row label is present:
    assert "typical HVAC load" in text
    # Per-season labels are NOT present:
    assert "AC running" not in text
    assert "heat pump heating" not in text
    assert "winter heating load" not in text


def test_render_known_hvac_shows_both_seasons_with_decimal(tmp_path: Path):
    """When hvac_type IS known, both summer + winter rows are present
    AND use .1f format so the 5.2 vs 4.6 distinction shows."""
    import pypdf

    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.loads.hvac_type = "heat_pump"
    out = tmp_path / "heat-pump.pdf"
    render_customer_summary(run(inputs), out)

    text = "\n".join(p.extract_text() or "" for p in
                     pypdf.PdfReader(str(out)).pages)
    # Two season rows present
    assert "AC running" in text
    assert "heat pump heating" in text
    # .1f format means we see "5.2" or "4.6" (with a decimal), not just "5"
    # Build a regex check: at least one of the HVAC rows has 'N.M h'
    import re
    hvac_decimals = re.findall(r"\b\d\.\d\s*h\b", text)
    assert len(hvac_decimals) >= 2, (
        f"expected ≥2 HVAC rows with decimal hours, got {hvac_decimals!r}"
    )


# ─── K.4.6.1 — battery-optional + PV-only render path ──────────────────


def test_battery_installed_property_reflects_quantity():
    """The new `Battery.installed` property must return False iff
    quantity = 0 and True for any positive count. Downstream code (PDF,
    doctor) reads this single flag instead of duplicating the > 0 check
    everywhere — proves the single source of truth."""
    from pvess_calc.schema import Battery
    common = dict(
        brand="X", model="Y", nominal_voltage=51.2,
        capacity_kwh_each=13.5, install_location="garage",
    )
    assert Battery(quantity=0, **common).installed is False
    assert Battery(quantity=1, **common).installed is True
    assert Battery(quantity=2, **common).installed is True
    # total_kwh property still works correctly for the 0 case
    assert Battery(quantity=0, **common).total_kwh == 0.0


def test_render_pv_only_collapses_spec_strip_and_backup(tmp_path: Path):
    """K.4.6.1 regression-bait: when battery.quantity = 0 (TX-market
    PV-only default), the customer PDF must:
      1. NOT print '0.0 kWh battery storage' in the spec strip
         (replaced with a 2-cell PV + inverter layout)
      2. Replace the 4-row backup runtime table with a single
         'PV-only — grid-tied, no outage backup' notice
      3. Still render cleanly (≥ 30 KB; backup block is the biggest
         single block, so cutting it shrinks the PDF noticeably)
    """
    import pypdf
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.battery.quantity = 0   # PV-only
    out = tmp_path / "pv-only.pdf"
    render_customer_summary(run(inputs), out,
                            lookup_fields={"annual_energy_kwh_per_kw": 1757.4})
    assert out.exists()
    assert out.stat().st_size > 30_000

    text = "\n".join(p.extract_text() or "" for p in
                     pypdf.PdfReader(str(out)).pages)
    # The PV-only banner must appear
    assert "PV-only" in text
    assert "grid-tied" in text or "outage" in text
    # And the misleading "0.0 kWh" line MUST NOT appear in spec strip
    assert "0.0 kWh" not in text
    # The backup runtime table rows must NOT appear
    assert "Essentials only" not in text
    assert "AC running" not in text


def test_render_with_battery_preserves_full_backup_table(tmp_path: Path):
    """Closing the contract from the other side: when a battery IS
    installed, the spec strip + backup table render as before. Catches
    the regression of "I made everything always-PV-only by accident"."""
    import pypdf
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    assert inputs.battery.installed is True   # precondition: Phoenix has 8 batt
    out = tmp_path / "with-battery.pdf"
    render_customer_summary(run(inputs), out,
                            lookup_fields={"annual_energy_kwh_per_kw": 1757.4})
    text = "\n".join(p.extract_text() or "" for p in
                     pypdf.PdfReader(str(out)).pages)
    # The battery cell in the spec strip
    assert "battery storage" in text
    assert "kWh" in text
    # Backup runtime table rows present
    assert "Essentials only" in text
    # PV-only notice MUST NOT appear
    assert "PV-only" not in text


# ─── K.4.6.3 — installer cost overrides ────────────────────────────────


def test_economics_without_overrides_keeps_benchmark_cost():
    """Backward compat: pre-K.4.6.3 yamls (no installer_cost_overrides
    block) must compute installed_cost identically to before. Locks
    the 'zero regression' contract."""
    inputs = Inputs.from_yaml(PHOENIX_YAML)
    assert inputs.project.installer_cost_overrides is None  # precondition
    e = compute_economics(inputs)
    assert e.cost_source == "benchmark-estimate"
    # Phoenix benchmark: 25.2 kW × $3.50/W = $88,200 PV
    #                  + 40.96 kWh × $950 = $38,912 ESS
    #                  ≈ $127,000 total (pre-K.4.6.3 baseline)
    assert 120_000 < e.installed_cost_usd < 135_000


def test_economics_installer_override_pv_turnkey_only():
    """K.4.6.3 path: yaml carries pv_turnkey_usd_per_w but no
    inverter/battery overrides. Cost = pv_turnkey × W_dc, period.
    No phantom inverter or battery cost added on top."""
    from pvess_calc.schema import InstallerCostOverrides
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.project.installer_cost_overrides = InstallerCostOverrides(
        pv_turnkey_usd_per_w=2.40,    # no refs, no totals
    )
    e = compute_economics(inputs)
    assert e.cost_source == "installer-override"
    # Pure PV-turnkey: 25.2 kW × 1000 × $2.40 = $60,480
    assert e.installed_cost_usd == pytest.approx(25.2 * 1000 * 2.40, rel=0.01)


def test_economics_installer_override_with_library_refs():
    """K.4.6.3 path: pv_turnkey + inverter_ref + battery_ref. Costs
    pulled from devices/* library × quantity. Verifies the contract
    K.4.6.5 3-tier-quote table will lean on."""
    from pvess_calc.devices import BATTERY_PRICES_USD, INVERTER_PRICES_USD
    from pvess_calc.schema import InstallerCostOverrides
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.project.installer_cost_overrides = InstallerCostOverrides(
        pv_turnkey_usd_per_w=2.40,
        inverter_ref="megarevo_r11klna",      # $2,000 wholesale
        battery_ref="inhouse_16kwh_hv",       # $6,000
    )
    e = compute_economics(inputs)
    expected = (
        25.2 * 1000 * 2.40                                           # PV
        + INVERTER_PRICES_USD["megarevo_r11klna"] * inputs.inverter.quantity
        + BATTERY_PRICES_USD["inhouse_16kwh_hv"] * inputs.battery.quantity
    )
    assert e.installed_cost_usd == pytest.approx(expected, rel=0.001)


def test_economics_explicit_total_wins_over_ref():
    """K.4.6.3 precedence: explicit `*_cost_usd_total` overrides
    `*_ref`. One-off custom equipment case."""
    from pvess_calc.schema import InstallerCostOverrides
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.project.installer_cost_overrides = InstallerCostOverrides(
        pv_turnkey_usd_per_w=2.40,
        inverter_ref="megarevo_r11klna",     # would give $2,000 × qty
        inverter_cost_usd_total=12_000,      # but this explicit value wins
        battery_cost_usd_total=8_500,
    )
    e = compute_economics(inputs)
    expected = 25.2 * 1000 * 2.40 + 12_000 + 8_500
    assert e.installed_cost_usd == pytest.approx(expected, rel=0.001)


def test_installer_overrides_pv_turnkey_validator():
    """Schema-level guard: pv_turnkey_usd_per_w must be >0 and
    flagged as unit error if >$10/W. Stops dollars-vs-cents mistakes
    landing in customer quotes."""
    from pvess_calc.schema import InstallerCostOverrides
    with pytest.raises(ValueError, match="must be > 0"):
        InstallerCostOverrides(pv_turnkey_usd_per_w=0.0)
    with pytest.raises(ValueError, match="unit error"):
        InstallerCostOverrides(pv_turnkey_usd_per_w=250)   # cents-as-dollars
    # Reasonable value passes
    ok = InstallerCostOverrides(pv_turnkey_usd_per_w=2.40)
    assert ok.pv_turnkey_usd_per_w == 2.40


def test_economics_override_battery_ref_skipped_for_pv_only():
    """K.4.6.3 + K.4.6.1 interaction: when battery.installed=False the
    override `battery_ref` is ignored (no phantom battery cost)."""
    from pvess_calc.schema import InstallerCostOverrides
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.battery.quantity = 0   # PV-only
    inputs.project.installer_cost_overrides = InstallerCostOverrides(
        pv_turnkey_usd_per_w=2.40,
        battery_ref="inhouse_16kwh_hv",    # would normally add $6,000
    )
    e = compute_economics(inputs)
    expected = 25.2 * 1000 * 2.40   # PV only, no battery added
    assert e.installed_cost_usd == pytest.approx(expected, rel=0.001)


# ─── K.4.6.4 — TX REP buyback picker ────────────────────────────────────


def test_economics_tx_green_mountain_preset_gives_1to1_rate():
    """K.4.6.4: tx_green_mountain preset = 1.00 export ratio →
    effective rate = retail (same as classic 1to1_nem). Verifies the
    preset table is wired."""
    from pvess_calc.customer.economics import EXPORT_RATIOS
    assert EXPORT_RATIOS["tx_green_mountain"] == 1.00

    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.loads.export_tariff_model = "tx_green_mountain"
    e = compute_economics(inputs, lookup_fields={
        "annual_energy_kwh_per_kw": 1535.0,
    })
    # With 1:1 ratio the effective rate equals retail rate exactly
    expected_rate = e.utility_rate_usd_per_kwh
    assert e.annual_bill_savings_usd == pytest.approx(
        e.annual_production_kwh * expected_rate, rel=0.001,
    )
    assert e.export_ratio_applied == 1.00
    assert "Green Mountain" in e.export_tariff_label


def test_economics_tx_default_oncor_at_half_retail():
    """K.4.6.4: tx_default_oncor = 0.50 export ratio — most TX
    customers' starting point if they don't actively switch REP.
    Quantifies the cost of staying on the default plan."""
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.loads.export_tariff_model = "tx_default_oncor"
    inputs.loads.self_consumption_fraction = 0.30   # PV-only typical
    e = compute_economics(inputs)
    # effective_rate = retail × (0.30 + 0.70 × 0.50) = retail × 0.65
    expected_rate = e.utility_rate_usd_per_kwh * (0.30 + 0.70 * 0.50)
    assert e.annual_bill_savings_usd == pytest.approx(
        e.annual_production_kwh * expected_rate, rel=0.001,
    )
    assert e.export_ratio_applied == 0.50


def test_economics_rep_buyback_ratio_overrides_named_tariff():
    """K.4.6.4 escape hatch: explicit `rep_buyback_ratio` wins over
    `export_tariff_model`. Use case: REP plan not in preset list, or
    mid-year rate change before we update the constants."""
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.loads.export_tariff_model = "tx_default_oncor"   # → 0.50
    inputs.loads.rep_buyback_ratio = 0.85                   # custom override
    inputs.loads.rep_plan_name = "TXU OnTrack Solar Special 2026"
    e = compute_economics(inputs)
    assert e.export_ratio_applied == 0.85
    assert e.export_tariff_model == "tx_rep_custom"
    assert "TXU OnTrack" in e.export_tariff_label


def test_loads_rep_buyback_ratio_range_validator():
    """Schema-level guard: rep_buyback_ratio must be in [0, 1]
    (it's a fraction of retail, not a multiplier). Catches yaml
    typos like 0.85 → 85 (intended percent)."""
    from pvess_calc.schema import Loads
    # OK values
    Loads(rep_buyback_ratio=0.0)
    Loads(rep_buyback_ratio=1.0)
    Loads(rep_buyback_ratio=0.5)
    # Fails
    with pytest.raises(ValueError, match="rep_buyback_ratio"):
        Loads(rep_buyback_ratio=85)         # percent-as-fraction typo
    with pytest.raises(ValueError, match="rep_buyback_ratio"):
        Loads(rep_buyback_ratio=-0.1)
