# Web UI

`pvess serve` starts the local browser workflow for TGE Solar project intake,
preflight, package generation, BOM review, and delivery-file download.

```bash
pvess serve --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`.

For a shared browser preview, protect the page and same-origin APIs with
Cloudflare Access or browser Basic Auth. For script/API automation, enable a
server-side access token:

```bash
pvess serve --host 0.0.0.0 --port 8765 --access-token "$PVESS_WEB_ACCESS_TOKEN"
```

The current operator page does not expose a token entry field. In the hosted
workflow, browser/session auth protects the page and same-origin API calls.
The token mode remains available for scripts and automation that can send the
`X-PVESS-Token` header.

API clients can authenticate with either:

- the admin/bootstrap token from `PVESS_WEB_ACCESS_TOKEN` or
  `pvess serve --access-token`
- an operator token created by an admin through `POST /api/operators`

Admin tokens can create operators and inspect all jobs. Operator tokens are
scoped to the jobs they create.

## Workflow

1. Fill **Project basics**, **Site and field data**, **System equipment**,
   **Service, roof, and cost assumptions**, and
   **Source materials and evidence**.
2. Optional: click **Check address**. Online mode uses configured
   Mapbox, NREL, and Google Solar providers when keys are available; offline
   mode uses only bundled utility/AHJ/NEC/rate datasets.
3. Run **Check readiness**. This checks schema validity, interconnection status,
   reference-profile intake gaps, ESS placement inputs, BOM cost, ITC cost,
   and payback sensitivity without writing a project package.
4. Select outputs and click **Generate estimate package**.
5. Review **Handoff readiness**, **Review preview**,
   **BOM and quote estimate**, and **Generated deliverables**.
6. Run **Package QA** when a generated package is ready for internal review.
7. Download **Complete Project ZIP** for handoff.

User-facing copy follows **[Web UI language](web-ui-language.md)**.
Production deployment details live in **[Web deployment](web-deployment.md)**.

## Operator Layout

The main page is organized as a dense operator workspace rather than a
marketing page:

- a compact top bar with product identity, public-request entry point, and
  optional operator token
- a sticky workflow rail for quick jumps through basics, site data, equipment,
  costs, evidence, and generation
- a left-side intake form and a right-side panel that behaves as a
  **Project checklist** during intake, then becomes **Review and generate** on
  the final step
- a sticky generate action bar so long intake forms keep the primary run
  actions visible

Design tooling stays code-first for now: layout tokens, spacing, borders, and
copy rules live in the static HTML/CSS and this documentation. Figma can be
introduced later when the page needs collaborative mocks or a reusable
component library, but it is not required for the current local-hosted
operator workflow.

## Wizard Intake

P10 changes the operator page from a single long intake form into a guided
wizard. The same browser form fields and generation API remain underneath, but
the operator now works through six reviewable steps:

1. **Project & Address** — system type, customer name, standard U.S. address,
   and an address-check result for utility, AHJ, and code basis.
2. **Usage & Goals** — monthly usage, simulated-vs-real source status, meter
   data, and ESS install constraints.
3. **System Equipment** — module, string, inverter, and battery selections.
4. **Electrical & Roof Costs** — service, interconnection, tariff, roof
   geometry, and cost assumptions.
5. **Evidence** — utility bill, site photos, structural letter, and spec
   sheets.
6. **Review & Generate** — output selection, readiness check, and package
   generation.

Each step validates only the inputs needed for that step. `Error` items block
**Continue**. `Warning` items remain visible but allow the operator to move on,
because many estimate-stage packages intentionally start with simulated site
data. The final generation still runs the full payload validation and
preflight checks.

Draft behavior has two layers:

- Browser autosave stores the current payload, step, and timestamp in
  `localStorage` so refresh/back navigation does not lose work.
- Authenticated operators can also save the same draft to the Web SQLite
  index through `/api/drafts`; the local draft remains available if an
  operator token is not present.

The UX standard for this flow is that the operator should never need to scroll
back through the full form to understand what is wrong. Step feedback, invalid
field highlighting, and the sticky Back / Save draft / Continue controls must
stay visible while completing each step.

## P11 Right Panel

P11 reduces attention cost in the right-side panel:

- Steps 1-5 show **Project checklist** only: current-step validation, next
  action, error count, warning count, and passed checks.
- Step 6 switches to **Review and generate**: readiness check, generation
  progress, delivery ZIP, handoff readiness, preview, BOM, generated files,
  and source-material status.
