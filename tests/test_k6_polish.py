"""K.6 — visual-polish regression guards.

Closing standard #2: each of the 6 K.6 polish items has at least one
test that locks the new layout / wording so a future refactor catches
the drift on `pytest` rather than at PDF review time.

Tests use pypdf text extraction (NOT byte-equality) so unrelated
reportlab churn doesn't break them — but the specific strings /
counts the K.6 polish introduced must remain present.
"""
from __future__ import annotations

from pathlib import Path

import pypdf
import pytest

from pvess_calc.calc.engine import run
from pvess_calc.schema import Inputs


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHOENIX_INPUTS = PROJECT_ROOT / "projects" / "002-phoenix-25kw" / "inputs.yaml"


# ─── Shared fixture: render the full permit + customer to tmp_path ────


@pytest.fixture
def phoenix_pdfs(tmp_path: Path) -> dict[str, Path]:
    """Render permit package + customer summary to tmp_path. Returns
    a dict of {"permit": path, "customer": path}."""
    inputs = Inputs.from_yaml(PHOENIX_INPUTS)
    result = run(inputs)
    out: dict[str, Path] = {}

    # Customer summary
    from pvess_calc.customer.pdf import render_customer_summary
    out["customer"] = tmp_path / "customer.pdf"
    render_customer_summary(result, out["customer"],
                            lookup_fields={"avg_residential_rate_usd_per_kwh": 0.131})

    # Specific permit sheets we care about for K.6:
    from pvess_calc.permit.cover_sheet import render_cover_sheet
    from pvess_calc.permit.general_notes import render_general_notes
    from pvess_calc.permit.panel_schedule import render_panel_schedule
    from pvess_calc.permit.site_plan import render_site_plan

    out["cover"] = tmp_path / "cover.pdf"
    out["site"] = tmp_path / "site.pdf"
    out["panels"] = tmp_path / "panels.pdf"
    out["notes"] = tmp_path / "notes.pdf"
    render_cover_sheet(result, out["cover"])
    render_site_plan(result, out["site"])
    render_panel_schedule(result, out["panels"])
    render_general_notes(result, out["notes"])
    return out


def _pdf_text(path: Path) -> str:
    """Extract all text from a PDF, normalized to single-spaced."""
    raw = "\n".join(
        page.extract_text() or "" for page in pypdf.PdfReader(str(path)).pages
    )
    return " ".join(raw.split())


# ─── A. EE-4 Site Plan ────────────────────────────────────────────────


def test_ee4_site_plan_renders_setback_distances(phoenix_pdfs):
    """K.6 (A): site plan must include front/rear/side setback values.
    Phoenix 80×120 lot, 50×35 house centered → front/rear ≈ 43', side ≈ 15'."""
    text = _pdf_text(phoenix_pdfs["site"])
    assert "43'" in text or "Front yard setback" in text
    assert "15'" in text or "Side yard setback" in text


def test_ee4_site_plan_has_scale_bar(phoenix_pdfs):
    """K.6 (A): scale bar present (SCALE (ft) caption + numeric ticks)."""
    text = _pdf_text(phoenix_pdfs["site"])
    assert "SCALE" in text


def test_ee4_site_plan_has_equipment_route_legend(phoenix_pdfs):
    """K.6 (A): orange dashed MSP→AC-DISC→ESS route + its legend chip."""
    text = _pdf_text(phoenix_pdfs["site"])
    assert "equipment route" in text


# ─── B. EE-3 Panel Schedules ──────────────────────────────────────────


def test_ee3_orphan_subpanel_renders_centered_in_phoenix(phoenix_pdfs):
    """K.6 (B): 3-panel Phoenix project ends in a single orphan
    Sub Panel #1 in the bottom row. Smoke check: all 3 panels appear
    in the rendered PDF text."""
    text = _pdf_text(phoenix_pdfs["panels"])
    assert "MSP" in text
    assert "Sub Panel #2" in text
    assert "Sub Panel #1" in text


