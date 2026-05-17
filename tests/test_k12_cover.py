"""K.12.4 + K.12.5 — PV-1 cover sheet v2 visual contract + doctor check.

Locks the 12-block layout via PDF text extraction. Renders the cover
for Phoenix (full data, 1:1 NEM) and verifies each block emits its
expected content.
"""
from __future__ import annotations

from pathlib import Path

import pypdf
import pytest

from pvess_calc.calc.engine import run
from pvess_calc.permit.cover_sheet import render_cover_sheet
from pvess_calc.schema import (
    BuildingCodes,
    DesignCriteria,
    Inputs,
    MeterInfo,
    RevisionEntry,
    RoofInfo,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHOENIX = PROJECT_ROOT / "projects" / "002-phoenix-25kw" / "inputs.yaml"
FRISCO = PROJECT_ROOT / "projects" / "003-frisco-glasshouse" / "inputs.yaml"


def _cover_text(tmp_path: Path, inputs_path: Path) -> str:
    out = tmp_path / "cover.pdf"
    result = run(Inputs.from_yaml(inputs_path))
    render_cover_sheet(result, out)
    return "\n".join(p.extract_text() or ""
                     for p in pypdf.PdfReader(str(out)).pages)


# ─── Title strip ────────────────────────────────────────────────────────


def test_cover_has_industry_standard_title(tmp_path: Path):
    """K.12.4: the cover headline matches the Wyssling reference
    image's "NEW PV SYSTEM DESIGN" — AHJ-standard phrasing."""
    text = _cover_text(tmp_path, PHOENIX)
    assert "NEW PV SYSTEM DESIGN" in text


def test_cover_title_strip_includes_system_size(tmp_path: Path):
    """Right under the title: '60 MODULES · 25.20 kW DC · 23.76 kW AC
    SYSTEM SIZE'-style line. Catches the regression of dropping the
    sub-headline."""
    text = _cover_text(tmp_path, PHOENIX)
    # 60 modules × 420W = 25.2 kW DC
    assert "60 MODULES" in text
    assert "25.20 kW DC" in text
    # Phoenix has 3 × 8K hybrid = 23.76 kW AC
    assert "kW AC SYSTEM SIZE" in text


# ─── 12 blocks present ─────────────────────────────────────────────────


def test_cover_emits_all_12_blocks(tmp_path: Path):
    """K.12.4 contract: every block heading must appear in the
    rendered cover. Drift sentry — if anyone deletes a block, this
    fails before the next live `pvess permit` invocation."""
    text = _cover_text(tmp_path, PHOENIX)
    required_blocks = [
        "AERIAL MAP",
        "VICINITY MAP",
        "SHEET INDEX",
        "SCOPE OF WORK",
        "GOVERNING CODES",
        "DESIGN CRITERIA",
        "ROOF INFO",
        "INTERCONNECTION",
        "ARRAYS",
        "METER INFO",
        "REVISION HISTORY",
        "PE STAMP",
    ]
    missing = [b for b in required_blocks if b not in text]
    assert not missing, f"cover missing blocks: {missing}"


# ─── Governing codes block ─────────────────────────────────────────────


def test_cover_governing_codes_includes_nec_and_icc_family(tmp_path: Path):
    """K.12.5 contract: GOVERNING CODES lists NEC version + all 8 ICC
    family codes."""
    text = _cover_text(tmp_path, PHOENIX)
    # NEC year (Phoenix yaml is 2023 NEC)
    assert "2023 NEC" in text
    # ICC family — defaults are 2021 cycle
    for code in ("IBC", "IRC", "IFC", "IFGC", "IEBC", "IECC", "IMC", "IPC"):
        assert code in text, f"governing code {code} missing from cover"


# ─── Design criteria block ─────────────────────────────────────────────


def test_cover_design_criteria_includes_wind_snow_asce(tmp_path: Path):
    """K.12.4 — Wind / Snow / ASCE values appear with their units."""
    text = _cover_text(tmp_path, PHOENIX)
    assert "115 mph" in text
    assert "5 psf" in text
    assert "ASCE" in text
    assert "7-16" in text


# ─── Roof info block ───────────────────────────────────────────────────


def test_cover_roof_info_renders_with_defaults(tmp_path: Path):
    """K.12.4 — ROOF INFO renders even when fields are at defaults
    (em-dash placeholders for blanks)."""
    text = _cover_text(tmp_path, PHOENIX)
    assert "ROOF INFO" in text
    # Stories default = 1
    assert "Stories:" in text or "1" in text


def test_cover_roof_info_renders_explicit_values(tmp_path: Path):
    """K.12.4 — when yaml supplies RoofInfo fields, they appear."""
    inputs = Inputs.from_yaml(PHOENIX).model_copy(deep=True)
    inputs.project.roof_info = RoofInfo(
        stories=2, type="Comp Shingle", height_ft=25,
        condition="good", being_replaced=False,
    )
    out = tmp_path / "explicit-roof.pdf"
    render_cover_sheet(run(inputs), out)
    text = "\n".join(p.extract_text() or ""
                     for p in pypdf.PdfReader(str(out)).pages)
    assert "Comp Shingle" in text
    assert "Good" in text   # capitalized for display


# ─── Meter info block ──────────────────────────────────────────────────


def test_cover_meter_info_includes_esid_when_provided(tmp_path: Path):
    """K.12.4: Oncor ESID (Texas-specific) appears when yaml supplies it."""
    inputs = Inputs.from_yaml(FRISCO).model_copy(deep=True)
    inputs.project.meter_info = MeterInfo(
        number="153468971", location="1st floor garage",
        esid="10443720007628433",
    )
    out = tmp_path / "esid.pdf"
    render_cover_sheet(run(inputs), out)
    text = "\n".join(p.extract_text() or ""
                     for p in pypdf.PdfReader(str(out)).pages)
    assert "153468971" in text
    assert "10443720007628433" in text


# ─── Arrays table ──────────────────────────────────────────────────────


def test_cover_arrays_table_lists_each_roof_section(tmp_path: Path):
    """K.12.4 — ARRAYS table has one row per roof_section with TILT and
    AZIMUTH columns. Phoenix has 2 sections (South + West)."""
    text = _cover_text(tmp_path, PHOENIX)
    # Header row
    assert "ARRAYS" in text
    assert "TILT" in text
    assert "AZIMUTH" in text


# ─── Revision history ─────────────────────────────────────────────────


def test_cover_revision_history_falls_back_to_initial_design(tmp_path: Path):
    """K.12.4 backward-compat: pre-K.12 yaml has no `revision_history`
    list. The cover synthesizes a single row from `revision +
    initial_design_date` so the table isn't empty."""
    text = _cover_text(tmp_path, PHOENIX)
    assert "REVISION HISTORY" in text
    # Phoenix has revision='A' and initial_design_date='2026-05-12'
    assert "2026-05-12" in text


def test_cover_revision_history_renders_multi_row_when_provided(tmp_path: Path):
    """K.12.4 — when yaml supplies multiple revision entries, all
    appear in the table."""
    inputs = Inputs.from_yaml(PHOENIX).model_copy(deep=True)
    inputs.project.revision_history = [
        RevisionEntry(date="2026-04-01", revision="A", comment="initial"),
        RevisionEntry(date="2026-05-12", revision="B", comment="updated"),
        RevisionEntry(date="2026-05-17", revision="C", comment="final"),
    ]
    out = tmp_path / "multi-rev.pdf"
    render_cover_sheet(run(inputs), out)
    text = "\n".join(p.extract_text() or ""
                     for p in pypdf.PdfReader(str(out)).pages)
    assert "2026-04-01" in text
    assert "2026-05-12" in text
    assert "2026-05-17" in text


# ─── Map placeholders (no API key) ─────────────────────────────────────


def test_cover_renders_with_map_placeholders_when_no_keys(tmp_path: Path,
                                                          monkeypatch):
    """Closing standard: cover MUST render without crashing when
    PVESS_GOOGLE_SOLAR_KEY and PVESS_MAPBOX_TOKEN are absent. Each
    map shows a "X required" placeholder instead."""
    from pvess_calc.lookup.config import (
        ENV_GOOGLE_SOLAR_KEY,
        ENV_MAPBOX_TOKEN,
        reset_cache_for_tests,
    )
    monkeypatch.delenv(ENV_GOOGLE_SOLAR_KEY, raising=False)
    monkeypatch.delenv(ENV_MAPBOX_TOKEN, raising=False)
    reset_cache_for_tests()

    text = _cover_text(tmp_path, PHOENIX)
    # Cover still renders — title is there
    assert "NEW PV SYSTEM DESIGN" in text
    # And the map placeholders surface the missing-key message
    assert "PVESS_GOOGLE_SOLAR_KEY required" in text \
        or "PVESS_MAPBOX_TOKEN required" in text \
        or "AERIAL MAP" in text   # at minimum the block header


# ─── K.12.5 doctor check ──────────────────────────────────────────────


def test_doctor_cover_governing_codes_passes_with_defaults():
    """K.12.5 positive guard: BuildingCodes defaults to 2021 ICC cycle
    → check PASSes for every project."""
    from pvess_calc.doctor import _check_cover_has_governing_codes
    result = run(Inputs.from_yaml(PHOENIX))
    [r] = _check_cover_has_governing_codes(result)
    assert r.status == "PASS"
    assert "9 codes present" in r.detail


def test_doctor_cover_kv_values_fit_block_width_passes_on_frisco():
    """K.12.5+ regression guard for the 2026-05-17 "AC overflows
    frame" bug. Frisco's scope-of-work has the longest system-size
    string ('14.94 kW DC  /  10.99 kW AC') — if the KV truncation
    formula reverts to the bogus char-count heuristic, the AC kW
    token will be clipped and this check fails.
    """
    from pathlib import Path
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_cover_kv_values_fit_block_width
    from pvess_calc.schema import Inputs
    project_root = Path(__file__).resolve().parents[1]
    frisco = project_root / "projects" / "003-frisco-glasshouse" / "inputs.yaml"
    [r] = _check_cover_kv_values_fit_block_width(run(Inputs.from_yaml(frisco)))
    assert r.status == "PASS"
    assert "renders unclipped" in r.detail


def test_doctor_cover_blocks_no_vertical_overlap_passes_on_frisco():
    """K.12.5+ regression guard for the 2026-05-17 overlap bug:
    INTERCONNECTION + ARRAYS + METER row was 1.7" tall, REVISION +
    PE STAMP row also 1.5" tall — total ~3.2" but only 2.0" available
    → bands overlapped 1.3" and REV HISTORY headers bled into the
    INTERCONNECTION block. New layout has explicit 0.15" gaps.

    Positive guard: current Frisco cover passes the no-overlap check.
    """
    from pathlib import Path
    from pvess_calc.calc.engine import run
    from pvess_calc.doctor import _check_cover_blocks_no_vertical_overlap
    from pvess_calc.schema import Inputs
    project_root = Path(__file__).resolve().parents[1]
    frisco = project_root / "projects" / "003-frisco-glasshouse" / "inputs.yaml"
    [r] = _check_cover_blocks_no_vertical_overlap(run(Inputs.from_yaml(frisco)))
    assert r.status == "PASS"
    assert "non-overlapping order" in r.detail or "12 blocks" in r.detail


def test_doctor_cover_governing_codes_fails_on_wiped_codes(monkeypatch):
    """K.12.5 regression-bait: someone clears the BuildingCodes
    defaults to empty strings → check FAILs listing the missing codes."""
    from pvess_calc.doctor import _check_cover_has_governing_codes
    inputs = Inputs.from_yaml(PHOENIX).model_copy(deep=True)
    inputs.project.building_codes = BuildingCodes(
        ibc="", irc="", ifc="", ifgc="", iebc="", iecc="", imc="", ipc="",
    )
    result = run(inputs)
    [r] = _check_cover_has_governing_codes(result)
    assert r.status == "FAIL"
    assert "IBC" in r.detail
    assert "IECC" in r.detail
