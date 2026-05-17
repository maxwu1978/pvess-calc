# Verify

The verify phase is the structural self-audit before sending a permit
package out the door. Two subcommands.

## `pvess doctor` — 28 structural checks

```bash
pvess doctor projects/<id>/
pvess doctor --quiet projects/<id>/      # only print failures
```

Walks 28 invariants. Exits non-zero on any FAIL — wire into CI / pipeline
so broken packages never ship.

### Check inventory

| Group | Check | What it catches |
|---|---|---|
| **Loadability** | `inputs_load` | `inputs.yaml` parses cleanly |
|  | `calc_engine` | Engine runs without exception |
| **Registry consistency** | `ahj_profile.austin_tx`, `.california_generic`, `.hawaii_generic`, `.phoenix_az` | Each AHJ profile's sheet/label codes are registered |
|  | `label_set.*` (×4) | Each AHJ's label set references real LabelSpec entries |
| **Anti-patterns** | `no_truncation_slices` | No `text[:N]` slices in render code (forces `fit()` / `fit_dxf()`) |
| **K.2.5 schema** | `subpanel_slots_sufficient` | New PV/ESS breakers fit available slots |
| **K.2.6b** | `ess_install_compliant` | IRC R328 setbacks + 40 kWh ceiling |
| **K.5** | `grounding_electrode_system_compliant` | GEC sizing vs NEC 250.66 + NEC 250.50 electrode count + 250.24 bonding |
| **K.2.6c–K.2.8** | `roof_usable_area_sufficient` | Module count × footprint ≤ usable polygon area |
| **K.3 / K.4** | `lookup_offline_works_without_keys` | Offline lookup chain returns ≥5 fields without API keys |
|  | `customer_summary_renderable` | K.4 PDF renders without crash |
|  | `customer_design_tokens_respected` | PDF font sizes in 4-tier whitelist |
| **K.7 final** | `nec_edition_artifacts_consistent` | report.md / permit PDF carry NEC edition from inputs.yaml |
|  | `export_tariff_matches_state` | CA → ca_nem3, HI → hi_self_consumption mandatory |
|  | `rsd_label_substitution_wired` | `{{RSD_BOUNDARY_V}}` placeholder + build_substitutions wired |
|  | `compare_pdf_renderable` | `pvess compare` emits valid PDF |
| **Permit package** | `cover_index_matches_pipeline` | EE-0 SHEET INDEX = actual emitted pages |
|  | `permit_emits_registry` | ≥ N pages emitted (one per registered sheet) |
|  | `pdf_text_searchable` | Permit PDF is text-extractable (not image-only) |
| **DXF** | `dxf_text_no_overflow` | EE-1/EE-2 schedule text fits column widths |
|  | `dxf_no_text_overlap` | TEXT bboxes don't overlap > 25% |
| **Site checklist** | `site_checklist_covers_schema` | Every yaml_path on the checklist resolves to a real Inputs field |

### Sample run

```bash
$ pvess doctor projects/002-phoenix-25kw
  PASS  inputs_load
  PASS  calc_engine
  PASS  ahj_profile.austin_tx
  …
  PASS  compare_pdf_renderable                compare PDF rendered (3,188 B)
  …
  ✓ all 28 check(s) passed
```

### Common failures + fixes

| FAIL | Cause | Fix |
|---|---|---|
| `subpanel_slots_sufficient` | New PV/ESS breakers > free slots | Hand-edit `service.sub_panels[i].available_slots` / `used_slots` (or do panel swap) |
| `ess_install_compliant` | Indoor + setback < 3 ft | Move ESS or set `battery.distance_to_doorway_ft ≥ 3` |
| `grounding_electrode_system_compliant` | Existing #8 AWG GEC on 200 A service | Hand-edit yaml or upsize GEC at install |
| `export_tariff_matches_state` | CA project still `1to1_nem` | Set `loads.export_tariff_model: "ca_nem3"` |
| `nec_edition_artifacts_consistent` | Stale report.md from old NEC edition | Re-run `pvess calc` |
| `roof_usable_area_sufficient` | `module_count × 22 sqft > usable area` | Increase face width/height or split modules across faces |

## `pvess symbols` — symbol library swatch

```bash
pvess symbols                           # → swatch.pdf
pvess symbols --dxf-only                # → swatch.dxf (DXF inspection)
```

Renders every icon in `dxf/symbols.py` on a single page. Useful when
adding new equipment types — verify the new symbol's stroke weight,
proportions, and ATTDEF positions are consistent with the existing
library before wiring it into the renderer.

## Doctor in CI

The pipeline command surfaces doctor's exit code:

```bash
pvess pipeline submit projects/<id>/
```

Fails the pipeline on any FAIL. Suitable for:

```yaml
# GitHub Actions example
- run: pvess pipeline submit projects/${{ matrix.project }}/
```

## Adding new doctor checks

The pattern (mirrors existing checks in `src/pvess_calc/doctor.py`):

```python
def _check_my_new_invariant(calc_result):
    name = "my_new_invariant"
    if condition_broken(calc_result):
        return [CheckResult(name, "FAIL", "specific actionable detail")]
    return [CheckResult(name, "PASS", "what worked")]


# In run_doctor():
results.extend(_check_my_new_invariant(calc_result))
```

Always include a **regression-bait test** that synthesises the broken
state and asserts the check FAILs. See `tests/test_doctor.py` for
examples (`test_export_tariff_matches_state_fails_ca_with_1to1`,
`test_subpanel_slots_sufficient_catches_full_msp`, etc.).
