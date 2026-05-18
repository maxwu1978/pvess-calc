"""Stage 7 — roof-mask contour extraction from Google Solar dataLayers.

This module turns the `mask` layer (True = target building roof) into a
review-only site-coordinate polygon. It deliberately does NOT write YAML
or replace designer-provided `house_outline_vertices`; the output is a
candidate overlay for human calibration.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .polygon import polygon_area


Point = tuple[float, float]


@dataclass(frozen=True)
class MaskContourCandidate:
    """A simplified contour derived from the Google Solar roof mask."""
    pixel_vertices: list[Point]
    site_vertices_ft: list[Point]
    area_sqft: float
    source: str = "google_solar_mask"

    @property
    def vertex_count(self) -> int:
        return len(self.site_vertices_ft)


def contour_from_mask(
    mask: np.ndarray,
    *,
    radius_m: float,
    center_site_ft: Point,
    simplify_ft: float = 2.0,
    max_vertices: int = 32,
) -> MaskContourCandidate | None:
    """Extract the largest exterior contour from a boolean roof mask.

    Args:
        mask: 2D boolean/uint8 array. True/non-zero = roof.
        radius_m: Google Solar dataLayers radius used to fetch the
            square image. The image spans `2 * radius_m` in both axes.
        center_site_ft: site-coordinate point aligned with the image
            centre. Stage 7 uses the house bbox centre as the first
            approximation; Stage 8 can replace it with manual alignment.
        simplify_ft: Ramer-Douglas-Peucker tolerance in feet after
            converting pixels to site coords.
        max_vertices: upper bound for review polygons. Epsilon increases
            until the contour is compact enough.

    Returns:
        MaskContourCandidate, or None when the mask is empty/degenerate.
    """
    arr = np.asarray(mask).astype(bool)
    if arr.ndim != 2 or not arr.any():
        return None

    pixel_poly = _largest_pixel_loop(arr)
    if len(pixel_poly) < 3:
        return None

    h, w = arr.shape
    span_ft = radius_m * 2.0 * 3.28084
    px_ft_x = span_ft / max(w, 1)
    px_ft_y = span_ft / max(h, 1)
    cx, cy = center_site_ft

    site_poly: list[Point] = []
    for px, py in pixel_poly:
        site_x = cx + (px - w / 2.0) * px_ft_x
        site_y = cy + (h / 2.0 - py) * px_ft_y
        site_poly.append((site_x, site_y))

    site_poly = _remove_duplicate_close(site_poly)
    if len(site_poly) < 3:
        return None

    eps = max(0.0, simplify_ft)
    simplified = _rdp_closed(site_poly, eps)
    while len(simplified) > max_vertices and eps < 50.0:
        eps = eps * 1.35 + 0.25
        simplified = _rdp_closed(site_poly, eps)

    if len(simplified) < 3:
        return None
    area = polygon_area(simplified)
    if area < 0:
        simplified = list(reversed(simplified))
        area = -area
    if area <= 0:
        return None

    # Keep pixel vertices aligned with the simplified site count only
    # when no RDP simplification happened. Otherwise pixel_vertices are
    # the exact raster outline and site_vertices_ft are the review form.
    return MaskContourCandidate(
        pixel_vertices=pixel_poly,
        site_vertices_ft=simplified,
        area_sqft=area,
    )


def transform_candidate(
    candidate: MaskContourCandidate,
    *,
    origin_ft: Point | None = None,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    rotation_deg: float = 0.0,
    offset_ft: Point = (0.0, 0.0),
    source_suffix: str = "",
) -> MaskContourCandidate:
    """Apply Stage 8 manual calibration to a mask contour candidate."""
    import math

    vertices = list(candidate.site_vertices_ft)
    if len(vertices) < 3:
        return candidate
    if origin_ft is None:
        origin_ft = _bbox_center(_bbox(vertices))
    ox, oy = origin_ft
    dx, dy = offset_ft
    theta = math.radians(rotation_deg)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)

    out: list[Point] = []
    for px, py in vertices:
        sx = (px - ox) * scale_x
        sy = (py - oy) * scale_y
        rx = sx * cos_t - sy * sin_t
        ry = sx * sin_t + sy * cos_t
        out.append((ox + rx + dx, oy + ry + dy))
    area = polygon_area(out)
    if area < 0:
        out = list(reversed(out))
        area = -area
    source = candidate.source
    if source_suffix:
        source = f"{source}:{source_suffix}"
    return MaskContourCandidate(
        pixel_vertices=candidate.pixel_vertices,
        site_vertices_ft=out,
        area_sqft=area,
        source=source,
    )


def fit_candidate_to_bbox(
    candidate: MaskContourCandidate,
    target_bbox: tuple[float, float, float, float],
    *,
    preserve_aspect: bool = False,
    source_suffix: str = "fit_bbox",
) -> MaskContourCandidate:
    """Fit a review contour into a target site-coordinate bbox.

    Stage 8 uses this as the first practical calibration mode: the
    Google Solar mask supplies the roof silhouette, while the existing
    EE-4 house bbox supplies the current permit-coordinate frame. This
    is still review-only and must not overwrite designer geometry.
    """
    vertices = list(candidate.site_vertices_ft)
    if len(vertices) < 3:
        return candidate
    sx0, sy0, sx1, sy1 = _bbox(vertices)
    tx0, ty0, tx1, ty1 = target_bbox
    src_w = sx1 - sx0
    src_h = sy1 - sy0
    tgt_w = tx1 - tx0
    tgt_h = ty1 - ty0
    if src_w <= 0 or src_h <= 0 or tgt_w <= 0 or tgt_h <= 0:
        return candidate

    if preserve_aspect:
        scale = min(tgt_w / src_w, tgt_h / src_h)
        out_w = src_w * scale
        out_h = src_h * scale
        ox = tx0 + (tgt_w - out_w) / 2
        oy = ty0 + (tgt_h - out_h) / 2
        out = [
            (ox + (px - sx0) * scale, oy + (py - sy0) * scale)
            for px, py in vertices
        ]
    else:
        scale_x = tgt_w / src_w
        scale_y = tgt_h / src_h
        out = [
            (tx0 + (px - sx0) * scale_x, ty0 + (py - sy0) * scale_y)
            for px, py in vertices
        ]

    area = polygon_area(out)
    if area < 0:
        out = list(reversed(out))
        area = -area
    return MaskContourCandidate(
        pixel_vertices=candidate.pixel_vertices,
        site_vertices_ft=out,
        area_sqft=area,
        source=f"{candidate.source}:{source_suffix}",
    )


def _bbox(points: list[Point]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _bbox_center(
    bbox: tuple[float, float, float, float],
) -> Point:
    x0, y0, x1, y1 = bbox
    return ((x0 + x1) / 2, (y0 + y1) / 2)


def _largest_pixel_loop(mask: np.ndarray) -> list[Point]:
    """Build oriented cell-boundary loops and return the largest area."""
    edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    h, w = mask.shape

    def is_on(r: int, c: int) -> bool:
        return 0 <= r < h and 0 <= c < w and bool(mask[r, c])

    for r in range(h):
        for c in range(w):
            if not mask[r, c]:
                continue
            if not is_on(r - 1, c):
                edges.add(((c, r), (c + 1, r)))
            if not is_on(r, c + 1):
                edges.add(((c + 1, r), (c + 1, r + 1)))
            if not is_on(r + 1, c):
                edges.add(((c + 1, r + 1), (c, r + 1)))
            if not is_on(r, c - 1):
                edges.add(((c, r + 1), (c, r)))

    loops: list[list[Point]] = []
    unused = set(edges)
    while unused:
        edge = min(unused)
        unused.remove(edge)
        start, end = edge
        loop: list[tuple[int, int]] = [start, end]
        while end != start:
            candidates = [e for e in unused if e[0] == end]
            if not candidates:
                break
            nxt = _choose_next_edge(loop[-2], end, candidates)
            unused.remove(nxt)
            end = nxt[1]
            loop.append(end)
            if len(loop) > len(edges) + 1:
                break
        if loop[-1] == start:
            cleaned = _remove_collinear([(float(x), float(y)) for x, y in loop[:-1]])
            if len(cleaned) >= 3:
                loops.append(cleaned)

    if not loops:
        return []
    return max(loops, key=lambda pts: abs(_screen_area(pts)))


def _choose_next_edge(
    prev: tuple[int, int],
    curr: tuple[int, int],
    candidates: Iterable[tuple[tuple[int, int], tuple[int, int]]],
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Pick a deterministic continuation at rare ambiguous vertices."""
    cand = list(candidates)
    if len(cand) == 1:
        return cand[0]
    vx, vy = curr[0] - prev[0], curr[1] - prev[1]

    def score(edge) -> tuple[int, tuple[int, int]]:
        nxt = edge[1]
        wx, wy = nxt[0] - curr[0], nxt[1] - curr[1]
        # Prefer straight, then right turn, then left/back. This keeps
        # orthogonal outlines stable at 4-connected diagonal touches.
        if (vx, vy) == (wx, wy):
            turn = 0
        elif (vy, -vx) == (wx, wy):
            turn = 1
        elif (-vy, vx) == (wx, wy):
            turn = 2
        else:
            turn = 3
        return (turn, nxt)

    return min(cand, key=score)


