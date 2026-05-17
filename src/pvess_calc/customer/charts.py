"""Two-chart matplotlib renderer for K.4 customer-summary PDF.

Outputs PNG bytes (in-memory BytesIO) that reportlab embeds in the PDF.
Charts are intentionally minimal — no legends when avoidable, no
unnecessary tick marks, no chart titles inside the figure (the PDF's
section heading IS the title). DPI tuned for sharp print at 8.5×11.

The two-and-only-two chart types reflect the closing rule in
design_tokens.ALLOWED_CHART_KINDS:
  * `donut_offset_chart` — annual PV production vs household usage.
  * `bar_monthly_production_chart` — 12-month bars stacked on
    monthly_kwh use when present.
"""
from __future__ import annotations

import io
from typing import Optional, Sequence

import matplotlib

matplotlib.use("Agg")    # headless — no Tk/Qt dependency
import matplotlib.pyplot as plt

from . import design_tokens as dt


_DPI = 220


def donut_offset_chart(offset_pct: float, *, width_in: float = 2.6,
                       height_in: float = 2.6) -> bytes:
    """Donut showing what fraction of the homeowner's annual usage the
    PV system offsets. Capped at 200% (anything above is "you produce
    way more than you use").
    """
    pct = max(0.0, min(offset_pct, 200.0))
    # Trick: matplotlib doesn't natively render a >100% donut, so we
    # split the wedge into two sectors when pct > 100.
    if pct <= 100.0:
        sizes = [pct, 100.0 - pct]
        colors = [dt.MPL_PRIMARY, dt.MPL_GRID]
    else:
        # 100% bottom blue + excess as a brighter overlap ring.
        sizes = [100.0, pct - 100.0, 200.0 - pct]
        colors = [dt.MPL_PRIMARY, dt.MPL_ACCENT, dt.MPL_GRID]

    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=_DPI)
    ax.pie(sizes, colors=colors, startangle=90, counterclock=False,
           wedgeprops={"width": 0.32, "edgecolor": "white", "linewidth": 1.5})
    ax.text(0, 0.08, f"{pct:.0f}%", ha="center", va="center",
            fontsize=24, fontweight="bold", color=dt.MPL_INK)
    ax.text(0, -0.18, "annual offset", ha="center", va="center",
            fontsize=8, color=dt.MPL_MUTED)
    ax.set(aspect="equal")
    return _fig_to_png_bytes(fig)


def bar_monthly_production_chart(
    monthly_production_kwh: Sequence[float],
    *,
    monthly_usage_kwh: Optional[Sequence[float]] = None,
    width_in: float = 7.2,
    height_in: float = 2.6,
) -> bytes:
    """12-month production bars; overlays usage line when supplied.

    monthly_production_kwh must be length 12 (Jan..Dec).
    monthly_usage_kwh, if given, drives a faint comparison line."""
    assert len(monthly_production_kwh) == 12
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=_DPI)
    bars = ax.bar(months, monthly_production_kwh,
                  color=dt.MPL_PRIMARY, width=0.65, zorder=2)

    if monthly_usage_kwh is not None and len(monthly_usage_kwh) == 12:
        ax.plot(months, monthly_usage_kwh, color=dt.MPL_ACCENT,
                linewidth=2, marker="o", markersize=4, zorder=3,
                label="Household usage")
        ax.legend(loc="upper right", fontsize=8, frameon=False)

    # K.6 (F) polish: bumped axis labels 7 → 8.5 pt so a homeowner
    # holding the PDF at arm's length can read the month / kWh ticks
    # without leaning in. Caption-tier text on the rest of the PDF
    # stays at PT_MICRO (7.5 pt) so the chart's mild emphasis is
    # intentional, not accidental.
    ax.set_ylabel("kWh", fontsize=9, color=dt.MPL_MUTED)
    ax.tick_params(axis="x", labelsize=8.5, colors=dt.MPL_MUTED)
    ax.tick_params(axis="y", labelsize=8, colors=dt.MPL_MUTED)
    ax.grid(axis="y", color=dt.MPL_GRID, linewidth=0.6, zorder=1)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(dt.MPL_GRID)
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def _fig_to_png_bytes(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=_DPI, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    return buf.getvalue()
