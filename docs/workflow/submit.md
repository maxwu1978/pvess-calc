# Submit

Submit phase emits the AHJ-bundle artifacts: permit PDF, two DXF schematics,
NEC labels PDF, QET single-line, plus EE-4 trace helpers. Pipeline shortcut
bundles the production artifacts.

## `pvess permit` — AHJ submittal

```bash
pvess permit projects/<id>/
pvess permit --ahj phoenix_az projects/<id>/    # AHJ-specific subset
pvess permit --profile tx_residential_pv projects/<id>/
```

Generates `output/permit-package-<id>.pdf`. The default `internal` package
profile emits one PDF, 12 pages:

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

### Reference package profile

Use `--profile tx_residential_pv` or `project.permit_profile:
"tx_residential_pv"` when the target is a contractor / Wyssling-style
residential plan set. `wyssling_like` is an alias for the same sheet set.

Reference profile page order:

| Code | Sheet |
|---|---|
| PV-1 | Cover Page |
| PV-2 | Site Plan |
| PV-3 | Property Plan |
| PV-4 | Attachment Plan |
| PV-5 | Mounting Details |
| EE-1 | String Plan |
| EE-2 | Three Line Diagram |
| EE-2.1 | One Line Diagram, only for supply-side / service-intercept paths |
| EE-3 | Electrical Notes |
| EE-4 | Labels |
| EE-5 | Placard |
| PV-6 | Design Notes |
| PV-7 | Site Photos |
| SPEC | Specification Sheets |

If `project.structural_letter_pdf` points at a signed engineering PDF, the
builder prepends it before PV-1. If not, it prepends a clearly marked
unsigned structural-review draft. PV-7 and SPEC also degrade to explicit
placeholders when photos or manufacturer PDFs are not yet supplied, and
`pvess doctor` reports those as WARN rather than FAIL.

### EE-4 trace skeleton

For complex roofs, generate a starter `site.ee4_trace` block before
manual visual polish:

```bash
pvess ee4-trace projects/<id>/
pvess ee4-trace --stdout projects/<id>/      # print instead of writing
```

Default output is `output/ee4-trace-skeleton.yaml`. Paste the
`site.ee4_trace` block into `inputs.yaml`, then adjust vertices against
the rendered EE-4 preview. `pvess doctor` emits a WARN if trace mode is
enabled but the outline / roof-line / fire-pathway layers are incomplete.

### EE-4 preview loop

Render just EE-4 while tuning trace points:

```bash
pvess ee4-preview projects/<id>/
pvess ee4-preview projects/<id>/ --no-png  # PDF only; no Poppler needed
pvess ee4-preview projects/<id>/ --strict-lint
```

Default outputs:

- `output/ee4-preview.pdf` — single-page EE-4 sheet
- `output/ee4-preview.png` — page-1 raster preview via `pdftoppm`

The command also prints the `ee4_trace_ready_for_review` status and visual
lint before writing artifacts. The lint checks traced roof containment,
module-rectangle overlaps, module/fire-pathway conflicts, equipment leader
labels, optimizer callout placement, fire offset labels, and drawing scale.
Use `--strict-lint` when you want WARN/FAIL to block a scripted review loop.

### PV-4 attachment overlay

When `site.ee4_trace` and per-module placements are available, PV-4 uses the
same traced roof outline as EE-4 and overlays structural attachment data on a
single roof plan: pale module rectangles, gray framing guides, red attachment
points, and spacing callouts. Projects without trace geometry still use the
legacy per-roof-section fallback.

### PV-6 string layout overlay

Stage 9.10 upgrades PV-6 when `site.ee4_trace` and per-module placements are
available. The sheet switches from per-section thumbnails to a full traced
roof plan with saturated module fills by string, small per-module string
numbers, a left-side string legend, north arrow, top-right equipment
summary, and automatic external `STRING N` leader callouts. Projects without
traced geometry continue to use the legacy per-section string table fallback.

`pvess doctor` runs `pv6_string_layout_visual_lint` for traced PV-6 sheets.
It catches missing string assignments, missing leader callouts, bad rollups,
and obvious label collisions before the package reaches manual review.

### EE-4A property context

Projects with traced roof geometry also emit `EE-4A · Property Context Plan`
in the full permit package. EE-4 stays focused on the roof array and
equipment callouts; EE-4A carries property-line, fence, driveway, and
dimension context in the style of contractor site plans.

Stage 9.9 makes this layer data-driven through `site.property_context`:
`lot_outline`, `driveway_polygon`, `fence_lines`, and
`property_dimensions` are drawn directly when present. If the block is
empty, EE-4A keeps the Stage 9.8 generated context as a visual fallback.
Use survey / GIS / satellite-reviewed coordinates in the same local feet
frame as `site.ee4_trace`.

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
- `output/sheet-EE-2.1.dxf` — One-line diagram, only when the project uses a
  supply-side / service-intercept path
- (with `--preview`) matching `sheet-EE-*.png` previews — matplotlib
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
