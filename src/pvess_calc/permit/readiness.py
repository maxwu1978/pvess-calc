"""Reference-planset data readiness assessment.

This is intentionally separate from renderers: the permit package should keep
rendering with placeholders, while doctor reports whether the source data is
real enough for AHJ submission or still simulated/missing.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Literal

import yaml

from ..calc.engine import CalculationResult


ReadinessStatus = Literal["ready", "simulated", "missing", "not_applicable"]


_PLACEHOLDER_RE = re.compile(
    r"(?:\bTODO\b|\bTBD\b|PLACEHOLDER|\bmock\b|simulated|sample|example|"
    r"dummy|internal review|555-0100)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ReadinessItem:
    key: str
    status: ReadinessStatus
    detail: str


@dataclass(frozen=True)
class SimulatedSource:
    key: str
    status: ReadinessStatus
    source: str = ""
    replacement: str = ""
    files: tuple[str, ...] = ()


@dataclass(frozen=True)
class SimulatedSiteDataPack:
    path: Path
    name: str
    updated: str
    purpose: str
    sources: dict[str, SimulatedSource]


@dataclass(frozen=True)
class ReferenceReadiness:
    items: tuple[ReadinessItem, ...]
    source_pack: SimulatedSiteDataPack | None = None

    @property
    def counts(self) -> Counter[str]:
        return Counter(item.status for item in self.items)

    @property
    def needs_review(self) -> bool:
        return any(
            item.status in {"simulated", "missing"} for item in self.items
        )

    def doctor_detail(self, limit: int = 8) -> str:
        counts = self.counts
        prefix = (
            f"{counts['ready']} ready, {counts['simulated']} simulated, "
            f"{counts['missing']} missing, "
            f"{counts['not_applicable']} not applicable"
        )
        if self.source_pack:
            prefix += (
                f"; pack {self.source_pack.path.name}: "
                f"{len(self.source_pack.sources)} source item(s)"
            )
        review_items = [
            item for item in self.items
            if item.status in {"missing", "simulated"}
        ]
        if not review_items:
            return prefix
        details = "; ".join(
            f"{item.key}: {_doctor_detail_fragment(item.detail)}"
            for item in review_items[:limit]
        )
        if len(review_items) > limit:
            details += f"; +{len(review_items) - limit} more"
        return f"{prefix}; review: {details}"


def assess_reference_profile_readiness(
    result: CalculationResult,
    project_dir: Path | None = None,
) -> ReferenceReadiness:
    """Classify permit-package source data as ready/simulated/missing.

    The classification is deliberately conservative. Existing placeholder
    renderers already keep package generation unblocked; this layer keeps
    simulated data from being mistaken for submission-ready field data.
    """
    i = result.inputs
    project_dir = project_dir or Path.cwd() / "projects" / i.project.id
    raw_yaml = _read_raw_yaml(project_dir)
    source_pack = load_simulated_site_data_pack(project_dir)
    items: list[ReadinessItem] = []

    def add(
        key: str,
        value: object,
        *,
        missing_detail: str = "missing",
        ready_detail: str = "present",
        simulated_detail: str = "placeholder/simulated value",
    ) -> None:
        items.append(_classify_value(
            key,
            value,
            missing_detail=missing_detail,
            ready_detail=ready_detail,
            simulated_detail=simulated_detail,
        ))

    add("project.site_address", i.project.site_address)
    add("project.coordinates", i.project.coordinates)
    add("project.apn", i.project.apn,
        missing_detail="assessor parcel number missing")
    add("project.utility", i.project.utility)
    add("project.meter_info.number", i.project.meter_info.number)
    add("project.meter_info.location", i.project.meter_info.location)
    if "TX" in (i.project.site_address or i.project.location).upper():
        add("project.meter_info.esid", i.project.meter_info.esid,
            missing_detail="Texas ESID missing")

    engineer_fields = [
        i.design_engineer.firm,
        i.design_engineer.firm_number,
        i.design_engineer.contact_email,
        i.design_engineer.contact_phone,
    ]
    items.append(_classify_group(
        "design_engineer",
        engineer_fields,
        missing_detail="engineer of record metadata missing",
        ready_detail="engineer of record metadata present",
        simulated_detail="engineer metadata is placeholder/internal",
    ))

    installer_fields = [i.installer.company, i.installer.address]
    items.append(_classify_group(
        "installer",
        installer_fields,
        missing_detail="installer company/address missing",
        ready_detail="installer company/address present",
        simulated_detail="installer identity is TBD/placeholder",
    ))

    ri = i.project.roof_info
    roof_fields = [
        ri.type,
        ri.height_ft,
        ri.construction or ri.framing,
        ri.condition,
        ri.attic_access,
        ri.decking_thickness_in,
        ri.roof_layers,
    ]
    items.append(_classify_group(
        "project.roof_info",
        roof_fields,
        missing_detail="roof survey fields incomplete",
        ready_detail="roof type/framing/decking/attic data present",
        simulated_detail="roof survey fields contain placeholder values",
    ))

    structural = _resolve(project_dir, i.project.structural_letter_pdf)
    if structural and structural.exists():
        items.append(ReadinessItem(
            "project.structural_letter_pdf",
            _path_status(structural),
            "signed structural packet present",
        ))
    else:
        items.append(ReadinessItem(
            "project.structural_letter_pdf",
            "missing",
            "signed structural letter missing; draft page will be prepended",
        ))

    items.append(_photo_readiness(result, project_dir))
    items.append(_spec_sheet_readiness(result, project_dir))

    if len(i.loads.monthly_kwh) == 12:
        status: ReadinessStatus = "simulated" if _raw_context_has(
            raw_yaml, "monthly_kwh", ("placeholder", "simulated", "mock")
        ) else "ready"
        detail = (
            "12-month usage exists but YAML marks it as placeholder"
            if status == "simulated"
            else "12-month usage present"
        )
        items.append(ReadinessItem("loads.monthly_kwh", status, detail))
    else:
        items.append(ReadinessItem(
            "loads.monthly_kwh",
            "missing",
            "12-month utility usage missing",
        ))

    if i.site.roof_sections:
        status = "simulated" if _raw_context_has(
            raw_yaml, "roof_sections:", ("google solar", "yaml-pinned")
        ) else "ready"
        detail = (
            f"{len(i.site.roof_sections)} roof face(s) modeled; "
            "field/EagleView verification required"
            if status == "simulated"
            else f"{len(i.site.roof_sections)} roof face(s) present"
        )
        items.append(ReadinessItem("site.roof_sections", status, detail))
    else:
        items.append(ReadinessItem(
            "site.roof_sections", "missing", "roof face geometry missing"
        ))

    if i.site.ee4_trace.enabled and i.site.property_context.has_data:
        items.append(ReadinessItem(
            "site.plan_geometry",
            "simulated",
            "trace/property context is modeled from reference imagery",
        ))
    else:
        items.append(ReadinessItem(
            "site.plan_geometry",
            "missing",
            "EE-4 trace or property context missing",
        ))

    if i.site.equipment_locations.has_data:
        items.append(ReadinessItem(
            "site.equipment_locations",
            "ready",
            "MSP/inverter/equipment coordinates present",
        ))
    else:
        items.append(ReadinessItem(
            "site.equipment_locations",
            "missing",
            "equipment coordinates missing; wire routing falls back",
        ))

    if i.battery.installed:
        add("battery.install_location", i.battery.install_location,
            missing_detail="ESS install location missing")
    else:
        items.append(ReadinessItem(
            "battery.install_location",
            "not_applicable",
            "PV-only project; no ESS install data required",
        ))

    if source_pack:
        items = _apply_source_pack(items, source_pack)

    return ReferenceReadiness(tuple(items), source_pack=source_pack)


def format_reference_readiness_markdown(readiness: ReferenceReadiness) -> str:
    """Human-readable readiness report for output/reference-readiness.md."""
    lines = [
        "# Reference Package Data Readiness",
        "",
        readiness.doctor_detail(limit=100),
        "",
    ]
    if readiness.source_pack:
        pack = readiness.source_pack
        lines.extend([
            "## Simulated Site Data Pack",
            "",
            f"- File: `{pack.path.name}`",
            f"- Name: {pack.name or '-'}",
            f"- Updated: {pack.updated or '-'}",
            f"- Purpose: {pack.purpose or '-'}",
            "",
            "| Key | Status | Source | Replacement Standard | Files |",
            "|---|---|---|---|---|",
        ])
        for source in pack.sources.values():
            files = ", ".join(f"`{f}`" for f in source.files) or "-"
            lines.append(
                f"| `{source.key}` | {source.status} | "
                f"{source.source or '-'} | "
                f"{source.replacement or '-'} | {files} |"
            )
        lines.append("")

    lines.extend([
        "| Key | Status | Detail |",
        "|---|---|---|",
    ])
    for item in readiness.items:
        lines.append(f"| `{item.key}` | {item.status} | {item.detail} |")
    lines.append("")
    return "\n".join(lines)


def format_real_data_checklist_markdown(readiness: ReferenceReadiness) -> str:
    """Operator-facing checklist to clear `pvess readiness --strict`."""
    review_items = [
        item for item in readiness.items
        if item.status in {"simulated", "missing"}
    ]
    lines = [
        "# Real-Data Replacement Checklist",
        "",
        "Use this checklist to replace simulated or missing source data before "
        "running `pvess readiness --strict` for an AHJ-ready gate.",
        "",
        readiness.doctor_detail(limit=100),
        "",
    ]
    if not review_items:
        lines.extend([
            "All applicable readiness items are real and present.",
            "",
        ])
        return "\n".join(lines)

    lines.extend([
        "| Done | Key | Current Status | Required Real-Data Replacement | Current Source / Files |",
        "|---|---|---|---|---|",
    ])
    for item in review_items:
        source = _source_for_item(readiness, item.key)
        replacement = _replacement_for_item(item, source)
        current = _current_source_for_item(item, source)
        lines.append(
            f"| [ ] | `{item.key}` | {item.status} | "
            f"{replacement} | {current} |"
        )
    lines.extend([
        "",
        "Closeout rule: every row above must be replaced with real project "
        "evidence, then rerun `pvess readiness --strict <project-dir>`.",
        "",
    ])
    return "\n".join(lines)


def render_readiness_appendix(
    result: CalculationResult,
    out_path: Path,
    *,
    project_dir: Path | None = None,
) -> int:
    """Render an internal-review PDF appendix for source-data readiness.

    This appendix is deliberately outside the Sheet Registry. It is not an
    AHJ submittal sheet and should only be appended when explicitly requested.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    readiness = assess_reference_profile_readiness(result, project_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=landscape(letter),
        leftMargin=0.45 * inch,
        rightMargin=0.45 * inch,
        topMargin=0.42 * inch,
        bottomMargin=0.42 * inch,
        title="Internal Data Readiness Appendix",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "ReadinessTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=20,
        alignment=1,
        spaceAfter=6,
    )
    warning = ParagraphStyle(
        "ReadinessWarning",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#B45309"),
        spaceAfter=8,
    )
    body = ParagraphStyle(
        "ReadinessBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.4,
        leading=9,
    )
    body_bold = ParagraphStyle(
        "ReadinessBodyBold",
        parent=body,
        fontName="Helvetica-Bold",
    )

    story: list = [
        Paragraph("DATA READINESS APPENDIX", title),
        Paragraph(
            "INTERNAL REVIEW ONLY - NOT FOR AHJ SUBMISSION UNLESS "
            "EXPLICITLY APPROVED.",
            warning,
        ),
        Paragraph(readiness.doctor_detail(limit=100), body),
        Spacer(1, 0.10 * inch),
    ]

    if readiness.source_pack:
        pack = readiness.source_pack
        story.extend([
            Paragraph("SIMULATED SITE DATA PACK", body_bold),
            _table(
                [
                    ["File", pack.path.name],
                    ["Name", pack.name or "-"],
                    ["Updated", pack.updated or "-"],
                    ["Purpose", pack.purpose or "-"],
                ],
                col_widths=[1.2 * inch, 8.75 * inch],
                body_style=body,
                repeat_header=False,
            ),
            Spacer(1, 0.10 * inch),
        ])
        source_rows = [["Key", "Status", "Source", "Replacement Standard"]]
        for source in pack.sources.values():
            source_rows.append([
                source.key,
                source.status,
                source.source or "-",
                source.replacement or "-",
            ])
        story.extend([
            _table(
                source_rows,
                col_widths=[1.75 * inch, 0.72 * inch, 3.15 * inch, 4.33 * inch],
                body_style=body,
                repeat_header=True,
            ),
            PageBreak(),
        ])

    readiness_rows = [["Key", "Status", "Detail"]]
    for item in readiness.items:
        readiness_rows.append([item.key, item.status, item.detail])
    story.extend([
        Paragraph("READINESS ITEMS", body_bold),
        _table(
            readiness_rows,
            col_widths=[2.05 * inch, 0.82 * inch, 7.08 * inch],
            body_style=body,
            repeat_header=True,
        ),
    ])

    doc.build(story)
    from pypdf import PdfReader
    return len(PdfReader(str(out_path)).pages)


