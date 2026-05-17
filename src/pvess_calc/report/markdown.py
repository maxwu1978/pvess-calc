"""Render the Markdown NEC report from a CalculationResult."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from ..calc.engine import CalculationResult

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )


def render(result: CalculationResult) -> str:
    env = _env()
    template = env.get_template("report.md.j2")
    ctx = result.to_dict()
    # design_low_temp_c is a property, not in model_dump; inject it.
    ctx["inputs"]["pv_array"]["design_low_temp_c"] = result.inputs.pv_array.design_low_temp_c
    # inverter.count() depends on per_unit / quantity logic; resolve once.
    ctx["inverter_count"] = result.inputs.inverter.count(
        result.inputs.battery.quantity
    )
    # K.2.5: load demand properties (annual / peak month) — only valid
    # when 12 monthly values are supplied. Inject as None when absent so
    # the template's `is not none` gate skips the section.
    ctx["inputs"]["loads"]["annual_kwh"] = result.inputs.loads.annual_kwh
    ctx["inputs"]["loads"]["peak_month_kwh"] = result.inputs.loads.peak_month_kwh
    # K.2.6b: `overall_status` is a property, not in asdict() output —
    # inject explicitly so the template can render the status banner.
    ctx["ess_install"]["overall_status"] = result.ess_install.overall_status
    # K.5: `electrode_summary` is a property on GroundingResult; inject
    # it for the template's GES list (otherwise jinja sees the asdict()
    # output which doesn't carry the @property).
    ctx["grounding"]["electrode_summary"] = result.grounding.electrode_summary
    return template.render(**ctx)


def write_markdown(result: CalculationResult, path: Path) -> None:
    path.write_text(render(result), encoding="utf-8")
