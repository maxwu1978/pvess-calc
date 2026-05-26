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

1. Fill **Project basics**, **Usage and site basics**, **System equipment**,
   **Service, roof, and cost assumptions**, and
   **Source materials and evidence**.
2. Optional: click **Check address**. Online mode uses configured
   Mapbox, NREL, and Google Solar providers when keys are available; offline
   mode uses only bundled utility/AHJ/NEC/rate datasets.
3. In **Roof and usage**, build the roof preview and complete the Step 2
   roof workflow before relying on permit drawings. The workflow reviews the
   satellite image, roof-outline candidate, saved topology draft, and panel
   layout count.
4. In **Review and generate**, choose a package type: customer estimate,
   engineering review, or AHJ-ready candidate.
5. Run **Check readiness**. This checks schema validity, interconnection status,
   reference-profile intake gaps, ESS placement inputs, BOM cost, ITC cost,
   and payback sensitivity without writing a project package.
6. Confirm selected deliverables and click **Generate package**.
7. Review generated artifacts in the **Package review workspace**. The
   workspace paginates package overview, each PDF/PNG preview, BOM/cost,
   source materials, all deliverables, and final handoff.
8. Run **Package QA** when a generated package is ready for internal review.
9. Download **Complete Project ZIP** for handoff.

User-facing copy follows **[Web UI language](web-ui-language.md)**.
Production deployment details live in **[Web deployment](web-deployment.md)**.

## Operator Layout

The main page is organized as a dense operator workspace rather than a
marketing page:

- a compact top bar with product identity and public-request entry point
- a sticky workflow rail for quick jumps through basics, site data, equipment,
  costs, evidence, and generation
- a left-side intake form and a right-side panel that behaves as a compact
  **Step status** during intake, then becomes **Review and generate** on the
  final step
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
4. **Electrical & Roof Costs** — service amperage, interconnection
   preference, utility tariff, usage behavior, roof fallback, and cost
   assumptions.
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

## OSR Roof Topology Workflow

OSR3-OSR12 make Step 2 the source of truth for the roof model used by
downstream permit sheets.

Step 2 now emits one `roof_topology` status object with four checks:

- **OSR3 Roof evidence** — satellite image, uploaded roof photo, or accepted
  manual trace evidence exists.
- **OSR4 Roof outline** — a satellite, draft, or manually edited polygon
  outline is available.
- **OSR5 Topology draft** — the accepted `site.ee4_trace` has an outline plus
  roof lines/facets and fire-pathway candidates.
- **OSR6 Panel layout preview** — traced module geometry matches the project
  module count and clears blocking layout lints.

Every generated project writes:

- `output/roof-workflow-validation.json`
- `output/roof-workflow-validation.md`

These files are the repeatable real-address validation record. They capture
the input address, coordinates, satellite crop mode, Step 2 stage, module
count match, accepted trace state, R8 status, and the OSR3-OSR6 check rows.

When the satellite mask is too broad, the operator can use **Editable roof
outline** in Step 2. The tool supports:

- tighten/expand by 5 percent around the outline centroid
- direct vertex coordinate edits
- add/remove vertex controls
- saving the edited outline as reviewed `site.ee4_trace`

Saving an edited outline regenerates the package. The backend completes
missing roof lines and fire-pathway candidates, then derives a polygon
`roof_section` from the accepted trace. That keeps EE-4, PV-1/PV-4/PV-6,
module placement, and layout QA aligned to the same reviewed topology instead
of falling back to provider roof-segment boxes.

The `pvess-roof-topology-vision` skill is exposed through
`POST /api/jobs/{job_id}/roof-topology/proposal`. It generates reviewable
proposal artifacts under `output/roof-topology-vision/`:

- `site-ee4-trace-proposed.yaml`
- `roof-topology-review.pdf`
- `roof-topology-qa.json`
- `roof-topology-qa.md`

The skill is an assistant, not the final drafter. Model or deterministic
output must still pass PVESS structured validation, module-count matching,
setback/fire-pathway checks, and operator review before acceptance.

## P11 Right Panel

P11 reduces attention cost in the right-side panel:

- Steps 1-5 show compact **Step status** only: step number, a short outcome
  such as **Address verified**, and error/warning/check counts. Detailed cards
  appear only when a step has an error or warning.
- Field-level error and warning text is written directly below the affected
  input whenever a step check identifies a specific field.
- Step 6 switches to **Review and generate**: project summary, package type,
  selected deliverables, readiness check, then a paginated
  **Package review workspace** after a package is generated.
- After generation, Step 6 enters **Review Focus Mode**. The right panel and
  generation action bar are hidden, the review workspace expands to full
  width, and a compact sticky status bar shows page position, required
  approvals, readiness, Package QA, and ZIP state.
- Step 6 is the only place for the full **Review checklist**, including
  readiness, blocking issues, estimate warnings, AHJ-ready evidence gaps,
  selected deliverables, and Package QA access.
