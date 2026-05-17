"""DXF-text fitting helper — mirror of `permit/_textfit.py` for the DXF path.

DESIGN.md §7 forbids silent fixed-width truncation. The reportlab side has
`stringWidth` for real font metrics, but DXF/matplotlib renders with a
stroke-font whose width depends on the viewer (AutoCAD vs LibreCAD vs
matplotlib). We use a single empirically-tuned `CHAR_WIDTH_RATIO` instead —
it's an estimate, not a measurement, but it's close enough to drive both
proactive truncation (here) and the doctor's overflow check.

Tuning notes (2026-05-13):
  • Measured against EE-2 schedule overflow ("MSP → grounding electrode
    system" at h=0.075, observed visible width ≈ 1.55" for 32 chars):
    visible/char/height = 1.55/32/0.075 = 0.65.
  • We use 0.60 — slightly conservative so `fit_dxf` trims more
    aggressively (always fits) and the doctor's check triggers slightly
    LATER than a real overflow (no false-positive flag for tight-but-fits
    cases).
"""
from __future__ import annotations


# Estimated character width as a fraction of text height for DXF default
# (matplotlib-backend) font. See module docstring for derivation.
CHAR_WIDTH_RATIO = 0.60

ELLIPSIS = "..."  # ASCII triple-dot; DXF stroke fonts may lack U+2026 (…)


def estimate_text_width(text: str, char_height: float) -> float:
    """Return the estimated rendered width of `text` at `char_height` inches.

    Used both by `fit_dxf` (to decide whether to truncate) and by the
    doctor's `_check_dxf_text_no_overflow` (to detect overflow that the
    renderer wouldn't have prevented on its own).
    """
    return len(text) * char_height * CHAR_WIDTH_RATIO


def fit_dxf(text: str, max_width_in: float, char_height: float) -> str:
    """Return `text` if it fits in `max_width_in`, else a shorter copy
    appended with "...".

    All distances are in DXF user units (inches in our setup; INSUNITS=1).
    Pure function — no ezdxf or matplotlib imports.
    """
    if not text:
        return text
    if estimate_text_width(text, char_height) <= max_width_in:
        return text
    # Binary-search the longest prefix that fits with the ellipsis suffix.
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        candidate = text[:mid].rstrip() + ELLIPSIS
        if estimate_text_width(candidate, char_height) <= max_width_in:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + ELLIPSIS
