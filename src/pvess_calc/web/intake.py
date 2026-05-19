"""Source-material intake helpers for the Web generator."""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SITE_PHOTO_KINDS = {
    "front_elevation",
    "roof",
    "meter",
    "main_panel",
    "sub_panel",
    "attic",
    "equipment_location",
    "other",
}

SPEC_EQUIPMENT = {"module", "inverter", "optimizer", "battery", "racking", "other"}

MONTH_NAMES = (
    "jan", "january", "feb", "february", "mar", "march", "apr", "april",
    "may", "jun", "june", "jul", "july", "aug", "august", "sep",
    "sept", "september", "oct", "october", "nov", "november", "dec",
    "december",
)


@dataclass(frozen=True)
class UtilityParseResult:
    status: str
    monthly_kwh: tuple[float, ...] = ()
    confidence: str = "miss"
    message: str = ""
    source: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "monthly_kwh": list(self.monthly_kwh),
            "confidence": self.confidence,
            "message": self.message,
            "source": self.source,
        }


def parse_utility_usage(
    *,
    filename: str,
    content_type: str,
    content: bytes,
) -> UtilityParseResult:
    """Extract 12 monthly kWh values from common CSV/text/PDF uploads.

    This intentionally stays conservative: it only returns parsed values when
    it finds exactly 12 plausible monthly energy readings from a kWh column,
    month-labeled rows, or a simple 12-number export.
    """
    text = _decode_text(content)
    source = Path(filename or "utility-upload").name
    if not text.strip():
        return UtilityParseResult(
            status="unparsed",
            confidence="miss",
            message="No readable text found in utility upload.",
            source=source,
        )

    from_table = _monthly_from_csv(text)
    if _valid_monthly(from_table):
        return UtilityParseResult(
            status="parsed",
            monthly_kwh=tuple(from_table),
            confidence="high",
            message="Parsed 12 monthly kWh values from utility CSV columns.",
            source=source,
        )

    from_month_lines = _monthly_from_month_lines(text)
    if _valid_monthly(from_month_lines):
        return UtilityParseResult(
            status="parsed",
            monthly_kwh=tuple(from_month_lines),
            confidence="medium",
            message="Parsed 12 month-labeled kWh values from utility text.",
            source=source,
        )

    # Last fallback for Smart Meter exports pasted or saved as a plain CSV with
    # one row of 12 monthly values.  The plausibility filter avoids accepting
    # account numbers, dates, or meter identifiers as energy readings.
    numbers = [
        _parse_number(match.group(0))
        for match in re.finditer(r"(?<![\w.-])\d[\d,]*(?:\.\d+)?(?![\w.-])", text)
    ]
    plausible = [value for value in numbers if 50 <= value <= 5000]
    if len(plausible) == 12:
        return UtilityParseResult(
            status="parsed",
            monthly_kwh=tuple(plausible),
            confidence="low",
            message="Parsed 12 plausible kWh values from utility upload.",
            source=source,
        )

    return UtilityParseResult(
        status="unparsed",
        confidence="miss",
        message="Could not find 12 valid monthly kWh values.",
        source=source,
    )


def classify_site_photo(
    *,
    filename: str,
    provided_kind: str = "other",
) -> dict[str, Any]:
    text = _tokens(filename)
    guesses: list[tuple[str, set[str]]] = [
        ("front_elevation", {"front", "elevation", "street", "facade"}),
        ("roof", {"roof", "array", "shingle", "aerial"}),
        ("meter", {"meter", "esid"}),
        ("main_panel", {"main", "msp", "service", "panelboard"}),
        ("sub_panel", {"sub", "subpanel", "loadcenter", "load"}),
        ("attic", {"attic", "rafter", "truss", "framing"}),
        ("equipment_location", {"equipment", "inverter", "battery", "ess", "wall"}),
    ]
    for kind, keywords in guesses:
        if text & keywords:
            return {
                "filename": Path(filename or "").name,
                "provided_kind": provided_kind,
                "classified_kind": kind,
                "confidence": "high" if provided_kind in {"other", kind} else "medium",
                "review_required": provided_kind not in {"other", kind},
                "reason": f"filename matched {kind.replace('_', ' ')} keywords",
            }
    fallback = provided_kind if provided_kind in SITE_PHOTO_KINDS else "other"
    return {
        "filename": Path(filename or "").name,
        "provided_kind": provided_kind,
        "classified_kind": fallback,
        "confidence": "field" if fallback != "other" else "miss",
        "review_required": fallback == "other",
        "reason": (
            "field input supplied the photo kind"
            if fallback != "other" else "no filename keyword matched a required PV-7 kind"
        ),
    }