def _table(
    rows: list[list[str]],
    *,
    col_widths: list[float],
    body_style,
    repeat_header: bool,
) -> "Table":
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Table, TableStyle

    def cell(value: str):
        return Paragraph(str(value), body_style)

    data = [[cell(value) for value in row] for row in rows]
    table = Table(
        data,
        colWidths=col_widths,
        repeatRows=1 if repeat_header else 0,
        splitByRow=True,
    )
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#9CA3AF")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def load_simulated_site_data_pack(
    project_dir: Path,
) -> SimulatedSiteDataPack | None:
    """Load optional project-level simulated-data source metadata.

    The file is intentionally outside inputs.yaml because it is about source
    provenance, not electrical design. Keeping it separate lets demo fixtures
    mark data as simulated without teaching the calculation schema new fields.
    """
    for filename in ("simulated-site-data.yaml", "simulated_site_data.yaml"):
        path = project_dir / filename
        if path.exists():
            break
    else:
        return None

    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    raw_sources = data.get("sources", {})
    if isinstance(raw_sources, list):
        source_items = {
            str(item.get("key", "")): item
            for item in raw_sources
            if isinstance(item, dict) and item.get("key")
        }
    elif isinstance(raw_sources, dict):
        source_items = raw_sources
    else:
        source_items = {}

    sources: dict[str, SimulatedSource] = {}
    for key, raw in source_items.items():
        if not isinstance(raw, dict):
            continue
        key_str = str(raw.get("key") or key)
        files_raw = raw.get("files", ())
        files = (
            tuple(str(f) for f in files_raw)
            if isinstance(files_raw, list)
            else ()
        )
        sources[key_str] = SimulatedSource(
            key=key_str,
            status=_source_status(raw.get("status", "simulated")),
            source=str(raw.get("source", "")),
            replacement=str(raw.get("replacement", "")),
            files=files,
        )

    return SimulatedSiteDataPack(
        path=path,
        name=str(data.get("name", "")),
        updated=str(data.get("updated", "")),
        purpose=str(data.get("purpose", "")),
        sources=sources,
    )


