---
name: pvess-roof-topology-vision
description: Generate and QA a proposed PVESS EE-4 roof topology from satellite review artifacts, roof imagery, or vision-model JSON. Use when roof drawings do not match satellite imagery, when Step 2 roof topology needs refinement, or when a user asks to use a large vision model/skill to draft roof outline, roof lines, fire pathways, and panel layout.
---

# pvess-roof-topology-vision

## Overview

Use this skill to create a reviewable `site.ee4_trace` proposal before a PVESS permit package is generated. The goal is not to let an LLM draw the final sheet directly; the model proposes structured roof topology, then PVESS deterministic renderers and QA decide whether it is usable.

## Workflow

1. Locate the web job or project directory containing `request.json` and `output/`.
2. If a vision model is available, ask it to return JSON matching `references/output_schema.md`; otherwise use the existing satellite trace candidate or EE-4 draft as deterministic fallback.
3. Run:

```bash
python .agents/skills/pvess-roof-topology-vision/scripts/generate_topology_proposal.py \
  --job-dir "$JOB_DIR"
```

If you have model output saved as JSON:

```bash
python .agents/skills/pvess-roof-topology-vision/scripts/generate_topology_proposal.py \
  --job-dir "$JOB_DIR" \
  --vision-json /tmp/roof-topology-model-output.json
```

If you want the script to call OpenAI vision directly, pass the satellite crop:

```bash
python .agents/skills/pvess-roof-topology-vision/scripts/generate_topology_proposal.py \
  --job-dir "$JOB_DIR" \
  --openai-image "$JOB_DIR/output/satellite-roof-outline-candidate.png"
```

By default the script auto-selects a vision-capable model from `/models`
when `OPENAI_BASE_URL` points to an OpenAI-compatible gateway. Override
with `--openai-model <model>` or `PVESS_ROOF_TOPOLOGY_OPENAI_MODEL`.

4. Review generated artifacts in `output/roof-topology-vision/`:

- `site-ee4-trace-proposed.yaml` — paste/apply candidate for `site.ee4_trace`
- `roof-topology-review.pdf` — EE-4-only review PDF
- `roof-topology-review.png` — quick visual preview when Poppler is available
- `roof-topology-qa.json` / `.md` — roof trace and trace-module layout gate results

## Provider Comparison

To compare OpenAI-compatible providers and the direct-drawing approach:

```bash
python .agents/skills/pvess-roof-topology-vision/scripts/compare_topology_providers.py \
  --job-dir "$JOB_DIR" \
  --image "$JOB_DIR/output/satellite-roof-outline-candidate.png"
```

The comparison writes `provider-comparison.md` and one folder per provider.
It automatically skips missing API keys. For each available provider it tests:

- **structured topology**: model returns JSON trace; PVESS sanitizes, validates, and renders it.
- **direct SVG drawing**: model returns a drawing-like SVG; this is saved for visual comparison but is never AHJ-ready because PVESS cannot verify module count, setbacks, scale, or geometry invariants.

## Rules

- Do not edit `inputs.yaml` automatically unless the user explicitly approves applying the proposal.
- The LLM output must be structured data, not a final drawing image. Final drawings always come from PVESS renderers.
- Live OpenAI use is opt-in and requires `OPENAI_API_KEY`; otherwise use deterministic fallback.
- V1 accepts model roof lines/facets only. Satellite mask remains the authoritative outline, code-generated fire pathways remain authoritative, and model-guessed obstruction symbols are discarded unless a future evidence workflow explicitly enables them.
- A proposal is acceptable only when `roof_trace.can_ahj_ready=true`, `trace_module_layout.can_ahj_ready=true`, and `placed_modules == target_modules`.
- If QA fails, report the blocking lints and keep the review PNG/YAML for manual correction.
- For visual-model prompting, load only `references/output_schema.md`; keep the prompt focused on visible roof outline, ridges/hips/valleys, obstructions, fire-pathway candidate strips, and PV module count.

## Closing Standard

All five checks must pass before recommending a trace for Step 2 acceptance:

| Check | Pass condition |
|---|---|
| Structured trace | `site-ee4-trace-proposed.yaml` validates as `EE4Trace` |
| Review rendering | EE-4 review PDF exists and PNG exists when Poppler is installed |
| Roof trace QA | `roof_trace.status` is `PASS` |
| Module layout QA | `trace_module_layout.can_ahj_ready` is true |
| Count match | `placed_modules == target_modules` |

If any check fails, treat the output as a draft for manual tracing, not as AHJ-ready geometry.