- Leads, recent projects, and Package QA are grouped under collapsed
  **Operator tools** so they are available without competing with intake.

The panel should read as guidance while the operator is entering facts, and as
a run console only when the operator intentionally reaches Review.

### Field UX Audit

P11 also audited every visible intake field from the user's point of view. The
main conclusion is that P12 should reduce typing by adding presets and hiding
estimate-only defaults, rather than deleting payload fields that downstream
generation still uses.

| Step | Field group | UX decision |
|---|---|---|
| Project | System type, customer name, standard U.S. address | Keep in the primary path. These are the only fields a normal user must know. |
| Project | Utility, AHJ, code basis | Keep visible as **Address check result**. These are derived from lookup and editable for correction, but should not block estimate-stage continuation. |
| Project | Project name, coordinates, APN, lookup mode, permit profile, sample project | Hide from the user path. Keep them as system metadata: project name is auto-generated, coordinates come from address lookup, permit profile and lookup mode use defaults, and APN is filled only when a parcel provider returns it. |
| Usage | Meter number, ESID | Keep typed; project-specific utility identifiers. |
| Usage | Meter location | Convert to select + Other in P12 (`Exterior garage wall`, `Exterior side wall`, `Basement`, `Meter bank`, `Other`). |
| Usage | ESS install location, roof condition, attic access | Already good as selects. Keep. |
| Usage | Door/window/egress setbacks | Hide until ESS location is indoor/garage. They are not useful for PV-only or unknown-location estimates. |
| Usage | Roof type, roof construction, roof framing | Convert to selects in P12 with common North American values and an Other option. |
| Usage | Roof height, decking thickness, roof layers | Keep numeric but move behind `Advanced roof details` unless AHJ-ready mode is selected. |
| Usage | Engineer firm/contact/address | Make a saved profile selector in P12. Default profile should fill these fields; manual editing should be advanced. |
| Usage | Installer company/address | Make a saved installer profile selector. For TGE-only operation these should be defaulted, not repeatedly typed. |
| Usage | Equipment coordinates | Hide behind `Advanced routing coordinates`; most users cannot enter these confidently without a site-plan drawing. |
| Usage | Monthly kWh | Keep textarea for pasted bills, but P12 should add monthly total presets and CSV/Smart Meter import affordance. |
| Equipment | Module, inverter, battery | Already good as selects. Keep one inverter brand/model family selected at a time. |
| Equipment | Module watts/brand/model, inverter model, battery kWh/model | These are read-only derived fields. P12 should visually mark them as derived or collapse them under equipment details. |
| Equipment | Modules, strings, inverter qty, battery qty | Keep numeric. P12 should offer steppers or suggested package sizes. |
| Equipment | AC output amps | Usually derived from selected inverter. Keep editable only under advanced override. |
| Electrical | Main breaker, busbar | Convert to standard amperage selects in P12 (`100/125/150/175/200/225/400`). |
| Electrical | Interconnection, export tariff | Already good as selects. Keep. |
| Electrical | Self-consumption | Replace raw 0-1 input with a scenario select in P12 (`PV-only`, `PV+ESS typical`, `High backup/load shifting`, `Custom`). |
| Electrical | PV turnkey $/W, inverter cost, battery cost | Keep for quoting, but show as BOM cost assumptions rather than general electrical inputs. |
| Electrical | Roof pitch, azimuth, width, height | Keep for manual fallback. P12 should prefer roof lookup/manual roof editor and make raw dimensions advanced. |
| Evidence | Source mode, files, photos | Keep. P12 should show required-vs-optional status by selected mode and output target. |
| Review | Output checkboxes | Keep. They are explicit and understandable. |

### P10 Testing Plan

User-experience testing must cover more than API success:

- first-screen comprehension: the first viewport shows one step, not the full
  long form
- step feedback: invalid inputs produce field-level highlights and clear
  messages before the operator can continue
- warning tolerance: simulated evidence and missing AHJ-ready attachments warn
  without blocking estimate generation
- navigation safety: Back and completed-step navigation preserve entered data
- draft safety: manual save and refresh restore the payload and current step
- lead/history safety: **Load intake** and **Load form** enter the wizard with
  the prefilled payload visible
- responsive safety: desktop keeps intake plus review side-by-side, while
  mobile collapses to one column with no horizontal overflow

### P10 Closing Standards

