"""Tests for Phase F (permit packet) + Phase G (AHJ profiles)."""
from __future__ import annotations

from pathlib import Path

import pytest

from pvess_calc.ahj import get_ahj_profile, list_ahj_profiles
from pvess_calc.calc.engine import run
from pvess_calc.permit.builder import build_permit_package
from pvess_calc.permit.compliance import build_checklist
from tests.conftest import make_inputs


# --- Phase F: permit packet -----------------------------------------------

def test_permit_pdf_built_with_expected_pages(tmp_path: Path):
    result = run(make_inputs())
    out = tmp_path / "permit.pdf"
    n_pages = build_permit_package(result, out)
    assert out.exists()
    assert out.stat().st_size > 1000   # sanity: non-trivial PDF
    # 7 sheets, EE-6 labels can be 2 pages → at least 7
    assert n_pages >= 7


def test_permit_pdf_starts_with_pdf_magic(tmp_path: Path):
    result = run(make_inputs())
    out = tmp_path / "permit.pdf"
    build_permit_package(result, out)
    assert out.read_bytes()[:4] == b"%PDF"


def test_compliance_checklist_has_all_status_levels():
    """Every status level must be representable; some items should be MANUAL."""
    result = run(make_inputs())
    items = build_checklist(result)
    statuses = {it.status for it in items}
    assert "PASS" in statuses
    assert "MANUAL" in statuses


def test_compliance_checklist_flags_600v_violation():
    """24-module string at -10°C exceeds 600V — should appear as FAIL."""
    inputs = make_inputs(modules=24, strings=2, voc_temp_coeff=None,
                         design_low_c=-10)
    result = run(inputs)
    items = build_checklist(result)
    voc_item = next(it for it in items if it.nec_clause == "690.7(A)")
    # Voc cold = 12 * 49.5 * 1.14 = 677V > 600 → FAIL
    assert voc_item.status == "FAIL"


def test_permit_with_ahj_filter_omits_unrequested_sheets(tmp_path: Path):
    """When an AHJ profile lists only a subset of sheets, others are skipped."""
    # Build a fake profile that only includes cover + ee-1 + labels
    import tempfile, shutil
    from pvess_calc.ahj import profile as ahj_mod
    # Patch profiles dir temporarily
    fake_dir = tmp_path / "profiles"
    fake_dir.mkdir()
    (fake_dir / "lean.yaml").write_text(
        "name: 'Lean AHJ'\n"
        "required_sheets: [cover, ee-1, labels]\n"
    )
    orig_dir = ahj_mod.PROFILES_DIR
    ahj_mod.PROFILES_DIR = fake_dir
    try:
        result = run(make_inputs())
        out = tmp_path / "lean.pdf"
        n_pages_full = build_permit_package(result, tmp_path / "full.pdf")
        n_pages_lean = build_permit_package(result, out, ahj_name="lean")
        assert n_pages_lean < n_pages_full
        assert n_pages_lean >= 3   # cover + ee-1 + at least 1 labels page
    finally:
        ahj_mod.PROFILES_DIR = orig_dir


# --- Phase G: AHJ profiles --------------------------------------------------

def test_builtin_ahj_profiles_load():
    """All shipped profiles parse without error."""
    names = list_ahj_profiles()
    assert "austin_tx" in names
    assert "phoenix_az" in names
    assert "california_generic" in names
    assert "hawaii_generic" in names
    for name in names:
        profile = get_ahj_profile(name)
        assert profile.name


def test_ahj_profile_unknown_name_raises():
    with pytest.raises(KeyError, match="Unknown AHJ profile"):
        get_ahj_profile("does_not_exist")


def test_phoenix_profile_has_inspector_checklist():
    profile = get_ahj_profile("phoenix_az")
    assert any("APS" in item for item in profile.inspector_checklist)
    assert any("attic" in item.lower() for item in profile.inspector_checklist)


def test_california_profile_mentions_title24():
    profile = get_ahj_profile("california_generic")
    blob = " ".join(profile.inspector_checklist) + " " + profile.notes
    assert "Title 24" in blob or "CalGreen" in blob
    assert "NEM 3.0" in profile.notes or "Title 24" in profile.notes
