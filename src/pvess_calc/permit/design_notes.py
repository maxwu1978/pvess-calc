"""PV-6 design notes sheet for reference-style packages."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from ..calc.engine import CalculationResult


DESIGN_NOTES = [
    "All equipment shall be installed per manufacturer instructions and applicable NEC, IRC, IFC, and AHJ amendments.",
    "All roof penetrations shall be flashed and sealed using listed products compatible with the roof covering.",
    "Installer shall verify roof framing, attic access, and exact rafter/truss locations prior to mounting.",
    "PV module locations shown are approximate and may be shifted in field to avoid verified obstructions while maintaining fire access pathways.",
    "String wiring shall follow the string plan; module-level power electronics shall be installed one per module unless otherwise noted.",
    "All conductors and raceways shall be supported, protected from abrasion, and routed to minimize exposed roof runs.",
    "Final equipment locations shall maintain NEC 110.26 working clearances and utility accessibility requirements.",
    "Any equipment substitution shall be equal or better and shall preserve listed ratings, conductor ampacity, OCPD sizing, and rapid shutdown compliance.",
]


def render_design_notes(result: CalculationResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=landscape(letter))
    W, H = landscape(letter)

    c.setLineWidth(1.0)
    c.rect(0.4 * inch, 0.4 * inch, W - 0.8 * inch, H - 0.8 * inch)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(W / 2, H - 0.8 * inch, "PV-6 · DESIGN NOTES")
    c.setFont("Helvetica", 9)
    c.drawCentredString(
        W / 2, H - 1.05 * inch,
        f"{result.inputs.project.client_name or result.inputs.project.name} · "
        f"NEC {result.inputs.project.nec_edition}",
    )

    x = 0.75 * inch
    y = H - 1.55 * inch
    w = W - 1.5 * inch
    c.setFont("Helvetica", 9)
    for idx, note in enumerate(DESIGN_NOTES, 1):
        if y < 0.85 * inch:
            break
        c.setFillColor(colors.HexColor("#1F2937"))
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, y, f"{idx}.")
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 9)
        lines = _wrap(c, note, w - 0.35 * inch, 9)
        for line_idx, line in enumerate(lines):
            c.drawString(x + 0.30 * inch, y, line)
            y -= 0.17 * inch if line_idx < len(lines) - 1 else 0
        y -= 0.25 * inch

    c.setFont("Helvetica-Bold", 9)
    c.drawString(0.75 * inch, 0.62 * inch, "STRUCTURAL NOTE:")
    c.setFont("Helvetica", 8.5)
    c.drawString(
        2.18 * inch, 0.62 * inch,
        "Engineer letter or draft structural packet governs framing and attachment assumptions.",
    )
    c.save()


def _wrap(c, text: str, max_w: float, size: float) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur: list[str] = []
    for word in words:
        trial = " ".join(cur + [word])
        if c.stringWidth(trial, "Helvetica", size) <= max_w:
            cur.append(word)
        else:
            if cur:
                lines.append(" ".join(cur))
            cur = [word]
    if cur:
        lines.append(" ".join(cur))
    return lines