def classify_spec_sheet(
    *,
    filename: str,
    provided_equipment: str = "other",
) -> dict[str, Any]:
    text = _tokens(filename)
    guesses: list[tuple[str, set[str]]] = [
        ("module", {"module", "pv", "panel", "talesun", "rec", "canadian"}),
        ("inverter", {"inverter", "growatt", "hoymile", "hoymiles", "megarevo", "megarova"}),
        ("battery", {"battery", "ess", "powerwall", "apx", "eg4", "franklin"}),
        ("racking", {"racking", "rail", "ironridge", "flashfoot", "mount"}),
        ("optimizer", {"optimizer", "tigo", "rapid", "rsd"}),
    ]
    for equipment, keywords in guesses:
        if text & keywords:
            return {
                "filename": Path(filename or "").name,
                "provided_equipment": provided_equipment,
                "classified_equipment": equipment,
                "confidence": "high" if provided_equipment in {"other", equipment} else "medium",
                "review_required": provided_equipment not in {"other", equipment},
                "reason": f"filename matched {equipment} spec keywords",
            }
    fallback = provided_equipment if provided_equipment in SPEC_EQUIPMENT else "other"
    return {
        "filename": Path(filename or "").name,
        "provided_equipment": provided_equipment,
        "classified_equipment": fallback,
        "confidence": "field" if fallback != "other" else "miss",
        "review_required": fallback == "other",
        "reason": (
            "field input supplied the equipment kind"
            if fallback != "other" else "no filename keyword matched a spec category"
        ),
    }


def required_spec_equipment(*, battery_installed: bool) -> list[str]:
    required = ["module", "inverter", "optimizer", "racking"]
    if battery_installed:
        required.append("battery")
    return required


def spec_sheet_coverage(
    *,
    present_equipment: set[str],
    battery_installed: bool,
) -> dict[str, Any]:
    required = required_spec_equipment(battery_installed=battery_installed)
    items = [
        {
            "equipment": equipment,
            "required": True,
            "status": "ready" if equipment in present_equipment else "missing",
        }
        for equipment in required
    ]
    optional = sorted((present_equipment - set(required)) - {"other"})
    items.extend(
        {
            "equipment": equipment,
            "required": False,
            "status": "ready",
        }
        for equipment in optional
    )
    return {
        "required": required,
        "present": sorted(present_equipment - {"other"}),
        "missing": [item["equipment"] for item in items if item["status"] == "missing"],
        "items": items,
    }


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("latin-1", errors="ignore")


def _monthly_from_csv(text: str) -> list[float]:
    try:
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        dialect = csv.excel

    rows = list(csv.reader(io.StringIO(text), dialect))
    if not rows:
        return []

    header = [cell.strip().lower() for cell in rows[0]]
    kwh_idx = next(
        (
            idx for idx, name in enumerate(header)
            if "kwh" in name or "usage" in name or "consumption" in name
        ),
        None,
    )
    if kwh_idx is not None:
        values: list[float] = []
        for row in rows[1:]:
            if kwh_idx >= len(row):
                continue
            value = _parse_number(row[kwh_idx])
            if value > 0:
                values.append(value)
        if len(values) >= 12:
            return values[:12]

    # Headerless 12-row exports often have month/date in the first column and
    # kWh in the second.  Use the last plausible value per row.
    values = []
    for row in rows:
        plausible = [
            _parse_number(cell)
            for cell in row
            if 50 <= _parse_number(cell) <= 5000
        ]
        if plausible:
            values.append(plausible[-1])
    return values[:12] if len(values) >= 12 else []


def _monthly_from_month_lines(text: str) -> list[float]:
    values: list[float] = []
    month_re = "|".join(re.escape(month) for month in MONTH_NAMES)
    pattern = re.compile(
        rf"\b(?:{month_re})\b[^\n\r\d]{{0,32}}([0-9][0-9,]*(?:\.\d+)?)",
        re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        value = _parse_number(match.group(1))
        if 50 <= value <= 5000:
            values.append(value)
    return values[:12] if len(values) >= 12 else []


def _valid_monthly(values: list[float]) -> bool:
    return len(values) == 12 and all(50 <= value <= 5000 for value in values)


def _parse_number(raw: Any) -> float:
    try:
        return float(str(raw).replace(",", "").strip())
    except ValueError:
        return 0.0


def _tokens(filename: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", Path(filename or "").name.lower())
        if token
    }
