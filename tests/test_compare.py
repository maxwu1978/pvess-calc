"""Phase E tests: scenario comparison + BOM."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pvess_calc.calc.engine import run
from pvess_calc.compare.bom import FIXED_BOM_USD, compute_bom
from pvess_calc.compare.report import render_json, render_markdown
from pvess_calc.compare.scenarios import (
    ScenarioResult, load_scenarios, run_scenarios,
)
from pvess_calc.schema import Inputs
from tests.conftest import make_inputs


# --- BOM ----

def test_bom_includes_modules_inverter_battery(tmp_path: Path):
    """Every BOM should have at least PV + inverter + battery lines."""
    result = run(make_inputs())
    bom = compute_bom(result)
    labels = " ".join(l.label for l in bom.lines)
    assert "PV module" in labels
    assert "Inverter" in labels
    # Default fixture has per_unit=True → battery line skipped (integrated)
    # so check it's there only when not integrated:
    if not result.inputs.inverter.per_unit:
        assert "Battery" in labels


def test_bom_subtotal_matches_line_sum():
    result = run(make_inputs())
    bom = compute_bom(result)
    sum_lines = sum(l.total_usd for l in bom.lines)
    assert abs(bom.subtotal_usd - sum_lines) < 0.01


def test_bom_skips_battery_for_powerwall_style_integrated():
    """When inverter.per_unit=True (integrated PW3), don't double-count battery."""
    inputs = make_inputs(per_unit=True, battery_qty=2)
    result = run(inputs)
    bom = compute_bom(result)
    bat_lines = [l for l in bom.lines if "Battery" in l.label]
    assert len(bat_lines) == 0


def test_bom_fixed_lines_present():
    """Fixed line items (RSD, AC disc, conduit, wire, labels, hardware) appear."""
    result = run(make_inputs())
    bom = compute_bom(result)
    labels = {l.label for l in bom.lines}
    for fixed in ("Rapid shutdown device", "AC disconnect (fused)",
                  "Conduit + fittings (est.)", "Labels & placards kit"):
        assert fixed in labels


def test_bom_includes_subpanel_when_present():
    inputs = make_inputs()
    from pvess_calc.schema import SubPanel
    inputs.service.sub_panels = [
        SubPanel(name="Sub Panel #1", rating_a=200, busbar_a=200),
    ]
    result = run(inputs)
    bom = compute_bom(result)
    labels = " ".join(l.label for l in bom.lines)
    assert "Sub-panel" in labels


# --- Scenario loader ----

def test_load_scenarios_discovers_subdirs(tmp_path: Path, monkeypatch):
    """A folder with A/B/C subdirs each holding inputs.yaml is found."""
    repo_root = Path(__file__).resolve().parents[1]
    src_yaml = repo_root / "projects" / "001-demo-austin" / "inputs.yaml"
    scenarios_dir = tmp_path / "scenarios"
    for name in ("A", "B", "C"):
        sub = scenarios_dir / name
        sub.mkdir(parents=True)
        shutil.copy(src_yaml, sub / "inputs.yaml")
    found = load_scenarios(scenarios_dir)
    assert {n for n, _ in found} == {"A", "B", "C"}


def test_run_scenarios_returns_complete_results(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    src_yaml = repo_root / "projects" / "001-demo-austin" / "inputs.yaml"
    scenarios_dir = tmp_path / "sx"
    for name in ("small", "large"):
        sub = scenarios_dir / name
        sub.mkdir(parents=True)
        shutil.copy(src_yaml, sub / "inputs.yaml")
    results = run_scenarios(scenarios_dir)
    assert len(results) == 2
    for r in results:
        assert r.name in ("small", "large")
        assert r.bom.subtotal_usd > 0
        assert r.result.interconnect.recommended is not None


# --- Report rendering ----

def test_markdown_report_has_all_summary_metrics(tmp_path: Path):
    """Comparison markdown should include every key metric column."""
    repo_root = Path(__file__).resolve().parents[1]
    src_yaml = repo_root / "projects" / "001-demo-austin" / "inputs.yaml"
    scenarios_dir = tmp_path / "sx"
    sub = scenarios_dir / "A"
    sub.mkdir(parents=True)
    shutil.copy(src_yaml, sub / "inputs.yaml")
    results = run_scenarios(scenarios_dir)
    md = render_markdown(results)
    for expected in ("PV (kW)", "AC (kW)", "Interconnect", "Voc cold (V)",
                     "AIC margin", "BOM (USD)"):
        assert expected in md
    assert "BOM Breakdown" in md
    assert "Subtotal" in md


def test_json_report_is_valid_json(tmp_path: Path):
    import json
    repo_root = Path(__file__).resolve().parents[1]
    src_yaml = repo_root / "projects" / "001-demo-austin" / "inputs.yaml"
    scenarios_dir = tmp_path / "sx"
    sub = scenarios_dir / "A"
    sub.mkdir(parents=True)
    shutil.copy(src_yaml, sub / "inputs.yaml")
    results = run_scenarios(scenarios_dir)
    raw = render_json(results)
    parsed = json.loads(raw)
    assert isinstance(parsed, list)
    assert len(parsed) == 1
    assert "bom_subtotal_usd" in parsed[0]
