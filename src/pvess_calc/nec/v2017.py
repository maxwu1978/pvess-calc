"""NEC 2017 rule set.

Key differences from 2020 / 2023:

- **690.12 Rapid Shutdown**: 2017 cycle requires array boundary voltage
  ≤ **80 V** (not 30 V like 2020+). Threshold applies within 1 ft outside
  the array.
- **705.12(B)(3)(1) sum rule** still present (deleted only in 2020).
- **690.31(C)(1)** PV system DC conductors not allowed inside dwelling
  unless metal raceway / metal-clad cable.
- **705.12(D)(2)** previous 120% allowance is the same.

Numeric multipliers and basic factors are unchanged between cycles.
"""
from __future__ import annotations

EDITION = "2017"

BUSBAR_MULTIPLIER_120_RULE = 1.20
PV_SOURCE_CURRENT_FACTOR = 1.25
PV_CONDUCTOR_AMPACITY_FACTOR = 1.25
PV_OCPD_FACTOR = 1.25
PV_MAX_SYSTEM_VOLTAGE_DWELLING = 600.0

# 2017 still allowed sum_rule (removed in 2020).
DISALLOWED_INTERCONNECT_METHODS: set[str] = set()

# 2017-specific: array boundary RSD threshold (vs 30 V in 2020+).
RSD_BOUNDARY_VOLTAGE_LIMIT = 80.0
