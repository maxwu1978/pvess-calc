# Add a NEC edition

The tool currently ships rules for **NEC 2017 / 2020 / 2023**, all real
implementations (not aliases). When NEC 2026 publishes (or your AHJ
needs a half-cycle interpretation), here's how to add it.

## File locations

```
src/pvess_calc/nec/v2026.py          # rule constants — new file
src/pvess_calc/nec/__init__.py       # dispatcher — add a branch
src/pvess_calc/schema.py             # Literal type — add "2026"
```

## Step 1: New rules module

Look at `nec/v2023.py` for the baseline shape. A typical new edition only
overrides what actually changed vs the prior cycle:

```python
# src/pvess_calc/nec/v2026.py
"""NEC 2026 rule set.

Changes from 2023 (relevant to this tool):
  - 705.12(B)(3)(N)  — <changes go here>
  - 690.12          — <RSD changes go here>
"""
from __future__ import annotations

EDITION = "2026"

# Most constants unchanged 2023 → 2026.
BUSBAR_MULTIPLIER_120_RULE = 1.20
PV_SOURCE_CURRENT_FACTOR = 1.25
PV_CONDUCTOR_AMPACITY_FACTOR = 1.25
PV_OCPD_FACTOR = 1.25
PV_MAX_SYSTEM_VOLTAGE_DWELLING = 600.0

# NEC 2026: same as 2023 (sum_rule retained, RSD = 30 V).
DISALLOWED_INTERCONNECT_METHODS: set[str] = set()
RSD_BOUNDARY_VOLTAGE_LIMIT = 30.0

# Add new constants for actual 2026 deltas here.
```

## Step 2: Wire dispatcher

```python
# src/pvess_calc/nec/__init__.py
from . import v2017, v2020, v2023, v2026

def get_rules(edition: str):
    edition = (edition or "2023").strip()
    if edition == "2026":
        return v2026
    if edition == "2023":
        return v2023
    if edition == "2020":
        return v2020
    if edition == "2017":
        return v2017
    return v2023    # safest default = latest stable
```

## Step 3: Update the schema Literal

```python
# src/pvess_calc/schema.py
class ProjectMeta(BaseModel):
    id: str
    name: str
    location: str
    ahj: str
    nec_edition: Literal["2026", "2023", "2020", "2017"] = "2023"
    #            ^^^^^ add here
```

This is the only schema-level change. Every consumer (interconnect.py,
labels, qet/inject) already reads via `get_rules(edition)` — they pick
up the new module automatically.

## Step 4: Add tests

```python
# tests/test_phase_hi.py (or a new test_nec_2026.py)

def test_nec_2026_module_loads():
    rules = get_rules("2026")
    assert rules.EDITION == "2026"
    # 2026 retains the changes you added:
    assert rules.RSD_BOUNDARY_VOLTAGE_LIMIT == 30.0
    assert "sum_rule" not in rules.DISALLOWED_INTERCONNECT_METHODS
```

If 2026 introduces an interconnect-method change (e.g. a new method),
add an integration test mirroring
`test_nec_2017_allows_sum_rule_2020_does_not`.

## Step 5: Update lookup recommendations

`lookup/data/nec_adoption.json` lists per-state defaults:

```json
{
  "AZ": {"edition": "2017", "note": "..."},
  "CA": {"edition": "2023", "note": "..."},
  ...
}
```

When AZ adopts 2026, edit the entry. The state-level default flows into
`pvess init --address` pre-fill.

## Step 6: Document the RSD label voltage difference

If 2026 changes `RSD_BOUNDARY_VOLTAGE_LIMIT`, that constant flows
automatically through to `{{RSD_BOUNDARY_V}}` in the labels PDF —
nothing to edit there. The doctor's `rsd_label_substitution_wired`
check will exercise the new value in its parametric test.

## Verification

```bash
pytest -q tests/test_phase_hi.py        # NEC version tests
pytest -q tests/test_interconnect.py    # interconnect dispatch
pvess-doctor projects/<id>/             # full structural check
```

Doctor should still report 28/28 PASS, and now any project with
`nec_edition: "2026"` runs the new rules.
