"""Tests for the NEC label generator."""
from __future__ import annotations

from pathlib import Path

import pytest

from pvess_calc.calc.engine import run
from pvess_calc.labels.render import (
    PLACEHOLDER_RE,
    SEVERITY_STYLES,
    materialize,
    render_for_result,
)
from pvess_calc.labels.specs import LABEL_CATALOG
from tests.conftest import make_inputs


def test_catalog_has_expected_nec_clauses():
    """Sanity-check that the catalog covers the key residential clauses."""
    clauses = {s.nec_clause for s in LABEL_CATALOG}
    must_have = {
        "690.13(B)",   # PV DC disconnect
        "690.14",      # PV AC disconnect
        "690.53",      # DC power source placard
        "690.56(C)",   # Rapid Shutdown
        "705.10",      # Source identification
        "706.7",       # ESS disconnect
    }
    missing = must_have - clauses
    assert not missing, f"catalog missing required NEC clauses: {missing}"


def test_all_severity_levels_have_styles():
    """Every severity used in the catalog must have a color style defined."""
    used = {s.severity for s in LABEL_CATALOG}
    assert used.issubset(SEVERITY_STYLES.keys())


def test_materialize_clears_all_placeholders():
    """After materialization, no `{{KEY}}` should remain in titles or body."""
    result = run(make_inputs())
    labels = materialize(LABEL_CATALOG, result, strict=True)
    for lbl in labels:
        assert "{{" not in lbl.title
        for line in lbl.body_lines:
            assert "{{" not in line


def test_supply_side_path_includes_705_11_excludes_705_12():
    """For the Smith-Residence example (supply-side recommended), the
    705.11 placard applies and the 705.12 'do not relocate' does not."""
    result = run(make_inputs())  # default = supply-side wins
    assert result.interconnect.recommended == "supply_side_tap"
    clauses = {l.nec_clause for l in materialize(LABEL_CATALOG, result)}
    assert "705.11" in clauses
    assert "705.12(B)(3)(2)" not in clauses


def test_120_rule_path_includes_705_12_excludes_705_11():
    """When the 120% rule is the chosen method, swap the conditional labels."""
    inputs = make_inputs(
        main_panel_a=200, busbar_a=225, inverter_a=30, battery_qty=1,
        per_unit=True,
        interconnection_methods=["120%_rule", "supply_side_tap"],
    )
    result = run(inputs)
    assert result.interconnect.recommended == "120%_rule"
    clauses = {l.nec_clause for l in materialize(LABEL_CATALOG, result)}
    assert "705.12(B)(3)(2)" in clauses
    assert "705.11" not in clauses


def test_render_pdf_writes_a_real_pdf_file(tmp_path: Path):
    """The generated file should be a valid PDF (starts with %PDF magic)."""
    result = run(make_inputs())
    out = tmp_path / "labels.pdf"
    n = render_for_result(result, out)
    assert n >= 7  # at least the always-on labels
    assert out.exists() and out.stat().st_size > 0
    assert out.read_bytes()[:4] == b"%PDF"


def test_label_text_includes_real_calculation_values(tmp_path: Path):
    """End-to-end: the rendered PDF should embed real Voc/OCPD/etc. strings.
    Verify by checking the underlying RenderedLabel objects (more robust than
    binary PDF inspection)."""
    result = run(make_inputs())
    labels = materialize(LABEL_CATALOG, result)

    flat = "\n".join(
        lbl.title + "\n" + "\n".join(lbl.body_lines)
        for lbl in labels
    )
    # Smith Residence example: PV OCPD = 25 A, Voc(cold) ≈ 644 V DC.
    assert "25 A" in flat       # PV OCPD on 690.53 placard
    assert "644 V DC" in flat   # Voc(cold) on 690.13(B) / 690.53
    assert "PV-1" in flat       # PV label appears on 705.10


def test_placeholder_pattern_matches_only_screaming_snake():
    assert PLACEHOLDER_RE.findall("{{FOO}} {{BAR_BAZ}}") == ["FOO", "BAR_BAZ"]
    assert PLACEHOLDER_RE.findall("{{lower}}") == []
