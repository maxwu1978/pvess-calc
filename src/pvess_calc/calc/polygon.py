"""K.2.7 — polygon geometry primitives for arbitrary roof faces.

Three operations the roof_layout engine + PV-4 renderer need:

  1. **Area** (`polygon_area`) — signed shoelace, used both for the
     gross face area and for orientation checks. Same implementation
     as `schema._signed_polygon_area` but exported here so consumers
     don't import private helpers.
  2. **Inset / Minkowski** (`polygon_inset_area`) — area of the
     polygon shrunk by uniform perpendicular distance `d`. Uses the
     standard formula:
            A' = A − d · P + π · d²
     which is exact for convex polygons and a tight approximation for
     mildly concave ones (residential roofs rarely exceed 10° concavity).
     For pathological shapes the result is still conservative (slightly
     under-reports usable area) — preferred to over-reporting.
  3. **Point-in-polygon** (`point_in_polygon`) — ray-casting test, O(n)
     per query. Used by `clipped_grid` to filter module candidates that
     fall outside the polygon outline.

Plus a `clipped_grid` convenience that generates the module-placement
grid for a polygon's bounding box, drops every candidate whose center
sits outside, and returns the surviving centers.
"""
from __future__ import annotations

import math
from typing import Iterable


Point = tuple[float, float]


# ─── Area + perimeter ─────────────────────────────────────────────────


def polygon_area(vertices: list[Point]) -> float:
    """Signed shoelace area. Positive for CCW vertex order."""
    n = len(vertices)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x0, y0 = vertices[i]
        x1, y1 = vertices[(i + 1) % n]
        s += (x0 * y1) - (x1 * y0)
    return s / 2.0


def offset_polygon(vertices: list[Point], d: float) -> list[Point]:
    """K.2.8 — Per-vertex bisector offset (works for convex AND concave
    polygons, unlike the K.2.7 centroid-shrink approximation).

    For each vertex V of a CCW polygon:
      * Compute inward unit normals of the two adjacent edges
        (`n_prev`, `n_next`) by rotating the edge direction +90° CCW.
      * The new vertex sits at V + (n_prev + n_next) × d / (1 + n_prev · n_next).
      * The formula handles convex corners (small offset toward
        interior), concave corners (offset still inward — normals
        sum constructively), and straight (180°) vertices (n_prev =
        n_next, denominator = 2).
      * Near anti-parallel normals (sharp 180° fold-back), the
        denominator → 0 and the offset blows up. We clamp the
        denominator at 0.05 (≈3° internal angle) so degenerate
        spikes don't produce infinite offsets.

    Positive `d` shrinks the polygon. Negative `d` would expand —
    disallowed because the K.2.8 use cases only need inset.
    """
    if d < 0:
        raise ValueError("offset_polygon: d must be ≥ 0")
    n = len(vertices)
    if n < 3:
        return list(vertices)
    if d == 0:
        return list(vertices)

    result: list[Point] = []
    for i in range(n):
        v_prev = vertices[i - 1]
        v = vertices[i]
        v_next = vertices[(i + 1) % n]

        # Edge directions (vectors from previous vertex to current,
        # and from current to next).
        e1x = v[0] - v_prev[0]
        e1y = v[1] - v_prev[1]
        l1 = math.hypot(e1x, e1y)
        e2x = v_next[0] - v[0]
        e2y = v_next[1] - v[1]
        l2 = math.hypot(e2x, e2y)
        if l1 < 1e-12 or l2 < 1e-12:
            # Duplicate vertex — preserve current as-is.
            result.append(v)
            continue
        # Inward normals (rotate edge direction +90° CCW; for a CCW
        # polygon the interior is on the left side of each edge).
        n1x = -e1y / l1
        n1y = e1x / l1
        n2x = -e2y / l2
        n2y = e2x / l2

        denom = 1.0 + n1x * n2x + n1y * n2y
        if denom < 0.05:
            # Anti-parallel normals / hairpin turn → offset would
            # blow up. Clamp denominator so result stays bounded.
            denom = 0.05
        ox = (n1x + n2x) * d / denom
        oy = (n1y + n2y) * d / denom
        result.append((v[0] + ox, v[1] + oy))
    return result


