# Web UI Language

This page is the copy standard for the **TGE Solar Project Generator**.
The Web UI uses English because the deliverables target North American
permit, utility, and engineering workflows.

## Product Name

Use **TGE Solar Project Generator** everywhere.

Avoid:

- PVESS Project Generator in user-facing UI
- Project Estimator as a product name
- Internal phase names such as W14 or K.12 on the page

## Core Terms

| Term | Meaning | Use |
|---|---|---|
| Project | One address + one selected system configuration | Project name, project history |
| Project template | Starting configuration such as PV + ESS or PV-only | Form selector |
| Address sample | Built-in example address used for smoke tests or demos | Optional form helper |
| Address lookup | Utility/AHJ/NEC/roof-data prefill from lookup providers | Button/API label |
| Preflight | Generation-before-check for schema, cost, intake, and code warnings | Button and panel |
| Package | Generated output bundle for review/handoff | Generate package, Delivery package |
| Preview | Embedded PDF/PNG review surface | Preview panel |
| Readiness | Source-material completeness for internal/AHJ review | Readiness panel |
| Source materials | Uploaded or simulated photos, bills, specs, and structural files | Source materials panel |
| BOM cost | Bill-of-materials cost estimate | Cost panel |
| Generated files | Complete artifact list | File panel |

## Button Language

Use direct verb phrases:

- `Lookup address`
- `Run preflight`
- `Generate package`
- `Download complete ZIP`
- `Load`
- `Rerun`
- `Delete`
- `Save`

Avoid vague verbs such as `Submit`, `Start`, `Process`, or `Do it` unless
the action is a final external submission.

## Status Language

Use these status labels consistently:

- `Estimate only` — not enough source material for internal review
- `Internal review` — generated package with known data gaps
- `AHJ-ready candidate` — strict source-data gate can be considered
- `Simulated source materials` — generated or assumed data
- `Field-uploaded source materials` — user uploaded real site data
- `Missing source data` — required item not present
- `Review before AHJ submission` — package has warnings or simulated data

## Mansfield Test Addresses

W17a keeps two Mansfield, TX addresses as realistic Web smoke-test inputs:

- `905 Crossvine Drive, Mansfield, TX`
- `2806 Green Circle Drive, Mansfield, TX`

Until utility bills are available, tests use a simulated DFW residential
monthly usage curve:

```text
880, 780, 720, 820, 1050, 1450, 1700, 1750, 1450, 1050, 820, 860
```

This is source-data **simulation**, not AHJ-ready utility evidence. The UI
should keep it visible as simulated until a real bill or Smart Meter Texas
export replaces it.
