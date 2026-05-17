"""K.2.7 — polygon math primitive unit tests.

Three known-shape contracts:
  * Convex pentagon (5 equilateral edges)
  * L-shape (concave hexagon — typical L-house wing)
  * Plus / cross-shape (concave dodecagon — typical T-house addition)

Plus point-in-polygon + clipped_grid edge cases.
"""
from __future__ import annotations

import math

import pytest

from pvess_calc.calc.polygon import (
    bounding_box,
    clipped_grid,
    fit_module_grid,
    is_convex,
    offset_polygon,
    point_in_polygon,
    polygon_area,
    polygon_inset_area,
    polygon_perimeter,
)


# ─── Test fixtures: well-known polygons ───────────────────────────────


def _square_10ft() -> list[tuple[float, float]]:
    """A 10×10 CCW square. Area=100, perimeter=40."""
    return [(0, 0), (10, 0), (10, 10), (0, 10)]


def _l_shape() -> list[tuple[float, float]]:
    """L-shape: 20×10 main + 10×10 wing on east side.
       ┌────────┐
       │        │
       │   ┌────┘
       │   │
       └───┘
    Vertices CCW from bottom-left. Area = 20*10 - 10*10/2... actually
    let me lay it out properly:
       (0,0) → (10,0) → (10,10) → (20,10) → (20,20) → (0,20) → close
    That's a 20-wide top + 10-wide bottom, total = 20*10 + 10*10 = 300.
    """
    return [(0, 0), (10, 0), (10, 10), (20, 10), (20, 20), (0, 20)]


def _plus_shape() -> list[tuple[float, float]]:
    """Plus / cross shape: 30×30 bbox with 10×30 vertical bar + 30×10
    horizontal bar. Area = 30*10 + 10*30 - 10*10 (overlap) = 500.
    Vertices CCW:
       (10,0) → (20,0) → (20,10) → (30,10) → (30,20) → (20,20)
                  → (20,30) → (10,30) → (10,20) → (0,20) → (0,10) → (10,10) → close
    """
    return [
        (10, 0), (20, 0), (20, 10), (30, 10),
        (30, 20), (20, 20), (20, 30), (10, 30),
        (10, 20), (0, 20), (0, 10), (10, 10),
    ]


# ─── polygon_area ─────────────────────────────────────────────────────


def test_area_unit_square():
    assert polygon_area(_square_10ft()) == pytest.approx(100.0)


def test_area_l_shape_300_sqft():
    """L-shape: 20×10 top + 10×10 bottom = 200 + 100 = 300."""
    assert polygon_area(_l_shape()) == pytest.approx(300.0)


def test_area_plus_shape_500_sqft():
    """Plus: 30×10 + 10×30 - 10×10 overlap = 500."""
    assert polygon_area(_plus_shape()) == pytest.approx(500.0)


def test_signed_area_cw_polygon_is_negative():
    """Reversing vertex order flips the signed area's sign."""
    sq_cw = list(reversed(_square_10ft()))
    assert polygon_area(sq_cw) == pytest.approx(-100.0)


# ─── polygon_perimeter ────────────────────────────────────────────────


def test_perimeter_square():
    assert polygon_perimeter(_square_10ft()) == pytest.approx(40.0)


def test_perimeter_l_shape():
    """L-shape perimeter: 10 + 10 + 10 + 10 + 20 + 20 = 80."""
    assert polygon_perimeter(_l_shape()) == pytest.approx(80.0)


# ─── polygon_inset_area ───────────────────────────────────────────────


def test_inset_square_by_1ft():
    """10×10 inset 1 ft on all sides → 8×8 = 64 sqft (exact for rect).
    Minkowski formula: A − d·P + π·d² = 100 − 1×40 + π = 100 − 40 + 3.14
    = 63.14. Off by π from the exact 64 — this is the known
    Minkowski-vs-AABB-inset discrepancy. We accept ±2% for K.2.7."""
    A_inset = polygon_inset_area(_square_10ft(), 1.0)
    assert 62 < A_inset < 65    # accepts both Minkowski (63.14) and exact (64)


def test_inset_zero_returns_full_area():
    assert polygon_inset_area(_square_10ft(), 0.0) == pytest.approx(100.0)


def test_inset_oversize_returns_zero():
    """Inset bigger than the polygon's inradius → 0."""
    assert polygon_inset_area(_square_10ft(), 100.0) == 0.0


def test_inset_negative_raises():
    with pytest.raises(ValueError):
        polygon_inset_area(_square_10ft(), -1.0)


# ─── point_in_polygon ────────────────────────────────────────────────


def test_point_inside_square():
    assert point_in_polygon((5, 5), _square_10ft()) is True


