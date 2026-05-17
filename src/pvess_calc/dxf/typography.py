"""DXF typography tiers — single source of truth for text heights.

Four sizes covering every text element in EE-1 / EE-2, with a clean
geometric ratio (~1.2× between adjacent tiers). DESIGN.md §3 policy:
all magic numbers at the top, propagate by name.

  TEXT_TITLE   → schedule table titles (CONDUCTOR SCHEDULE, etc.) +
                 the "EQUIPMENT GROUNDING BUS" / "GROUNDING ELECTRODE
                 SYSTEM" banners on EE-2.
  TEXT_HEADER  → section / column / device headers:
                 • title-block section bars (DESIGN ENGINEER, …)
                 • notes-strip labels + values
                 • schedule column header row (TAG, WIRES, …)
                 • TAG1 ATTDEF below each device box
                 • equipment-stub labels on EE-2 grounding diagram
  TEXT_BODY    → body text:
                 • title-block body lines
                 • schedule data rows
                 • ATTDEF DESC1 / DESC2 / MFG / CAT
                 • bay labels (GEN/LOAD/GRID) inside inverter
                 • panel/inverter header strip ABOVE the device box
                 • AC/DC GEC wire labels, RSD text, ±battery markers,
                   MLPE optimizer label
  TEXT_CAPTION → small captions:
                 • panel subtitle ("200A · 120/240V")
                 • internal breaker rows (function label + rating)
                 • inline breaker symbol label (2P-45A)
                 • N-G BOND annotation
                 • electrode-symbol qualifier line ("8 FT MIN, …")

Lives in its own module (rather than render.py) so symbols.py can import
the tiers without creating a render ↔ symbols circular dependency.
"""
from __future__ import annotations


TEXT_TITLE   = 0.115
TEXT_HEADER  = 0.095
TEXT_BODY    = 0.080
TEXT_CAPTION = 0.065
