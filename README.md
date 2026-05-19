# pvess-calc

Parameter-driven NEC calculation + permit-package generator for residential
PV + ESS designs. One `inputs.yaml` → AHJ submittal package, homeowner
one-pager, NEC labels, ACADE-compatible DXF. Projects can use the default
internal sheet set or a reference-style `tx_residential_pv` /
`wyssling_like` package with PV-1/PV-7/SPEC pages.

## 5-minute install + run

```bash
git clone <repo> && cd 11CAD家庭储能
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Single command: NEC math + permit PDF + DXF + structural checks
pvess pipeline submit projects/002-phoenix-25kw/
```

Result: `projects/002-phoenix-25kw/output/permit-package-002-phoenix-25kw.pdf`
(12 pages, ~800 KB) + DXF schematics + all doctor checks PASS.

Reference-style package:

```bash
pvess pipeline submit projects/003-frisco-glasshouse/ --profile tx_residential_pv
```

That profile emits the contractor-style PV/EE sheet numbering, conditional
EE-2.1 one-line diagram, PV-7 site-photo sheet, SPEC attachment section, and
an unsigned structural-review draft when no signed engineering PDF is supplied.

Browser UI:

```bash
pvess serve --host 127.0.0.1 --port 8765
# Optional for a shared preview machine:
pvess serve --host 0.0.0.0 --port 8765 --access-token "$PVESS_WEB_ACCESS_TOKEN"
```

This starts the local **TGE Solar Project Generator** so an operator can enter
site and equipment data, run address lookup/preflight, generate package
outputs, preview generated PDFs/PNGs, and review BOM cost without hand-editing
`inputs.yaml`.

## Documentation

```bash
pip install -e ".[docs]"     # adds mkdocs + material theme
mkdocs serve                 # local docs site at http://127.0.0.1:8000
```

Or read the markdown directly under [`docs/`](docs/):

- [`docs/index.md`](docs/index.md) — overview + 30-second pitch
- [`docs/quickstart.md`](docs/quickstart.md) — 10-minute walkthrough
- [`docs/web-ui.md`](docs/web-ui.md) — browser generator workflow
- [`docs/web-ui-language.md`](docs/web-ui-language.md) — UI terminology and copy standard
- [`docs/workflow/`](docs/workflow/) — intake → design → submit → verify
- [`docs/recipes/`](docs/recipes/) — add AHJ / NEC edition / lookup provider
- [`docs/reference/`](docs/reference/) — CLI / schema / doctor checks

## What's modelled

- **NEC 2017 / 2020 / 2023** — real per-version dispatch (sum-rule legal
  in 2017, removed in 2020; RSD boundary 80 V vs 30 V; etc.).
- **705.12 / 706.10 / IRC R328** — interconnection + ESS install location.
- **250.66 / 250.122 / 250.166** — GEC + EGC sizing vs **actual** GES.
- **310.15(B)** derating, **240.4(D)** small conductor, **110.24** AIC.
- **NREL PVWatts + Mapbox** — optional online providers (env-var keys);
  fully offline-capable.
- **Polygon roof geometry** (rect / tri / arbitrary N-gon) with module
  placement clipped to the inset polygon (K.2.6c → K.2.8).
- **CA NEM 3.0** + **HI Rule 14H** — accurate ROI for those markets
  (K.7 [2/4]).

## Tooling

- **`pvess <subcommand>`** — unified CLI; subcommands + pipelines.
- **`pvess serve`** — local browser project generator + BOM estimator.
- **`pvess doctor`** — structural self-checks; CI-ready.
- **MkDocs Material** site under `docs/`.
- **Pytest suite** under `tests/`; `pytest -q` runs in ~30 s.

## Changelog

See [`CHANGELOG.md`](CHANGELOG.md) for the full K-phase milestone history.
Latest milestones: Web UI W1-W13 local generator (2026-05-19), Phase I
regional rules (2026-05-18), and reference-style planset profile
(2026-05-18).

## Scope + license

Internal tool. US residential market only. **Not a substitute for a
licensed PE's seal** — the NEC numbers it emits need a real engineer's
review before permit submittal.

For the project plan + design rationale see [`docs/DESIGN.md`](docs/DESIGN.md)
and [`docs/TESTING.md`](docs/TESTING.md).