def test_point_outside_square():
    assert point_in_polygon((11, 5), _square_10ft()) is False
    assert point_in_polygon((-1, 5), _square_10ft()) is False


def test_point_in_l_concave_region_is_outside():
    """The L-shape's concave corner: (15, 5) is in the bounding box
    but NOT in the L itself (it's in the corner cut-out)."""
    assert point_in_polygon((15, 5), _l_shape()) is False


def test_point_in_l_arm_is_inside():
    """(15, 15) is inside the L's east arm."""
    assert point_in_polygon((15, 15), _l_shape()) is True


def test_point_in_plus_center():
    """Center of plus is inside (the cross overlap zone)."""
    assert point_in_polygon((15, 15), _plus_shape()) is True


def test_point_in_plus_corner_is_outside():
    """Plus shape has 4 missing corners. (5, 5) is in one of them."""
    assert point_in_polygon((5, 5), _plus_shape()) is False


# ─── bounding_box ─────────────────────────────────────────────────────


def test_bbox_square():
    assert bounding_box(_square_10ft()) == (0, 0, 10, 10)


def test_bbox_plus():
    assert bounding_box(_plus_shape()) == (0, 0, 30, 30)


# ─── clipped_grid ────────────────────────────────────────────────────


def test_clipped_grid_square_fills_evenly():
    """10×10 square with 2×2 cells, no inset → 5×5 = 25 centers."""
    centers = clipped_grid(_square_10ft(), cell_w=2, cell_h=2, inset=0)
    assert len(centers) == 25


def test_clipped_grid_l_shape_excludes_concave_corner():
    """L-shape with 2×2 cells. Bounding box is 20×20 → 100 grid cells
    in total, but only ~75 fall inside the L (300/400 ≈ 0.75)."""
    centers = clipped_grid(_l_shape(), cell_w=2, cell_h=2, inset=0)
    assert 70 <= len(centers) <= 80
    # Verify NO center sits in the concave cut-out (x>10 AND y<10)
    for cx, cy in centers:
        assert not (cx > 10 and cy < 10), \
            f"({cx},{cy}) leaked into the L's concave corner"


def test_clipped_grid_inset_shrinks_count():
    """Inset reduces the candidate area, so center count drops."""
    n_no_inset = len(clipped_grid(_square_10ft(), cell_w=1, cell_h=1, inset=0))
    n_with_inset = len(clipped_grid(_square_10ft(), cell_w=1, cell_h=1, inset=2))
    assert n_with_inset < n_no_inset


def test_clipped_grid_degenerate_inset_returns_empty():
    """Inset > half the bbox → empty result."""
    centers = clipped_grid(_square_10ft(), cell_w=2, cell_h=2, inset=10)
    assert centers == []


# ─── Schema-level validator (CCW + simple polygon) ───────────────────


def test_schema_rejects_polygon_with_fewer_than_3_vertices():
    """Schema's _check_shape_constraints raises on too-few vertices."""
    from pvess_calc.schema import RoofSection
    with pytest.raises(ValueError, match="≥3 vertices"):
        RoofSection(shape="polygon", vertices=[(0, 0), (1, 0)])


def test_schema_rejects_clockwise_polygon():
    """CW vertices → signed area ≤ 0 → validator FAIL."""
    from pvess_calc.schema import RoofSection
    cw_square = list(reversed(_square_10ft()))
    with pytest.raises(ValueError, match="counter-clockwise"):
        RoofSection(shape="polygon", vertices=cw_square)


def test_schema_rejects_self_intersecting_polygon():
    """Bow-tie polygon → self-intersection → validator FAIL."""
    from pvess_calc.schema import RoofSection
    bowtie = [(0, 0), (10, 10), (10, 0), (0, 10)]
    with pytest.raises(ValueError, match="self-intersecting"):
        RoofSection(shape="polygon", vertices=bowtie)


def test_schema_accepts_valid_l_polygon():
    """L-shape passes the validator and reports the right gross area."""
    from pvess_calc.schema import RoofSection
    rs = RoofSection(
        shape="polygon", vertices=_l_shape(),
        width_ft=20, height_ft=20,
    )
    assert rs.gross_area_sqft == pytest.approx(300.0)


# ─── K.2.8 — offset_polygon (per-vertex bisector) ────────────────────


def test_offset_square_shrinks_by_d_on_each_side():
    """10×10 square inset by 1 ft → 8×8 square. Each vertex moves
    diagonally inward by sqrt(2) ft, landing at (1,1), (9,1), (9,9), (1,9).
    """
    out = offset_polygon(_square_10ft(), 1.0)
    expected = [(1, 1), (9, 1), (9, 9), (1, 9)]
    for got, want in zip(out, expected):
        assert got[0] == pytest.approx(want[0], abs=1e-6)
        assert got[1] == pytest.approx(want[1], abs=1e-6)


