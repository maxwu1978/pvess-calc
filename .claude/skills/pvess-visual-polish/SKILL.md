---
name: pvess-visual-polish
description: Run a bounded visual-polish iteration on EE-1 / EE-2 DXF sheets — closing-standard, time-boxed, with known collision-patterns and their fixes. Use when the user asks to "再磨一下", "细调", "优化排版", "polish", "继续优化视觉", or hands over a screenshot pointing at a layout problem.
---

# pvess-visual-polish — bounded visual iteration

This skill captures the lessons learned from the 2026-05-13 → 2026-05-14
visual-polish iterations: typography collapse, stroke collapse, text-overlap
detection, and the specific text-vs-wire collisions that doctor's automated
checks **don't catch**.

## Closing standard (5 criteria, all must PASS)

Anchor every visual-polish session against these. Do not start free-form
iteration without re-checking which criterion is the current target.

| # | Criterion | How to verify |
|---|---|---|
| ① | **Typography收敛** — no `height=0.XXX` literals in `dxf/*.py` | `grep -nE "height=0\." src/pvess_calc/dxf/*.py \| grep -v "typography\|strokes\|symbols_preview"` must be empty |
| ② | **线重收敛** — no `lineweight=N` literals in `dxf/*.py` | `grep -nE "\"lineweight\":\s*\d+\|lineweight=\d+" src/pvess_calc/dxf/*.py \| grep -v strokes` must be empty |
| ③ | **文字-容器零溢出** | `pvess-doctor` → `dxf_text_no_overflow` PASS |
| ④ | **文字-文字零重叠** | `pvess-doctor` → `dxf_no_text_overlap` PASS |
| ⑤ | **视觉肉眼复查 5 项** | Open swatch + EE-1 + EE-2, eyeball this list:<br>• 整张图只能看到 4 种字号大小<br>• 整张图只能看到 3 种线重<br>• 没有 wire 线穿过 text 中心<br>• 没有 text 跟 icon 几何重叠<br>• 颜色清晰（DC+ 红 / DC− 黑 / AC L1 黑 / L2 红 / N 灰 / G 绿） |

## Time-box: 2 iterations max

Visual polish is unbounded. Cap at 2 iterations from any closing standard.
After that, defer remaining items to a Phase-N backlog and ship. Do not
chase pixel-perfect — chase "passes all 5 criteria, no obvious eye-sore".

## Toolchain

Three commands, in this order each iteration:

```bash
# 1. Verify standards still hold + automated checks
.venv/bin/pytest -q                                  # must be all-green
.venv/bin/pvess-doctor projects/002-phoenix-25kw/    # must be 16/16 PASS
grep -nE "height=0\.|\"lineweight\":\s*\d+|lineweight=\d+" \
  src/pvess_calc/dxf/*.py | grep -v "typography\|strokes\|symbols_preview"
# should output nothing

# 2. Visual swatch — symbols isolated, 3 sec
.venv/bin/pvess-symbols-preview -o /tmp/swatch.pdf

# 3. Full permit visual review
./scripts/pvess-review        # builds everything + rasterizes EE-1..12 to /tmp/pvess_review-NN.png
```

The swatch is for SYMBOL-level iteration (icon shapes, stroke balance,
internal text). The pvess-review output is for INTEGRATION-level iteration
(spacing, wire routing, headers, ATTDEFs).

## Known collision patterns + canonical fixes

Each pattern is something we hit. The "Diagnosis" column tells you what
the screenshot looks like. The "Fix" column is what's been proven to work.

### A. Text vs text (horizontal proximity)

| Symptom | Diagnosis | Fix |
|---|---|---|
| Two adjacent panels' headers butt together | header text width > panel width + chain_gap | Shorten header text OR widen `chain_gap` OR shrink header font (move to TEXT_BODY tier) |
| ATTDEF stack of device A overlaps ATTDEF stack of device B | Device boxes too close horizontally | Widen the spec.w OR widen `chain_gap` |
| Internal breaker label crowds the next breaker row | Row pitch too tight | Increase panel height (taller box) OR reduce breaker count |

### B. Text vs container border (covered by doctor)

| Symptom | Diagnosis | Fix |
|---|---|---|
| Schedule cell text bleeds past frame line | Text width > column width | Apply `fit_dxf(text, max_w, height)` from `dxf/_textfit.py` |
| Title block body line bleeds past frame | Same | Same |
| Notes strip line extends past the schematic area | Notes too long | Shorten or wrap |

### C. Text vs wire (doctor MISSES this — manual review!)

This is the class of bug the closing standard's ④ does NOT cover.
`dxf_no_text_overlap` only checks text-vs-text. Wires and polyline icons
go undetected. Always eyeball page 2 + page 3 for these.

| Symptom | Diagnosis | Fix |
|---|---|---|
| Vertical wire from MSP bottom crosses MSP's DESC1/DESC2 ATTDEFs | ATTDEFs at center-X, wire at center-X | **Set `attdef.dxf.flags = 1` (invisible) for the conflicting ATTDEFs**. Wyssling header above the box already carries the info. Test `test_device_blocks_carry_acade_attributes` still passes because data is preserved.<br>Implemented for `MSP` block in `_ensure_device_block`. |
| Vertical wire from MSP bottom crosses SUB-#1's header text | Header centered on panel top, wire centered too | **Move header to the SIDE of the panel** (right-aligned, ending just left of panel edge). See `_place_critical_panels` in render.py. |
| Notes strip text touches PV-S1 box top | PV column extends higher than expected (multi-string layout) | **Increase `NOTES_AREA_H`** in `_draw_schematic` — shifts the whole inverter + PV column DOWN to clear the notes |

