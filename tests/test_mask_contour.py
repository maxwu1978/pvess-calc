"""Stage 7 — Google Solar mask → review contour geometry."""
from __future__ import annotations

import numpy as np
import pytest

from pvess_calc.calc.mask_contour import (
    contour_from_mask,
    fit_candidate_to_bbox,
    transform_candidate,
)


def test_rect_mask_extracts_four_vertex_site_polygon():
    mask = np.zeros((100, 100), dtype=bool)
    mask[30:70, 35:65] = True

    c = contour_from_mask(
        mask,
        radius_m=15.24,          # 100 ft full span
        center_site_ft=(50.0, 50.0),
        simplify_ft=0.5,
    )

    assert c is not None
    assert c.vertex_count == 4
    # 30 px × 40 px in a 100 ft span = 30 ft × 40 ft.
    assert c.area_sqft == pytest.approx(1200.0, rel=0.03)
    xs = [p[0] for p in c.site_vertices_ft]
    ys = [p[1] for p in c.site_vertices_ft]
    assert min(xs) == pytest.approx(35.0, abs=0.4)
    assert max(xs) == pytest.approx(65.0, abs=0.4)
    assert min(ys) == pytest.approx(30.0, abs=0.4)
    assert max(ys) == pytest.approx(70.0, abs=0.4)


def test_l_shape_mask_preserves_concave_review_outline():
    mask = np.zeros((80, 80), dtype=bool)
    mask[20:60, 20:38] = True
    mask[42:60, 20:62] = True

    c = contour_from_mask(
        mask,
        radius_m=12.192,         # 80 ft full span
        center_site_ft=(40.0, 40.0),
        simplify_ft=0.25,
    )

    assert c is not None
    assert c.vertex_count >= 6
    # Area = vertical 40*18 + horizontal 18*42 - overlap 18*18.
    assert c.area_sqft == pytest.approx(1152.0, rel=0.03)


def test_empty_mask_returns_none():
    c = contour_from_mask(
        np.zeros((20, 20), dtype=bool),
        radius_m=10,
        center_site_ft=(0.0, 0.0),
    )
    assert c is None


def test_fit_candidate_to_bbox_calibrates_review_polygon_to_site_frame():
    mask = np.zeros((100, 100), dtype=bool)
    mask[30:70, 35:65] = True
    c = contour_from_mask(
        mask,
        radius_m=15.24,
        center_site_ft=(0.0, 0.0),
        simplify_ft=0.5,
    )

    fitted = fit_candidate_to_bbox(c, (10.0, 20.0, 70.0, 62.0))

    assert fitted is not None
    xs = [p[0] for p in fitted.site_vertices_ft]
    ys = [p[1] for p in fitted.site_vertices_ft]
    assert min(xs) == pytest.approx(10.0)
    assert max(xs) == pytest.approx(70.0)
    assert min(ys) == pytest.approx(20.0)
    assert max(ys) == pytest.approx(62.0)
    assert fitted.area_sqft == pytest.approx(60.0 * 42.0)
    assert "fit_bbox" in fitted.source


def test_transform_candidate_applies_manual_stage8_offsets():
    mask = np.zeros((50, 50), dtype=bool)
    mask[15:35, 20:30] = True
    c = contour_from_mask(
        mask,
        radius_m=7.62,
        center_site_ft=(25.0, 25.0),
        simplify_ft=0.5,
    )
    moved = transform_candidate(
        c,
        origin_ft=(25.0, 25.0),
        scale_x=1.0,
        scale_y=1.0,
        offset_ft=(3.5, -2.0),
        source_suffix="manual",
    )

    before_x = min(p[0] for p in c.site_vertices_ft)
    before_y = min(p[1] for p in c.site_vertices_ft)
    after_x = min(p[0] for p in moved.site_vertices_ft)
    after_y = min(p[1] for p in moved.site_vertices_ft)
    assert after_x - before_x == pytest.approx(3.5)
    assert after_y - before_y == pytest.approx(-2.0)
    assert "manual" in moved.source
