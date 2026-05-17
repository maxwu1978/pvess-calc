"""Inject calculation results into a QET template by replacing `{{KEY}}` placeholders.

Hard constraints (Phase 0):
  - Only edit text content (the `text` attribute on `<input>`, or element text body).
  - Never modify element position (x/y/rotation), structure, or connections.
  - Any unresolved `{{KEY}}` placeholder after injection is an error.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from lxml import etree

from ..calc.engine import CalculationResult
from ..nec import get_rules
from .parse import iter_text_elements, parse, write


def _rsd_boundary_volts(nec_edition: str) -> str:
    """K.7 Step 2 — return the formatted RSD boundary voltage limit for
    the given NEC edition (e.g. '80 V' for 2017, '30 V' for 2020+).

    Centralised here so the labels.specs body template can include the
    actual threshold value via {{RSD_BOUNDARY_V}} substitution. Falls
    back to the v2023 value when an unknown edition is supplied —
    matches the get_rules() dispatcher behaviour.
    """
    rules = get_rules(nec_edition)
    return f"{rules.RSD_BOUNDARY_VOLTAGE_LIMIT:.0f} V"

PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Z0-9_]+)\s*\}\}")


@dataclass
class InjectionReport:
    output_path: Path
    substitutions_applied: int
    keys_used: set[str]


def build_substitutions(result: CalculationResult) -> dict[str, str]:
    """Map placeholder keys (in template) to formatted display values."""
    i = result.inputs
    pv = result.pv_string
    cond = result.pv_conductor
    vd = result.pv_voltage_drop
    ic = result.interconnect
    ess = result.ess
    ess_cond = result.ess_conductor

    recommended = ic.recommended or "FAIL"

    return {
        # Project metadata
        "PROJECT_NAME": i.project.name,
        "PROJECT_ID": i.project.id,
        "PROJECT_LOCATION": i.project.location,
        "NEC_EDITION": f"NEC {i.project.nec_edition}",
        # PV array
        "PV_LABEL": "PV-1",
        "PV_MODULE": f"{i.pv_array.module.brand} {i.pv_array.module.model} ({i.pv_array.module.power_w:.0f} W)",
        "PV_STRINGS": str(i.pv_array.strings),
        "PV_MODULES_PER_STRING": str(i.pv_array.modules_per_string),
        "PV_MODULE_COUNT": str(i.pv_array.modules),
        "PV_VOC_COLD": f"{pv.string_voc_cold:.0f} V DC",
        "PV_ISC_MAX": f"{pv.isc_690_8_a:.1f} A",
        # DC combiner / conductor / OCPD
        "DC_COMBINER_LABEL": "DC-COMB-1",
        "PV_OCPD": f"{result.pv_ocpd_a} A",
        "PV_CONDUCTOR": f"{cond.size} AWG @ 75°C ({cond.ampacity_a} A)",
        "PV_VOLTAGE_DROP": f"{vd.drop_volts:.2f} V ({vd.drop_percent:.2f} %)",
        # RSD — boundary voltage threshold differs by NEC edition
        # (2017 = 80V, 2020/2023 = 30V). The label printer pulls this
        # from the version-specific rules module.
        "RSD_LABEL": "RSD-1",
        "RSD_MODEL": "Per inverter mfr (NEC 690.12)",
        "RSD_BOUNDARY_V": _rsd_boundary_volts(i.project.nec_edition),
        # Inverter
        "INVERTER_LABEL": "INV-1",
        "INVERTER_QTY": str(i.inverter.count(i.battery.quantity)),
        "INVERTER_MODEL": (
            f"{i.inverter.brand} {i.inverter.model}"
            + (f" × {i.inverter.count(i.battery.quantity)}"
               if i.inverter.count(i.battery.quantity) > 1 else "")
        ),
        "INVERTER_AC": (
            f"{i.inverter.ac_output_v:.0f} V / {i.inverter.ac_output_a:.0f} A AC"
            + (f" (× {i.inverter.count(i.battery.quantity)} = "
               f"{i.inverter.ac_output_a * i.inverter.count(i.battery.quantity):.0f} A total)"
               if i.inverter.count(i.battery.quantity) > 1 else "")
        ),
        # ESS
        "ESS_LABEL": "ESS-1",
        "ESS_MODEL": f"{i.battery.brand} {i.battery.model}",
        "ESS_QTY": str(i.battery.quantity),
        "ESS_KWH": f"{ess.total_kwh:.1f} kWh",
        # AC disconnect
        "AC_DISC_LABEL": "AC-DISC-1",
        "AC_DISC_OCPD": f"{ess.ac_disconnect_ocpd_a} A",
        "ESS_AC_CONDUCTOR": f"{ess_cond.size} AWG ({ess_cond.ampacity_a} A)",
        # Service / interconnection
        "MSP_LABEL": "MSP",
        "MSP_RATING": f"{int(i.service.main_panel_a)} A / {i.service.voltage}",
        "BUSBAR_RATING": f"{int(i.service.busbar_a)} A ({i.service.busbar_source})",
        "TOTAL_BACKFEED": f"{ic.total_backfeed_a:.1f} A",
        "INTERCONNECT_METHOD": recommended,
        "INTERCONNECT_STATUS": ic.overall_status,
    }


def inject(
    template_path: Path,
    output_path: Path,
    substitutions: Mapping[str, str],
    strict: bool = True,
) -> InjectionReport:
    """Copy template → output_path, then replace `{{KEY}}` placeholders."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template_path, output_path)

    tree = parse(output_path)

    count = 0
    keys_used: set[str] = set()
    unresolved: list[str] = []

    for el in iter_text_elements(tree):
        for attr in ("text",):
            v = el.get(attr)
            if v and PLACEHOLDER_RE.search(v):
                new_v, n, missing = _substitute(v, substitutions)
                el.set(attr, new_v)
                count += n
                keys_used.update(_keys_in(v) - set(missing))
                unresolved.extend(missing)
        if el.text and PLACEHOLDER_RE.search(el.text):
            new_v, n, missing = _substitute(el.text, substitutions)
            el.text = new_v
            count += n
            keys_used.update(_keys_in(el.text or "") - set(missing))
            unresolved.extend(missing)

    if strict and unresolved:
        raise KeyError(
            f"Unresolved placeholders in {template_path}: {sorted(set(unresolved))}"
        )

    write(tree, output_path)
    return InjectionReport(
        output_path=output_path,
        substitutions_applied=count,
        keys_used=keys_used,
    )


def _substitute(
    text: str, subs: Mapping[str, str]
) -> tuple[str, int, list[str]]:
    missing: list[str] = []
    count = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal count
        key = m.group(1)
        if key in subs:
            count += 1
            return subs[key]
        missing.append(key)
        return m.group(0)

    return PLACEHOLDER_RE.sub(repl, text), count, missing


def _keys_in(text: str) -> set[str]:
    return {m.group(1) for m in PLACEHOLDER_RE.finditer(text)}


def inject_from_result(
    result: CalculationResult,
    template_path: Path,
    output_path: Path,
    strict: bool = True,
) -> InjectionReport:
    return inject(
        template_path=template_path,
        output_path=output_path,
        substitutions=build_substitutions(result),
        strict=strict,
    )
