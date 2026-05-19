# Changelog

All notable changes to **pvess-calc** are listed below. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) ; project uses
**K-phase milestones** rather than semver until a 1.0 release tag.

## [Unreleased]

Tracked work that's merged but not yet bundled into a tagged release.

### 2026-05-20 — Web Ops P2 prep: Cloudflare Access automation

- Added `configure-cloudflare-access.sh` for creating the Access self-hosted
  application, operator email allow policy, health-check service token, and
  service-auth policy
- Extended `online-smoke-curl.sh` to send Cloudflare Access service-token
  headers from `~/.pvess/secrets/cloudflare-access-service.env`
- Extended `pvess web-smoke` with Cloudflare Access service-token options
- Documented the required Cloudflare token permissions and operator email
  inputs
- Recorded the current blocker: the provided token verifies and can read the
  zone, but Cloudflare Access API endpoints return 403

### 2026-05-19 — Web Ops P1: access, backups, and uptime checks

- Added optional site-level HTTP Basic Auth for the Web server via
  `PVESS_WEB_BASIC_AUTH_USER` / `PVESS_WEB_BASIC_AUTH_PASSWORD`
- Extended `pvess web-smoke` and the public curl smoke script for
  Basic-Auth-protected deployments
- Reworked local backup creation to stage the workdir and use SQLite `.backup`
  for `web-jobs.sqlite3`
- Added restore-drill and public health-check scripts
- Added a LaunchAgent installer for daily backups and 5-minute public smoke
  checks
- Updated deployment docs and the operator runbook with access control,
  backup, restore, uptime, and token-rotation status

### 2026-05-19 — Web Ops P0: Cloudflare production stabilization

- Activated `reelamate.com` in Cloudflare and routed
  `https://tge.reelamate.com` through Cloudflare Tunnel
- Preserved the existing apex and `www` Vercel DNS records in Cloudflare
- Moved the running Web service into `~/Services/pvess-calc` for launchd-safe
  operation outside the Desktop privacy boundary
- Added user LaunchAgent runbooks for the local Web service and Cloudflare
  Tunnel
- Added `online-smoke-curl.sh` to verify the public Cloudflare path with
  `curl`
- Added `backup-local.sh` to archive the persistent Web workdir under
  `~/.pvess/reelamate-web`
- Added a P0 operator runbook covering health checks, restart, logs, backup,
  and token rotation

### 2026-05-19 — Web UI W30: local Cloudflare Tunnel profile

- Added a local workstation deployment profile for
  `https://tge.reelamate.com` using `pvess serve` plus Cloudflare Tunnel
- Added a loopback-only local startup script, env template, and example
  `cloudflared` ingress config under `deploy/reelamate/local-tunnel/`
- Documented the DNS precondition: `reelamate.com` must be managed by
  Cloudflare before `cloudflared tunnel route dns` can create the public
  hostname route
- Retargeted the Docker/Caddy fallback profile from `pvess.reelamate.com` to
  `tge.reelamate.com`
- Added smoke-check and security notes for local tunnel operation

### 2026-05-19 — Web UI W29: reelamate.com deployment profile

- Added a Docker Compose + Caddy deployment profile for
  the dedicated reelamate generator subdomain
- Documented DNS setup that keeps the current `reelamate.com` / `www`
  Vercel records intact while routing the PVESS tool through a subdomain
- Added an env template for the production access token and optional lookup
  provider API keys
- Added deployment smoke-check and backup commands for the persistent Web job
  volume
- Documented why the current FastAPI generator should run on Docker with
  persistent storage instead of Vercel serverless

### 2026-05-19 — Web UI W28: generated package review pass

- Ran the Web generator against the two Mansfield test addresses in PV-only
  and PV + ESS variants
- Verified Package QA runs for all four generated packages with zero FAIL
  results and valid ZIP archives
- Confirmed QA reports are persisted into each handoff ZIP
- Confirmed W25-W27 gate behavior across NOT_RUN QA, pending artifact review,
  artifact approval, and simulated-source blocking
- Recorded follow-up polish items for simulated site geometry, EE-4 fire-offset
  label placement, and DXF-derived low-text permit pages

### 2026-05-19 — Web UI W27: handoff review visibility

- Added per-required-artifact review rows to the Web AHJ gate response
- The Readiness panel now shows required artifact approval progress and each
  required artifact's current review status
- Added approved/pending styling for the handoff artifact review list
- Added regression coverage for the gate response and static UI contract

### 2026-05-19 — Web UI W26: review-gated AHJ handoff

- Added required-artifact approval to the Web AHJ gate
- Permit PDF, NEC label PDF, DXF sheets, PNG previews, and generated Package QA
  reports now block `AHJ-ready candidate` until approved for internal review
- Added required/pending artifact review counts to gate responses
- Added regression coverage for blocked and approved handoff paths

### 2026-05-19 — Web UI W25: QA-gated AHJ handoff

- Added Package QA status to the Web AHJ gate
- Packages now stay in `Internal review` until Package QA is `PASS`; missing,
  WARN, or FAIL QA blocks `AHJ-ready candidate`
- Running Package QA now refreshes and persists the job readiness gate
- Added `package_qa_status` to the SQLite job index
- Recent jobs now show gate level and Package QA status
- Added regression coverage for missing-QA blocking and QA persistence

### 2026-05-19 — Web UI W24: package QA workbench

- Added a Web package QA action for completed jobs
- The QA action runs `pvess-doctor`, validates the Complete Project ZIP, and
  checks generated PDFs for page count and searchable text
- Added `output/package-qa.json` and `output/package-qa.md` artifacts, exposed
  them in the generated-file list, and rebuilt the handoff ZIP to include them
- Added a browser **Package QA** panel with a **Run QA** control and a compact
  doctor/PDF/archive status summary
- Added regression coverage for QA persistence, file categorization, and ZIP
  inclusion

### 2026-05-19 — Web UI W21-W23: source intake, review workspace, AHJ gate

- Added utility-upload parsing for common CSV/text/PDF-like files; a real
  upload with 12 valid monthly kWh values now replaces simulated/form monthly
  usage in generated `inputs.yaml`
- Added filename-based auto-classification for unsorted site photos and spec
  sheets, plus selected-equipment spec-sheet coverage in preflight and source
  material status
- Added selectable lookup roof candidates instead of applying only one best
  roof section from lookup data
- Added document/sheet thumbnails in the Preview panel and per-artifact review
  state persisted in `review-status.json`
- Added package readiness levels: `Estimate only`, `Internal review`, and
  `AHJ-ready candidate`
- Added an AHJ gate that blocks simulated source materials, missing utility
  evidence, signed structural data, selected-equipment specs, PV-7 photos,
  field intake gaps, selected output incompleteness, and artifacts marked
  `needs revision`
- Extended Web regression tests for uploaded-source parsing/classification,
  review persistence, simulated/PV-only/PV+ESS gate paths, and UI terminology

### 2026-05-19 — Web UI W20: production deployment profile

- Added a Dockerfile production profile for the FastAPI Web app
- Set container default job storage to `/data/pvess-web` and declared it as a
  Docker volume so generated artifacts persist outside the image layer
- Added `.dockerignore` to keep outputs, SQLite files, caches, and virtualenvs
  out of the production build context
- Expanded `/api/health` with app version and storage status
- Added `pvess web-smoke` / `pvess-web-smoke` to verify health, static assets,
  auth mode, and a lightweight generated job
- Documented Docker run command, environment variables, backup strategy,
  health checks, and reverse-proxy assumptions

### 2026-05-19 — Web UI W19: operator accounts and isolation

- Added SQLite-backed operator token storage with hashed tokens and one-time
  token return on creation
- Preserved `PVESS_WEB_ACCESS_TOKEN` / `pvess serve --access-token` as the
  admin/bootstrap mode
- Added `owner_id` to Web job state and job index records
- Scoped job history, job detail, payload loading, rerun, delete, and file
  downloads by operator owner
- Added admin-only all-jobs support via `/api/jobs?all_jobs=true` and the
  Recent jobs **All jobs** filter
- Added regression tests for operator creation, cross-owner denial, admin
  all-jobs access, and owner-scoped delete/download behavior

### 2026-05-19 — Web UI W18: durable job storage

- Added a SQLite-backed Web job index at `<workdir>/web-jobs.sqlite3` while
  keeping generated artifacts on disk
- Indexed job state, payload summary, project/address search fields,
  source-material status, readiness status, installed cost, and artifact list
- Added compatibility import from existing `job-status.json` folders so old
  local jobs remain visible
- Added API and browser job filters for status, project/address text, and
  created date range
- Extended Web regression tests for empty database, legacy import, filtering,
  delete cleanup, sync-job persistence, and artifact-index consistency

### 2026-05-19 — Web UI W17b: release-readiness closeout

- Reorganized `ROADMAP.md` so upcoming Web phases W18-W23 are explicit
  planned work and completed W1-W17a items sit under completed milestones
- Removed duplicated production-Web future wording now covered by W18-W20
- Prepared the Web UI W1-W17a workstream for GitHub publication with a
  focused release branch and validation pass

### 2026-05-19 — Web UI W17a: language standardization

- Added `docs/web-ui-language.md` as the user-facing terminology and copy
  standard for the TGE Solar Project Generator
- Standardized Web UI labels around Project, Preflight, Package, Preview,
  Readiness, Source materials, Generated files, and BOM cost
- Added built-in address samples for `905 Crossvine Drive, Mansfield, TX` and
  `2806 Green Circle Drive, Mansfield, TX`
- Added DFW simulated residential monthly usage for Mansfield smoke tests,
  clearly treated as simulated source material until replaced by real bills
- Added regression tests for page terminology and Mansfield address generation

### 2026-05-19 — Web UI W14-W16: deployment hardening, preview, lookup

- Added optional `PVESS_WEB_ACCESS_TOKEN` / `pvess serve --access-token`
  protection for Web API and generated-file routes
- Added optional CORS origin configuration through `PVESS_WEB_CORS_ORIGINS`
  for hosted deployments
- Added `/api/runtime-config` and `/api/lookup/address`, with offline-only
  and online-if-configured lookup modes
- Wired address lookup into the browser form so utility, AHJ, NEC edition,
  coordinates, tariff, and roof defaults can be prefilled from existing
  lookup providers
- Upgraded the Preview panel with an embedded PDF/PNG viewer while preserving
  direct file-open/download links
- Extended Web regression coverage for token-protected API/files and offline
  address prefill

### 2026-05-19 — Web UI W1-W13: local project generator MVP

- Added `pvess serve`, a local FastAPI + static browser UI branded as
  **TGE Solar Project Generator**
- Added browser intake for project metadata, address/site fields, PV module,
  battery, and single selected inverter brand/model path
- Added generated BOM cost estimates, cost overrides, quote tiers, BOM CSV,
  artifact manifest, and complete package ZIP export
- Added preflight checks, async generation jobs, source-data readiness,
  generated-file filtering, preview/download links, and recent-job
  load/rerun/delete actions
- Added upload handling for site photos, utility bills, structural letters,
  and equipment spec sheets, plus explicit simulated-photo/source-data output
- Documented the Web UI flow and added endpoint/UI regression coverage

### 2026-05-18 — Phase I: regional-rule summary closure

- Added a `regional` calculation-result surface that aggregates CA Title 24,
  Hawaii Rule 14H, Texas/Oncor, and NYC DOB/FDNY ESS filing checks
- Added NYC stationary ESS filing-readiness screening so NYC ESS projects
  surface DOB/FDNY manual review instead of falling through generic IRC
  assumptions
- Rendered applicable regional checks in `report.md`
- Added `regional_requirements_consistent` doctor coverage and tests for
  Frisco regional PASS plus NYC ESS MANUAL review

### 2026-05-18 — Phase H.4: AHJ-specific SPD policy overrides

- Added optional AHJ profile `spd_policy` configuration for stricter service,
  DC, and ESS surge-protection requirements
- Added `project.ahj_profile` and wired `pvess permit --ahj` into Phase H
  surge planning
- Ensured AHJ SPD policy can only make base NEC results stricter, not relax
  NEC 230.67 when the selected NEC edition already requires service SPD
- Surfaced AHJ SPD overrides in EE-5 with a `285 / AHJ` checklist row
- Added regression tests for strict AHJ SPD policy, profile loading, and
  permit-builder propagation

### 2026-05-18 — Phase H.3: configurable raceway types

- Added `routing.pv_raceway_type` and `routing.ac_raceway_type` with EMT
  defaults for backward-compatible project inputs
