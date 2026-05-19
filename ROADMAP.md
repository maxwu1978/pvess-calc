# pvess-calc Roadmap

Forward-looking plan. `CHANGELOG.md` tracks past work in date order;
this file tracks **next-N K-phases** with scope, closing standards,
and rough estimates.

When a K-phase ships:
1. Move its section from "Planned" → "Done" with a date
2. Bump the corresponding entry into `CHANGELOG.md` proper
3. Re-evaluate priority of remaining planned phases

---

## Planned

No active Web phases are queued after P0. Next planned engineering work
should be selected from the non-Web backlog below after another generated
package review pass.

## Completed Milestones

### Web Ops P0 — Cloudflare production stabilization ✅ DONE 2026-05-19

Goal: turn the W30 local tunnel profile into a stable operator-managed
production path for `https://tge.reelamate.com`.

Completed:

- Added `reelamate.com` to Cloudflare and confirmed the zone became active.
- Switched registrar nameservers to the Cloudflare-assigned nameservers.
- Recreated the existing apex and `www` records in Cloudflare to preserve the
  existing Vercel-hosted site.
- Created the `tge.reelamate.com` Cloudflare Tunnel route.
- Moved the runtime checkout to `~/Services/pvess-calc` to avoid Desktop
  privacy restrictions under launchd.
- Installed user LaunchAgents for the local Web service and the Cloudflare
  Tunnel.
- Added a curl-based public smoke script for the Cloudflare route.
- Added a local workdir backup script for `~/.pvess/reelamate-web`.
- Added a P0 operator runbook covering health checks, restart, logs, backup,
  and token rotation.

Closing standards met:

- Public index, authenticated `/api/health`, and `/assets/app.js` load through
  `https://tge.reelamate.com`.
- Local loopback smoke passes against `http://127.0.0.1:8765`.
- The app remains loopback-only; public ingress is through Cloudflare Tunnel.
- Runtime secrets stay in local env/token files and are not committed.
- Generated jobs remain on local persistent storage outside the repo.

### Web UI W30 — local Cloudflare Tunnel profile ✅ DONE 2026-05-19

Goal: expose the local workstation-hosted TGE Solar Project Generator at
`https://tge.reelamate.com` without requiring an immediate Docker VPS.

Completed:

- Confirmed current DNS state: `tge.reelamate.com` has no A/CNAME record and
  `reelamate.com` is still delegated to Spaceship nameservers.
- Documented the required Cloudflare precondition: add the zone to Cloudflare,
  switch nameservers, and recreate any existing apex / `www` records before
  routing the tunnel hostname.
- Added `deploy/reelamate/local-tunnel/.env.example` for the local Web token,
  port, workdir, and optional lookup-provider API keys.
- Added `deploy/reelamate/local-tunnel/run-local.sh` to start `pvess serve`
  on `127.0.0.1` with persistent local storage.
- Added `deploy/reelamate/local-tunnel/cloudflared-config.example.yml` mapping
  `tge.reelamate.com` to `http://127.0.0.1:8765`.
- Added an operator runbook for installing `cloudflared`, creating the tunnel,
  routing DNS, starting both processes, and running `pvess web-smoke`.
- Retargeted the Docker/Caddy fallback deployment from `pvess.reelamate.com`
  to `tge.reelamate.com`.

Closing standards met:

- The local app remains loopback-only; the tunnel is the only public ingress.
- No secrets are committed; operators copy `.env.example` to `.env`.
- Persistent generated files stay outside the repo under
  `~/.pvess/reelamate-web` by default.
- The public validation path uses `pvess web-smoke` against
  `https://tge.reelamate.com`.

### Web UI W29 — reelamate.com deployment profile ✅ DONE 2026-05-19

Goal: make the existing `reelamate.com` domain usable as the public entry
point for the TGE Solar Project Generator without breaking the current apex /
`www` Vercel DNS records.

Completed:

- Confirmed current DNS: `reelamate.com` and `www.reelamate.com` point to
  Vercel.
- Added the initial dedicated-subdomain deployment profile so the apex domain
  can remain untouched. W30 retargeted the hostname to `tge.reelamate.com`.
- Added `deploy/reelamate/docker-compose.yml` for the PVESS Docker image,
  persistent `/data/pvess-web` storage, and provider API-key env passthrough.
- Added `deploy/reelamate/Caddyfile` to terminate TLS and reverse proxy to the
  FastAPI container.
- Added `deploy/reelamate/.env.example` and `deploy/reelamate/README.md` with
  DNS, token, smoke-check, and backup commands.
- Updated Web deployment docs with the reelamate rollout path and a warning
  that the current app should not be deployed as Vercel serverless without a
  storage redesign.

Closing standards met:

- Deployment profile keeps generated jobs, uploaded evidence, PDFs, DXFs, ZIPs,
  and `web-jobs.sqlite3` on a persistent Docker volume.
- TLS and reverse proxy settings are explicit.
- `docker compose ... config` validates the compose file.
- Production validation path uses `pvess web-smoke` against the dedicated
  generator hostname.

### Web UI W28 — generated package review pass ✅ DONE 2026-05-19

Goal: validate the current Web system as an end-to-end internal review path
using simulated site data for the two Mansfield test addresses.

Review matrix:

| Address | Variant | Result |
|---|---|---|
| 905 Crossvine Drive, Mansfield, TX | PV-only | Generated, QA ran, ZIP valid |
| 905 Crossvine Drive, Mansfield, TX | PV + ESS | Generated, QA ran, ZIP valid |
| 2806 Green Circle Drive, Mansfield, TX | PV-only | Generated, QA ran, ZIP valid |
| 2806 Green Circle Drive, Mansfield, TX | PV + ESS | Generated, QA ran, ZIP valid |

Completed:

- Generated all four Web packages through the Web API path with customer PDF,
  permit PDF, DXF/PNG previews, NEC labels, QET, BOM, manifests, and ZIP.
- Ran Package QA for each package; all four completed with zero FAIL results.
- Verified each ZIP is readable and includes `output/package-qa.json` and
  `output/package-qa.md`.
- Verified gate behavior: initial packages were blocked by `NOT_RUN` QA and
  pending artifact review; after QA they remained `Estimate only` because
  source data was simulated; after approving required artifacts, pending
  review count dropped to zero while simulated source data still prevented AHJ
  submission.
- Rendered and visually checked representative PV + ESS pages: cover,
  property plan, PV-4 attachment plan, EE-1 string plan, EE-2 three-line,
  EE-2.1 one-line, PV-6 notes, PV-7 photos, SPEC placeholder, NEC labels, and
  customer summary.

Findings:

- No W28 blocker found. Permit PDFs were 17 pages, labels PDFs were 2 pages,
  and customer summaries rendered searchable text.
- Package QA status is `WARN`, not `PASS`, for the simulated packages. The
  warnings are expected for missing signed structural/spec attachments,
  simulated PV-7 photos, missing site/property geometry, and field-proof items.
- `ee4_preview_visual_lint` still warns that one fire-offset label is close to
  or outside the frame. Treat as a visual-polish follow-up after real site
  geometry/satellite data is introduced.
- Permit pages 9-10 are visually readable but have low extracted text because
  the DXF-derived sheets are embedded as drawing previews. This remains a QA
  warning, not a generation failure.

Closing standards met:

- Both Mansfield addresses generate complete Web packages for PV-only and
  PV + ESS.
- Package QA runs and persists QA artifacts into the ZIP for every package.
- Readiness and artifact approval gate behavior matches W25-W27 rules.
- Representative rendered sheets show no blank pages, broken tables, or
  obvious text/image collisions.

### Web UI W27 — handoff review visibility ✅ DONE 2026-05-19

Goal: make the W26 artifact-approval gate visible enough for an operator to
clear it without reading raw blocker text.