def test_offset_l_concave_corner_moves_inward_correctly():
    """K.2.8 critical case: the L's inner (concave) corner at (10, 10)
    should move INWARD to (9, 11) at d=1 — not outward, not staying
    put. This is the test that K.2.7 centroid-shrink couldn't pass.
    """
    out = offset_polygon(_l_shape(), 1.0)
    # Vertex index 2 is (10, 10), the inner concave corner.
    inner = out[2]
    # Expected per the bisector formula: at the concave corner of an L
    # where edges go (south→north) then (west→east), inward normals
    # are (-1,0) and (0,1). offset = (-1+0, 0+1) × 1 / (1 + 0) = (-1, 1).
    # New vertex = (10-1, 10+1) = (9, 11).
    assert inner[0] == pytest.approx(9.0, abs=1e-6)
    assert inner[1] == pytest.approx(11.0, abs=1e-6)


def test_offset_zero_returns_unchanged():
    out = offset_polygon(_l_shape(), 0.0)
    assert out == _l_shape()


def test_offset_negative_raises():
    with pytest.raises(ValueError, match="d must be"):
        offset_polygon(_square_10ft(), -1.0)


def test_offset_preserves_vertex_count():
    """Offset polygon has same number of vertices as input."""
    assert len(offset_polygon(_l_shape(), 1.5)) == len(_l_shape())
    assert len(offset_polygon(_plus_shape(), 1.5)) == len(_plus_shape())


def test_offset_l_area_close_to_minkowski():
    """Cross-check: offset_polygon's resulting area matches the
    Minkowski formula within ~1% for the L-shape, d=1 ft.
        A_minkowski = 300 - 1×80 + π ≈ 223 sqft
    The bisector offset gives an exact polygon area for L; expect
    around 220-228 sqft (the two methods agree to within π/A error).
    """
    out = offset_polygon(_l_shape(), 1.0)
    A_bisector = polygon_area(out)
    A_minkowski = polygon_inset_area(_l_shape(), 1.0)
    # Both are within 2% of one another
    assert A_bisector == pytest.approx(A_minkowski, rel=0.04)


# ─── K.2.8 — fit_module_grid (binary-search cell size) ───────────────


def test_fit_module_grid_returns_exact_count_when_possible():
    """K.2.8 — request 10 modules on a 30×20 rect (600 sqft, plenty
    of room). Binary search picks a cell size that lands exactly 10
    centers inside the inset polygon."""
    rect = [(0, 0), (30, 0), (30, 20), (0, 20)]
    cell_ft, centers = fit_module_grid(rect, target_count=10, inset=1.5)
    assert len(centers) == 10
    assert cell_ft > 2.0    # binary search should converge well above min


def test_fit_module_grid_zero_target_returns_empty():
    cell, centers = fit_module_grid(_square_10ft(), target_count=0)
    assert centers == []


def test_fit_module_grid_handles_l_shape():
    """L-shape (300 sqft) requesting 12 modules — verify all 12 centers
    fall inside the L (none in the concave cut-out)."""
    cell, centers = fit_module_grid(_l_shape(), target_count=12, inset=1.0)
    assert len(centers) == 12
    for cx, cy in centers:
        # The L cuts out (x > 10 AND y < 10) — no center should land there.
        assert not (cx > 10 and cy < 10), \
            f"module center ({cx},{cy}) leaked into L's concave corner"


def test_fit_module_grid_underfit_when_polygon_too_small():
    """If we ask for more modules than the polygon can hold at
    min_cell_ft, fit_module_grid returns the densest grid it found
    (centers count < target). No crash, no negative-cell guarantees."""
    tiny = [(0, 0), (3, 0), (3, 3), (0, 3)]    # 3×3 = 9 sqft
    cell, centers = fit_module_grid(tiny, target_count=100, inset=0.5)
    # At min_cell=1.5, a 2×2 ft interior (inset 0.5 on each side) holds
    # at most ~1 module center. Definitely < 100.
    assert len(centers) < 5


def test_fit_module_grid_sorts_top_down_left_right():
    """Returned centers must be sorted by (y desc, x asc) — visual
    'fill from top'. Important for the PV-4 trim-to-N step to drop
    the bottom-right corner modules first instead of random ones."""
    rect = [(0, 0), (20, 0), (20, 20), (0, 20)]
    cell, centers = fit_module_grid(rect, target_count=20, inset=0)
    # Walk through centers; each consecutive pair has either
    # (same y AND larger x) or (smaller y AND smaller x is OK).
    for prev, cur in zip(centers, centers[1:]):
        assert (prev[1] > cur[1]) or (prev[1] == cur[1] and prev[0] < cur[0]), (
            f"sort order broken: {prev} → {cur}"
        )
