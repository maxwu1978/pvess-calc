"""OSR1 geometry adapter tests."""
from __future__ import annotations

import pytest

from pvess_calc.calc.geometry import (
    polygon_area,
    polygon_bounds,
    polygon_covers_polygon,
    polygons_overlap_area,
    rectangle_vertices,
    usable_inset_polygon,
)


def _l_shape() -> list[tuple[float, float]]:
    return [(0, 0), (10, 0), (10, 10), (20, 10), (20, 20), (0, 20)]


def test_usable_inset_polygon_handles_concave_l_shape():
    """Shapely negative buffer should return a usable concave roof polygon,
    not a bbox approximation or an empty result."""
    inset = usable_inset_polygon(_l_shape(), 1.0)
    assert len(inset) >= 6
    assert polygon_area(inset) == pytest.approx(224.0, rel=0.03)
    assert polygon_bounds(inset) == pytest.approx((1.0, 1.0, 19.0, 19.0))


def test_polygon_covers_polygon_requires_full_footprint():
    l_shape = _l_shape()
    valid = rectangle_vertices(2, 12, 5, 4)
    crossing_cutout = rectangle_vertices(8, 8, 5, 4)
    assert polygon_covers_polygon(l_shape, valid)
    assert not polygon_covers_polygon(l_shape, crossing_cutout)


def test_polygons_overlap_area_ignores_boundary_touch():
    a = rectangle_vertices(0, 0, 4, 4)
    b = rectangle_vertices(4, 0, 4, 4)
    c = rectangle_vertices(3.99, 0, 4, 4)
    assert not polygons_overlap_area(a, b)
    assert polygons_overlap_area(a, c)