- Extended Chapter 9 40% fill sizing from EMT-only to EMT, PVC Schedule 40,
  PVC Schedule 80, RMC, and FMC raceway tables
- Propagated configured raceway type through aggregate Phase H facts,
  A/B/C/D raceway segments, topology conductor schedules, and `report.md`
- Added regression tests for PVC80 step-up behavior, topology propagation,
  and non-EMT report rendering

### 2026-05-18 — Phase H.2: routed raceway schedule

- Added `adjacent.raceways[]` with A/B/C/D segment records, K.11 route
  lengths, conductor sizes, selected raceway, and Chapter 9 fill percent
- Kept legacy `pv_conduit` / `ac_conduit` aggregate fields while making the
  segment schedule the detailed source for EE-2 / EE-2.1 topology output
- Added a H.2 raceway table to `report.md`
- Tightened `phase_h_adjacent_calcs_complete` so doctor fails missing
  H.2 segments, overfilled segment raceways, and routed zero-length B/C/D
  raceways
- Added regression tests for routed Frisco raceway lengths, topology
  propagation, report output, and doctor missing-segment failure

### 2026-05-18 — Phase H.1: adjacent protection closure

- Added datasheet-backed DC AFCI recognition for the selected Growatt
  MIN 11400TL-XH-US path, plus Hoymiles/Megarevo candidate recognition for
  future scenario swaps
- Extended inverter metadata with `dc_afci` and `ul1699b_listed` so device
  refs can carry NEC 690.11 evidence without hard-coded project logic
- Split SPD planning into NEC 230.67 required service SPD for 2020+ dwelling
  services and recommended PV/ESS-side SPD locations
- Added conduit-fill percentage and unknown-conductor validation to the
  Chapter 9 EMT fill selector
- Surfaced Phase H outputs in `report.md` and EE-5 compliance checklist
- Added `phase_h_adjacent_calcs_complete` doctor guard for AFCI evidence,
  required SPD location, ground-rod field proof, and overfilled conduit

### 2026-05-18 — Stage 5.1: reference data readiness simulation

- Added `reference_profile_data_readiness` doctor output to separate
  ready field data from simulated/mock/TBD data, missing signed attachments,
  and PV-only not-applicable ESS inputs
- Added a reusable readiness assessor that can generate a Markdown data-gap
  report for the Frisco reference package
- Kept the check non-blocking (`WARN`) so simulated data can be used for
  layout iteration without being mistaken for AHJ-ready source material
- Clarified `ess_install_compliant` so PV-only projects skip ESS install
  readiness instead of warning on a deliberately empty battery block
- Added `pvess readiness` / `pvess-readiness` to regenerate the Markdown
  readiness report from any project, with `--strict` for AHJ-ready gating
- Added `simulated-site-data.yaml` source-pack support so mock photos,
  synthetic usage, modeled roof geometry, and placeholder metadata have
  explicit replacement standards and cannot accidentally report as ready
- Added opt-in permit `--readiness-appendix` support for internal review
  packages. The appendix is outside the Sheet Registry, omitted by default,
  and clearly marked not for AHJ submission
- Tightened SPEC handling so `project.spec_sheets[]` represents selected
  equipment only. Frisco now submits only the selected Growatt inverter
  datasheet; Hoymiles / Megarevo PDFs are retained as candidate references
  outside the permit SPEC path
- Added `output/real-data-checklist.md` generation from `pvess readiness`,
  giving operators a concrete replacement action for each simulated/missing
  data item before running the strict AHJ-ready gate

### 2026-05-18 — Stage 10.2: visual-stability guards

Closed the post-reference-package stabilization pass for EE-2 / EE-2.1 / PV-5:

- Added `dxf_wire_text_no_overlap` doctor guard for conductor geometry crossing
  visible DXF `TEXT` / AutoCAD `ATTRIB` labels on EE-2 and EE-2.1
- Added `pv5_text_no_overlap` doctor guard for mounting-detail callout text
  collisions
- Shifted the EE-2 schematic down to clear top notes from multi-string PV bus
  geometry
- Hid duplicate inverter ATTRIB text that conflicted with the ESS/battery drop
  while preserving AutoCAD Electrical metadata
- Adjusted PV-5 FlashVue callout placement to remove text crowding
- Added regression-bait tests for crossed DXF text, crossed visible ATTRIBs, and
  PV-5 overlapping callouts

### 2026-05-18 — Stage 9.11-9.17: reference-style planset profile

Completed the Wyssling/Texas Green Eco style package path:

- Added `tx_residential_pv` / `wyssling_like` permit profiles with PV-1/PV-7,
  EE-1/EE-5, conditional EE-2.1, and SPEC numbering
- Extended `inputs.yaml` schema for roof/framing/attic/decking survey data,
  meter/ESID, site photos, signed structural-letter PDFs, and manufacturer
  spec sheets
- Added new renderers for EE-2.1 one-line, EE-5 placard, PV-6 design notes,
  PV-7 site photos, SPEC placeholder/appendix, and unsigned structural-review
  draft
- Updated the permit builder so reference profiles can prepend signed/draft
  structural packets, append selected SPEC PDFs, and keep the cover sheet index
  in sync with emitted sheets
- Added doctor guards `reference_profile_site_intake_complete` and
  `reference_profile_attachments_ready`
- Added regression tests for profile sheet order, conditional one-line
  emission, draft/photo/spec placeholder output, and reference-profile doctor
  behavior

### 2026-05-18 — Stage 9.8/9.9: EE-4A property-context plan

Stage 9.8 split the competitor-style property context out of EE-4 into a
new `EE-4A · PROPERTY CONTEXT PLAN` sheet. EE-4 now stays focused on roof
array geometry and equipment callouts; EE-4A carries property line,
driveway, fence, north arrow, dimensions, and the traced roof overlay.

Stage 9.9 makes EE-4A data-driven:

- Added `site.property_context` schema with `lot_outline`,
  `driveway_polygon`, `fence_lines`, and `property_dimensions`
- Renderer now uses those survey / GIS / satellite-reviewed geometries
  when present, with the 9.8 generated rectangle / driveway kept as a
  backward-compatible fallback
- Frisco fixture now supplies explicit context geometry, so the top and
  right dimension callouts render from YAML rather than inferred bounds
- Added regression tests for registry wiring, polygon validation, and
  rendered EE-4A survey dimension text

### 2026-05-18 — Stage 9.10.1-9.10.3: PV-6 traced string layout

Started the reference-style string layout sheet:

- PV-6 now uses the whole traced roof plan when `site.ee4_trace` and
  per-module placements are present
- Each module is filled by actual `string_index` with saturated string
  colors and a small per-module string number
- Added the left-side module/inverter/optimizer summary, string legend
  swatches, north arrow, scale note, and top-right equipment summary
- Legacy projects without trace geometry keep the previous per-section
  string layout fallback

### 2026-05-18 — Stage 9.10.4/9.10.5: PV-6 callouts and visual lint

Completed the PV-6 string-plan closeout:

- Added automatic external `STRING N` leader callouts around the traced roof
- Shared the PV-6 trace transform / callout layout between renderer and lint
- Added `permit/pv6_lint.py` with checks for rollup completeness, missing
  callouts, label-label collisions, and label-module collisions
- Added doctor check `pv6_string_layout_visual_lint`
- Added regression tests for callout count, missing string assignments, and
  doctor-detected label collisions

---

## 2026-05-17 — K.13.1: EE-4 visual-collision polish

Follow-up to K.13. Post-K.13 visual review of Frisco's EE-4
surfaced 4 specific text-on-text collisions that didn't trip any
doctor check (visual not structural). K.13.1 closes them.

### P0 — Optimizer leader callout moved inside the lot

Pre-K.13.1 the leader endpoint was at
`lot_x + lot_w_pt + 0.20 * inch` — exactly where the SITE
INFORMATION column begins. The "(N) PV MODULE EQUIPPED W/ ..."
text overprinted the right-column "Lot dimensions / Residence
footprint" rows.

