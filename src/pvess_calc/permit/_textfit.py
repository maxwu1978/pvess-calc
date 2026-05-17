"""Reportlab-canvas text fitting helper.

DESIGN.md §7 forbids `text[:N]` patterns in render code because they cut
silently mid-word and depend on font metrics nobody actually measured. This
helper does what `text[:N]` was *trying* to do: keep a string within a
column width, but using actual font metrics and adding an ellipsis so the
truncation is visible.

Usage:

    c.drawString(x, y, fit(c, item.detail, "Helvetica", 9, 2.5 * inch))

If the string fits, it's returned unchanged. If not, characters are
trimmed from the end (preserving the right-trimmed prefix) and "…" is
appended until the rendered width is below the limit.
"""
from __future__ import annotations

from reportlab.pdfbase.pdfmetrics import stringWidth


ELLIPSIS = "…"  # single-character horizontal ellipsis (1 char wide)


def fit(text: str, font: str, size: float, max_width_pt: float) -> str:
    """Return `text` if it fits in `max_width_pt`, else a shorter copy with
    an ellipsis. `max_width_pt` is in reportlab points (1 inch = 72 pt).

    Pure function — does no drawing, takes no canvas. Lets call sites stay
    declarative and lets unit tests exercise the truncation logic without
    instantiating a PDF.
    """
    if not text:
        return text
    if stringWidth(text, font, size) <= max_width_pt:
        return text
    # Binary-search the longest prefix that fits with an ellipsis suffix.
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        candidate = text[:mid].rstrip() + ELLIPSIS
        if stringWidth(candidate, font, size) <= max_width_pt:
            lo = mid
        else:
            hi = mid - 1
    # lo is the largest prefix length that fits with ellipsis.
    return text[:lo].rstrip() + ELLIPSIS
