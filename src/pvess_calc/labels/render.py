"""Render NEC label placards to a print-ready PDF.

Layout: US Letter portrait, 6 labels per page (2 columns × 3 rows). Each label
is sized roughly 3.5" × 3.0" — readable, and stages nicely onto common Avery
adhesive sheets if the AHJ expects field-applied labels.

Severity color conventions follow ANSI Z535.4 (which NEC 110.21(B) effectively
codifies for electrical labels): DANGER = white-on-red, WARNING = black-on-
orange, CAUTION = black-on-yellow, NOTICE = white-on-blue.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.colors import Color, HexColor, black, white
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from ..calc.engine import CalculationResult
from ..qet.inject import build_substitutions
from .specs import LABEL_CATALOG, LabelSpec, Severity

PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Z0-9_]+)\s*\}\}")


SEVERITY_STYLES: dict[Severity, tuple[Color, Color]] = {
    # (banner background, banner text color)
    "DANGER":  (HexColor("#C00000"), white),
    "WARNING": (HexColor("#F4A300"), black),
    "CAUTION": (HexColor("#FFD400"), black),
    "NOTICE":  (HexColor("#1F5BD7"), white),
    "PLAIN":   (HexColor("#E0E0E0"), black),
}

# Page grid
PAGE_W, PAGE_H = letter
COLS, ROWS = 2, 3
MARGIN = 0.4 * inch
LABEL_W = (PAGE_W - 2 * MARGIN) / COLS
LABEL_H = (PAGE_H - 2 * MARGIN) / ROWS


def _substitute(text: str, subs: dict[str, str]) -> tuple[str, list[str]]:
    missing: list[str] = []

    def repl(m: re.Match[str]) -> str:
        k = m.group(1)
        if k in subs:
            return subs[k]
        missing.append(k)
        return m.group(0)

    return PLACEHOLDER_RE.sub(repl, text), missing


@dataclass
class RenderedLabel:
    """A spec after placeholder substitution; what we actually draw."""
    nec_clause: str
    severity: Severity
    title: str
    body_lines: list[str]
    location_hint: str


def materialize(
    catalog: list[LabelSpec], result: CalculationResult, strict: bool = True
) -> list[RenderedLabel]:
    """Filter the catalog by `applies(result)` and substitute placeholders."""
    subs = build_substitutions(result)
    out: list[RenderedLabel] = []
    missing_all: list[str] = []
    for spec in catalog:
        if not spec.applies(result):
            continue
        title, m1 = _substitute(spec.title, subs)
        body = []
        for line in spec.body_lines:
            line_out, m2 = _substitute(line, subs)
            body.append(line_out)
            missing_all.extend(m2)
        missing_all.extend(m1)
        out.append(RenderedLabel(
            nec_clause=spec.nec_clause,
            severity=spec.severity,
            title=title,
            body_lines=body,
            location_hint=spec.location_hint,
        ))
    if strict and missing_all:
        raise KeyError(f"Unresolved label placeholders: {sorted(set(missing_all))}")
    return out


def _draw_label(c: canvas.Canvas, x: float, y: float, lbl: RenderedLabel) -> None:
    """Draw one label inside a (LABEL_W × LABEL_H) box anchored at (x, y) bot-left."""
    bg, fg = SEVERITY_STYLES[lbl.severity]
    pad = 0.12 * inch
    banner_h = 0.35 * inch
    inner_w = LABEL_W - 2 * pad

    # Outer border (cut line for installer)
    c.setStrokeColor(black)
    c.setLineWidth(0.5)
    c.rect(x + pad, y + pad, LABEL_W - 2 * pad, LABEL_H - 2 * pad, stroke=1, fill=0)

    # Severity banner across top of label
    banner_y = y + LABEL_H - pad - banner_h
    c.setFillColor(bg)
    c.rect(x + pad, banner_y, LABEL_W - 2 * pad, banner_h, stroke=0, fill=1)
    c.setFillColor(fg)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(x + LABEL_W / 2, banner_y + banner_h / 2 - 4, lbl.severity)

    # Title (bold caps, may have \n)
    c.setFillColor(black)
    title_y = banner_y - 0.18 * inch
    c.setFont("Helvetica-Bold", 11)
    for line in lbl.title.split("\n"):
        c.drawCentredString(x + LABEL_W / 2, title_y, line.upper())
        title_y -= 0.18 * inch

    # Body lines
    body_y = title_y - 0.05 * inch
    c.setFont("Helvetica", 8.5)
    for line in lbl.body_lines:
        c.drawString(x + pad + 0.05 * inch, body_y, line)
        body_y -= 0.13 * inch

    # Footnote: NEC clause + install location
    c.setFont("Helvetica-Oblique", 6.5)
    c.setFillColor(HexColor("#555555"))
    c.drawString(x + pad + 0.05 * inch, y + pad + 0.10 * inch,
                 f"NEC {lbl.nec_clause}  ·  {lbl.location_hint}")


def render_pdf(labels: list[RenderedLabel], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=letter)
    c.setTitle("NEC Labels — pvess-calc")

    for i, lbl in enumerate(labels):
        slot = i % (COLS * ROWS)
        if i > 0 and slot == 0:
            c.showPage()
        col = slot % COLS
        row = slot // COLS
        x = MARGIN + col * LABEL_W
        # Row 0 is top; reportlab origin is bottom-left.
        y = PAGE_H - MARGIN - (row + 1) * LABEL_H
        _draw_label(c, x, y, lbl)

    c.save()


def render_for_result(result: CalculationResult, out_path: Path) -> int:
    """Convenience: materialize the catalog for a CalculationResult and write
    the PDF. Returns the number of labels rendered."""
    labels = materialize(LABEL_CATALOG, result, strict=True)
    render_pdf(labels, out_path)
    return len(labels)
