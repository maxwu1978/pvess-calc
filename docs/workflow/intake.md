# Intake

The intake phase captures the project's facts: address, electrical service,
roof shape, equipment selection. Three subcommands, in roughly the order a
new project would use them:

## `pvess init` — interactive wizard

Creates a new project from scratch by walking every required field with
a labeled prompt:

```bash
pvess init 003-jones-residence
```

The wizard:

- Iterates `WIZARD_FIELDS` (sourced from `wizard/field_specs.py` + the
  site-survey checklist's `SITE_FIELDS`).
- Shows each prompt with `yaml_path` + hint + "where to find" tag.
- Checkpoints answers after every prompt to
  `projects/<id>/.wizard-state.json` — `Ctrl-C` and `pvess init --resume <id>`
  picks up where you left off.
- Validates the assembled yaml via `Inputs.model_validate()` at the end
  and writes `projects/<id>/inputs.yaml`.

### `--address` pre-fill (K.3)

```bash
pvess init 003-jones-residence --address "Los Angeles, CA"
```

The lookup orchestrator pre-fills 6–11 fields as **prompt defaults** (not
silent writes — you still press `<enter>` to accept):

| Field | Source |
|---|---|
| `project.utility` | static_utility (offline) |
| `project.ahj` | static_ahj (offline) |
| `project.nec_edition` | static_nec (state-level adoption) |
| `pv_array.ashrae_2pct_min_c` | static_ashrae (city-level) |
| `routing.ambient_temp_c` | derived from ASHRAE 2% max |
| `loads.export_tariff_model` | per-state recommendation (CA→`ca_nem3`, HI→`hi_self_consumption`, else `1to1_nem`) |
| `latitude` / `longitude` / `county` | Mapbox v5 (online, env-var key) |
| `annual_energy_kwh_per_kw` | NREL PVWatts v8 (online, env-var key) |
| `avg_residential_rate_usd_per_kwh` | static_utility_rate (offline, 30+ cities) |

See [Add a lookup provider](../recipes/add-lookup-provider.md) for the
provider plug-in pattern.

## `pvess survey` — printable site checklist PDF

```bash
pvess survey -o my-checklist.pdf
```

A 5-page printable form (US Letter) the field surveyor takes on site:

- **Section 1** — Client + admin (name / address / GPS / APN / utility / AHJ)
- **Section 2** — Electrical service (MSP / busbar / sub-panels +
  K.2.5 slot capacity + K.5 GES inventory)
- **Section 3** — Roof sections (shape: rect / tri / polygon + obstructions
  free-text + per-edge setback override)
- **Section 4** — Routing & wire lengths (6 segments + conduit fill)
- **Section 5** — Climate (ASHRAE 2% min/max + attic ambient)

Each row prints its `yaml_path` tag — engineer transcribes filled values
into `inputs.yaml`.

The field list is the single source of truth in
`src/pvess_calc/site_checklist/field_specs.py` (`SITE_FIELDS` tuple).
The doctor's `site_checklist_covers_schema` check cross-references it
against the `Inputs` pydantic schema.

## `pvess lookup` — verify address lookup config

```bash
pvess lookup                        # smoke-test Phoenix
pvess lookup "Honolulu, HI"        # any address
```

Prints:

1. `.env` file path (if present) + token fingerprints (first 7 + last 4 chars)
2. The full resolved field set with source provenance
3. Summary line: `N offline + M online = N+M fields`

Use this *after* setting API keys to verify they're picked up without
leaking the full token into terminal scrollback or screenshots.

## After intake

Once `inputs.yaml` exists and is valid:

- Hand-edit any K.2.5 / K.2.6 / K.5 fields that the wizard didn't ask
  about (sub-panel slots, ESS install location, GES rod count).
- Move on to **[Design](design.md)** to run the NEC math.

## Common pitfalls

- **Sub-panel order matters.** When `service.sub_panels[]` has > 1 entry,
  index 0 is the panel closest to AC-DISC and the last index is closest
  to MSP. The K.2.6a voltage-drop chain walks left to right.
- **`shape: "polygon"`** vertices must be counter-clockwise and form a
  simple (non-self-intersecting) polygon. The pydantic validator rejects
  bow-ties + clockwise lists with a clear error.
- **NEC 2017** isn't a CLAUDE.md fallback anymore (K.7 [1/4]) —
  `nec_edition: "2017"` gets real 2017 rules. Confirm against your AHJ's
  actual cycle (`lookup/data/nec_adoption.json` lists state defaults).
