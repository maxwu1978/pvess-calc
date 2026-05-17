"""Stage B — auto-anchor for RoofSections without explicit anchors.

Locks the heuristic in `calc/site_layout.py::auto_anchor_sections` so
legacy yamls (no `site_anchor_x_ft`) get sensible per-face placements
on the EE-4 site plan.
"""
from __future__ import annotations

import pytest

from pvess_calc.calc.site_layout import (
    apply_auto_anchors,
    auto_anchor_sections,
    house_bbox,
)
from pvess_calc.schema import RoofSection, Site


# ─── house_bbox ────────────────────────────────────────────────────────


def test_house_bbox_rect_centered_in_lot():
    """No polygon outline → centered rect inside the lot."""
    site = Site(lot_width_ft=80, lot_depth_ft=120,
                house_width_ft=50, house_depth_ft=35)
    x0, y0, x1, y1 = house_bbox(site)
    assert (x0, y0) == (15.0, 42.5)
    assert (x1, y1) == (65.0, 77.5)


def test_house_bbox_polygon_uses_minmax():
    """L-shaped polygon → bbox = (min x, min y, max x, max y) of verts."""
    site = Site(
        lot_width_ft=80, lot_depth_ft=120,
        house_outline_vertices=[
            (10.0, 30.0), (60.0, 30.0),
            (60.0, 55.0), (40.0, 55.0),
            (40.0, 80.0), (10.0, 80.0),
        ],
    )
    assert house_bbox(site) == (10.0, 30.0, 60.0, 80.0)


# ─── _classify_orientation (private but worth locking) ───────────────────


def test_orientation_buckets_at_quadrant_centers():
    """North / east / south / west azimuth centers each land in their
    own bucket. The function gates which wall each face gets anchored
    against."""
    from pvess_calc.calc.site_layout import _classify_orientation
    assert _classify_orientation(0) == "north"
    assert _classify_orientation(90) == "east"
    assert _classify_orientation(180) == "south"
    assert _classify_orientation(270) == "west"


def test_orientation_handles_wraparound():
    """Azimuth ≥ 360 or negative wraps via % 360."""
    from pvess_calc.calc.site_layout import _classify_orientation
    assert _classify_orientation(360) == "north"
    assert _classify_orientation(450) == "east"
    assert _classify_orientation(-90) == "west"


# ─── auto_anchor_sections — single-face cases ────────────────────────────


def test_single_south_face_anchored_on_south_wall():
    """One south-facing face → anchor at SW corner of house, az=0
    (eave runs east, ridge to north)."""
    site = Site(
        lot_width_ft=80, lot_depth_ft=120,
        house_width_ft=50, house_depth_ft=35,
        roof_sections=[
            RoofSection(name="South", azimuth_deg=180,
                        width_ft=24, height_ft=16),
        ],
    )
    anchors = auto_anchor_sections(site)
    assert "South" in anchors
    x, y, az = anchors["South"]
    assert (x, y) == (15.0, 42.5)   # SW of centered 50×35 house
    assert az == 0.0


def test_single_west_face_anchored_on_west_wall():
    site = Site(
        lot_width_ft=80, lot_depth_ft=120,
        house_width_ft=50, house_depth_ft=35,
        roof_sections=[
            RoofSection(name="West", azimuth_deg=270,
                        width_ft=24, height_ft=16),
        ],
    )
    anchors = auto_anchor_sections(site)
    x, y, az = anchors["West"]
    assert (x, y) == (15.0, 77.5)   # NW corner
    assert az == 270.0


def test_single_east_face_anchored_on_east_wall():
    site = Site(
        lot_width_ft=80, lot_depth_ft=120,
        house_width_ft=50, house_depth_ft=35,
        roof_sections=[
            RoofSection(name="East", azimuth_deg=90,
                        width_ft=24, height_ft=16),
        ],
    )
    anchors = auto_anchor_sections(site)
    x, y, az = anchors["East"]
    assert (x, y) == (65.0, 42.5)   # SE corner
    assert az == 90.0