Completed:

- Added per-required-artifact review rows to the AHJ gate response.
- The Readiness panel now shows required artifact approval progress and a
  status line for each required handoff artifact.
- Added color treatment for approved vs pending review states.
- Updated Web docs and regression coverage for the response/UI contract.

Closing standards met:

- Gate responses include label/path/status for every required artifact review.
- The browser Readiness panel exposes approval counts and required artifact
  statuses.
- Existing W26 blocking behavior remains unchanged.

### Web UI W26 — review-gated AHJ handoff ✅ DONE 2026-05-19

Goal: close the handoff loop so a package cannot become AHJ-ready just because
automated QA passed; core generated artifacts must also be internally approved.

Completed:

- Added required-artifact review checks to the AHJ gate.
- Permit PDF, NEC label PDF, DXF sheets, PNG previews, and generated Package QA
  reports now block `AHJ-ready candidate` until marked `approved_internal`.
- Gate responses now include required/pending artifact review counts.
- Updated Web docs to make the manual review requirement explicit.

Closing standards met:

- A real-source package with strict readiness PASS, generated selected outputs,
  and Package QA PASS remains `Internal review` when required artifacts have
  not been approved.
- The same package can become `AHJ-ready candidate` once required artifacts are
  marked `approved_internal`.
- Regression tests cover both the blocked and cleared paths.

### Web UI W25 — QA-gated AHJ handoff ✅ DONE 2026-05-19

Goal: make Package QA an actual gate for AHJ-ready handoff, not just a
sidecar report.

Completed:

- Added Package QA status to AHJ gate checks.
- Packages now remain `Internal review` until Package QA is `PASS`; missing,
  WARN, or FAIL QA states block `AHJ-ready candidate`.
- Running Package QA automatically refreshes the job's readiness gate and
  persists the updated gate in `job-status.json` and SQLite-backed state.
- Added `package_qa_status` to the Web job index and surfaced gate/QA status
  in the Recent jobs list.

Closing standards met:

- A real-source package that otherwise satisfies source/readiness/output
  checks is blocked when Package QA has not run.
- A real-source package with strict readiness PASS, selected outputs, and
  Package QA PASS can become eligible for the final review gate.
- Package QA results remain visible after reload and in Recent jobs.
- Regression tests cover missing-QA blocking and QA persistence.

### Web UI W24 — package QA workbench ✅ DONE 2026-05-19

Goal: turn the R1 manual generated-package review loop into a repeatable Web
job action before internal/AHJ handoff.

Completed:

- Added a `POST /api/jobs/<job_id>/qa` action that runs package QA for a
  completed Web job.
- QA now runs `pvess-doctor`, verifies the Complete Project ZIP, and checks
  generated PDFs for page count and searchable text.
- The action writes `output/package-qa.json` and `output/package-qa.md`,
  stores the QA result in job state, exposes the files in the generated-file
  list, and rebuilds the ZIP to include QA outputs.
- Added a browser **Package QA** panel with a **Run QA** control and summary
  of doctor/PDF/archive failures and warnings.

Closing standards met:

- QA cannot be run against an incomplete job.
- QA artifacts persist in the job folder and remain visible after reload.
- The regenerated Complete Project ZIP contains the QA JSON and Markdown
  reports.
- Regression tests cover the endpoint, persisted job state, file categorization,
  and ZIP inclusion.

### Web UI W21-W23 — source intake, review workspace, AHJ gate ✅ DONE 2026-05-19

Goal: reduce manual source-data entry, make generated outputs reviewable in
the browser, and separate quick estimates from packages that can be considered
for formal AHJ submission.

Completed:

- **W21** — Added utility upload parsing for common CSV/text/PDF-like files.
  When 12 valid monthly kWh values are detected, generated `inputs.yaml`
  automatically uses the uploaded utility data instead of simulated/form
  monthly usage. Added filename-based auto-classification for unsorted site
  photos and spec sheets, selected-equipment spec coverage, and lookup roof
  candidates that can be applied from the UI.
- **W22** — Added document/sheet thumbnails in the Preview panel and
  per-artifact review state: `not reviewed`, `needs revision`, and
  `approved for internal review`. Review state is stored in
  `review-status.json` inside the job folder and survives reloads.
- **W23** — Added an AHJ gate with three levels: `Estimate only`,
  `Internal review`, and `AHJ-ready candidate`. The gate combines source
  material provenance, selected output completeness, spec coverage, field
  intake completeness, and artifact review state into actionable blockers.

Closing standards met:

- Simulated monthly usage is replaced automatically when a real utility upload
  yields 12 valid monthly values.
- Photo/spec classification is visible in source-material status and does not
  silently make a package AHJ-ready.
- Review state is persisted per artifact and can be loaded after page reload.
- Simulated source materials can never produce `AHJ-ready candidate`.
- Missing utility evidence, signed structural packet, selected-equipment spec
  sheets, PV-7 photos, roof/field data, or selected permit/DXF/label outputs
  block the AHJ-ready gate with field names.
- Regression tests cover uploaded-source parsing/classification, review
  persistence, simulated gate blocking, PV-only AHJ-ready candidate, and
  PV+ESS missing-battery-spec blocking.

### Web UI W1-W13 — local project generator ✅ DONE 2026-05-19

Goal: put the current PVESS generation pipeline behind a local browser UI so
an operator can enter project requirements, choose one inverter family, upload
available source material, generate the current package outputs, and review
BOM cost before moving to engineer/AHJ review.

Completed:

- **W1-W3** — Added `pvess serve`, local FastAPI endpoints, static UI shell,
  and the `TGE Solar Project Generator` title/branding.
- **W4-W7** — Wired project form input to `inputs.yaml`, calculation,
  permit/DXF/customer-summary generation, package ZIP creation, and
  selectable inverter brands (`megarova`, `hoymile`, `growatt`) mapped to
  their US-market model metadata.
- **W8-W10** — Added BOM cost estimation, override fields, generated-file
  filtering, preview/download actions, preflight checks, and clearer
  generation/readiness status in the UI.
- **W11-W13** — Added real-source intake fields, site/source uploads,
  simulated site-photo fallback, artifact/source manifests, BOM CSV,
  recent-job load/rerun/delete controls, and documentation/test coverage.

Closing standards met:

- Browser form can create a project job without hand-editing YAML.
- Each job stores `request.json`, `inputs.yaml`, output artifacts,
  `bom-cost.json`, `bom-cost.csv`, `artifact-manifest.json`, and a complete
  ZIP under the configured Web workdir.
- Inverter selection is single-family per project; alternatives are catalog
  choices, not simultaneous selected equipment.
- Preflight separates blocking validation errors from simulated/missing
  source-data warnings.
- File download paths are bounded to generated job artifacts.
- Web regression tests cover static UI, catalog/preflight/generation APIs,
  uploads, BOM overrides, model mapping, job history, rerun, delete, and
  traversal rejection.

Remaining follow-up:

- Optional account/user model if multiple operators need isolated job history.

### Web UI W14-W16 — deploy hardening + preview + lookup ✅ DONE 2026-05-19

Goal: make the local Web generator less fragile when exposed beyond a single
developer machine, improve review ergonomics, and let address/site lookup
prefill the browser form without requiring YAML edits.

Completed:

- **W14** — Added optional shared-token protection for `/api/*` and
  `/files/*` via `PVESS_WEB_ACCESS_TOKEN` or `pvess serve --access-token`.
  Added optional `PVESS_WEB_CORS_ORIGINS` for hosted front-end/API splits.
- **W15** — Reworked the Preview panel into an embedded document/image viewer
  for generated PDFs and PNG sheet previews, while keeping direct Open links.
