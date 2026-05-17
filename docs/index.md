# pvess-calc

**Parameter-driven NEC calculation + permit package generator for residential
PV + ESS designs.** One `inputs.yaml` → full 12-page AHJ submittal package,
homeowner-friendly summary PDF, customer comparison sheet, NEC labels,
ACADE-compatible DXF schematics.

---

## In 30 seconds

```bash
pip install -e .

pvess pipeline submit projects/002-phoenix-25kw/
```

That single command runs:

1. **`pvess calc`** — NEC 690 / 705 / 706 / 250 / 110 math + `report.md`
2. **`pvess permit`** — 12-page AHJ submission PDF (EE-0..EE-5, PV-4..PV-N, labels)
3. **`pvess dxf`** — EE-1 three-line + EE-2 grounding DXF (ACADE-compatible)
4. **`pvess doctor`** — 28 structural self-checks (cover index, slot counts,
   NEC edition consistency, GES compliance, …)

```
✓ Submit pipeline complete — ready for AHJ.
  Package: projects/002-phoenix-25kw/output/permit-package-002-phoenix-25kw.pdf
```

---

## What it covers

The tool was built around a real engineer's permit-package workflow. Every
phase has a CLI subcommand and a corresponding output file:

| Phase | Command | Output |
|---|---|---|
| **Intake** | `pvess init`, `pvess survey`, `pvess lookup` | new `inputs.yaml` from wizard, printable site-survey PDF, address-based pre-fill |
| **Design** | `pvess calc`, `pvess customer`, `pvess compare` | NEC `report.md`, customer-summary one-pager, scenario comparison PDF |
| **Submit** | `pvess permit`, `pvess dxf`, `pvess labels`, `pvess render` | 12-page permit PDF, DXF schematics, NEC label PDF, QET single-line |
| **Verify** | `pvess doctor`, `pvess symbols` | 28-check structural audit, symbol library swatch |

See **[Workflow → Intake](workflow/intake.md)** for the full guided tour.

---

## What's modelled

- **NEC 2017 / 2020 / 2023** — real per-version dispatch (not just a label).
  Sum-rule still legal under 2017, removed under 2020. RSD boundary
  voltage 80 V (2017) vs 30 V (2020+). See
  [recipes/add-nec-edition.md](recipes/add-nec-edition.md).
- **690.7 cold-Voc** — datasheet βVoc preferred; Table 690.7 fallback.
- **690.8 / 690.9** — PV source current ×1.25 with NEC 240.6 standard OCPD rounding.
- **705.12 interconnection** — sum / 120% / supply-side / center-fed,
  evaluated against actual busbar + main-breaker + existing solar.
- **706.10 / IRC R328** — ESS install-location compliance (setbacks +
  40 kWh indoor ceiling).
- **310.15(B) derating** — ambient temperature + conduit fill on every conductor.
- **250.66 / 250.122** — GEC + EGC sizing with **actual** GES inspection
  (rod count, water-pipe metal check, Ufer, existing GEC size).
- **NREL PVWatts + Mapbox** — address → annual kWh / county / lat-lng
  (optional online providers; env-var keys, fully offline-capable).

---

## What's still rough

- **NEC 2026** not yet shipped (just released; preview rules pending).
- **Multi-level roofs / dormers** — `RoofSection` supports rect / tri / polygon,
  but cross-section adjacency (ridge / valley topology) is K.2.9+ work.
- **Real-time online providers** beyond Mapbox + NREL.
- **Web UI / mobile** — currently CLI only.

---

## Where to go next

- **[Quickstart →](quickstart.md)** — 10-minute walkthrough on a real project
- **[Workflow guide →](workflow/intake.md)** — every phase, in order
- **[CLI reference →](reference/cli.md)** — every command + option
- **[Schema reference →](reference/schema.md)** — every `inputs.yaml` field
- **[Recipes →](recipes/add-ahj-profile.md)** — extend the tool

---

## License + scope

Internal tool. US residential market only. Not a substitute for a licensed
PE's seal. The NEC numbers it outputs need a real engineer's review before
permit submittal.
