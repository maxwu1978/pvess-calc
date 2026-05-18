"""General + Electrical Notes sheet (industry boilerplate).

Mirrors the conventions on Wyssling-style permit sets (PV-6 / PV-7) — a
single page split into two columns:
  • General Notes (contractor scope, code compliance, manufacturer specs)
  • General Electrical Notes (grounding, conductor specs, install practices)

**K.6 (C) restructuring**: notes inside each column are now sub-grouped
under topical mini-banners (e.g. "§A · Scope & Compliance", "§B ·
Grounding & Bonding"). The banner gives the reviewer a navigable
table of contents on the same page and a visual rhythm that's easier
to scan than a single long numbered list.

Notes are kept as data so AHJ profiles can swap subsets.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from ..calc.engine import CalculationResult


# Group = (banner letter, banner title, list of notes).
# Numbering RESETS at each group; reviewer references e.g. "B.3" not "11".

GENERAL_NOTE_GROUPS: list[tuple[str, str, list[str]]] = [
    ("A", "Scope & Code Compliance", [
        "Contractor shall field-verify all dimensions and review all manufacturer installation documents prior to initiating construction.",
        "Contractor shall obtain all electrical permits prior to installation and testing commissioning, and acceptance with the homeowner, utility, AHJ, and city inspector.",
        "Conforming-load voltage of the electrical components service to the connected equipment shall be within service voltage tolerance (NEC 215, 220).",
        "Service entrance equipment includes meter sockets, main service panels, and service-entrance conductors per NEC 230.",
    ]),
    ("B", "Equipment & Materials", [
        "All components shall be new and listed by a recognized testing laboratory and listed for their specific application.",
        "Equipment may be substituted for similar equipment based on availability; substituted equipment shall comply with design intent and be approved by the engineer of record.",
        "Inverter is dimensioned for code compliance per IEEE-1547 and UL-1741. Power conditioning equipment shall be installed per manufacturer requirements.",
        "Any modular fields require ground-fault protection per most recent NEC and current jurisdictional requirements.",
    ]),
    ("C", "Installation Practices", [
        "Access to electrical components over 50 V to ground shall be restricted by qualified personnel.",
        "All raceways shall be supported and securely fastened in place per NEC 300.11.",
        "All wiring must be permanently supported by direct or mechanical means designed and listed for such use; for roof-mounted systems wiring must be permanently and completely held off of the roof surface.",
        "Removal of an interior surface mounted to the wall (drywall, plaster, etc.) for the purpose of installing equipment will require finishing as required by NEC 110.16 / IRC.",
        "Required IRC fire setback at PV array exposed to system or rooftop, per current NEC, IRC, and AHJ requirements.",
        "AC disconnect shall be located on an accessible exterior wall within 10 feet of utility meter.",
    ]),
]


ELECTRICAL_NOTE_GROUPS: list[tuple[str, str, list[str]]] = [
    ("A", "Conductors, Conduit & Raceway", [
        "Conduit and bare runs shall be installed and supported in such a way that they remain visible and accessible per NEC.",
        "Conduit shall be installed to maintain a minimum clearance of 1\" from radiant heat sources.",
        "All wiring shall be sized per NEC ampacity requirements based on conductor type, ambient temperature, and conduit fill (NEC 310.15).",
        "All conductors in conduit shall be derated per NEC 310.15(B)(3)(a)(1) for more than three current-carrying conductors.",
        "Temperature correction shall be applied to all conductors exposed to ambient temperatures above 30 °C per NEC 310.15(B)(2)(a).",
        "Conductors entering or leaving boxes, enclosures, etc., shall be protected by approved bushings, fittings, or terminating in approved cable-fittings.",
        "All conduit penetrations through the roof shall be flashed and sealed per manufacturer specifications and local building code.",
    ]),
    ("B", "Grounding & Bonding", [
        "DC system grounding shall be in accordance with NEC 690.41 through 690.50.",
        "AC system grounding shall be in accordance with NEC 250.",
        "Equipment grounding conductor shall be sized per NEC 250.122 and shall be continuous between equipment.",
        "Grounding electrode conductor shall be installed per NEC 250.64 and sized per NEC 250.66.",
        "All exposed conductive metal parts shall be bonded together using equipment grounding conductors and connected to the grounding electrode system.",
    ]),
    ("C", "OCPD & Disconnects", [
        "Photovoltaic system disconnect shall be located within 10 ft of service equipment per NEC 690.13 / 705.20 and AHJ amendment, if any.",
        "Rapid shutdown initiation device shall be readily accessible and clearly labeled per NEC 690.56(C).",
        "Inverter output circuits shall be sized for 125% of continuous current and OCPD shall not be less than 125% of continuous current per NEC 705.60.",
        "If the inverter does not include integrated DC arc-fault protection, an external listed AFCI device per UL 1699B shall be added per NEC 690.11.",
        "Surge protective devices (SPDs) shall be installed at the service entrance and PV system per NEC 230.67, 690.12, and 285.",
    ]),
    ("D", "Connectors, Markings & Commissioning", [
        "Compatible-listed connectors shall be used for all PV system connections; mixed-brand connectors are prohibited.",
        "All terminations shall be made with approved listed lugs or connectors. Torque shall be set per manufacturer specifications and verified during inspection.",
        "Permanent line markers shall be installed at exterior junction points and conduits per NEC 690.31(D).",
        "The contractor shall flush conduits and pull boxes after installation to remove debris before energizing.",
        "Wiring shall comply with NEC Article 690 for PV systems including conductor sizing, OCPD ratings, and disconnecting means.",
    ]),
]


# Backwards-compat exports for any external import: flatten group list
# into the original single-list shape.
GENERAL_NOTES: list[str] = [n for _, _, notes in GENERAL_NOTE_GROUPS for n in notes]
ELECTRICAL_NOTES: list[str] = [n for _, _, notes in ELECTRICAL_NOTE_GROUPS for n in notes]


def _sheet_label(result: CalculationResult) -> str:
    code = getattr(result, "_active_sheet_display_code", "PV-N")
    title = getattr(result, "_active_sheet_title", "General & Electrical Notes")
    return f"{code} · {title.upper()}"


def render_general_notes(result: CalculationResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=landscape(letter))
    W, H = landscape(letter)

    c.setLineWidth(1.0)
    c.rect(0.4 * inch, 0.4 * inch, W - 0.8 * inch, H - 0.8 * inch)

    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(W / 2, H - 0.8 * inch, _sheet_label(result))
    c.setFont("Helvetica-Oblique", 9)
    c.drawCentredString(
        W / 2, H - 1.05 * inch,
        f"Project {result.inputs.project.id} · NEC {result.inputs.project.nec_edition}"
    )

    col_w = (W - 1.2 * inch) / 2
    left_x = 0.5 * inch
    right_x = left_x + col_w + 0.2 * inch
    top_y = H - 1.35 * inch

    _draw_grouped_column(c, left_x, top_y, col_w,
                         "GENERAL NOTES", GENERAL_NOTE_GROUPS)
    _draw_grouped_column(c, right_x, top_y, col_w,
                         "GENERAL ELECTRICAL NOTES", ELECTRICAL_NOTE_GROUPS)

    c.save()


def _draw_grouped_column(
    c, x: float, top_y: float, col_w: float,
    title: str, groups: list[tuple[str, str, list[str]]],
) -> None:
    """Render one column: blue header banner + N sub-grouped sections.

    Each sub-group gets a thin grey mini-banner with the letter + title;
    notes inside are numbered A.1, A.2, ... reset per group.
    """
    # Main column banner
    c.setFillColor(colors.HexColor("#1F5BD7"))
    c.rect(x, top_y - 0.30 * inch, col_w, 0.30 * inch, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x + 0.10 * inch, top_y - 0.22 * inch, title)
    c.setFillColor(colors.black)

    y = top_y - 0.45 * inch
    line_height = 0.115 * inch          # tighter so all 22 right-col notes fit
    floor_y = 0.55 * inch
    note_pt = 7.2

    for letter, group_title, notes in groups:
        if y < floor_y + 0.40 * inch:
            break

        # Mini-banner: thin grey strip with letter + title.
        # Banner height 0.17" + 0.07" below-gap keeps the 8pt bold
        # banner text from descender-clipping into the first-note row.
        banner_h = 0.17 * inch
        c.setFillColor(colors.HexColor("#E5E7EB"))
        c.rect(x, y - banner_h, col_w, banner_h, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#1F2937"))
        c.setFont("Helvetica-Bold", 8.0)
        c.drawString(x + 0.10 * inch, y - banner_h + 0.05 * inch,
                     f"§{letter} · {group_title}")
        c.setFillColor(colors.black)
        y -= banner_h + 0.07 * inch

        c.setFont("Helvetica", note_pt)
        for idx, note in enumerate(notes, start=1):
            if y < floor_y:
                break
            num = f"{letter}.{idx}"
            wrapped = _wrap_text(note, max_width_pt=col_w - 0.40 * inch,
                                  font_name="Helvetica", font_size=note_pt,
                                  canvas_obj=c)
            for line_idx, line in enumerate(wrapped):
                if y < floor_y:
                    break
                if line_idx == 0:
                    c.setFont("Helvetica-Bold", note_pt)
                    c.drawString(x + 0.10 * inch, y, num)
                    c.setFont("Helvetica", note_pt)
                    c.drawString(x + 0.40 * inch, y, line)
                else:
                    c.drawString(x + 0.40 * inch, y, line)
                y -= line_height
            y -= 0.015 * inch
        y -= 0.04 * inch    # extra gap between groups


def _wrap_text(text: str, max_width_pt: float, font_name: str,
               font_size: float, canvas_obj) -> list[str]:
    """Word-wrap a string at the given pixel width."""
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        trial = " ".join(current + [word])
        if canvas_obj.stringWidth(trial, font_name, font_size) <= max_width_pt:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines
