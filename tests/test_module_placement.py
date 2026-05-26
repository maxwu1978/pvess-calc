"""K.9.1 — module placement algorithm tests.

Five layers of coverage:
  1. **Empty / boundary** — target_count=0, degenerate sections, too-small
     faces, obstruction-covered faces all return [].
  2. **Rect placement** — modules respect edge setbacks, count is correct.
  3. **Orientation choice** — algorithm picks the orientation that fits
     MORE modules; ties prefer landscape.
  4. **Obstruction avoidance** — no module straddles an obstruction halo.
  5. **Conservation + ordering** — instances are sorted ridge → eave,
     truncated to target_count.
"""
from __future__ import annotations

import pytest

from pvess_calc.calc.geometry import (
    polygon_covers_polygon,
    polygons_overlap_area,
    rectangle_vertices,
    usable_inset_polygon,
)
from pvess_calc.calc.module_placement import ModuleInstance, place_modules
from pvess_calc.schema import EdgeSetback, RoofObstruction, RoofSection


# ─── Boundary / empty cases ─────────────────────────────────────────────


def test_place_modules_target_zero_returns_empty():
    """`target_count = 0` short-circuits to empty list — no grid work."""
    s = RoofSection(name="X", shape="rect", width_ft=20, height_ft=20,
                    module_count=0)
    assert place_modules(s) == []


def test_place_modules_uses_section_module_count_when_target_omitted():
    """When `target_count` kwarg is None, falls back to
    `section.module_count`. Lets engine call `place_modules(section)`
    directly without restating the count."""
    s = RoofSection(name="X", shape="rect", width_ft=25, height_ft=25,
                    module_count=8)
    placed = place_modules(s)
    assert len(placed) == 8


def test_place_modules_returns_empty_when_section_smaller_than_module():
    """A 4×4 ft face can't fit a 5.65×3.72 ft module — return []."""
    s = RoofSection(name="Tiny", shape="rect", width_ft=4, height_ft=4,
                    module_count=10)
    assert place_modules(s) == []


def test_place_modules_returns_empty_when_setbacks_consume_face():
    """If setback > half the dimension, no usable area → []."""
    s = RoofSection(name="OverSetback", shape="rect",
                    width_ft=5, height_ft=5,
                    default_setback_ft=3.0,    # > half of 5
                    module_count=10)
    assert place_modules(s) == []


def test_place_modules_returns_empty_when_polygon_has_no_vertices():
    """Pre-K.2.7 yaml: shape='polygon' but vertices=[] → safe empty."""
    s = RoofSection(name="P", shape="rect", width_ft=20, height_ft=20,
                    module_count=4)
    # Force shape to polygon without vertices via model_copy
    bad = s.model_copy(update={"shape": "rect"})   # keep rect for control
    assert len(place_modules(bad)) == 4
    # Now demonstrate polygon-without-verts is empty by direct ctor
    # (pydantic validator rejects polygon w/ < 3 vertices, so we use
    # model_construct to bypass for this test)
    poly = RoofSection.model_construct(
        name="EmptyPoly", shape="polygon", width_ft=20, height_ft=20,
        vertices=[], module_count=4, pitch_deg=22, azimuth_deg=180,
        default_setback_ft=1.5, edge_setbacks=[], obstructions=[],
        apex_x_ratio=0.5, attachment_count=0,
        roof_type="Comp Shingle", shading_factor=1.0,
        obstructions_note="",
    )
    assert place_modules(poly) == []


# ─── Rect placement math ────────────────────────────────────────────────


def test_place_modules_respects_default_setback_inset():
    """No module should be placed within `default_setback_ft` of the
    face boundary. Verify by checking every instance's bounding box
    stays inside the inset rectangle."""
    s = RoofSection(name="Test", shape="rect",
                    width_ft=20, height_ft=15,
                    default_setback_ft=1.5,
                    module_count=20)
    placed = place_modules(s)
    for m in placed:
        # Module's footprint must stay inside the 1.5-ft inset rect
        assert m.x_ft >= 1.5 - 1e-6, f"module x={m.x_ft} crosses left setback"
        assert m.y_ft >= 1.5 - 1e-6, f"module y={m.y_ft} crosses eave setback"
        assert m.x_ft + m.width_ft <= 20 - 1.5 + 1e-6
        assert m.y_ft + m.height_ft <= 15 - 1.5 + 1e-6


