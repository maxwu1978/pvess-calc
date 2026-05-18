"""End-to-end: example project inputs.yaml → report.md + system.qet."""
from __future__ import annotations

from pathlib import Path

from pvess_calc.calc.engine import run
from pvess_calc.qet.inject import inject_from_result
from pvess_calc.report.markdown import render
from pvess_calc.schema import Inputs


def test_smith_residence_example_runs_clean(repo_root: Path, tmp_path: Path):
    project_dir = repo_root / "projects" / "001-demo-austin"
    inputs = Inputs.from_yaml(project_dir / "inputs.yaml")
    result = run(inputs)

    # Sanity-check key numbers from the user's worked example.
    assert result.interconnect.total_backfeed_a == 60.0
    assert result.interconnect.recommended == "supply_side_tap"
    assert result.interconnect.overall_status == "PASS"

    # OCPD = next standard ≥ Isc × 1.25 × 1.25 = 21.5625 → 25 A
    assert result.pv_ocpd_a == 25

    # Markdown report renders without exception, mentions key values.
    md = render(result)
    assert "Smith Residence ESS" in md
    assert "supply_side_tap" in md
    assert "25 A" in md
    assert "120%_rule" in md

    # QET injection works against the shipped template.
    template = repo_root / "library" / "templates" / "residential-ess-v0.qet"
    out = tmp_path / "system.qet"
    report = inject_from_result(result, template, out, strict=True)
    assert "{{" not in out.read_text(encoding="utf-8")
    assert report.substitutions_applied > 20


def test_pv_only_report_skips_ess_install_warning(repo_root: Path):
    project_dir = repo_root / "projects" / "003-frisco-glasshouse"
    result = run(Inputs.from_yaml(project_dir / "inputs.yaml"))

    md = render(result)
    assert "PV-only project" in md
    assert "install_location_specified" not in md
    assert "Raceway schedule（H.2）" in md
    assert "区域规则 / Utility 提交（Phase I）" in md
    assert "| B | PV DC OUTPUT |" in md


def test_report_renders_configured_raceway_type(repo_root: Path):
    project_dir = repo_root / "projects" / "003-frisco-glasshouse"
    inputs = Inputs.from_yaml(project_dir / "inputs.yaml")
    inputs.routing.ac_raceway_type = "PVC80"
    result = run(inputs)

    md = render(result)
    assert "PVC80" in md
    assert "| D | SUPPLY TAP |" in md
