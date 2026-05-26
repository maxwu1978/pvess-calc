"""Shared geometry helpers for roof layout and module placement.

The historical polygon helpers in :mod:`pvess_calc.calc.polygon` are
kept for deterministic lightweight math and schema validation. This
module wraps Shapely for operations where exact geometry matters:
negative buffers for setbacks, full-footprint containment, and polygon
intersection checks.
"""
from __future__ import annotations

from typing import Iterable

from .polygon import (
    bounding_box as fallback_bounding_box,
    offset_polygon,
    point_in_polygon,
    polygon_area as fallback_polygon_area,
)


Point = tuple[float, float]

try:  # pragma: no cover - the fallback is for constrained installs.
    from shapely.geometry import Polygon
    from shapely.geometry.base import BaseGeometry

    HAS_SHAPELY = True
except Exception:  # pragma: no cover
    Polygon = None  # type: ignore[assignment]
    BaseGeometry = object  # type: ignore[assignment]
    HAS_SHAPELY = False


def usable_inset_polygon(
    vertices: list[Point],
    setback_ft: float,
) -> list[Point]:
    """Return a polygon inset by ``setback_ft``.

    Shapely's negative buffer is the primary implementation because it
    handles concave outlines and corner topology better than the older
    per-vertex fallback. The fallback keeps local tooling from failing
    hard if Shapely is unavailable.
    """
    if setback_ft <= 0:
        return _normalize_vertices(vertices)
    if HAS_SHAPELY:
        poly = _polygon(vertices)
        if poly is None:
            return []
        buffered = poly.buffer(-setback_ft, join_style=2, mitre_limit=5.0)
        largest = _largest_polygon(buffered)
        return _vertices_from_polygon(largest)
    inset = offset_polygon(vertices, setback_ft)
    return inset if fallback_polygon_area(inset) > 0 else []


def rectangle_vertices(
    x_ft: float,
    y_ft: float,
    width_ft: float,
    height_ft: float,
) -> list[Point]:
    """Return a CCW rectangle polygon."""
    x1 = x_ft + width_ft
    y1 = y_ft + height_ft
    return [(x_ft, y_ft), (x1, y_ft), (x1, y1), (x_ft, y1)]


def polygon_bounds(vertices: list[Point]) -> tuple[float, float, float, float]:
    """Return ``(xmin, ymin, xmax, ymax)`` for a polygon."""
    if HAS_SHAPELY:
        poly = _polygon(vertices)
        if poly is not None and not poly.is_empty:
            return tuple(float(v) for v in poly.bounds)  # type: ignore[return-value]
    return fallback_bounding_box(vertices)


def polygon_area(vertices: list[Point]) -> float:
    """Return positive polygon area."""
    if HAS_SHAPELY:
        poly = _polygon(vertices)
        if poly is not None and not poly.is_empty:
            return float(poly.area)
    return abs(fallback_polygon_area(vertices))


def polygon_covers_polygon(
    container_vertices: list[Point],
    candidate_vertices: list[Point],
    *,
    tolerance_ft: float = 1e-7,
) -> bool:
    """True when the full candidate polygon is inside or on container."""
    if HAS_SHAPELY:
        container = _polygon(container_vertices)
        candidate = _polygon(candidate_vertices)
        if container is None or candidate is None:
            return False
        return bool(container.buffer(tolerance_ft).covers(candidate))
    return all(point_in_polygon(p, container_vertices) for p in candidate_vertices)


def polygons_overlap_area(
    a_vertices: list[Point],
    b_vertices: list[Point],
    *,
    min_area_sqft: float = 1e-7,
) -> bool:
    """True when two polygons overlap by non-trivial area."""
    if HAS_SHAPELY:
        a_poly = _polygon(a_vertices)
        b_poly = _polygon(b_vertices)
        if a_poly is None or b_poly is None:
            return False
        return float(a_poly.intersection(b_poly).area) > min_area_sqft
    return (
        any(point_in_polygon(p, b_vertices) for p in a_vertices)
        or any(point_in_polygon(p, a_vertices) for p in b_vertices)
    )


def obstruction_halo_vertices(obstruction) -> list[Point]:
    """Return the obstruction rectangle expanded by its clear-space halo."""
    setback = max(0.0, float(getattr(obstruction, "setback_ft", 0.0)))
    x0 = float(getattr(obstruction, "x_ft", 0.0)) - setback
    y0 = float(getattr(obstruction, "y_ft", 0.0)) - setback
    x1 = (
        float(getattr(obstruction, "x_ft", 0.0))
        + float(getattr(obstruction, "width_ft", 0.0))
        + setback
    )
    y1 = (
        float(getattr(obstruction, "y_ft", 0.0))
        + float(getattr(obstruction, "height_ft", 0.0))
        + setback
    )
    return rectangle_vertices(x0, y0, x1 - x0, y1 - y0)


def _normalize_vertices(vertices: Iterable[Point]) -> list[Point]:
    out = [(float(x), float(y)) for x, y in vertices]
    if len(out) >= 2 and out[0] == out[-1]:
        out.pop()
    return out


def _polygon(vertices: list[Point]) -> BaseGeometry | None:
    pts = _normalize_vertices(vertices)
    if len(pts) < 3:
        return None
    poly = Polygon(pts)  # type: ignore[operator]
    if poly.is_empty:
        return None
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty:
        return None
    return poly


def _largest_polygon(geom: BaseGeometry | None) -> BaseGeometry | None:
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type == "Polygon":
        return geom
    if geom.geom_type == "MultiPolygon":
        geoms = list(geom.geoms)
        return max(geoms, key=lambda g: g.area) if geoms else None
    if geom.geom_type == "GeometryCollection":
        polys = [g for g in geom.geoms if g.geom_type == "Polygon"]
        return max(polys, key=lambda g: g.area) if polys else None
    return None


def _vertices_from_polygon(poly: BaseGeometry | None) -> list[Point]:
    if poly is None or poly.is_empty or poly.geom_type != "Polygon":
        return []
    coords = list(poly.exterior.coords)
    if coords and coords[0] == coords[-1]:
        coords.pop()
    pts = [(float(x), float(y)) for x, y in coords]
    return pts if len(pts) >= 3 else []