def _screen_area(points: list[Point]) -> float:
    if len(points) < 3:
        return 0.0
    total = 0.0
    for idx, (x0, y0) in enumerate(points):
        x1, y1 = points[(idx + 1) % len(points)]
        total += x0 * y1 - x1 * y0
    return total / 2.0


def _remove_collinear(points: list[Point]) -> list[Point]:
    pts = _remove_duplicate_close(points)
    changed = True
    while changed and len(pts) >= 3:
        changed = False
        out: list[Point] = []
        n = len(pts)
        for idx, b in enumerate(pts):
            a = pts[(idx - 1) % n]
            c = pts[(idx + 1) % n]
            ab = (b[0] - a[0], b[1] - a[1])
            bc = (c[0] - b[0], c[1] - b[1])
            cross = ab[0] * bc[1] - ab[1] * bc[0]
            if abs(cross) > 1e-9:
                out.append(b)
            else:
                changed = True
        pts = out
    return pts


def _remove_duplicate_close(points: list[Point]) -> list[Point]:
    out: list[Point] = []
    for p in points:
        if not out or abs(out[-1][0] - p[0]) > 1e-9 or abs(out[-1][1] - p[1]) > 1e-9:
            out.append(p)
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) < 1e-9 and abs(out[0][1] - out[-1][1]) < 1e-9:
        out.pop()
    return out