Fix: endpoint relocated to inside the lot top-right
(`lot_x + lot_w_pt - 1.70 * inch`, ~0.45" below lot top). Leader
now goes vertical-first (target module → up → bend → horizontal
to text) to keep the line from crossing other module rows.

### P1 — PV ARRAY caption moved from bottom margin to top banner

Pre-K.13.1 the caption sat at `lot_y - 0.48 * inch` (Stage C
placement). When the leader-callout column stacked horizontally
below the lot (3+ equipment chips), the caption and labels
competed for the same horizontal band.

Fix: caption relocated to `lot_y + lot_h_pt + 0.22 * inch` (top
banner above the lot), left-anchored. The conduit-routed legend
chip moved to right-anchored on the same banner — caption left
+ legend right, no overlap.

### P2 — auto-anchor corner inset

Pre-K.13.1 `auto_anchor_sections()` placed every cursor flush
against its wall's starting corner. For Phoenix-style 2-face
yamls (South + West, both 38×24 ft on a 50×35 ft house) the SW
corner was double-claimed and the two face footprints
geometrically overlapped.

Fix: each cursor's starting position is inset by the
perpendicular orientation's max H. `_inset_or_zero()` falls
back to flush when the inset would consume more than half the
wall (data over-packed signal — overlap is the right visual cue).

Phoenix outcome: South cursor moves 15 → 39, leaving West's
24 ft eastward inset free of conflict.

### P3 — PROPERTY LINE label moved off bottom-right

Pre-K.13.1 the label sat at bottom-right outside the lot
(`lot_y - 0.14 * inch`). When the leader-callout column went
stacked_below, the label crowded the rightmost callout.

Fix: label relocated to top-left outside the lot
(`lot_y + lot_h_pt + 0.06 * inch`), in the corner where the
rotated address column ends. Cleanly separated from all the
bottom-margin content (leader callouts, setback dims, scale bar).

### Tests

- **13 new tests** in `tests/test_ee4_k131_polish.py`:
  - P0: source-string check + Frisco end-to-end PDF text check
  - P1: caption banner placement + conduit right-anchor + content
  - P2: Phoenix inset numerical contract + single-orientation
    pass-through + half-wall fallback threshold + engine
    integration
  - P3: source-string check + content preservation
  - Cross-cutting: all 3 projects render + doctor still passes
- **Total: 635 passing (was 622). 39 doctor checks (unchanged —
  K.13.1 is pure visual polish, no new structural invariants).**

### Visual benchmark (Frisco EE-4 220 DPI)

| Collision | Pre-K.13.1 | Post-K.13.1 |
|---|---|---|
| Optimizer leader vs SITE INFORMATION | text overprinted "Lot dimensions" row | Leader inside lot top-right; SITE INFORMATION fully readable |
| PV ARRAY caption vs leader callouts | both at bottom margin, same band | Caption on top banner; callouts at bottom unobstructed |
| Phoenix South + West auto-anchor | SW corner double-claimed, footprints overlap | South inset to x=39; faces clearly separated |
| PROPERTY LINE vs rightmost leader | 0.05" horizontal gap to "(N) INV-1 ..." | Label at lot top-left; clean separation |

### Known limits (not in K.13.1 scope)

- **Frisco's explicit anchors** keep the SW corner overlap between
  South #1 and West #1 — it's a designer-encoded yaml decision,
  not an auto-anchor artefact. Changing it requires yaml edit
  (e.g. shift West anchors to NW corner). Out of scope.
- **Phoenix South face overflows east** by ~12 ft after the inset
  (38 ft face + 24 ft inset starts past the 50 ft east wall).
  The overflow IS the correct visual signal that the yaml's
  roof_sections don't fit the declared house dimensions.

---

## 2026-05-17 — K.13: EE-4 site-focused restructure (Stages A → D)

Closes the EE-4 "looks like a placeholder" gap surfaced when the user
spot-checked the Frisco permit package. Pre-K.13 a project without
explicit per-face `site_anchor` data fell back to a painted yellow
PV ARRAY rectangle + synthetic N×M module grid on top of the centred
house rect — visually redundant with PV-4 and consistently confusing
to AHJ reviewers. K.13 deletes that path entirely; every project
either gets real per-face module geometry (auto-anchored when not
hand-anchored) or a clear "see PV-4" warning strip.

Landed in 4 staged passes:

### Stage A — Frisco yaml: explicit K.11 site geometry

- Added `site.lot/house` dimensions + `equipment_locations` block
  (MSP, AC-DISC, Inverter, attic drop) to the Frisco yaml
- Added `site_anchor_x_ft / _y_ft / _azimuth_deg` to each of the
  5 roof_sections (3 South stacked along south edge, 2 West along
  west edge)
- Frisco EE-4 immediately upgraded from blank lot → real modules +
  orange Manhattan conduit polyline + leader callouts
- Doctor `auto_routed_lengths_sane` PASS with longest segment 48 ft

### Stage B — Auto-anchor for any yaml with `roof_sections`

- New module **`src/pvess_calc/calc/site_layout.py`**:
  - `auto_anchor_sections(site)` — by-azimuth quadrant classifier
    (S/E/N/W) + per-wall head-to-tail stacking with 1 ft gap
  - `apply_auto_anchors(site, anchors)` — pure: returns deep-copy
    with anchors patched; never mutates input
  - `house_bbox(site)` — uses polygon outline when present, else
    centred rect from `house_width_ft × house_depth_ft`
- Hooked into `engine.run()` at
  entry so all downstream code (wire_routing, EE-4 renderer,
  doctor) sees fully-anchored sections without behaviour changes
- Phoenix (2 faces, no explicit anchors) now renders multi-face
  geometry on EE-4 with zero yaml edits
- **17 new tests** in `tests/test_site_layout.py` covering single-
  face per-orientation, multi-face stacking, mixed orientations,
  explicit-anchor pass-through, determinism, engine integration

### Stage C — Visual density polish

5 layout adjustments to fix overlap + missing-data signalling:

1. **Aerial inset radius 25 m → 35 m** in
   `_draw_aerial_inset` — at
   25 m, suburban ≥80 ft lots cropped past the neighbour buildings
2. **Rotated address offset 0.30" → 0.50"** off the lot's left
   property line (was visually pressed against the lot dashed line)
3. **`PROPERTY LINE` label moved top-left → bottom-right** outside
   the lot to clear the rotated address + the routed-mode legend
   strip above the lot
4. **PV ARRAY caption relocated to bottom margin** between the lot
   frame and the scale bar. Pre-Stage C the caption sat at
   `bb_y_bot - 0.16"` which for arrays anchored on the south wall
   pushed the text BELOW the lot frame, colliding with the scale bar
5. **`NOTE — Array shown schematically` warning strip** at the top
   of EE-4 when neither `routed` nor `has_face_anchors` is active
   (Stage D revised wording to "PV array geometry omitted from EE-4")

**8 new tests** in `tests/test_site_plan_polish.py`.

### Stage D — EE-4 K.13 restructure

The closing pass. Surgical deletes + structural cleanup:

- **Deleted the legacy abstract PV-grid block** in `site_plan.py`
  (lines 175-218 of the pre-K.13 code): the yellow `_PV_COLOR`
  rectangle + `_pick_module_grid()`-driven N×M cell layout +
  "PV ARRAY · ... · 6×4 grid · see PV-4" caption — all gone
- **`_pick_module_grid()` deleted as dead code** (47 lines)
- **Aerial inset enlarged 2.5×2.2" → 3.0×2.6"** to use the right
  column space freed by the deleted abstract render. SITE
  INFORMATION column anchor pushed `W - 3.2"` → `W - 3.4"` to keep
  the wider inset inside the page frame
- **Warning strip wording revised** from "Array shown
  schematically..." to "PV array geometry omitted from EE-4 (no
  site.roof_sections in yaml). See PV-4 for module attachment plan.
  EE-4 shows lot + setbacks + equipment." — explicit + actionable

#### Three EE-4 render modes (Stage D contract)

| Trigger | Renders |
|---|---|
| `wire_routing.routed=True` | Real K.9.1 modules + fire-offset hatch + Manhattan conduit polyline + leader-line equipment callouts |
| `has_face_anchors=True` only | Real modules + fire-offset hatch (no conduit, no leaders — no equipment_locations available) |
| neither (no roof_sections) | Lot + house outline + setbacks + K.6 east-wall equipment chips + NOTE warning strip |

#### New doctor check

**`ee4_focuses_on_site_geometry`** — renders EE-4 to a temp PDF +
greps for the legacy `\b\d+\s*[×x]\s*\d+\s+grid\b` regex pattern.
FAILS if any `N×M grid` substring leaks back into EE-4. Positive
states report `per-face render active (N section(s))` or
`incompleteness NOTE strip` depending on yaml shape. **Doctor list
38 → 39.**

#### Tests

- **12 new tests** in `tests/test_ee4_k13.py`: abstract-grid
  absence on all 3 sample projects, `_pick_module_grid` dead-code
  removal, doctor check positive cases (Austin / Phoenix / Frisco),
  per-mode contracts (routed / anchor-only / pure-legacy), aerial
  inset size locks, info-column width lock
- **Updated 2 existing tests**:
  - `test_legacy_yaml_keeps_abstract_grid` →
    `test_legacy_yaml_has_no_abstract_grid_after_k13` (assertion
    inverted — must NOT find grid pattern)
  - `test_ee4_site_plan_has_equipment_route_legend` — re-narrated
    to make the K.13 carve-out explicit (K.6 east-wall column
    kept; abstract PV grid deleted)
- **Total: 622 passing (was 585). 39 doctor checks (was 38).**

### Visual benchmark

Frisco EE-4 before / after K.13:

| Element | Pre-K.13 | Post-K.13 |
|---|---|---|
| Lot area | Mostly empty (~94% blank) | Dense — real footprints + conduit + setbacks |
| PV array | 24×16 ft yellow box, 8×5 abstract grid | 5 real face footprints with 34 K.9.1-placed modules |
| Equipment | 3 floating chips on east wall (synthetic) | 4 leader-line callouts at real (x,y) on east wall |
| Conduit | None | Manhattan polyline (orange dashed) for 4 segments |
| Aerial | 2.5×2.2" street-view radius 25 m | 3.0×2.6" Google Solar dataLayers radius 35 m |
| Fire offset | None on EE-4 | Orange hatch bands per face + "18\" FIRE OFFSET" callout |

Phoenix EE-4 went from "yellow placeholder box" → "2 real face
footprints with auto-anchored modules" with zero yaml edits.

Austin EE-4 (true legacy — no roof_sections at all) went from
"yellow box + 6×4 abstract grid" → "clean lot + setbacks + warning
strip pointing to PV-4".

### Known limits (not in K.13 scope)

Surfaced during the post-K.13 visual review of Frisco's EE-4; will
be picked up in K.13.1 visual-polish:

- **Optimizer leader callout overlaps SITE INFORMATION column** —
  end_x of the leader is too close to the right column anchor
- **PV ARRAY bottom-margin caption + leader-callout column compete
  for the same horizontal band** in routed mode when labels stack
  below the lot
- **5-face anchor stacking shares corners** — South #1 + West #1
  geometrically overlap at the SW corner because the auto-stacker
  packs faces tight against the wall starting point
- **PROPERTY LINE label sits 0.05" from the rightmost leader
  callout** — needs a horizontal nudge or a move to lot-top in
  routed mode

---

## 2026-05-17 — K.11: wire trunk auto-routing

Closes the loop between K.9.1 module placement, K.10 string assignment,
and the NEC 215.2 voltage-drop math. Pre-K.11 every project hand-typed
six numbers in `inputs.wire_lengths` (50 ft fallback per segment when
omitted). Post-K.11 those numbers are computed from real 2D site
coordinates: per-face roof penetration → attic drop → equipment column.
Manhattan-routing assumption keeps the algorithm conservative (over-
estimates by 5-10 % vs straight-line, which is safe for NEC).

### Added

- **3 schema models** (all additive — legacy yamls untouched):
  - `RoofSection.site_anchor_x_ft / _y_ft / _azimuth_deg` — roof-local
    → 2D site-coord transform per face (the eave-left corner gets a
    site position + an azimuth for the eave direction)
  - `RoofSection.roof_penetration_x_ft / _y_ft` — where the string
    trunk conduit penetrates each face; defaults to the ridge midpoint
    (`apex` for triangular faces)
  - `EquipmentLocations` block on `Site` — MSP, inverters, sub-panels,
    ESS units, AC disconnect, attic_drop_point — each as
    `EquipmentLocation(label, x_ft, y_ft)`. `has_data` property gates
    routing activation on at least `msp + 1 inverter`.
- **`calc/wire_routing.py`** — `compute_wire_routing()` produces a
  `WireRoutingResult` carrying:
  - 5 per-segment lengths (A · PV source through E · ESS → INV)
  - `segments` list with per-segment label + provenance + 2D
    waypoints (for DXF polyline rendering)
  - `routed` flag + `fallback_reason` for the doctor check
  - Manhattan distance helpers + `_face_local_to_site()` transform
- **`CalculationResult.wire_routing: Optional[WireRoutingResult]`** —
  exposed in `to_dict()` for JSON export + report consumption
- **EE-4 overlay** — when routing is active, draws the real conduit
  polyline (orange dashed Manhattan path) + equipment dots with labels.
  Legend chip identifies the auto-routed layer. Legacy path (when
  `routed=False`) keeps the K.6 east-wall column bit-identical.
- **Doctor check `auto_routed_lengths_sane`** — verifies no single
  segment exceeds 200 ft (catches frame/unit-mismatch bugs like coord
  swap or m ↔ ft confusion). +1 to doctor list (37 → 38 checks).

### Changed

- **`engine.run()`** — restructured to compute module placements
  (K.9.1 + K.10) BEFORE voltage_drop. K.11 wire routing slots between
  placement and voltage_drop; when active, builds an `inputs_for_vd`
  overlay via `model_copy(update={"wire_lengths": ...})` so voltage-
  drop math consumes the auto-routed numbers without mutating the
  user's yaml.
- **`_compute_module_placements()`** — extracted from inline `run()`
  body into a top-level helper (no behaviour change; reusable).

### Tests

- 20 new tests in `tests/test_wire_routing.py` covering:
  - Degenerate fallback (empty equipment_locations, msp-only)
  - Coordinate transform at 0° / 90° / partial-anchor cases
  - Per-segment math: A (worst-case module, 5ft min), B (avg face),
    C (2ft min cable allowance), D (sub-panel chain in order),
    E (worst-case ESS, 0 when no ESS)
  - Engine integration (routed=True overrides manual wire_lengths)
  - WireRoutingResult shape contract (all 5 segments present with
    waypoints + provenance="routed")
- 3 new tests in `tests/test_doctor.py`:
  - Legacy yaml → PASS-skip with "legacy" detail
  - Sane routing → PASS with "200 ft envelope" detail
  - 500 ft equipment placement → FAIL with frame-hint message
- **Total: 576 passing (was 553). 38 doctor checks (was 37).**

### Why this matters

The 50 ft default was a Phase 0 placeholder — engineering review of
a 14 kW Frisco install with real 60+ ft DC runs would have shown
**voltage drop at 2 % vs the 0.8 % the report claimed**. K.11
closes that gap for any project that fills in site coords, and the
sane-bounds doctor check catches the most common data-entry mistake
(unit / frame mix-up) before it reaches AHJ submission.

---

## 2026-05-17 — K.10: string-level layout + EE-1 string overlay

Closes the loop between K.9.1 per-module placement and the
electrical-side string plan. Pre-K.10 PV-4 colored every module a
single shade of blue, and EE-1 used a synthetic `√n × √n` heuristic
grid that didn't match PV-4's real geometry. Post-K.10 every module
carries its assigned `string_index`; PV-4 + EE-1 share one color
scheme + one underlying placement; AHJ reviewer reads strings without
flipping between sheets.

### Added

- **`calc/string_assignment.py`** — `assign_modules_to_strings()`
  implements face-coupled, ridge-first, balanced allocation. Spec:
  - Sort key: `(face_name, -y, x)` — ridge → eave → left → right
  - Counts: round-robin trim from end on shortfall (34/4×9 → [9,9,8,8],
    33/4×9 → [9,8,8,8]). K.10.5 doctor invariant `|max - min| ≤ 1`
    holds for any total / n_strings / target combo.
- **`ModuleInstance.string_index: Optional[int]`** — 0..n_strings-1
  after `engine.run()` populates it. `None` only for n_strings ≤ 0
  degenerate yaml.
- **PV-4 color-by-string** — `_string_stroke()` / `_string_fill()`
  helpers wrap `STRING_COLORS` with `_lighten_hex()` for soft pastel
  fills + saturated strokes. Each module rect drawn in its string's
  color. Footer note updated to mention K.10 color semantics.
- **PV-4 string legend** (bottom-left, mirrors module dim callout):
  swatch + `S{n}: {count} mods · {faces}` rows, textfit-truncated.
- **EE-1 string plan rewrite** — replaces the K.10.0 heuristic grid
  with per-section roof plans (reusing `_draw_section_plan`) + a
  per-string details table (count / faces / Voc-cold / conductor).
  Footer cites NEC 690.7(A) 600 V dwelling cap.
- **Doctor check `string_balance_within_target`** — PASS when
  spread ≤ 1; WARN at 2; FAIL at ≥ 3 or when any string exceeds
  target (NEC 690.7(A) headroom breach). +1 to the doctor list
  (36 → 37 checks).

### Changed

- **`engine.run()`** — after `place_modules` per face, flattens
  placements, calls `assign_modules_to_strings`, re-buckets by face
  preserving K.9.1 ridge-first order. Legacy single-orientation
  yamls (empty `module_placements`) are bit-identical to pre-K.10.
- **`_allocate_string_counts()` algorithm fix** — pre-K.10.1 dev
  code lumped the whole shortfall on the tail string (`34/4×9 →
  [9,9,9,7]`) violating the `|max-min| ≤ 1` invariant. Switched to
  round-robin trim from end. Doctor invariant + test
  `test_assign_shortfall_first_strings_full_length` lock the new
  behavior.

### Tests

- 18 new tests in `tests/test_string_assignment.py` covering empty /
  degenerate, clean divide, shortfall, surplus, face coupling,
  ridge-first ordering, balance helpers, immutability, and the live
  Frisco 34-module / 5-face case.
- 4 new tests in `tests/test_doctor.py` for the new doctor check
  (Phoenix PASS, Frisco PASS-with-spread-1, Austin PASS-skip,
  drift FAIL via monkey-patched `module_placements`).
- **Total: 553 passing (was 531). 37 doctor checks (was 36).**

---

## 2026-05-17 — K.12: industry-standard PV-1 cover page (Wyssling-style)

Closes the cover-sheet gap surfaced by the user's 2026-05-17 comparison
to a real Wyssling Consulting permit. Pre-K.12 cover was the legacy
4-block (client / engineer / system summary / installer) layout; post-
K.12 cover matches the 12-block AHJ-submittal convention used by major
US residential installers, including aerial + vicinity maps when API
keys are available.

### Added

- **5 new schema models** in `schema.py` (all optional, defaults
  preserve every pre-K.12 yaml):
  - `RoofInfo`: stories, type, height_ft, construction, condition,
    being_replaced, flashing
  - `BuildingCodes`: IBC + IRC + IFC + IFGC + IEBC + IECC + IMC + IPC
    versions (default 2021 cycle — dominant US residential as of 2026)
  - `DesignCriteria`: wind speed, snow load, ASCE version, exposure,
    occupancy, construction type, sprinklers (default 115 mph / 5 psf
    / ASCE 7-16 / R-3 / V-B / no sprinklers — DFW typical)
  - `MeterInfo`: utility meter number, location, Oncor ESID
  - `RevisionEntry`: date + revision letter + comment for the cover's
    revision history table
- **`src/pvess_calc/permit/cover_maps.py`** — aerial + vicinity map
  fetchers:
  - `fetch_aerial_map_png(lat, lng)` — reuses K.3c+ Google Solar
    dataLayers RGB; returns None when `PVESS_GOOGLE_SOLAR_KEY` missing
  - `fetch_vicinity_map_png(lat, lng)` — Mapbox Static Images API
    (~$0.005/render, ~10× cheaper than aerial); returns None when
    `PVESS_MAPBOX_TOKEN` missing
  - Both cached on-disk under `~/.pvess/cache/cover_maps/`
- **`permit/cover_sheet.py` v2** — complete rewrite. 12 blocks:
  TITLE STRIP, AERIAL MAP, VICINITY MAP, SHEET INDEX, SCOPE OF WORK,
  GOVERNING CODES, DESIGN CRITERIA, ROOF INFO, INTERCONNECTION,
  ARRAYS table, METER INFO, REVISION HISTORY, PE STAMP placeholder.
  Each block is a self-contained `_draw_*` function for maintainability.
- **`pvess-doctor cover_has_governing_codes_for_ahj`** — regression
  guard that catches anyone wiping the 8 ICC family code defaults
  (which would render empty cells AHJ rejects). Validates every
  IBC/IRC/IECC/etc. has a 4-digit year.
- **22 new tests** across 2 files:
  - `tests/test_k12_schema.py` (8) — default-construction zero-args,
    BuildingCodes 2021 cycle defaults, DFW design criteria defaults,
    optional MeterInfo/RevisionEntry, ProjectMeta integration,
    backward-compat Phoenix yaml load
  - `tests/test_k12_cover.py` (14) — title strip with industry phrasing,
    all 12 blocks present, governing codes + design criteria content,
    roof info defaults + explicit values, ESID rendering, arrays table
    per-section, revision history (1-row fallback + N-row explicit),
    map placeholders when keys absent, K.12.5 doctor positive + negative

### Changed

- Cover sheet title now reads **"NEW PV SYSTEM DESIGN"** (Wyssling
  convention) instead of "PV + ENERGY STORAGE SYSTEM / PERMIT
  SUBMITTAL PACKAGE" (legacy). Sub-headline shows
  `N MODULES · X kW DC · Y kW AC SYSTEM SIZE`.
- Frisco permit-package PDF cover (page 1 of 12) now renders the
  full 12-block layout; with both API keys set, it includes aerial
  imagery from Google Solar dataLayers + vicinity street map from
  Mapbox Static — matching the visual density of the Wyssling
  reference image at 80%+ information completeness.

### Visual benchmark

Frisco PV-1 v2 vs 2026-05-17 Wyssling reference:
| Element | Reference | pvess-calc K.12 | Match |
|---|---|---|---|
| Title + system size headline | ✓ | ✓ | ✓ |
| Aerial map | ✓ | ✓ (Google Solar) | ✓ |
| Vicinity map | ✓ | ✓ (Mapbox Static) | ✓ |
| Sheet index | ✓ | ✓ (registry-driven) | ✓ |
| Scope of work | ✓ | ✓ | ✓ |
| Governing codes | 9 codes | 9 codes | ✓ |
| Design criteria | 7 items | 7 items | ✓ |
| Roof info | 7 items | 8 items | ✓+ |
| Interconnection | ✓ | ✓ | ✓ |
| Arrays table | ✓ | ✓ | ✓ |
| Meter info | ✓ (Oncor) | ✓ (incl. ESID) | ✓ |
| Revision history | ✓ | ✓ (with fallback) | ✓ |
| PE stamp area | ✓ | ✓ (placeholder) | ✓ |

Closes K.12 from the ROADMAP (originally 3-4 days; landed in 1
session). Tests 507 → 529; doctor 33 → 34.

---

## 2026-05-17 — K.9: per-module placement + PV-4 v2 (Aurora-grade attach plan)

Closes the visual gap between pvess-calc's PV-4 (K.2.6c grid concept)
and Aurora / OpenSolar's permit drawings: each module now renders at
its true (x, y, rotation) with the correct physical aspect ratio +
a corner dimension callout. The placement algorithm respects every
existing constraint (edge setbacks, obstruction halos, K.2.7 polygons).

### Added

- **`src/pvess_calc/calc/module_placement.py`** — new placement engine:
  - `ModuleInstance` frozen dataclass: `face_name / x_ft / y_ft /
    width_ft / height_ft / rotation_deg`. Roof-local coords.
  - `place_modules(section, *, module_length_in, module_width_in,
    target_count, ...)` — tries landscape + portrait orientations,
    picks whichever fits more, respects setbacks + obstruction halos,
    sorts ridge-first.
  - Supports rect / tri / polygon face shapes.
- **`src/pvess_calc/calc/face_distribution.py`** — extracts the K.8.1
  Largest Remainder Method from `customer/production.py` so BOTH the
  engine (PV-4 placement) and customer-PDF (kWh math) share the same
  per-face module counts. Single source of truth.
- **`CalculationResult.module_placements: dict[str, list[ModuleInstance]]`**
  — keyed by `RoofSection.name`. Empty for legacy single-orientation
  projects.
- **`PvModule.length_in / width_in / weight_lbs`** schema fields —
  default Talesun TP7G54M 415 dimensions (67.80 × 44.65 in, 47.40 lb).
  Backward compat: every pre-K.9.1 yaml gets defaults.
- **PV-4 v2 renderer** (`permit/structural.py::_draw_section_plan`):
  - When `result.module_placements[face]` is populated, draws each
    `ModuleInstance` as a true-aspect rectangle at (x, y, rotation).
  - K.2.8 grid heuristic remains as fallback for legacy projects.
  - Bottom-right **module dimension callout box** — small reference
    rectangle showing module brand + model + wattage + length×width,
    matching the Aurora reference image's corner layout.
- **`pvess-doctor pv4_module_count_matches_yaml`** check — 5 states:
  no roof_sections (skip), 0 PV (skip), 0% shortfall (PASS), ≤5%
  shortfall (PASS w/ designer-review note), 5-10% (WARN), >10% (FAIL).
  Catches "array over-designed for available roof" before AHJ submit.
- **27 new tests** across 3 files:
  - `tests/test_module_placement.py` (18) — boundary cases (target=0,
    too-small face, all-obstruction), rect placement math, orientation
    choice (narrow strip → landscape), obstruction halo avoidance,
    ridge-first sort order, tri face support
  - `tests/test_pv4_v2.py` (6) — backward compat (Austin), real
    placements render Phoenix + Frisco, dimension callout text,
    default-Talesun-dims contract, count consistency
  - `tests/test_doctor.py` (+3) — K.9.5 doctor positive guard +
    skip case + regression-bait (50 modules on 1 tiny face → FAIL)

### Changed

- `customer/production.py` LRM block refactored to call
  `face_distribution.distribute_modules_to_faces` — math unchanged,
  but now both engine and customer paths consume the same helper.
  Test invariants preserved (all K.8.1 + K.8.2 tests pass).
- Frisco permit-package PV-4 page now renders 5 face plans with real
  module rectangles (~34 of 36 placed; 2-module shortfall on small
  West/South faces — doctor PASS with designer-review note).

### Deferred to future K-phase

- **K.9.4 equipment callout engine** (auto-routing arrows for MSP /
  Inverter / ESS on the site plan). The current PV-4 already labels
  equipment via the existing layout; auto-routing arrows can be a
  K.9.4 polish phase when needed.

### Visual benchmark

Frisco PV-4 v2 now shows:
- 5 face plans (3 South + 2 West, SW-concentrated)
- Each module rendered at its true 5.65 × 3.72 ft aspect (landscape)
  or 3.72 × 5.65 ft (portrait) — algorithm picks per face
- Setback dashed lines (NEC 690.12 + per-edge overrides)
- Bottom-right callout: "TALESUN TP7G54M 415 · 415 W · 47.4 lbs"
  with scaled rectangle showing the 67.80″ × 44.65″ dimensions

Closes K.9 from the ROADMAP (originally 5 days; landed in 1 session).

---

## 2026-05-17 — K.8.2: value-weighted orientation derate (auto SW-quadrant)

Automates the user's "concentrate on SW" installation strategy. The
Sandia annual-kWh derate (K.8) treats East and West faces equally
because their annual integral is the same; in the TX market reality
(sub-1:1 REP buyback + PV-only), West-facing kWh produced 2-6 PM are
self-consumed during the AC peak at full retail, while East-facing
AM kWh are mostly exported at 50% retail. The K.8.2 hourly value
model captures this asymmetry — West beats East by ~12% on a 0.50×
plan, automatically shifting LRM modules toward the SW quadrant.

### Added

- **`src/pvess_calc/calc/value_weighted.py`** — new module:
  - `hourly_face_profile(azimuth, pitch, lat)` — 24-hour relative
    production (equinox model, cos-incidence-only, normalized).
  - `hourly_value_factor(rep_buyback_ratio, sc_pattern)` — 24-hour
    $-multiplier. Math collapses to constant 1.0 on 1:1 plans.
  - `face_value_weighted_derate(az, pitch, lat, ratio)` — single
    scalar ∈ (0, 1]. Reference = south-30° tilt; East ≈ 0.80 vs
    West ≈ 0.93 on 0.50× REP plan (12% spread).
  - `DEFAULT_DFW_SELF_CONSUMPTION_PATTERN` — 24-h typical weekday
    (empty house mid-day, AC + cooking 3-7 PM, evening peak 6-9 PM).
- **`Loads.use_value_weighted_distribution: bool = False`** — opt-in
  flag in `schema.py`. When True + latitude available, LRM uses
  `area × value_weighted_derate` instead of area-only. Default off
  preserves K.8.1 behavior for every pre-K.8.2 yaml.
- **`production.compute_annual_production` accepts `latitude_deg`**
  (optional). When None, falls back to K.8.1 area-only even with
  the flag on (no silent default-lat fudge).
- **`compute_economics` parses `project.coordinates`** to extract
  latitude when lookup_fields don't carry it, wiring the value-
  weighted path end-to-end from yaml.
- **New per-face method `per_face_auto_distributed_value_weighted`**
  in `ProductionResult.method`. `is_per_face` property updated to
  recognize all three per-face methods uniformly.
- **`pvess-doctor face_value_score_distinguishes_east_west`** — math
  contract guard. Synthesises E + W faces, verifies sub-1:1 spread
  ≥ 8% AND 1:1 collapse ≤ 0.01. Catches anyone "simplifying" the
  SC pattern to flat 0.50 (regression-bait test included).
- **19 new tests** (`tests/test_value_weighted.py` + 2 in
  `tests/test_doctor.py`):
  - Hourly profile: South noon-peak, West afternoon-peak, E/W mirror
    symmetry, North weakest-overall
  - Value factor: 1:1 collapse to constant 1.0, sub-1:1 dip on
    low-SC hours, 24-h length validator
  - Face derate: south normalizes to 1.000, math-collapse on 1:1
    (E ≈ W), West > East on sub-1:1, **SW beats pure South on
    sub-1:1** (signature property), North bad on all plans
  - LRM integration: area-only when flag off (backward compat),
    West > East when flag on + sub-1:1, equal split on 1:1 (math
    collapse at integration layer), fallback when latitude is None
  - Doctor: positive guard (current math passes) + flat-SC-pattern
    regression-bait (catches AM/PM asymmetry loss)

### Changed

- **Frisco yaml** (`003-frisco-glasshouse/inputs.yaml`) enables
  `use_value_weighted_distribution: true`. Mathematically a no-op
  on Frisco's GME 1:1 plan (math collapse), but documents design
  intent + future-proofs: if homeowner switches REP, algorithm
  auto-rebalances toward SW without yaml face-pruning.
- `ROADMAP.md` — K.8.2 entry moved from Planned → Done with date.

### Math contract (locked in tests)

```
On 1:1 REP plans:
   value_weighted_derate(face)  ==  Sandia annual derate(face)
   → ZERO regression from K.8.1 for every 1:1 project (Phoenix /
     Frisco / generic 1to1_nem). Distribution unchanged.

On sub-1:1 REP plans:
   value_weighted_derate(W-30°) - value_weighted_derate(E-30°) ≥ 0.08
   value_weighted_derate(SW-30°) > value_weighted_derate(S-30°)
   → LRM auto-distribute shifts modules from East to SW-quadrant.
```

---

## 2026-05-17 — K.4.6.6 closes the K.4.6 milestone (SMT-aware TX checks)

K.4.6 done — last sub-task adds 2 doctor checks that lock in the
business-narrative invariants K.4.6.3 / .4 / .5 set up. Combined with
the user's "smart meter = all generation used" insight: customer PDF
footer now distinguishes 1:1 vs sub-1:1 plans and surfaces SMT
load-shifting as a homeowner action when on sub-1:1.

### Added

- **`_check_tx_rep_plan_explicitly_chosen`** doctor check — fires
  WARN on TX projects still using the generic `1to1_nem` tariff
  (no preset chosen, no `rep_buyback_ratio` override). Hint cites the
  ±$90/mo swing between Green Mountain (1:1) and default Oncor (~0.5×).
  PASS for: non-TX projects (skip), TX projects on tx_* presets, TX
  projects with explicit `rep_buyback_ratio`.
- **`_check_self_consumption_realistic_for_rep_plan`** doctor check —
  SMT-aware. Fires WARN when:
    * `rep_buyback_ratio < 0.80` (sub-1:1 plan, exports discounted), AND
    * `self_consumption_fraction < 0.40` (passive baseline), AND
    * `battery.installed = False` (no battery time-shifting)
  Hint message: "Smart Meter Texas + load-shifted dishwasher / EV /
  pool pump raises self_cons to 0.60+ → adds $X/yr". PASS for 1:1
  plans (math collapses), battery-equipped projects, or projects
  already declaring aggressive self-consumption.
- **8 new tests** in `tests/test_doctor.py`:
  - `test_tx_rep_plan_check_skips_non_tx_project`
  - `test_tx_rep_plan_check_warns_on_tx_default_1to1` (regression-bait)
  - `test_tx_rep_plan_check_passes_on_tx_preset`
  - `test_tx_rep_plan_check_passes_with_explicit_ratio_override`
  - `test_self_consumption_check_warns_on_sub_1to1_with_passive_self_cons`
  - `test_self_consumption_check_passes_on_1to1_plan` (math-collapse case)
  - `test_self_consumption_check_passes_when_battery_installed`
  - `test_self_consumption_check_passes_when_already_aggressive`

### Changed

- **Customer PDF footer logic** (`customer/pdf.py::_footer_block`):
  switched from `export_tariff_model == "1to1_nem"` string check to
  `export_ratio_applied >= 0.99` numeric check. Now all 1:1 plans
  (1to1_nem / tx_green_mountain / tx_txu_buyback) get the same
  unified "Smart-meter NEM credits every kWh at retail" message;
  all sub-1:1 plans get the new "SMT load-shifting tip" prompt.
- **`schema.py::Loads.self_consumption_fraction` docstring** explicitly
  documents the math-collapse on 1:1 plans + the SMT load-shifting
  strategy on sub-1:1 plans.
- **Frisco yaml** (`003-frisco-glasshouse/inputs.yaml`) — updated comment
  on `self_consumption_fraction: 0.30` to note that on the 1:1 GME
  plan this value is mathematically irrelevant; documents the SMT NEM
  semantic ("all generation offsets the bill, timing irrelevant").

### Milestone summary — K.4.6 (2026-05-17)

| Sub-task | Status | Tests added |
|---|---|---|
| K.4.6.1 Battery-optional + PV-only PDF render | ✅ | 3 |
| K.4.6.2 Equipment library (Megarevo/Growatt/Hoymiles + in-house batt) | ✅ | 6 |
| K.4.6.3 Installer cost overrides | ✅ | 6 |
| K.4.6.4 TX REP picker + escape hatch | ✅ | 4 |
| K.4.6.5 3-tier quote table | ✅ | 8 |
| K.4.6.6 SMT-aware doctor checks | ✅ | 8 |

Tests: 425 → **461** (+36). Doctor: 29 → **31** (+2). 3 projects all
green (Austin / Phoenix / Frisco). Frisco project quote dropped from
the NREL-benchmark $52k / 11 yr payback to the installer-real $26k /
7.9 yr payback — the K.4.6 endgame.

---

## 2026-05-17 — K.4.6.5 + SW-quadrant installation strategy fix

Two threads landed together:

1. **Installer strategy correction** — flagged by the user: the Sandia
   annual-kWh derate ranks pure-south above west, but in the TX market
   reality (PV-only + REP buyback) west kWh are worth ~2× east kWh
   because they self-consume the 2-8 PM AC peak at full retail. The
   Frisco project drops East faces (Sandia derate 75-81%) even though
   they look "good enough" on paper.
2. **K.4.6.5 — 3-tier quote table** in customer PDF. The K.4.6 sales
   narrative payoff: every battery option earns the SAME monthly
   savings (same PV array → same kWh → same bill offset). The upgrade
   decision is backup-vs-cost, not savings-vs-cost.

### Added

- **`BackupOption` schema model** (`schema.py`) — yaml `loads.backup_options[]`
  list. Each entry: `name` + `battery_ref` (devices library key) +
  `quantity`.
- **`Loads.backup_options: list[BackupOption]`** — default empty
  (every pre-K.4.6.5 yaml unchanged).
- **`customer/quote_tiers.py`** — new module:
  - `QuoteTier` view-model: cost / monthly-savings / payback / backup
    summary per column.
  - `compute_quote_tiers(inputs, lookup_fields)` runs the base config
    + each option (via `Battery.model_copy(update=…)` swap) and
    returns `[base_tier, *option_tiers]`. Pure data, no rendering.
- **`_quote_tiers_block` PDF renderer** (`customer/pdf.py`) — wires
  the tiers into a side-by-side table with the base column tinted
  + "★ best ROI" tag when the base is PV-only.
- **8 new tests** in `tests/test_quote_tiers.py`:
  - empty options → 1-element list (backward compat)
  - 2 options → 3 tiers (base + 2)
  - **monthly savings invariant across all tiers** (K.4.6 narrative
    lock — fails if anything double-counts battery into savings)
  - cost monotonicity (bigger battery → higher cost)
  - unknown battery_ref → graceful zero-battery fallback (no crash)
  - backup_summary shows BOTH essentials and AC-running hours
  - PDF renders "Your options" + tier names when backup_options set
  - PDF omits the block when backup_options empty (backward compat)
- **`K.8.2` planned phase added to `ROADMAP.md`** — value-weighted
  orientation derate that automates the SW-quadrant preference (2-day
  scope). Documents the gap between Sandia annual kWh and TX-market
  $-per-kWh; today the workaround is manual yaml face-dropping.

### Changed

- **Frisco project (`003-frisco-glasshouse/inputs.yaml`)** — three updates:
  1. Skip 3 East faces in addition to 5 North faces — concentrate
     on the SW quadrant (3 South + 2 West = 5 faces total). Blended
     derate climbs 86% → 88.5%; monthly savings $273 → $279; payback
     8.1 yr → 7.9 yr.
  2. Add `loads.backup_options` with the 2 standard battery upgrade
     tiers (16 kWh in-house + 20 kWh Growatt HV).
  3. PDF now renders the 3-tier quote table with all three options
     showing $279/mo savings — visualises the "battery is backup
     cost, not savings" message.
- `customer/quote_tiers._backup_summary` shows TWO numbers per tier
  ("~X hr essentials · ~Y hr w/ AC") so the homeowner sees both the
  long-tail outage case and the realistic DFW summer scenario.

---

## 2026-05-17 — K.4.6.3 + K.4.6.4: installer cost overrides + TX REP picker

Closes the cost-honesty gap that the Frisco PV-only run surfaced:
the customer PDF was quoting NREL Q1-2026 benchmark $52k pre-ITC for
a system that the installer's real BOM puts at $38k. After K.4.6.3
the PDF reflects the actual quote (payback drops from 11 yr to 8 yr).

K.4.6.4 adds the missing dimension for the Texas market: REP buyback
ratio. Same PV system, different REP plan → up to 90% variance in
savings. Now the yaml carries the plan name and the ratio drives
economics.

### Added

- **`InstallerCostOverrides` schema model** (`schema.py`) — opt-in
  yaml block. Required `pv_turnkey_usd_per_w` + optional refs into
  the devices library or explicit per-component totals. Validator
  catches dollars-vs-cents typos (> $10/W → ValueError).
- **`ProjectMeta.installer_cost_overrides: Optional[…]`** — schema
  wiring. Absent → falls back to the NREL benchmark unchanged
  (zero regression for every pre-K.4.6.3 yaml).
- **`_override_installed_cost()`** helper in `customer/economics.py`
  with documented precedence:
    1. explicit `*_cost_usd_total` (one-off custom equipment)
    2. `*_ref` key → device-library wholesale × project quantity
    3. nothing set → component cost = 0 (assumed bundled in PV turnkey)
  Battery cost auto-skipped when `battery.installed = False` (K.4.6.1
  interaction).
- **5 TX REP presets** in `EXPORT_RATIOS` + `EXPORT_TARIFF_LABELS`:
  - `tx_default_oncor` (0.50× retail) — most TX customers' default
  - `tx_txu_buyback` (1.00×) — TXU Home Solar Buyback
  - `tx_green_mountain` (1.00×) — Green Mountain Renewable Rewards
  - `tx_reliant_sun` (0.95×) — Reliant Sun Sustainability
  - `tx_rhythm_pure` (0.70×) — Rhythm Pure Energy
- **`Loads.rep_buyback_ratio` + `rep_plan_name`** (`schema.py`)
  escape hatch for custom REP plans not in the preset list, or for
  mid-year rate changes. Validator enforces 0..1 range (catches
  percent-as-fraction typos).
- **10 new tests** in `tests/test_customer.py`:
  - `test_economics_without_overrides_keeps_benchmark_cost` — regression guard
  - `test_economics_installer_override_pv_turnkey_only`
  - `test_economics_installer_override_with_library_refs`
  - `test_economics_explicit_total_wins_over_ref`
  - `test_installer_overrides_pv_turnkey_validator` — unit-error guard
  - `test_economics_override_battery_ref_skipped_for_pv_only`
  - `test_economics_tx_green_mountain_preset_gives_1to1_rate`
  - `test_economics_tx_default_oncor_at_half_retail`
  - `test_economics_rep_buyback_ratio_overrides_named_tariff` — escape hatch
  - `test_loads_rep_buyback_ratio_range_validator`

### Changed

- Frisco project `inputs.yaml` (`003-frisco-glasshouse/`) carries the
  K.4.6.3 + K.4.6.4 yaml blocks. Real installer cost ($37,856
  pre-ITC / $26,499 post-ITC) replaces the NREL benchmark
  ($52,290 / $36,603). Payback drops 11.2 yr → 8.1 yr. **The PDF
  now matches the manual sales pitch.**
- `customer/economics.py::compute_economics` documents 3-way cost
  precedence: `system_cost_usd_override` kwarg → yaml overrides →
  benchmark. `tariff_label` resolution centralised so the K.4.6.4
  custom-REP path renders the homeowner's plan name on the PDF.

### NOT yet in this milestone (next K.4.6 sub-tasks)

- K.4.6.5 customer-PDF 3-tier quote table (PV-only / +inhouse-battery
  / +growatt-battery side-by-side, all three at the same monthly
  savings — visualises the "battery is backup cost, not savings"
  insight).
- K.4.6.6 doctor `tx_rep_buyback_is_set_explicitly` WARN check (when
  state=TX and tariff defaults to `1to1_nem`, flag that REP-switch
  could add ~$90/mo).

---

## 2026-05-17 — K.4.6.1 + K.4.6.2: battery-optional + DFW installer stack

First two sub-tasks of K.4.6 (Equipment library + cost overrides +
battery-optional + TX REP picker). See `ROADMAP.md` for the full
K.4.6 plan. Closes the cosmetic + sales-narrative gap that the
2026-05-17 Frisco E2E test surfaced: the customer-summary PDF was
quoting "0.0 kWh battery storage / 0 h backup" instead of telling
the homeowner "this is a PV-only system, no backup by design".

### Added

- **`Battery.installed: bool` property** in `schema.py`. Returns
  `quantity > 0`. Downstream consumers (PDF, doctor checks) read this
  single flag instead of re-checking `quantity` everywhere.
- **`customer/pdf.py` PV-only render path** — when `battery.installed`
  is False:
  - Spec strip collapses from 3 cells (PV / battery / inverter) to
    2 cells (PV / inverter) — no misleading "0.0 kWh battery storage"
  - Backup runtime block is REPLACED with a single notice paragraph
    explaining NEC 690.10 non-islanding behavior + the path to adding
    a battery later
- **4 new inverter library entries** (`devices/inverters.py`):
  - `megarevo_r11klna` — 11 kW Megarevo hybrid, wholesale $2,000
    (sweet spot for 14 kW DC arrays in DFW projects)
  - `growatt_min11000tl_x` — 11 kW Growatt, wholesale $2,500
  - `hoymiles_hys_lv_11k` — 11 kW Hoymiles, wholesale $2,200
- **2 new battery library entries** (`devices/batteries.py`):
  - `inhouse_16kwh_hv` — 16 kWh in-house HV stack at $6,000 ($375/kWh
    — 60% below Tesla PW3 per kWh; the user's main competitive lever
    in the TX market)
  - `growatt_apx_20kwh` — 20 kWh Growatt APX HV, $10,000
- **`INVERTER_PRICES_USD` + `BATTERY_PRICES_USD`** dicts now exported
  from `pvess_calc.devices` package init so K.4.6.3 cost-override can
  pull them in one import.
- **9 new tests**:
  - `test_battery_installed_property_reflects_quantity`
  - `test_render_pv_only_collapses_spec_strip_and_backup` — verifies
    the K.4.6.1 PV-only notice + "0.0 kWh" leak suppression
  - `test_render_with_battery_preserves_full_backup_table` — closes
    the contract from the other side
  - `test_inverter_library_has_dfw_installer_11kw_stack` — all 3
    11 kW brands registered + priced + resolvable
  - `test_inverter_wholesale_prices_distinct_from_retail_tier` —
    Chinese OEM wholesale ≤ $3 k; retail tier ≥ $5 k. Guards against
    accidentally pricing Megarevo at Tesla MSRP.
  - `test_battery_library_has_dfw_installer_hv_stack` — both HV
    batteries registered with `nominal_voltage ≥ 100 V`
  - `test_battery_in_house_priced_below_retail_tier_per_kwh` — locks
    the "in-house ≤ 60% Tesla/kWh" sales-advantage invariant
  - `test_get_inverter_unknown_ref_raises_keyerror` +
    `test_get_battery_unknown_ref_raises_keyerror` — typos in yaml
    fail loud, not silent

### Changed

- `tests/test_phase_d.py` device-library tests grew from 3 to 9
  entries (+6 K.4.6.2 cases).
- Frisco project regenerates with the K.4.6.1 PV-only render path —
  `customer-summary.pdf` now reads honestly as "PV-only · grid-tied
  · no backup" instead of "0 kWh battery / 0 h backup".

### NOT yet in this milestone (next K.4.6 sub-tasks)

- K.4.6.3 `project.installer_cost_overrides` schema block — the PDF
  cost number still uses the NREL benchmark $3.50/W. Connecting the
  library prices to the customer PDF requires this schema addition.
- K.4.6.4 TX REP buyback model (`loads.rep_buyback_ratio` + presets).
- K.4.6.5 3-tier quote table in customer PDF.
- K.4.6.6 doctor `tx_rep_buyback_is_set_explicitly` WARN check.

---

## 2026-05-17 — K.8.1 v2: Largest Remainder Method + Frisco E2E project

### Added

- **`projects/003-frisco-glasshouse/`** — first end-to-end real-address
  project: yaml + calc + customer-summary + roof-vis all generated
  from the K.3c lookup of 7652 Glasshouse Walk, Frisco TX. NEC 2020,
  Oncor utility, Talesun + Tesla PW3 + Megarevo stack. doctor PASS
  29/29.
- **Largest Remainder Method (Hamilton 1792) apportionment** in
  `customer/production.py` replaces the K.8.1-v1 "last-face-remainder"
  algorithm for auto-distributing modules across roof faces.
- `tests/test_production.py::test_production_auto_distribute_no_face_unjustly_zeroed`
  — regression-bait using Frisco's exact 13-face geometry; locks
  the "every face with fair share ≥ 0.5 gets ≥ 1 module" invariant.

### Fixed

- **K.8.1-v1 zeroed the LAST roof_section** when cumulative rounding
  consumed the module budget early. Surfaced by the Frisco E2E test:
  doctor reported `13 usable sections declared but 12 faces in
  production_breakdown`. Pre-fix the geometrically-warranted "North
  Roof #4" face got 0 modules; post-fix LRM gives it the deserved 1.
  Conservation property unchanged (Σ allocated == pv_array.modules).

---

## 2026-05-16 — Roof-vis polish: target crosshair + bar-chart legibility

Field-testing the K.3c diagrams against the Frisco project surfaced
two visual papercuts. Both fixed; regression tests added.

### Fixed

- **Target identification in dense subdivisions** — pre-polish the
  satellite RGB / flux panels showed 8-10 houses with no indication
  of which was the project. Reduced default `radius_m` from 50 → 25
  (50 × 50 m frame instead of 100 × 100 m), tightened `pixel_size_m`
  from 0.5 → 0.25 to keep the same pixel density, and overlaid a red
  ring + crosshair at the centre of both panels so the viewer can
  identify the target even when neighbours are in frame.
- **Bar-chart label overlap with 13+ faces** — the pre-polish layout
  split metadata across THREE places (y-tick face name + inline
  white-on-bar pitch/az hint + outside-right area·derate annotation).
  In the narrower satellite bar panel the inline hint collided with
  adjacent y-tick labels. Consolidated all metadata into ONE
  outside-right annotation per bar: `"412 ft²  ·  34° / 180°  ·  96%"`.
  Bumped figure widths (satellite 15 → 18 in) and made the right
  column dominate (`width_ratios=[1, 1.4]`) so the longer single-line
  annotation fits without truncation.
- **Polar title kissing N label** — `pad=18` → `pad=28` on the polar
  axis title so "By orientation" never touches the compass north
  label even with full-amplitude bars.

### Changed

- Figure height in BOTH renderers now scales with face count:
  `min(14, max(8, 6 + 0.4 × N))` for the analysis-only diagram,
  `min(16, max(11, 9 + 0.4 × N))` for the satellite version. A
  13-face Frisco roof rendered ~38 % taller than a 4-face baseline.

### Added

- 3 regression-bait tests (`tests/test_roof_diagram.py` +
  `tests/test_roof_satellite.py`):
  - `test_render_height_scales_with_face_count` — 13-face PNG must
    be ≥ 30 % taller than a 4-face PNG (catches the pre-fix
    "fixed-8 in regardless of N" bug).
  - `test_face_bars_use_single_outside_right_annotation` — one
    annotation per face, white-text-on-bar regression killed.
  - `test_render_satellite_includes_target_crosshair` — both RGB
    and flux panels must carry `Circle` patches at image centre.
  - `test_fetch_data_layers_default_radius_is_tight_for_subdivisions`
    — locks `radius_m=25, pixel_size_m=0.25` defaults.

---

## 2026-05-16 — `pvess roof-vis --satellite` real-imagery + flux render

Tier-gated upgrade to `pvess roof-vis`. Adds a 2×2 layout that brings
back Google Solar `dataLayers:get` — true-colour aerial photo of the
roof + annual-flux heatmap masked to the building outline + the same
analytical compass/bar charts as the free view. Reserved for signed
customers because each render costs ~$0.50 (Google Solar SKU), so the
CLI gates the call behind `--confirm-cost` or `PVESS_ALLOW_PAID_RENDERS=1`.

### Added

- **`src/pvess_calc/lookup/providers/google_solar_data_layers.py`** —
  HTTP wrapper around `dataLayers:get` + the follow-up signed-URL TIFF
  fetch. Deliberately NOT in `DEFAULT_PROVIDERS` (10× more expensive
  than buildingInsights; large signed-URL response doesn't fit the
  lookup cache pattern). Emits `DataLayersError` distinct from the
  generic `ProviderError` so the CLI can surface paid-call failures
  separately.
- **`src/pvess_calc/customer/roof_satellite.py`** — 2×2 figure: left
  column = real RGB photo + annual-flux heatmap (matplotlib `inferno`
  cmap, masked via Google's building mask so non-roof pixels fade);
  right column = compass rose + ranked bars (re-used from
  `roof_diagram` so visual language stays consistent across tiers).
- **`pvess roof-vis --satellite`** + **`--confirm-cost`** flags. Gate
  trips when satellite is requested without explicit cost acknowledge;
  exits 4 with pricing warning. Honors `PVESS_ALLOW_PAID_RENDERS=1`
  env-var for sales reps who've pre-acknowledged the SKU.
- **11 new tests** in `tests/test_roof_satellite.py`:
  - dataLayers HTTP wrapper: no-key error, happy path URLs, 404
    coverage-gap note, 5xx error, signed-URL byte passthrough
  - Renderer with synthetic numpy assets (no network): valid-PNG,
    empty-sections fail-loud
  - `_decode_tiff` round-trips uint8 RGB + float32 flux via Pillow
  - CLI tier gate: missing `--confirm-cost` → exit 4, env-allow →
    bypasses gate

### Changed

- `.env.example` documents the two-SKU pricing model
  (buildingInsights ~$0.05 vs dataLayers ~$0.50) + the
  `PVESS_ALLOW_PAID_RENDERS` session-level override.
- `pvess roof-vis` output filename suffix changes with tier:
  `-roof-diagram.png` for analytical, `-roof-satellite.png` for paid.

### Usage

```bash
# Prospect tier (free, $0.05 buildingInsights only)
pvess roof-vis "7652 Glasshouse Walk, Frisco TX 75035"

# Signed customer tier ($0.50/render, real imagery + flux)
pvess roof-vis "7652 Glasshouse Walk, Frisco TX 75035" \
               --satellite --confirm-cost

# Sales rep session — set once, no per-call prompt
export PVESS_ALLOW_PAID_RENDERS=1
pvess roof-vis "<addr>" --satellite
```

---

## 2026-05-16 — `pvess roof-vis` rooftop visualization from address

A K.3c sidekick: takes a raw address, runs the lookup chain (Mapbox +
NREL + Google Solar), renders a 2-panel diagram of every face Google
Solar returned. Sales-quality output for the "is this roof worth
pursuing?" call BEFORE running a full project.

### Added

- **`src/pvess_calc/customer/roof_diagram.py`** — matplotlib-based
  renderer. Two panels side-by-side: left = polar compass rose (each
  face = wedge at its azimuth, colored by orientation × shading
  derate); right = horizontal bar chart ranked by derate (best on top),
  bar length = face area, derate % annotated.
- **`pvess roof-vis <address>`** — new CLI command (console_script
  `pvess-roof-vis`). Options: `-o/--output` (default: slugified-address
  PNG), `--density` (rural / suburban / urban / unknown, drives
  shading default), `--dpi`. Exits 2 if `PVESS_GOOGLE_SOLAR_KEY` is
  missing; exits 3 if Google Solar returns no roof_sections for the
  address (rural / new construction / multi-family near lat-lng).
- **10 new tests** in `tests/test_roof_diagram.py` — PNG signature +
  IHDR dimension check, single-face / empty / zero-area edge cases,
  orientation × shading math contract, per-face shading override
  precedence, missing-name fallback, `render_from_address` end-to-end
  via patched lookup (returns None on empty, writes PNG on hit).

### Use

```bash
pvess roof-vis "7652 Glasshouse Walk, Frisco TX 75035"
# → 7652-glasshouse-walk-frisco-tx-75035-roof-diagram.png (275 KB)
```

Drops into a sales deck / homeowner email / WeChat without further
processing.

---

## 2026-05-16 — K.8.1 K.3c × K.8 hand-off + wizard plumbing

Pre-test code review surfaced three gaps in the K.3c (Google Solar)
→ K.8 (per-face derate) integration. None broke any single unit test,
but together they meant a fresh `pvess init --address` would silently
over-promise production in the customer-summary PDF by 5–10 %. Fixed
all three plus two minor cleanups.

### Added

- **`per_face_auto_distributed` production method** — when
  `site.roof_sections` is present but every `section.module_count = 0`
  (the K.3c-init state — Google Solar populated face geometry but the
  designer hasn't manually distributed modules yet), the engine now
  distributes `pv_array.modules` across faces proportionally to
  `gross_area_sqft`. Last-face-remainder rounding keeps the total
  exactly equal to `pv_array.modules` (no conservation leak).
- **Wizard K.3c side-channel** — `_prefill_from_address` stashes the
  Google Solar `roof_sections` list under a magic `__k3c_roof_sections`
  key in the prefills dict; `run_wizard` pours it into
  `nested.site.roof_sections` right before validate-and-write. The
  scalar-prompt path is untouched.
- **5 new tests** locking the contracts:
  - `test_production_sections_with_zero_modules_auto_distributes`
    (replaces the pre-K.8.1 "falls back to system_aggregate" test)
  - `test_production_auto_distribute_proportional_to_unequal_areas`
  - `test_production_auto_distribute_preserves_total_modules`
    (sweeps 7 awkward totals to catch rounding leaks)
  - `test_production_auto_distribute_falls_back_when_areas_zero`
  - `test_production_method_string_is_per_face_for_both_paths`
  - `test_production_breakdown_per_face_handles_k3c_init_state`
    (doctor regression-bait)
  - `test_production_breakdown_per_face_skipped_when_no_pv_declared`
  - `test_wizard_writes_roof_sections_from_google_solar`
  - `test_google_solar_max_panels_accepts_float_and_int`

### Changed

- `ProductionResult.is_per_face` now returns True for both `per_face`
  AND `per_face_auto_distributed` — downstream consumers (customer PDF,
  doctor check) treat them identically.
- `_check_production_breakdown_per_face` doctor check distinguishes 3
  states cleanly:
  - no `roof_sections` → PASS "single-orientation project"
  - sections present but `pv_array.modules = 0` → PASS "no PV declared"
  - sections + PV → MUST emit breakdown; if `module_count` distribution
    wasn't done by designer, surfaces "(auto-distributed by area —
    designer review recommended)" in the PASS detail
- `google_solar.py` accepts `maxArrayPanelsCount` as int OR float (some
  JSON serializers emit `76.0` instead of `76`); negative values
  rejected as malformed.
- Provider comment for `requiredQuality=LOW` corrected (was claiming
  MEDIUM floor; code uses LOW).

### Fixed

- **Critical** — Wizard's prefill loop only walked `LOOKUP_FIELD_TO_YAML_PATH`
  (scalar mapping), so Google Solar's `roof_sections` list output was
  silently dropped by `pvess init --address`. K.3c work paid for an API
  call and got nothing back into the yaml.
- **Critical** — Customer-summary PDF over-promised production by ~5 %
  for K.3c-init projects: `compute_annual_production` fell back to
  `system_aggregate` (south-20° baseline × system_kw, no orientation
  derate) when every `module_count = 0`, masking the per-face reality
  that Google Solar's geometry implied.
- **Medium** — Doctor check `production_breakdown_per_face` reported
  "single-orientation project (skipped)" for K.3c-init projects even
  though they had 2-4 declared roof sections — misleading PASS message.

---

## 2026-05-15 — K.3c Google Solar API provider

Replaces the $20-40/property EagleView roof report with a $0.05 API
call for the calc-engine path. The K.8 per-face derate now resolves
end-to-end from address alone — designer no longer has to hand-measure
roof segments on Google Earth Pro just to fill `site.roof_sections`.

### Added

- **`src/pvess_calc/lookup/providers/google_solar.py`** — new K.3c
  online provider. Calls `buildingInsights:findClosest` (Solar API v1,
  GA 2024). Emits:
  - `roof_sections[]` — per-face dicts mirroring `schema.RoofSection`
    (name auto-named by 8-direction compass, pitch_deg, azimuth_deg,
    width_ft / height_ft as sqrt(area) square equivalent, shape=rect,
    module_count=0 for designer to fill).
  - `google_solar_imagery_quality` (HIGH/MEDIUM/LOW) — drives our
    internal confidence band (LOW → low → wizard surfaces as REVIEW-ME).
  - `google_solar_imagery_date`, `google_solar_max_panels`,
    `google_solar_whole_roof_area_m2`.
- **`ENV_GOOGLE_SOLAR_KEY` + `get_google_solar_key()`** in
  `lookup/config.py` — same env-var-with-fingerprint pattern as the
  existing Mapbox / NREL keys.
- **`pvess lookup` CLI** now prints the Google Solar key fingerprint
  alongside Mapbox + NREL, hints if the key is missing, and counts
  `google-solar` toward the online-fields summary.
- **`.env.example`** documents `PVESS_GOOGLE_SOLAR_KEY` with enable +
  pricing links.
- **11 new tests** in `tests/test_lookup_online.py` — no-key miss,
  no-lat/lng miss, 4-face Frisco happy path, LOW quality confidence
  downgrade, duplicate-direction name suffixing, 404 / 5xx / empty
  segments → miss, params-on-wire contract, default-chain skip
  without key, full mapbox→google integration.

### Changed

- `DEFAULT_PROVIDERS` chain in `lookup/__init__.py` adds `google_solar`
  after `nrel_pvwatts`. Pure additive — zero-config chain (no env
  vars) returns the same fields as K.3b.
- The "online sources" set in CLI + tests expanded from
  `{mapbox, nrel}` to `{mapbox, nrel, google}`.

### Limitations (deliberately surfaced upstream)

- Google returns axis-aligned bounding boxes only — no K.2.7 polygon
  vertices. Hip / L-shape roofs approximated as same-area squares; the
  EagleView 18-page PDF stays as the recommended permit attachment
  when an AHJ demands it.
- Building lookup is by closest-to-lat/lng — on townhomes /
  attached-row construction the API occasionally returns an adjacent
  unit. Cross-check mapbox `canonical_address` vs Google's response
  `center` coords.
- 404 NOT_FOUND (rural / new construction) returns a `miss` with a
  pointer to the EagleView fallback rather than a generic HTTP error.

---

## 2026-05-15 — K.8 per-face orientation derate + shading

The pre-K.8 customer-summary used `system_kw_dc × NREL_baseline` for every
project — fine for a single-orientation array, wildly optimistic for a
multi-face roof. K.8 closes the gap with a Sandia-table-driven orientation
derate + site-density shading model.

### Added

- **`src/pvess_calc/calc/orientation.py`** — Sandia 30°–45°-latitude
  derate table (7 tilt rows × 7 azimuth-offset columns) with bilinear
  interpolation. `orientation_derate(180, 30) == 1.00` (south-facing
  latitude-tilt reference); `orientation_derate(270, 22)` ≈ 0.86
  (west-facing, typical residential pitch).
- **`src/pvess_calc/customer/production.py`** — per-face production
  aggregator. Returns `ProductionResult` carrying total kWh + a list
  of `FaceProduction` (face name, kW, azimuth, tilt, orientation
  derate, shading factor, annual kWh). `blended_derate` property is
  weighted by face capacity.
- **`EconomicsResult.production_breakdown`** + `production_blended_derate`
  — new fields surfacing the per-face math up to the PDF layer.
- **Customer-summary PDF "Production by roof face" table** — appears
  automatically when ≥ 2 faces with declared modules. Columns: face,
  kW DC, azimuth/tilt, orientation derate, shading, annual kWh.
- **`site.urban_density: Literal["rural", "suburban", "urban", "unknown"]`**
  — default shading fallback when per-face `shading_factor` is left at
  1.0. Rural/unknown = 1.00; suburban = 0.96; urban = 0.90.
- **`RoofSection.shading_factor: float = 1.0`** — per-face override
  for engineer-measured shading.
- **`pvess-doctor production_breakdown_per_face` check** — verifies
  multi-face projects emit a breakdown with valid (0, 1] derates;
  skips for single-orientation projects.
- **22 new tests**: `tests/test_orientation.py` (9 — symmetry, flat-roof
  invariance, bilinear interp, density-table parity), `tests/test_production.py`
  (10 — legacy fallback, zero-modules short-circuit, multi-face math,
  capacity-weighted blending, density override), `tests/test_doctor.py`
  (3 — positive guard + skip case + invalid-derate regression-bait).

### Changed

- `compute_economics` now delegates production to
  `compute_annual_production`. For single-orientation projects the
  number is bit-identical to pre-K.8; for multi-face projects it drops
  by the face-weighted derate (Phoenix S+W example: 44.3k → 36.9k kWh,
  ~17 % more honest).
- `tests/test_customer.py` Phoenix expectations updated to reflect
  per-face math (39 000 < kWh < 45 000 instead of "exactly 44 300";
  blended derate asserted between 0.85 and 0.99).

### Fixed

- `compute_annual_production` short-circuits when `pv_array.modules = 0`.
  Pre-K.8 a yaml with `modules = 0` but stale `roof_sections.module_count > 0`
  would still produce non-zero face kWh (the `test_economics_payback_after_itc_is_none_when_no_savings`
  trap). Now: no array → 0 production → None payback.

---

## 2026-05-15 — Docs + CI / CD infrastructure

### Added

- **MkDocs Material documentation site** at `docs/` (13 pages covering
  quickstart, workflow phases (intake / design / submit / verify),
  recipes (add AHJ profile / NEC edition / lookup provider), and
  reference (CLI / schema / doctor checks)).
- **GitHub Actions `docs.yml`** auto-deploys docs to GitHub Pages on push
  to `main`. Uses official `actions/deploy-pages@v4` flow (no gh-pages
  branch).
- **GitHub Actions `ci.yml`** runs pytest + doctor on every push to main
  and every PR. Tests Python 3.10 + 3.12 matrix.
- `docs/deploying.md` — first-time GH Pages setup steps + 4 troubleshooting
  cases.
- `pyproject.toml` `[docs]` extra: `mkdocs>=1.6` + `mkdocs-material>=9.5`.

### Changed

- `README.md` rewritten — Phase 0 quickstart replaced by 5-minute install +
  K.7 `pvess pipeline submit` overview + link to docs site.
- `mkdocs.yml` `site_url` / `repo_url` / `edit_uri` parameterised with
  `your-org` / `pvess-calc` placeholders + sed-replace instructions.

---

## 2026-05-14 — K.7 unified CLI + 4-step precision

### Added

- **`pvess <subcommand>`** — single root CLI with 12 subcommands +
  3 pipeline shortcuts (`customer` / `submit` / `review`). Legacy
  `pvess-*` commands remain registered for backward compatibility.
- **NEC 2017 real implementation** — `nec/v2017.py` no longer falls
  back to v2020. `sum_rule` still legal under 2017, `RSD_BOUNDARY_VOLTAGE_LIMIT = 80V`
  (vs 30V for 2020+).
- **CA NEM 3.0 + HI Rule 14H** support — `loads.export_tariff_model:
  Literal["1to1_nem", "ca_nem3", "hi_self_consumption"]` drives K.4
  customer-summary ROI calc. ACC 0.27 ratio for CA → 40 % savings
  reduction vs naive 1:1 NEM (the actual market reality).
- **Per-state export tariff recommendation** — `static_utility_rate`
  provider emits `recommended_export_tariff` field (CA → `ca_nem3`,
  HI → `hi_self_consumption`, else `1to1_nem`). Auto-wired via
  `pvess init --address`.
- **`pvess-compare` PDF output** — landscape 1-page side-by-side
  comparison alongside existing `comparison.md` + `.json`. Hero strip
  shows $/mo + payback + annual production per scenario; metric table
  shows 11 NEC + financial rows.
- **4 new doctor checks** locking K.7 invariants:
  - `nec_edition_artifacts_consistent` — report.md / permit PDF carry
    the NEC edition declared in inputs.yaml
  - `export_tariff_matches_state` — CA → ca_nem3 / HI →
    hi_self_consumption mandatory
  - `rsd_label_substitution_wired` — `{{RSD_BOUNDARY_V}}` placeholder
    + build_substitutions populate it correctly
  - `compare_pdf_renderable` — `pvess compare` emits valid PDF

### Changed

- RSD label body now references `{{RSD_BOUNDARY_V}}` and resolves to
  "80 V" (NEC 2017) or "30 V" (NEC 2020/2023) at substitution time.
- `nec/v2020.py` + `nec/v2023.py` declare `RSD_BOUNDARY_VOLTAGE_LIMIT = 30.0`
  for consistency with the v2017 module.

### Doctor count

24 → **28** checks PASS.

---

## 2026-05-13 — K.6 visual polish (Layer 1 + 2)

### Changed

- **EE-4 site plan** redesigned: front / rear / side-yard setback
  dimensioning, MSP→AC-DISC→ESS orange dashed route, filled-triangle
  north arrow, scale bar bottom-left, sidebar enriched with setback
  distances.
- **EE-3 panel schedules** — orphan single-panel rows now centered
  (no more left-aligned with right-side whitespace).
- **PV-N general notes** restructured into §A / §B / §C / §D
  topical sub-banners. Tightened layout fits all 22 ELECTRICAL_NOTES
  without clipping.
- **Cover sheet PE STAMP box** — adds "to be affixed by engineer of
  record" placeholder so AHJ reviewers don't mistake the empty area
  for a layout error.
- **EE-2 NOTES strip** — line spacing 0.16″ → 0.20″ for legibility.
- **Customer-summary** — "estimated monthly savings" caption now left-
  aligned (was floating mid-cell), monthly chart x-axis 7pt → 8.5pt.

### Added

- 11 K.6 polish-guard tests in `tests/test_k6_polish.py`.

---

## 2026-05-13 — K.2.8 polygon refinements

### Added

- `calc/polygon.py::offset_polygon` — per-vertex bisector offset that
  works for both convex AND concave polygons (replaces K.2.7
  centroid-shrink approximation which crossed edges on L / T / cross
  shapes).
- `calc/polygon.py::fit_module_grid` — binary-search cell size to fit
  ≥ N modules inside the inset polygon, choosing the largest
  (visually clearest) cell that works.

### Fixed

- L-shape roof's PV-4 dashed setback inset now traces correctly
  through the concave corner.
- Polygon roof modules now placed at the exact requested count (was
  underfitting by 30–40% under the K.2.7 heuristic).

---

## 2026-05-12 — K.2.7 polygon roof geometry

### Added

- `RoofSection.shape: Literal["rect", "tri", "polygon"]` — arbitrary
  N-gon faces via `vertices: list[(x, y)]`.
- `calc/polygon.py` module: `polygon_area` (shoelace), `polygon_inset_area`
  (Minkowski), `point_in_polygon` (ray-cast), `clipped_grid`, `is_convex`.
- pydantic validator: ≥3 vertices, simple (non-self-intersecting),
  counter-clockwise.
- PV-4 polygon renderer with module grid clipped to polygon interior
  (`clipped_grid`).
- 26 polygon math + schema tests + 4 roof_layout integration tests
  (L-shape, plus / cross, convex pentagon).

---

## 2026-05-12 — K.5 grounding electrode system

### Added

- `Service.grounding_electrode_system: GroundingElectrodeSystem` —
  actual GES inventory (rods, water pipe, Ufer) + existing GEC size
  + bonding status.
- `GroundRod` / `MetalWaterPipeBond` / `UferElectrode` models.
- `compare_gec_to_required()` — NEC 250.66 comparison emits PASS /
  UNDERSIZED / UNKNOWN status.
- Doctor check `grounding_electrode_system_compliant`.
- EE-2 conditionally renders only the actual GES components (no
  phantom Ufer when not declared).
- EE-2 GEC label flags `⚠ UNDERSIZED — NEC 250.66 requires #X AWG CU`
  when existing GEC < requirement.

---

## 2026-05-12 — K.4.5 customer-summary polish

### Changed

- Degraded-mode customer-summary (no donut) — hero numbers now expand
  to full-width (no more "ghost column" whitespace).
- HVAC type "unknown" → backup runtime collapses summer + winter to a
  single "with typical HVAC load" row.
- Payback line shows BOTH before-ITC and after-30%-ITC values.
- HVAC backup hours use `.1f` formatting so 5.2 h (AC) vs 4.6 h
  (heat pump heating) is visible (was `.0f` rounding both to "5 h").

---

## 2026-05-11 — K.4 customer summary PDF

### Added

- `pvess customer projects/<id>/` → `output/customer-summary.pdf` —
  homeowner one-pager with system overview, monthly savings,
  backup runtime, monthly production chart.
- `customer/economics.py` — annual production + bill savings + payback
  with USA-avg / latitude-fallback / NREL three-tier fallback.
- `customer/backup.py` — backup runtime per HVAC type (heat_pump /
  gas_furnace_ac / electric_resistance / unknown).
- `customer/design_tokens.py` — 4 font tiers + 2 accent colors +
  2 chart types contract. Doctor enforces.
- `customer/charts.py` — matplotlib donut + bar (220 DPI).
- Two doctor checks: `customer_summary_renderable`,
  `customer_design_tokens_respected`.

---

## 2026-05-11 — K.3b online lookup providers

### Added

- `lookup/providers/mapbox_geocode.py` — Mapbox v5 forward geocoding
  → lat/lng/county/canonical_address.
- `lookup/providers/nrel_pvwatts.py` — NREL PVWatts v8 → annual kWh
  per kW + irradiance.
- `lookup/config.py` env-var module with `.env` auto-loader (no
  external `python-dotenv` dependency).
- `pvess lookup-check` CLI for fingerprint + happy-path verification
  without exposing full API tokens.
- HTTP layer `lookup/providers/_http.py` — 5s timeout, ProviderError
  exception mapping, graceful 4xx / 5xx / DNS failure.
- 16 mock-HTTP tests via `responses` library.

### Fixed

- Address parser: full street addresses like
  `"2500 Hollow Hill Lane, Lewisville TX 75067"` now extract
  city=Lewisville correctly (was treating the street as city).

---

## 2026-05-10 — K.3 offline address lookup

### Added

- `lookup.resolve("Phoenix, AZ")` returns ≥6 fields from 5 offline
  data sources: ASHRAE 2% min/max, utility name, AHJ name, IECC
  climate zone, NEC adoption.
- `lookup/data/{ashrae,utility,ahj,climate_zone,nec_adoption}.json` —
  hand-curated 30+ city datasets.
- `Provider` Protocol + per-provider try/except so one bad source
  never breaks the chain.
- 24-hour JSON cache at `~/.pvess/cache/lookup/<sha>.json`.
- `pvess init --address "Phoenix, AZ"` wizard pre-fill — every field
  shown as a prompt default, user confirms each one (never silent).
- 19 lookup tests.

---

## 2026-05-09 — K.2.6c roof shape + obstructions

### Added

- `RoofSection.shape: Literal["rect", "tri"]` — gable vs hip face.
- `RoofSection.obstructions: list[RoofObstruction]` — chimneys,
  skylights, vent pipes, HVAC, fan vents, access hatches.
- `RoofSection.edge_setbacks: list[EdgeSetback]` — per-edge override
  for eave / ridge / rake / valley / hip / apex.
- `calc/roof_layout.py` — usable-area engine: rect inset, tri inradius
  shrink, obstruction halo subtraction.
- PV-4 attachment plan upgrade — SHAPE / GROSS / USABLE columns +
  per-section roof plans with shape outline + dashed setback inset
  + hatched obstructions + module grid.
- Doctor check `roof_usable_area_sufficient`.

### Fixed

- Phoenix yaml's pre-K.2.6c roof_sections were over-packed (30
  modules × 22 sqft = 660 sqft on 360 sqft faces). Updated to
  realistic 38×24 ft faces with 30 modules each.

---

## 2026-05-09 — K.2.6b ESS install location

### Added

- `Battery.install_location: Literal["indoor", "garage", "outdoor",
  "outdoor_protected", "unknown"]`.
- `Battery.distance_to_doorway_ft` / `distance_to_window_ft` /
  `distance_to_egress_ft`.
- `calc/ess_install.py` — NEC 706.10 + IRC R328 evaluator (3-ft
  setbacks + 40 kWh indoor capacity ceiling).
- Doctor check `ess_install_compliant`.

---

## 2026-05-09 — K.2.6a per-subpanel voltage drop

### Added

- `SubPanel.distance_to_msp_ft: float` — per-panel wire-run length.
- `voltage_drop._ac_trunk_segments` — when ANY sub-panel has
  `distance_to_msp_ft > 0`, the AC trunk expands into a chain of
  D1 / D2 / D3 segments (vs the legacy single "D · AC-DISC→MSP"
  segment). Each hop contributes its own drop.

### Fixed

- Multi-sub-panel projects no longer under-report voltage drop. Phoenix
  with 2 sub-panels was showing only the 12 ft final-hop drop; actual
  trunk run is 65 ft.

---

## 2026-05-08 — K.2.5 schema feasibility

### Added

- `SubPanel.{service_rated, available_slots, used_slots,
  existing_solar_breaker_a, enclosure_rating}` — physical / electrical
  feasibility fields.
- `Service.{existing_solar_breaker_a_msp, msp_available_slots,
  msp_used_slots}` — MSP-level equivalents.
- `Loads.{monthly_kwh, hvac_type, has_ev, planned_ev,
  planned_electrification}` — household demand context.
- **705.12 multi-existing-PV bus-load principle** — interconnect
  evaluator now includes existing PV/ESS backfeed in the sum.
  `combined_backfeed_a = new + existing` for sum / 120% checks.
- Doctor check `subpanel_slots_sufficient`.

---

## 2026-05-08 — K.3 / K.4 site checklist + wizard

### Added

- `pvess survey` — printable 5-page site-survey checklist PDF
  (`site_checklist/`).
- `pvess init <id>` — interactive wizard walks every required field
  with yaml_path + hint + where-to-find. Checkpoints to
  `.wizard-state.json` for resume after ctrl-C.
- `wizard/field_specs.py` declares `DESIGN_FIELDS` (project
  metadata, equipment) which extend the K.1 `SITE_FIELDS`.

---

## Earlier work (pre-K.* milestones)

| Phase | Date range | Scope |
|---|---|---|
| Phase 0 | 2026-Q1 | NEC 2023 baseline (PV string / OCPD / 705.12) + Markdown report + QET single-line injection |
| Phase 1 | 2026-Q1 | 7-device SLD + 6 connection conductors + real `.elmt` symbols |
| Phase 1.5 | 2026-Q1 | NEC labels PDF (US Letter, 2×3 grid, ANSI Z535.4 colors) |
| Phase B/C | 2026-Q2 | DXF EE-1 three-line + EE-2 grounding (ACADE-compatible) |
| Phase D | 2026-Q2 | Real voltage drop (NEC 215.2/210.19) + AIC (110.24) + device library + temp/conduit derating + NEC 2020 dispatch |
| Phase E | 2026-Q2 | Scenario comparison + BOM estimate (`pvess compare`) |
| Phase F+G | 2026-Q2 | Complete 7-page permit PDF + AHJ profile system |
| Phase H | 2026-Q2 | DC AFCI / SPD / ground rod topology / conduit fill |
| Phase J | 2026-Q2 | Site/roof layout + structural sheets (PV-4/5/6) |

For each phase's design rationale see `docs/DESIGN.md`; for testing
conventions see `docs/TESTING.md`.