- No step displays more than one task group as the primary form surface.
- Every **Continue** click runs current-step validation and focuses the first
  blocking field when present.
- Errors, warnings, and passed checks are visually distinct and readable.
- Save draft works locally without a token and server-side when authenticated.
- Back/Continue/step navigation never clears entered values.
- Final generation remains compatible with the existing `/api/projects/form`
  payload and file-upload path.
- Browser QA includes at least one failed-step path, one successful
  multi-step path, draft restore, and a mobile viewport check.

## Public Lead Intake

`/lead` serves a lightweight public estimate-request form for homeowners. It
collects contact details, project interest, address, optional utility, average
or 12-month usage, notes, and an optional utility bill or Smart Meter Texas
export.

`POST /api/leads` stores the request in the Web SQLite index and copies any
uploaded bill under `<workdir>/leads/<lead_id>/`. If the utility upload contains
12 valid monthly kWh values, those values are attached to the lead.

The public page also captures campaign attribution from the landing URL:
`utm_source`, `utm_medium`, `utm_campaign`, and `utm_content`, plus browser
referrer and landing URL. Operators can search these fields, export them in
CSV, and review aggregate source/campaign metrics from the protected Web UI.

The internal **Public leads** panel is visible in the main operator UI after
login. Operators can filter by status, search by name/email/address, save
follow-up notes, update lifecycle status, archive inactive leads, export the
visible queue to CSV, view the active lead digest, prepare a follow-up email
draft, review lead notification delivery, load intake fields back into the
project form, and click **Generate estimate**. Lead conversion creates an
estimate-only package:

- customer summary enabled
- permit, DXF, labels, and QET disabled
- source material mode set to `simulated`
- battery omitted for PV-only leads

Converted leads keep the generated job ID so operators can reopen the package
from the lead row.

Lead statuses are:

- `new`
- `contacted`
- `qualified`
- `converted`
- `archived`

Archived leads are hidden from the default active queue but remain available
through the `Archived` filter and CSV export.

P6 follow-up helpers are intentionally local-first. The system generates a
mailto draft and prefilled payload, but it does not send email or submit a
permit package without an operator action.

P7 lead notifications are audit-first. Every new public lead creates a
notification event in SQLite. The default `dry_run` mode records the event and
marks it sent without contacting an external service. Setting
`PVESS_LEAD_NOTIFICATION_MODE=webhook` and
`PVESS_LEAD_NOTIFICATION_WEBHOOK_URL` sends the same event payload to a
configured webhook; failures are recorded in the operator panel and can be
retried without blocking the homeowner submission.

P8 marketing attribution is operator-only. `GET /api/leads/metrics` summarizes
lead totals, conversion count, conversion rate, source mix, and campaign mix.
The endpoint requires the same admin/operator token as the internal lead list.

## Address Lookup

`/api/lookup/address` returns provider provenance and a `suggested_payload`
that the browser can apply to form fields. It can prefill utility, AHJ, NEC
edition, coordinates, export tariff, and best available roof-section defaults.
Provider misses are surfaced as low-confidence data instead of blocking the
project form. When lookup returns multiple roof faces, the UI lists candidate
sections with pitch, azimuth, and area so the operator can choose a roof face
instead of accepting only the automatic best match.

## Address Input

Project basics uses standard U.S. address fields in the primary path:

- Street address
- Unit / suite
- City
- State
- ZIP code

The browser composes these into the existing `site_address` and `location`
payload fields for lookup, preflight, and generation. If the project name
override is blank, it also generates a project name from the street address and
system type.

Utility, AHJ, and NEC code basis appear under **Address check result**. They
are editable because lookup data can be incomplete, but they are not required
knowledge for a customer starting an estimate.

Project title overrides, coordinates, permit profile, lookup mode, and sample
projects are hidden from the normal UI. They remain in the DOM/payload as system
metadata so operators can still run smoke tests and downstream generation keeps
the same schema contract.

Parcel/APN is also hidden from the user path. `_lookup_suggested_payload()` will
map `apn`, `parcel_id`, `parcel_number`, `property_id`, `account_number`, or
`cad_account_number` into the project APN field when a county parcel provider is
configured. The built-in Mapbox/NREL/Google Solar providers do not currently
guarantee APN data.

## Source Materials

The form accepts:

- PV-7 site photos: front elevation, roof, meter, main panel, sub-panel, and
  equipment location.
- Unsorted site photos. The Web intake helper classifies these by filename
  into the closest PV-7 kind and keeps the classification visible for review.