def test_single_north_face_anchored_on_north_wall():
    site = Site(
        lot_width_ft=80, lot_depth_ft=120,
        house_width_ft=50, house_depth_ft=35,
        roof_sections=[
            RoofSection(name="North", azimuth_deg=0,
                        width_ft=24, height_ft=16),
        ],
    )
    anchors = auto_anchor_sections(site)
    x, y, az = anchors["North"]
    assert (x, y) == (65.0, 77.5)   # NE corner
    assert az == 180.0


# ─── auto_anchor_sections — multi-face stacking ──────────────────────────


def test_multiple_south_faces_stack_along_south_wall():
    """Two south faces should stack east of each other with a 1 ft gap."""
    site = Site(
        lot_width_ft=80, lot_depth_ft=120,
        house_width_ft=50, house_depth_ft=35,
        roof_sections=[
            RoofSection(name="S1", azimuth_deg=180, width_ft=20, height_ft=16),
            RoofSection(name="S2", azimuth_deg=180, width_ft=15, height_ft=10),
        ],
    )
    anchors = auto_anchor_sections(site)
    x1, y1, _ = anchors["S1"]
    x2, y2, _ = anchors["S2"]
    assert (x1, y1) == (15.0, 42.5)
    assert (x2, y2) == (15.0 + 20 + 1.0, 42.5)   # +width +gap


def test_multiple_west_faces_stack_along_west_wall():
    """Two west faces stack going south (cursor moves -y)."""
    site = Site(
        lot_width_ft=80, lot_depth_ft=120,
        house_width_ft=50, house_depth_ft=35,
        roof_sections=[
            RoofSection(name="W1", azimuth_deg=270, width_ft=15, height_ft=10),
            RoofSection(name="W2", azimuth_deg=270, width_ft=12, height_ft=10),
        ],
    )
    anchors = auto_anchor_sections(site)
    x1, y1, _ = anchors["W1"]
    x2, y2, _ = anchors["W2"]
    assert (x1, y1) == (15.0, 77.5)
    assert (x2, y2) == (15.0, 77.5 - 15 - 1.0)


def test_mixed_orientations_no_collision():
    """3 South + 2 West (Frisco-style) → all anchors within or adjacent
    to the house bbox. Sections on different walls don't share cursor
    state."""
    site = Site(
        lot_width_ft=90, lot_depth_ft=125,
        house_width_ft=60, house_depth_ft=42,
        roof_sections=[
            RoofSection(name="S1", azimuth_deg=180, width_ft=25, height_ft=20),
            RoofSection(name="S2", azimuth_deg=180, width_ft=18, height_ft=15),
            RoofSection(name="W1", azimuth_deg=270, width_ft=15, height_ft=10),
            RoofSection(name="W2", azimuth_deg=270, width_ft=10, height_ft=8),
            RoofSection(name="S3", azimuth_deg=180, width_ft=12, height_ft=10),
        ],
    )
    anchors = auto_anchor_sections(site)
    assert len(anchors) == 5
    # House centered in lot: (90-60)/2 = 15 west wall; (125-42)/2 = 41.5 south wall
    s_anchors = [anchors[n] for n in ("S1", "S2", "S3")]
    w_anchors = [anchors[n] for n in ("W1", "W2")]
    assert all(a[1] == 41.5 for a in s_anchors)   # south wall y
    assert all(a[0] == 15.0 for a in w_anchors)   # west wall x


# ─── auto_anchor_sections — explicit anchors pass-through ────────────────


def test_explicit_anchor_not_overwritten():
    """A section with site_anchor_x_ft already set is OMITTED from
    the auto-anchor result entirely."""
    site = Site(
        lot_width_ft=80, lot_depth_ft=120,
        house_width_ft=50, house_depth_ft=35,
        roof_sections=[
            RoofSection(name="Explicit", azimuth_deg=180,
                        width_ft=24, height_ft=16,
                        site_anchor_x_ft=20.0,
                        site_anchor_y_ft=40.0,
                        site_anchor_azimuth_deg=10.0),
            RoofSection(name="Auto", azimuth_deg=270,
                        width_ft=20, height_ft=12),
        ],
    )
    anchors = auto_anchor_sections(site)
    assert "Explicit" not in anchors
    assert "Auto" in anchors


