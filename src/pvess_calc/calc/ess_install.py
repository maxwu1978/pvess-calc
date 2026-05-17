"""K.2.6b — NEC 706.10 + IRC R328 ESS install-location compliance.

What this module checks (in homeowner language: "can the battery
physically go where you want to put it?"):

  * **Setbacks** — IRC R328.5 requires ≥3 ft clearance from doors,
    operable windows that open into occupiable spaces, and required
    egress paths.
  * **Capacity ceiling per location** — IRC R328.4 (2021): 40 kWh max
    per location for residential indoor installs. IRC 2024 raised this
    to 80 kWh for ESS that carry UL 9540A non-propagation listing.
  * **Location-class rules** — `indoor` is the strictest;
    `garage` permits more capacity; `outdoor` follows NEC 706 only.
    `outdoor_protected` = weather-rated NEMA 3R enclosure with thermal
    management, treated as outdoor for code purposes.

Output is a `ComplianceResult` listing per-check PASS / FAIL / WARN
with the relevant code reference, mirroring the 705.12 evaluator's
shape so the report renderer can format both uniformly.

Limits (K.2.6b conservative — assumes IRC 2021 + NEC 2023):
  * Setbacks: 3 ft (door / window / egress)
  * Capacity ceiling per location: 40 kWh (IRC 2021)
  * `unknown` install_location → WARN (missing data), not FAIL
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..schema import Inputs


CheckStatus = Literal["PASS", "FAIL", "WARN", "N/A"]


# IRC R328 setback minima (ft). Conservative defaults; some AHJs
# permit smaller setbacks for listed-as-non-propagating ESS — flag in
# yaml when verified.
MIN_SETBACK_FT: float = 3.0

# IRC R328.4 (2021) — max ESS energy per dwelling unit location.
MAX_INDOOR_CAPACITY_KWH: float = 40.0


@dataclass
class ComplianceCheck:
    name: str
    status: CheckStatus
    code_ref: str       # e.g. "IRC R328.5"
    detail: str         # one-line explanation for the report


@dataclass
class EssInstallCompliance:
    install_location: str
    checks: list[ComplianceCheck]

    @property
    def overall_status(self) -> CheckStatus:
        if any(c.status == "FAIL" for c in self.checks):
            return "FAIL"
        if any(c.status == "WARN" for c in self.checks):
            return "WARN"
        return "PASS"


def evaluate_ess_install(inputs: Inputs) -> EssInstallCompliance:
    """Run every applicable check. Always returns a result (never raises) —
    'unknown' location yields a single WARN check so the report shows
    'data needed' rather than crashing or silently passing."""
    bat = inputs.battery
    loc = bat.install_location
    checks: list[ComplianceCheck] = []

    if loc == "unknown":
        return EssInstallCompliance(
            install_location=loc,
            checks=[ComplianceCheck(
                name="install_location_specified",
                status="WARN",
                code_ref="IRC R328 / NEC 706.10",
                detail=("Install location not specified in inputs.yaml. "
                        "Set `battery.install_location` to one of indoor / "
                        "garage / outdoor / outdoor_protected to enable "
                        "compliance checks."),
            )],
        )

    # Setback checks — only meaningful for indoor / garage installs.
    indoor_class = loc in ("indoor", "garage")
    if indoor_class:
        checks.append(_setback_check(
            "doorway_setback", bat.distance_to_doorway_ft,
            "doorways", "IRC R328.5",
        ))
        checks.append(_setback_check(
            "window_setback", bat.distance_to_window_ft,
            "operable windows", "IRC R328.5",
        ))
        checks.append(_setback_check(
            "egress_setback", bat.distance_to_egress_ft,
            "required egress paths", "IRC R328.4",
        ))

        # Capacity ceiling per location.
        if bat.total_kwh > MAX_INDOOR_CAPACITY_KWH:
            checks.append(ComplianceCheck(
                name="capacity_ceiling",
                status="FAIL",
                code_ref="IRC R328.4 (2021)",
                detail=(f"Total {bat.total_kwh:.1f} kWh exceeds "
                        f"{MAX_INDOOR_CAPACITY_KWH:.0f} kWh ceiling for "
                        f"{loc} install. Either split across locations, "
                        "move outdoors, or verify ESS has UL 9540A "
                        "non-propagation listing (allows up to 80 kWh "
                        "under IRC 2024)."),
            ))
        else:
            checks.append(ComplianceCheck(
                name="capacity_ceiling",
                status="PASS",
                code_ref="IRC R328.4 (2021)",
                detail=(f"{bat.total_kwh:.1f} kWh ≤ "
                        f"{MAX_INDOOR_CAPACITY_KWH:.0f} kWh limit for "
                        f"{loc} install."),
            ))
    else:
        # Outdoor / outdoor_protected — no setback or capacity ceiling
        # under IRC R328 (NEC 706 only). Surface that as a passing note
        # rather than silently skipping.
        checks.append(ComplianceCheck(
            name="outdoor_install",
            status="PASS",
            code_ref="NEC 706.10",
            detail=(f"Outdoor install ({loc}) — IRC R328 setbacks and "
                    "capacity ceilings do not apply. Verify NEC 706.10 "
                    "disconnect placement at install time."),
        ))

    return EssInstallCompliance(install_location=loc, checks=checks)


def _setback_check(
    name: str, distance_ft: float, what: str, code: str,
) -> ComplianceCheck:
    """Single-distance compliance row. 0.0 = unknown → WARN, not FAIL,
    so missing measurements don't masquerade as compliant."""
    if distance_ft <= 0.0:
        return ComplianceCheck(
            name=name, status="WARN", code_ref=code,
            detail=(f"Distance to {what} not measured. Required "
                    f"≥{MIN_SETBACK_FT:.0f} ft."),
        )
    if distance_ft >= MIN_SETBACK_FT:
        return ComplianceCheck(
            name=name, status="PASS", code_ref=code,
            detail=(f"{distance_ft:.1f} ft to {what} ≥ "
                    f"{MIN_SETBACK_FT:.0f} ft."),
        )
    return ComplianceCheck(
        name=name, status="FAIL", code_ref=code,
        detail=(f"{distance_ft:.1f} ft to {what} < required "
                f"{MIN_SETBACK_FT:.0f} ft. Relocate ESS or modify "
                "doorway/window placement."),
    )