- **W16** — Added `/api/lookup/address` with `online` and deterministic
  `offline` modes. The UI can apply returned utility, AHJ, NEC edition,
  coordinates, export tariff, and best roof-section defaults to the form.

Closing standards met:

- Static UI stays publicly loadable, while API/file routes require the token
  only when configured.
- Token-protected file links still work in the browser via signed query token
  URLs generated client-side from the locally stored token.
- Address lookup works without online credentials in `offline` mode.
- Online mode reuses the existing lookup provider chain and degrades through
  provider misses instead of blocking the UI.
- Browser preview can switch between generated PDF/Markdown documents and
  PNG previews without leaving the generator page.
- Regression tests cover token protection, file access, runtime config, and
  offline address prefill.

### Web UI W17a — language standardization ✅ DONE 2026-05-19

Goal: standardize the page language before deeper productization so the Web
UI reads like a North American PV permit workflow rather than a mix of internal
engineering terms and ad-hoc labels.

Completed:

- Added `docs/web-ui-language.md` as the single copy standard for product name,
  core terms, button language, status language, and simulated-data wording.
- Updated the Web UI to use **Source materials** consistently for uploaded or
  simulated photos, bills, specs, and structural documents.
- Replaced default project copy that implied a standalone estimator with
  package-generation language.
- Added UI address samples for:
  `905 Crossvine Drive, Mansfield, TX` and
  `2806 Green Circle Drive, Mansfield, TX`.
- Added a DFW simulated residential monthly usage curve for Mansfield tests:
  `880, 780, 720, 820, 1050, 1450, 1700, 1750, 1450, 1050, 820, 860`.

Closing standards met:

- UI title remains **TGE Solar Project Generator**.
- Buttons use stable action verbs: `Lookup address`, `Run preflight`,
  `Generate package`, `Load`, `Rerun`, `Delete`, `Save`.
- The UI no longer presents **Project Estimator** as a product name.
- Mansfield sample addresses generate valid project outputs with 12-month
  simulated usage and still surface simulated source-material status.
- Documentation, navigation, and tests cover the copy standard.

### Web UI W18 — durable Web job storage ✅ DONE 2026-05-19

Goal: move Web job metadata out of directory-only discovery so generated
projects can be searched, filtered, retained, and migrated predictably.

Completed:

- Added a SQLite-backed Web job index at `<workdir>/web-jobs.sqlite3`.
- Kept generated files on disk while storing job state, payload summary,
  project/address search fields, source-material status, readiness status,
  installed cost, and artifact metadata in SQLite.
- Added compatibility import from existing `job-status.json` folders so old
  local jobs appear after the first W18 run.
- Added API and browser filters for job status, project/address text, and
  created date range.

Closing standards met:

- Empty Web workdirs return an empty history and create the SQLite index.
- Legacy filesystem-only jobs are imported into the database on list/load.
- New async and sync jobs write both `job-status.json` and SQLite metadata.
- Deleting a job removes the database row and generated project folder.
- Regression tests cover empty database, legacy import, create/list/filter,
  delete, sync status persistence, and artifact-index consistency.

### Web UI W19 — operator accounts and project isolation ✅ DONE 2026-05-19

Goal: replace shared-token-only access with a lightweight operator model for
multi-user internal use.

Completed:

- Added SQLite-backed operator token storage. Tokens are returned once at
  creation and stored as hashes.
- Preserved `PVESS_WEB_ACCESS_TOKEN` / `pvess serve --access-token` as the
  admin/bootstrap token.
- Added `owner_id` to Web job state and the SQLite job index.
- Scoped job history, job detail, payload loading, rerun, delete, and file
  downloads by operator owner.
- Added admin-only all-jobs support through `/api/jobs?all_jobs=true` and the
  Recent jobs **All jobs** filter.

Closing standards met:

- An operator cannot load, rerun, delete, or download another operator's job.
- Admin/bootstrap token can inspect all jobs and create operator tokens.
- Auth failures return 401/403 JSON without filesystem path leakage.
- Regression tests cover operator creation, owner-scoped history, cross-owner
  denial paths, admin all-jobs access, and owner delete/download behavior.

### Web UI W20 — production deployment profile ✅ DONE 2026-05-19

Goal: package the Web app for a repeatable hosted deployment without changing
the local CLI workflow.

Completed:

- Added a Dockerfile production profile for the FastAPI app.
- Set the container default Web workdir to `/data/pvess-web` and declared it
  as a Docker volume so generated artifacts persist outside the image layer.
- Added `.dockerignore` to keep local outputs, SQLite files, caches, and
  virtualenvs out of the production image context.
- Expanded `/api/health` with app version and storage status.
- Added `pvess web-smoke` / `pvess-web-smoke` to verify health, static
  assets, auth mode, and a lightweight generated job.
- Documented local Docker run command, environment variables, backup strategy,
  health checks, and reverse-proxy assumptions.

Closing standards met:

- One documented Docker command starts the production profile locally.
- Health check returns app/version/auth/storage status.
- Generated artifacts persist under the mounted `/data/pvess-web` volume.
- Regression tests cover smoke-command behavior, CLI registration, health
  storage payload, and Dockerfile persistent-volume guardrails.

### Stage 5 — simulated site-data readiness path ✅ DONE 2026-05-18

Goal: while real field photos, utility bills, APN lookup, signed structural
letter, and engineer/installer metadata are not available, keep the Frisco
reference package useful for layout iteration without letting simulated data
look AHJ-ready.

Completed:

- **5.1** — Added a source-data readiness assessor and
  `reference_profile_data_readiness` doctor check. The check classifies each
  item as `ready`, `simulated`, `missing`, or `not_applicable`, and keeps
  simulated data as non-blocking WARN.
- **5.2** — Added `pvess readiness` / `pvess-readiness` to regenerate
  `output/reference-readiness.md` from any project. Default mode is
  non-blocking; `--strict` exits 1 when simulated/missing data remains.
- **5.3** — Added project-level `simulated-site-data.yaml` source packs to
  formalize mock field inputs under a
  stable project fixture convention (`photos/mock-*`, placeholder usage,
  modeled trace geometry). Readiness now reads the pack and keeps listed
  fields simulated until their replacement standard is satisfied.
- **5.4** — Added an opt-in `--readiness-appendix` permit builder path that
  appends the readiness summary as an `INTERNAL REVIEW ONLY` appendix. It is
  outside the Sheet Registry, omitted from the cover index, and never appears
  in AHJ packages unless explicitly enabled.
- **5.5** — Added `output/real-data-checklist.md`, generated by
  `pvess readiness`, with one operator-facing replacement action for every
  simulated/missing item before `pvess readiness --strict` can pass.

Closing standards:

- Simulated APN, PE, installer, photos, utility usage, or hand-modeled site
  geometry must never show as `ready`.
- PV-only projects classify ESS installation data as `not_applicable`, not
  missing.
- `pvess readiness --strict <project>` fails while simulated/missing data
  remains and passes only when every applicable item is real.
- `pvess-doctor` remains exit-zero on WARN-only simulated-data projects so
  layout iteration can continue.
- The readiness appendix is opt-in, internal-review-only, and must not alter
  the cover sheet index or AHJ-selected sheet registry.

Test plan:

- CLI tests for default report generation and strict failure on Frisco mock
  data.
- Doctor test asserting current Frisco stays WARN, not FAIL.
- Full `pytest`, `pvess-doctor projects/003-frisco-glasshouse`, and
  `mkdocs build --strict` before closing the stage.

### Stage 9.8/9.9 — EE-4A property context plan ✅ DONE 2026-05-18

Stage 9.8 added a separate `EE-4A · PROPERTY CONTEXT PLAN` sheet so
contractor-style property line / driveway / fence / dimension context no
longer crowds EE-4. Stage 9.9 moved that sheet from visual fallback to
data-driven geometry via `site.property_context`.

