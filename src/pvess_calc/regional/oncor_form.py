"""Texas Oncor — Distributed Generation Interconnection Application cover letter.

Single-page PDF template populated from CalculationResult, used as a
supplemental form to attach to an Oncor TDU interconnection submittal.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

if TYPE_CHECKING:
    from ..calc.engine import CalculationResult


def render_oncor_cover_letter(result: "CalculationResult", out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=letter)
    W, H = letter
    i = result.inputs
    n_inv = i.inverter.count(i.battery.quantity)
    ac_kw = i.inverter.ac_output_v * i.inverter.ac_output_a * n_inv / 1000.0

    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(W / 2, H - 1.0 * inch,
                        "ONCOR ELECTRIC DELIVERY")
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(W / 2, H - 1.25 * inch,
                        "Distributed Generation Interconnection Application")
    c.setLineWidth(0.5)
    c.line(0.8 * inch, H - 1.40 * inch, W - 0.8 * inch, H - 1.40 * inch)

    def field(label: str, value: str, x: float, y: float, w: float = 3.0 * inch):
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, y, label)
        c.setFont("Helvetica", 10)
        c.drawString(x, y - 0.18 * inch, value or "—")
        c.setLineWidth(0.3)
        c.line(x, y - 0.22 * inch, x + w, y - 0.22 * inch)

    y = H - 1.9 * inch
    field("Customer Name", i.project.client_name or i.project.name,
          0.8 * inch, y)
    field("Service Address", i.project.site_address or i.project.location,
          4.2 * inch, y)
    y -= 0.55 * inch
    field("Customer Account #", "(provided by customer)", 0.8 * inch, y)
    field("Meter #", "(field-installed)", 4.2 * inch, y)
    y -= 0.55 * inch
    field("DG System AC Size (kW)", f"{ac_kw:.2f}", 0.8 * inch, y)
    field("Storage Capacity (kWh)",
          f"{i.battery.total_kwh:.1f}" if i.battery.quantity else "N/A",
          4.2 * inch, y)
    y -= 0.55 * inch
    field("Inverter Manufacturer",
          f"{i.inverter.brand} {i.inverter.model}", 0.8 * inch, y)
    field("Inverter Quantity", str(n_inv), 4.2 * inch, y)
    y -= 0.55 * inch
    field("Interconnection Method",
          result.interconnect.recommended or "FAIL", 0.8 * inch, y)
    field("NEC Edition", i.project.nec_edition, 4.2 * inch, y)

    # Designer signature block
    y = 3.0 * inch
    c.setFont("Helvetica-Bold", 10)
    c.drawString(0.8 * inch, y, "Design Engineer Attestation")
    c.setLineWidth(0.3)
    c.line(0.8 * inch, y - 0.05 * inch, W - 0.8 * inch, y - 0.05 * inch)

    c.setFont("Helvetica", 9.5)
    c.drawString(0.8 * inch, y - 0.30 * inch,
                 f"I, the undersigned engineer of record, certify that the proposed")
    c.drawString(0.8 * inch, y - 0.46 * inch,
                 f"distributed generation system complies with NEC {i.project.nec_edition}, "
                 f"IEEE 1547, and applicable Oncor TDU technical requirements.")

    y -= 1.10 * inch
    field("Engineer Name / PE #",
          f"{i.design_engineer.firm} · {i.design_engineer.firm_number}",
          0.8 * inch, y, 3.5 * inch)
    field("Date", date.today().isoformat(), 4.8 * inch, y, 2.5 * inch)

    y -= 0.55 * inch
    c.setFont("Helvetica-Bold", 9)
    c.drawString(0.8 * inch, y, "Signature")
    c.line(0.8 * inch, y - 0.50 * inch, 5.0 * inch, y - 0.50 * inch)

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(0.8 * inch, 0.5 * inch,
                 "Submit alongside Oncor DG-001 form and one-line diagram. "
                 "Do not energize until permission-to-operate (PTO) is granted.")
    c.save()
