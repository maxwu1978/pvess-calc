"""Regional-rule aggregation for Phase I.

The individual regional modules are intentionally narrow. This module is the
single surface consumed by reports, JSON, and doctor checks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import TYPE_CHECKING, Literal

from .california import check_title_24
from .hawaii import check_rule_14h
from .nyc import check_nyc_ess, is_nyc_project

if TYPE_CHECKING:
    from ..calc.engine import CalculationResult


RegionalStatus = Literal["PASS", "WARN", "FAIL", "MANUAL", "N/A"]


@dataclass
class RegionalCheck:
    jurisdiction: str
    topic: str
    status: RegionalStatus
    detail: str


@dataclass
class RegionalSummary:
    state: str = ""
    checks: list[RegionalCheck] = field(default_factory=list)

    @property
    def applicable(self) -> bool:
        return bool(self.checks)

    @property
    def overall_status(self) -> RegionalStatus:
        statuses = [c.status for c in self.checks]
        if not statuses:
            return "N/A"
        if "FAIL" in statuses:
            return "FAIL"
        if "MANUAL" in statuses:
            return "MANUAL"
        if "WARN" in statuses:
            return "WARN"
        if "PASS" in statuses:
            return "PASS"
        return "N/A"


def infer_state(result: "CalculationResult") -> str:
    """Infer a two-letter state from structured-ish project metadata."""
    for text in (
        result.inputs.project.location,
        result.inputs.project.site_address,
    ):
        if not text:
            continue
        matches = re.findall(r"\b[A-Z]{2}\b", text.upper())
        if matches:
            return matches[-1]
    return ""


def evaluate_regional_requirements(
    result: "CalculationResult",
) -> RegionalSummary:
    state = infer_state(result)
    checks: list[RegionalCheck] = []

    if state == "CA":
        annual = result.inputs.loads.annual_kwh or 6500.0
        t24 = check_title_24(result, annual_load_kwh=annual)
        checks.append(RegionalCheck(
            "California",
            "Title 24 PV sizing",
            "PASS" if t24.pv_meets_t24 else "WARN",
            (
                f"{t24.pv_provided_kw:.2f} kWdc provided vs "
                f"{t24.pv_sizing_min_kw:.2f} kWdc screening threshold"
            ),
        ))
        checks.append(RegionalCheck(
            "California",
            "ESS-ready / NEM 3 awareness",
            "PASS" if t24.nem_3_aware else "MANUAL",
            "Battery installed" if t24.battery_storage_ready
            else "No battery installed; verify ESS-ready compliance if new construction",
        ))

    if state == "HI":
        hi = check_rule_14h(result)
        checks.append(RegionalCheck(
            "Hawaii",
            "Rule 14H fast-track screen",
            "PASS" if hi.fast_track_eligible else "WARN",
            hi.notes[0],
        ))
        checks.append(RegionalCheck(
            "Hawaii",
            "Rule 14H smart inverter / CSS",
            "MANUAL",
            "Smart inverter settings evidence required; CSS eligible"
            if hi.css_eligible
            else "Smart inverter settings evidence required; no ESS for CSS path",
        ))

    utility_blob = " ".join([
        result.inputs.project.utility,
        result.inputs.project.ahj,
        result.inputs.project.site_address,
    ]).lower()
    if state == "TX" and "oncor" in utility_blob:
        esid = result.inputs.project.meter_info.esid
        checks.append(RegionalCheck(
            "Texas / Oncor",
            "DG interconnection cover letter",
            "PASS",
            "Oncor cover-letter renderer available for package appendix",
        ))
        checks.append(RegionalCheck(
            "Texas / Oncor",
            "ESID field",
            "PASS" if esid else "MANUAL",
            f"ESID {esid}" if esid else "Oncor ESID missing; collect from utility bill",
        ))

    if is_nyc_project(result):
        nyc = check_nyc_ess(result)
        if nyc.applies:
            checks.append(RegionalCheck(
                "NYC DOB / FDNY",
                "Stationary ESS filing path",
                nyc.status,
                "; ".join(nyc.notes[:2]) if nyc.notes else "No NYC ESS action",
            ))
            if nyc.required_filings:
                checks.append(RegionalCheck(
                    "NYC DOB / FDNY",
                    "Required ESS filings",
                    "MANUAL",
                    "; ".join(nyc.required_filings),
                ))

    return RegionalSummary(state=state, checks=checks)