Closing standards met:

- EE-4 remains roof-array/equipment focused; EE-4A owns property context
- `lot_outline`, `driveway_polygon`, `fence_lines`, and
  `property_dimensions` render directly when present
- Empty `property_context` remains backward-compatible with the generated
  Stage 9.8 fallback
- Frisco package rebuilds with 13 pages and doctor passing

Follow-up candidate: Stage 9.10 should add a lightweight EE-4A visual lint
for label/dimension collisions and optional satellite/GIS import helpers
for the property-context block.

### Stage 9.10.1-9.10.5 — PV-6 traced string layout ✅ DONE 2026-05-18

PV-6 now supports the competitor-style string layout reference: full traced
roof linework, saturated module fills by `string_index`, per-module string
numbers, left-side string legend, north arrow, top-right equipment summary,
and automatic `STRING N` leader callouts around the roof. The legacy
per-section PV-6 fallback remains active when trace geometry is unavailable.

Closing standards met:

- One external leader callout per non-empty string
- `STRING N` labels remain inside the sheet frame and do not overlap each
  other or module rectangles
- PV-6 rollup total equals placed modules; declared strings cannot silently
  disappear
- New doctor check `pv6_string_layout_visual_lint` guards missing strings,
  bad rollups, missing callouts, and label collisions
- Frisco package rebuilds with doctor passing

### Reference planset parity roadmap — address + site info → full package ✅ DONE 2026-05-18

Goal: from address lookup, site-survey inputs, selected equipment, and
optional signed engineering/spec PDFs, emit a Wyssling/Texas Green Eco style
residential PV permit package similar to the two reference plansets reviewed
on 2026-05-18.

Stages 9.11-9.17 are implemented:

- `tx_residential_pv` / `wyssling_like` package profiles with contractor-style
  PV/EE numbering and cover-index parity
- Extended field-survey schema for roof/framing/attic/decking, meter/ESID,
  structural letter, PV-7 photos, and SPEC PDFs
- New reference sheets: conditional EE-2.1 one-line, EE-5 placard, PV-6
  design notes, PV-7 site photos, SPEC placeholder/appendix, and unsigned
  structural-review draft when no signed PDF is supplied
- Doctor guards for reference-profile intake completeness and attachment
  readiness
- Frisco reference package builds as 17 pages with doctor PASS and expected
  WARNs for missing signed/photo/spec source files

#### 9.11 — Package profile and sheet numbering

Scope:
- Add a `tx_residential_pv` / `wyssling_like` permit profile
- Map internal sheets to reference numbering:
  `PV-1 Cover`, `PV-2 Site Plan`, `PV-3 Property Plan`, `PV-4 Attachment`,
  `PV-5 Mounting Details`, `EE-1 String Plan`, `EE-2 Three-Line`,
  conditional `EE-2.1 One-Line`, `EE-3 Notes`, `EE-4 Labels`,
  `EE-5 Placard`, `PV-6 Design Notes`, `PV-7 Site Photos`, `SPEC`
- Keep existing AHJ profiles backward-compatible

Closing standards:
- Sheet index exactly matches emitted pages
- Glasshouse-style project emits a reference-profile package without
  changing the existing internal profile
- Missing optional pages are omitted intentionally, not as registry drift

Test plan:
- Unit tests for sheet-code mapping and profile selection
- Positive + regression-bait doctor tests for sheet-index/profile parity
- Full `pvess-review` on Frisco and one legacy project

#### 9.12 — Site intake and field-survey data model

Scope:
- Extend inputs / wizard for roof stories, roof height, roof condition,
  roof construction, attic access, framing, decking, roof layers, meter
  number, ESID, disconnect location, service/sub-panel locations, and
  photo paths
- Mark address-derived or satellite-derived fields as review-needed when
  confidence is low

Closing standards:
- Address + site-survey fields populate PV-1/PV-2/PV-3/PV-4/EE pages
- Unknown fields degrade to explicit blanks or review notes, not invented
  permit facts

Test plan:
- Schema compatibility tests for old YAML
- Wizard/intake tests for complete and partial survey payloads
- Doctor check for required field completeness under the reference profile

#### 9.13 — PV-7 site photos

Scope:
- Render owner/installer site photos into a PV-7 sheet: front elevation,
  roof, meter, MSP, sub-panel, attic/framing, proposed equipment area
- Use stable captions sourced from the site-survey model

Closing standards:
- Photo pages preserve aspect ratio and never crop away the primary subject
- Missing photos render checklist placeholders with required-shot labels

Test plan:
- Golden PDF text checks for captions
- Raster smoke checks for image presence and nonblank placeholders
- Frisco package review with and without photos

#### 9.14 — SPEC sheet attachment library

Scope:
- Equipment library stores manufacturer PDF references for module,
  inverter, optimizer, racking/flashing, disconnect, and battery when present
- Permit builder appends selected spec pages after the drawing set

Closing standards:
- SPEC pages match selected equipment and are listed in the sheet index
- Missing spec PDF is surfaced as WARN with the exact equipment key

Test plan:
- Unit tests for equipment → spec-page resolution
- PDF merge tests for page count and order
- Doctor check for required spec coverage under the reference profile

#### 9.15 — Structural letter packet

Scope:
- Support prepending a signed structural letter PDF when supplied
- Generate an unsigned structural-review draft from system/site inputs when
  no signed letter is available

Closing standards:
- Signed PDFs are preserved verbatim and placed before PV-1
- Unsigned drafts are clearly marked as draft / engineer-review only
- The system never fabricates PE signature, stamp, or license attestation

Test plan:
- PDF prepend tests preserving page count and order
- Text checks for draft watermark / signed-source metadata
- Doctor WARN when reference profile lacks signed structural PDF

#### 9.16 — One-line / three-line conditional electrical pages

Scope:
- Add conditional EE-2.1 one-line page for line-side tap or complex
  service-intercept cases
- Keep EE-2 three-line as the default electrical plan

Closing standards:
- Service topology selects the correct electrical page set
- Conductor schedule, OCPD, grounding, VLLD, and tap labels remain
  calculation-backed

Test plan:
- Fixture matrix: service intercept, line-side tap, backfeed breaker,
  SPAN/main-panel upgrade
- Doctor checks for page presence by interconnection method
- Visual review for text/wire collisions

#### 9.17 — Reference-profile visual QA

Scope:
- Unify title block, right-side engineer/client/project column, revision
  table, signature area, scale notes, and page labels across CAD sheets
- Add package-level visual lint for nonblank pages, expected colors/text,
  and obvious label collisions

Closing standards:
- Contact sheet reads as one coherent permit package
- `pytest`, `mkdocs build --strict`, `pvess-doctor`, and `pvess-review`
  all pass on Frisco reference-profile output

Test plan:
- Raster/contact-sheet smoke tests for key pages
- Doctor check for reference-profile package completeness
- Manual visual review against the two reference PDFs before moving into
  Phase H / regional-rule work

### K.4.6 — Equipment library + cost overrides + battery-optional + TX REP picker ✅ DONE 2026-05-17

All 6 sub-tasks complete; 31/31 doctor; +37 tests landed across the
milestone (461 total vs 425 at start). Frisco project quotes the
real installer BOM ($26k post-ITC) at 7.9 yr payback with the
3-tier upgrade table inline.


**Why first**: Surfaced by the 2026-05-17 Frisco E2E test. Three
overlapping gaps that compound into a single-day sales problem:

1. **Battery is a required field** in the yaml — but the TX market
   default (per `2026-05-17` discussion with the user) is PV-only.
   Smart Meter Texas + a 1:1 REP buyback plan (Green Mountain
   Renewable Rewards, TXU Home Solar Buyback) delivers full ROI
   without storage. Battery is a backup decision, NOT an economics
   decision. Quoting Tesla PW3 by default kills deals: payback
   22 yr (with battery) vs 11 yr (PV-only on 1:1 REP).
