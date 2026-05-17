# Doctor checks reference

The doctor runs 28 structural self-checks. Every check has a name, an
implementation function in `src/pvess_calc/doctor.py`, and a
regression-bait test in `tests/test_doctor.py` that synthesises the
broken state and asserts the check FAILs.

## Loadability

| Check | Function | Notes |
|---|---|---|
| `inputs_load` | `_check_inputs_load` | `inputs.yaml` parses cleanly via pydantic |
| `calc_engine` | `_check_calc_engine` | Engine runs without exception |

## Registry consistency

| Check | Function | Notes |
|---|---|---|
| `ahj_profile.austin_tx` | `_check_ahj_profile_codes` | austin AHJ profile references real sheet codes |
| `ahj_profile.california_generic` | same | |
| `ahj_profile.hawaii_generic` | same | |
| `ahj_profile.phoenix_az` | same | |
| `label_set.austin_tx` | `_check_label_set_codes` | austin AHJ profile references real label codes |
| `label_set.california_generic` | same | |
| `label_set.hawaii_generic` | same | |
| `label_set.phoenix_az` | same | |

## Anti-patterns

| Check | Function | Notes |
|---|---|---|
| `no_truncation_slices` | `_check_no_fixed_width_truncation_markers` | No `text[:N]` slices in render code |

## K.2.5 — schema feasibility

| Check | Function | What it catches |
|---|---|---|
| `subpanel_slots_sufficient` | `_check_subpanel_slots_sufficient` | New PV/ESS breakers fit panel slots (panel swap required otherwise) |

## K.2.6b — ESS install

| Check | Function | What it catches |
|---|---|---|
| `ess_install_compliant` | `_check_ess_install_compliant` | IRC R328.5 3-ft setbacks + 40 kWh indoor ceiling |

## K.5 — grounding

| Check | Function | What it catches |
|---|---|---|
| `grounding_electrode_system_compliant` | `_check_grounding_electrode_system_compliant` | NEC 250.66 GEC sizing + 250.50 electrode count + 250.24 main bonding jumper |

## K.2.6c–K.2.8 — roof layout

| Check | Function | What it catches |
|---|---|---|
| `roof_usable_area_sufficient` | `_check_roof_usable_area_sufficient` | Module count × 22 sqft ≤ usable polygon area (after setback + obstructions) |

## K.3 / K.4 — lookup + customer summary

| Check | Function | What it catches |
|---|---|---|
| `lookup_offline_works_without_keys` | `_check_lookup_offline_works_without_keys` | Offline lookup chain returns ≥5 fields without API keys |
| `customer_summary_renderable` | `_check_customer_summary_renderable` | K.4 PDF renders without crash (worst-case path: no lookup, no monthly_kwh) |
| `customer_design_tokens_respected` | `_check_customer_design_tokens_respected` | Customer PDF uses only the 4-tier font sizes from `design_tokens.py` |

## K.7 final — invariant locks

| Check | Function | What it catches |
|---|---|---|
| `nec_edition_artifacts_consistent` | `_check_nec_edition_artifacts_consistent` | report.md / permit PDF carry the NEC edition declared in inputs.yaml |
| `export_tariff_matches_state` | `_check_export_tariff_matches_state` | CA → ca_nem3, HI → hi_self_consumption mandatory |
| `rsd_label_substitution_wired` | `_check_rsd_label_substitution_wired` | RSD label body has `{{RSD_BOUNDARY_V}}` + build_substitutions populates it |
| `compare_pdf_renderable` | `_check_compare_pdf_renderable` | `pvess compare` emits valid PDF |

## Permit package consistency

| Check | Function | What it catches |
|---|---|---|
| `cover_index_matches_pipeline` | `_check_cover_lists_all_sheets` | EE-0 SHEET INDEX = actual emitted page order |
| `permit_emits_registry` | `_check_permit_emits_registry` | ≥ N pages emitted (one per registered sheet) |
| `pdf_text_searchable` | `_check_pdf_is_text_searchable` | Permit PDF text-extractable (not image-only) |

## DXF rendering

| Check | Function | What it catches |
|---|---|---|
| `dxf_text_no_overflow` | `_check_dxf_text_no_overflow` | EE-1/EE-2 SCHEDULE/TITLE_BLOCK/NOTES text fits its container width |
| `dxf_no_text_overlap` | `_check_dxf_no_text_overlap` | TEXT entity bboxes don't overlap > 25% |

## Site checklist coverage

| Check | Function | What it catches |
|---|---|---|
| `site_checklist_covers_schema` | `_check_site_checklist_covers_schema` | Every `yaml_path` on the site-checklist PDF resolves to a real `Inputs` field |

---

## Status semantics

| Status | Doctor exit |
|---|---|
| `PASS` | OK — no action |
| `FAIL` | doctor exits non-zero; CI / pipeline blocks |
| (`WARN`) | Reported inside `PASS` detail text — no exit-code change. Used when data is missing but not invalid (e.g. ESS install location set to `unknown`) |

## What doctor does NOT cover

- Text vs **wire / icon geometry** collisions in DXF (requires visual review)
- NEC interpretation correctness (the engine outputs correct math for
  the rules it implements; doctor doesn't verify the *interpretation* of
  those rules)
- AHJ-specific paperwork beyond profile-level sheet/label filtering
- Real shading / sky-view factor for PV production

For those gaps, the `pvess-visual-polish` skill (`.claude/skills/`)
gives a manual review checklist.
