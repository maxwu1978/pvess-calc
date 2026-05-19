# CLI reference

Every `pvess` subcommand, sorted by phase.

> **Legacy aliases.** Each `pvess <sub>` has a back-compat alias
> `pvess-<sub>` (e.g. `pvess-calc`). Both forms work; new docs prefer
> the unified `pvess` form.

## Root

```bash
pvess --help                 # see workflow overview + subcommand list
pvess --version
pvess <sub> --help           # subcommand-specific options
```

## INTAKE

### `pvess init`

Interactive wizard that walks every required `inputs.yaml` field and writes
`projects/<project-id>/inputs.yaml`.

```bash
pvess init <project-id> [--resume] [--address ADDR]
```

| Option | Notes |
|---|---|
| `<project-id>` | Becomes the project directory name + `project.id` field |
| `--resume` | Pick up where ctrl-C'd; reads `.wizard-state.json` |
| `--address`, `-a` | Pre-fill via K.3 lookup chain (utility/AHJ/NEC/ASHRAE/export tariff) |

### `pvess survey`

```bash
pvess survey [-o PATH]
```

Generates a printable 5-page US-Letter site-survey checklist PDF. Default
output: `site-survey-checklist.pdf`. Doesn't take a project — same form
fits every project.

### `pvess lookup`

```bash
pvess lookup                            # smoke-test default "Phoenix, AZ"
pvess lookup "Honolulu, HI"             # any address
```

Prints:

- `.env` file path (if found) + token fingerprints (no full tokens)
- Resolved field set with source + confidence per field
- Summary: `N offline + M online = N+M fields`

Use after setting `PVESS_MAPBOX_TOKEN` / `PVESS_NREL_API_KEY` to verify
they're picked up.

## DESIGN

### `pvess calc`

```bash
pvess calc <project-dir>
```

Runs every NEC calculation. Writes:

- `output/calculation.json` — full machine-readable dump
- `output/report.md` — engineer-readable NEC report

Prints `interconnect: PASS (supply_side_tap)` summary line.

### `pvess customer`

```bash
pvess customer <project-dir> [--address ADDR]
```

Generates `output/customer-summary.pdf` (1 page). Pulls system size from
the engine + economics from `customer/economics.py` (uses lookup fields
when available).

### `pvess compare`

```bash
pvess compare <scenarios-dir>
```

Where `<scenarios-dir>` contains subdirectories each with their own
`inputs.yaml`. Writes:

- `comparison.md` — Markdown side-by-side
- `comparison.json` — machine-readable
- `comparison.pdf` — 1-page landscape PDF (K.7 [4/4])

### `pvess serve`

```bash
pvess serve [--host HOST] [--port PORT] [--workdir DIR] [--access-token TOKEN] [--reload]
```

Starts the local **TGE Solar Project Generator** browser UI. The UI collects
site and equipment data, runs preflight checks, generates package outputs, and
writes BOM cost artifacts.

| Option | Notes |
|---|---|
| `--host` | Bind address. Defaults to `127.0.0.1` |
| `--port` | Bind port. Defaults to `8765` |
| `--workdir` | Job/output storage. Defaults to `~/.pvess/web_jobs` |
| `--access-token` | Optional shared token required for `/api/*` and `/files/*` routes |
| `--reload` | Enable Uvicorn reload during UI/API development |

Each generated job stores `request.json`, `inputs.yaml`, generated outputs,
`bom-cost.json`, `bom-cost.csv`, `artifact-manifest.json`, uploaded source
files, and a complete ZIP package under the Web workdir.

The workdir also contains `web-jobs.sqlite3`, a searchable job index for
history, filters, source-material/readiness metadata, and artifact records.
Generated files remain in each job folder. Existing job folders with
`job-status.json` are imported into the index automatically when history is
listed.

Environment equivalents:

- `PVESS_WEB_WORKDIR` — default generated-job directory
- `PVESS_WEB_ACCESS_TOKEN` — same behavior as `--access-token`
- `PVESS_WEB_CORS_ORIGINS` — comma-separated allowed origins for hosted
  front-end/API deployments

## SUBMIT

### `pvess permit`

```bash
pvess permit <project-dir> [--ahj NAME] [--profile PROFILE] [--readiness-appendix]
```

Generates `output/permit-package-<id>.pdf`.

| Option | Notes |
|---|---|
| `--ahj` | AHJ profile name. Defaults to "all sheets". Available: `austin_tx`, `phoenix_az`, `california_generic`, `hawaii_generic` |
| `--profile` | Permit package profile. Defaults to `project.permit_profile` or `internal`. Available: `internal`, `tx_residential_pv`, `wyssling_like` |
| `--readiness-appendix` | Appends an `INTERNAL REVIEW ONLY` data-readiness appendix generated from `pvess readiness`. It is opt-in and should not be included in AHJ submissions unless explicitly approved. |

