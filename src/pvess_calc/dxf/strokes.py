"""DXF stroke-weight tiers — single source of truth for line thickness.

Three weights covering every line in EE-1 / EE-2. Values are in DXF
lineweight units (0.01 mm; e.g. 35 = 0.35 mm wide). Geometric ratio
~2× / 1.7× between adjacent tiers — visually distinct in any viewer
that respects lineweight (AutoCAD, LibreCAD, BricsCAD, matplotlib-DXF).

  STROKE_THIN  → background / accent strokes:
                 • swatch cell dashed border
                 • subtle accents inside icons
                 • cell-divider lines inside schedules
  STROKE_MED   → equipment outline + icon geometry + frame strokes:
                 • device outlines (PV / COMB / INV / ESS / panel boxes)
                 • internal icon geometry (chevron, knife lever, battery
                   cells, breaker notches, terminal blocks, DC ladder)
                 • title-block / schedule frame box strokes
                 • callout circles (A/B/C/D/E)
                 • inline breaker symbol box
  STROKE_HEAVY → main conductor trunks + dominant bus bars:
                 • DC/AC trunk lines (vertical buses)
                 • equipment grounding bus on EE-2
                 • GEC main run
                 • outer sheet border (so the page reads as bordered)
                 • meter circle (so the M is anchored visually)

Lives in its own module (rather than render.py or typography.py) so
icon code, sheet code, and the swatch tool can all import without
creating cycles. Matches DESIGN.md §3 "magic numbers at the top"
policy — symmetry with `typography.py`.
"""
from __future__ import annotations


STROKE_THIN  = 18
STROKE_MED   = 35
STROKE_HEAVY = 60
