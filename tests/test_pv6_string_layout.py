"""Stage 9.10 — PV-6 traced whole-roof string layout."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pypdf

from pvess_calc.calc.engine import run
from pvess_calc.permit.pv6_lint import (
    _bbox_intersection_area,
    lint_pv6_string_layout,
)
from pvess_calc.permit.structural import (
    _pv6_string_callouts,
    _pv6_string_rollup,
    _pv6_trace_layout,
    render_string_plan,
)
from pvess_calc.schema import Inputs


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUSTIN = PROJECT_ROOT / "projects" / "001-demo-austin" / "inputs.yaml"
FRISCO = PROJECT_ROOT / "projects" / "003-frisco-glasshouse" / "inputs.yaml"


def _pdf_text(path: Path) -> str:
    return "\n".join(p.extract_text() or ""
                     for p in pypdf.PdfReader(str(path)).pages)


def test_stage910_frisco_pv6_uses_traced_whole_roof_layout(tmp_path: Path):
    result = run(Inputs.from_yaml(FRISCO))
    out = tmp_path / "frisco-pv6.pdf"
    render_string_plan(result, out)

    text = _pdf_text(out)
    assert "PV-6 · STRING LAYOUT PLAN" in text
    assert "EQUIPMENT SUMMARY" in text
    assert "STRING 1: (9) MODULES" in text
    assert "STRING 2: (9) MODULES" in text
    assert "STRING 3: (9) MODULES" in text
    assert "STRING 4: (9) MODULES" in text
    assert text.count("STRING 1") >= 2
    assert "PER-STRING DETAILS" not in text


def test_stage9104_pv6_emits_one_external_callout_per_string():
    result = run(Inputs.from_yaml(FRISCO))
    layout = _pv6_trace_layout(result)
    assert layout is not None

    callouts = _pv6_string_callouts(result, layout)

    assert [c.text for c in callouts] == [
        "STRING 1",
        "STRING 2",
        "STRING 3",
        "STRING 4",
    ]
    assert all(c.target != c.label_anchor for c in callouts)
    assert {c.side for c in callouts} <= {"top", "right", "bottom", "left"}

    frame = layout.frame
    for callout in callouts:
        x0, y0, x1, y1 = callout.label_bbox
        assert frame[0] <= x0 < x1 <= frame[2]
        assert frame[1] <= y0 < y1 <= frame[3]
    for idx, a in enumerate(callouts):
        for b in callouts[idx + 1:]:
            assert _bbox_intersection_area(a.label_bbox, b.label_bbox) == 0


def test_stage910_pv6_string_rollup_matches_placements():
    result = run(Inputs.from_yaml(FRISCO))
    counts = _pv6_string_rollup(result)

    assert counts == {0: 9, 1: 9, 2: 9, 3: 9}
    assert sum(counts.values()) == sum(
        len(mods) for mods in result.module_placements.values()
    )


def test_stage9105_pv6_visual_lint_passes_for_frisco():
    result = run(Inputs.from_yaml(FRISCO))
    lint_results = lint_pv6_string_layout(result)

    assert lint_results
    assert all(r.status == "PASS" for r in lint_results), lint_results


def test_stage9105_pv6_visual_lint_fails_when_a_string_is_missing():
    result = run(Inputs.from_yaml(FRISCO))
    for face_name, modules in list(result.module_placements.items()):
        result.module_placements[face_name] = [
            replace(m, string_index=0 if m.string_index == 3 else m.string_index)
            for m in modules
        ]

    lint_results = lint_pv6_string_layout(result)
    rollup = next(r for r in lint_results if r.name == "pv6_string_rollup_complete")

    assert rollup.status == "FAIL"
    assert "STRING 4" in rollup.detail


def test_stage9105_doctor_fails_on_pv6_label_collision(monkeypatch):
    import pvess_calc.permit.pv6_lint as pv6_lint
    from pvess_calc.doctor import _check_pv6_string_layout_visual_lint

    result = run(Inputs.from_yaml(FRISCO))
    original = pv6_lint._pv6_string_callouts

    def colliding_callouts(result, layout=None):
        callouts = original(result, layout)
        if len(callouts) < 2:
            return callouts
        first_bbox = callouts[0].label_bbox
        return [
            callout if idx == 0 else replace(callout, label_bbox=first_bbox)
            for idx, callout in enumerate(callouts)
        ]

    monkeypatch.setattr(pv6_lint, "_pv6_string_callouts", colliding_callouts)

    [check] = _check_pv6_string_layout_visual_lint(result)

    assert check.status == "FAIL"
    assert "overlaps" in check.detail


def test_stage910_pv6_legacy_fallback_still_renders(tmp_path: Path):
    result = run(Inputs.from_yaml(AUSTIN))
    out = tmp_path / "austin-pv6.pdf"
    render_string_plan(result, out)

    text = _pdf_text(out)
    assert "PV-6 · STRING LAYOUT PLAN" in text
    assert "ROOF SECTION PLANS" in text
    assert "PER-STRING DETAILS" in text
    assert out.stat().st_size > 2_500
