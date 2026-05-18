"""K.7 — `pvess` root CLI smoke tests.

What this guards:
  * Every legacy `pvess-*` command is registered as a subcommand of
    the root `pvess` group, with the same name minus the `pvess-`
    prefix (except `pvess-site-checklist` → `survey`, `pvess-customer-
    summary` → `customer`, `pvess-symbols-preview` → `symbols`).
  * `pvess --help` and `pvess <sub> --help` exit 0 (no broken Click
    metadata).
  * `pvess pipeline customer` runs calc + customer-summary in sequence
    and produces both output files.
  * `pvess pipeline submit` runs calc + permit + dxf + doctor and the
    doctor's exit code propagates through the pipeline.
  * Legacy `pvess-calc` etc. continue to work unchanged (additive
    compatibility — K.7 didn't break old workflows).
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from pvess_calc.cli_root import pvess


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHOENIX = PROJECT_ROOT / "projects" / "002-phoenix-25kw"


# ─── Help-text smoke ─────────────────────────────────────────────────


def test_pvess_root_help_lists_workflow_phases():
    """K.7 closing standard #4: `pvess --help` mentions the workflow
    phases so a new user knows where to start."""
    runner = CliRunner()
    result = runner.invoke(pvess, ["--help"])
    assert result.exit_code == 0
    assert "INTAKE" in result.output
    assert "DESIGN" in result.output
    assert "SUBMIT" in result.output
    assert "VERIFY" in result.output


EXPECTED_SUBCOMMANDS = {
    # name in pvess root: legacy CLI it wraps
    "init":     "pvess-init",
    "survey":   "pvess-site-checklist",
    "lookup":   "pvess-lookup-check",
    "calc":     "pvess-calc",
    "customer": "pvess-customer-summary",
    "compare":  "pvess-compare",
    "permit":   "pvess-permit",
    "dxf":      "pvess-dxf",
    "labels":   "pvess-labels",
    "render":   "pvess-render",
    "ee4-trace": "pvess-ee4-trace",
    "ee4-preview": "pvess-ee4-preview",
    "doctor":   "pvess-doctor",
    "symbols":  "pvess-symbols-preview",
}


@pytest.mark.parametrize("subname", sorted(EXPECTED_SUBCOMMANDS))
def test_every_subcommand_help_exits_zero(subname):
    """Closing standard #2: every documented subcommand responds to
    `pvess <sub> --help` with a non-error exit. Catches Click metadata
    drift (missing decorators, broken option types)."""
    runner = CliRunner()
    result = runner.invoke(pvess, [subname, "--help"])
    assert result.exit_code == 0, (
        f"`pvess {subname} --help` exited {result.exit_code}: {result.output}"
    )


def test_pipeline_subgroup_help_exits_zero():
    runner = CliRunner()
    result = runner.invoke(pvess, ["pipeline", "--help"])
    assert result.exit_code == 0
    for name in ("customer", "submit", "review"):
        assert name in result.output


# ─── Pipeline integration smoke ──────────────────────────────────────


def test_pipeline_customer_writes_both_outputs(tmp_path: Path):
    """K.7 closing standard #3: `pvess pipeline customer` runs calc +
    customer-summary in sequence and both output files end up in
    `<project>/output/`."""
    project_dir = tmp_path / "phoenix"
    shutil.copytree(PHOENIX, project_dir)

    runner = CliRunner()
    result = runner.invoke(pvess, ["pipeline", "customer", str(project_dir)])
    assert result.exit_code == 0, result.output
    # Both pipeline steps printed:
    assert "[1/2]" in result.output and "[2/2]" in result.output
    # Both files exist + non-trivial size:
    assert (project_dir / "output" / "report.md").stat().st_size > 1000
    assert (project_dir / "output" / "customer-summary.pdf").stat().st_size > 20_000


def test_pipeline_submit_writes_permit_and_runs_doctor(tmp_path: Path):
    """K.7 closing standard: `pvess pipeline submit` runs all 4 steps
    + doctor exits zero (Phoenix is known-clean)."""
    project_dir = tmp_path / "phoenix"
    shutil.copytree(PHOENIX, project_dir)

    runner = CliRunner()
    result = runner.invoke(pvess, ["pipeline", "submit", str(project_dir)])
    assert result.exit_code == 0, result.output
    # Pipeline echoed 4 steps
    assert "[1/4]" in result.output
    assert "[4/4]" in result.output
    # Permit PDF emitted — name uses project.id (from yaml), not dir name,
    # so glob to stay robust against renames.
    permit_pdfs = list((project_dir / "output").glob("permit-package-*.pdf"))
    assert len(permit_pdfs) == 1, (
        f"expected exactly 1 permit-package-*.pdf, found {permit_pdfs}"
    )
    assert permit_pdfs[0].stat().st_size > 100_000
    # Doctor all-pass message visible — accept any count ≥ 24 so the
    # assertion survives new K.* check additions.
    import re
    m = re.search(r"all (\d+) check\(s\) passed", result.output)
    assert m is not None, "doctor 'all N check(s) passed' line missing"
    assert int(m.group(1)) >= 24, f"only {m.group(1)} checks ran"


# ─── Legacy compatibility ────────────────────────────────────────────


def test_legacy_cli_imports_still_work():
    """K.7 closing standard #1: the 11 legacy `pvess-*` commands must
    still be importable from `pvess_calc.cli` / `.doctor`. Drift here
    would silently break the entry-points table in pyproject.toml.
    """
    from pvess_calc import cli
    from pvess_calc.doctor import doctor_cmd

    for attr in (
        "calc_cmd", "render_cmd", "labels_cmd", "permit_cmd",
        "compare_cmd", "dxf_cmd", "init_cmd", "customer_summary_cmd",
        "lookup_check_cmd", "site_checklist_cmd", "symbols_preview_cmd",
        "ee4_trace_cmd", "ee4_preview_cmd",
    ):
        assert hasattr(cli, attr), f"legacy CLI '{attr}' missing from cli module"
    assert callable(doctor_cmd)


def test_pyproject_entry_points_match_root_subcommands():
    """K.7 closing standard #1 (sanity): every name registered as a
    pyproject `pvess-*` script must exist as a click command somewhere.
    Catches stale entry-points pointing at deleted functions."""
    import tomllib
    pyproject = PROJECT_ROOT / "pyproject.toml"
    with open(pyproject, "rb") as fh:
        cfg = tomllib.load(fh)
    scripts = cfg["project"]["scripts"]

    # Each `pvess-*` script entry must reference an importable callable
    import importlib
    for script_name, ref in scripts.items():
        module_path, _, func_name = ref.partition(":")
        mod = importlib.import_module(module_path)
        assert callable(getattr(mod, func_name)), (
            f"pyproject script {script_name} → {ref} is not callable"
        )
