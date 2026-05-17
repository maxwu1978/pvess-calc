"""K.10.1 — string-level layout assignment.

Bridges K.9.1 per-module placement and the PV-4 / PV-6 renderers:
given a flat list of `ModuleInstance` objects (across all roof
faces) + the project's declared string count, return the SAME list
with `string_index` populated.

Constraint hierarchy (most important first):

  1. **Per-string Voc-cold compliance** — same number of modules per
     string keeps the NEC 690.7(A) cold-Voc check uniform across
     MPPTs. Already enforced by the schema validator
     `modules == strings × modules_per_string`; this algorithm
     respects the declared length.

  2. **Face-coupled when possible** — modules in a single string
     SHOULD live on one face (or contiguous faces in the same
     compass quadrant). Different-face strings mix orientations,
     producing different cold-Voc per module + sub-optimal MPPT
     tracking. K.10.1 v1 prefers face-coupling but doesn't fully
     prohibit split-face strings — future K.10.x might add a
     `prefer_face_coupled: bool` flag.

  3. **Geometric continuity** — within a face, modules in a string
     should be ADJACENT (one row, or contiguous columns). Easier
     wiring; less voltage drop. Achieved by sorting placements
     ridge→eave + left→right before sequential assignment.

  4. **Balance** — when the placement count doesn't divide evenly
     into `n_strings` (typical K.9 shortfall: 34 placed of 36
     target, 4 strings × 9), distribute the short modules to the
     LAST strings so the first strings stay at `modules_per_string`
     (Voc-cold check sees the strongest case).

Returns a new list — input ModuleInstances are NOT mutated.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Optional

from .module_placement import ModuleInstance


def assign_modules_to_strings(
    placements: Iterable[ModuleInstance],
    *,
    n_strings: int,
    modules_per_string: int,
) -> list[ModuleInstance]:
    """Assign each placement a `string_index` in [0, n_strings).

    Args:
        placements: flat list of K.9.1 ModuleInstance (mixed faces).
        n_strings: how many strings the inverter MPPT supports
            (`pv_array.strings`).
        modules_per_string: nominal length of each string
            (`pv_array.modules_per_string`). Used as a target;
            actual length may be one less when placement count
            falls short.

    Returns:
        New list of ModuleInstance with `string_index` populated.
        Same length as input. None of the input objects are mutated.

    Edge cases:
        * Empty input → empty output.
        * n_strings ≤ 0 → all modules get string_index = None
          (degenerate; doctor flags this).
        * total < n_strings × modules_per_string (K.9 shortfall) →
          modules trail off; LAST strings get fewer modules.
        * total > n_strings × modules_per_string (shouldn't happen
          per schema validator) → extra modules dropped from end
          (with a warning surfaced in the result-aware caller).
    """
    placements_list = list(placements)
    if not placements_list:
        return []
    if n_strings <= 0:
        # Degenerate yaml — emit with string_index unset
        return [replace(m, string_index=None) for m in placements_list]

    # Stable, deterministic ordering: face name, then ridge → eave
    # (descending y), then left → right (ascending x). Matches the
    # K.9.1 ridge-first sort the renderer uses, so the modules end
    # up colored in horizontal/vertical bands the eye can follow.
    sorted_pl = sorted(
        placements_list,
        key=lambda m: (m.face_name, -m.y_ft, m.x_ft),
    )

    # Allocate counts per string. Target = modules_per_string.
    # Total placements ≤ n_strings × modules_per_string almost always
    # (per K.9.5 doctor); if placement fell short, the last strings
    # absorb the deficit.
    total = len(sorted_pl)
    counts = _allocate_string_counts(
        total=total,
        n_strings=n_strings,
        target_per_string=modules_per_string,
    )

    # Apply: walk sorted_pl and assign each module to a string.
    result: list[ModuleInstance] = []
    idx = 0
    for s, count in enumerate(counts):
        for _ in range(count):
            if idx >= total:
                break
            result.append(replace(sorted_pl[idx], string_index=s))
            idx += 1
    # Any leftover (shouldn't happen, but defensive)
    while idx < total:
        result.append(replace(sorted_pl[idx], string_index=None))
        idx += 1
    return result


def _allocate_string_counts(
    *, total: int, n_strings: int, target_per_string: int,
) -> list[int]:
    """Decide how many modules each string holds.

    Cases:
      A. total == n_strings × target → every string gets target (clean)
      B. total < that → first strings get target; last strings get
         one fewer (the "leave the strongest at full length" rule —
         keeps the worst-case cold-Voc check on full-length strings)
      C. total > that → first strings get target, the OVERFLOW past
         the limit is dropped from the last string (defensive only;
         the schema validator should already prevent this)
    """
    ideal = n_strings * target_per_string
    if total == ideal:
        return [target_per_string] * n_strings

    if total < ideal:
        # Distribute the shortfall one-at-a-time across the LAST
        # strings, working backwards. The K.10.5 doctor invariant
        # requires `|max - min| ≤ 1`, so we trim ONE module per pass
        # rather than emptying the tail string first. Examples:
        #   total=34, n=4, target=9, shortfall=2 → [9, 9, 8, 8]
        #   total=32, n=4, target=9, shortfall=4 → [8, 8, 8, 8]
        #   total=33, n=4, target=9, shortfall=3 → [9, 8, 8, 8]
        counts = [target_per_string] * n_strings
        shortfall = ideal - total
        s = n_strings - 1
        while shortfall > 0:
            if counts[s] > 0:
                counts[s] -= 1
                shortfall -= 1
            s -= 1
            if s < 0:
                s = n_strings - 1
        return counts

    # total > ideal — clamp to target per string (drops surplus).
    return [target_per_string] * n_strings


# ─── Public helpers for the renderer ───────────────────────────────────


def placements_by_string(
    placements: Iterable[ModuleInstance],
) -> dict[Optional[int], list[ModuleInstance]]:
    """Group a flat placement list by `string_index`. Convenience for
    PV-4 / PV-6 color iteration. None-keyed entry collects modules
    that didn't get a string (degenerate-yaml fallback)."""
    out: dict[Optional[int], list[ModuleInstance]] = {}
    for m in placements:
        out.setdefault(m.string_index, []).append(m)
    return out


def string_balance_pp(
    placements: Iterable[ModuleInstance],
    *,
    target_per_string: int,
) -> tuple[int, int]:
    """Return (max_modules_in_any_string, min_modules_in_any_string).
    Caller checks `max - min ≤ 1` for a "balanced" allocation —
    the K.10.5 doctor invariant."""
    by_str = placements_by_string(placements)
    valid = {k: v for k, v in by_str.items() if k is not None}
    if not valid:
        return 0, 0
    lengths = [len(v) for v in valid.values()]
    return max(lengths), min(lengths)
