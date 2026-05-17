"""K.7 [4/4] — pvess-compare PDF emission tests.

Locks:
  * `write_outputs` emits comparison.pdf alongside .md + .json by default.
  * PDF contains every scenario name in text.
  * PDF contains the economics strip ($/mo, payback) for each scenario.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pypdf

from pvess_calc.compare.report import write_outputs
from pvess_calc.compare.scenarios import run_scenarios


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHX_SCENARIOS = PROJECT_ROOT / "projects" / "002-phoenix-25kw" / "scenarios"


def _pdf_text(path: Path) -> str:
    return "\n".join(
        page.extract_text() or "" for page in pypdf.PdfReader(str(path)).pages
    )


def test_compare_emits_pdf_alongside_md_and_json(tmp_path: Path):
    """K.7 [4/4] closing contract: write_outputs() generates the PDF
    by default — no special flag needed."""
    work = tmp_path / "scenarios"
    shutil.copytree(PHX_SCENARIOS, work)
    scenarios = run_scenarios(work)
    assert len(scenarios) >= 2, "need ≥ 2 scenarios for a comparison"

    write_outputs(scenarios,
                  md_path=work / "comparison.md",
                  json_path=work / "comparison.json")

    assert (work / "comparison.md").exists()
    assert (work / "comparison.json").exists()
    assert (work / "comparison.pdf").exists()
    # PDF is compact (font subsetting + 1 page); 2 KB is the floor for a
    # 2-scenario table + economics strip — anything smaller means the
    # PDF didn't actually render content.
    assert (work / "comparison.pdf").stat().st_size > 2000


def test_compare_pdf_contains_scenario_names_and_economics(tmp_path: Path):
    """PDF text extraction shows every scenario name + $ /mo headlines."""
    work = tmp_path / "scenarios"
    shutil.copytree(PHX_SCENARIOS, work)
    scenarios = run_scenarios(work)
    write_outputs(scenarios,
                  md_path=work / "comparison.md",
                  json_path=work / "comparison.json")
    text = _pdf_text(work / "comparison.pdf")

    for s in scenarios:
        assert s.name in text, (
            f"scenario name {s.name!r} missing from compare PDF"
        )
    # Each scenario has a $/mo line — at least 1 dollar amount visible.
    import re
    dollars = re.findall(r"\$\d", text)
    assert len(dollars) >= len(scenarios), (
        f"expected ≥ {len(scenarios)} dollar amounts in PDF (one per "
        f"scenario), got {len(dollars)}"
    )


def test_compare_pdf_includes_all_11_metric_rows(tmp_path: Path):
    """Metric table has 11 rows (PV / Inverter / Battery / Backfeed /
    Interconnect / Voc / PV OCPD / AC OCPD / Vd / AIC / BOM) — locks
    the row inventory so a future drop is caught."""
    work = tmp_path / "scenarios"
    shutil.copytree(PHX_SCENARIOS, work)
    scenarios = run_scenarios(work)
    write_outputs(scenarios,
                  md_path=work / "comparison.md",
                  json_path=work / "comparison.json")
    text = _pdf_text(work / "comparison.pdf")
    expected_labels = [
        "PV array", "Inverter AC", "Battery storage", "PV+ESS backfeed",
        "705.12 method", "Voc cold-corrected", "PV OCPD",
        "AC disconnect OCPD", "End-to-end Vd", "AIC margin",
        "BOM subtotal",
    ]
    for label in expected_labels:
        assert label in text, f"metric row {label!r} missing from compare PDF"
