# Design Standards

These are not aspirations. Each section is a binding rule for the code that
ships under `src/pvess_calc/`. When a future change conflicts with one of these,
**update the standard first** (in this file, with reasoning) before changing
the code; never silently violate.

## 1. NEC version dispatch

Every NEC-version-sensitive rule lives in `pvess_calc/nec/vYYYY.py`. The calc
engine, dxf renderers, and permit builders **must not** branch on
`nec_edition` directly. Use `pvess_calc.nec.get_rules(edition)` to pick the
ruleset; if a rule isn't there, add it to the ruleset, don't inline it.

```python
# ❌ bad — scattered version logic
if result.inputs.project.nec_edition == "2023":
    ocpd = pv_isc * 1.25 * 1.25

# ✅ good — versioned in nec/v2023.py
rules = get_rules(result.inputs.project.nec_edition)
ocpd = rules.pv_ocpd(pv_isc)
```

When a new NEC edition lands, `nec/v2026.py` (or whatever) inherits from the
most recent and overrides only the changed rules.

## 2. Sheet Registry — single source of truth

Every sheet (EE-*, PV-*, PV-N, …) is registered once in
`pvess_calc/permit/sheet_registry.py`:

```python
SHEET_REGISTRY: list[SheetSpec] = [
    SheetSpec(code="cover",  title="Cover Sheet",         render=render_cover),
    SheetSpec(code="ee-1",   title="Three-Line Diagram",  render=render_ee1),
    SheetSpec(code="ee-2",   title="Grounding & Bonding", render=render_ee2),
    ...
]
```

Three places **must** read from this list, none may hardcode:

1. `permit/cover.py` — the SHEET INDEX block on the cover page
2. `permit/builder.py` — the pipeline order
3. `ahj/profile.py` default `required_sheets` + validation of YAML profiles

A new sheet means one PR adding one entry. If the registry says it exists, the
cover lists it, the builder emits it, and the AHJ profiles are validated
against it. **Cross-page consistency is structural, not enforced by review.**

## 3. Layout constants — top-of-file block

Each sheet renderer keeps its layout numbers (margins, gaps, heights, font
sizes) in a single named-constants block at the top of the file. Magic numbers
mid-function are forbidden.

```python
# ✅ top of grounding_sheet.py
SHEET_W = 17.0
NOTES_STRIP_H = 0.9      # top notes block (4 lines, height 0.16 ea)
BUS_OFFSET = 1.9         # below SCHEMATIC_Y1; tuned so labels clear notes
```

When visual review surfaces a collision, the fix changes a constant — never
sprinkles `+0.4` into a function body. This is what made the Phase J round of
EE-2/EE-4 fixes one-line edits.

## 4. Schema additivity

New fields on Pydantic models **must**:

- Be `Optional` or have a sensible default
- Round-trip against the unchanged Smith Residence yaml (old projects keep working)
- Use `type(self).model_fields` (V2.11+), not `self.model_fields` (deprecated)

Removing or renaming a field is a breaking change — we don't have any users
yet, but the policy still applies because it forces the conversation. If you
need to remove, write a migration note in the same PR.

## 5. AHJ extensibility — YAML only

Switching from `--ahj phoenix_az` to `--ahj austin_tx` must require **zero**
Python changes. AHJ-specific behavior is configured in
`src/pvess_calc/ahj/profiles/<name>.yaml`:

- `required_sheets`: subset of Sheet Registry codes
- `label_set`: subset of NEC label codes in `pvess_calc/labels/specs.py`
- `inspector_checklist`: free-form strings rendered on EE-5
- `form_blanks`: free-form strings rendered on cover

If something new can't be expressed in YAML, extend the **profile schema**
(`ahj/profile.py`), don't hardcode an `if ahj == "phoenix_az"` somewhere.

## 6. Device library references

PV modules, batteries, inverters, optimizers are stored in
`pvess_calc/devices/<kind>.py` as dicts keyed by short slug
(`talesun_tp7g54m_415`, `eg4_lifepower4_v2`, `tigo_ts4_a_o`). Project YAMLs
reference them by `*_ref`. Inline-field syntax is a fallback for prototyping
and **must** raise a warning in the calc engine when used.

## 7. String-truncation discipline

`text[:N]` is forbidden in any rendered output. Use one of:

- Shorten the source string so it fits the field
- Widen the field
- Use reportlab's `Paragraph` with a `Frame` to flow text (multi-line)
- Call the appropriate `fit*()` helper (see below)

This was the MSP "utility m" bug. The fix is policy, not patch.

### Per-path fit helpers

Two rendering paths, two helpers — same idea, different measurement:

