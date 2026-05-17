# Quickstart

10-minute walkthrough: install the tool, generate a complete permit
package + customer-friendly summary for an existing demo project, then
verify everything with the doctor.

## Install

```bash
git clone <repo>
cd 11CAD家庭储能

# Create venv + install in editable mode
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Editable install means subsequent `git pull` is enough — no reinstall.

## Generate a permit package

The repo ships with two demo projects:

```bash
ls projects/
# 001-demo-austin     002-phoenix-25kw
```

Generate everything for the Phoenix project (25 kW PV + 41 kWh ESS,
3 hybrid inverters, supply-side tap):

```bash
pvess pipeline submit projects/002-phoenix-25kw/
```

Pipeline output:

```
[1/4] pvess calc projects/002-phoenix-25kw
[2/4] pvess permit projects/002-phoenix-25kw
[3/4] pvess dxf --preview projects/002-phoenix-25kw
[4/4] pvess doctor projects/002-phoenix-25kw

  ✓ all 28 check(s) passed

✓ Submit pipeline complete — ready for AHJ.
  Package: projects/002-phoenix-25kw/output/permit-package-002-phoenix-25kw.pdf
```

## What got built

```bash
ls projects/002-phoenix-25kw/output/
```

| File | Purpose | Size |
|---|---|---|
| `permit-package-002-phoenix-25kw.pdf` | 12-page AHJ submittal | ~800 KB |
| `report.md` | Engineering NEC report (markdown) | ~5 KB |
| `calculation.json` | Machine-readable calc dump | ~15 KB |
| `sheet-EE-1.dxf` / `.png` | Three-line diagram | ~135 KB / 75 KB |
| `sheet-EE-2.dxf` / `.png` | Grounding & bonding | ~75 KB / 60 KB |
| `customer-summary.pdf` | Homeowner one-pager (if generated) | ~40 KB |
| `system.qet` | QElectroTech single-line | ~30 KB |

## Inspect the permit PDF

```bash
open projects/002-phoenix-25kw/output/permit-package-002-phoenix-25kw.pdf
```

The 12 pages:

| # | Sheet | What's on it |
|---|---|---|
| 1 | EE-0 | Cover sheet (client / engineer / installer / sheet index / PE stamp box) |
| 2 | EE-1 | Three-line diagram |
| 3 | EE-2 | Grounding & bonding (per-equipment EGC + GES) |
| 4 | EE-3 | Panel schedules (MSP + sub-panels) |
| 5 | EE-4 | Site plan (lot + house + array + equipment route) |
| 6 | PV-4 | Attachment plan (per-roof-section shapes + module grid) |
| 7 | PV-5 | Mounting details (rail / flashing / anchor) |
| 8 | PV-6 | String layout plan (color-coded strings on roof outlines) |
| 9 | EE-5 | NEC compliance checklist |
| 10 | PV-N | General + electrical notes |
| 11-12 | Labels | NEC 690/706/705 placards |

## Run for your own project

```bash
# Create a new project via the interactive wizard
pvess init 003-jones-residence --address "Los Angeles, CA"

# Wizard pre-fills utility / AHJ / NEC edition / ASHRAE / export tariff
# from the address. Answer prompts (or accept defaults).

# After wizard completes:
pvess pipeline submit projects/003-jones-residence/
```

Need NREL irradiance + lat/lng to refine ROI? Add API keys (optional):

```bash
# In your terminal — NEVER paste tokens into a chat:
cp .env.example .env
$EDITOR .env       # paste PVESS_MAPBOX_TOKEN + PVESS_NREL_API_KEY

# Verify keys are loaded (prints fingerprint only)
pvess lookup
```

See **[Workflow → Intake](workflow/intake.md)** for what each subcommand
does and when to use it.

## Run the tests

```bash
pytest -q
```

You should see ~360 tests pass in ~30 s.

## Help, my project fails the doctor

The doctor runs 28 structural checks. A common case for new projects:

```
FAIL  export_tariff_matches_state    project location is CA but
                                     loads.export_tariff_model = '1to1_nem';
                                     expected 'ca_nem3'
```

Fix: edit `projects/<id>/inputs.yaml` and set
`loads.export_tariff_model: "ca_nem3"`. See
**[Workflow → Verify](workflow/verify.md)** for the full check inventory.
