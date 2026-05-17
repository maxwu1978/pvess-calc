# Add an AHJ profile

An AHJ profile is a yaml file that customises which permit sheets and
NEC labels appear in a project's package for a specific Authority Having
Jurisdiction. Use cases: California Title 24 amendments, Hawaii Rule 14H,
Texas Oncor TDU paperwork, etc.

## File location

```
src/pvess_calc/permit/ahj_profiles/<name>.yaml
```

Existing profiles: `austin_tx.yaml`, `phoenix_az.yaml`,
`california_generic.yaml`, `hawaii_generic.yaml`.

## File format

```yaml
# src/pvess_calc/permit/ahj_profiles/oncor_tx.yaml
name: oncor_tx
display_name: "Oncor Electric Delivery (TX)"
description: >
  TDU profile for Texas deregulated market. Oncor handles wires +
  interconnection; homeowner's REP handles energy contract.

# Which sheets in the permit package to emit. Codes match the keys in
# permit/sheet_registry.py (`SHEET_REGISTRY[].code`).
# Omitting a code skips that sheet for this AHJ.
sheets:
  - cover               # EE-0
  - three_line          # EE-1
  - grounding           # EE-2
  - panels              # EE-3
  - site_plan           # EE-4
  - attachment_plan     # PV-4
  - mounting_details    # PV-5
  - string_plan         # PV-6
  - compliance          # EE-5
  - general_notes       # PV-N
  - labels              # NEC labels grid

# Which NEC labels appear. Codes match `labels/specs.py`
# `LabelSpec.code` for each entry.
labels:
  - pv_dc_disconnect
  - pv_ac_disconnect
  - rapid_shutdown
  - power_sources_present
  - supply_side_tap         # 705.11 — only when project uses this method
  - ess_disconnect
  - pv_power_source         # 690.53 plain label
  - conduit_interval        # 690.31(D)

# Optional: AHJ-specific notes appended to PV-N general notes section.
extra_general_notes:
  - "Texas Public Utility Commission (PUCT) Rule 25.211 interconnection
     application must be filed via Oncor's distributed-generation portal
     prior to commissioning."
  - "TDU service inspection required before utility energization."

# Optional: utility-specific tariff fields surfaced in customer-summary.
default_export_tariff: 1to1_nem    # Oncor still does 1:1 net metering
```

## Registration

The profile yaml is auto-discovered by `permit/ahj_profile_loader.py`
on import — no separate registration step. Confirm by listing:

```python
from pvess_calc.permit.ahj_profile_loader import list_ahj_profiles
print(list_ahj_profiles())
# ['austin_tx', 'california_generic', 'hawaii_generic', 'phoenix_az', 'oncor_tx']
```

## Use the new profile

```bash
pvess permit --ahj oncor_tx projects/<id>/
```

## Test it

Add a doctor smoke test (`tests/test_doctor.py`):

```python
def test_oncor_tx_ahj_profile_emits_known_sheet_codes():
    from pvess_calc.permit.ahj_profile_loader import load_ahj_profile
    from pvess_calc.permit.sheet_registry import codes
    profile = load_ahj_profile("oncor_tx")
    registered = set(codes())
    assert all(code in registered for code in profile.sheets), (
        f"oncor_tx profile references unknown sheet codes: "
        f"{set(profile.sheets) - registered}"
    )
```

The existing doctor check `ahj_profile.*` will automatically pick up the
new profile and validate it on the next `pvess doctor` run.

## Common gotchas

- **Sheet codes are NOT display codes.** `cover` (code) → `EE-0` (display).
  See `permit/sheet_registry.py:SHEET_REGISTRY` for the mapping.
- **Label codes** in `labels/specs.py` are kebab-case; match exactly.
- **`extra_general_notes` runs through the same word-wrap** as PV-N
  default notes — keep each item under ~80 chars per line for readability.
- The AHJ profile **does NOT** affect NEC calculations. NEC math is per
  `inputs.project.nec_edition`. The profile only filters output artifacts.