| Path | Helper | Width source | Fallback marker |
|---|---|---|---|
| reportlab (permit/*.py) | `permit._textfit.fit(text, font, size, max_pt)` | `reportlab.pdfbase.pdfmetrics.stringWidth` (real font metrics) | `…` (U+2026) |
| DXF (dxf/*.py) | `dxf._textfit.fit_dxf(text, max_in, height)` | `len(text) * height * CHAR_WIDTH_RATIO` (estimate, ratio=0.60) | `...` (ASCII tripledot — stroke fonts may lack U+2026) |

The DXF estimate has ~10% error vs. actual rendered width; the doctor's
`_check_dxf_text_no_overflow` uses the same estimator, biased slightly
toward false-negatives, so a real overflow is flagged but tight-but-fits
text isn't.

### Doctor enforcement

`pvess-doctor` enforces this rule on **both** paths:

- `no_truncation_slices` — scans `permit/` and `dxf/` source for the
  forbidden `text[:N]` pattern
- `dxf_text_no_overflow` — renders EE-1/EE-2 DXF and verifies every
  TEXT entity on `SCHEDULE`, `TITLE_BLOCK`, and `NOTES` layers fits
  within its declared container bounds
- `dxf_no_text_overlap` — pairwise bbox check across all TEXT entities
  on EE-1/EE-2 (excluding `ANNOTATION` layer, where wire tags are
  intentionally placed near other elements); flags overlaps above 25%
  of the smaller bbox area

The reportlab path doesn't need a runtime overflow check because `fit()`
uses real `stringWidth` — by construction the text fits.

### Doctor gap: text vs. non-text geometry

Doctor's automated checks **do not** catch text crossing through wires
or polyline icon geometry — this is text-vs-text and text-vs-bounds
only. The skill `.claude/skills/pvess-visual-polish/` documents the
canonical fixes for each known collision pattern:

- **Vertical wire crosses an ATTDEF stack** (e.g. MSP's "200A main"
  DESC1 hit by the wire dropping to the critical sub-panel): set
  `attdef.dxf.flags = 1` (invisible) on the redundant ATTDEFs. Data is
  preserved for ACADE; only the rendered output drops the conflicting
  text. Currently applied to the `MSP` device block.
- **Vertical wire crosses a panel header** (e.g. SUB-#1's "(N) SUB
  PANEL #1" hit by the wire from MSP above): move the header to the
  SIDE of the panel (right-aligned, ending before the panel's left
  edge), not centered above. Currently applied to critical sub-panels.
- **Notes strip text grazes the top of a column** (PV-S1's box outline
  touched the NOTES line's descenders): increase `NOTES_AREA_H` in
  `_draw_schematic` to push the whole device column down.

Manual eyeball review of EE-1 and EE-2 remains required for these
cases — the 5-criteria closing standard's ⑤ explicitly covers them.

## 7.5. Design tokens — typography + strokes

Every text height and line weight is parameterized into a tier; no
magic numbers in render code.

| Module | Tiers | File |
|---|---|---|
| `dxf/typography.py` | `TEXT_TITLE` (0.115") · `TEXT_HEADER` (0.095") · `TEXT_BODY` (0.080") · `TEXT_CAPTION` (0.065") | 4 tiers, ~1.2× geometric ratio |
| `dxf/strokes.py` | `STROKE_THIN` (18) · `STROKE_MED` (35) · `STROKE_HEAVY` (60) | 3 tiers, DXF lineweight 0.01 mm units |

Tier-to-element mapping is documented at the top of each file. Adding
a new text size or lineweight = picking a tier, never a literal. If
no tier fits, the layout is wrong, not the tier system — fix the layout.

The swatch tool (`symbols_preview.py`) has its own `SWATCH_*` constants
because it's a different presentation environment (single-page dev
tool, larger text for readability). Production DXF and dev swatch live
in separate type scales by design.

## 7.6. Schedule table conventions

Both the EE-1 CONDUCTOR SCHEDULE and EE-2 GROUNDING & BONDING SCHEDULE
follow these rules. New schedules added later (e.g. an EGC sequence
table, a junction-box schedule) must follow them too.

### A. Cell values must be data-driven, never hardcoded

**Anti-pattern from 2026-05-14 audit**: the EE-1 schedule had
`"10 AWG"` and `"FREE AIR"` literally in the row tuple. For the Phoenix
test fixture these happened to match `result.grounding.egc_pv_source`
and the implicit conduit choice — so tests passed. But any other
project (bigger array, different inverter, different ambient temp)
would render values that **silently disagreed with the calc engine**.

Rule: every cell value in a schedule row must come from `result.*` or
be a fixed-by-NEC-definition constant (e.g. "THWN-2 CU"). Specifically:

- **GND** column → `result.grounding.egc_*` (NEC 250.122 selection)
- **CONDUIT** column → `result.adjacent.*_conduit.selected_conduit`
  (NEC Chapter 9 fill calc)
- **SIZE** column → `result.<path>_conductor.size` (310.16 + 240.4(D))
- **AMPCY** column → `result.<path>_conductor.ampacity_a` (note: this is
  the DERATED ampacity after 310.15(B)(2)(a) temperature correction and
  (3)(a)(1) conduit fill adjustment — already includes Phoenix-style
  hot-ambient knockdowns)
- **OCPD** column → `result.<ocpd_field>` (240.6 next standard)

### B. Column headers at TEXT_BODY tier (not TEXT_HEADER)

Schedule column headers (TAG, WIRES, SIZE, …) render at TEXT_BODY,
NOT TEXT_HEADER. The visual hierarchy comes from:

1. The schedule's TITLE bar (CONDUCTOR SCHEDULE / GROUNDING & BONDING
   SCHEDULE) at TEXT_TITLE — that's the table's prominence anchor.
2. A horizontal underline below the column-header row separates
   headers from data.

Putting headers at TEXT_HEADER (one tier above data) made them
~25% wider than data and caused dense tables to spill text into the
neighboring column ("WIRESSIZE", "AMPCYOCPD"). This rule overrides
the general §7.5 "schedule column header row → TEXT_HEADER" mapping
specifically for tables with ≥6 columns or ≥4.5" total width
constraint. The dxf/typography.py top-of-file comment notes both
mappings exist; for tables, use BODY.

### C. Drop redundant column prefixes

If the column header declares the kind, the row values don't repeat it:

| ❌ before                | ✅ after        | why                          |
|---|---|---|
| `EGC: PV source`         | `PV source`     | CONDUCTOR header says "EGC:" |
| `10 AWG CU` (every row)  | `10 AWG`        | notes header says "CU"       |
| `(N) 2P-50A` (breaker row) | `2P-50A`       | panel header says "(N)"      |

The general principle: redundancy at the row level is multiplied by
the row count — for a 6-row schedule, dropping a 4-char prefix saves
visual space equal to a small column.

### D. Drop derivable columns

Don't render columns whose values are trivially computed from other
columns. The "×1.25" column in EE-1 conductor schedule was AMPS ×
1.25, recoverable by mental math. Dropping it freed ~0.4" of frame
width that the remaining 9 columns redistributed. NEC inspectors don't
need every step printed; they verify the chain themselves.

### E. RUN / DESCRIPTION cells use abbreviated arrow notation

Long descriptive English forces either tiny font or fit_dxf
truncation (`MSP → grounding electrode system` → `MSP → grounding...`
which conveys nothing). Use the device-tag arrows established in
EE-1: `MSP → GES`, `PV equip → GEC`, `INV → AC trunk`, `Modules →
COMB`. The diagram itself shows the topology; the schedule's RUN
column is just a re-statement, not a primary teaching tool.

### F. Standing tests

Each schedule should have at least one **positive-guard test**
(see `tests/test_doctor.py::test_grounding_schedule_rows_fit_without_fit_dxf`):
disable fit_dxf, render the schedule, verify the doctor's overflow
check still PASSES. This proves the rows fit by design rather than by
runtime truncation — preventing future maintainers from accidentally
re-introducing long strings that "look fine" only because fit_dxf
silently chops them.

## 8. Naming conventions (already in CLAUDE.md, repeated for completeness)

- Device tags: `PV-1`, `DC-COMB-1`, `RSD-1`, `INV-1`, `ESS-1`, `AC-DISC-1`, `MSP`
- Project dirs: `NNN-customer-name` (3-digit zero-padded)
- Sheet codes: `ee-N` for electrical, `pv-N` for PV structural, `pv-n` for general notes
- Standard OCPD ratings: NEC 240.6, defined in `nec/v2023.py::STANDARD_OCPD_RATINGS`

## 9. File-touch checklist for common changes

| Change | Files |
|---|---|
| Add an NEC calculation | `nec/v2023.py` (rule) + `calc/<area>.py` (caller) + `tests/test_<area>.py` |
| Add a sheet | `permit/<sheet>.py` (renderer) + `permit/sheet_registry.py` (one line) + AHJ profile YAMLs (if AHJ-specific) |
| Add an AHJ profile | one YAML in `ahj/profiles/` + one row in `tests/test_permit_ahj.py` |
| Add a device | one entry in `devices/<kind>.py` |
| Add a NEC label | one `LabelSpec` in `labels/specs.py::LABEL_CATALOG` |

If a change touches **more files than the table above lists**, it's probably
violating one of §1-§7. Read the standard, fix the design.