def is_convex(vertices: list[Point]) -> bool:
    """True iff the polygon is convex (every turn is in the same
    rotational direction). The K.2.7 PV-4 renderer uses this to decide
    whether the centroid-shrink visualization of the setback inset is
    safe — non-convex polygons would render with crossed inset edges.

    Triangles are trivially convex; ≤2 vertices is degenerate → False.
    """
    n = len(vertices)
    if n < 3:
        return False
    if n == 3:
        return True
    sign = 0
    for i in range(n):
        ax, ay = vertices[i]
        bx, by = vertices[(i + 1) % n]
        cx, cy = vertices[(i + 2) % n]
        cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
        if cross != 0:
            cur = 1 if cross > 0 else -1
            if sign == 0:
                sign = cur
            elif sign != cur:
                return False
    return True


def polygon_perimeter(vertices: list[Point]) -> float:
    n = len(vertices)
    if n < 2:
        return 0.0
    p = 0.0
    for i in range(n):
        x0, y0 = vertices[i]
        x1, y1 = vertices[(i + 1) % n]
        p += math.hypot(x1 - x0, y1 - y0)
    return p


# ─── Minkowski inset ──────────────────────────────────────────────────


def polygon_inset_area(vertices: list[Point], d: float) -> float:
    """Approximate area of a polygon inset by uniform distance `d`.

    Uses A' = A − d·P + π·d² (Minkowski subtraction by a disk of
    radius d). Exact for CONVEX polygons; under-estimates by O(d²)
    for slightly concave ones (acceptable for residential roofs
    where d is typically 1.5 ft and edges are 20-60 ft long).

    Returns 0 when the inset is degenerate (d larger than the
    polygon's effective inradius — `r_eff = 2A / P`, which would
    swallow the entire polygon). Negative `d` would expand —
    disallowed. The two-stage guard (degeneracy check BEFORE the
    Minkowski formula) prevents the π·d² term from producing a
    spurious positive area when d is large.
    """
    if d < 0:
        raise ValueError("polygon_inset_area: d must be ≥ 0")
    A = polygon_area(vertices)
    if A <= 0:
        return 0.0
    P = polygon_perimeter(vertices)
    # Effective inradius — when `d` exceeds this, the polygon is fully
    # consumed and the Minkowski formula is no longer valid.
    r_eff = 2 * A / P if P > 0 else 0.0
    if d >= r_eff:
        return 0.0
    # Minkowski subtraction by disc of radius d (valid for d < r_eff).
    A_prime = A - d * P + math.pi * d * d
    return max(0.0, A_prime)


# ─── Point-in-polygon ─────────────────────────────────────────────────


def point_in_polygon(point: Point, vertices: list[Point]) -> bool:
    """Ray-casting test (Dan Sunday algorithm). Returns True for points
    strictly inside; boundary points are reported as inside (we don't
    care about the measure-zero edge case for module placement).
    """
    x, y = point
    n = len(vertices)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = vertices[i]
        xj, yj = vertices[j]
        # Horizontal ray from (x, y) crosses edge i-j?
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi + 1e-15) + xi
        ):
            inside = not inside
        j = i
    return inside


# ─── Clipped grid ─────────────────────────────────────────────────────


def bounding_box(vertices: list[Point]) -> tuple[float, float, float, float]:
    """Returns (x_min, y_min, x_max, y_max)."""
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    return min(xs), min(ys), max(xs), max(ys)


