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

## SUBMIT

### `pvess permit`

```bash
pvess permit <project-dir> [--ahj NAME]
```

Generates `output/permit-package-<id>.pdf` — 12 pages.

| Option | Notes |
|---|---|
| `--ahj` | AHJ profile name. Defaults to "all sheets". Available: `austin_tx`, `phoenix_az`, `california_generic`, `hawaii_generic` |

### `pvess dxf`

```bash
pvess dxf <project-dir> [--preview]
```

Outputs `output/sheet-EE-1.dxf` + `output/sheet-EE-2.dxf` (AutoCAD R2018,
ACADE-compatible). `--preview` also emits PNG rasterizations.

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

## VERIFY

### `pvess doctor`

```bash
pvess doctor <project-dir> [--quiet]
```

Runs 28 structural self-checks. Exits non-zero on any FAIL. `--quiet`
suppresses PASS lines (CI-friendly).

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
pvess pipeline submit <project-dir> [--ahj NAME]
```

`calc + permit + dxf + doctor` — the full AHJ-submission bundle. Exits
non-zero on doctor FAIL.

### `pvess pipeline review`

```bash
pvess pipeline review <project-dir> [--ahj NAME]
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
