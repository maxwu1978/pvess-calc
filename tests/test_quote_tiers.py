"""K.4.6.5 — 3-tier quote table tests.

Two layers of coverage:
  1. **Pure data** (`compute_quote_tiers`) — locks the math contract:
     all tiers share annual production / monthly savings (PV array
     unchanged), but cost + payback + backup-capability vary by which
     battery is swapped in.
  2. **PDF render** — the `_quote_tiers_block` actually appears in the
     output PDF when `loads.backup_options` is non-empty, and stays
     OUT when the list is empty (backward compat for every pre-K.4.6.5
     yaml).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pvess_calc.calc.engine import run
from pvess_calc.customer.pdf import render_customer_summary
from pvess_calc.customer.quote_tiers import compute_quote_tiers
from pvess_calc.schema import BackupOption, Inputs


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHOENIX_YAML = PROJECT_ROOT / "projects" / "002-phoenix-25kw" / "inputs.yaml"


# ─── compute_quote_tiers — pure data ────────────────────────────────────


def test_quote_tiers_empty_options_returns_only_base():
    """Backward compat: when `loads.backup_options` is empty (every
    pre-K.4.6.5 yaml), the function returns a single base tier.
    Caller (pdf.py) interprets 1-element list = skip the block."""
    inputs = Inputs.from_yaml(PHOENIX_YAML)
    assert inputs.loads.backup_options == []   # precondition
    tiers = compute_quote_tiers(inputs)
    assert len(tiers) == 1
    assert tiers[0].is_base is True


def test_quote_tiers_three_columns_with_two_options():
    """K.4.6.5: 2 backup options → 3 tiers total (base + 2)."""
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.battery.quantity = 0   # PV-only base
    inputs.loads.backup_options = [
        BackupOption(name="+ 16 kWh", battery_ref="inhouse_16kwh_hv"),
        BackupOption(name="+ 20 kWh", battery_ref="growatt_apx_20kwh"),
    ]
    tiers = compute_quote_tiers(inputs)
    assert len(tiers) == 3
    assert tiers[0].is_base
    assert not tiers[1].is_base
    assert not tiers[2].is_base
    # Base name reflects PV-only state (no brand to print).
    assert "PV-only" in tiers[0].name


def test_quote_tiers_share_monthly_savings():
    """**The K.4.6 narrative payoff**: every tier earns the same
    monthly savings (PV array is identical → kWh is identical → bill
    offset is identical). The upgrade decision is backup-vs-cost,
    NOT savings-vs-cost. Lock this invariant — if it ever fails,
    something is double-counting battery effects into savings."""
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.battery.quantity = 0
    inputs.loads.backup_options = [
        BackupOption(name="+ 16", battery_ref="inhouse_16kwh_hv"),
        BackupOption(name="+ 20", battery_ref="growatt_apx_20kwh"),
    ]
    tiers = compute_quote_tiers(inputs,
                                lookup_fields={"annual_energy_kwh_per_kw": 1757.4})
    base_savings = tiers[0].monthly_savings_usd
    for t in tiers[1:]:
        assert t.monthly_savings_usd == pytest.approx(base_savings, rel=0.001)


def test_quote_tiers_costs_increase_monotonically_with_battery():
    """Closing standard: bigger battery → higher cost. Catches a
    regression where the swap-in path misses applying the battery
    cost (e.g., breaking the installer_cost_overrides redirect)."""
    from pvess_calc.schema import InstallerCostOverrides
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.battery.quantity = 0
    inputs.project.installer_cost_overrides = InstallerCostOverrides(
        pv_turnkey_usd_per_w=2.40,
        inverter_ref="megarevo_r11klna",
    )
    inputs.loads.backup_options = [
        BackupOption(name="+ 16", battery_ref="inhouse_16kwh_hv"),     # $6k
        BackupOption(name="+ 20", battery_ref="growatt_apx_20kwh"),    # $10k
    ]
    tiers = compute_quote_tiers(inputs)
    # Each step up must be ≥ $4k more (the cheapest battery is $6k)
    assert tiers[1].installed_cost_usd > tiers[0].installed_cost_usd + 4000
    assert tiers[2].installed_cost_usd > tiers[1].installed_cost_usd + 2000


def test_quote_tiers_unknown_battery_ref_falls_back_silently():
    """Resilience: a typo in `battery_ref` should NOT crash compute_
    quote_tiers — the tier just shows 0 kWh battery (caught by the
    K.4.6.6 doctor check, planned). Loud crashes here would kill
    the customer PDF for the whole project."""
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.battery.quantity = 0
    inputs.loads.backup_options = [
        BackupOption(name="+ typo", battery_ref="megarevo_battery_typo"),
    ]
    tiers = compute_quote_tiers(inputs)
    assert len(tiers) == 2
    # The typo'd tier should have 0 kWh battery + "none" backup
    assert tiers[1].battery_kwh_total == 0.0
    assert "none" in tiers[1].backup_summary


def test_quote_tiers_backup_summary_shows_both_essentials_and_ac():
    """K.4.6.5 PDF layout decision: show TWO numbers per battery tier
    so the homeowner sees realistic AC-running hours vs essentials-
    only hours. One-number rendering was misleading (it hid the AC
    drain that homeowners always ask about)."""
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.battery.quantity = 0
    inputs.loads.backup_options = [
        BackupOption(name="+ 16", battery_ref="inhouse_16kwh_hv"),
    ]
    tiers = compute_quote_tiers(inputs)
    summary = tiers[1].backup_summary
    # Both number-and-label segments must appear
    assert "essentials" in summary
    assert "w/ AC" in summary
    # The essentials number must be larger than the AC number
    # (AC adds load → shorter runtime). Format: "~6 hr essentials  ·  ~2 hr w/ AC"
    import re
    nums = re.findall(r"(\d+)\s*hr", summary)
    assert len(nums) == 2
    assert int(nums[0]) >= int(nums[1])   # essentials ≥ AC-running


# ─── PDF render — block present/absent based on yaml ────────────────────


def test_render_with_backup_options_includes_tier_block(tmp_path: Path):
    """K.4.6.5 contract: when `loads.backup_options` is set, the
    customer PDF must contain a 'Your options' header + each tier's
    name. Verifies the wiring from yaml → compute_quote_tiers →
    _quote_tiers_block → reportlab output."""
    import pypdf
    inputs = Inputs.from_yaml(PHOENIX_YAML).model_copy(deep=True)
    inputs.battery.quantity = 0    # PV-only base
    inputs.loads.backup_options = [
        BackupOption(name="+ TestBatteryA",
                     battery_ref="inhouse_16kwh_hv"),
        BackupOption(name="+ TestBatteryB",
                     battery_ref="growatt_apx_20kwh"),
    ]
    out = tmp_path / "3-tier.pdf"
    render_customer_summary(run(inputs), out,
                            lookup_fields={"annual_energy_kwh_per_kw": 1757.4})
    text = "\n".join(
        p.extract_text() or "" for p in pypdf.PdfReader(str(out)).pages
    )
    assert "Your options" in text
    assert "TestBatteryA" in text
    assert "TestBatteryB" in text
    # The K.4.6 narrative blurb must appear
    assert "Same monthly savings" in text or "identical" in text


def test_render_without_backup_options_omits_tier_block(tmp_path: Path):
    """Backward compat: empty `backup_options` → no 'Your options'
    block. Every pre-K.4.6.5 yaml renders exactly as before."""
    import pypdf
    inputs = Inputs.from_yaml(PHOENIX_YAML)
    assert inputs.loads.backup_options == []  # precondition
    out = tmp_path / "no-tiers.pdf"
    render_customer_summary(run(inputs), out,
                            lookup_fields={"annual_energy_kwh_per_kw": 1757.4})
    text = "\n".join(
        p.extract_text() or "" for p in pypdf.PdfReader(str(out)).pages
    )
    assert "Your options" not in text
