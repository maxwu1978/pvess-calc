"""Available fault current and OCPD AIC validation (NEC 110.24).

110.24(A) requires every service to be marked with the maximum available fault
current; (B) prohibits using OCPDs with interrupting rating below that value.

We compute the fault current at the service entrance from a simple
transformer-impedance model (NEC Annex D / IEEE 141), then check each OCPD's
AIC rating against it.

This is a residential approximation — utility-side impedance is ignored and
the transformer is assumed to be an infinite source on its primary side. Real
projects should defer to the utility's fault-current letter.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from ..schema import Inputs


@dataclass
class OcpdAicCheck:
    label: str                   # e.g. "PV OCPD", "ESS AC disconnect"
    ocpd_rating_a: int
    aic_required_ka: float       # = available fault current
    aic_supplied_ka: float       # = OCPD interrupting rating
    status: Literal["PASS", "FAIL"]
    margin_ka: float


@dataclass
class AicResult:
    transformer_kva: float
    transformer_z_pct: float
    secondary_voltage_v: float
    available_fault_current_a: float
    available_fault_current_ka: float
    ocpd_checks: list[OcpdAicCheck] = field(default_factory=list)
    overall_status: Literal["PASS", "FAIL"] = "PASS"


def available_fault_current(kva: float, z_pct: float, v_secondary: float) -> float:
    """Transformer-impedance approximation.

    For single-phase (split-phase) residential:
        I_FLA = (kVA × 1000) / V
        I_SC  = I_FLA / (Z / 100)

    For three-phase (commercial), multiply by √3 in I_FLA — not needed for
    typical residential. We assume single-phase here; callers concerned with
    three-phase should bypass this helper.
    """
    if z_pct <= 0 or v_secondary <= 0:
        return 0.0
    i_fla = kva * 1000.0 / v_secondary
    i_sc = i_fla * 100.0 / z_pct
    return i_sc


def compute_aic(
    inputs: Inputs,
    *,
    ocpd_ratings: dict[str, int],
) -> AicResult:
    """Validate every project OCPD against the service available fault current."""
    xfmr = inputs.service.utility_transformer
    i_sc = available_fault_current(
        kva=xfmr.kva,
        z_pct=xfmr.impedance_pct,
        v_secondary=xfmr.secondary_voltage,
    )
    i_sc_ka = i_sc / 1000.0
    aic_supplied_ka = inputs.service.default_ocpd_aic_ka

    checks: list[OcpdAicCheck] = []
    for label, rating in ocpd_ratings.items():
        margin = aic_supplied_ka - i_sc_ka
        checks.append(OcpdAicCheck(
            label=label,
            ocpd_rating_a=rating,
            aic_required_ka=i_sc_ka,
            aic_supplied_ka=aic_supplied_ka,
            status="PASS" if margin >= 0 else "FAIL",
            margin_ka=margin,
        ))

    overall = "FAIL" if any(c.status == "FAIL" for c in checks) else "PASS"

    return AicResult(
        transformer_kva=xfmr.kva,
        transformer_z_pct=xfmr.impedance_pct,
        secondary_voltage_v=xfmr.secondary_voltage,
        available_fault_current_a=i_sc,
        available_fault_current_ka=i_sc_ka,
        ocpd_checks=checks,
        overall_status=overall,
    )
