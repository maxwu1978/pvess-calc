"""DC optimizer / MLPE datasheet registry."""
from __future__ import annotations

from ..schema import Optimizer

OPTIMIZERS: dict[str, dict] = {
    "tigo_ts4_a_o": dict(
        brand="Tigo", model="TS4-A-O",
        type="pass_through",
        count="per_module",
        max_input_v=80.0,
        max_output_a=15.0,
    ),
    "tigo_ts4_a_f": dict(
        brand="Tigo", model="TS4-A-F (rapid shutdown only)",
        type="pass_through",
        count="per_module",
        max_input_v=80.0,
        max_output_a=15.0,
    ),
    "solaredge_p505": dict(
        brand="SolarEdge", model="P505",
        type="mppt",
        count="per_module",
        max_input_v=83.0,
        max_output_a=10.1,
    ),
}

OPTIMIZER_PRICES_USD: dict[str, float] = {
    "tigo_ts4_a_o":     65,
    "tigo_ts4_a_f":     35,
    "solaredge_p505":   80,
}


def get_optimizer(ref: str) -> Optimizer:
    if ref not in OPTIMIZERS:
        raise KeyError(
            f"Unknown optimizer ref {ref!r}. "
            f"Available: {sorted(OPTIMIZERS.keys())}"
        )
    return Optimizer(**OPTIMIZERS[ref])