def _apply_source_pack(
    items: list[ReadinessItem],
    pack: SimulatedSiteDataPack,
) -> list[ReadinessItem]:
    enriched: list[ReadinessItem] = []
    for item in items:
        source = pack.sources.get(item.key)
        if source is None:
            enriched.append(item)
            continue

        status = item.status
        if source.status == "missing":
            status = "missing"
        elif source.status == "simulated" and item.status != "missing":
            status = "simulated"
        elif source.status == "not_applicable":
            status = "not_applicable"

        detail_parts = [item.detail]
        if source.source:
            detail_parts.append(f"source pack: {source.source}")
        if source.replacement:
            detail_parts.append(f"replace with {source.replacement}")
        enriched.append(ReadinessItem(
            item.key,
            status,
            "; ".join(part for part in detail_parts if part),
        ))
    return enriched


def _source_status(raw: object) -> ReadinessStatus:
    value = str(raw).strip().lower()
    if value in {"ready", "simulated", "missing", "not_applicable"}:
        return value  # type: ignore[return-value]
    return "simulated"


def _doctor_detail_fragment(detail: str) -> str:
    """Keep doctor output terse; Markdown report carries full provenance."""
    return detail.split("; source pack:", 1)[0]


def _source_for_item(
    readiness: ReferenceReadiness,
    key: str,
) -> SimulatedSource | None:
    if readiness.source_pack is None:
        return None
    return readiness.source_pack.sources.get(key)