- Utility bill or usage export.
- Signed structural letter PDF.
- Manufacturer spec sheets for module, inverter, battery, racking, and
  optimizer.
- Unsorted spec sheets. The intake helper classifies module, inverter,
  optimizer, racking, and battery PDFs by filename and reports coverage for
  the equipment selected in the form.

Uploaded files are copied into `source_materials/` under the generated job
directory and listed in `simulated-site-data.yaml` so simulated or missing
inputs remain visible before AHJ submission.

If a utility upload contains 12 valid monthly kWh values, those values replace
form/simulated monthly usage in the generated `inputs.yaml`. The source status
records whether monthly usage came from the form or from a parsed utility
file.

## Generated Files

Every run writes:

- `inputs.yaml`
- `request.json`
- `output/calculation.json`
- `output/report.md`
- `output/bom-cost.json`
- `output/bom-cost.csv`
- `output/reference-readiness.md`
- `output/real-data-checklist.md`
- `output/artifact-manifest.json`
- `output/project-package-<job>.zip`

Optional outputs add customer PDF, permit PDF, DXF/PNG previews, NEC labels,
and QET.

PDFs and PNG sheet previews render inside the **Preview** panel. Direct
Open/download links remain available for external PDF viewers and CAD review.
The preview grid also shows document/sheet thumbnails for PDFs, Markdown
reports, and PNG previews.

Each generated artifact can be marked:

- `not reviewed`
- `needs revision`
- `approved for internal review`

Review state is stored in `review-status.json` inside the job folder and is
served through `/api/jobs/<job_id>/reviews`.

## AHJ Gate

The **Readiness** panel includes a package gate:

- `Estimate only` — useful for sizing/cost preview; never AHJ-ready.
- `Internal review` — real source-material mode is selected, but required
  evidence, outputs, or field data still need review.
- `AHJ-ready candidate` — source evidence and selected deliverables satisfy
  the Web gate and the package can move to formal engineering/AHJ review.

Simulated source materials can never produce `AHJ-ready candidate`. The gate
also blocks missing parsed utility usage, signed structural packet, selected
equipment spec sheets, PV-7 photos, roof/field data, selected permit/DXF/label
outputs, package QA that has not passed, generated artifacts marked
`needs revision`, and required generated artifacts that have not been marked
`approved for internal review`.

## Package QA

After a project package completes, click **Run package QA** to create:

- `output/package-qa.json`
- `output/package-qa.md`

The QA pass runs `pvess-doctor`, verifies the Complete Project ZIP can be read,
and checks generated PDFs for page count and searchable text. The job result is
updated with the QA status and the ZIP is rebuilt so the QA reports are included
in the handoff archive. A package cannot reach `AHJ-ready candidate` until
Package QA is `PASS` and the required handoff artifacts have been approved in
the Preview review controls. The Readiness panel shows the required artifact
approval count and each required artifact's current review status.

## History

Recent projects can be viewed, loaded back into the form, rerun, or deleted from
the browser UI. Loading a job restores the JSON request payload. Browser file
inputs cannot be restored by JavaScript, so attach new files before rerunning
with changed uploads.

Job history is indexed in SQLite at `<workdir>/web-jobs.sqlite3`. Generated
artifacts stay in their job folders; SQLite stores searchable metadata,
payload summaries, source-material/readiness status, and artifact records.
Existing filesystem-only jobs with `job-status.json` are imported into the
index the first time history is listed. New W19 jobs also store `owner_id` so
history, payload loading, rerun, delete, and file download permissions can be
scoped by operator.

The **Recent projects** panel can filter by status, project/address text, and
created date range. The same filters are available through `/api/jobs` using
`status`, `q`, `created_from`, `created_to`, and `limit` query parameters.
Admins can add `all_jobs=true` or select **All jobs** in the UI for internal
support review. Operators cannot enable all-jobs mode.

Each project row shows its current AHJ gate level and Package QA status, so
operators can distinguish estimate-only packages from QA-cleared handoff
candidates without opening every job.

## Operators

When access-token mode is enabled, create operator tokens with the admin token:

```bash
curl -X POST http://127.0.0.1:8765/api/operators \
  -H "X-PVESS-Token: $PVESS_WEB_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"operator_id":"designer-1","display_name":"Designer 1"}'
```

The response includes the operator token once. Store it in the script or
automation secret that sends the `X-PVESS-Token` header. The server stores only
a hash of the token.