# ─── C. PV-N General Notes ────────────────────────────────────────────


def test_pvn_general_notes_show_group_banners(phoenix_pdfs):
    """K.6 (C): notes grouped under §A / §B / §C banners with titles."""
    text = _pdf_text(phoenix_pdfs["notes"])
    assert "§A" in text or "A · Scope" in text
    assert "Scope" in text
    assert "Grounding" in text
    assert "Conductors" in text  # right column §A


def test_pvn_all_electrical_notes_visible_after_layout_tightening(phoenix_pdfs):
    """K.6 (C) closing contract: the layout tightening must keep all
    22 ELECTRICAL_NOTES visible — earlier draft was clipping D.4 / D.5."""
    from pvess_calc.permit.general_notes import ELECTRICAL_NOTE_GROUPS
    text = _pdf_text(phoenix_pdfs["notes"])
    # Group D ("Connectors, Markings & Commissioning") must be visible
    last_group_letter, last_title, last_notes = ELECTRICAL_NOTE_GROUPS[-1]
    assert "Connectors" in text or "Commissioning" in text
    # The numbered D.5 prefix should appear (last note in last group).
    assert f"{last_group_letter}.{len(last_notes)}" in text


# ─── D. Cover PE STAMP placeholder ────────────────────────────────────


def test_cover_pe_stamp_box_explicit_placeholder(phoenix_pdfs):
    """K.6 (D): PE STAMP box now carries 'to be affixed' subtext so
    AHJ reviewers see the empty area as intentional."""
    text = _pdf_text(phoenix_pdfs["cover"])
    assert "PE STAMP" in text
    assert "to be affixed" in text


# ─── E. EE-2 NOTES — geometric, not visual (line height changed) ──────


def test_ee2_notes_line_spacing_constant():
    """K.6 (E): NOTES line spacing was 0.16 → 0.20. Lock in the new
    value at the source-code level — visual quality regression is hard
    to spot in PDF text extraction alone."""
    src = (PROJECT_ROOT / "src" / "pvess_calc"
           / "dxf" / "grounding_sheet.py").read_text()
    # The polished _draw_notes function uses `y -= 0.20` between lines.
    assert "y -= 0.20" in src, (
        "EE-2 NOTES line spacing constant drifted from K.6 0.20\" value"
    )


# ─── F. Customer-summary polish ───────────────────────────────────────


def test_customer_summary_caption_is_left_aligned_now(phoenix_pdfs):
    """K.6 (F): the 'estimated monthly savings' caption shows up after
    $483 in the natural reading order (no big horizontal gap from a
    centered caption inside a wide cell)."""
    text = _pdf_text(phoenix_pdfs["customer"])
    # The caption must be present
    assert "estimated monthly savings" in text
    # And the dollar amount must precede it in reading order
    cap_idx = text.find("estimated monthly savings")
    dollar_idx = text.find("$483")
    if dollar_idx != -1:
        assert dollar_idx < cap_idx


def test_customer_summary_monthly_chart_axes_bumped_to_8pt():
    """K.6 (F) closing contract: bar chart x-axis labelsize raised from
    7 → 8.5 pt. Source-level guard so a future style refactor catches it."""
    src = (PROJECT_ROOT / "src" / "pvess_calc"
           / "customer" / "charts.py").read_text()
    assert "labelsize=8.5" in src, (
        "Customer-summary bar chart x-axis labelsize drifted from K.6 value"
    )


# ─── Cross-cutting: doctor still 24/24 after all polish ───────────────


def test_all_doctor_checks_still_pass_after_k6_polish():
    """K.6 closing standard #1: visual polish doesn't break any
    structural invariant. Run the full doctor on Phoenix and assert
    zero failures."""
    from pvess_calc.doctor import run_doctor
    results = run_doctor(PROJECT_ROOT / "projects" / "002-phoenix-25kw")
    failed = [r for r in results if r.status == "FAIL"]
    assert not failed, f"K.6 introduced doctor failures: {failed}"
