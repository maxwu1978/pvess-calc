"""Stage 9.10.5 — lightweight visual lint for PV-6 string plans."""
from __future__ import annotations

from dataclasses import dataclass

from ..calc.engine import CalculationResult
from .structural import (
    _can_draw_traced_string_plan,
    _pv6_string_callouts,
    _pv6_string_rollup,
    _pv6_trace_layout,
)


@dataclass(frozen=True)
class PV6LintResult:
    name: str
    status: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status in ("PASS", "WARN")


def lint_pv6_string_layout(result: CalculationResult) -> list[PV6LintResult]:
    """Run non-OCR checks for the traced PV-6 string plan."""
    if not _can_draw_traced_string_plan(result):
        return [PV6LintResult(
            "pv6_traced_string_layout",
            "PASS",
            "legacy PV-6 fallback active (no traced roof layout)",
        )]
    return [
        _lint_string_rollup_complete(result),
        _lint_string_callouts_present(result),
        _lint_string_callout_labels_clear(result),
    ]


def _lint_string_rollup_complete(result: CalculationResult) -> PV6LintResult:
    name = "pv6_string_rollup_complete"
    n_strings = result.inputs.pv_array.strings
    all_modules = [
        module
        for modules in result.module_placements.values()
        for module in modules
    ]
    if not all_modules:
        return PV6LintResult(name, "WARN", "no module placements to roll up")

    rollup = _pv6_string_rollup(result)
    assigned = sum(rollup.values())
    if assigned != len(all_modules):
        return PV6LintResult(
            name, "FAIL",
            f"{assigned}/{len(all_modules)} placed module(s) have string IDs",
        )

    invalid = [
        idx + 1 for idx, count in sorted(rollup.items())
        if count > 0 and (idx < 0 or idx >= n_strings)
    ]
    if invalid:
        return PV6LintResult(
            name, "FAIL",
            "module(s) assigned outside declared string range: "
            + ", ".join(f"STRING {idx}" for idx in invalid),
        )

    missing = [
        idx + 1 for idx in range(n_strings)
        if rollup.get(idx, 0) == 0
    ]
    if missing and result.inputs.pv_array.modules >= n_strings:
        return PV6LintResult(
            name, "FAIL",
            "declared string(s) have no modules: "
            + ", ".join(f"STRING {idx}" for idx in missing),
        )
    if missing:
        return PV6LintResult(
            name, "WARN",
            "module count is smaller than string count; empty string(s): "
            + ", ".join(f"STRING {idx}" for idx in missing),
        )

    return PV6LintResult(
        name,
        "PASS",
        f"{assigned} module(s) assigned across {n_strings} string(s)",
    )


def _lint_string_callouts_present(result: CalculationResult) -> PV6LintResult:
    name = "pv6_string_callouts_present"
    layout = _pv6_trace_layout(result)
    if layout is None:
        return PV6LintResult(name, "FAIL", "no traced PV-6 layout transform")

    rollup = _pv6_string_rollup(result)
    expected = {
        idx for idx in range(result.inputs.pv_array.strings)
        if rollup.get(idx, 0) > 0
    }
    callouts = _pv6_string_callouts(result, layout)
    seen = {c.string_index for c in callouts}
    missing = sorted(expected - seen)
    extra = sorted(seen - expected)
    if missing or extra:
        detail: list[str] = []
        if missing:
            detail.append(
                "missing " + ", ".join(f"STRING {idx + 1}" for idx in missing)
            )
        if extra:
            detail.append(
                "extra " + ", ".join(f"STRING {idx + 1}" for idx in extra)
            )
        return PV6LintResult(name, "FAIL", "; ".join(detail))
    return PV6LintResult(
        name,
        "PASS",
        f"{len(callouts)} string leader callout(s) present",
    )


def _lint_string_callout_labels_clear(
    result: CalculationResult,
) -> PV6LintResult:
    name = "pv6_string_callout_labels_clear"
    layout = _pv6_trace_layout(result)
    if layout is None:
        return PV6LintResult(name, "FAIL", "no traced PV-6 layout transform")

    callouts = _pv6_string_callouts(result, layout)
    frame = layout.frame
    problems: list[str] = []
    for callout in callouts:
        if not _bbox_inside(callout.label_bbox, frame):
            problems.append(f"{callout.text} outside page frame")

    for idx, a in enumerate(callouts):
        for b in callouts[idx + 1:]:
            area = _bbox_intersection_area(a.label_bbox, b.label_bbox)
            if area > 0.5:
                problems.append(f"{a.text} overlaps {b.text}")

    module_bboxes = _module_page_bboxes(result, layout)
    for callout in callouts:
        for label, module_bbox in module_bboxes:
            area = _bbox_intersection_area(callout.label_bbox, module_bbox)
            if area > 0.5:
                problems.append(f"{callout.text} overlaps module {label}")
                break

    if problems:
        return PV6LintResult(name, "FAIL", "; ".join(problems[:6]))
    return PV6LintResult(
        name,
        "PASS",
        f"{len(callouts)} callout label(s) fit without collisions",
    )


def _module_page_bboxes(result: CalculationResult, layout) -> list[
    tuple[str, tuple[float, float, float, float]]
]:
    from .site_plan import _ee4_module_site_points

    bboxes: list[tuple[str, tuple[float, float, float, float]]] = []
    for section in result.inputs.site.roof_sections:
        for idx, module in enumerate(
            result.module_placements.get(section.name, []),
            1,
        ):
            pts = [layout.to_pt(p) for p in _ee4_module_site_points(section, module)]
            if len(pts) < 4:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            bboxes.append((
                f"{section.name}#{idx}",
                (min(xs), min(ys), max(xs), max(ys)),
            ))
    return bboxes


def _bbox_inside(
    inner: tuple[float, float, float, float],
    outer: tuple[float, float, float, float],
) -> bool:
    return (
        inner[0] >= outer[0]
        and inner[1] >= outer[1]
        and inner[2] <= outer[2]
        and inner[3] <= outer[3]
    )


def _bbox_intersection_area(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[2], b[2])
    y1 = min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0)
