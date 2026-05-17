# Design

Design phase runs the NEC math and emits engineer-facing + customer-facing
outputs. Three subcommands.

## `pvess calc` — NEC engine

```bash
pvess calc projects/<id>/
```

Loads `inputs.yaml`, runs every NEC calculation in `src/pvess_calc/calc/`,
writes:

| File | Contents |
|---|---|
| `output/calculation.json` | Full machine-readable dump — every intermediate value |
| `output/report.md` | Human-readable markdown report with all NEC references |
| stdout | One-line summary: `interconnect: PASS (supply_side_tap)` |

### What's computed

| Module | NEC | What it does |
|---|---|---|
| `calc/pv_string.py` | 690.7 / 690.8 | Cold-Voc correction (datasheet βVoc or Table 690.7) + Isc ×1.25 |
| `calc/conductor.py` | 310.15 / 310.16 / 240.4(D) | Wire sizing w/ temp + fill derate + small-conductor rule |
| `calc/ocpd.py` | 240.6 | Standard OCPD rounding (15/20/25/.../500 A) |
| `calc/interconnect.py` | 705.12 | sum / 120% / supply-side / center-fed evaluation. K.2.5: includes existing PV on bus |
| `calc/ess.py` | 706.7 / 706.15 | ESS AC disconnect + OCPD sizing |
| `calc/ess_install.py` | 706.10 + IRC R328 | ESS install-location compliance |
| `calc/grounding.py` | 250.66 / 250.122 / 250.166 | EGC / GEC sizing. K.5: compares actual vs required |
| `calc/voltage_drop.py` | 215.2 / 210.19 | 5-segment vd table. K.2.6a: per-sub-panel chain |
| `calc/aic.py` | 110.24 | Available fault current vs OCPD AIC rating |
| `calc/adjacent.py` | 690.11 / 690.12 / 230.67 / 250.50 | AFCI / SPD / RSD / ground rod topology |
| `calc/roof_layout.py` | 690.12 | K.2.6c–K.2.8: per-roof-section usable area + module placement |

The engine returns a `CalculationResult` dataclass; every downstream
artifact (permit / customer / DXF / labels) reads from this single object.

## `pvess customer` — homeowner one-pager

```bash
pvess customer projects/<id>/
```

Generates `output/customer-summary.pdf` — a 1-page sales/conversation tool
for the homeowner. Built with reportlab; chart via matplotlib (`savefig`
to PNG → reportlab embed).

Sections (top to bottom):

1. **Title** — system name + location
2. **Spec strip** — 3 boxed values: PV modules / battery kWh / inverter kW
3. **Hero** — $X/mo savings (orange) + $Y/yr + payback (after ITC + before)
   + optional **annual offset donut** (only if `loads.monthly_kwh` has 12 values)
4. **Backup runtime** — essentials only / with AC / with heat-pump heating
   (HVAC-type aware)
5. **Monthly production bar chart** — overlaid with homeowner usage line
   (if `monthly_kwh` provided)
6. **Notes** — pre/post-ITC cost, NREL source, **tariff model**
   (K.7 [2/4]: CA NEM 3.0 makes a 40% ROI difference vs 1:1 NEM)

### What's NOT in customer-summary

- NEC clause references (those live in `report.md`)
- Specific equipment models (those live in the permit package)
- BOM (lives in scenario comparison; see below)

## `pvess compare` — scenario comparison

```bash
pvess compare projects/<id>/scenarios/
```

Where `scenarios/` is a directory of subdirectories, each with its own
`inputs.yaml`. Generates three outputs in `scenarios/`:

- `comparison.md` — markdown table (one column per scenario)
- `comparison.json` — machine-readable
- `comparison.pdf` — **K.7 [4/4]**: customer-facing landscape PDF with
  economics strip + 11-row metric table

The PDF layout:

| Block | Per scenario |
|---|---|
| Hero strip (top) | $X/mo (orange) + $Y/yr + payback after ITC + annual kWh |
| Metric table (bottom) | PV / Inverter / Battery / Backfeed / 705.12 method / Voc / OCPD / Vd / AIC / BOM |

Use case: sales meeting with multiple PV+ESS configurations. Pair with
`pvess customer` for the single-scenario deep dive.

## Pipeline shortcut

The whole design phase in one command:

```bash
pvess pipeline customer projects/<id>/        # calc + customer-summary
```

See **[Submit](submit.md)** for the full AHJ-bundle pipeline.

## Editing inputs and re-running

After `pvess calc`, edit `inputs.yaml` and re-run — outputs regenerate in
~600 ms. There's no persistent state outside of `output/` and (optionally)
`.wizard-state.json` for unfinished wizard sessions.

Verify changes look right with **[Verify → `pvess doctor`](verify.md)**.
