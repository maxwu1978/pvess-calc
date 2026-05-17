"""Bill-of-materials cost estimation from device-library prices.

Given a CalculationResult, this module looks up retail prices for every
catalog item used by the project and computes a high-level installed cost
estimate (parts only, no labor / permit / overhead).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..calc.engine import CalculationResult
from ..devices.batteries import BATTERY_PRICES_USD
from ..devices.inverters import INVERTER_PRICES_USD
from ..devices.modules import MODULE_PRICES_USD
from ..devices.optimizers import OPTIMIZER_PRICES_USD


# Approximate fixed line items for residential PV+ESS installs (parts only).
FIXED_BOM_USD: dict[str, float] = {
    "DC combiner box":            120,
    "Rapid shutdown device":      350,
    "AC disconnect (fused)":      180,
    "Sub-panel (200A)":           220,
    "Conduit + fittings (est.)":  300,
    "Wire (est., excl. mains)":   600,
    "Labels & placards kit":       60,
    "Hardware / consumables":     250,
}


@dataclass
class BomLine:
    label: str
    quantity: int | float
    unit_price_usd: float
    total_usd: float
    note: str = ""


@dataclass
class BomEstimate:
    lines: list[BomLine] = field(default_factory=list)
    subtotal_usd: float = 0.0
    note: str = "Parts only — excludes labor, permit, sales tax, contingency."


def _lookup(ref_or_model: str, table: dict[str, float], default: float) -> float:
    """Best-effort price lookup; falls back to the default if not in the table."""
    return table.get(ref_or_model, default)


def compute_bom(result: CalculationResult) -> BomEstimate:
    i = result.inputs
    lines: list[BomLine] = []

    # PV modules
    mod = i.pv_array.module
    mod_ref = _ref_guess(mod.brand, mod.model, MODULE_PRICES_USD)
    mod_price = _lookup(mod_ref, MODULE_PRICES_USD, default=150.0)
    lines.append(BomLine(
        label=f"PV module — {mod.brand} {mod.model} ({mod.power_w:.0f} W)",
        quantity=i.pv_array.modules,
        unit_price_usd=mod_price,
        total_usd=mod_price * i.pv_array.modules,
        note=f"ref guess: {mod_ref}",
    ))

    # Inverters
    n_inv = i.inverter.count(i.battery.quantity)
    inv_ref = _ref_guess(i.inverter.brand, i.inverter.model, INVERTER_PRICES_USD)
    inv_price = _lookup(inv_ref, INVERTER_PRICES_USD, default=3000.0)
    lines.append(BomLine(
        label=f"Inverter — {i.inverter.brand} {i.inverter.model}",
        quantity=n_inv,
        unit_price_usd=inv_price,
        total_usd=inv_price * n_inv,
        note=f"ref guess: {inv_ref}",
    ))

    # Module-level optimizer (Tigo / SolarEdge / etc.)
    if i.optimizer.brand:
        opt = i.optimizer
        opt_count = opt.effective_count(i.pv_array.modules, i.pv_array.strings)
        opt_ref = _ref_guess(opt.brand, opt.model, OPTIMIZER_PRICES_USD)
        opt_price = _lookup(opt_ref, OPTIMIZER_PRICES_USD, default=70.0)
        lines.append(BomLine(
            label=f"Optimizer — {opt.brand} {opt.model}",
            quantity=opt_count,
            unit_price_usd=opt_price,
            total_usd=opt_price * opt_count,
            note=f"ref guess: {opt_ref}",
        ))

    # Battery (skip if integrated with Powerwall-style inverter)
    if not i.inverter.per_unit:
        bat_ref = _ref_guess(i.battery.brand, i.battery.model, BATTERY_PRICES_USD)
        bat_price = _lookup(bat_ref, BATTERY_PRICES_USD, default=2500.0)
        lines.append(BomLine(
            label=f"Battery — {i.battery.brand} {i.battery.model}",
            quantity=i.battery.quantity,
            unit_price_usd=bat_price,
            total_usd=bat_price * i.battery.quantity,
            note=f"ref guess: {bat_ref}",
        ))

    # Fixed accessories
    for label, price in FIXED_BOM_USD.items():
        # Skip sub-panel line if no sub-panels in project
        if "Sub-panel" in label and not i.service.sub_panels:
            continue
        # Multiply sub-panel cost by actual count
        qty = len(i.service.sub_panels) if "Sub-panel" in label else 1
        lines.append(BomLine(
            label=label,
            quantity=qty,
            unit_price_usd=price,
            total_usd=price * qty,
        ))

    subtotal = sum(l.total_usd for l in lines)
    return BomEstimate(lines=lines, subtotal_usd=subtotal)


def _ref_guess(brand: str, model: str, table: dict[str, float]) -> str:
    """Heuristic: try to match a brand+model string to a known ref key."""
    needle = (brand + " " + model).lower().replace(" ", "_")
    needle = needle.replace("-", "_").replace(".", "")
    for ref in table:
        ref_norm = ref.replace("-", "_")
        if ref_norm in needle or needle.startswith(ref_norm.split("_")[0]):
            return ref
    return "unknown"
