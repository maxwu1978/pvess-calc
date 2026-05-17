"""K.9.2 — shared face-distribution helper.

Extracts the K.8.1 Largest Remainder Method (LRM) auto-distribute logic
from `customer/production.py` so it can be called from BOTH paths:

  * `customer/production.compute_annual_production` (kWh math)
  * `calc/engine.run` (PV-4 module placement, K.9.1)

Both consumers see byte-identical distribution — no risk of the
customer-PDF and the permit-PDF disagreeing on which face holds how many
modules. K.8.1 tests + K.9.1 tests guard the math invariant; this file
is the single implementation.

Extends K.8.1 with optional K.8.2 value-weighting when:
  * `inputs.loads.use_value_weighted_distribution` is True, AND
  * latitude_deg is available

On 1:1 REP plans the value-weighted math collapses to area-only (same
result), so the engine doesn't need to know which mode it's in.
"""
from __future__ import annotations

import math
from typing import Optional

from ..schema import Inputs


def distribute_modules_to_faces(
    inputs: Inputs,
    *,
    latitude_deg: Optional[float] = None,
) -> dict[str, int]:
    """Return per-face module counts, honouring whatever was already
    declared in the yaml. Three states:

      A. Every `section.module_count > 0` (designer-pinned) → return
         declared counts unchanged.
      B. All `module_count = 0` BUT `pv_array.modules > 0` (K.3c init
         state) → run LRM auto-distribute proportional to face weight.
      C. `pv_array.modules = 0` OR no sections → return empty dict.

    Returns:
        Dict keyed by `section.name` → integer module count. Σ values
        ≤ `pv_array.modules` (conservation).
    """
    sections = list(inputs.site.roof_sections)
    if not sections:
        return {}
    total_modules = inputs.pv_array.modules
    if total_modules <= 0:
        return {}

    # State A: designer already distributed → respect their yaml.
    declared = sum(s.module_count for s in sections)
    if declared > 0:
        return {s.name: s.module_count for s in sections if s.module_count > 0}

    # State B: K.3c init → run LRM auto-distribute.
    face_areas = [s.gross_area_sqft for s in sections]
    total_area = sum(face_areas)
    if total_area <= 0:
        return {}

    # K.8.2 value-weighting (opt-in). When the flag is on AND latitude
    # is known, weight faces by `area × face_value_weighted_derate`
    # instead of pure area. Math collapses on 1:1 REP plans → same as
    # area-only there.
    use_value_weight = (
        inputs.loads.use_value_weighted_distribution
        and latitude_deg is not None
    )
    if use_value_weight:
        from ..customer.economics import EXPORT_RATIOS
        from .value_weighted import face_value_weighted_derate

        if inputs.loads.rep_buyback_ratio is not None:
            ratio = float(inputs.loads.rep_buyback_ratio)
        else:
            ratio = EXPORT_RATIOS.get(inputs.loads.export_tariff_model, 1.0)

        face_weights = [
            a * face_value_weighted_derate(
                s.azimuth_deg, s.pitch_deg, latitude_deg, ratio,
            )
            for a, s in zip(face_areas, sections)
        ]
    else:
        face_weights = face_areas

    total_weight = sum(face_weights)
    if total_weight <= 0:
        # Edge: every face's value_weighted_derate is 0 (degenerate
        # high-lat winter). Fall back to area-only.
        face_weights = face_areas
        total_weight = total_area

    # Largest Remainder Method (Hamilton 1792, US House apportionment).
    # 1. Each face's fair share = total × weight / sum(weights).
    # 2. Floor everything; remainder distributes one-by-one to the
    #    faces with the largest fractional shortfall.
    fair_shares = [total_modules * w / total_weight for w in face_weights]
    floors = [math.floor(fs) for fs in fair_shares]
    remainder = total_modules - sum(floors)
    # Tie-break by descending fractional part; stable (input order).
    order = sorted(
        range(len(sections)),
        key=lambda i: (-(fair_shares[i] - floors[i]), i),
    )
    counts = list(floors)
    for j in range(remainder):
        counts[order[j]] += 1

    return {sections[i].name: counts[i] for i in range(len(sections))}