def _replacement_for_item(
    item: ReadinessItem,
    source: SimulatedSource | None,
) -> str:
    if source and source.replacement:
        return source.replacement
    defaults = {
        "project.apn": "assessor parcel/APN record",
        "project.structural_letter_pdf": "signed/sealed structural letter PDF",
        "project.site_photos": "actual site-survey photos",
        "loads.monthly_kwh": "12-month utility usage export or bills",
        "site.roof_sections": "field-verified roof measurements/report",
        "site.plan_geometry": "field/survey/GIS verified site geometry",
        "design_engineer": "engineer-of-record metadata",
        "installer": "contracted installer metadata",
    }
    return defaults.get(item.key, "real project evidence")


def _current_source_for_item(
    item: ReadinessItem,
    source: SimulatedSource | None,
) -> str:
    parts: list[str] = []
    if source and source.source:
        parts.append(source.source)
    if source and source.files:
        parts.append(", ".join(f"`{f}`" for f in source.files))
    if not parts:
        parts.append(_doctor_detail_fragment(item.detail))
    return "<br/>".join(parts)


def _classify_value(
    key: str,
    value: object,
    *,
    missing_detail: str,
    ready_detail: str,
    simulated_detail: str,
) -> ReadinessItem:
    if _is_missing(value):
        return ReadinessItem(key, "missing", missing_detail)
    if _is_placeholder(value):
        return ReadinessItem(key, "simulated", simulated_detail)
    return ReadinessItem(key, "ready", ready_detail)