- Generated file review no longer lives in the right panel. The right panel
  remains a lightweight status rail before generation; after generation,
  detailed status moves into the **Status details** drawer.

The panel should read as guidance while the operator is entering facts, and as
a run console only when the operator intentionally reaches Review.

### Field UX Audit

P11/P12 also audited every visible intake field from the user's point of view.
The main conclusion is that customer-facing steps should collect only data a
homeowner can answer confidently, while AHJ-ready, structural, and routing
fields stay in hidden payload defaults or the Review checklist.

| Step | Field group | UX decision |
|---|---|---|
| Project | System type, customer name, standard U.S. address | Keep in the primary path. These are the only fields a normal user must know. |
| Project | Utility, AHJ, code basis | Keep visible as **Address check result**. These are derived from lookup and editable for correction, but should not block estimate-stage continuation. |
| Project | Project name, coordinates, APN, lookup mode, permit profile, sample project | Hide from the user path. Keep them as system metadata: project name is auto-generated, coordinates come from address lookup, permit profile and lookup mode use defaults, and APN is filled only when a parcel provider returns it. |
| Usage | Usage source, average monthly kWh, 12 monthly kWh | Keep in the primary path. Local default is the default, average monthly kWh is the simplest manual input, and 12-month detail is available when the user has bills. |
| Usage | Meter location | Keep optional as a select. It improves plan callouts but does not block an estimate. |
| Usage | ESS install location | Keep when battery is selected. Hide the entire block for PV-only scope. |
| Usage | Door/window/egress clearances | Hide from the customer path. Keep the internal fields for AHJ/IRC checks, but verify them from photos, site survey, or operator review instead of asking the homeowner to type measurements. |
| Usage | Roof material | Keep as a simple select. Detailed roof structure stays in Review/AHJ-ready checklist. |
| Usage | Meter number, ESID, roof height, construction, framing, condition, attic access, decking, roof layers | Hide from the customer path. These are AHJ/structural review fields collected from utility bills, photos, site survey, or operator review. |
| Usage | Engineer firm/contact/address, installer details, equipment coordinates | Hide from the customer path. Engineer/installer values are profile/default data; coordinates are internal routing inputs. |
| Equipment | Module, inverter, battery | Split into three visible sections: PV modules, Inverter, and Battery. Keep one inverter brand/model family selected at a time; battery package follows the selected inverter brand. |
| Equipment | Module watts/brand/model, inverter model, battery kWh/model | These are read-only derived fields. P12 should visually mark them as derived or collapse them under equipment details. |
| Equipment | Modules, strings, inverter qty, battery qty | Keep numeric. P12 should offer steppers or suggested package sizes. |
| Equipment | AC output amps | Usually derived from selected inverter. Keep editable only under advanced override. |
| Electrical | Main breaker, busbar | Standard amperage selects (`100/125/150/175/200/225/400`). |
| Electrical | Interconnection, export tariff | Customer-facing selects with engineering-friendly labels. |
| Electrical | Self-consumption | Scenario select mapped to the underlying 0-1 calculation value. |
| Electrical | PV turnkey $/W, inverter cost, battery cost | PV $/W stays visible for quoting; inverter/battery overrides are advanced. |
| Electrical | Roof pitch, azimuth, width, height | Manual fallback remains in advanced roof geometry; address lookup and evidence should replace it when available. |
| Evidence | Source mode, files, photos | Keep as an evidence-level choice plus bulk uploaders. Full required-vs-optional status belongs in Review. |
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

Step 5 is an evidence collection step, not another engineering data-entry
sheet. The normal user path exposes:

- Evidence mode: quick estimate with simulated evidence, or uploaded field
  evidence.
- Utility bill or Smart Meter export.
- One bulk site-photo uploader. The Web intake helper classifies these by
  filename into PV-7 targets: front elevation, roof/array area, meter, main
  panel, sub-panel/load center, and equipment location.
- A collapsed engineering-documents area for signed structural letters and
  missing manufacturer documents.

Per-equipment spec sheet upload fields are intentionally hidden from the main
path. The system-selected equipment should use internal library references
first; uploaded spec PDFs are for custom equipment, missing library references,
or AHJ-ready review support.

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

PDFs and PNG sheet previews render inside the Step 6
**Package review workspace** as separate review pages. Direct Open/download
links remain available for external PDF viewers and CAD review. The final
handoff page centralizes readiness, Package QA, required artifact approvals,
blocking items, and ZIP download.

The **Status details** drawer is the only expanded status surface during
Review Focus Mode. It contains readiness warnings, blocking items, Package QA,
and required artifact approvals without permanently reducing PDF or drawing
preview width.

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
the paginated review workspace. The Step 6 status rail shows the required
artifact approval count, while the final handoff page shows each required
artifact's current review status.

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
