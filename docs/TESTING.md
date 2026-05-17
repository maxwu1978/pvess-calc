# Testing Standards

This file is the hard contract for what every new feature must add. The 120-case
pytest suite is the floor, not the ceiling — `pytest -q` going green is *necessary
but not sufficient* for landing a change. The list below is what we discovered
the suite was *not* catching when Phase J shipped (cover-sheet index was stale;
EE-2/EE-4 had visual collisions; `desc[:30]` silently truncated MSP description).

## 1. Coverage by feature kind

| Feature kind | Required tests | Example file |
|---|---|---|
| New NEC calculation | One unit test per branch + alignment with a published worked example (Mike Holt / IAEI / NEC handbook) | `tests/test_phase_d.py::test_voltage_drop_ac_branch` |
| New schema field | Default-value test (old yaml still loads) + round-trip test | `tests/test_phase_d.py::test_device_ref_expansion` |
| New CLI subcommand | At least one end-to-end run on Phoenix fixture asserting exit 0 + expected output file appears | `tests/test_end_to_end.py` |
| New sheet (any code: EE-*/PV-*) | **All five** of the items in §3 below | `tests/test_permit_ahj.py` |
| New AHJ profile YAML | Loads via `AhjProfile.load()` + required_sheets is a subset of registered Sheet Registry codes | `tests/test_permit_ahj.py::test_ahj_profile_filter` |
| Reportlab / matplotlib output | Page-count assert + at least one `pdftotext` content assert (so all-image regressions are caught) | `tests/test_labels.py` |
| QET XML generator | Schema version, terminal x-inset (4px), `sequentialNumbers` presence, element sort order | `tests/test_qet_elements.py` |

## 2. Bugs that escaped before — never again

Each row below is a real Phase J regression with the assertion that would have
caught it. New code that opens a similar surface must add the equivalent assert.

| Bug class | Where it landed | Assertion to add |
|---|---|---|
| Cover sheet index hardcoded, didn't list new sheets | `cover.py` | `set(cover_index) == set(builder.emitted_sheet_codes)` |
| Title text collides with drawing area | EE-2 / EE-4 | Bounding-box overlap check between title and lot/diagram rect (pvess-doctor §3) |
| Fixed-width string slice → "Main Service Panel + utility m" | site_plan.py | Reject `desc[:N]` patterns; require `len(text) ≤ N` instead and assert it in test |
| Sheet added to builder but missing from AHJ profile required_sheets | structural.py | `for code in SHEET_REGISTRY: assert code in default_ahj.required_sheets or marked optional` |
| pydantic v2 deprecation `self.model_fields` → `type(self).model_fields` | schema.py | Run pytest with `-W error::DeprecationWarning` periodically |

## 3. The "new sheet" checklist

Adding a sheet (EE-*, PV-*, or otherwise) requires touching all five touch points
in the same PR. The Sheet Registry (see DESIGN.md §2) makes this mechanical, but
the asserts still belong in tests:

1. **Register** the code in `pvess_calc.permit.sheet_registry.SHEET_REGISTRY`
2. **Cover index** test: `tests/test_permit_ahj.py` asserts the new code appears
   in the cover-sheet rendered text (pdftotext search)
3. **AHJ profile coverage**: every YAML in `src/pvess_calc/ahj/profiles/` either
   lists the new code in `required_sheets` or the loader test fails
4. **Builder page-count** assertion incremented in `test_permit_ahj.py`
5. **pvess-doctor** auto-checks the Sheet Registry contract — see DESIGN.md §2.
   No special-case logic; if the registry contains it, the doctor checks it.

## 4. Fixture & golden policy

- Phoenix project (`projects/002-phoenix-25kw/`) is the canonical end-to-end
  fixture. Every CLI must run cleanly on it.
- Smith Residence (in `tests/fixtures/`) is the canonical interconnect edge
  case (sum_rule FAIL + 120%_rule FAIL → supply_side_tap selected).
- Golden snapshots live in `tests/fixtures/golden_*`. Regenerate with
  `UPDATE_GOLDEN=1 pytest tests/<file>::<test>` — the env-var gate is mandatory
  so accidental overwrites can't sneak in.

## 5. What we *don't* test (and why)

These are conscious omissions, not gaps:

- **Pixel-perfect visual regression** of generated PNG/PDF. Reportlab and
  matplotlib backend updates would churn the goldens constantly. We rely on
  pvess-doctor's structural checks + manual visual review on Phoenix.
- **Round-trip QET → DXF → ACADE**. Not in scope until Phase 2.
- **Live AHJ portal submission**. Out of scope forever — this tool produces the
  submittal package, the engineer/installer submits.

## 6. Running tests

```bash
.venv/bin/pytest -q                 # 6-7 sec, all 135 cases
.venv/bin/pytest tests/test_phase_d.py -v   # narrow
.venv/bin/pytest -W error::DeprecationWarning  # surface library deprecations
```

CI is not yet wired. Manual contract: `pytest -q` green + `pvess-doctor
projects/002-phoenix-25kw/` green before any commit that touches `permit/`,
`dxf/`, or `qet/`.

## 7. Positive-guard vs regression-bait

Two testing patterns for the same doctor check; pick the one that fits
what you're guarding against.

### Regression-bait

Reverts the fix in-test, verifies the doctor STILL flags the original
bug class. Useful when the bug is a *recurring class* (e.g.
text-vs-container overflow) and you want a test that fails the moment
someone removes the check or breaks its logic.

Example: `test_unknown_sheet_code_in_ahj_profile_is_caught` — monkey-
patches an unknown sheet code into an AHJ profile, asserts doctor
catches it.

### Positive-guard

Renders the actual artifact under "worst-case" conditions (e.g.
fit_dxf disabled), verifies the doctor STILL PASSES. Useful when
the fix is *in the data, not the check* — the strings/values are
designed to fit by construction, and you want to prevent a future
maintainer from re-introducing a bad value that fit_dxf would
silently mask.

Example: `test_grounding_schedule_rows_fit_without_fit_dxf` — monkey-
patches `fit_dxf` to identity, asserts schedule rows still fit. If
someone adds a long RUN description, this test fails immediately
rather than letting fit_dxf chop it with ellipses.

### Choosing between them

| Situation | Pattern |
|---|---|
| Check logic could regress (someone deletes the check) | Regression-bait |
| Data could regress (someone adds a long string) | Positive-guard |
| Both could regress | One of each — they're complementary |

When a fix is "shorten the strings so they fit by design" (the
2026-05-14 schedule rework), positive-guard is the appropriate test —
the strings are the safety, fit_dxf is the redundancy.
