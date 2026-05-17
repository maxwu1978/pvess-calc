"""ESS disconnect / OCPD sizing (NEC 706.7, 706.15)."""
from __future__ import annotations

from dataclasses import dataclass

from ..schema import Inputs
from .ocpd import select_ocpd


@dataclass
class EssResult:
    ac_disconnect_min_a: float
    ac_disconnect_ocpd_a: int
    n_units: int
    total_kwh: float


def compute_ess(inputs: Inputs) -> EssResult:
    inv = inputs.inverter
    bat = inputs.battery

    n_inverters = inv.count(bat.quantity)
    total_ac = inv.ac_output_a * n_inverters

    # 706.15 / 690.9 style: OCPD ≥ 1.25 × continuous current.
    min_a = total_ac * 1.25
    ocpd = select_ocpd(min_a)

    return EssResult(
        ac_disconnect_min_a=min_a,
        ac_disconnect_ocpd_a=ocpd,
        n_units=bat.quantity,
        total_kwh=bat.total_kwh,
    )
