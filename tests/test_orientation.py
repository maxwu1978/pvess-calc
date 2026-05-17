"""K.8 — Sandia orientation derate + density-based shading resolution.

Unit-level checks on `calc/orientation.py`. The table is the source of
truth for any face that isn't due-south at latitude tilt; if its outputs
drift, every per-face production number drifts with it. Lock the
corners, the symmetry, and the bilinear interpolation contract.
"""
from __future__ import annotations

import pytest

from pvess_calc.calc.orientation import (
    DENSITY_DEFAULT_SHADING,
    orientation_derate,
    resolve_shading_factor,
)


# ─── orientation_derate ────────────────────────────────────────────────


def test_orientation_derate_due_south_latitude_tilt_is_one():
    """The reference: 180° azimuth (due south, US convention) at 30°
    tilt is the NREL baseline → derate == 1.00 exactly."""
    assert orientation_derate(180.0, 30.0) == pytest.approx(1.00)


def test_orientation_derate_flat_roof_is_orientation_independent():
    """A truly flat roof (tilt=0°) is orientation-insensitive — every
    azimuth should land on the same 0.89 multiplier."""
    south = orientation_derate(180.0, 0.0)
    east = orientation_derate(90.0, 0.0)
    west = orientation_derate(270.0, 0.0)
    north = orientation_derate(0.0, 0.0)
    assert south == pytest.approx(0.89)
    assert south == east == west == north


def test_orientation_derate_east_and_west_symmetric():
    """Azimuth is symmetric around the south meridian — a 90° east face
    and a 90° west face should produce the same yearly kWh in the model."""
    for tilt in (10.0, 22.0, 30.0, 45.0):
        east = orientation_derate(90.0, tilt)     # 90° offset from south
        west = orientation_derate(270.0, tilt)    # also 90° offset
        assert east == pytest.approx(west, abs=0.001), (
            f"asymmetric at tilt={tilt}: east={east} west={west}"
        )


def test_orientation_derate_north_at_steep_tilt_penalized():
    """A north-facing 40° pitch is the worst residential case — should
    derate well below 0.50. Catches table-row-swap bugs."""
    north_steep = orientation_derate(0.0, 40.0)
    assert north_steep < 0.50
    # And much worse than the same tilt facing south
    south_steep = orientation_derate(180.0, 40.0)
    assert south_steep > 0.95
    assert (south_steep - north_steep) > 0.45


def test_orientation_derate_bilinear_between_known_cells():
    """A 22° tilt south face must fall between the 20° and 30° table
    rows for tilt-0 azimuth. Verifies bilinear math wasn't replaced
    with nearest-neighbour."""
    v20 = orientation_derate(180.0, 20.0)
    v22 = orientation_derate(180.0, 22.0)
    v30 = orientation_derate(180.0, 30.0)
    assert v20 < v22 < v30
    # 22° is 20% of the way from 20° to 30°
    expected = v20 + 0.2 * (v30 - v20)
    assert v22 == pytest.approx(expected, abs=0.001)


def test_orientation_derate_clamps_out_of_range_inputs():
    """Tilts >60° clamp to the 60° row (the steepest residential band
    we support). Azimuths normalize to the [0, 180] offset window."""
    assert orientation_derate(180.0, 90.0) == orientation_derate(180.0, 60.0)
    # 540° azimuth == 180° azimuth (after mod 360)
    assert orientation_derate(540.0, 30.0) == pytest.approx(
        orientation_derate(180.0, 30.0), abs=0.001
    )


# ─── resolve_shading_factor ────────────────────────────────────────────


def test_shading_factor_explicit_face_value_wins():
    """If the engineer set face shading_factor=0.85, the site density
    default is irrelevant — explicit overrides win."""
    assert resolve_shading_factor(0.85, "rural") == 0.85
    assert resolve_shading_factor(0.85, "urban") == 0.85
    assert resolve_shading_factor(0.50, "unknown") == 0.50


def test_shading_factor_default_falls_back_to_density():
    """face_shading=1.0 is the "I didn't measure" sentinel — let the
    site density supply a sensible default. Suburban 0.96, urban 0.90."""
    assert resolve_shading_factor(1.0, "rural") == 1.00
    assert resolve_shading_factor(1.0, "suburban") == 0.96
    assert resolve_shading_factor(1.0, "urban") == 0.90
    assert resolve_shading_factor(1.0, "unknown") == 1.00


def test_shading_factor_density_table_covers_all_literal_options():
    """If schema.Site.urban_density adds a value, DENSITY_DEFAULT_SHADING
    must add a corresponding row — otherwise the .get(..., 1.0) silently
    no-derates new categories."""
    from pvess_calc.schema import Site
    # Pull the Literal options off the field annotation
    field = Site.model_fields["urban_density"]
    literal_values = set(field.annotation.__args__)
    table_keys = set(DENSITY_DEFAULT_SHADING.keys())
    assert literal_values == table_keys, (
        f"density literal {literal_values} vs table {table_keys}"
    )
