# Add an AHJ profile

An AHJ profile is a yaml file that customises which permit sheets and
NEC labels appear in a project's package for a specific Authority Having
Jurisdiction. Use cases: California Title 24 amendments, Hawaii Rule 14H,
Texas Oncor TDU paperwork, etc.

## File location

```
src/pvess_calc/ahj/profiles/<name>.yaml
```

Existing profiles: `austin_tx.yaml`, `phoenix_az.yaml`,
`california_generic.yaml`, `hawaii_generic.yaml`.

## File format

```yaml
# src/pvess_calc/ahj/profiles/oncor_tx.yaml
name: "Oncor Electric Delivery (TX)"
region: "Texas deregulated market"

# Which sheets in the permit package to emit. Codes match
# permit/sheet_registry.py. Omitting a code skips that sheet for this AHJ.
required_sheets:
  - cover
  - ee-1
  - ee-2
  - one-line
  - ee-3
  - ee-4
  - ee-4a
  - ee-5
  - pv-4
  - pv-5
  - pv-6
  - notes
  - labels

# Which NEC label clauses appear. Values match labels/specs.py nec_clause.
label_set:
  - 690.13(B)
  - "690.53"
  - 690.56(C)
  - "705.11"
  - "706.7"

inspector_checklist:
  - "PUCT / TDU interconnection application complete"
  - "Utility service inspection complete before energization"

form_blanks:
  - "Oncor distributed-generation interconnection form"

# Optional H.4: AHJ-specific SPD rules. These can only make the base NEC
# result stricter; they cannot relax NEC 230.67 when the NEC edition already
# requires a dwelling-service SPD.
spd_policy:
  service_spd_required: true
  dc_spd_required: false
  ess_spd_required: false
  spd_type: "Type 2"
  required_locations:
    - "Main Service Panel (MSP)"
  recommended_locations: []
  note: "Local amendment requires service SPD verification."

notes: >
  TDU profile for Texas deregulated market. Oncor handles wires +
  interconnection; homeowner's REP handles energy contract.
```

## Registration

The profile yaml is auto-discovered by `permit/ahj_profile_loader.py`
on import — no separate registration step. Confirm by listing:

```python
from pvess_calc.ahj.profile import list_ahj_profiles
print(list_ahj_profiles())
# ['austin_tx', 'california_generic', 'hawaii_generic', 'phoenix_az', 'oncor_tx']
```

## Use the new profile

```bash
pvess permit --ahj oncor_tx projects/<id>/
```

You can also set `project.ahj_profile: "oncor_tx"` in `inputs.yaml` when
the calculation/report should pick up the profile outside the permit command.

## Test it

Add a doctor smoke test (`tests/test_doctor.py`):

```python
def test_oncor_tx_ahj_profile_emits_known_sheet_codes():
    from pvess_calc.ahj.profile import get_ahj_profile
    from pvess_calc.permit.sheet_registry import codes
    profile = get_ahj_profile("oncor_tx")
    registered = set(codes())
    assert all(code in registered for code in profile.required_sheets), (
        f"oncor_tx profile references unknown sheet codes: "
        f"{set(profile.required_sheets) - registered}"
    )
```

The existing doctor check `ahj_profile.*` will automatically pick up the
new profile and validate it on the next `pvess doctor` run.

## Common gotchas

- **Sheet codes are NOT display codes.** `cover` (code) → `EE-0` (display).
  See `permit/sheet_registry.py:SHEET_REGISTRY` for the mapping.
- **Label clauses** in `labels/specs.py` use NEC clause strings such as
  `690.13(B)`; match exactly.
- `spd_policy` can only make the base NEC result stricter. Do not use it
  to remove a service SPD required by the selected NEC edition.
- Most AHJ profile fields filter output artifacts. `spd_policy` is the
  exception: it feeds Phase H surge-protection calculations and EE-5.
