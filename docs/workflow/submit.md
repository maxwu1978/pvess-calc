# Submit

Submit phase emits the AHJ-bundle artifacts: 12-page permit PDF, two DXF
schematics, NEC labels PDF, QET single-line. Four subcommands; pipeline
shortcut bundles them.

## `pvess permit` — 12-page AHJ submittal

```bash
pvess permit projects/<id>/
pvess permit --ahj phoenix_az projects/<id>/    # AHJ-specific subset
```

Generates `output/permit-package-<id>.pdf` — one PDF, 12 pages:

| # | Code | Renderer | Notes |
|---|---|---|---|
| 1 | EE-0 | `permit/cover_sheet.py` | Title, client / engineer / installer, sheet index, PE stamp box |
| 2 | EE-1 | `dxf/render.py` → reportlab inset | Three-line diagram (DXF rasterized into PDF) |
| 3 | EE-2 | `dxf/grounding_sheet.py` → reportlab inset | Grounding & bonding (K.5: actual GES vs assumed) |
| 4 | EE-3 | `permit/panel_schedule.py` | MSP + sub-panel breaker tables (K.6: orphan-row centered) |
| 5 | EE-4 | `permit/site_plan.py` | Lot + house + array + setback dims + scale bar + equipment route |
| 6 | PV-4 | `permit/structural.py:render_attachment_plan` | Per-section roof plans + module grid clipped to polygon (K.2.6c–K.2.8) |
| 7 | PV-5 | `permit/structural.py:render_mounting_details` | Cross-section + plan + flashing detail (3-up) |
| 8 | PV-6 | `permit/structural.py:render_string_plan` | Color-coded string layout per roof face |
| 9 | EE-5 | `permit/compliance_checklist.py` | NEC compliance line-by-line w/ PASS/MANUAL flags |
| 10 | PV-N | `permit/general_notes.py` | General + electrical notes (K.6: §A/§B/§C/§D banners) |
| 11-12 | Labels | `labels/render.py` | 2×3 grid of NEC placards per page |

Order + content of sheets is the single source of truth in
`permit/sheet_registry.py`. The doctor's `cover_index_matches_pipeline`
check guarantees cover SHEET INDEX matches the actual emitted pipeline.

### AHJ profiles (`--ahj`)

`--ahj <name>` filters sheets + labels per AHJ profile:

```bash
pvess permit --ahj phoenix_az projects/002-phoenix-25kw/
pvess permit --ahj california_generic projects/<id>/
```

Available profiles (see `pvess_calc/permit/ahj_profiles/*.yaml`):

- `austin_tx` — Austin Energy
- `phoenix_az` — APS / SRP / Tucson Electric Power
- `california_generic` — covers all CA AHJs (Title 24 amendments)
- `hawaii_generic` — Rule 14H interconnection paths

[Add an AHJ profile](../recipes/add-ahj-profile.md) covers the file-level
recipe.

## `pvess dxf` — EE-1 + EE-2 schematics

```bash
pvess dxf projects/<id>/
pvess dxf --preview projects/<id>/    # also emits PNG rasterizations
```

Outputs:

- `output/sheet-EE-1.dxf` — Three-line diagram, AutoCAD R2018 format
- `output/sheet-EE-2.dxf` — Grounding & bonding
- (with `--preview`) `sheet-EE-1.png` + `sheet-EE-2.png` — matplotlib
  rasterizations for review w/o opening AutoCAD

The DXF files are ACADE (AutoCAD Electrical)-friendly: every device is
a block insert with `ATTDEF`s for nameplate data (tag / wires / amps /
OCPD). Engineers can open in ACADE and the schedule populates from the
attributes automatically.

### Visual conventions

Stable across DXF + DXF-preview PNG:

- **3 stroke weights** (`dxf/strokes.py`): `STROKE_THIN=18`, `MED=35`, `HEAVY=60`
- **4 text tiers** (`dxf/typography.py`): `TEXT_TITLE / HEADER / BODY / CAPTION`
- **Symbol library** (`dxf/symbols.py`): Wyssling-style PV chevron / GEN-LOAD-GRID
  inverter / knife switch — all designed at the same line weight tier.

## `pvess labels` — NEC label PDF

```bash
pvess labels projects/<id>/
```

Generates `output/labels.pdf` — ANSI Z535.4 placards on US Letter, 2×3
grid per page:

| Severity | Color | Label types |
|---|---|---|
| **DANGER** | Red | (none in default set) |
| **WARNING** | Orange | DC disconnect, AC disconnect, RSD, ESS disconnect, supply-side tap |
| **NOTICE** | Blue | Power-sources-present, PV power source |
| **CAUTION** | Yellow | (per-AHJ amendments) |
| **PLAIN** | Grey | Conduit interval markers |

Each label body is templated — runtime substitutions from
`qet/inject.build_substitutions` fill in `{{MAX_VOC_COLD}}`, `{{PV_OCPD}}`,
`{{RSD_BOUNDARY_V}}`, etc. K.7 [1/4] wired the NEC-edition-specific
80V / 30V threshold here.

## `pvess render` — QET single-line diagram

```bash
pvess render projects/<id>/
```

Generates `output/system.qet` — a QElectroTech v0.90 project file with
the engineer's NEC values text-injected into a hand-painted template at
`library/templates/residential-ess-v1.qet`.

QET is for **internal review** — engineers open the `.qet` to verify the
SLD makes sense before approving the permit package. AHJ submittals go
through the DXF / PDF outputs.

The renderer only touches `<dynamic_text>` content — never moves
elements, rotates symbols, or changes connections. The doctor's
`qet_xml_diff_only_text` check enforces this contract.

## Pipeline shortcut

The whole submit phase in one command:

```bash
pvess pipeline submit projects/<id>/         # calc + permit + dxf + doctor
pvess pipeline review projects/<id>/         # same, then opens PDF in Preview
```

`submit` exits non-zero on any doctor FAIL, so wiring into CI is safe.