def test_place_modules_honors_per_edge_setback():
    """Per-edge setbacks (K.2.6c) win over default. Bigger eave setback
    → no modules in the bottom strip."""
    s = RoofSection(name="EaveBig", shape="rect",
                    width_ft=25, height_ft=20,
                    default_setback_ft=1.5,
                    edge_setbacks=[EdgeSetback(edge_type="eave",
                                               setback_ft=5.0)],
                    module_count=20)
    placed = place_modules(s)
    # Every module's y must be ≥ 5.0 (eave setback)
    for m in placed:
        assert m.y_ft >= 5.0 - 1e-6, (
            f"module y={m.y_ft} crosses 5-ft eave setback"
        )


# ─── Orientation choice ────────────────────────────────────────────────


def test_place_modules_picks_orientation_with_more_capacity():
    """A 20×6 ft narrow face: landscape (5.65 wide × 3.72 tall) fits
    one row of 3-4; portrait (3.72 wide × 5.65 tall) doesn't even
    fit one row in the 6-ft direction after setbacks. Landscape wins."""
    s = RoofSection(name="Strip", shape="rect",
                    width_ft=22, height_ft=6,
                    default_setback_ft=0.5,   # generous to fit more
                    module_count=4)
    placed = place_modules(s)
    assert len(placed) >= 3, "narrow face should fit ≥3 landscape modules"
    # All should be landscape (rotation 90)
    for m in placed:
        assert m.rotation_deg == 90, (
            f"narrow face should pick landscape, got rotation={m.rotation_deg}"
        )


def test_place_modules_landscape_is_horizontal_orientation():
    """Landscape: width (along eave) > height (eave-to-ridge).
    Portrait: width < height. Visual sanity for PV-4 renderer."""
    s = RoofSection(name="Big", shape="rect",
                    width_ft=25, height_ft=25,
                    module_count=8)
    placed = place_modules(s)
    assert placed
    # Whatever orientation was picked, dimensions reflect the rotation
    for m in placed:
        if m.rotation_deg == 0:    # portrait
            assert m.width_ft < m.height_ft
        elif m.rotation_deg == 90: # landscape
            assert m.width_ft > m.height_ft


# ─── Obstruction avoidance ─────────────────────────────────────────────


def test_place_modules_avoids_obstruction_halo():
    """A chimney in the middle of the roof: no module's bounding box
    may intersect the halo (chimney + setback)."""
    chimney = RoofObstruction(
        kind="chimney", x_ft=10, y_ft=10,
        width_ft=2, height_ft=2, setback_ft=1.5,
    )
    s = RoofSection(name="WithChimney", shape="rect",
                    width_ft=25, height_ft=25,
                    obstructions=[chimney],
                    module_count=20)
    placed = place_modules(s)
    # Halo: (10-1.5, 10-1.5) to (10+2+1.5, 10+2+1.5) = (8.5, 8.5) to (13.5, 13.5)
    for m in placed:
        m_x1 = m.x_ft + m.width_ft
        m_y1 = m.y_ft + m.height_ft
        # No intersection with halo bbox
        if m_x1 > 8.5 and m.x_ft < 13.5 and m_y1 > 8.5 and m.y_ft < 13.5:
            pytest.fail(
                f"module ({m.x_ft:.2f}, {m.y_ft:.2f}, "
                f"{m.width_ft:.2f}x{m.height_ft:.2f}) overlaps chimney halo"
            )


def test_place_modules_full_footprint_stays_inside_l_polygon():
    """OSR1: polygon placement must validate the entire module rectangle,
    not only the center point. This catches modules that visually hang over
    the L-shaped concave cut-out."""
    l_shape = [(0, 0), (10, 0), (10, 10), (20, 10), (20, 20), (0, 20)]
    s = RoofSection(
        name="L Roof",
        shape="polygon",
        vertices=l_shape,
        width_ft=20,
        height_ft=20,
        default_setback_ft=1.0,
        module_count=30,
    )
    placed = place_modules(
        s,
        module_length_in=48.0,
        module_width_in=30.0,
        target_count=30,
    )
    assert placed
    usable = usable_inset_polygon(l_shape, 1.0)
    cutout = [(10, 0), (20, 0), (20, 10), (10, 10)]
    for module in placed:
        footprint = rectangle_vertices(
            module.x_ft,
            module.y_ft,
            module.width_ft,
            module.height_ft,
        )
        assert polygon_covers_polygon(usable, footprint)
        assert not polygons_overlap_area(footprint, cutout)


