"""Preview image generation for imported roof-review geometry."""
from __future__ import annotations

from pathlib import Path
import json


def write_import_preview(imported, output_path: Path) -> Path:
    """Render a lightweight PNG preview of imported CAD roof geometry."""
    import matplotlib.pyplot as plt

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    trace = imported.site.ee4_trace
    fig, ax = plt.subplots(figsize=(8.0, 6.0), dpi=150)
    ax.set_aspect("equal", adjustable="box")
    ax.set_facecolor("#f8fafc")

    if trace.roof_outline is not None:
        _plot_polygon(ax, trace.roof_outline.vertices, "#0f172a", 2.0, None)
    active_facet_names = {
        section.name for section in imported.site.roof_sections
    }
    for facet in trace.roof_facets:
        _plot_polygon(ax, facet.vertices, "#2563eb", 1.2, "#dbeafe")
        if facet.name not in active_facet_names:
            continue
        cx = sum(x for x, _y in facet.vertices) / len(facet.vertices)
        cy = sum(y for _x, y in facet.vertices) / len(facet.vertices)
        ax.text(cx, cy, facet.name, fontsize=7, ha="center", va="center")
    for line in trace.roof_lines:
        xs = [pt[0] for pt in line.points]
        ys = [pt[1] for pt in line.points]
        ax.plot(xs, ys, color="#dc2626", linewidth=1.0)
    for symbol in trace.symbols:
        ax.scatter([symbol.x_ft], [symbol.y_ft], s=18, color="#f97316")

    ax.grid(True, color="#cbd5e1", linewidth=0.4)
    ax.set_xlabel("site/local x (ft)")
    ax.set_ylabel("site/local y (ft)")
    ax.set_title("CAD roof-review import preview")
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    return output_path


def write_roof_review_preview(
    underlay_path: Path,
    candidate_json_path: Path,
    output_path: Path,
    *,
    line_candidates: dict | None = None,
    face_priorities: list[dict] | None = None,
    obstruction_zones: list[dict] | None = None,
    underlay_placement: dict | None = None,
) -> Path:
    """Write a human preview for the CAD roof-review package.

    The generic DXF preview path cannot reliably render DXF IMAGE entities,
    so the roof-review package owns this preview. It intentionally shows the
    same raster underlay CAD will reference, plus the candidate status.
    """
    from PIL import Image, ImageDraw

    underlay_path = Path(underlay_path)
    candidate_json_path = Path(candidate_json_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    image = Image.open(underlay_path).convert("RGB")
    scale = max(1.0, min(2.0, 900 / max(image.size)))
    if scale > 1.01:
        image = image.resize(
            (round(image.width * scale), round(image.height * scale)),
            Image.Resampling.LANCZOS,
        )
    header_h = 92
    footer_h = 80
    margin = 22
    side_w = 310 if (face_priorities or obstruction_zones) else 0
    canvas = Image.new(
        "RGB",
        (
            image.width + margin * 2 + side_w,
            image.height + header_h + footer_h,
        ),
        "white",
    )
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 18), "PVESS Roof CAD Review", fill="#0f172a")
    draw.text(
        (margin, 42),
        "Satellite underlay with mask outline candidate - verify in CAD before import.",
        fill="#475569",
    )
    canvas.paste(image, (margin, header_h))
    if obstruction_zones and underlay_placement:
        _draw_obstruction_zones_on_preview(
            canvas,
            obstruction_zones,
            underlay_placement,
            image_offset=(margin, header_h),
            image_size=image.size,
        )
    if line_candidates and underlay_placement:
        _draw_candidate_lines_on_preview(
            draw,
            line_candidates,
            underlay_placement,
            image_offset=(margin, header_h),
            image_size=image.size,
        )

    detail = _candidate_detail(candidate_json_path)
    y = header_h + image.height + 18
    draw.text((margin, y), detail, fill="#0f172a")
    if line_candidates:
        draw.text(
            (margin, y + 22),
            _line_candidate_detail(line_candidates),
            fill="#7c2d12",
        )
    if side_w:
        _draw_guidance_panel(
            draw,
            face_priorities or [],
            obstruction_zones or [],
            x=margin + image.width + 24,
            y=header_h,
            width=side_w - 24,
        )
    canvas.save(output_path)
    return output_path


def write_placeholder_underlay(output_path: Path, *, title: str, detail: str) -> Path:
    """Write a placeholder underlay PNG when no satellite layer is available."""
    from PIL import Image, ImageDraw

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (1400, 900), "#f8fafc")
    draw = ImageDraw.Draw(img)
    draw.rectangle((40, 40, 1360, 860), outline="#94a3b8", width=3)
    draw.text((80, 90), title, fill="#0f172a")
    draw.text((80, 130), detail, fill="#475569")
    draw.text(
        (80, 810),
        "Draw reviewed geometry in CAD using ROOF_OUTLINE and ROOF_FACET layers.",
        fill="#475569",
    )
    img.save(output_path)
    return output_path


