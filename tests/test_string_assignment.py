"""K.10.1 — string-level layout assignment tests.

Eight layers of coverage:
  1. **Empty / degenerate** — empty input, n_strings ≤ 0 short-circuit.
  2. **Clean divide** — total == n_strings × target → uniform counts.
  3. **Shortfall** — total < ideal → LAST strings absorb the deficit
     (K.10.1 "keep the strongest cold-Voc check on full-length strings"
     rule). Verified bit-exact via 34/4×9 → [9,9,8,8].
  4. **Surplus** — total > ideal → extras dropped (defensive guard).
  5. **Face coupling** — modules on the same face land in the same
     string when count allows.
  6. **Ridge-first ordering** — within a face, higher-y (ridge-side)
     modules come first; ties break left → right.
  7. **Balance** — `string_balance_pp` returns (max, min) lengths and
     they differ by at most 1.
  8. **Immutability** — input ModuleInstances are NOT mutated; the
     function returns new objects.
"""
from __future__ import annotations

import pytest

from pvess_calc.calc.module_placement import ModuleInstance
from pvess_calc.calc.string_assignment import (
    _allocate_string_counts,
    assign_modules_to_strings,
    placements_by_string,
    string_balance_pp,
)


# ─── Test fixture helper ───────────────────────────────────────────────


def _mod(face: str, x: float, y: float) -> ModuleInstance:
    """Build a placement with sensible defaults. Only face/x/y matter
    for the sort key — width/height/rotation are irrelevant here."""
    return ModuleInstance(
        face_name=face, x_ft=x, y_ft=y,
        width_ft=3.72, height_ft=5.65, rotation_deg=0.0,
    )


def _row(face: str, y: float, n: int, x_step: float = 4.0) -> list[ModuleInstance]:
    """One row of `n` modules left-to-right on `face` at height `y`."""
    return [_mod(face, x=i * x_step, y=y) for i in range(n)]


# ─── Layer 1: empty / degenerate ───────────────────────────────────────


def test_assign_empty_input_returns_empty():
    """Empty placement list short-circuits to empty result."""
    assert assign_modules_to_strings(
        [], n_strings=4, modules_per_string=9,
    ) == []


def test_assign_n_strings_zero_marks_all_none():
    """Degenerate yaml (n_strings=0) → every module's string_index=None.
    Doctor flags this elsewhere; algorithm doesn't crash."""
    placements = _row("South", y=10, n=5)
    result = assign_modules_to_strings(
        placements, n_strings=0, modules_per_string=9,
    )
    assert len(result) == 5
    assert all(m.string_index is None for m in result)


def test_assign_n_strings_negative_marks_all_none():
    """Defensive: even nonsensical -1 doesn't crash."""
    placements = _row("South", y=10, n=3)
    result = assign_modules_to_strings(
        placements, n_strings=-1, modules_per_string=9,
    )
    assert all(m.string_index is None for m in result)


# ─── Layer 2: clean divide ─────────────────────────────────────────────


def test_assign_clean_divide_uniform_counts():
    """36 modules / 4 strings × 9 → every string gets exactly 9."""
    # Two faces, 18 modules each, 2 rows × 9
    placements = (
        _row("South", y=20, n=9) + _row("South", y=15, n=9)
        + _row("West", y=20, n=9) + _row("West", y=15, n=9)
    )
    result = assign_modules_to_strings(
        placements, n_strings=4, modules_per_string=9,
    )
    by_str = placements_by_string(result)
    assert sorted(by_str.keys()) == [0, 1, 2, 3]
    for s in range(4):
        assert len(by_str[s]) == 9, f"string {s} has {len(by_str[s])} modules"


# ─── Layer 3: shortfall (K.9 placed fewer than target) ─────────────────


def test_allocate_counts_shortfall_last_strings_short():
    """The canonical 34/4×9 case from the spec: [9, 9, 8, 8]."""
    counts = _allocate_string_counts(
        total=34, n_strings=4, target_per_string=9,
    )
    assert counts == [9, 9, 8, 8]
    assert sum(counts) == 34


def test_allocate_counts_shortfall_4of4_balanced():
    """Bigger shortfall: 32/4×9, shortfall=4 → [8, 8, 8, 8] (perfectly
    balanced after one full -1 pass across all strings)."""
    counts = _allocate_string_counts(
        total=32, n_strings=4, target_per_string=9,
    )
    assert counts == [8, 8, 8, 8]
    assert sum(counts) == 32