2. **Cost benchmark is Tesla-tier ($3.50/W + $950/kWh)** — overstates
   the actual installer's stack (Megarevo / Growatt inverters +
   in-house batteries) by 30-65 %. Customer PDF payback looks 50 %
   worse than reality.
3. **`export_tariff_model` enum is too coarse** — `1to1_nem` /
   `ca_nem3` / `hi_self_consumption` don't capture the TX-specific
   REP-by-REP buyback ratio (0.5× default vs 1.0× on the "good"
   REP plans). $90/mo savings difference between same-PV + different
   REP.

**Business priority**: HIGHER than K.9 (the Aurora-grade visual
upgrade). K.4.6 fixes how every quote is presented, which affects
conversion rate directly. K.9 is craft polish.

**Total estimate**: **4 working days**

#### K.4.6.1 — Battery-optional schema (0.5 day) ✅ DONE 2026-05-17

- `Battery.install: bool = True` field; when False, downstream fields
  (brand / model / quantity / capacity) become optional via
  `model_validator(mode='after')`
- Or simpler: keep current schema, just allow `quantity: 0` cleanly
  (already mostly works per the 2026-05-17 Frisco PV-only run, but
  needs explicit doctor + customer PDF support for the "no backup"
  state)
- Customer PDF: when battery.quantity = 0, replace the backup-hours
  block with a "PV-only — grid-tied, no outage backup" notice
- 3 new tests + update existing tests that assumed quantity ≥ 1

#### K.4.6.2 — Equipment library expansion (0.5 day) ✅ DONE 2026-05-17

New `devices/` entries matching the installer's actual product line:

```python
# devices/inverters.py
"megarevo_r8klna":   { brand: "Megarevo", model: "R8KLNA",
                       ac_w: 8000, ac_v: 240,
                       cost_usd: 1600, n_mppt: 2, max_dc_v: 600 }
"megarevo_r11klna":  { brand: "Megarevo", model: "R11KLNA",
                       ac_w: 11000, ac_v: 240,
                       cost_usd: 2000, n_mppt: 2, max_dc_v: 600 }
"growatt_min11000":  { brand: "Growatt", model: "MIN 11000TL-X",
                       ac_w: 11000, ac_v: 240,
                       cost_usd: 2500, n_mppt: 2, max_dc_v: 600 }
"hoymiles_hys11k":   { brand: "Hoymiles", model: "HYS-LV-11K",
                       ac_w: 11000, ac_v: 240,
                       cost_usd: 2200, n_mppt: 2, max_dc_v: 600 }

# devices/batteries.py
"inhouse_16kwh_hv":  { brand: "InHouse", model: "HV-16",
                       kwh: 16.0, v_nom: 400.0,
                       cost_usd: 6000, chemistry: "LFP" }
"growatt_apx_20kwh": { brand: "Growatt", model: "APX HV",
                       kwh: 20.0, v_nom: 400.0,
                       cost_usd: 10000, chemistry: "LFP" }
```

#### K.4.6.3 — Cost-override schema (0.5 day) ✅ DONE 2026-05-17

```yaml
project:
  installer_cost_overrides:        # NEW K.4.6 schema block
    pv_turnkey_usd_per_w: 2.40    # modules+racking+labor+permit, no inverter/battery
    # If absent, falls back to NREL benchmark $3.50/W.
    # Inverter / battery costs pulled from devices/* library when
    # `inverter.ref` / `battery.ref` set; explicit `cost_usd` here
    # overrides the library value.
```

Wire through `customer/economics.py` so the PDF cost number reflects
the real quote, not the NREL benchmark.

#### K.4.6.4 — TX REP buyback model (0.5 day) ✅ DONE 2026-05-17

```yaml
loads:
  rep_buyback_ratio: 1.00         # NEW: 0..1, fraction of retail
                                  # paid back for exported kWh
  rep_plan_name: "Green Mountain Renewable Rewards"   # informational
```

Preset alias for common TX REP plans (so users don't need to
remember the 0.50 / 0.65 / 1.00 numbers):

```python
TX_REP_PRESETS = {
    "default_oncor":       0.50,
    "txu_solar_buyback":   1.00,
    "green_mountain_rr":   1.00,
    "reliant_sun":         0.95,
    "rhythm_pure_energy":  0.70,
}
```

`economics.py` computes effective rate using `rep_buyback_ratio`
when present; `export_tariff_model` stays for non-TX projects.

#### K.4.6.5 — Customer PDF: 3-tier quote table (1 day) ✅ DONE 2026-05-17

When `battery.install = False` (or quantity = 0), the customer PDF
auto-generates a side-by-side table:

```
┌──────────────────────────────────────────────────────────┐
│  Your options                                            │
│  ┌────────────┬──────────────┬──────────────┐            │
│  │ PV-only    │ +16 kWh      │ +20 kWh      │            │
│  │            │ inhouse      │ Growatt HV   │            │
│  ├────────────┼──────────────┼──────────────┤            │
│  │ $25,105    │ $29,305      │ $32,455      │            │
│  │ post-ITC   │ post-ITC     │ post-ITC     │            │
│  ├────────────┼──────────────┼──────────────┤            │
│  │ $257/mo    │ $257/mo      │ $257/mo      │            │
│  │ 8.2 yr     │ 9.5 yr       │ 10.5 yr      │            │
│  ├────────────┼──────────────┼──────────────┤            │
│  │ no backup  │ ~14 hr crit  │ ~18 hr crit  │            │
│  └────────────┴──────────────┴──────────────┘            │
│                                                          │
│  Picking a battery is a backup-vs-cost decision, not     │
│  a savings decision. All three options earn the same     │
│  monthly savings.                                        │
└──────────────────────────────────────────────────────────┘
```

Generated from yaml's installer_cost_overrides + 2-3 named battery
options (defined in `loads.backup_options[]` list).

#### K.4.6.6 — Doctor + tests + docs (1 day) ✅ DONE 2026-05-17

- New doctor check `tx_rep_buyback_is_set_explicitly` — if state =
  TX and `rep_buyback_ratio` is at default (0.50 inferred from
  `default_oncor`), surface as WARN with "switching REP plan adds
  $90/mo" hint
- 8 new tests covering: battery=0 path, REP presets, cost overrides
  end-to-end, 3-tier table render
- Update CHANGELOG + this ROADMAP

#### K.4.6 master closing standards

```
✅ Tests:          426 → ≥ 440 (+14 new)
✅ Doctor:         29 → 30 (+1 TX REP-plan WARN check)
✅ Frisco PV-only PDF: matches the manual calculation of
                       $25k post-ITC / $257/mo / 8.2 yr payback
✅ Frisco backup option PDF: 3-tier table renders cleanly
✅ Backward compat: every existing yaml validates unchanged
                    (defaults preserve current behavior)
```

---

### K.9 — Per-module layout + PV-4 v2 (Aurora-grade attachment plan) ✅ DONE 2026-05-17

K.9.1 + .2 + .3 + .5 landed; +27 tests; doctor 32 → 33. K.9.4 (equipment
callout auto-routing) deferred — the existing PV-4 equipment labels work
fine for now; auto-routing can be a polish phase when sales feedback
demands it.

---

### K.12 — Industry-standard PV-1 cover page (Wyssling-style) ✅ DONE 2026-05-17

Triggered by user's 2026-05-17 side-by-side comparison to a real
Wyssling Consulting permit. 12-block layout: title strip, aerial +
vicinity maps, sheet index, scope of work, governing codes (NEC + 8
ICC family), design criteria (wind/snow/ASCE/exposure/occupancy/
construction/sprinklers), roof info, interconnection, arrays table,
meter info (incl. Oncor ESID), revision history, PE stamp.