def _classify_group(
    key: str,
    values: list[object],
    *,
    missing_detail: str,
    ready_detail: str,
    simulated_detail: str,
) -> ReadinessItem:
    if any(_is_missing(v) for v in values):
        return ReadinessItem(key, "missing", missing_detail)
    if any(_is_placeholder(v) for v in values):
        return ReadinessItem(key, "simulated", simulated_detail)
    return ReadinessItem(key, "ready", ready_detail)


def _photo_readiness(
    result: CalculationResult,
    project_dir: Path,
) -> ReadinessItem:
    from .site_photos import REQUIRED_PHOTOS

    required = {kind for kind, _label in REQUIRED_PHOTOS}
    supplied = {p.kind: p for p in result.inputs.project.site_photos}
    missing: list[str] = []
    simulated: list[str] = []
    for kind in sorted(required):
        photo = supplied.get(kind)
        path = _resolve(project_dir, photo.path if photo else "")
        if not path or not path.exists():
            missing.append(kind)
        elif _path_status(path) == "simulated":
            simulated.append(kind)
    if missing:
        return ReadinessItem(
            "project.site_photos",
            "missing",
            "missing PV-7 photo(s): " + ", ".join(missing),
        )
    if simulated:
        return ReadinessItem(
            "project.site_photos",
            "simulated",
            "mock PV-7 photo(s): " + ", ".join(simulated),
        )
    return ReadinessItem(
        "project.site_photos",
        "ready",
        f"{len(required)} required PV-7 photos present",
    )


def _spec_sheet_readiness(
    result: CalculationResult,
    project_dir: Path,
) -> ReadinessItem:
    specs = []
    for ref in result.inputs.project.spec_sheets:
        path = _resolve(project_dir, ref.path)
        if path and path.exists():
            specs.append(ref)
    cut_sheets_dir = project_dir / "cut_sheets"
    cut_sheets = list(cut_sheets_dir.glob("*.pdf")) if cut_sheets_dir.exists() else []
    if not specs and not cut_sheets:
        return ReadinessItem(
            "project.spec_sheets",
            "missing",
            "manufacturer PDFs missing",
        )
    simulated = [
        Path(ref.path).name for ref in specs
        if _path_status(Path(ref.path)) == "simulated"
    ]
    if simulated:
        return ReadinessItem(
            "project.spec_sheets",
            "simulated",
            "placeholder/mock spec path(s): " + ", ".join(simulated),
        )
    return ReadinessItem(
        "project.spec_sheets",
        "ready",
        f"{len(specs) or len(cut_sheets)} manufacturer PDF(s) present",
    )


def _path_status(path: Path) -> ReadinessStatus:
    return "simulated" if _is_placeholder(path.as_posix()) else "ready"


def _resolve(project_dir: Path, raw: str) -> Path | None:
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = project_dir / path
    return path


def _is_missing(value: object) -> bool:
    if value in (None, "", 0, 0.0):
        return True
    if isinstance(value, str) and value.strip().lower() in {"", "-", "unknown"}:
        return True
    return False


def _is_placeholder(value: object) -> bool:
    return bool(_PLACEHOLDER_RE.search(str(value)))


def _read_raw_yaml(project_dir: Path) -> str:
    try:
        return (project_dir / "inputs.yaml").read_text(encoding="utf-8")
    except OSError:
        return ""


def _raw_context_has(
    raw_yaml: str,
    anchor: str,
    terms: tuple[str, ...],
    window: int = 360,
) -> bool:
    if not raw_yaml:
        return False
    idx = raw_yaml.lower().find(anchor.lower())
    if idx < 0:
        return False
    snippet = raw_yaml[max(0, idx - window): idx + window].lower()
    return any(term.lower() in snippet for term in terms)
