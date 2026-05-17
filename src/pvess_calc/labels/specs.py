"""NEC 2023 placard / label catalog for residential PV + ESS systems.

Each `LabelSpec` is a template; `{{KEY}}` placeholders resolve from
`pvess_calc.qet.inject.build_substitutions(result)`. The `applies()` predicate
gates whether the label gets emitted for a given project (e.g. only print the
705.12 "do not relocate" placard when the 120% rule is the chosen
interconnection method).

This module is *data* — keep it free of rendering concerns. The renderer in
`labels.render` is responsible for layout, colors, and PDF output.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

from ..calc.engine import CalculationResult

Severity = Literal["DANGER", "WARNING", "CAUTION", "NOTICE", "PLAIN"]


@dataclass
class LabelSpec:
    nec_clause: str              # e.g. "690.13(B)"
    purpose: str                 # short human description
    severity: Severity           # banner color/word at top of label
    title: str                   # bold caps, one or two lines (use \n)
    body_lines: list[str]        # template lines; may contain {{KEY}}
    location_hint: str           # where the installer should mount it
    applies: Callable[[CalculationResult], bool] = field(
        default=lambda r: True
    )


# --- Predicates -------------------------------------------------------------

def _has_ess(r: CalculationResult) -> bool:
    return r.inputs.battery.quantity > 0


def _interconnect_is(method: str) -> Callable[[CalculationResult], bool]:
    return lambda r: r.interconnect.recommended == method


# --- The catalog ------------------------------------------------------------

LABEL_CATALOG: list[LabelSpec] = [
    LabelSpec(
        nec_clause="690.13(B)",
        purpose="PV DC disconnect identifier",
        severity="WARNING",
        title="PHOTOVOLTAIC SYSTEM\nDC DISCONNECT",
        body_lines=[
            "Maximum System Voltage: {{PV_VOC_COLD}}",
            "Short-Circuit Current:  {{PV_ISC_MAX}}",
            "",
            "ELECTRIC SHOCK HAZARD.",
            "TERMINALS ON BOTH LINE AND LOAD SIDES",
            "MAY BE ENERGIZED IN THE OPEN POSITION.",
        ],
        location_hint="On or adjacent to the PV DC disconnect.",
    ),

    LabelSpec(
        nec_clause="690.53",
        purpose="DC PV power source placard",
        severity="NOTICE",
        title="DC PHOTOVOLTAIC POWER SOURCE",
        body_lines=[
            "Maximum System Voltage:  {{PV_VOC_COLD}}",
            "Max PV Source Current:   {{PV_ISC_MAX}}",
            "Max OCPD Rating:         {{PV_OCPD}}",
            "Array: {{PV_STRINGS}} × {{PV_MODULES_PER_STRING}} = {{PV_MODULE_COUNT}} modules",
        ],
        location_hint="On the PV system DC disconnect.",
    ),

    LabelSpec(
        nec_clause="690.14",
        purpose="PV AC disconnect identifier",
        severity="WARNING",
        title="PHOTOVOLTAIC SYSTEM\nAC DISCONNECT",
        body_lines=[
            "Rated AC Output: {{INVERTER_AC}}",
            "OCPD: {{AC_DISC_OCPD}}",
            "",
            "TURN OFF BEFORE SERVICING.",
        ],
        location_hint="On the AC disconnect serving the PV/ESS inverter.",
    ),

    LabelSpec(
        nec_clause="690.56(C)",
        purpose="Rapid Shutdown identification at service equipment",
        severity="WARNING",
        title="SOLAR PV SYSTEM EQUIPPED WITH\nRAPID SHUTDOWN",
        body_lines=[
            "TURN RAPID SHUTDOWN SWITCH TO THE \"OFF\"",
            "POSITION TO SHUT DOWN PV SYSTEM AND",
            "REDUCE SHOCK HAZARD IN THE ARRAY.",
            "",
            # K.7: boundary voltage limit is NEC-edition specific —
            # 80 V for 2017, 30 V for 2020+. {{RSD_BOUNDARY_V}} is
            # populated by qet.inject.build_substitutions().
            "Within 30 s after initiation, array boundary",
            "voltage reduces to ≤ {{RSD_BOUNDARY_V}} (NEC 690.12(B)(2)).",
            "",
            "RSD device: {{RSD_LABEL}} ({{RSD_MODEL}})",
        ],
        location_hint="At service equipment / main meter; visible from street.",
    ),

    LabelSpec(
        nec_clause="705.10",
        purpose="Identification of all on-site power sources at service",
        severity="NOTICE",
        title="POWER SOURCES PRESENT",
        body_lines=[
            "UTILITY SERVICE:     {{MSP_RATING}}",
            "PHOTOVOLTAIC SOURCE: {{PV_OCPD}}  ({{PV_LABEL}})",
            "ENERGY STORAGE:      {{AC_DISC_OCPD}}  ({{ESS_LABEL}})",
            "",
            "SEE INSIDE PANEL FOR DISCONNECT DIRECTORY.",
        ],
        location_hint="At the main service disconnect.",
    ),

    LabelSpec(
        nec_clause="705.12(B)(3)(2)",
        purpose="Backfed OCPD positional lock (120% rule path)",
        severity="WARNING",
        title="INVERTER OUTPUT CONNECTION",
        body_lines=[
            "DO NOT RELOCATE THIS OVERCURRENT DEVICE.",
            "",
            "Busbar: {{BUSBAR_RATING}}",
            "Backfeed: {{TOTAL_BACKFEED}}",
        ],
        location_hint="On the backfed breaker in the load center.",
        applies=_interconnect_is("120%_rule"),
    ),

    LabelSpec(
        nec_clause="705.11",
        purpose="Supply-side tap identification",
        severity="WARNING",
        title="SOLAR PV SYSTEM\nAC CONNECTION:\nSUPPLY SIDE TAP",
        body_lines=[
            "DO NOT REMOVE.",
            "",
            "Tap conductors per NEC 240.21(B).",
            "Backfeed: {{TOTAL_BACKFEED}}",
        ],
        location_hint="At the supply-side tap (between meter and service disconnect).",
        applies=_interconnect_is("supply_side_tap"),
    ),

    LabelSpec(
        nec_clause="706.7",
        purpose="ESS disconnect identifier",
        severity="WARNING",
        title="ENERGY STORAGE SYSTEM\nDISCONNECT",
        body_lines=[
            "{{ESS_MODEL}}",
            "Capacity: {{ESS_KWH}}  ({{ESS_QTY}} units)",
            "",
            "ELECTRIC SHOCK HAZARD.",
            "ENERGIZED EVEN WHEN UTILITY IS OFF.",
        ],
        location_hint="On each ESS unit and its DC/AC disconnects.",
        applies=_has_ess,
    ),

    LabelSpec(
        nec_clause="690.31(D)",
        purpose="PV power source label for DC conduits and junction boxes",
        severity="PLAIN",
        title="PHOTOVOLTAIC POWER SOURCE",
        body_lines=[
            "(Place at intervals of ≤ 10 ft on DC conduit",
            "and on every junction box, pull box, and conduit body.)",
        ],
        location_hint="DC conduit at ≤10 ft intervals; every junction box.",
    ),
]
