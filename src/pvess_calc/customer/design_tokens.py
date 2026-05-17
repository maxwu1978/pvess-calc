"""K.4 design tokens — the single place that decides the customer-PDF
visual language.

Centralising all colors / type sizes / spacing here means:
  * The doctor can spot-check that the PDF respects the closing rule
    "≤3 font tiers, ≤2 chart-color palettes".
  * Tweaking the visual look is a one-file change — no risk of one
    chart drifting out of step with the title block.

Tier rationale (3 type sizes only — like Wyssling permit packets):
  * HERO  — big headline numbers (\"$483/mo\")
  * BODY  — running text, labels, axis ticks
  * MICRO — disclaimers, attribution, units

Color palette (2 active accents max):
  * PRIMARY (deep blue)  — system / production
  * ACCENT (warm orange) — savings / payback
Plus neutrals (dark / muted grey / faint grid).
"""
from __future__ import annotations

from reportlab.lib.colors import HexColor


# ─── Color palette ──────────────────────────────────────────────────────

COLOR_PRIMARY        = HexColor("#1F4E79")    # deep blue — PV / production / engineering
COLOR_ACCENT         = HexColor("#D97706")    # warm orange — savings / financial
COLOR_INK            = HexColor("#1F2937")    # body text
COLOR_MUTED          = HexColor("#6B7280")    # disclaimers, attribution
COLOR_GRID           = HexColor("#E5E7EB")    # chart gridlines, table rules
COLOR_BG             = HexColor("#FAFAFA")    # card backgrounds
COLOR_SUCCESS        = HexColor("#059669")    # backup hours, offset %

# matplotlib-friendly equivalents (str hex) — matplotlib accepts both
# but we keep parallel constants for clarity.
MPL_PRIMARY = "#1F4E79"
MPL_ACCENT  = "#D97706"
MPL_INK     = "#1F2937"
MPL_MUTED   = "#6B7280"
MPL_GRID    = "#E5E7EB"


# ─── Typography tiers ───────────────────────────────────────────────────
# Sizes are points. Three tiers — no more — match the Wyssling closing
# standard (DESIGN.md §7.5).

PT_HERO   = 28.0       # \"$483/mo\" headline numbers
PT_TITLE  = 18.0       # section banners (\"System Overview\")
PT_BODY   = 10.5       # paragraph text, table cells
PT_MICRO  = 7.5        # disclaimers, unit annotations


# ─── Spacing tokens ─────────────────────────────────────────────────────

GUTTER_OUTER_IN = 0.50    # page margin
GUTTER_SECTION_IN = 0.20  # between blocks
GUTTER_INNER_IN = 0.10    # within blocks
CARD_RADIUS_PT  = 6.0     # corner radius on stat cards


# ─── Chart limits (closing standard contract) ───────────────────────────
#
# K.4 collapses to TWO chart types only. Anything else means the PDF is
# competing with itself for the viewer's attention.
ALLOWED_CHART_KINDS: frozenset[str] = frozenset({"bar", "donut"})