# ─── apply_auto_anchors ──────────────────────────────────────────────────


def test_apply_auto_anchors_does_not_mutate_input():
    """apply_auto_anchors must return a fresh Site; the input is
    untouched."""
    site = Site(
        lot_width_ft=80, lot_depth_ft=120,
        house_width_ft=50, house_depth_ft=35,
        roof_sections=[
            RoofSection(name="South", azimuth_deg=180,
                        width_ft=24, height_ft=16),
        ],
    )
    assert site.roof_sections[0].site_anchor_x_ft is None
    anchors = auto_anchor_sections(site)
    patched = apply_auto_anchors(site, anchors)
    assert site.roof_sections[0].site_anchor_x_ft is None     # untouched
    assert patched.roof_sections[0].site_anchor_x_ft == 15.0  # patched


def test_apply_auto_anchors_preserves_explicit():
    """apply_auto_anchors leaves explicit anchors alone."""
    site = Site(
        lot_width_ft=80, lot_depth_ft=120,
        house_width_ft=50, house_depth_ft=35,
        roof_sections=[
            RoofSection(name="A", azimuth_deg=180,
                        width_ft=24, height_ft=16,
                        site_anchor_x_ft=99.0,
                        site_anchor_y_ft=99.0,
                        site_anchor_azimuth_deg=99.0),
        ],
    )
    anchors = auto_anchor_sections(site)
    assert anchors == {}
    patched = apply_auto_anchors(site, anchors)
    assert patched.roof_sections[0].site_anchor_x_ft == 99.0


# ─── Determinism / engine integration ───────────────────────────────────


def test_auto_anchor_deterministic():
    """Same input → same anchors. Order-stable iteration."""
    def make_site() -> Site:
        return Site(
            lot_width_ft=80, lot_depth_ft=120,
            roof_sections=[
                RoofSection(name="A", azimuth_deg=180, width_ft=15, height_ft=10),
                RoofSection(name="B", azimuth_deg=270, width_ft=15, height_ft=10),
                RoofSection(name="C", azimuth_deg=180, width_ft=15, height_ft=10),
            ],
        )
    a1 = auto_anchor_sections(make_site())
    a2 = auto_anchor_sections(make_site())
    assert a1 == a2


def test_engine_run_patches_anchors_for_legacy_phoenix():
    """End-to-end: legacy Phoenix yaml (no site_anchor) round-trips
    through engine.run() and the resulting CalculationResult sees
    fully-anchored sections."""
    from pathlib import Path
    from pvess_calc.calc.engine import run
    from pvess_calc.schema import Inputs
    project = (Path(__file__).resolve().parents[1] / "projects"
               / "002-phoenix-25kw" / "inputs.yaml")
    inputs = Inputs.from_yaml(project)
    for s in inputs.site.roof_sections:
        assert s.site_anchor_x_ft is None
    result = run(inputs)
    for s in result.inputs.site.roof_sections:
        assert s.site_anchor_x_ft is not None
        assert s.site_anchor_y_ft is not None


def test_engine_run_does_not_touch_explicit_anchors():
    """Explicit anchors from yaml survive engine.run() intact."""
    from pathlib import Path
    from pvess_calc.calc.engine import run
    from pvess_calc.schema import Inputs
    project = (Path(__file__).resolve().parents[1] / "projects"
               / "003-frisco-glasshouse" / "inputs.yaml")
    inputs = Inputs.from_yaml(project)
    # Frisco has explicit anchors via Stage A yaml edit
    pre = [(s.name, s.site_anchor_x_ft, s.site_anchor_y_ft)
           for s in inputs.site.roof_sections]
    result = run(inputs)
    post = [(s.name, s.site_anchor_x_ft, s.site_anchor_y_ft)
            for s in result.inputs.site.roof_sections]
    assert pre == post
