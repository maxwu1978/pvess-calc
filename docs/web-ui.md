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

## Public Lead Intake

`/lead` serves a lightweight public estimate-request form for homeowners. It
collects contact details, project interest, address, optional utility, average
or 12-month usage, notes, and an optional utility bill or Smart Meter Texas
export.

`POST /api/leads` stores the request in the Web SQLite index and copies any
uploaded bill under `<workdir>/leads/<lead_id>/`. If the utility upload contains
12 valid monthly kWh values, those values are attached to the lead.

The internal **Public leads** panel is visible in the main operator UI after
login. Operators can refresh the list, see which leads have usage data, and
click **Generate estimate**. Lead conversion creates an estimate-only package:

- customer summary enabled
- permit, DXF, labels, and QET disabled
- source material mode set to `simulated`
- battery omitted for PV-only leads

Converted leads keep the generated job ID so operators can reopen the package
from the lead row.

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
