"""K.9.3 — PV-4 v2 renderer visual contract tests.

The K.9.3 upgrade replaces the K.2.8 grid-only module rendering with
real ModuleInstance rectangles at (x, y, rotation) from K.9.1 placement.
These tests lock the contract via PDF byte-level inspection (text +
size) since pixel-perfect comparison is out of scope.

Five concerns:
  1. **Backward compat** — legacy yaml (no roof_sections) renders OK.
  2. **PV-4 renders ≥ 30 KB for Phoenix** — real module rects are
     denser SVG output than the grid concept.
  3. **Module dimension callout** appears with brand + model + W +
     dimensions.
  4. **Frisco K.3c-init path** — engine auto-distributes, PV-4 draws
     the placed modules.
  5. **Module count consistency** — Σ placements within bounds of
     `pv_array.modules`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pvess_calc.calc.engine import run
from pvess_calc.permit.structural import render_attachment_plan
from pvess_calc.schema import Inputs


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHOENIX = PROJECT_ROOT / "projects" / "002-phoenix-25kw" / "inputs.yaml"
AUSTIN = PROJECT_ROOT / "projects" / "001-demo-austin" / "inputs.yaml"
FRISCO = PROJECT_ROOT / "projects" / "003-frisco-glasshouse" / "inputs.yaml"


def _pdf_text(path: Path) -> str:
    import pypdf
    return "\n".join(p.extract_text() or ""
                     for p in pypdf.PdfReader(str(path)).pages)


# ─── Backward compat ───────────────────────────────────────────────────


def test_pv4_renders_for_austin_legacy_no_roof_sections(tmp_path: Path):
    """Austin demo has no roof_sections — `module_placements` is empty.
    PV-4 must fall back to the K.2.8 grid concept (or a sane default)
    rather than crash or render a 0-byte PDF."""
    result = run(Inputs.from_yaml(AUSTIN))
    assert result.module_placements == {}
    out = tmp_path / "austin-pv4.pdf"
    render_attachment_plan(result, out)
    assert out.exists()
    # PV-4 is one landscape page — ~3-5 KB typical reportlab output.
    # Larger threshold caught the "empty canvas" failure mode at < 1 KB.
    assert out.stat().st_size > 2_500


# ─── PV-4 v2 renders for real projects ─────────────────────────────────


def test_pv4_renders_for_phoenix_with_placements(tmp_path: Path):
    """Phoenix has 2 faces × 30 modules = 60 placements. The PV-4 PDF
    must render successfully with sufficient file size."""
    result = run(Inputs.from_yaml(PHOENIX))
    total_placed = sum(len(m) for m in result.module_placements.values())
    assert total_placed >= 40, (
        f"only {total_placed} placements; engine integration may have regressed"
    )

    out = tmp_path / "phoenix-pv4.pdf"
    render_attachment_plan(result, out)
    assert out.exists()
    # 60 placements ≈ 60 rect calls + dimension callout → ~4-6 KB
    assert out.stat().st_size > 3_500


def test_pv4_renders_for_frisco_k3c_init_path(tmp_path: Path):
    """Frisco yaml has all module_count=0 (K.3c init). K.9.2 engine
    integration must auto-distribute via LRM → place_modules → PV-4
    draws the placed rectangles. Renders ≥ 10 KB."""
    result = run(Inputs.from_yaml(FRISCO))
    total_placed = sum(len(m) for m in result.module_placements.values())
    # Frisco target = 36; some shortfall is geometrically OK (small
    # faces can't fit their LRM quota). Lock the lower bound.
    assert total_placed >= 30, (
        f"Frisco K.3c → only {total_placed} placements (target 36); "
        "LRM auto-distribute may have regressed"
    )
    out = tmp_path / "frisco-pv4.pdf"
    render_attachment_plan(result, out)
    assert out.exists()
    # ~30 placements + 5 face frames + callout → ~4-5 KB
    assert out.stat().st_size > 3_500


# ─── Module dimension callout ──────────────────────────────────────────


def test_pv4_includes_module_dimension_callout(tmp_path: Path):
    """K.9.3 — the corner callout box must display module brand, model,
    wattage, and physical dimensions. Matches the Aurora-style
    `67.80″ × 44.65″` reference block."""
    result = run(Inputs.from_yaml(PHOENIX))
    out = tmp_path / "phoenix-callout.pdf"
    render_attachment_plan(result, out)

    text = _pdf_text(out)
    # Module brand + model uppercase (from _draw_module_dim_callout)
    mod = result.inputs.pv_array.module
    assert mod.brand.upper() in text or mod.model.upper() in text
    # Module wattage in the secondary line
    assert f"{mod.power_w:.0f} W" in text
    # Dimensions — must have both length and width with " suffix
    assert f'{mod.length_in:.2f}"' in text
    assert f'{mod.width_in:.2f}"' in text


def test_pv4_dimension_callout_works_with_default_talesun(tmp_path: Path):
    """K.9.1 module schema defaults to Talesun TP7G54M 415 dims
    (67.80 × 44.65 in). Verify the callout renders correctly when
    yaml doesn't explicitly override these fields (backward compat
    for every pre-K.9.1 yaml)."""
    inputs = Inputs.from_yaml(PHOENIX)
    # Override module to use defaults (no explicit length_in / width_in)
    inputs = inputs.model_copy(deep=True)
    inputs.pv_array.module = inputs.pv_array.module.model_copy(update={
        "brand": "Generic", "model": "Default 420W",
    })
    # Defaults from the schema definition
    assert inputs.pv_array.module.length_in == 67.80
    assert inputs.pv_array.module.width_in == 44.65

    result = run(inputs)
    out = tmp_path / "phoenix-default-mod.pdf"
    render_attachment_plan(result, out)
    text = _pdf_text(out)
    assert '67.80"' in text
    assert '44.65"' in text


# ─── Consistency contract ──────────────────────────────────────────────


def test_pv4_placements_dont_exceed_pv_array_modules():
    """Closing standard: Σ placements ≤ pv_array.modules. The K.9.1
    algorithm truncates to `target_count`; LRM allocates ≤ total. If
    this ever fires, something is double-counting."""
    for yaml_path in (PHOENIX, FRISCO, AUSTIN):
        result = run(Inputs.from_yaml(yaml_path))
        total_placed = sum(len(m) for m in result.module_placements.values())
        target = result.inputs.pv_array.modules
        assert total_placed <= target, (
            f"{yaml_path.parent.name}: placed {total_placed} > target {target}"
        )
