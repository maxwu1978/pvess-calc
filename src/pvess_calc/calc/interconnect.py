"""NEC 705.12 interconnection-point compliance.

Evaluates each candidate method declared in inputs.yaml and reports which one
should be used. Multiple methods can PASS; we recommend the first PASS in the
user-declared priority order.

**K.2.5 — multi-existing-PV bus-load principle.** NEC 705.12(B)(3) governs
the TOTAL backfeed presence on the busbar, not just the newly-added
system. When a homeowner already has rooftop PV on the MSP (or on a
sub-panel) and is adding ESS, the sum / 120% checks must apply to
(main_breaker + existing_solar + new_inverter_backfeed). Missing the
existing breaker is the #1 way an interconnection drawing PASSES at
desk-review but FAILS at the AHJ utility-coordination meeting.

`Service.total_existing_solar_a` rolls up:
  * `service.existing_solar_breaker_a_msp` — backfeed already on the MSP itself
  * sum of `sub_panels[i].existing_solar_breaker_a` — backfeed in any sub-panel

The evaluator adds this to the new system's backfeed BEFORE comparing
against the busbar limit.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..nec import get_rules
from ..schema import InterconnectMethod, Inputs

MethodStatus = Literal["PASS", "FAIL", "N/A"]


@dataclass
class MethodEvaluation:
    method: InterconnectMethod
    status: MethodStatus
    formula: str
    explanation: str


@dataclass
class InterconnectResult:
    total_backfeed_a: float           # NEW system backfeed only
    existing_solar_a: float           # K.2.5: pre-existing PV/ESS on bus
    combined_backfeed_a: float        # K.2.5: total_backfeed_a + existing_solar_a
    main_breaker_a: float
    busbar_a: float
    evaluations: list[MethodEvaluation]
    recommended: InterconnectMethod | None
    overall_status: Literal["PASS", "FAIL"]


def compute_interconnection(inputs: Inputs) -> InterconnectResult:
    inv = inputs.inverter
    bat = inputs.battery
    svc = inputs.service
    rules = get_rules(inputs.project.nec_edition)

    n_inverters = inv.count(bat.quantity)
    new_backfeed = inv.ac_output_a * n_inverters
    existing_solar = svc.total_existing_solar_a
    combined_backfeed = new_backfeed + existing_solar

    main = svc.main_panel_a
    bus = svc.busbar_a

    evals: list[MethodEvaluation] = []
    for method in svc.interconnection_methods:
        if method in rules.DISALLOWED_INTERCONNECT_METHODS:
            evals.append(MethodEvaluation(
                method=method,
                status="N/A",
                formula=f"removed in NEC {rules.EDITION}",
                explanation=(
                    f"The {method} interconnection path was removed in the "
                    f"NEC {rules.EDITION} cycle; skip it for this project."
                ),
            ))
            continue
        evals.append(_evaluate(
            method, main, bus, new_backfeed, existing_solar, rules,
        ))

    recommended: InterconnectMethod | None = next(
        (e.method for e in evals if e.status == "PASS"), None
    )
    overall = "PASS" if recommended is not None else "FAIL"

    return InterconnectResult(
        total_backfeed_a=new_backfeed,
        existing_solar_a=existing_solar,
        combined_backfeed_a=combined_backfeed,
        main_breaker_a=main,
        busbar_a=bus,
        evaluations=evals,
        recommended=recommended,
        overall_status=overall,
    )


def _evaluate(
    method: InterconnectMethod, main: float, bus: float,
    new_backfeed: float, existing_solar: float, rules,
) -> MethodEvaluation:
    """Apply ONE 705.12 method to the bus, summing new + existing
    backfeed before comparing against the bus limit.

    `existing_solar` is the rolled-up `Service.total_existing_solar_a`
    (MSP + all sub-panels). When zero, the formula degenerates to the
    classic greenfield sum: main + new_backfeed ≤ limit.
    """
    combined = new_backfeed + existing_solar
    existing_part = (
        f" + {existing_solar:.0f} (existing)" if existing_solar > 0 else ""
    )

    if method == "120%_rule":
        limit = bus * rules.BUSBAR_MULTIPLIER_120_RULE
        total = main + combined
        ok = total <= limit
        return MethodEvaluation(
            method=method,
            status="PASS" if ok else "FAIL",
            formula=("main + new_backfeed + existing_solar ≤ busbar × 1.20"
                     if existing_solar > 0 else
                     "main + backfeed ≤ busbar × 1.20"),
            explanation=(
                f"{main:.0f} + {new_backfeed:.0f}{existing_part} "
                f"= {total:.0f} A "
                f"{'≤' if ok else '>'} {bus:.0f} × 1.20 = {limit:.0f} A"
            ),
        )

    if method == "sum_rule":
        # 705.12(B)(3)(1): main + ALL backfeed ≤ bus
        total = main + combined
        ok = total <= bus
        return MethodEvaluation(
            method=method,
            status="PASS" if ok else "FAIL",
            formula=("main + new_backfeed + existing_solar ≤ busbar"
                     if existing_solar > 0 else "main + backfeed ≤ busbar"),
            explanation=(
                f"{main:.0f} + {new_backfeed:.0f}{existing_part} "
                f"= {total:.0f} A "
                f"{'≤' if ok else '>'} {bus:.0f} A"
            ),
        )

    if method == "supply_side_tap":
        # 705.11: supply-side tap is not bound by busbar rules.
        # Always feasible from a busbar-math standpoint; physical install
        # requirements (tap conductors per 240.21(B)) are out of scope here.
        note = (
            "Tap is on the line side of the service disconnect; "
            "busbar 120%/sum rules do not apply. Verify tap conductor "
            "sizing per 240.21(B) at install time."
        )
        if existing_solar > 0:
            note += (
                f" NOTE: pre-existing PV backfeed ({existing_solar:.0f} A) "
                "remains on the load side and must still comply with 705.12 "
                "for that panel."
            )
        return MethodEvaluation(
            method=method,
            status="PASS",
            formula="N/A (705.11 supply-side tap bypasses busbar rules)",
            explanation=note,
        )

    if method == "center_fed":
        # 705.12(B)(3)(3): backfeed ≤ bus, main at one end, backfeed at center.
        # Without panel geometry we report N/A and defer to install.
        return MethodEvaluation(
            method=method,
            status="N/A",
            formula="backfeed ≤ busbar, source at center-fed position",
            explanation=(
                "Center-fed eligibility depends on panel construction; "
                "evaluate against the listed panel only."
            ),
        )

    return MethodEvaluation(
        method=method,
        status="N/A",
        formula="(unknown method)",
        explanation=f"Method '{method}' not implemented.",
    )
