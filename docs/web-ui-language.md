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
| Project basics | Address, client, AHJ, utility, and project type | First form section |
| Project type | Starting configuration such as PV + ESS or PV-only | Form selector |
| Try a sample address | Built-in example address used for smoke tests or demos | Optional form helper |
| Auto-fill from address | Utility/AHJ/NEC/roof-data prefill from lookup providers | Button/API label |
| Readiness check | Generation-before-check for schema, cost, intake, and code warnings | Button and panel |
| Estimate package | Generated output bundle for review/handoff | Generate button and delivery copy |
| Review preview | Embedded PDF/PNG review surface | Preview panel |
| Handoff readiness | Source-material completeness for internal/AHJ review | Readiness panel |
| Source materials and evidence | Uploaded or simulated photos, bills, specs, and structural files | Upload panel |
| BOM and quote estimate | Bill-of-materials and quote-level cost estimate | Cost panel |
| Generated deliverables | Complete artifact list | File panel |
| Estimate request | Public homeowner request submitted before operator review | Public lead page |
| Public leads | Internal queue of public estimate requests | Operator panel |
| Follow-up notes | Internal sales/design notes for a public lead | Lead row notes |
| Email follow-up draft | Operator-reviewed email text generated from a lead | Lead follow-up panel |
| Lead notification | Internal alert event created when a public lead arrives | Notification panel |
| Marketing attribution | UTM/referrer source attached to a public lead | Lead metrics panel |
| Load intake | Pre-fill the project form from a lead without generating output | Lead action |
| Run and review | Right-side operator console for readiness, progress, QA, previews, BOM, leads, and history | Operator panel |
| Package outputs | Output selection before generation | Generate panel |

## Button Language

Use direct verb phrases:

- `Auto-fill from address`
- `Check readiness`
- `Generate estimate package`
- `Request estimate`
- `Generate estimate`
- `Export CSV`
- `Email draft`
- `Load intake`
- `Archive`
- `Download complete ZIP`
- `Load form`
- `Rerun package`
- `Delete`
- `Save`

Avoid vague verbs such as `Submit`, `Start`, `Process`, or `Do it` unless
the action is a final external submission.

## Guidance Pattern

Lead users through the workflow in this order:

1. Enter project basics or choose a sample address.
2. Auto-fill address data when available.
3. Confirm site, system, service, roof, cost, and source evidence.
4. Check readiness before generation.
5. Generate the estimate package.
6. Review handoff readiness, preview artifacts, BOM/quote estimate, and
   generated deliverables.

For the public lead page, guide the homeowner toward the smallest useful input:
contact, address, project interest, usage, and bill upload. Do not expose
operator-only terms such as Package QA, AHJ-ready candidate, or artifact review
on the public page.

Use engineering terms when they are the user's decision point, such as AHJ,
NEC edition, interconnection, source materials, Package QA, and BOM. Avoid
internal-only terms as primary labels when a workflow label is clearer.

## Layout Pattern

Use a work-focused, scan-first layout:

- Keep product identity and security controls compact in the top bar.
- Use the workflow rail as navigation, not as explanatory marketing copy.
- Keep the intake form on the left and review/output state on the right on
  desktop screens.
- Keep the generate actions visible near the bottom of the viewport while the
  operator scrolls long forms.
- Prefer code-native layout tokens for day-to-day iteration. Bring in Figma
  only when collaborative mockups or reusable component specifications are
  needed.

## Status Language

Use these status labels consistently:

- `Estimate only` — not enough source material for internal review
- `Internal review` — generated package with known data gaps
- `AHJ-ready candidate` — strict source-data gate can be considered
- `Simulated source materials` — generated or assumed data
- `Field-uploaded source materials` — user uploaded real site data
- `Missing source data` — required item not present
- `Review before AHJ submission` — package has warnings or simulated data
- `New` — public lead received but not contacted
- `Contacted` — first outreach completed or in progress
- `Qualified` — lead has enough detail for estimate/design follow-up
- `Converted` — estimate package has been generated from the lead
- `Archived` — inactive lead hidden from the default active queue
- `Lead notification` — internal alert event created when a public lead arrives
- `Dry-run notification` — notification recorded locally without external send
- `Webhook failed` — external notification delivery failed; lead data is still saved
- `Marketing attribution` — source/campaign summary from public lead UTM data

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
