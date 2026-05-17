---
name: pvess-review
description: Rebuild the full pvess submittal package + run pvess-doctor + rasterize PDF + show every page for visual review. Use when the user asks to "regenerate the drawings", "see the latest output", "重新生成图纸", or after any change to permit/, dxf/, qet/, or schema code.
---

# pvess-review — rebuild & visually review a submittal package

This skill is thin glue: the real work is in `scripts/pvess-review`, a bash
script that runs `pvess-calc → pvess-render → pvess-labels → pvess-dxf →
pvess-permit → pvess-doctor`, then rasterizes the resulting PDF to
`/tmp/pvess_review-NN.png`. The skill's only added value is the visual
review step (reading each PNG back to the user) which the bash script can't
do on its own.

## Inputs

`$ARGUMENTS` may be:

- **empty** — defaults to the canonical `projects/002-phoenix-25kw/` fixture
- **a project dir** — `projects/003-newproj/`
- **a project dir + `--pages N,M,...`** — only show those page numbers
- **a project dir + `--no-permit`** — skip permit PDF, only show EE-1/EE-2 PNGs

## Procedure

### Step 1 · Run the build script

Parse `$ARGUMENTS`. Strip out any `--pages N,M,...` segment (that's for the
review step, not the build) and pass everything else through to the script:

```bash
./scripts/pvess-review <remaining-args>
```

The script handles `.pth` unhiding, AHJ auto-detection from `inputs.yaml`,
and runs `pvess-doctor`. If the doctor FAILS, the script exits non-zero —
report the failure to the user and stop.

### Step 2 · Read the rasterized PNGs

After the script succeeds, PNGs live at `/tmp/pvess_review-01.png`,
`-02.png`, ... up to `-NN.png` (zero-padded).

If user passed `--pages N,M,...`, show only those pages. Otherwise show all.

Issue Read tool calls **in parallel in a single message** (multiple Read
blocks together). Don't sleep, don't poll — PNGs are already on disk when
the script returns.

### Step 3 · Summarize

After the user has seen the pages, give a short markdown table:

| Page | Sheet | Status |
|---|---|---|
| 1 | EE-0 Cover | ✅ |
| 2 | EE-1 Three-Line | ⚠️ note any visible issue |

The Sheet codes in column 2 map to `pvess_calc.permit.sheet_registry.SHEET_REGISTRY`
in pipeline order. Call out visible layout issues (overlap, truncation,
mis-aligned text) — the doctor catches structural drift but can't catch
visual quality regressions.

## What this skill is NOT

- Does not modify code. Visual feedback only.
- Does not open QET (`open <project>/output/system.qet` is a manual step).
- Does not run pytest (use `.venv/bin/pytest -q` separately if needed).

## Failure recovery

| Symptom | Action |
|---|---|
| Script reports `✗ pvess-doctor reported structural drift` | Surface the doctor's FAIL detail verbatim; suggest reading docs/DESIGN.md |
| `pdftoppm: command not found` | Tell user to `brew install poppler` |
| Script exits 2 with "venv not set up" | Tell user to `python -m venv .venv && .venv/bin/pip install -e .` |

## Example invocations

```
/pvess-review
/pvess-review projects/003-austin-15kw/
/pvess-review --pages 1,3,5
/pvess-review projects/002-phoenix-25kw/ --no-permit
```
