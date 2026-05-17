"""Run N scenarios in parallel and tabulate the key design metrics."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from ..calc.engine import CalculationResult, run
from ..schema import Inputs
from .bom import BomEstimate, compute_bom


@dataclass
class ScenarioResult:
    name: str                       # subdirectory name (e.g. "A", "small")
    inputs_path: Path
    result: CalculationResult
    bom: BomEstimate

    @property
    def summary(self) -> dict[str, str]:
        """One-line summary fields used by the comparison table."""
        r = self.result
        i = r.inputs
        n_inv = i.inverter.count(i.battery.quantity)
        dc_kw = i.pv_array.modules * i.pv_array.module.power_w / 1000.0
        ac_kw = i.inverter.ac_output_v * i.inverter.ac_output_a * n_inv / 1000.0
        backup_kwh = i.battery.total_kwh
        aic_status = r.aic.overall_status
        aic_margin = min(
            (c.margin_ka for c in r.aic.ocpd_checks), default=0.0
        )
        vd_status = r.voltage_drop_analysis.overall_status
        return {
            "scenario": self.name,
            "PV (kW)":      f"{dc_kw:.2f}",
            "AC (kW)":      f"{ac_kw:.2f}",
            "ESS (kWh)":    f"{backup_kwh:.1f}",
            "Backfeed (A)": f"{r.interconnect.total_backfeed_a:.0f}",
            "Interconnect": r.interconnect.recommended or "FAIL",
            "Voc cold (V)": f"{r.pv_string.string_voc_cold:.0f}",
            "PV OCPD":      f"{r.pv_ocpd_a} A",
            "AC OCPD":      f"{r.ess.ac_disconnect_ocpd_a} A",
            "Vd e2e":       f"{r.voltage_drop_analysis.total_end_to_end_pct:.2f}% ({vd_status})",
            "AIC margin":   f"{aic_margin:+.1f} kA ({aic_status})",
            "BOM (USD)":    f"${self.bom.subtotal_usd:,.0f}",
        }


def load_scenarios(scenarios_dir: Path) -> list[tuple[str, Path]]:
    """Find every immediate subdirectory of `scenarios_dir` that contains an
    inputs.yaml. Subdirectory name = scenario name."""
    out: list[tuple[str, Path]] = []
    for child in sorted(scenarios_dir.iterdir()):
        if not child.is_dir():
            continue
        yaml = child / "inputs.yaml"
        if yaml.exists():
            out.append((child.name, yaml))
    return out


def run_scenarios(scenarios_dir: Path) -> list[ScenarioResult]:
    """Load + run every scenario, return ScenarioResult per."""
    results: list[ScenarioResult] = []
    for name, path in load_scenarios(scenarios_dir):
        inputs = Inputs.from_yaml(path)
        result = run(inputs)
        bom = compute_bom(result)
        results.append(ScenarioResult(
            name=name, inputs_path=path, result=result, bom=bom,
        ))
    return results
