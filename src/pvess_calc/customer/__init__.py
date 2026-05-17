"""K.4 — customer-friendly output layer.

Turns a `CalculationResult` (engineer-level NEC math) into a one-pager
PDF a homeowner can show to their spouse / banker / HOA:

  * system overview (modules / battery kWh / inverter)
  * annual production + monthly bill savings + payback
  * backup runtime for critical loads
  * a 12-month production vs. usage chart

The layer is deliberately additive: every section degrades gracefully
when its inputs are missing. A yaml with only Phase 0 fields still
renders a valid (shorter) PDF.
"""
from .economics import (
    EconomicsResult,
    compute_economics,
    DEFAULT_USA_AVG_RATE_USD_PER_KWH,
)
from .backup import BackupResult, compute_backup


__all__ = [
    "EconomicsResult",
    "compute_economics",
    "DEFAULT_USA_AVG_RATE_USD_PER_KWH",
    "BackupResult",
    "compute_backup",
]
