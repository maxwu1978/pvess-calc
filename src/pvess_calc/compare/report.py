"""Render the scenario comparison as Markdown + JSON."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .scenarios import ScenarioResult


def render_markdown(scenarios: list[ScenarioResult]) -> str:
    """Emit a side-by-side comparison table (one column per scenario)."""
    if not scenarios:
        return "# Scenario Comparison\n\n_No scenarios found._\n"

    lines = ["# Scenario Comparison", ""]
    # Header row: metric | A | B | C
    summaries = [s.summary for s in scenarios]
    metrics = list(summaries[0].keys())

    header = "| Metric | " + " | ".join(s["scenario"] for s in summaries) + " |"
    sep = "|---" + "|---" * len(summaries) + "|"
    lines.append(header)
    lines.append(sep)
    for m in metrics:
        if m == "scenario":
            continue
        row = "| " + m + " | " + " | ".join(s[m] for s in summaries) + " |"
        lines.append(row)

    lines.append("")
    lines.append("## BOM Breakdown")
    lines.append("")
    for s in scenarios:
        lines.append(f"### Scenario **{s.name}** — ${s.bom.subtotal_usd:,.0f}")
        lines.append("")
        lines.append("| Line | Qty | Unit (USD) | Total (USD) |")
        lines.append("|------|----:|-----------:|------------:|")
        for ln in s.bom.lines:
            lines.append(
                f"| {ln.label} | {ln.quantity} | "
                f"${ln.unit_price_usd:,.0f} | ${ln.total_usd:,.0f} |"
            )
        lines.append(f"| **Subtotal** | | | **${s.bom.subtotal_usd:,.0f}** |")
        lines.append("")
        lines.append(f"_{s.bom.note}_")
        lines.append("")
    return "\n".join(lines) + "\n"


def render_json(scenarios: list[ScenarioResult]) -> str:
    """Machine-readable dump of every scenario."""
    payload = []
    for s in scenarios:
        payload.append({
            "name": s.name,
            "inputs_path": str(s.inputs_path),
            "summary": s.summary,
            "bom_subtotal_usd": s.bom.subtotal_usd,
            "bom_lines": [asdict(ln) for ln in s.bom.lines],
            "result": s.result.to_dict(),
        })
    return json.dumps(payload, indent=2, ensure_ascii=False)


def write_outputs(
    scenarios: list[ScenarioResult],
    md_path: Path,
    json_path: Path,
    *,
    pdf_path: Optional[Path] = None,
    lookup_fields: Optional[dict] = None,
) -> None:
    """K.7 [4/4]: also emit a customer-facing comparison PDF alongside
    the existing Markdown + JSON outputs. `pdf_path` defaults to
    `md_path.with_suffix('.pdf')` so callers can opt out by passing
    an explicit `pdf_path=None` from the CLI."""
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(scenarios), encoding="utf-8")
    json_path.write_text(render_json(scenarios), encoding="utf-8")
    if scenarios:
        if pdf_path is None:
            pdf_path = md_path.with_suffix(".pdf")
        from .pdf import render_comparison_pdf
        render_comparison_pdf(scenarios, pdf_path, lookup_fields=lookup_fields)