### D. Text vs icon geometry (doctor also MISSES — manual review!)

| Symptom | Diagnosis | Fix |
|---|---|---|
| Centered "INV"/"PV" caption inside box grazes the icon geometry | The dead `_ensure_device_block` caption text was redundant with TAG1 below | Already removed — block factory has no centered caption since 2026-05-13. Don't re-add. |
| RSD has duplicate "RSD" text | Icon function draws "RSD" AND factory adds "RSD" caption | Already fixed — icon function is the sole source. Don't add a factory caption. |

### E. Schedule table overflow (recurring class)

Both EE-1 CONDUCTOR SCHEDULE and EE-2 GROUNDING & BONDING SCHEDULE
fit ≥6 rows × 4-10 columns into 4.5" width. They keep colliding as
new fields get added. **Canonical fix order**:

| Symptom | Fix (in order of escalation) |
|---|---|
| Headers like "WIRESSIZE" / "AMPCYOCPD" run together | Step 1: demote column headers from `TEXT_HEADER` → `TEXT_BODY`. Same width as data; visual distinction via underline. See DESIGN.md §7.6.B. |
| Data cells like "10 AWG" overflow into next column | Step 2: drop redundant prefixes — "EGC: PV source" → "PV source", "10 AWG CU" → "10 AWG" when notes header already declares CU. See §7.6.C. |
| Schedule has columns derived from others (×1.25, AMPS×0.8, etc.) | Step 3: drop derivable columns. NEC inspectors do mental math. See §7.6.D. |
| RUN/DESCRIPTION column gets fit_dxf-chopped to ellipsis | Step 4: shorten descriptions to device-tag arrows ("MSP → GES" not "MSP → grounding electrode system"). See §7.6.E. |
| Column values are hardcoded literals that "happen to match" | Step 5: wire to `result.grounding.*` / `result.adjacent.*` etc. See §7.6.A. |

## When the user asks about "how is this number computed"

Reading a schedule cell is also an audit opportunity. If the user asks
"how is GND column computed?" or "is this OCPD right?", **trace it to
`result.<...>` and verify the calc reads the right derating factor**.

Real example (2026-05-14): user asked about CONDUCTOR SCHEDULE values.
Trace revealed:

- GND column: was hardcoded `"10 AWG"`, not `result.grounding.egc_*`
- CONDUIT column: was hardcoded `"3/4\" EMT"`, not
  `result.adjacent.*_conduit.selected_conduit`
- `_per_inverter_ac_spec` was passing `derating_factor=1.0` to
  `select_copper`, missing NEC 310.15(B) temperature correction. In
  Phoenix (45°C ambient → 0.82 factor), 8 AWG @ 75°C nominal 50A
  derated to 41A — just below 41.25A required. Algorithm silently
  undersized the per-inverter AC tap conductor.

**Lesson**: when a value looks plausible for one fixture, run the calc
with a different fixture (or just trace it in the source) before
declaring it correct. The 8 AWG choice "looked right" because the
display didn't show derating — but the conductor was actually undersized.

For test methodology around these audits, see
`docs/TESTING.md` §7 "Positive-guard vs regression-bait".

## The "design tokens" architecture

After this round, every text/stroke is parameterized:

```
dxf/typography.py    → TEXT_TITLE (0.115) / TEXT_HEADER (0.095) / TEXT_BODY (0.080) / TEXT_CAPTION (0.065)
dxf/strokes.py       → STROKE_THIN (18) / STROKE_MED (35) / STROKE_HEAVY (60)
```

Tier mapping is documented at the top of each file. **New text or new
lineweight = pick a tier, never a number**. If a tier doesn't fit, the
problem is the layout, not the tier — fix the layout.

The swatch tool (`symbols_preview.py`) has its own `SWATCH_*` constants
because the swatch is a different presentation environment (single-page
DEV tool, larger text for readability). Don't mix.

## Closing checklist (paste into chat when shipping a polish round)

```
Iteration N closed.

Automated:
  pytest:       135/135 ✓
  doctor:       16/16   ✓
  ① typography: 0 height literals
  ② strokes:    0 lineweight literals
  ③ overflow:   PASS (SCHEDULE/TITLE_BLOCK/NOTES)
  ④ text-text:  PASS (25% threshold)

Visual (eyeball):
  4 字号:   PASS / FAIL
  3 线重:   PASS / FAIL
  wire-text: PASS / FAIL
  text-geom: PASS / FAIL
  色彩清晰:  PASS / FAIL

Deferred to Phase-N: <list any items>
```

## Anti-patterns (do not do)

1. **Hardcoding `height=0.XXX` "just this once"** — drift starts here. Use a tier.
2. **Adding a new lineweight value** — same. Use STROKE_THIN/MED/HEAVY.
3. **Centered caption text inside a device box** — it always grazes the icon or duplicates the TAG1 ATTDEF below.
4. **Extending the panel header text to fix overflow** — the panel width is the constraint; SHORTEN the header instead.
5. **Adding a new doctor check without a regression-bait test** — every doctor check should have a paired test that monkey-patches the fix back out and verifies the check fires. See `tests/test_doctor.py::test_dxf_text_overflow_is_caught_when_fit_disabled` for the template.
6. **Polishing 3+ iterations without writing it up** — at 2 iterations, document remaining items as Phase-N backlog and stop.

## Skill invocation

```
/pvess-visual-polish
```

Reads the user's screenshot or description, classifies the collision
(A/B/C/D from above), applies the canonical fix, re-runs the toolchain,
and reports against the 5 criteria. If the user wants a clean
walkthrough rather than fix-driven, refer them to docs/DESIGN.md §7.
