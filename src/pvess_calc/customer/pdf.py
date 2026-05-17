"""K.4 customer-summary PDF — one-pager (or two-page if monthly data
present) for homeowners.

Layout (US Letter, portrait):

  Page 1
    ┌────────────────────────────────────────────┐
    │  System Summary — {project name}          │  ← title block
    │────────────────────────────────────────────│
    │  [ 24 modules │ 13 kWh │ 8 kW inv ]       │  ← spec strip
    │────────────────────────────────────────────│
    │  $483/mo savings   |  [donut: 110% offset]│  ← hero numbers
    │  $5,802/year       |                       │
    │  14-yr payback*    |                       │
    │────────────────────────────────────────────│
    │  Backup runtime:                          │
    │    Essentials only:   10 hr                │
    │    With AC running:    5 hr               │
    │    With heat pump:     5 hr               │
    │────────────────────────────────────────────│
    │  [Monthly production bar chart, full width]│  ← only if monthly data
    │────────────────────────────────────────────│
    │  Notes:                                    │  ← footer / disclaimers
    │  *Cost estimate from regional benchmarks   │
    │   — confirm with installer.                │
    └────────────────────────────────────────────┘

Every block hides itself when its data is missing — a yaml with only
Phase 0 fields still renders a valid (shorter) PDF.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional, Sequence

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from ..calc.engine import CalculationResult
from . import charts, design_tokens as dt
from .backup import BackupResult, compute_backup
from .economics import EconomicsResult, compute_economics


# Average monthly distribution of solar production at mid-US latitudes
# (NREL TMY3 12-station blend). Used to break an annual figure into
# 12 monthly values when the PVWatts call didn't return per-month data.
# Sums to 1.0 exactly.
_DEFAULT_MONTHLY_FRACTIONS: tuple[float, ...] = (
    0.058, 0.066, 0.085, 0.094, 0.099, 0.099,
    0.099, 0.099, 0.091, 0.083, 0.067, 0.060,
)


# ─── Public entry ──────────────────────────────────────────────────────


def render_customer_summary(
    result: CalculationResult,
    out_path: Path,
    *,
    lookup_fields: Optional[dict] = None,
    monthly_production_kwh: Optional[Sequence[float]] = None,
) -> Path:
    """Render the K.4 customer-summary PDF.

    Args:
        result: CalculationResult from the engine (provides system specs).
        out_path: where to write the PDF.
        lookup_fields: merged `LookupResult.fields` from K.3 (optional;
            enables NREL-driven production + city-rate savings).
        monthly_production_kwh: explicit 12-value override (mostly for
            tests / future integration with PVWatts monthly response).
    """
    economics = compute_economics(result.inputs, lookup_fields=lookup_fields)
    backup = compute_backup(result.inputs)

    # Derive monthly production breakdown if not supplied explicitly.
    if monthly_production_kwh is None:
        monthly_production_kwh = tuple(
            economics.annual_production_kwh * f
            for f in _DEFAULT_MONTHLY_FRACTIONS
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=letter,
        leftMargin=dt.GUTTER_OUTER_IN * inch,
        rightMargin=dt.GUTTER_OUTER_IN * inch,
        topMargin=dt.GUTTER_OUTER_IN * inch,
        bottomMargin=dt.GUTTER_OUTER_IN * inch,
    )

    story = []
    styles = _styles()
    story.extend(_title_block(result, styles))
    story.extend(_spec_strip(result, styles))
    story.extend(_hero_numbers_and_donut(economics, styles))
    story.extend(_backup_block(backup, result, styles))
    if result.inputs.loads.monthly_kwh and len(result.inputs.loads.monthly_kwh) == 12:
        story.extend(_monthly_chart_block(
            monthly_production_kwh,
            result.inputs.loads.monthly_kwh,
            styles,
        ))
    else:
        story.extend(_monthly_chart_block(monthly_production_kwh, None, styles))
    # K.8: multi-face projects get an extra "per roof face" table so the
    # homeowner sees why a west-facing roof produces less than south.
    # Single-orientation projects skip this block entirely (no value to
    # show 1 row + a 1.00 derate).
    if len(economics.production_breakdown) >= 2:
        story.extend(_production_breakdown_block(economics, styles))
    # K.4.6.5: when the yaml carries `loads.backup_options[]`, render
    # the 3-tier quote table so the homeowner sees PV-only vs each
    # battery upgrade tier side-by-side. Empty list = old behavior.
    if result.inputs.loads.backup_options:
        from .quote_tiers import compute_quote_tiers
        tiers = compute_quote_tiers(result.inputs, lookup_fields=lookup_fields)
        story.extend(_quote_tiers_block(tiers, styles))
    story.extend(_footer_block(economics, styles))

    doc.build(story)
    return out_path


# ─── Blocks ────────────────────────────────────────────────────────────


def _title_block(result: CalculationResult, styles) -> list:
    proj = result.inputs.project
    title = f"<b>System Summary &mdash; {proj.name}</b>"
    sub = f"{proj.location}"
    if proj.client_name:
        sub = f"{proj.client_name} &nbsp;&nbsp;|&nbsp;&nbsp; {sub}"
    return [
        Paragraph(title, styles["title"]),
        Paragraph(sub, styles["sub"]),
        Spacer(1, dt.GUTTER_SECTION_IN * inch),
    ]


def _spec_strip(result: CalculationResult, styles) -> list:
    """Spec values side by side. 3 cells (PV / battery / inverter) for
    standard PV+ESS projects; K.4.6.1 — for PV-only projects
    (`battery.installed = False`, e.g. TX-market default) the battery
    cell collapses and the strip becomes 2 cells (PV / inverter) so
    we don't print "0.0 kWh battery storage" — which reads as a bug,
    not a feature."""
    inp = result.inputs
    inverter_kw = inp.inverter.ac_output_v * inp.inverter.ac_output_a / 1000.0
    inverter_count = inp.inverter.count(inp.battery.quantity)
    inverter_label = (
        f"<b>{inverter_kw * inverter_count:.1f}</b> kW AC"
    )
    inverter_cap = f"inverter{'s' if inverter_count > 1 else ''}"

    if inp.battery.installed:
        cells = [
            [
                Paragraph(f"<b>{inp.pv_array.modules}</b>", styles["hero_sm"]),
                Paragraph(
                    f"<b>{inp.battery.total_kwh:.1f}</b> kWh",
                    styles["hero_sm"]),
                Paragraph(inverter_label, styles["hero_sm"]),
            ],
            [
                Paragraph("PV modules", styles["caption"]),
                Paragraph("battery storage", styles["caption"]),
                Paragraph(inverter_cap, styles["caption"]),
            ],
        ]
        col_widths = [2.5 * inch] * 3
    else:
        # PV-only: 2 cells centred, slightly wider so the strip
        # doesn't look orphaned.
        cells = [
            [
                Paragraph(f"<b>{inp.pv_array.modules}</b>", styles["hero_sm"]),
                Paragraph(inverter_label, styles["hero_sm"]),
            ],
            [
                Paragraph("PV modules", styles["caption"]),
                Paragraph(inverter_cap, styles["caption"]),
            ],
        ]
        col_widths = [3.75 * inch] * 2

    tbl = Table(cells, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), dt.COLOR_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, dt.COLOR_GRID),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, dt.COLOR_GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return [tbl, Spacer(1, dt.GUTTER_SECTION_IN * inch)]


def _hero_numbers_and_donut(econ: EconomicsResult, styles) -> list:
    """Big savings numbers + (optional) donut. K.4.5 polish:
       * If `offset_pct` is None → donut is hidden AND the hero
         column expands to full page width (no orphan whitespace).
       * Payback shows BOTH before-ITC and after-30%-ITC numbers so
         the homeowner sees the realistic-after-incentive deal too.
    """
    # Build the hero stack first — same content either layout.
    hero_lines = [
        Paragraph(
            f'<font color="{dt.COLOR_ACCENT.hexval()}"><b>${econ.monthly_bill_savings_usd:,.0f}</b></font>',
            styles["hero"]),
        Paragraph("estimated monthly savings", styles["caption_left"]),
        Paragraph(
            f"<b>${econ.annual_bill_savings_usd:,.0f}</b> / year",
            styles["body"]),
    ]
    if econ.payback_period_years is not None and econ.payback_after_itc_years is not None:
        # Show after-ITC prominently (that's the deal homeowners get),
        # before-ITC as the small comparison. The PDF footer explains.
        hero_lines.append(Paragraph(
            f'Payback: <b>{econ.payback_after_itc_years:.1f}</b> yr '
            f"after 30% federal ITC "
            f'<font color="{dt.COLOR_MUTED.hexval()}">'
            f"(<b>{econ.payback_period_years:.1f}</b> yr before)</font>",
            styles["body"]))
    elif econ.payback_period_years is not None:
        hero_lines.append(Paragraph(
            f"<b>{econ.payback_period_years:.1f}</b> years to payback*",
            styles["body"]))

    has_donut = econ.offset_pct is not None
    if not has_donut:
        # Degraded mode: hero takes the full page width, centered horizontally.
        return [*hero_lines, Spacer(1, dt.GUTTER_SECTION_IN * inch)]

    # Full layout: hero on left, donut on right with proper column span.
    donut_png = charts.donut_offset_chart(econ.offset_pct)
    donut_img = Image(io.BytesIO(donut_png),
                      width=2.4 * inch, height=2.4 * inch)

    n = len(hero_lines)
    cells = []
    for i, line in enumerate(hero_lines):
        right = donut_img if i == 0 else ""
        cells.append([line, right])
    tbl = Table(cells, colWidths=[4.7 * inch, 2.8 * inch])
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("SPAN", (1, 0), (1, n - 1)),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("VALIGN", (1, 0), (1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return [tbl, Spacer(1, dt.GUTTER_SECTION_IN * inch)]


def _backup_block(backup: BackupResult, result: CalculationResult,
                  styles) -> list:
    """Backup runtime table. K.4.5 polish: when HVAC type is `unknown`
    (no signal to distinguish summer cooling from winter heating), we
    collapse the two HVAC rows into ONE 'with typical HVAC load' row —
    showing the same number twice with different labels looked like a
    bug. With a known HVAC type the two rows give homeowners the
    seasonal contrast they actually care about (heat pumps vs gas).

    K.4.6.1 — PV-only path: when `battery.installed = False` (TX-market
    default, the homeowner accepted the grid-tied tradeoff for the
    8-yr ROI), replace the runtime table with a single explanatory
    notice. NEC 690.10 requires non-islanding inverters to disconnect
    on grid loss; the home goes dark when the utility does. Adding a
    battery later (see ROADMAP K.4.6.5 3-tier quote) is the path back
    to backup capability without re-quoting the PV side.
    """
    # K.4.6.1: PV-only short-circuit BEFORE any runtime math.
    if not result.inputs.battery.installed:
        notice = (
            "<b>PV-only system &mdash; grid-tied, no outage backup.</b>  "
            "Per NEC 690.10 the inverter shuts down when the utility goes "
            "down, so the panels won't power your home during a blackout.  "
            "Adding a battery later (see your installer's options) "
            "restores backup capability without changing the PV array."
        )
        return [
            Paragraph("<b>Backup runtime</b>", styles["section_title"]),
            Paragraph(notice, styles["body"]),
            Spacer(1, dt.GUTTER_SECTION_IN * inch),
        ]

    hvac = result.inputs.loads.hvac_type or "unknown"
    rows: list[list] = [[
        Paragraph("<b>Backup runtime</b> (estimated)",
                  styles["section_title"]), ""
    ]]

    # Row 1 (always): essentials only.
    rows.append([
        Paragraph("Essentials only (no HVAC)", styles["body"]),
        Paragraph(
            f'<font color="{dt.COLOR_SUCCESS.hexval()}">'
            f'<b>{backup.backup_hours_loads_only:.0f}</b> h</font>',
            styles["body_right"]),
    ])

    # HVAC rows use .1f so seasonal contrast is visible — heat-pump
    # summer 5.2 h vs winter 4.6 h both round to 5 with .0f, defeating
    # the entire reason for showing two rows. Essentials stays .0f (no
    # comparison to defend; 10 h reads cleaner than 10.2 h).
    if hvac == "unknown":
        # Single combined row — summer/winter are equal by construction
        # when type is unknown (HVAC_PEAK_W['unknown'] has summer=winter).
        rows.append([
            Paragraph("With typical HVAC load", styles["body"]),
            Paragraph(f"<b>{backup.backup_hours_summer:.1f}</b> h",
                      styles["body_right"]),
        ])
    else:
        summer_label = (
            "With AC running" if hvac in ("heat_pump", "gas_furnace_ac")
            else "With cooling load"
        )
        winter_label = {
            "heat_pump":           "With heat pump heating",
            "gas_furnace_ac":      "With furnace running",
            "electric_resistance": "With electric heating",
        }.get(hvac, "With winter heating load")
        rows.append([
            Paragraph(summer_label, styles["body"]),
            Paragraph(f"<b>{backup.backup_hours_summer:.1f}</b> h",
                      styles["body_right"]),
        ])
        rows.append([
            Paragraph(winter_label, styles["body"]),
            Paragraph(f"<b>{backup.backup_hours_winter:.1f}</b> h",
                      styles["body_right"]),
        ])

    tbl = Table(rows, colWidths=[5.5 * inch, 2.0 * inch])
    tbl.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, dt.COLOR_GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return [tbl, Spacer(1, dt.GUTTER_SECTION_IN * inch)]


def _monthly_chart_block(
    production: Sequence[float],
    usage: Optional[Sequence[float]],
    styles,
) -> list:
    png = charts.bar_monthly_production_chart(production, monthly_usage_kwh=usage)
    title = ("<b>Estimated monthly production</b> "
             "(blue) vs. household usage (orange line)"
             if usage else
             "<b>Estimated monthly production</b>")
    return [
        Paragraph(title, styles["section_title"]),
        Image(io.BytesIO(png), width=7.2 * inch, height=2.55 * inch),
        Spacer(1, dt.GUTTER_SECTION_IN * inch),
    ]


def _production_breakdown_block(econ: EconomicsResult, styles) -> list:
    """K.8: per-face production breakdown for multi-face arrays.

    A roof with a south face AND a west face produces noticeably
    different kWh per kW — the homeowner deserves to see why their
    array doesn't quite hit "rated capacity × peak hours". One row
    per face: face name, capacity, azimuth/tilt, orientation derate,
    shading factor, estimated annual kWh.
    """
    rows = [[
        Paragraph("<b>Roof face</b>", styles["caption"]),
        Paragraph("<b>kW DC</b>", styles["caption"]),
        Paragraph("<b>Azimuth / tilt</b>", styles["caption"]),
        Paragraph("<b>Orientation</b>", styles["caption"]),
        Paragraph("<b>Shading</b>", styles["caption"]),
        Paragraph("<b>kWh / yr</b>", styles["caption"]),
    ]]
    for face in econ.production_breakdown:
        rows.append([
            Paragraph(face.name, styles["body"]),
            Paragraph(f"{face.kw_dc:.1f}", styles["body"]),
            Paragraph(
                f"{face.azimuth_deg:.0f}° / {face.tilt_deg:.0f}°",
                styles["body"]),
            Paragraph(f"{face.orientation_derate*100:.0f}%", styles["body"]),
            Paragraph(f"{face.shading_factor*100:.0f}%", styles["body"]),
            Paragraph(f"{face.annual_production_kwh:,.0f}", styles["body"]),
        ])

    tbl = Table(
        rows,
        colWidths=[1.6 * inch, 0.7 * inch, 1.2 * inch,
                   1.1 * inch, 0.9 * inch, 1.0 * inch],
    )
    tbl.setStyle(TableStyle([
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, dt.COLOR_GRID),
        ("BACKGROUND", (0, 0), (-1, 0), dt.COLOR_BG),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    title = "<b>Production by roof face</b>"
    blurb = (
        f"Weighted average derate <b>{(econ.production_blended_derate or 1.0)*100:.0f}%</b> "
        "vs. an ideal south-facing roof. West / east faces and shading drop the number "
        "below the nameplate × peak-sun-hours rule of thumb."
    )
    return [
        Paragraph(title, styles["section_title"]),
        tbl,
        Spacer(1, dt.GUTTER_INNER_IN * inch),
        Paragraph(blurb, styles["micro"]),
        Spacer(1, dt.GUTTER_SECTION_IN * inch),
    ]


def _quote_tiers_block(tiers: list, styles) -> list:
    """K.4.6.5 — 3-tier quote comparison: base (PV-only or current
    config) + each `BackupOption`. Each tier gets one column showing
    cost / monthly savings / payback / backup capability.

    Key insight surfaced in the bottom blurb: monthly savings is
    IDENTICAL across all tiers (same PV array → same kWh → same
    bill offset). The upgrade is a backup-vs-cost decision, NOT a
    savings-vs-cost decision. This is the K.4.6 narrative payoff:
    don't quote Tesla PW3 to a customer who just wants the 8 yr
    payback — they walk because the headline payback inflates 50%.
    """
    if not tiers:
        return []

    # Row labels (leftmost column).
    row_labels = [
        "",                          # column header row (tier name)
        "Cost  (pre-ITC)",
        "Cost  (after 30% ITC)",
        "Estimated monthly savings",
        "Payback (post-ITC)",
        "Backup capability",
    ]

    # Tier columns: one per QuoteTier.
    def _cell_for(tier, row_idx: int) -> Paragraph:
        if row_idx == 0:
            # Tier name — bold; base gets a "✓ recommended" tag when
            # the base IS PV-only (the K.4.6 sales narrative).
            tag = ""
            if tier.is_base and tier.battery_kwh_total <= 0:
                tag = (f'  <font color="{dt.COLOR_SUCCESS.hexval()}" size="9">'
                       "<b>★ best ROI</b></font>")
            return Paragraph(
                f"<b>{tier.name}</b>{tag}",
                styles["body"],
            )
        if row_idx == 1:
            return Paragraph(f"${tier.installed_cost_usd:,.0f}",
                             styles["body_right"])
        if row_idx == 2:
            return Paragraph(f"${tier.cost_after_itc_usd:,.0f}",
                             styles["body_right"])
        if row_idx == 3:
            return Paragraph(f"${tier.monthly_savings_usd:,.0f} / mo",
                             styles["body_right"])
        if row_idx == 4:
            pb = tier.payback_after_itc_years
            return Paragraph(
                f"{pb:.1f} yr" if pb is not None else "—",
                styles["body_right"],
            )
        if row_idx == 5:
            return Paragraph(tier.backup_summary, styles["body"])
        return Paragraph("", styles["body"])

    # Build the matrix: rows × (1 label col + N tier cols)
    data = []
    for r, label in enumerate(row_labels):
        row = [Paragraph(f"<b>{label}</b>", styles["caption"]) if label
               else Paragraph("", styles["caption"])]
        for t in tiers:
            row.append(_cell_for(t, r))
        data.append(row)

    n_tiers = len(tiers)
    # 7.5 in usable width on Letter; label column ~2 in, tiers split rest.
    label_w = 2.0 * inch
    tier_w = (7.5 - 2.0) / n_tiers * inch
    col_widths = [label_w] + [tier_w] * n_tiers

    tbl = Table(data, colWidths=col_widths)

    # Highlight the base column (col index 1) — light tint so it's
    # the visual anchor. Other tiers stay neutral.
    style_cmds = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEABOVE", (0, 1), (-1, 1), 0.5, dt.COLOR_GRID),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, dt.COLOR_INK),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, dt.COLOR_GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    # Tier column dividers (vertical lines between tiers)
    for c in range(1, n_tiers + 1):
        style_cmds.append(
            ("LINEBEFORE", (c, 0), (c, -1), 0.4, dt.COLOR_GRID),
        )
    # Base-column tint
    for c, t in enumerate(tiers, start=1):
        if t.is_base:
            style_cmds.append(("BACKGROUND", (c, 0), (c, -1), dt.COLOR_BG))
    tbl.setStyle(TableStyle(style_cmds))

    # Footer blurb: the K.4.6 insight payoff.
    blurb = (
        "<b>Same monthly savings across every option</b> &mdash; the PV array "
        "is identical, so the bill offset is identical. The upgrade decision "
        "is about how many hours you want the lights on during a blackout, "
        "not about saving more money."
    )

    return [
        Paragraph("<b>Your options</b>", styles["section_title"]),
        Spacer(1, dt.GUTTER_INNER_IN * inch),
        tbl,
        Spacer(1, dt.GUTTER_INNER_IN * inch),
        Paragraph(blurb, styles["micro"]),
        Spacer(1, dt.GUTTER_SECTION_IN * inch),
    ]


def _footer_block(econ: EconomicsResult, styles) -> list:
    notes = []
    if econ.cost_source == "benchmark-estimate":
        notes.append(
            "Installed cost is a regional benchmark "
            f"(NREL Q1-2026 ~$3.50/W DC + $950/kWh ESS): "
            f"<b>${econ.installed_cost_usd:,.0f}</b> before incentives, "
            f"<b>${econ.cost_after_itc_usd:,.0f}</b> after the "
            f"{econ.itc_rate_used*100:.0f}% federal ITC. "
            "Final price depends on your installer quote plus any state "
            "or utility rebates we don't model."
        )
    notes.append(
        f"Production estimate: {econ.production_source}. "
        f"Utility rate: ${econ.utility_rate_usd_per_kwh:.3f}/kWh "
        f"({econ.rate_source})."
    )
    # K.7 [2/4] + K.4.6.6: surface the tariff model that actually drove
    # the savings number — was previously a hard-coded "1:1 net metering"
    # disclaimer regardless of project context.
    if econ.export_ratio_applied >= 0.99:
        # 1:1 plan — Smart Meter Texas / classic NEM. Self-consumption is
        # mathematically irrelevant; ALL kWh credit at retail.
        notes.append(
            f"Export tariff: <b>{econ.export_tariff_label}</b>. "
            "Smart-meter net metering credits EVERY kWh produced at "
            "retail — daytime export becomes nighttime credit, so "
            "timing of consumption doesn't change your savings."
        )
    else:
        # Sub-1:1 plan — self-consumption matters. K.4.6.6 surfaces the
        # SMT-load-shifting strategy as a homeowner action item.
        sc_pct = econ.self_consumption_fraction * 100
        ratio_pct = econ.export_ratio_applied * 100
        smt_hint = (
            "  &nbsp;&nbsp; <b>Tip:</b> with Smart Meter Texas you can shift "
            "dishwasher / EV charging / pool pump to PV-production hours "
            f"to raise self-consumption from {sc_pct:.0f}% to 60-70%, "
            "boosting savings without adding a battery."
        )
        notes.append(
            f"Export tariff: <b>{econ.export_tariff_label}</b>. "
            f"Self-consumption assumed {sc_pct:.0f}%; "
            f"exported kWh credit at {ratio_pct:.0f}% of retail."
            + smt_hint
        )

    return [
        Paragraph("<b>Notes</b>", styles["section_title"]),
        *[Paragraph(n, styles["micro"]) for n in notes],
    ]


# ─── Styles ────────────────────────────────────────────────────────────


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle(
            "title", fontName="Helvetica", fontSize=dt.PT_TITLE,
            leading=dt.PT_TITLE * 1.1, textColor=dt.COLOR_INK,
            spaceBefore=0, spaceAfter=2,
        ),
        "sub": ParagraphStyle(
            "sub", fontName="Helvetica", fontSize=dt.PT_BODY,
            textColor=dt.COLOR_MUTED, leading=dt.PT_BODY * 1.2,
            spaceAfter=0,
        ),
        "hero": ParagraphStyle(
            "hero", fontName="Helvetica-Bold", fontSize=dt.PT_HERO,
            leading=dt.PT_HERO * 1.05, textColor=dt.COLOR_INK,
        ),
        "hero_sm": ParagraphStyle(
            "hero_sm", fontName="Helvetica-Bold", fontSize=dt.PT_TITLE,
            alignment=1, leading=dt.PT_TITLE * 1.1, textColor=dt.COLOR_INK,
        ),
        "section_title": ParagraphStyle(
            "section_title", fontName="Helvetica", fontSize=dt.PT_BODY + 1.5,
            leading=dt.PT_BODY * 1.4, textColor=dt.COLOR_INK,
            spaceBefore=2, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body", fontName="Helvetica", fontSize=dt.PT_BODY,
            leading=dt.PT_BODY * 1.35, textColor=dt.COLOR_INK,
        ),
        "body_right": ParagraphStyle(
            "body_right", fontName="Helvetica", fontSize=dt.PT_BODY,
            leading=dt.PT_BODY * 1.35, textColor=dt.COLOR_INK, alignment=2,
        ),
        "caption": ParagraphStyle(
            "caption", fontName="Helvetica", fontSize=dt.PT_MICRO,
            alignment=1, textColor=dt.COLOR_MUTED, leading=dt.PT_MICRO * 1.2,
        ),
        # K.6 (F) polish: hero's "estimated monthly savings" caption
        # needs a left-aligned variant — center-alignment inside the
        # 4.7" hero column made it appear to float in empty space.
        "caption_left": ParagraphStyle(
            "caption_left", fontName="Helvetica", fontSize=dt.PT_MICRO,
            alignment=0, textColor=dt.COLOR_MUTED, leading=dt.PT_MICRO * 1.2,
        ),
        "micro": ParagraphStyle(
            "micro", fontName="Helvetica", fontSize=dt.PT_MICRO,
            leading=dt.PT_MICRO * 1.4, textColor=dt.COLOR_MUTED,
            spaceAfter=2,
        ),
    }
