# Web UI

`pvess serve` starts the local browser workflow for TGE Solar project intake,
preflight, package generation, BOM review, and delivery-file download.

```bash
pvess serve --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`.

For a shared preview machine, protect API and generated-file routes with a
token:

```bash
pvess serve --host 0.0.0.0 --port 8765 --access-token "$PVESS_WEB_ACCESS_TOKEN"
```

The static page still loads, then the browser sends the saved access token
with API requests and generated-file preview/download URLs.

The same token field accepts either:

- the admin/bootstrap token from `PVESS_WEB_ACCESS_TOKEN` or
  `pvess serve --access-token`
- an operator token created by an admin through `POST /api/operators`

Admin tokens can create operators and inspect all jobs. Operator tokens are
scoped to the jobs they create.

## Workflow

1. Fill **Project basics**, **Site and field data**, **System equipment**,
   **Service, roof, and cost assumptions**, and
   **Source materials and evidence**.
2. Optional: click **Auto-fill from address**. Online mode uses configured
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
- a left-side intake form and a right-side **Run and review** console for
  readiness, progress, QA, previews, BOM, leads, and recent projects
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

1. **Project & Address** — project type, client, address, AHJ, utility, NEC,
   permit profile, and address lookup.
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

## Address Samples

The **Try a sample address** selector keeps a few realistic smoke-test inputs
in the UI. W17a includes these Mansfield, TX samples:

- `905 Crossvine Drive, Mansfield, TX`
- `2806 Green Circle Drive, Mansfield, TX`

Both use the DFW simulated residential monthly usage curve documented in
**[Web UI language](web-ui-language.md)** until a real utility bill or Smart
Meter Texas export is uploaded.

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

The response includes the operator token once. Store it in the browser token
field for that operator. The server stores only a hash of the token.