def test_place_modules_full_footprints_do_not_overlap_each_other():
    """Grid offsets may change during optimization, but the emitted module
    rectangles must remain collision-free."""
    s = RoofSection(
        name="Dense Rect",
        shape="rect",
        width_ft=32,
        height_ft=24,
        default_setback_ft=1.0,
        module_count=40,
    )
    placed = place_modules(
        s,
        module_length_in=48.0,
        module_width_in=30.0,
        target_count=40,
    )
    assert len(placed) > 10
    footprints = [
        rectangle_vertices(m.x_ft, m.y_ft, m.width_ft, m.height_ft)
        for m in placed
    ]
    for i, a in enumerate(footprints):
        for b in footprints[i + 1:]:
            assert not polygons_overlap_area(a, b)


def test_place_modules_falls_back_when_obstruction_covers_face():
    """If an obstruction halo covers the entire usable area, no modules
    can be placed → empty list (not a crash)."""
    big_obstacle = RoofObstruction(
        kind="hvac_unit", x_ft=0, y_ft=0,
        width_ft=100, height_ft=100, setback_ft=2.0,    # covers everything
    )
    s = RoofSection(name="Covered", shape="rect",
                    width_ft=25, height_ft=25,
                    obstructions=[big_obstacle],
                    module_count=10)
    placed = place_modules(s)
    assert placed == []


# ─── Conservation + ordering ───────────────────────────────────────────


def test_place_modules_truncates_to_target_count():
    """A 25×25 face could fit 20+ modules; if target=5 the list is
    truncated to exactly 5 (not 20)."""
    s = RoofSection(name="Big", shape="rect",
                    width_ft=25, height_ft=25,
                    module_count=5)
    placed = place_modules(s)
    assert len(placed) == 5


def test_place_modules_first_modules_are_near_the_ridge():
    """Sort order: ridge → eave (top-down). The first module in the
    list should have the LARGEST y (closest to ridge), since the K.8.1
    truncation `[:target_count]` keeps the best spots."""
    s = RoofSection(name="Test", shape="rect",
                    width_ft=25, height_ft=25,
                    module_count=4)
    placed = place_modules(s, target_count=20)   # get all candidates
    # First module y should be ≥ last module y
    assert placed[0].y_ft >= placed[-1].y_ft, (
        f"first y={placed[0].y_ft}, last y={placed[-1].y_ft}; "
        "ridge-first sort broken"
    )


def test_module_instance_is_frozen_dataclass():
    """Closing standard: `ModuleInstance` is immutable. Prevents
    downstream code from accidentally mutating a placement after the
    engine has computed it (e.g., shifting x_ft for "alignment fix")."""
    m = ModuleInstance(face_name="X", x_ft=1.0, y_ft=2.0,
                       width_ft=3.0, height_ft=4.0, rotation_deg=0.0)
    with pytest.raises(Exception):    # FrozenInstanceError
        m.x_ft = 99.0


# ─── Triangle support (basic) ───────────────────────────────────────────


def test_place_modules_triangle_face_partial_fill():
    """Tri faces (hip roof): inset-polygon path. Should place fewer
    modules than the equivalent rect of same bbox. Sanity check that
    tri code path doesn't crash + returns a reasonable count."""
    s = RoofSection(name="HipTri", shape="tri",
                    width_ft=28, height_ft=14,
                    apex_x_ratio=0.5,
                    module_count=20)
    placed = place_modules(s)
    # Tri has half the area of bbox rect → fewer modules. Some plausible
    # range — just verify "some placed, not zero, not impossibly many".
    assert 2 <= len(placed) <= 12, (
        f"tri face placement: got {len(placed)} modules, expected 2-12"
    )


# ─── K.9.2 — engine integration ────────────────────────────────────────


