"""K.7 [4/4] — scenario comparison PDF.

Produces a 1-page landscape PDF that places N scenarios side-by-side:
    * System size + battery + interconnect method
    * Annual production / monthly savings / payback (after ITC)
    * NEC status (Voc, AIC, voltage drop, interconnect FAIL/PASS)
    * BOM subtotal

Reuses the K.4 customer-summary design tokens so the comparison sheet
visually matches the rest of the customer-facing artifacts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from ..customer import compute_economics, design_tokens as dt
from .scenarios import ScenarioResult


# Tier of metrics shown — order = display order, top→bottom.
_METRIC_ROWS: list[tuple[str, str]] = [
    # (column key in summary, display label)
    ("PV (kW)",      "PV array"),
    ("AC (kW)",      "Inverter AC"),
    ("ESS (kWh)",    "Battery storage"),
    ("Backfeed (A)", "PV+ESS backfeed"),
    ("Interconnect", "705.12 method"),
    ("Voc cold (V)", "Voc cold-corrected"),
    ("PV OCPD",      "PV OCPD"),
    ("AC OCPD",      "AC disconnect OCPD"),
    ("Vd e2e",       "End-to-end Vd"),
    ("AIC margin",   "AIC margin"),
    ("BOM (USD)",    "BOM subtotal"),
]


def render_comparison_pdf(
    scenarios: list[ScenarioResult],
    out_path: Path,
    *,
    lookup_fields: Optional[dict] = None,
) -> Path:
    """Render the K.7 [4/4] comparison PDF.

    `lookup_fields` (optional): merged `LookupResult.fields` from K.3
    — when present, enables NEM 3.0 / NREL economic calcs per scenario.
    Same shape as `customer/pdf.render_customer_summary` expects.
    """
    if not scenarios:
        raise ValueError("render_comparison_pdf: no scenarios provided")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=landscape(letter),
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    styles = _styles()
    story: list = [
        Paragraph("<b>Scenario Comparison</b>", styles["title"]),
        Paragraph(
            f"{len(scenarios)} scenarios · "
            f"compared on system size · NEC compliance · economics · BOM",
            styles["sub"],
        ),
        Spacer(1, 0.15 * inch),
    ]

    # ─── Headline economics row ──────────────────────────────────────
    # Compute K.4 customer-summary economics for each scenario so we
    # can show monthly savings + ITC-adjusted payback alongside the
    # technical comparison. This is the K.7 [4/4] add: pvess-compare
    # was previously NEC-only, no $.
    econ_per = [
        compute_economics(s.result.inputs, lookup_fields=lookup_fields)
        for s in scenarios
    ]

    story.extend(_economics_strip(scenarios, econ_per, styles))
    story.append(Spacer(1, 0.10 * inch))
    story.extend(_metric_table(scenarios, styles))

    doc.build(story)
    return out_path


# ─── Blocks ──────────────────────────────────────────────────────────


def _economics_strip(scenarios, econ_per, styles) -> list:
    """Top strip: $ /mo / payback / annual production per scenario.
    Big numbers, reusable customer-facing tone."""
    n = len(scenarios)
    # Build 1 row of N cells. Each cell = 3 stacked lines.
    cells = []
    for s, e in zip(scenarios, econ_per):
        cell_content = [
            Paragraph(f"<b>{s.name}</b>", styles["hero_cell_title"]),
            Paragraph(
                f"<font color='{dt.COLOR_ACCENT.hexval()}'>"
                f"<b>${e.monthly_bill_savings_usd:,.0f}</b></font> / mo",
                styles["hero_cell_main"],
            ),
            Paragraph(
                f"${e.annual_bill_savings_usd:,.0f} / yr",
                styles["hero_cell_body"],
            ),
            Paragraph(
                f"<b>{e.payback_after_itc_years:.1f}</b> yr after ITC"
                if e.payback_after_itc_years is not None else
                "Payback: n/a",
                styles["hero_cell_body"],
            ),
            Paragraph(
                f"{e.annual_production_kwh:,.0f} kWh/yr",
                styles["hero_cell_caption"],
            ),
        ]
        cells.append(cell_content)

    tbl = Table([cells], colWidths=[(landscape(letter)[0] - 1.0 * inch) / n] * n)
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, -1), dt.COLOR_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, dt.COLOR_GRID),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, dt.COLOR_GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return [tbl]


def _metric_table(scenarios, styles) -> list:
    """Big side-by-side metric table — one row per metric, one column
    per scenario."""
    summaries = [s.summary for s in scenarios]
    header_row = ["Metric"] + [s["scenario"] for s in summaries]
    body_rows = []
    for key, label in _METRIC_ROWS:
        body_rows.append(
            [label] + [s.get(key, "—") for s in summaries]
        )

    data = [header_row] + body_rows
    col_w = (landscape(letter)[0] - 1.0 * inch - 2.2 * inch) / len(scenarios)
    tbl = Table(data, colWidths=[2.2 * inch] + [col_w] * len(scenarios))
    tbl.setStyle(TableStyle([
        # Header band
        ("BACKGROUND", (0, 0), (-1, 0), dt.COLOR_PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        # Body
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, -1), 9.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        # Grid + alternating rows
        ("GRID", (0, 0), (-1, -1), 0.3, dt.COLOR_GRID),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, dt.COLOR_BG]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return [tbl]


# ─── Styles ──────────────────────────────────────────────────────────


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle(
            "title", fontName="Helvetica", fontSize=dt.PT_TITLE,
            leading=dt.PT_TITLE * 1.15, textColor=dt.COLOR_INK,
        ),
        "sub": ParagraphStyle(
            "sub", fontName="Helvetica", fontSize=dt.PT_BODY,
            textColor=dt.COLOR_MUTED, leading=dt.PT_BODY * 1.2,
        ),
        "hero_cell_title": ParagraphStyle(
            "hero_cell_title", fontName="Helvetica", fontSize=11,
            textColor=dt.COLOR_INK, leading=14, alignment=1,
            spaceAfter=4,
        ),
        "hero_cell_main": ParagraphStyle(
            "hero_cell_main", fontName="Helvetica-Bold", fontSize=16,
            textColor=dt.COLOR_INK, leading=20, alignment=1,
            spaceAfter=2,
        ),
        "hero_cell_body": ParagraphStyle(
            "hero_cell_body", fontName="Helvetica", fontSize=dt.PT_BODY,
            textColor=dt.COLOR_INK, leading=dt.PT_BODY * 1.3,
            alignment=1, spaceAfter=1,
        ),
        "hero_cell_caption": ParagraphStyle(
            "hero_cell_caption", fontName="Helvetica", fontSize=dt.PT_MICRO,
            textColor=dt.COLOR_MUTED, leading=dt.PT_MICRO * 1.3,
            alignment=1,
        ),
    }
