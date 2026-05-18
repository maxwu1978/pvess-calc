"""Stage D / K.13 — EE-4 site-focused restructure.

Locks the K.13 contract:

  1. EE-4 is a SITE plan, not a PV-array plan. The legacy abstract
     PV-grid box is deleted; only real per-face geometry renders.
  2. `_pick_module_grid` is dead code and must stay deleted (regression
     guard against re-introducing the legacy renderer).
  3. The doctor check `ee4_focuses_on_site_geometry` catches any
     `N×M grid` caption leaking back in.
  4. Three render modes coexist cleanly:
       routed → modules + conduit + leader callouts
       has_face_anchors → modules only (no conduit, no leaders)
       neither → NOTE strip + legacy K.6 equipment column
"""
from __future__ import annotations

import re
from pathlib import Path

import pypdf

from pvess_calc.calc.engine import run
from pvess_calc.permit.site_plan import render_site_plan
from pvess_calc.schema import Inputs


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUSTIN = PROJECT_ROOT / "projects" / "001-demo-austin" / "inputs.yaml"
PHOENIX = PROJECT_ROOT / "projects" / "002-phoenix-25kw" / "inputs.yaml"
FRISCO = PROJECT_ROOT / "projects" / "003-frisco-glasshouse" / "inputs.yaml"


def _ee4_text(tmp_path: Path, inputs: Inputs, *, suffix: str = "ee4") -> str:
    out = tmp_path / f"{suffix}.pdf"
    render_site_plan(run(inputs), out)
    return "\n".join(p.extract_text() or ""
                     for p in pypdf.PdfReader(str(out)).pages)


_GRID_PATTERN = re.compile(r"\b\d+\s*[×x]\s*\d+\s+grid\b")


# ─── #1 abstract grid is gone — all 3 sample projects ────────────────────


def test_austin_ee4_no_abstract_grid(tmp_path: Path):
    """Austin yaml has no roof_sections → legacy path → must NOT
    render a `N×M grid` caption (it would have under pre-K.13)."""
    text = _ee4_text(tmp_path, Inputs.from_yaml(AUSTIN), suffix="austin")
    assert _GRID_PATTERN.search(text) is None
    # And the warning strip SHOULD show
    assert "PV array geometry omitted" in text


def test_phoenix_ee4_no_abstract_grid(tmp_path: Path):
    """Phoenix has 2 roof_sections → Stage B auto-anchors → real
    per-face render; no abstract grid caption."""
    text = _ee4_text(tmp_path, Inputs.from_yaml(PHOENIX), suffix="phx")
    assert _GRID_PATTERN.search(text) is None
    # PV ARRAY caption appears in the bottom margin
    assert "PV ARRAY" in text


def test_frisco_ee4_no_abstract_grid(tmp_path: Path):
    """Frisco has 5 explicit anchors + equipment_locations → fully
    routed → per-face modules + conduit + leader callouts."""
    text = _ee4_text(tmp_path, Inputs.from_yaml(FRISCO), suffix="fri")
    assert _GRID_PATTERN.search(text) is None
    assert "PV ARRAY" in text
    # Routed mode signature
    assert "conduit" in text.lower()


# ─── #2 _pick_module_grid dead-code removal ─────────────────────────────


def test_pick_module_grid_function_deleted():
    """The legacy grid helper `_pick_module_grid` was deleted in K.13.
    Re-adding it (even unused) signals a likely intent to bring back
    the legacy path, so we lock its absence here."""
    src = (PROJECT_ROOT / "src" / "pvess_calc" / "permit"
           / "site_plan.py").read_text()
    assert "_pick_module_grid" not in src
    assert "_PV_COLOR" in src   # palette constant kept — used elsewhere


# ─── #3 doctor check positive + negative ────────────────────────────────


def test_doctor_ee4_focuses_check_passes_for_austin():
    """No roof_sections → check passes via the warning-strip path."""
    from pvess_calc.doctor import _check_ee4_focuses_on_site_geometry
    result = run(Inputs.from_yaml(AUSTIN))
    checks = _check_ee4_focuses_on_site_geometry(result)
    assert all(r.ok for r in checks)
    assert any("incompleteness NOTE strip" in r.detail for r in checks)


def test_doctor_ee4_focuses_check_passes_for_phoenix():
    """2 sections (auto-anchored) → check passes via per-face path."""
    from pvess_calc.doctor import _check_ee4_focuses_on_site_geometry
    result = run(Inputs.from_yaml(PHOENIX))
    checks = _check_ee4_focuses_on_site_geometry(result)
    assert all(r.ok for r in checks)
    assert any("per-face render active" in r.detail for r in checks)
    assert any("2 section" in r.detail for r in checks)


def test_doctor_ee4_focuses_check_passes_for_frisco():
    """5 no-overlap sections (explicit) + equipment_locations → routed → PASS."""
    from pvess_calc.doctor import _check_ee4_focuses_on_site_geometry
    result = run(Inputs.from_yaml(FRISCO))
    checks = _check_ee4_focuses_on_site_geometry(result)
    assert all(r.ok for r in checks)
    assert any("5 section" in r.detail for r in checks)


# ─── #4 mode contracts — render content per mode ────────────────────────


def test_routed_mode_renders_conduit_line(tmp_path: Path):
    """Routed mode (Frisco) → conduit legend chip + leader-line
    callouts visible."""
    text = _ee4_text(tmp_path, Inputs.from_yaml(FRISCO), suffix="fri-r")
    assert "conduit" in text.lower()
    # Equipment leader callouts include "(N)" or "(E)" markers + label.
    assert "(N) MAIN SERVICE PANEL" in text or "(N) MSP" in text


def test_anchor_only_mode_skips_conduit(tmp_path: Path):
    """Phoenix is auto-anchored but no equipment_locations →
    per-face modules render, but NO conduit polyline + NO leader
    callouts (those require routed=True)."""
    inputs = Inputs.from_yaml(PHOENIX)
    text = _ee4_text(tmp_path, inputs, suffix="phx-a")
    # Real modules render → PV ARRAY caption present
    assert "PV ARRAY" in text
    # No conduit legend chip in anchored-only mode
    assert "auto-routed" not in text


def test_pure_legacy_shows_warning_strip(tmp_path: Path):
    """No sections + no equipment → warning strip is the ONLY signal
    that PV exists at all. Must be both visible AND specific."""
    text = _ee4_text(tmp_path, Inputs.from_yaml(AUSTIN), suffix="aus-l")
    assert "PV array geometry omitted" in text
    assert "PV-4" in text
    assert "site.roof_sections" in text


# ─── #5 aerial inset enlargement ────────────────────────────────────────


def test_aerial_inset_enlarged_to_3x2_6():
    """K.13 bumped aerial inset 2.5×2.2" → 3.0×2.6" because the right
    column has more room without the legacy abstract box."""
    src = (PROJECT_ROOT / "src" / "pvess_calc" / "permit"
           / "site_plan.py").read_text()
    assert "w=3.0 * inch, h=2.6 * inch" in src
    # And the old size must be gone
    assert "w=2.5 * inch, h=2.2 * inch" not in src


def test_info_column_widened_to_3_4_inch():
    """SITE INFORMATION column anchor pushed from 3.2" → 3.4" from
    the right page edge to accommodate the wider aerial."""
    src = (PROJECT_ROOT / "src" / "pvess_calc" / "permit"
           / "site_plan.py").read_text()
    assert "W - 3.4 * inch" in src
    assert "W - 3.2 * inch" not in src