`tx_residential_pv` / `wyssling_like` emit a reference-style PV/EE drawing
set with PV-1 cover, PV-7 site photos, SPEC appendix, EE-5 placard, and a
conditional EE-2.1 one-line diagram for supply-side / service-intercept paths.
The SPEC appendix uses `project.spec_sheets[]` as the selected-equipment list;
candidate inverter alternatives should not be listed there.

### `pvess dxf`

```bash
pvess dxf <project-dir> [--preview]
```

Outputs `output/sheet-EE-1.dxf` + `output/sheet-EE-2.dxf` (AutoCAD R2018,
ACADE-compatible). When the selected interconnection is supply-side /
service-intercept, it also emits `output/sheet-EE-2.1.dxf`. `--preview`
also emits PNG rasterizations.

### `pvess labels`

```bash
pvess labels <project-dir>
```

Outputs `output/labels.pdf` (ANSI Z535.4 placards).

### `pvess render`

```bash
pvess render <project-dir> [--template PATH]
```

Outputs `output/system.qet` (QElectroTech v0.90). Template defaults to
`library/templates/residential-ess-v1.qet`.

### `pvess ee4-trace`

```bash
pvess ee4-trace <project-dir> [-o PATH] [--stdout] [--force]
```

Generates a paste-ready `site.ee4_trace` YAML skeleton for EE-4 from
`roof_sections`, module placements, and known obstructions. Default output:
`output/ee4-trace-skeleton.yaml`.

Use this when a project needs the permit-style traced roof layer rather
than the generated roof geometry alone.

### `pvess ee4-preview`

```bash
pvess ee4-preview <project-dir> [--pdf-output PATH] [--png-output PATH]
pvess ee4-preview <project-dir> --no-png
pvess ee4-preview <project-dir> --strict-lint
```

Renders only the EE-4 site-plan sheet for fast trace review. Default
outputs:

- `output/ee4-preview.pdf`
- `output/ee4-preview.png` (requires Poppler `pdftoppm`)

It prints the `ee4_trace_ready_for_review` status before writing files.
Visual lint is enabled by default and checks module-rectangle overlaps,
module/roof/fire-pathway geometry, plus leader/callout text placement.
`--strict-lint` turns any lint WARN/FAIL into a non-zero exit after
artifacts are written.

## VERIFY

### `pvess doctor`

```bash
pvess doctor <project-dir> [--quiet]
```

Runs structural self-checks. Exits non-zero on any FAIL. `--quiet`
suppresses PASS lines (CI-friendly).

### `pvess readiness`

```bash
pvess readiness <project-dir> [-o PATH] [--checklist-output PATH] [--stdout] [--strict]
```

Writes two source-data review files by default:

- `output/reference-readiness.md` — audit detail separating real field data
  from simulated/mock/TBD values and missing signed inputs
- `output/real-data-checklist.md` — operator checklist for replacing every
  simulated/missing item before submission

Default mode is non-blocking so teams can iterate with simulated site data.
`--strict` exits 1 when any readiness item is `simulated` or `missing`.

If the project root contains `simulated-site-data.yaml`, the report includes
that source pack as the explicit provenance record for mock photos,
synthetic utility usage, modeled roof geometry, and other demo-only inputs.
Fields listed in the source pack stay `simulated` until the replacement
standard in that file is satisfied.

### `pvess symbols`

```bash
pvess symbols [-o PATH] [--dxf-only]
```

Renders every icon in `dxf/symbols.py` on one page. Dev tool — use
after adding a new symbol to verify stroke weight / proportions
consistent with the library.

## PIPELINES

### `pvess pipeline customer`

```bash
pvess pipeline customer <project-dir> [--address ADDR]
```

`calc + customer-summary` in one command. Sales-meeting one-pager + the
NEC report.

### `pvess pipeline submit`

```bash
pvess pipeline submit <project-dir> [--ahj NAME] [--profile PROFILE]
```

`calc + permit + dxf + doctor` — the full AHJ-submission bundle. Exits
non-zero on doctor FAIL.

### `pvess pipeline review`

```bash
pvess pipeline review <project-dir> [--ahj NAME] [--profile PROFILE]
```

Same as `submit` + opens the permit PDF in the default viewer (macOS
Preview / Acrobat).

## Environment variables

| Var | Provider | Where to get one |
|---|---|---|
| `PVESS_MAPBOX_TOKEN` | Mapbox geocoding (lat/lng/county) | <https://account.mapbox.com/access-tokens/> |
| `PVESS_NREL_API_KEY` | NREL PVWatts (annual production) | <https://developer.nrel.gov/signup/> |
| `PVESS_CACHE_ROOT` | Override lookup cache location (default `~/.pvess`) | (testing only) |

Set via `.env` file in project root (auto-loaded by `lookup/config.py`)
or via shell `export`. **Never commit tokens to git** — the included
`.gitignore` covers `.env` / `.env.local`.