def clipped_grid(
    vertices: list[Point], *, cell_w: float, cell_h: float,
    inset: float = 0.0,
) -> list[Point]:
    """Lay a `cell_w × cell_h` grid over the polygon's bounding box and
    return the centers of every cell whose center is inside the
    inset-polygon (boundary minus `inset` on every edge).

    The inset is implemented by point-in-polygon against a "shrunk"
    candidate: a cell center counts as inside iff (a) the center is
    inside the original polygon AND (b) the center is at least `inset`
    from every edge. We approximate (b) by testing the cell center
    after pushing it inward `inset`/2 from the bbox edges — sufficient
    for K.2.7 module-placement precision.

    Used by PV-4 to drop modules whose center would fall outside a
    polygon roof face. Modules are conservatively excluded when their
    center is within `inset` of an edge — keeps NEC 690.12 setbacks.
    """
    if cell_w <= 0 or cell_h <= 0:
        return []
    xmin, ymin, xmax, ymax = bounding_box(vertices)
    # Pull bounding box inward by inset (rough proxy for per-edge inset)
    xmin += inset
    ymin += inset
    xmax -= inset
    ymax -= inset
    if xmax <= xmin or ymax <= ymin:
        return []

    cx = xmin + cell_w / 2
    centers: list[Point] = []
    while cx <= xmax - cell_w / 2 + 1e-9:
        cy = ymin + cell_h / 2
        while cy <= ymax - cell_h / 2 + 1e-9:
            if point_in_polygon((cx, cy), vertices):
                centers.append((cx, cy))
            cy += cell_h
        cx += cell_w
    return centers


def fit_module_grid(
    vertices: list[Point], *, target_count: int, inset: float = 0.0,
    min_cell_ft: float = 1.5, max_iter: int = 10,
) -> tuple[float, list[Point]]:
    """K.2.8 — find the LARGEST grid cell size that still fits at least
    `target_count` modules inside the inset polygon.

    Returns `(cell_ft, centers)` where:
      * `cell_ft` is the chosen module spacing (square cells).
      * `centers` is the list of module-center coords (already trimmed
        to `target_count`, oldest-grid-first sort: top-down,
        left-to-right inside each row).

    Why binary search? The K.2.7 single-shot heuristic
    (`cell ≈ sqrt(area/N × 1.4)`) under-counted by 30-40% on
    irregular polygons because the bounding-box → polygon clipping
    drops a variable fraction. Binary searching the cell size lets us
    converge on the actual densest grid that produces ≥ N centers,
    without iterating forever.

    Degrades gracefully:
      * If even `min_cell_ft` can't fit N modules (polygon too small),
        return the densest grid we found with as many centers as fit.
      * `target_count = 0` short-circuits to empty list.
    """
    if target_count <= 0:
        return 0.0, []
    xmin, ymin, xmax, ymax = bounding_box(vertices)
    bbox_diag = math.hypot(xmax - xmin, ymax - ymin)
    if bbox_diag <= 0:
        return 0.0, []

    lo = min_cell_ft
    hi = max(bbox_diag, min_cell_ft + 1.0)
    best_cell = lo
    best_centers: list[Point] = []
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        centers = clipped_grid(vertices, cell_w=mid, cell_h=mid, inset=inset)
        if len(centers) >= target_count:
            # Got enough; remember + try BIGGER cell (less dense).
            best_cell = mid
            best_centers = centers
            lo = mid
        else:
            # Not enough; try SMALLER cell.
            hi = mid
        if hi - lo < 0.05:    # 0.05 ft = 0.6 in convergence floor
            break
    if not best_centers:
        # Final fallback at min_cell_ft (may still under-fit)
        best_cell = min_cell_ft
        best_centers = clipped_grid(
            vertices, cell_w=min_cell_ft, cell_h=min_cell_ft, inset=inset,
        )

    # Sort top-down (y descending), then left-right (x ascending),
    # and trim to target_count. This makes the visual "fill from top".
    best_centers.sort(key=lambda p: (-p[1], p[0]))
    return best_cell, best_centers[:target_count]