def _rdp_closed(points: list[Point], epsilon: float) -> list[Point]:
    pts = _remove_duplicate_close(points)
    if len(pts) <= 3 or epsilon <= 0:
        return _remove_collinear(pts)
    # Break the ring at the lexicographically smallest point so the
    # open-polyline RDP is deterministic.
    start_idx = min(range(len(pts)), key=lambda i: (pts[i][0], pts[i][1]))
    ring = pts[start_idx:] + pts[:start_idx] + [pts[start_idx]]
    simplified = _rdp_open(ring, epsilon)
    return _remove_collinear(_remove_duplicate_close(simplified))


def _rdp_open(points: list[Point], epsilon: float) -> list[Point]:
    if len(points) <= 2:
        return points
    a = points[0]
    b = points[-1]
    max_dist = -1.0
    max_idx = 0
    for idx, p in enumerate(points[1:-1], 1):
        dist = _point_line_distance(p, a, b)
        if dist > max_dist:
            max_dist = dist
            max_idx = idx
    if max_dist <= epsilon:
        return [a, b]
    left = _rdp_open(points[:max_idx + 1], epsilon)
    right = _rdp_open(points[max_idx:], epsilon)
    return left[:-1] + right


def _point_line_distance(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx = bx - ax
    dy = by - ay
    denom = (dx * dx + dy * dy) ** 0.5
    if denom == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    return abs(dy * px - dx * py + bx * ay - by * ax) / denom
