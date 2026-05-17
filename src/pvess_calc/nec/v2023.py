"""NEC 2023 rule set.

Sibling modules (v2020.py) implement older editions; the engine dispatches
based on `inputs.project.nec_edition`.
"""
from __future__ import annotations

EDITION = "2023"

# 705.12(B)(3)(2) busbar 120% rule multiplier.
BUSBAR_MULTIPLIER_120_RULE = 1.20

# 690.8(A)(1): PV source circuit current factor.
PV_SOURCE_CURRENT_FACTOR = 1.25

# 690.8(B)(1): conductor ampacity factor on top of 690.8(A).
PV_CONDUCTOR_AMPACITY_FACTOR = 1.25

# 690.9(B): OCPD factor on top of 690.8(A).
PV_OCPD_FACTOR = 1.25

# 690.7: maximum system voltage for one- and two-family dwellings.
PV_MAX_SYSTEM_VOLTAGE_DWELLING = 600.0

# 2023 retains both 120% rule and sum rule (705.12(B)(3)(1)+(2)).
DISALLOWED_INTERCONNECT_METHODS: set[str] = set()

# 690.12(B)(2): array boundary RSD threshold within 1 ft of array
# boundary, 30 s after initiation. Same as 2020.
RSD_BOUNDARY_VOLTAGE_LIMIT = 30.0
