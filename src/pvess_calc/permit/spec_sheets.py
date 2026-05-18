"""SPEC placeholder sheet for reference-style permit packages."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from ..calc.engine import CalculationResult
from ._textfit import fit


def render_spec_placeholder(result: CalculationResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=landscape(letter))
    W, H = landscape(letter)
    i = result.inputs

    c.setLineWidth(1.0)
    c.rect(0.4 * inch, 0.4 * inch, W - 0.8 * inch, H - 0.8 * inch)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(W / 2, H - 0.8 * inch, "SPEC · SPECIFICATION SHEETS")

    c.setFont("Helvetica", 9)
    c.drawCentredString(
        W / 2, H - 1.05 * inch,
        "Manufacturer datasheets are appended here when provided in "
        "project.spec_sheets[] for selected equipment.",
    )

    rows = [
        ("PV MODULE", f"{i.pv_array.module.brand} {i.pv_array.module.model}"),
        ("INVERTER", f"{i.inverter.brand} {i.inverter.model}"),
        ("OPTIMIZER", f"{i.optimizer.brand} {i.optimizer.model}" if i.optimizer.brand else "—"),
        ("MOUNTING", i.site.mounting.rail_system or "—"),
        ("FLASHING", i.site.mounting.flashing or i.project.roof_info.flashing or "—"),
        ("BATTERY", f"{i.battery.brand} {i.battery.model}" if i.battery.installed else "PV-only — no ESS"),
    ]

    x = 1.0 * inch
    y = H - 1.65 * inch
    w = W - 2.0 * inch
    row_h = 0.34 * inch
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.5)
    c.rect(x, y - row_h * (len(rows) + 1), w, row_h * (len(rows) + 1))
    c.setFillColor(colors.HexColor("#E5E7EB"))
    c.rect(x, y - row_h, w, row_h, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x + 0.12 * inch, y - 0.22 * inch, "EQUIPMENT")
    c.drawString(x + 2.1 * inch, y - 0.22 * inch, "SELECTED MODEL")
    c.drawString(x + 6.0 * inch, y - 0.22 * inch, "SPEC STATUS")

    c.setFont("Helvetica", 8.5)
    for idx, (label, value) in enumerate(rows, 1):
        yy = y - row_h * (idx + 1)
        c.line(x, yy + row_h, x + w, yy + row_h)
        c.drawString(x + 0.12 * inch, yy + 0.11 * inch, label)
        c.drawString(
            x + 2.1 * inch,
            yy + 0.11 * inch,
            fit(value, "Helvetica", 8.5, 3.75 * inch),
        )
        c.drawString(x + 6.0 * inch, yy + 0.11 * inch, "PDF REQUIRED / PLACEHOLDER")

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#B45309"))
    c.drawString(x, 0.85 * inch, "REVIEW REQUIRED:")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    c.drawString(
        x + 1.75 * inch, 0.85 * inch,
        "Attach manufacturer PDFs before AHJ submission. This placeholder is not a datasheet.",
    )
    c.save()
