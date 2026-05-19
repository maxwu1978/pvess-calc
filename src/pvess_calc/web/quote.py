"""Web-facing quote helpers.

These functions turn the engineering BOM/economics data into a sales-facing
view model. They do not change NEC calculations or the underlying cost engine;
the web app simply adds categorization and standardized quote tiers.
"""
from __future__ import annotations

from typing import Any

from ..calc.engine import CalculationResult
from ..compare.bom import BomEstimate
from ..customer.backup import compute_backup
from ..customer.economics import compute_economics
from ..devices.batteries import get_battery
from ..schema import Battery, Inputs


WEB_QUOTE_TIERS: tuple[tuple[str, str | None, int], ...] = (
    ("PV-only", None, 0),
    ("Base backup", "inhouse_16kwh_hv", 1),
    ("Large backup", "growatt_apx_20kwh", 1),
)


def categorize_bom(bom: BomEstimate) -> list[dict[str, Any]]:
    groups: dict[str, list] = {
        "Major equipment": [],
        "Electrical BOS": [],
        "Racking & mounting": [],
    }
    for line in bom.lines:
        groups[_category_for(line.label)].append(line)

    categories = []
    for name, lines in groups.items():
        total = sum(line.total_usd for line in lines)
        categories.append({
            "name": name,
            "total_usd": round(total, 2),
            "lines": [
                {
                    "label": line.label,
                    "quantity": line.quantity,
                    "unit_price_usd": round(line.unit_price_usd, 2),
                    "total_usd": round(line.total_usd, 2),
                    "note": line.note,
                }
                for line in lines
            ],
        })
    return categories


def installed_breakdown(
    categories: list[dict[str, Any]],
    *,
    installed_cost_usd: float,
) -> list[dict[str, Any]]:
    parts_total = sum(cat["total_usd"] for cat in categories)
    soft_costs = max(installed_cost_usd - parts_total, 0.0)
    return [
        *categories,
        {
            "name": "Labor, permitting & soft costs",
            "total_usd": round(soft_costs, 2),
            "lines": [],
        },
    ]


def quote_tiers_for_result(result: CalculationResult) -> list[dict[str, Any]]:
    tiers = []
    selected_key = _selected_tier_key(result.inputs)
    for name, battery_ref, qty in WEB_QUOTE_TIERS:
        tier_inputs = _with_battery_option(result.inputs, battery_ref, qty)
        econ = compute_economics(tier_inputs)
        backup = compute_backup(tier_inputs)
        key = battery_ref or "none"
        tiers.append({
            "key": key,
            "name": name,
            "is_selected": key == selected_key,
            "battery_kwh_total": round(tier_inputs.battery.total_kwh, 2),
            "installed_cost_usd": round(econ.installed_cost_usd, 2),
            "cost_after_itc_usd": round(econ.cost_after_itc_usd, 2),
            "monthly_savings_usd": round(econ.monthly_bill_savings_usd, 2),
            "payback_after_itc_years": _round_optional(econ.payback_after_itc_years),
            "backup_summary": _backup_summary(tier_inputs.battery.total_kwh, backup),
        })
    return tiers


def _category_for(label: str) -> str:
    lower = label.lower()
    if any(token in lower for token in ("pv module", "inverter", "optimizer", "battery")):
        return "Major equipment"
    if any(token in lower for token in ("hardware", "racking", "mount")):
        return "Racking & mounting"
    return "Electrical BOS"


def _with_battery_option(inputs: Inputs, battery_ref: str | None, qty: int) -> Inputs:
    copied = inputs.model_copy(deep=True)
    if battery_ref is None or qty <= 0:
        copied.battery = Battery(
            brand="None",
            model="PV-only",
            quantity=0,
            nominal_voltage=max(inputs.battery.nominal_voltage, 1.0),
            capacity_kwh_each=0.0,
        )
    else:
        spec = get_battery(battery_ref)
        copied.battery = spec.model_copy(update={"quantity": qty})

    if copied.project.installer_cost_overrides is not None:
        overrides = copied.project.installer_cost_overrides
        copied.project.installer_cost_overrides = overrides.model_copy(update={
            "battery_ref": battery_ref,
            "battery_cost_usd_total": None,
        })
    return copied


def _selected_tier_key(inputs: Inputs) -> str:
    if not inputs.battery.installed:
        return "none"
    for _name, battery_ref, qty in WEB_QUOTE_TIERS:
        if battery_ref is None or qty <= 0:
            continue
        spec = get_battery(battery_ref)
        if (
            inputs.battery.brand == spec.brand
            and inputs.battery.model == spec.model
            and inputs.battery.quantity == qty
        ):
            return battery_ref
    return "custom"


def _backup_summary(battery_kwh: float, backup) -> str:
    if battery_kwh <= 0:
        return "none (grid-tied)"
    return (
        f"~{backup.backup_hours_loads_only:.0f} hr essentials · "
        f"~{backup.backup_hours_summer:.0f} hr w/ AC"
    )


def _round_optional(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 2)