def _candidate_detail(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return "Candidate: unavailable"
    status = payload.get("status", "WARN")
    candidate = payload.get("candidate") or {}
    if not candidate:
        return f"Candidate: {status} - {payload.get('detail', '-')}"
    return (
        f"Candidate: {status}; vertices={candidate.get('vertex_count', '-')}; "
        f"area={candidate.get('area_sqft', '-')} sqft; "
        f"source={candidate.get('source', '-')}"
    )


def _line_candidate_detail(payload: dict) -> str:
    lines = payload.get("lines") or []
    return (
        f"Roof-line candidates: {payload.get('status', 'WARN')}; "
        f"count={len(lines)}; source={payload.get('source', '-')}; "
        "redraw accepted lines on ROOF_* layers."
    )


def _draw_candidate_lines_on_preview(
    draw,
    payload: dict,
    placement: dict,
    *,
    image_offset: tuple[int, int],
    image_size: tuple[int, int],
) -> None:
    insert = placement.get("insert_ft") or []
    size = placement.get("size_ft") or []
    if len(insert) != 2 or len(size) != 2:
        return
    ix, iy = float(insert[0]), float(insert[1])
    sx, sy = float(size[0]), float(size[1])
    if sx <= 0 or sy <= 0:
        return
    ox, oy = image_offset
    w, h = image_size

    def to_px(pt):
        x, y = float(pt[0]), float(pt[1])
        px = ox + (x - ix) / sx * w
        py = oy + h - (y - iy) / sy * h
        return (px, py)

    for item in payload.get("lines") or []:
        pts = item.get("points") or []
        if len(pts) != 2:
            continue
        a = to_px(pts[0])
        b = to_px(pts[1])
        draw.line((a, b), fill="#f59e0b", width=4)


def _draw_obstruction_zones_on_preview(
    canvas,
    zones: list[dict],
    placement: dict,
    *,
    image_offset: tuple[int, int],
    image_size: tuple[int, int],
) -> None:
    from PIL import Image, ImageDraw

    insert = placement.get("insert_ft") or []
    size = placement.get("size_ft") or []
    if len(insert) != 2 or len(size) != 2:
        return
    ix, iy = float(insert[0]), float(insert[1])
    sx, sy = float(size[0]), float(size[1])
    if sx <= 0 or sy <= 0:
        return
    ox, oy = image_offset
    w, h = image_size
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    def to_px(x_ft, y_ft):
        px = ox + (float(x_ft) - ix) / sx * w
        py = oy + h - (float(y_ft) - iy) / sy * h
        return px, py

    px_per_ft = (w / sx + h / sy) / 2.0
    for zone in zones:
        try:
            x, y = to_px(zone.get("x_ft"), zone.get("y_ft"))
            r = max(float(zone.get("radius_ft") or 0.0) * px_per_ft, 4.0)
        except (TypeError, ValueError):
            continue
        bbox = (x - r, y - r, x + r, y + r)
        draw.ellipse(bbox, fill=(220, 38, 38, 52),
                     outline=(185, 28, 28, 255), width=3)
        draw.line((x - r, y - r, x + r, y + r),
                  fill=(185, 28, 28, 255), width=2)
        draw.line((x - r, y + r, x + r, y - r),
                  fill=(185, 28, 28, 255), width=2)
    composite = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    canvas.paste(composite, (0, 0))


def _draw_guidance_panel(
    draw,
    face_priorities: list[dict],
    obstruction_zones: list[dict],
    *,
    x: int,
    y: int,
    width: int,
) -> None:
    draw.text((x, y), "PV face priority", fill="#0f172a")
    draw.text((x, y + 18), "SW first · East second · North avoid", fill="#475569")
    row_y = y + 44
    for item in face_priorities[:10]:
        priority = item.get("priority") or {}
        color = priority.get("color") or "#64748b"
        draw.rectangle((x, row_y, x + 14, row_y + 14),
                       fill=color, outline="#334155")
        label = (
            f"{item.get('index', '-')}. {item.get('name', 'Face')} "
            f"AZ={item.get('azimuth_deg', '-')}"
        )
        draw.text((x + 20, row_y - 1), _fit_text(label, 38), fill="#0f172a")
        draw.text(
            (x + 20, row_y + 14),
            _fit_text(priority.get("label", "-"), 38),
            fill="#475569",
        )
        row_y += 38
        if row_y > y + 420:
            break

    if obstruction_zones:
        row_y += 10
        draw.text((x, row_y), "No-panel zones", fill="#0f172a")
        row_y += 22
        for idx, zone in enumerate(obstruction_zones[:8], start=1):
            label = (
                f"{idx}. {zone.get('kind', 'obstruction')} "
                f"R={zone.get('radius_ft', '-')}ft"
            )
            draw.text((x, row_y), _fit_text(label, 42), fill="#991b1b")
            row_y += 18


def _fit_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max(0, max_chars - 3)] + "..."


def _plot_polygon(ax, vertices, edge_color: str, line_width: float, fill_color: str | None) -> None:
    if not vertices:
        return
    xs = [pt[0] for pt in vertices] + [vertices[0][0]]
    ys = [pt[1] for pt in vertices] + [vertices[0][1]]
    if fill_color:
        ax.fill(xs, ys, color=fill_color, alpha=0.45)
    ax.plot(xs, ys, color=edge_color, linewidth=line_width)
