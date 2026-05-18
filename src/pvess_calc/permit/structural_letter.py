"""Unsigned structural-letter draft for reference-style packages."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from ..calc.engine import CalculationResult


def render_structural_letter_draft(
    result: CalculationResult, out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=letter)
    W, H = letter
    i = result.inputs
    ri = i.project.roof_info

    _watermark(c, W, H)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(0.75 * inch, H - 0.75 * inch, "STRUCTURAL REVIEW DRAFT")
    c.setFont("Helvetica", 9)
    c.drawString(0.75 * inch, H - 1.05 * inch,
                 "This draft is generated for engineer review only. It is not signed or sealed.")

    y = H - 1.55 * inch
    c.setFont("Helvetica", 10)
    lines = [
        f"Project: {i.project.client_name or i.project.name}",
        f"Address: {i.project.site_address or i.project.location}",
        f"System size: {i.pv_array.modules * i.pv_array.module.power_w / 1000:.3f} kW DC",
        "",
        "A. Site Assessment Information",
        "1. Site documentation and roof/framing information shall be verified by the engineer of record.",
        "2. Design drawings include site plan, roof plan, attachment plan, and electrical diagrams.",
        "",
        "B. Description of Structure",
        f"Roof framing: {ri.framing or ri.construction or 'FIELD VERIFY'}",
        f"Roof material: {ri.type or 'FIELD VERIFY'}",
        f"Roof slope: {', '.join(_unique_pitches(result)) or 'FIELD VERIFY'}",
        f"Attic access: {ri.attic_access}",
        f"Decking thickness: {_decking(ri.decking_thickness_in)}",
        "",
        "C. Loading Criteria Used",
        f"Ground snow load: {i.project.design_criteria.ground_snow_load_psf} psf",
        f"Wind speed: {i.project.design_criteria.wind_speed_mph} mph, Exposure {i.project.design_criteria.exposure_category}",
        "Dead load assumption: existing roof + PV/racking to be confirmed by structural engineer.",
    ]
    y = _draw_lines(c, lines, 0.75 * inch, y)

    c.setFont("Helvetica-Bold", 9)
    c.drawString(0.75 * inch, y - 0.20 * inch, "ENGINEER ACTION REQUIRED:")
    c.setFont("Helvetica", 9)
    c.drawString(
        2.75 * inch, y - 0.20 * inch,
        "Replace this draft with a signed structural letter before AHJ submission.",
    )
    c.showPage()

    _watermark(c, W, H)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(0.75 * inch, H - 0.75 * inch, "STRUCTURAL REVIEW DRAFT - ANCHORAGE")
    y = H - 1.25 * inch
    rows = [
        ("Total modules", str(i.pv_array.modules)),
        ("Total attachments", str(_total_attachments(result))),
        ("Max spacing", f"{i.site.mounting.max_x_spacing_in:.0f} in O.C."),
        ("Max cantilever", f"{i.site.mounting.max_cantilever_in:.0f} in"),
        ("Fastener", i.site.mounting.fastener or "FIELD VERIFY"),
        ("Min embedment", f"{i.site.mounting.min_embedment_in:g} in"),
        ("Mounting", i.site.mounting.rail_system or "FIELD VERIFY"),
        ("Flashing", i.site.mounting.flashing or ri.flashing or "FIELD VERIFY"),
    ]
    c.setFont("Helvetica", 9)
    for label, value in rows:
        c.setFont("Helvetica-Bold", 9)
        c.drawString(0.9 * inch, y, label + ":")
        c.setFont("Helvetica", 9)
        c.drawString(2.45 * inch, y, value)
        y -= 0.24 * inch

    c.setFont("Helvetica", 9)
    c.drawString(
        0.9 * inch, y - 0.20 * inch,
        "Installer shall notify the engineer if roof framing appears unstable, damaged, or non-uniform.",
    )
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#B91C1C"))
    c.drawCentredString(W / 2, 0.75 * inch, "UNSIGNED DRAFT - NOT FOR PERMIT SUBMISSION")
    c.save()


def _watermark(c, W: float, H: float) -> None:
    c.saveState()
    c.setFillColor(colors.Color(0.9, 0.9, 0.9, alpha=0.45))
    c.setFont("Helvetica-Bold", 54)
    c.translate(W / 2, H / 2)
    c.rotate(35)
    c.drawCentredString(0, 0, "DRAFT")
    c.restoreState()
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.8)
    c.rect(0.5 * inch, 0.5 * inch, W - inch, H - inch)


def _draw_lines(c, lines: list[str], x: float, y: float) -> float:
    for line in lines:
        if line.startswith(("A.", "B.", "C.")):
            c.setFont("Helvetica-Bold", 10)
        else:
            c.setFont("Helvetica", 9)
        c.drawString(x, y, line)
        y -= 0.20 * inch if line else 0.13 * inch
    return y


def _unique_pitches(result: CalculationResult) -> list[str]:
    vals: list[str] = []
    for section in result.inputs.site.roof_sections:
        pitch = f"{section.pitch_deg:.0f} deg"
        if pitch not in vals:
            vals.append(pitch)
    return vals


def _decking(value: float) -> str:
    return f"{value:.2f} in" if value > 0 else "FIELD VERIFY"


def _total_attachments(result: CalculationResult) -> int:
    total = sum(s.attachment_count for s in result.inputs.site.roof_sections)
    if total:
        return total
    return max(0, result.inputs.pv_array.modules * 3)
