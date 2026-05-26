"""Review-only roof-line candidates for CAD roof tracing."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any


Point = tuple[float, float]


@dataclass(frozen=True)
class RoofLineCandidate:
    kind: str
    points: tuple[Point, Point]
    source: str
    confidence: float
    note: str = ""
    evidence_score: float | None = None
    length_ft: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "kind": self.kind,
            "points": [
                [round(self.points[0][0], 2), round(self.points[0][1], 2)],
                [round(self.points[1][0], 2), round(self.points[1][1], 2)],
            ],
            "source": self.source,
            "confidence": round(float(self.confidence), 2),
            "note": self.note,
        }
        if self.evidence_score is not None:
            data["evidence_score"] = round(float(self.evidence_score), 1)
        if self.length_ft is not None:
            data["length_ft"] = round(float(self.length_ft), 2)
        return data


def build_roof_line_candidates(
    candidate_json_path: Path,
    output_path: Path,
    *,
    underlay_path: Path | None = None,
    underlay_placement: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build conservative review-only roof-line candidates.

    This is intentionally a geometry starter, not a roof model. It uses the
    satellite/mask outline as a bounded frame and emits a small set of
    plausible ridge/hip lines for CAD tracing. A designer must review and
    redraw accepted lines on the formal ROOF_* layers before import.
    """
    candidate_json_path = Path(candidate_json_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        payload = json.loads(candidate_json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        result = _warn(f"Could not read mask candidate: {exc}")
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    candidate = payload.get("candidate") or {}
    vertices = _points(candidate.get("vertices_ft") or [])
    if len(vertices) < 4:
        result = _warn("No usable mask outline; roof-line candidates skipped.")
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    x0, y0, x1, y1 = _bbox(vertices)
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        result = _warn("Mask outline bbox is degenerate.")
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    fallback_lines = _mask_skeleton_lines(vertices, (x0, y0, x1, y1))
    image_lines = _image_edge_line_candidates(
        underlay_path,
        underlay_placement,
        vertices,
    )

    lines: list[RoofLineCandidate] = []
    source = "vision_rgb_mask"
    if image_lines:
        source = "satellite_rgb_edges+mask"
        lines.extend(_refine_skeleton_with_image_edges(fallback_lines, image_lines))
    else:
        lines.extend(fallback_lines)
    if len(lines) < 4:
        lines.extend(fallback_lines)
    lines = _select_diverse_lines(lines, max_lines=10)

    result = {
        "status": "PASS" if len(lines) >= 4 else "WARN",
        "detail": (
            f"{len(lines)} review-only roof-line candidate(s) generated. "
            "Redraw accepted lines on ROOF_* layers before import."
        ),
        "source": source,
        "confidence": "low",
        "method": (
            "satellite_rgb_edge_hough"
            if source == "satellite_rgb_edges+mask"
            else "mask_bbox_skeleton"
        ),
        "image_candidate_count": len(image_lines),
        "fallback_candidate_count": len(fallback_lines),
        "lines": [line.to_dict() for line in lines],
    }
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def _mask_skeleton_lines(
    vertices: list[Point],
    bbox: tuple[float, float, float, float],
) -> list[RoofLineCandidate]:
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    lines: list[RoofLineCandidate] = []
    y_mid = y0 + h * 0.52
    ridge_left = (x0 + w * 0.22, y_mid)
    ridge_right = (x1 - w * 0.22, y_mid)
    lines.append(RoofLineCandidate(
        kind="ridge",
        points=(ridge_left, ridge_right),
        source="vision_rgb_mask",
        confidence=0.45,
        note="Main ridge candidate from long-axis roof-mask skeleton.",
    ))

    corners = _corner_vertices(vertices, (x0, y0, x1, y1))
    for label, corner in corners.items():
        target = ridge_left if "left" in label else ridge_right
        kind = "hip"
        confidence = 0.35
        lines.append(RoofLineCandidate(
            kind=kind,
            points=(corner, target),
            source="vision_rgb_mask",
            confidence=confidence,
            note=f"{label.replace('_', ' ')} to ridge-end skeleton.",
        ))

    for vertex in _notch_vertices(vertices, (x0, y0, x1, y1)):
        target = ridge_right if vertex[0] > (x0 + x1) / 2 else ridge_left
        lines.append(RoofLineCandidate(
            kind="valley",
            points=(vertex, target),
            source="vision_rgb_mask",
            confidence=0.30,
            note="Outline notch to ridge-end valley candidate.",
        ))

    return _dedupe_lines(lines)


def _image_edge_line_candidates(
    underlay_path: Path | None,
    placement: dict[str, Any] | None,
    vertices_ft: list[Point],
) -> list[RoofLineCandidate]:
    if underlay_path is None or not Path(underlay_path).exists() or not placement:
        return []
    try:
        import numpy as np
        from PIL import Image, ImageDraw
    except Exception:
        return []

    insert = placement.get("insert_ft") or []
    size = placement.get("size_ft") or []
    if len(insert) != 2 or len(size) != 2:
        return []
    ix, iy = float(insert[0]), float(insert[1])
    sx, sy = float(size[0]), float(size[1])
    if sx <= 0 or sy <= 0:
        return []

    try:
        image = Image.open(underlay_path).convert("RGB")
    except Exception:
        return []
    width, height = image.size
    if width <= 0 or height <= 0:
        return []

    def ft_to_px(pt: Point) -> tuple[float, float]:
        x, y = pt
        return (
            (float(x) - ix) / sx * width,
            height - (float(y) - iy) / sy * height,
        )

    polygon_px = [ft_to_px(pt) for pt in vertices_ft]
    mask_img = Image.new("1", (width, height), 0)
    ImageDraw.Draw(mask_img).polygon(polygon_px, fill=1)
    mask = np.asarray(mask_img, dtype=bool)
    mask = _erode_mask(mask, iterations=max(3, round(min(width, height) * 0.012)))
    if int(mask.sum()) < 80:
        return []

    arr = np.asarray(image).astype("float64")
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    gray = 0.299 * r + 0.587 * g + 0.114 * b
    padded = np.pad(gray, 1, mode="edge")
    gx = padded[1:-1, 2:] - padded[1:-1, :-2]
    gy = padded[2:, 1:-1] - padded[:-2, 1:-1]
    magnitude = np.hypot(gx, gy)

    red_marker = (r > 150) & (r > g * 1.25) & (r > b * 1.25)
    valid = mask & ~red_marker
    values = magnitude[valid]
    if values.size < 80:
        return []
    threshold = float(np.percentile(values, 88))
    edge = valid & (magnitude >= threshold)
    yx = np.argwhere(edge)
    if len(yx) < 80:
        return []

    points_px = np.column_stack((yx[:, 1], yx[:, 0])).astype("float64")
    weights = magnitude[edge].astype("float64")
    raw = _hough_segments(points_px, weights)
    candidates: list[RoofLineCandidate] = []

    def px_to_ft(pt: tuple[float, float]) -> Point:
        px, py = pt
        return (
            ix + float(px) / width * sx,
            iy + (height - float(py)) / height * sy,
        )

    score_ref = max((segment["score"] for segment in raw), default=1.0)
    for segment in raw:
        a = px_to_ft(segment["a"])
        b = px_to_ft(segment["b"])
        length_ft = _dist(a, b)
        if length_ft < 8.0:
            continue
        kind = _kind_from_angle(a, b)
        confidence = 0.40 + 0.22 * min(1.0, segment["score"] / score_ref)
        candidates.append(RoofLineCandidate(
            kind=kind,
            points=(a, b),
            source="satellite_rgb_edges",
            confidence=min(0.62, confidence),
            evidence_score=segment["score"],
            length_ft=length_ft,
            note=(
                "Image-edge candidate inside roof mask; verify against "
                "satellite underlay before redrawing."
            ),
        ))
    return _select_diverse_lines(candidates, max_lines=10)


def _erode_mask(mask, *, iterations: int):
    import numpy as np

    out = np.asarray(mask, dtype=bool)
    for _ in range(max(0, int(iterations))):
        inner = np.zeros_like(out, dtype=bool)
        inner[1:-1, 1:-1] = (
            out[1:-1, 1:-1]
            & out[:-2, 1:-1]
            & out[2:, 1:-1]
            & out[1:-1, :-2]
            & out[1:-1, 2:]
        )
        out = inner
    return out


def _hough_segments(points_px, weights) -> list[dict[str, Any]]:
    import numpy as np

    if len(points_px) == 0:
        return []
    segments: list[dict[str, Any]] = []
    for angle_deg in range(-75, 91, 15):
        theta = math.radians(angle_deg)
        direction = np.array([math.cos(theta), math.sin(theta)], dtype="float64")
        normal = np.array([-math.sin(theta), math.cos(theta)], dtype="float64")
        rho = points_px[:, 0] * normal[0] + points_px[:, 1] * normal[1]
        t = points_px[:, 0] * direction[0] + points_px[:, 1] * direction[1]
        bin_width = 6.0
        rho_min = float(np.min(rho))
        bins = np.floor((rho - rho_min) / bin_width).astype("int64")
        if bins.size == 0:
            continue
        score_by_bin = np.bincount(bins, weights=weights)
        count_by_bin = np.bincount(bins)
        top_bins = np.argsort(score_by_bin)[-4:][::-1]
        for bin_index in top_bins:
            score = float(score_by_bin[bin_index])
            if score <= 0 or int(count_by_bin[bin_index]) < 20:
                continue
            rho_center = rho_min + (float(bin_index) + 0.5) * bin_width
            selected = np.abs(rho - rho_center) <= bin_width * 0.55
            if int(selected.sum()) < 20:
                continue
            selected_t = t[selected]
            t0, t1 = np.percentile(selected_t, [5, 95])
            length_px = float(t1 - t0)
            if length_px < 35.0:
                continue
            center = rho_center * normal
            a = center + float(t0) * direction
            b = center + float(t1) * direction
            segments.append({
                "angle_deg": float(angle_deg),
                "score": score,
                "count": int(selected.sum()),
                "length_px": length_px,
                "a": (float(a[0]), float(a[1])),
                "b": (float(b[0]), float(b[1])),
            })
    segments.sort(key=lambda item: item["score"], reverse=True)
    return segments[:32]


def _kind_from_angle(a: Point, b: Point) -> str:
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    angle = abs(math.degrees(math.atan2(dy, dx)))
    if angle <= 12 or angle >= 78:
        return "ridge"
    return "hip"


def _refine_skeleton_with_image_edges(
    skeleton: list[RoofLineCandidate],
    image_lines: list[RoofLineCandidate],
) -> list[RoofLineCandidate]:
    refined: list[RoofLineCandidate] = []
    used: set[int] = set()
    for base in skeleton:
        best_index = -1
        best_score = -1.0
        base_length = _dist(base.points[0], base.points[1])
        for index, image_line in enumerate(image_lines):
            if index in used:
                continue
            if _angle_difference(base, image_line) > 24.0:
                continue
            if _center_distance(base, image_line) > max(8.0, base_length * 0.35):
                continue
            score = float(image_line.evidence_score or 0.0)
            if score > best_score:
                best_index = index
                best_score = score
        if best_index >= 0:
            used.add(best_index)
            matched = image_lines[best_index]
            refined.append(RoofLineCandidate(
                kind=base.kind,
                points=matched.points,
                source=matched.source,
                confidence=matched.confidence,
                evidence_score=matched.evidence_score,
                length_ft=matched.length_ft,
                note=(
                    f"Image-edge refinement of {base.kind} mask skeleton; "
                    "verify before redrawing on ROOF_* layers."
                ),
            ))
        else:
            refined.append(base)
    return refined


def _angle_difference(a: RoofLineCandidate, b: RoofLineCandidate) -> float:
    diff = abs(_line_angle(a) - _line_angle(b))
    return min(diff, 180.0 - diff)


def _center_distance(a: RoofLineCandidate, b: RoofLineCandidate) -> float:
    ax, ay = _line_center(a)
    bx, by = _line_center(b)
    return math.hypot(ax - bx, ay - by)


def _warn(detail: str) -> dict[str, Any]:
    return {
        "status": "WARN",
        "detail": detail,
        "source": "vision_rgb_mask",
        "confidence": "low",
        "lines": [],
    }


def _points(raw: list) -> list[Point]:
    points: list[Point] = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        try:
            points.append((float(item[0]), float(item[1])))
        except (TypeError, ValueError):
            continue
    return points


def _bbox(points: list[Point]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _corner_vertices(
    vertices: list[Point],
    bbox: tuple[float, float, float, float],
) -> dict[str, Point]:
    x0, y0, x1, y1 = bbox
    targets = {
        "bottom_left": (x0, y0),
        "top_left": (x0, y1),
        "bottom_right": (x1, y0),
        "top_right": (x1, y1),
    }
    result: dict[str, Point] = {}
    for name, target in targets.items():
        result[name] = min(vertices, key=lambda p: _dist(p, target))
    return result


def _notch_vertices(
    vertices: list[Point],
    bbox: tuple[float, float, float, float],
) -> list[Point]:
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    inset = []
    for p in vertices:
        near_outer = (
            abs(p[0] - x0) < w * 0.08
            or abs(p[0] - x1) < w * 0.08
            or abs(p[1] - y0) < h * 0.08
            or abs(p[1] - y1) < h * 0.08
        )
        if not near_outer:
            inset.append(p)
    return inset[:4]


def _dedupe_lines(lines: list[RoofLineCandidate]) -> list[RoofLineCandidate]:
    out: list[RoofLineCandidate] = []
    seen: set[tuple[int, int, int, int]] = set()
    for line in lines:
        a, b = line.points
        if _dist(a, b) < 3.0:
            continue
        key = (
            round(min(a[0], b[0]) * 2),
            round(min(a[1], b[1]) * 2),
            round(max(a[0], b[0]) * 2),
            round(max(a[1], b[1]) * 2),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
    return out


def _select_diverse_lines(
    lines: list[RoofLineCandidate],
    *,
    max_lines: int,
) -> list[RoofLineCandidate]:
    sorted_lines = sorted(
        _dedupe_lines(lines),
        key=lambda line: (
            float(line.evidence_score or 0.0),
            float(line.length_ft or _dist(line.points[0], line.points[1])),
            float(line.confidence),
        ),
        reverse=True,
    )
    selected: list[RoofLineCandidate] = []
    for line in sorted_lines:
        if any(_too_similar(line, existing) for existing in selected):
            continue
        selected.append(line)
        if len(selected) >= max_lines:
            break
    return selected


def _too_similar(a: RoofLineCandidate, b: RoofLineCandidate) -> bool:
    if a.kind != b.kind:
        return False
    angle_diff = abs(_line_angle(a) - _line_angle(b))
    angle_diff = min(angle_diff, 180.0 - angle_diff)
    if angle_diff > 12.0:
        return False
    ax, ay = _line_center(a)
    bx, by = _line_center(b)
    if math.hypot(ax - bx, ay - by) > 6.0:
        return False
    return True


def _line_angle(line: RoofLineCandidate) -> float:
    a, b = line.points
    angle = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    if angle < 0:
        angle += 180.0
    if angle >= 180.0:
        angle -= 180.0
    return angle


def _line_center(line: RoofLineCandidate) -> Point:
    a, b = line.points
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])