def test_allocate_counts_shortfall_odd_balanced():
    """33/4×9, shortfall=3 → [9, 8, 8, 8] (round-robin trim from end)."""
    counts = _allocate_string_counts(
        total=33, n_strings=4, target_per_string=9,
    )
    assert counts == [9, 8, 8, 8]
    # K.10.5 doctor invariant
    assert max(counts) - min(counts) <= 1


def test_assign_shortfall_first_strings_full_length():
    """K.10 contract: when placement falls short, the FIRST strings
    keep `modules_per_string` (strongest cold-Voc case stays at full
    voltage). Verified with 34 modules / 4 strings × 9 target."""
    placements = (
        _row("South", y=20, n=9) + _row("South", y=15, n=9)
        + _row("West", y=20, n=9) + _row("West", y=15, n=7)   # 34 total
    )
    result = assign_modules_to_strings(
        placements, n_strings=4, modules_per_string=9,
    )
    by_str = placements_by_string(result)
    counts = [len(by_str[s]) for s in range(4)]
    assert counts == [9, 9, 8, 8]


# ─── Layer 4: surplus (defensive) ──────────────────────────────────────


def test_assign_surplus_clamps_to_target():
    """If somehow more placements than n×target arrive, extras are
    dropped — the schema validator should prevent this, but the
    algorithm doesn't crash."""
    # 40 modules but only 4 strings × 9 = 36 slots
    placements = (
        _row("South", y=20, n=10) + _row("South", y=15, n=10)
        + _row("West", y=20, n=10) + _row("West", y=15, n=10)
    )
    result = assign_modules_to_strings(
        placements, n_strings=4, modules_per_string=9,
    )
    by_str = placements_by_string(result)
    # 4 strings each with target=9 → 36 assigned; 4 dropped or unassigned
    assigned = sum(1 for m in result if m.string_index is not None)
    assert assigned <= 36


# ─── Layer 5: face-coupling ────────────────────────────────────────────


def test_assign_face_coupling_groups_same_face_first():
    """Modules on the SAME face should land in adjacent strings when
    counts allow. With 18 South + 18 West and 4 strings × 9, the first
    two strings should both be 100% South, the last two 100% West."""
    placements = (
        _row("South", y=20, n=9) + _row("South", y=15, n=9)
        + _row("West", y=20, n=9) + _row("West", y=15, n=9)
    )
    result = assign_modules_to_strings(
        placements, n_strings=4, modules_per_string=9,
    )
    by_str = placements_by_string(result)
    # Strings 0 & 1 should be all-South; strings 2 & 3 all-West
    s0_faces = {m.face_name for m in by_str[0]}
    s3_faces = {m.face_name for m in by_str[3]}
    assert s0_faces == {"South"}, f"string 0 mixed: {s0_faces}"
    assert s3_faces == {"West"}, f"string 3 mixed: {s3_faces}"


def test_assign_face_coupling_allows_split_when_count_doesnt_divide():
    """If a face's modules don't divide evenly into strings, the
    LAST string of that face may span into the next face. K.10.1 v1
    doesn't fully prohibit split-face strings (future K.10.x might)."""
    # 5 South + 9 West, 2 strings × 7 — string 0 must span both faces
    placements = (
        _row("South", y=20, n=5) + _row("West", y=20, n=9)
    )
    result = assign_modules_to_strings(
        placements, n_strings=2, modules_per_string=7,
    )
    by_str = placements_by_string(result)
    s0_faces = {m.face_name for m in by_str[0]}
    # String 0 gets all 5 South + first 2 West — both faces present
    assert s0_faces == {"South", "West"}


# ─── Layer 6: ridge-first ordering within face ─────────────────────────


def test_assign_ridge_first_ordering():
    """Within a face, higher-y (ridge-side) modules come first.
    Verifies the (face, -y, x) sort key."""
    # 3 rows: y=20 (ridge), y=15, y=10 (eave-side). Each row 3 wide.
    placements = (
        _row("South", y=10, n=3)     # eave row
        + _row("South", y=20, n=3)   # ridge row
        + _row("South", y=15, n=3)   # middle
    )
    result = assign_modules_to_strings(
        placements, n_strings=1, modules_per_string=9,
    )
    # Single string holds all 9 in ridge → middle → eave, left → right
    assert [m.y_ft for m in result] == [20, 20, 20, 15, 15, 15, 10, 10, 10]
    # Within each row, x is ascending (left → right)
    ridge_row = [m for m in result if m.y_ft == 20]
    assert [m.x_ft for m in ridge_row] == sorted([m.x_ft for m in ridge_row])


