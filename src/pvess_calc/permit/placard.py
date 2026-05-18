"""EE-5 placard sheet for reference-style packages."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from ..calc.engine import CalculationResult
from ._textfit import fit


def render_placard_sheet(result: CalculationResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=landscape(letter))
    W, H = landscape(letter)
    i = result.inputs

    c.setLineWidth(1.0)
    c.rect(0.4 * inch, 0.4 * inch, W - 0.8 * inch, H - 0.8 * inch)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(W / 2, H - 0.8 * inch, "EE-5 · PLACARD")

    x = 2.65 * inch
    y = 1.85 * inch
    w = W - 5.3 * inch
    h = H - 3.1 * inch
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.1)
    c.rect(x, y, w, h)

    c.setFillColor(colors.HexColor("#F4A300"))
    c.rect(x, y + h - 0.58 * inch, w, 0.58 * inch, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(x + w / 2, y + h - 0.40 * inch, "CAUTION")

    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(x + w / 2, y + h - 1.08 * inch,
                        "POWER TO THIS BUILDING IS ALSO SUPPLIED")
    c.drawCentredString(x + w / 2, y + h - 1.36 * inch,
                        "FROM THE FOLLOWING SOURCES")

    rows = [
        ("UTILITY SERVICE", i.project.utility or "UTILITY"),
        ("PV SYSTEM", f"{i.pv_array.modules} modules / "
                      f"{i.pv_array.modules * i.pv_array.module.power_w / 1000:.2f} kW DC"),
        ("INVERTER", f"{i.inverter.brand} {i.inverter.model}"),
        ("INTERCONNECTION", result.interconnect.recommended or "FIELD VERIFY"),
    ]
    c.setFont("Helvetica", 10)
    yy = y + h - 1.92 * inch
    for label, value in rows:
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(x + 2.25 * inch, yy, label + ":")
        c.setFont("Helvetica", 10)
        c.drawString(x + 2.40 * inch, yy, fit(value, "Helvetica", 10, w - 2.70 * inch))
        yy -= 0.30 * inch

    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(x + w / 2, y + 0.52 * inch,
                        "SEE SITE PLAN AND LABEL SHEET FOR DISCONNECT LOCATIONS")
    c.setFont("Helvetica", 7)
    c.drawRightString(W - 0.42 * inch, 0.42 * inch, "EE-5 · PLACARD")
    c.save()
