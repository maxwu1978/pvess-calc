"""EE-5 NEC compliance checklist — PASS/FAIL per code section."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from ..calc.engine import CalculationResult
from ._textfit import fit


@dataclass
class ChecklistItem:
    nec_clause: str
    description: str
    status: Literal["PASS", "FAIL", "MANUAL", "N/A"]
    detail: str = ""


def build_checklist(result: CalculationResult) -> list[ChecklistItem]:
    """Derive PASS/FAIL per NEC clause from CalculationResult."""
    i = result.inputs
    pv = result.pv_string
    items: list[ChecklistItem] = []

    items.append(ChecklistItem(
        "690.7(A)", "Maximum PV system voltage (Voc cold)",
        "FAIL" if pv.exceeds_max_system_voltage else "PASS",
        f"{pv.string_voc_cold:.0f} V vs 600 V dwelling cap",
    ))
    items.append(ChecklistItem(
        "690.8(A)(1)", "PV source circuit current × 1.25",
        "PASS",
        f"Isc × 1.25 = {pv.isc_690_8_a:.2f} A",
    ))
    items.append(ChecklistItem(
        "690.8(B)", "PV conductor ampacity (× 1.25 × 1.25)",
        "PASS",
        f"{result.pv_conductor.size} AWG · {result.pv_conductor.ampacity_a} A",
    ))
    items.append(ChecklistItem(
        "690.9", "PV OCPD selection (≥ source × 1.25, next standard)",
        "PASS",
        f"{result.pv_ocpd_a} A",
    ))
    items.append(ChecklistItem(
        "240.4(D)", "Small-conductor rule (10/12/14 AWG OCPD cap)",
        "PASS",
        f"10 AWG OK with {result.pv_ocpd_a} A OCPD",
    ))
    items.append(ChecklistItem(
        "690.12", "Rapid Shutdown (array boundary 30V/30s)",
        "MANUAL",
        "RSD device specified — install per manufacturer",
    ))
    items.append(ChecklistItem(
        "690.11", "DC arc-fault protection",
        result.adjacent.dc_afci.status,
        f"{result.adjacent.dc_afci.inverter_model}: "
        f"{result.adjacent.dc_afci.note}",
    ))
    items.append(ChecklistItem(
        "230.67", "Dwelling service surge protection",
        "PASS" if result.adjacent.surge.service_spd_required else "N/A",
        (
            f"{result.adjacent.surge.spd_type} at "
            + ", ".join(result.adjacent.surge.required_locations)
        ) if result.adjacent.surge.service_spd_required
        else "NEC 2017: service SPD recommended, not mandated",
    ))
    items.append(ChecklistItem(
        "705.12", "Inverter interconnection method validation",
        "PASS" if result.interconnect.overall_status == "PASS" else "FAIL",
        f"Recommended: {result.interconnect.recommended or 'NONE'}",
    ))
    items.append(ChecklistItem(
        "706.7", "ESS disconnect requirement",
        "PASS",
        f"AC disconnect rated {result.ess.ac_disconnect_ocpd_a} A",
    ))
    items.append(ChecklistItem(
        "706.15", "ESS OCPD on AC side",
        "PASS",
        f"{result.ess.ac_disconnect_ocpd_a} A OCPD",
    ))
    items.append(ChecklistItem(
        "250.66", "AC GEC sizing",
        "PASS",
        f"Service {result.grounding.service_conductor_size} AWG → "
        f"GEC {result.grounding.ac_gec_size} AWG CU",
    ))
    items.append(ChecklistItem(
        "250.122", "Equipment grounding conductor sizing",
        "PASS",
        f"PV EGC #{result.grounding.egc_pv_source}, "
        f"AC trunk EGC #{result.grounding.egc_aggregate_ac}",
    ))
    items.append(ChecklistItem(
        "250.53(A)(2)", "Ground rod resistance / second electrode",
        result.adjacent.ground_rods.status,
        result.adjacent.ground_rods.note,
    ))
    items.append(ChecklistItem(
        "110.24", "Available fault current vs OCPD AIC rating",
        "PASS" if result.aic.overall_status == "PASS" else "FAIL",
        f"AFC {result.aic.available_fault_current_ka:.2f} kA vs "
        f"{result.aic.ocpd_checks[0].aic_supplied_ka:.1f} kAIC",
    ))
    items.append(ChecklistItem(
        "215.2 / 210.19", "Voltage drop end-to-end ≤ 5%",
        "PASS" if result.voltage_drop_analysis.overall_status in ("PASS", "DEFAULT")
            else "FAIL",
        f"{result.voltage_drop_analysis.total_end_to_end_pct:.2f}% total",
    ))
    items.append(ChecklistItem(
        "310.15(B)", "Temperature / conduit-fill derating applied",
        "PASS" if result.pv_derating_factor < 1.0 else "MANUAL",
        f"PV × {result.pv_derating_factor:.3f}, AC × {result.ac_derating_factor:.3f}",
    ))
    items.append(ChecklistItem(
        "Ch.9 Tbl.1", "Raceway fill within 40% limit",
        "PASS" if (
            result.adjacent.pv_conduit.fill_pct <= 100
            and result.adjacent.ac_conduit.fill_pct <= 100
        ) else "FAIL",
        f"PV {result.adjacent.pv_conduit.selected_conduit} "
        f"({result.adjacent.pv_conduit.fill_pct:.1f}%), "
        f"AC {result.adjacent.ac_conduit.selected_conduit} "
        f"({result.adjacent.ac_conduit.fill_pct:.1f}%)",
    ))
    items.append(ChecklistItem(
        "690.13(B)", "PV DC disconnect labeled per requirements",
        "MANUAL",
        "Field-applied label per labels.pdf",
    ))
    items.append(ChecklistItem(
        "690.56(C)", "Rapid Shutdown placard at service",
        "MANUAL",
        "Field-applied label per labels.pdf",
    ))
    items.append(ChecklistItem(
        "705.10", "Source identification at service",
        "MANUAL",
        "Field-applied label per labels.pdf",
    ))
    items.append(ChecklistItem(
        "110.26", "Working space ≥ 36\" in front of equipment",
        "MANUAL",
        "Verify at install — depends on site layout",
    ))

    return items


_COLORS = {
    "PASS":   colors.HexColor("#2BAA4E"),
    "FAIL":   colors.HexColor("#C00000"),
    "MANUAL": colors.HexColor("#F4A300"),
    "N/A":    colors.HexColor("#888888"),
}


def render_compliance_checklist(result: CalculationResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=landscape(letter))
    W, H = landscape(letter)
    items = build_checklist(result)

    c.setLineWidth(1.0)
    c.rect(0.4 * inch, 0.4 * inch, W - 0.8 * inch, H - 0.8 * inch)

    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(W / 2, H - 0.8 * inch, "EE-5 · NEC COMPLIANCE CHECKLIST")
    c.setFont("Helvetica", 10)
    c.drawCentredString(W / 2, H - 1.05 * inch,
                        f"NEC {result.inputs.project.nec_edition} · "
                        f"Project {result.inputs.project.id}")

    # Header
    header_y = H - 1.5 * inch
    c.setFont("Helvetica-Bold", 10)
    c.drawString(0.6 * inch, header_y, "NEC §")
    c.drawString(1.6 * inch, header_y, "Requirement")
    c.drawString(7.5 * inch, header_y, "Status")
    c.drawString(8.5 * inch, header_y, "Detail")
    c.setLineWidth(0.5)
    c.line(0.5 * inch, header_y - 0.05 * inch,
           W - 0.5 * inch, header_y - 0.05 * inch)

    # Rows
    c.setFont("Helvetica", 9)
    yy = header_y - 0.25 * inch
    for item in items:
        if yy < 0.7 * inch:
            break
        c.setFillColor(colors.black)
        c.drawString(0.6 * inch, yy, item.nec_clause)
        # Description column: 1.6" → 7.5" badge edge = 5.9" wide
        c.drawString(1.6 * inch, yy,
                     fit(item.description, "Helvetica", 9, 5.8 * inch))

        # Colored status badge
        c.setFillColor(_COLORS[item.status])
        c.rect(7.5 * inch, yy - 0.04 * inch, 0.7 * inch, 0.18 * inch, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(7.85 * inch, yy + 0.02 * inch, item.status)
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 9)
        # Detail column: 8.4" to right margin (W=11", margin 0.5") = 2.1"
        c.drawString(8.4 * inch, yy,
                     fit(item.detail, "Helvetica", 9, 2.1 * inch))
        yy -= 0.20 * inch

    # Legend
    legend_y = 0.7 * inch
    c.setFont("Helvetica-Bold", 9)
    c.drawString(0.6 * inch, legend_y, "Legend:")
    x = 1.3 * inch
    for status in ("PASS", "FAIL", "MANUAL", "N/A"):
        c.setFillColor(_COLORS[status])
        c.rect(x, legend_y - 0.04 * inch, 0.6 * inch, 0.16 * inch, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(x + 0.3 * inch, legend_y + 0.02 * inch, status)
        x += 0.8 * inch
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(W - 4.5 * inch, legend_y,
                 "MANUAL = field-verify or installer-applied label")

    c.save()