# ─── Layer 7: balance ──────────────────────────────────────────────────


def test_string_balance_pp_clean_divide_is_perfect():
    """36/4×9 → max==min==9, perfectly balanced."""
    placements = (
        _row("South", y=20, n=9) + _row("South", y=15, n=9)
        + _row("West", y=20, n=9) + _row("West", y=15, n=9)
    )
    result = assign_modules_to_strings(
        placements, n_strings=4, modules_per_string=9,
    )
    max_n, min_n = string_balance_pp(result, target_per_string=9)
    assert max_n == 9 and min_n == 9


def test_string_balance_pp_shortfall_within_one():
    """34/4×9 → max=9, min=8 (the doctor invariant: |max-min| ≤ 1)."""
    placements = (
        _row("South", y=20, n=9) + _row("South", y=15, n=9)
        + _row("West", y=20, n=9) + _row("West", y=15, n=7)
    )
    result = assign_modules_to_strings(
        placements, n_strings=4, modules_per_string=9,
    )
    max_n, min_n = string_balance_pp(result, target_per_string=9)
    assert max_n - min_n <= 1, f"unbalanced: max={max_n}, min={min_n}"


def test_string_balance_pp_empty_returns_zero_zero():
    """No valid strings → (0, 0) sentinel, doctor handles separately."""
    assert string_balance_pp([], target_per_string=9) == (0, 0)


# ─── Layer 8: immutability ─────────────────────────────────────────────


def test_assign_does_not_mutate_input():
    """Input ModuleInstance objects are frozen dataclasses — verifying
    we return NEW objects via `replace()`, not mutate originals."""
    original = _mod("South", x=0, y=10)
    placements = [original]
    result = assign_modules_to_strings(
        placements, n_strings=1, modules_per_string=1,
    )
    # Input untouched
    assert original.string_index is None
    # Result has the assignment
    assert result[0].string_index == 0
    # Different object identity (replace creates a new frozen instance)
    assert result[0] is not original


def test_placements_by_string_groups_correctly():
    """`placements_by_string` collects modules by their string_index."""
    placements = (
        _row("South", y=20, n=9) + _row("West", y=20, n=9)
    )
    result = assign_modules_to_strings(
        placements, n_strings=2, modules_per_string=9,
    )
    by_str = placements_by_string(result)
    assert set(by_str.keys()) == {0, 1}
    assert len(by_str[0]) == 9
    assert len(by_str[1]) == 9


# ─── Frisco regression case ────────────────────────────────────────────


def test_assign_frisco_34_module_5_face_case():
    """The live Frisco shape: 34 modules across 5 faces, 4 strings × 9.
    Result should be [9, 9, 8, 8] face-coupled where possible — the
    K.10.5 balanced-allocation rule (|max - min| ≤ 1) wins over
    "keep tail string short."

    This locks the distribution so future tweaks don't silently
    regress."""
    placements = (
        # South Roof: 12 modules
        _row("South Roof", y=20, n=6) + _row("South Roof", y=15, n=6)
        # South Roof #2: 8 modules
        + _row("South Roof #2", y=20, n=4) + _row("South Roof #2", y=15, n=4)
        # South Roof #3: 4 modules
        + _row("South Roof #3", y=20, n=4)
        # West Roof: 6 modules
        + _row("West Roof", y=20, n=3) + _row("West Roof", y=15, n=3)
        # West Roof #2: 4 modules
        + _row("West Roof #2", y=20, n=4)
    )
    assert len(placements) == 34
    result = assign_modules_to_strings(
        placements, n_strings=4, modules_per_string=9,
    )
    by_str = placements_by_string(result)
    counts = [len(by_str[s]) for s in range(4)]
    assert counts == [9, 9, 8, 8]
    # K.10.5 doctor invariant: |max - min| ≤ 1 even with shortfall.
    assert max(counts) - min(counts) <= 1