K.12.1 + .2 + .3 + .4 + .5 all landed; +22 tests; doctor 33 → 34.
Aerial via Google Solar dataLayers (K.3c+ reuse), vicinity via Mapbox
Static Images API. Both opt-in via env keys; cover renders with
placeholders when keys missing.


**Why**: Current PV-4 renders modules as **square cells** at a heuristic
grid spacing — the visual approximation served us through Phases F + J
when the system was "show the AHJ the modules exist." With K.3c +
K.8 now resolving per-face geometry from address alone, the bottleneck
is the PV-4 sheet itself: an Aurora / OpenSolar permit drawing shows
**each module's true rectangle at its real (x, y, rotation)** plus
auto-routed equipment callouts. K.9 closes that gap.

**Reference**: the 2026-05-17 review image (Talesun 415W / Megarevo
R8KLNA / Tigo TS4-A-O / Frisco Texas) — that's the visual benchmark.

**Scope boundaries (NOT in K.9)**:
- 3D roof model — stays 2D top-down (Aurora's 3D is 5-engineer-year work)
- Drone / Scanifly import — Google Solar K.3c is the geometry path
- Real-time wire trunk routing — equipment callouts get arrows, but
  the trunk lives in DXF EE-1, not PV-4
- Animations / web preview — PDF / DXF stays the deliverable

**Total estimate**: **5 working days** (1 engineer, focused)

#### K.9.1 — Module placement algorithm (1.5 days)

New module: `src/pvess_calc/calc/module_placement.py`

```python
@dataclass
class ModuleInstance:
    face_name: str          # which roof_section
    x_ft: float             # local coord (eave-left origin)
    y_ft: float             # +y toward ridge
    width_ft: float         # module physical W (after orientation)
    height_ft: float        # module physical H (after orientation)
    rotation_deg: float     # 0 = portrait (long edge ⟂ eave),
                            # 90 = landscape (long edge ∥ eave)
    string_index: Optional[int] = None   # K.9.3+: which string

def place_modules(
    section: RoofSection,
    *,
    module_w_in: float, module_h_in: float,
    target_count: int,
    inter_module_gap_in: float = 0.5,    # rail spacing
    inter_row_gap_in: float = 6.0,       # walking path
) -> list[ModuleInstance]:
    """Try portrait + landscape, return whichever fits ≥ target_count
    with the cleanest layout (preferring fewer rows, then fewer cols).
    Respects edge_setbacks + obstructions[] with halo + polygon shape.
    Caller decides what to do if neither orientation fits — typically
    truncate target_count down."""
```

**Algorithm**: for each candidate orientation:
1. Inset polygon by max(edge_setback, default_setback) per edge
2. Subtract every obstruction halo (Minkowski sum on obstruction rect
   inflated by `obs.setback_ft` from each side)
3. Compute usable bounding box `(bbox_x_min, bbox_y_min, bbox_w, bbox_h)`
4. Compute rows = `floor(bbox_h / (module_h + inter_row_gap))`
5. Compute cols = `floor(bbox_w / (module_w + inter_module_gap))`
6. Emit `rows × cols` candidate centers; filter those that fall
   inside the inset polygon AND outside every obstruction halo
7. Truncate to `target_count` (top-left first — predictable for
   reviewers comparing yaml vs drawing)

**Closing standards**:
- ✅ ≥ 8 unit tests (`tests/test_module_placement.py`)
  - rect / tri / polygon shapes
  - portrait vs landscape orientation choice
  - obstacle avoidance (halo correctly carves out region)
  - target_count > capacity → returns max-capacity, doesn't raise
  - target_count = 0 → returns empty list
  - degenerate (zero area) section → returns empty
  - polygon with concave bite → no module straddles bite
- ✅ Conservation: every emitted (x, y) is inside the inset polygon
  AND outside every obstruction halo (assertion test)
- ✅ Deterministic: same input → same output, byte-identical

#### K.9.2 — Engine integration (0.5 day)

- Add `CalculationResult.module_placements: dict[str, list[ModuleInstance]]`
  keyed by face_name
- `engine.run()` calls `place_modules` per section after the K.8.1
  auto-distribute determines per-face module counts
- Tri faces now get modules (current PV-4 skips them)
- 3 integration tests:
  - Phoenix S+W (2 face manual distribution) → 2 keys in dict
  - Frisco 13-face auto-distribute → 13 keys, each with right count
  - Austin demo (no roof_sections) → empty dict

#### K.9.3 — PV-4 sheet renderer upgrade (1.5 days)

Rewrite `src/pvess_calc/permit/structural.py::_draw_section_plan` to:

- For each `ModuleInstance` in `result.module_placements[face_name]`:
  - Draw rectangle at `(x_ft, y_ft, width_ft, height_ft)` rotated
    `rotation_deg` (use reportlab `c.saveState` / `c.translate` /
    `c.rotate`)
  - Fill `#E8F0FF` (matching current style)
  - Edge `#1F5BD7` 0.3 pt
  - At ~10 % of max module dimension, draw a small module ID number
    (1 .. N) in the top-left corner — lets the reviewer match the
    schedule

Add a **module dimension callout** in the bottom-right of every PV-4
sheet (matches the reference image's `67.80"  ·  44.65"` block):

```
                ┌──────────┐
                │          │ 44.65"
                │  module  │
                │          │
                └──────────┘
                  67.80"
            TALESUN TP7G54M 415
```

Pulled from `inputs.pv_array.module` (existing schema field).

**Closing standards**:
- ✅ ≥ 4 PV-4 visual contract tests
  - count of drawn module rectangles matches `Σ module_count`
  - module bounding boxes don't intersect any obstruction halo
    bounding box (PDF byte-level check by parsing reportlab output)
  - module dimension callout present (text match for module model)
  - Frisco fixture renders without error (snapshot file size > 50 KB)

#### K.9.4 — Equipment callout engine (1 day)

New module: `src/pvess_calc/dxf/equipment_callouts.py` (lives in `dxf/`
because the same engine drives EE-1 + EE-2; PV-4 imports it via the
permit/PDF layer)

```python
@dataclass
class EquipmentMarker:
    label: str              # "(N) MAIN SERVICE PANEL"
    x_ft: float             # location on the site plan
    y_ft: float
    side: Literal["bottom", "right", "left", "top"]
    # which side of the building the equipment lives on
```

Function: `render_callouts(c, markers, *, bbox)` — draws each
marker's text outside the bbox, with an arrow pointing back to its
(x_ft, y_ft) coordinate. Auto-routing: stack labels vertically on
the chosen side, route arrows so they don't cross.

Equipment markers come from a new schema block:

```yaml
service:
  equipment_locations:    # NEW K.9 schema addition
    msp:
      x_ft: 40, y_ft: 2, side: "bottom"
    inverter_1:
      x_ft: 38, y_ft: 1, side: "bottom"
    sub_panel_1:
      x_ft: 42, y_ft: 2, side: "bottom"
    # ...
```

Defaults: when the block is absent (every pre-K.9 yaml), no callouts
render — PV-4 looks like K.9.3 alone, no regression.

**Closing standards**:
- ✅ 3 callout layout tests
  - 5 markers on "bottom" → labels stacked vertically below bbox
  - 2 markers on "right" → labels stacked to right
  - mixed → arrows don't cross each other (intersection-free check)

#### K.9.5 — Closing standards + docs (0.5 day)

- New doctor check: `pv4_module_count_matches_yaml`
  - Verify `Σ len(module_placements.values()) == pv_array.modules`
  - Verify every face's placement count == that face's module_count
    (after K.8.1 distribution)
- 2 regression-bait tests for the doctor check
- Update `CLAUDE.md` "阶段总览" — mark K.9 done with date
- Move K.9 entry to `CHANGELOG.md` proper
- Bump doctor count: 29 → 30 in CLAUDE.md

#### K.9 master closing standards

```
✅ Total tests:        425 → ≥ 445 (+20 new)
✅ pytest:             all green
✅ pvess-doctor:       Phoenix + Austin 30/30 PASS
✅ Frisco PV-4:        renders all 13 faces with real module rectangles
✅ NO regression:      Austin (single-orientation legacy) PV-4 still works
✅ Visual benchmark:   side-by-side w/ 2026-05-17 reference → 70%+ visual parity
✅ Documentation:      ROADMAP K.9 → CHANGELOG; CLAUDE.md updated
```

---

## Backlog And Historical Detail

### K.8.2 — Value-weighted orientation derate (TX afternoon-peak / TOU) (2 days) ✅ DONE 2026-05-17

**Why**: K.8's Sandia derate table measures **annual kWh** — south =
100%, west = 86%. Mathematically correct for "total electrons over
the year" but the wrong yardstick for the TX market reality
(2026-05-17 SW-quadrant correction):

  * **PV-only + default REP** (~0.5× buyback): a kWh self-consumed
    during the 2-8 PM AC peak is worth ~$0.165 (full retail). A kWh
    exported at 11 AM is worth ~$0.083 (half retail). **West-facing
    kWh ≈ 2× the value of east-facing kWh** even though the Sandia
    derate ranks them equal.
  * **PV-only + 1:1 REP** (TXU / GME): annual kWh count is equal-valued,
    BUT west still wins on the qualitative "my roof produces when I'm
    using power" homeowner experience.
  * **CA NEM 3.0**: extreme version of the same logic — ACC tariff
    pays ~0.27× retail mid-day vs ~0.80× retail peak. SW-quadrant
    advantage is even larger there.

For Frisco specifically, the current workaround is to **manually
drop East faces from yaml** even though their Sandia derate (~80%)
looks "good enough." K.8.2 should automate this — when the algorithm
picks the highest-value faces, it should weight by time-of-day value
not just annual kWh.

**Scope**:

#### K.8.2.1 — Hourly production model per face (0.5 day)

Replace single-number `orientation_derate` with hourly production
profile per face:

```python
def hourly_production_profile(azimuth_deg, pitch_deg, lat) -> list[float]:
    """Returns 8760-length list (hours per year) or 24-length avg-day
    list, normalized to 1.0 = south-facing latitude-tilt at solar noon.
    Used to weight by hourly export price OR self-consumption value."""
```

Implementation: clear-sky model with diffuse + direct components, lat-
adjusted; simpler than full PVWatts but captures the AM-vs-PM tilt
that the Sandia annual table flattens.

#### K.8.2.2 — Hourly value model (TOU + REP buyback) (0.5 day)

```python
def hourly_value_factor(rep_buyback_ratio, self_consumption_pattern) -> list[float]:
    """Hourly multiplier on production. Self-consumed kWh = 1.0; exported
    kWh = rep_buyback_ratio. Returns 24 floats (avg weekday DFW pattern).
    Future: per-hour TOU tariff lookup for CA EV2-A, EV-A rates."""
```

DFW typical weekday self-consumption pattern: high 2-9 PM (AC + cooking),
medium 6-9 AM (morning routine), low overnight + midday-empty-house.

#### K.8.2.3 — Value-weighted face score (0.5 day)

```python
class FaceProduction:
    annual_production_kwh: float        # K.8 (existing, total energy)
    annual_value_usd: float              # K.8.2 (NEW, $-weighted)
    value_weighted_derate: float         # K.8.2 (NEW, vs ideal face)
```

K.8.1 LRM auto-distribute switches from area-proportional to
`value_weighted_derate × area` proportional. K.4.6.5 3-tier table
unchanged (PV array still identical across tiers).

#### K.8.2.4 — Doctor `face_value_score_distinguishes_east_west` (0.5 day)

New check that catches the "annual-kWh-only" regression: synthesize
a 14-face roof with equal areas; if East and West faces score
identically under K.8.2's value weighting, the hourly model is broken
(should be ~30 % spread). 4 new tests + CHANGELOG.

**Closing standards**: 460 → ≥ 470 tests; doctor 30 → 31; Frisco
re-runs without manual yaml face-drop; East faces auto-fall to the
bottom of the priority list when REP buyback ≤ 0.7.

---

### K.10 — String-level layout + EE-1 string overlay (3 days)
- Group `ModuleInstance` into strings (per inverter MPPT)
- Color-code each string in PV-4 + EE-1
- Wire to NEC 690.7 Voc-cold check per-string (already in calc engine)
- String balance heuristic: keep strings within ±2 modules

### K.11 — Wire trunk auto-routing ✅ DONE 2026-05-17

Replaced the manual `wire_lengths` yaml block (6 hand-typed numbers,
50 ft default) with computed lengths from real 2D site geometry.

Schema: 3 additive blocks (`RoofSection.site_anchor`,
`RoofSection.roof_penetration`, `Site.equipment_locations`). Algorithm:
Manhattan distance for the 5 segments (A·PV source, B·DC home run,
C·INV→AC disc, D·AC disc→MSP via sub-panel chain, E·ESS→INV).
EE-4 overlay: orange dashed conduit polyline + equipment dots with
labels when routing active. Doctor: `auto_routed_lengths_sane`
catches frame/unit mismatches (>200 ft envelope).

+23 tests (20 unit + 3 doctor). Tests 553 → 576. Doctor 37 → 38.
Legacy yamls bit-identical to pre-K.11 (routed=False keeps manual
`wire_lengths`).

K.11+ future scope (NOT in this phase):
  * True L-shaped / convex-hull routing optimiser (current Manhattan
    over-estimates by 5-10 %)
  * Multi-attic-drop installs (current code uses one drop point)
  * Per-string trunk separation (current code lumps all strings into
    one B-segment average)

### K.13 — EE-4 site-focused restructure ✅ DONE 2026-05-17

Triggered by user feedback that the Frisco EE-4 looked "very
unsuccessful": the legacy abstract PV-grid path was painting a tiny
yellow placeholder on a 94 %-empty lot.

Shipped in 4 staged passes:

- **A** — Hand-edit Frisco yaml with `equipment_locations` + 5 face
  `site_anchor` blocks → K.11 routed path activates
- **B** — `calc/site_layout.py::auto_anchor_sections()` auto-derives
  anchors from `azimuth_deg` for any yaml with `roof_sections`. 17
  tests; Phoenix EE-4 multi-face for free with no yaml edits
- **C** — 5 visual polish items: aerial 35 m, address 0.50", property
  line bottom-right, array caption bottom margin, NOTE warning strip.
  8 tests
- **D** — Delete `_pick_module_grid` + legacy `if not routed and not
  has_face_anchors` painter, enlarge aerial 3.0×2.6", new doctor
  check `ee4_focuses_on_site_geometry` (38 → 39). 12 tests + 2 test
  rewrites

Tests 585 → 622. Doctor 38 → 39.

### K.13.1 — EE-4 visual-collision polish ✅ DONE 2026-05-17

All 4 P-level fixes landed:

- **P0** — Optimizer leader endpoint moved inside lot top-right
  (was outside-right overlapping SITE INFORMATION)
- **P1** — PV ARRAY caption moved to top banner; conduit legend
  right-anchored on same banner (was bottom margin competing with
  leader callouts)
- **P2** — `auto_anchor_sections` cursor starts inset by
  perpendicular orientation's max H, with half-wall fallback.
  Phoenix's South face moves x=15 → 39, eliminating SW-corner
  overlap with West face
- **P3** — PROPERTY LINE label moved to top-left outside the lot
  (was bottom-right competing with rightmost leader callout)

+13 tests in `tests/test_ee4_k131_polish.py`. Tests 622 → 635.
Doctor 39 (unchanged — pure visual polish).

### Phase H — NEC 690.11 DC AFCI + SPD + Conduit fill

Status: **H.1 + H.2 + H.3 + H.4 complete**.

#### H.1 — Adjacent protection calculation closure

Development plan:
- Make DC AFCI evidence data-driven from selected inverter metadata or
  datasheet-backed model matching.
- Split SPD output into 230.67 required service SPD (NEC 2020+) vs
  PV/ESS-side recommended SPD locations.
- Turn EMT fill into an auditable Chapter 9 result with conductor area,
  selected raceway, headroom, and percentage of the 40% fill allowance.
- Surface the result in `report.md`, EE-5 compliance checklist, and doctor.

Closing standard:
- Selected Frisco Growatt package reports AFCI PASS from the selected
  datasheet/listing evidence.
- NEC 2017 projects do not falsely mark service SPD as required; NEC 2020+
  residential projects do.
- Unknown conductor sizes fail loudly instead of silently counting as zero
  area.
- Doctor fails only for hard structural problems (explicit AFCI fail,
  missing required SPD location, overfilled/unsupported conduit) and warns
  for field-proof items such as unconfirmed AFCI or ground-rod resistance.

Test plan:
- Unit tests cover known AFCI model recognition, unknown inverter manual
  state, NEC 2017 vs 2020+ SPD behavior, conduit step-up, fill percentage,
  and invalid conductor sizes.
- Doctor tests cover Frisco PASS, generic-inverter WARN, and overfilled
  conduit FAIL.
- E2E verification: `pytest -q`, `pvess-doctor projects/003-frisco-glasshouse`,
  and `pvess calc projects/003-frisco-glasshouse` to confirm report output.

#### H.2 — K.11 routed raceway schedule closure

Development plan:
- Promote raceway fill from PV/AC aggregate facts into A/B/C/D segment
  records tied to K.11 route lengths.
- Keep `pv_conduit` / `ac_conduit` aggregate fields for backward
  compatibility, but add `adjacent.raceways[]` as the new detail surface.
- Feed raceway size / fill data into the shared electrical topology so
  EE-2 and EE-2.1 conductor schedules no longer invent conduit facts.
- Render a dedicated H.2 raceway table in `report.md`.

Closing standard:
- Routed projects emit A/B/C/D raceway segments with non-zero lengths
  for B/C/D and a `FREE AIR` A row.
- Every raceway segment with a fill calculation is ≤100% of the NEC 40%
  fill allowance and stays inside the built-in EMT table.
- `build_electrical_topology()` conductor rows carry raceway length and
  fill percentage for downstream DXF/PDF renderers.
- Doctor fails on missing H.2 segments, overfilled raceways, or routed
  raceways with zero length.

Test plan:
- Phase H tests cover Frisco routed segment lengths, conduit fill on
  C/D rows, and topology propagation.
- Doctor tests cover missing raceway-segment regression.
- E2E report test verifies the H.2 raceway table renders for PV-only
  Frisco.

#### H.3 — Configurable raceway type closure

Development plan:
- Add project-level routing fields for PV DC output raceway type and AC /
  supply-tap raceway type.
- Extend the Chapter 9 40% fill selector beyond EMT to PVC Schedule 40,
  PVC Schedule 80, RMC, and FMC.
- Preserve EMT defaults so legacy yaml output is stable unless a project
  explicitly declares another raceway type.
- Propagate the selected type through aggregate Phase H facts,
  A/B/C/D raceway segments, topology conductor schedules, and `report.md`.

Closing standard:
- Frisco still emits the same EMT raceway schedule with no yaml changes.
- A project that declares `routing.ac_raceway_type: PVC80` shows PVC80 in
  `adjacent.ac_conduit`, C/D raceway segments, topology rows, and report
  output.
- The selector steps up trade size when a smaller-ID raceway such as PVC80
  cannot hold the same conductor set that fits EMT.
- Doctor failures refer to unsupported raceway tables generically instead
  of hard-coding EMT.

Test plan:
- Unit tests compare EMT vs PVC80 sizing on the same conductor set.
- Frisco regression verifies configured PV/AC raceway types propagate into
  the electrical topology.
- E2E report test verifies non-EMT raceway type text renders in Markdown.
- Full verification remains `pytest -q`, `mkdocs build --strict`, and
  `pvess-doctor projects/003-frisco-glasshouse`.

#### H.4 — Remaining adjacent detail work

Development plan:
- Extend AHJ profiles with optional `spd_policy` fields.
- Allow profiles to make base NEC SPD results stricter without allowing
  local profile data to relax a selected NEC edition's requirements.
- Wire `project.ahj_profile` and `pvess permit --ahj` into Phase H surge
  planning.
- Surface AHJ SPD overrides in EE-5 via a separate `285 / AHJ` checklist
  row.

Closing standard:
- A NEC 2017 project remains service-SPD recommended by default.
- A project/profile that declares stricter service SPD policy turns the
  same NEC 2017 project into service-SPD required.
- Profile-required DC/ESS SPD locations are deduped into
  `required_locations`.
- Permit builder applies `--ahj` SPD policy even when passed an existing
  CalculationResult created before the AHJ was known.

Test plan:
- Unit tests cover stricter AHJ SPD policy on NEC 2017.
- AHJ profile tests cover `spd_policy` schema loading.
- Permit-builder regression verifies `--ahj` mutates the result's surge
  plan before rendering EE-5.

### Phase I — Real regional rules (already in CLAUDE.md)

Status: **complete**.

Development plan:
- Keep existing regional modules for CA Title 24, Hawaii Rule 14H, and
  Texas Oncor cover-letter generation.
- Add a regional aggregator as the single result surface for JSON, report,
  and doctor.
- Add NYC DOB / FDNY stationary ESS filing-readiness screening for projects
  with NYC location/AHJ metadata.

Closing standard:
- CA projects show Title 24 PV sizing and ESS-ready / NEM 3 awareness in
  `regional.checks`.
- HI projects show Rule 14H fast-track and smart-inverter/CSS review rows.
- TX/Oncor projects show DG cover-letter availability and ESID readiness.
- NYC ESS projects are never silently treated as generic IRC residential
  installs; DOB/FDNY review rows appear as MANUAL.
- `report.md` includes a Phase I regional table when checks apply.
- Doctor fails only hard regional failures and warns for MANUAL regional
  filing work.

Test plan:
- Phase I tests cover CA, HI, TX/Oncor, and NYC dispatch.
- Doctor tests cover Frisco regional PASS and NYC ESS MANUAL warning.
- E2E report test verifies the regional section renders for Frisco.

### K-future — UX surface (no estimate)
- VS Code extension (yaml schema validation + inline preview)
- Real wizard CLI replacing yaml hand-edit (Aurora-style flow)
- Multi-language: lift `nec/` to `code/` to support IEC + metric

---

## Historical Done Index

Past K-phases live in `CHANGELOG.md`. Latest:

- **2026-05-19**: Web UI W1-W13 local project generator (`pvess serve`)
- **2026-05-17**: K.13.1 EE-4 visual-collision polish; K.13 EE-4
  site-focused restructure (Stages A–D); K.4.6 + K.8.2 + K.9 +
  K.10 + K.11 + K.12 (single-day landings)
- **2026-05-16**: K.3c + K.8 + K.8.1 + roof-vis (analytical + satellite)
- **2026-05-15**: K.8 per-face derate
- **2026-05-14**: K.7 unified CLI + 3-version NEC dispatch
- **2026-05-13**: K.6 visual polish
- See `CHANGELOG.md` for the full history.
