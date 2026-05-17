"""NEC 2020 rule set.

Differences from 2023 that affect this tool:

- **705.12(B)(3)(1) sum rule REMOVED in 2020** — the 2017 sum rule was deleted
  in the 2020 revision; only 120% rule (B)(3)(2) and supply-side tap remain
  as practical paths for residential. We mark sum_rule as unavailable so the
  recommendation engine won't pick it.
- **690.12 Rapid Shutdown threshold tightening** — 2017 allowed 80V within 1ft
  of the array boundary; 2020 dropped it to 30V. Same as 2023.

The numeric constants (busbar 120% multiplier, current factors, max system
voltage for dwellings) are unchanged between 2017/2020/2023.
"""
from __future__ import annotations

EDITION = "2020"

BUSBAR_MULTIPLIER_120_RULE = 1.20
PV_SOURCE_CURRENT_FACTOR = 1.25
PV_CONDUCTOR_AMPACITY_FACTOR = 1.25
PV_OCPD_FACTOR = 1.25
PV_MAX_SYSTEM_VOLTAGE_DWELLING = 600.0

# Methods explicitly NOT supported under this edition. The interconnect engine
# will mark these "N/A · removed in NEC 2020" instead of evaluating them.
DISALLOWED_INTERCONNECT_METHODS: set[str] = {"sum_rule"}

# 690.12(B)(2): array boundary RSD threshold within 1 ft of array
# boundary, 30 s after initiation. Tightened from 80 V in NEC 2017.
RSD_BOUNDARY_VOLTAGE_LIMIT = 30.0
