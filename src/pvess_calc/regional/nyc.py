"""NYC DOB / FDNY stationary ESS screening.

This is a filing-readiness screen, not a full NYC code engine. NYC ESS
projects require DOB and FDNY review paths that are materially different
from generic NEC/IRC residential assumptions, so the regional summary must
surface them instead of letting the base ESS checks look complete.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from ..calc.engine import CalculationResult


@dataclass
class NycEssResult:
    applies: bool
    status: Literal["PASS", "MANUAL", "N/A"]
    required_filings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def is_nyc_project(result: "CalculationResult") -> bool:
    i = result.inputs
    blob = " ".join([
        i.project.location,
        i.project.site_address,
        i.project.ahj,
    ]).lower()
    nyc_tokens = (
        "new york, ny", "new york city", "nyc", "brooklyn", "queens",
        "bronx", "staten island", "manhattan",
    )
    return any(token in blob for token in nyc_tokens)


def check_nyc_ess(result: "CalculationResult") -> NycEssResult:
    """Flag NYC-specific ESS filings for stationary residential storage."""
    if not is_nyc_project(result):
        return NycEssResult(applies=False, status="N/A")
    if result.inputs.battery.quantity <= 0:
        return NycEssResult(
            applies=True,
            status="N/A",
            notes=["NYC project has no ESS declared."],
        )

    location = result.inputs.battery.install_location
    total_kwh = result.inputs.battery.total_kwh
    filings = [
        "DOB full-plan ESS filing (GC work type / EESE subcategory)",
        "FDNY ESS Certificate of Approval / site-specific approval",
        "FDNY inspection / operating permit when indoor ESS applies",
    ]
    notes = [
        "NYC stationary ESS is outside the generic IRC-only residential path.",
        f"Declared ESS capacity: {total_kwh:.1f} kWh; install location: {location}.",
        "Verify UL 9540 listing, UL 9540A evidence, fire barrier, ventilation, "
        "and below-grade restrictions with FDNY/DOB.",
    ]
    if location in {"indoor", "garage", "unknown"}:
        notes.append(
            "Indoor/garage/unknown ESS location requires manual NYC FDNY review "
            "before treating the plan set as submit-ready."
        )

    return NycEssResult(
        applies=True,
        status="MANUAL",
        required_filings=filings,
        notes=notes,
    )