def test_engine_run_populates_module_placements_for_phoenix():
    """Phoenix has 2 faces with explicit module_count=30 each.
    `engine.run()` must call place_modules for each → `module_placements`
    dict keyed by section.name, each value is a list of ModuleInstance."""
    from pathlib import Path
    from pvess_calc.calc.engine import run
    from pvess_calc.schema import Inputs

    project_root = Path(__file__).resolve().parents[1]
    phoenix_yaml = project_root / "projects" / "002-phoenix-25kw" / "inputs.yaml"
    result = run(Inputs.from_yaml(phoenix_yaml))

    assert "South Roof" in result.module_placements
    assert "West Roof" in result.module_placements
    south = result.module_placements["South Roof"]
    west = result.module_placements["West Roof"]
    # Phoenix has 30 modules per face; placement may be capped by
    # geometry but should be > 20 each (the 38×24 ft faces fit ~30).
    assert len(south) >= 20
    assert len(west) >= 20
    # Each entry is a ModuleInstance
    for m in south:
        assert isinstance(m, ModuleInstance)
        assert m.face_name == "South Roof"


def test_engine_run_empty_placements_for_austin_legacy_yaml():
    """Austin demo predates K.2.6c roof_sections — no per-face data
    → empty module_placements dict. Legacy yaml path unchanged."""
    from pathlib import Path
    from pvess_calc.calc.engine import run
    from pvess_calc.schema import Inputs

    project_root = Path(__file__).resolve().parents[1]
    austin_yaml = project_root / "projects" / "001-demo-austin" / "inputs.yaml"
    result = run(Inputs.from_yaml(austin_yaml))
    assert result.module_placements == {}


def test_engine_run_uses_face_distribution_for_k3c_init_state():
    """K.9.2 closing contract: when roof_sections have all module_count=0
    (K.3c init state), the engine runs the LRM auto-distribute internally so
    PV-4 has counts to draw.
    Without this, K.3c-init projects would have empty placements
    (the original 2026-05-17 engine bug)."""
    from pathlib import Path
    from pvess_calc.calc.engine import run
    from pvess_calc.schema import Inputs

    project_root = Path(__file__).resolve().parents[1]
    frisco_yaml = project_root / "projects" / "003-frisco-glasshouse" / "inputs.yaml"
    inputs = Inputs.from_yaml(frisco_yaml)
    zero_sections = [
        s.model_copy(update={"module_count": 0})
        for s in inputs.site.roof_sections
    ]
    inputs = inputs.model_copy(
        update={"site": inputs.site.model_copy(update={"roof_sections": zero_sections})}
    )
    # The copied Frisco geometry mimics the K.3c init state.
    assert all(s.module_count == 0 for s in inputs.site.roof_sections)
    result = run(inputs)
    # K.9.2 must have populated placements via the LRM auto-distribute
    total_placed = sum(len(m) for m in result.module_placements.values())
    assert total_placed > 0
    # Capacity-aware placement recycles modules that LRM assigned to tiny
    # faces into larger faces with spare capacity, so the drawing should hit
    # the declared module target whenever total roof capacity allows it.
    assert total_placed == inputs.pv_array.modules


def test_engine_module_selection_prioritizes_good_faces_and_avoids_overlap():
    """R4: if CAD facets overlap, the module selector must not draw two
    panels into the same physical roof area. Shortfall should be recycled
    into higher-value faces before using a north-facing face."""
    from pvess_calc.calc.engine import run
    from pvess_calc.calc.wire_routing import _face_local_to_site
    from tests.conftest import make_inputs

    inputs = make_inputs(modules=6, strings=1)
    inputs.site.roof_sections = [
        RoofSection(
            name="SW Face",
            shape="rect",
            width_ft=32,
            height_ft=20,
            azimuth_deg=225,
            module_count=3,
            site_anchor_x_ft=0,
            site_anchor_y_ft=0,
        ),
        RoofSection(
            name="North Face",
            shape="rect",
            width_ft=32,
            height_ft=20,
            azimuth_deg=0,
            module_count=3,
            site_anchor_x_ft=0,
            site_anchor_y_ft=0,
        ),
    ]

    result = run(inputs)

    assert len(result.module_placements.get("SW Face", [])) == 6
    assert result.module_placements.get("North Face", []) in (None, [])
    footprints = []
    for section in result.inputs.site.roof_sections:
        for module in result.module_placements.get(section.name, []):
            local = [
                (module.x_ft, module.y_ft),
                (module.x_ft + module.width_ft, module.y_ft),
                (module.x_ft + module.width_ft, module.y_ft + module.height_ft),
                (module.x_ft, module.y_ft + module.height_ft),
            ]
            site = [_face_local_to_site(section, x, y) for x, y in local]
            footprint = [pt for pt in site if pt is not None]
            for existing in footprints:
                assert not polygons_overlap_area(footprint, existing)
            footprints.append(footprint)
