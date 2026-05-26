"""T1/T2 — auditable satellite mask roof-outline candidates.

This module is deliberately review-only. It audits the Google Solar
dataLayers cache and exports a paste-ready `site.ee4_trace.roof_outline`
candidate, but it never mutates project inputs automatically.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from ..calc.engine import CalculationResult
from ..calc.mask_contour import (
    MaskContourCandidate,
    contour_from_mask,
    fit_candidate_to_bbox,
    transform_candidate,
)
from ..calc.site_layout import house_bbox
from ..customer.roof_satellite import (
    SatelliteAssets,
    TargetMaskComponent,
    target_component_from_mask,
)
from ..schema import EE4Trace, EE4TracePolygon
from .cover_maps import coordinates_to_lat_lng, fetch_satellite_assets_cached
from .ee4_trace import ee4_trace_yaml


def write_satellite_roof_outline_artifacts(
    result: CalculationResult,
    output_dir: Path,
    *,
    radius_m: float,
    pixel_size_m: float = 0.25,
    allow_network: bool = False,
) -> dict[str, Any]:
    """Write T1 data-chain audit and T2 roof-outline candidate files."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    audit_json = output_dir / "satellite-data-chain-audit.json"
    audit_md = output_dir / "satellite-data-chain-audit.md"
    candidate_json = output_dir / "satellite-roof-outline-candidate.json"
    candidate_yaml = output_dir / "satellite-ee4-trace-candidate.yaml"
    candidate_png = output_dir / "satellite-roof-outline-candidate.png"
    candidate_underlay_json = (
        output_dir / "satellite-roof-outline-underlay-placement.json"
    )

    lat_lng = coordinates_to_lat_lng(result.inputs.project.coordinates)
    assets = None
    if lat_lng is not None:
        assets = fetch_satellite_assets_cached(
            *lat_lng,
            radius_m=radius_m,
            pixel_size_m=pixel_size_m,
            cache=True,
            allow_network=allow_network,
        )

    component = (
        target_component_from_mask(assets.mask, assets.target_px)
        if assets is not None else None
    )
    audit_payload = build_satellite_data_chain_audit(
        result,
        assets=assets,
        component=component,
        lat_lng=lat_lng,
        radius_m=radius_m,
        pixel_size_m=pixel_size_m,
    )
    audit_json.write_text(
        json.dumps(audit_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    audit_md.write_text(
        format_satellite_data_chain_markdown(audit_payload),
        encoding="utf-8",
    )

    candidate_payload = build_satellite_roof_outline_candidate(
        result,
        assets=assets,
        component=component,
        radius_m=radius_m,
    )

    yaml_path: Path | None = None
    png_path: Path | None = None
    if assets is not None and component is not None and candidate_payload.get("candidate"):
        trace = _trace_from_candidate_payload(candidate_payload)
        if trace is not None:
            candidate_yaml.write_text(ee4_trace_yaml(trace), encoding="utf-8")
            yaml_path = candidate_yaml
        contour = candidate_payload.get("_contour_object")
        if isinstance(contour, MaskContourCandidate):
            _write_outline_preview_png(
                assets,
                component,
                contour,
                candidate_png,
                underlay_json_path=candidate_underlay_json,
            )
            png_path = candidate_png

    candidate_payload.pop("_contour_object", None)
    candidate_json.write_text(
        json.dumps(candidate_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "status": {
            "status": candidate_payload.get("status", "WARN"),
            "detail": candidate_payload.get("detail", ""),
            "vertex_count": (
                candidate_payload.get("candidate") or {}
            ).get("vertex_count", 0),
            "area_sqft": (
                candidate_payload.get("candidate") or {}
            ).get("area_sqft", 0.0),
            "audit_status": audit_payload.get("status", "WARN"),
            "audit_detail": audit_payload.get("detail", ""),
        },
        "audit_json": audit_json,
        "audit_markdown": audit_md,
        "candidate_json": candidate_json,
        "candidate_yaml": yaml_path,
        "candidate_png": png_path,
        "candidate_underlay_json": (
            candidate_underlay_json
            if candidate_underlay_json.exists() else None
        ),
    }


def build_satellite_data_chain_audit(
    result: CalculationResult,
    *,
    assets: SatelliteAssets | None,
    component: TargetMaskComponent | None,
    lat_lng: tuple[float, float] | None,
    radius_m: float,
    pixel_size_m: float = 0.25,
) -> dict[str, Any]:
    """Return a compact, user-reviewable audit of satellite source layers."""
    if lat_lng is None:
        return {
            "status": "WARN",
            "detail": "Project coordinates are missing or invalid.",
            "address": result.inputs.project.site_address,
            "coordinates": result.inputs.project.coordinates,
            "radius_m": radius_m,
            "requested_pixel_size_m": pixel_size_m,
            "layers": {},
        }
    if assets is None:
        return {
            "status": "WARN",
            "detail": (
                "No cached Google Solar dataLayers assets are available. "
                "Generate the satellite review once with paid renders enabled."
            ),
            "address": result.inputs.project.site_address,
            "coordinates": result.inputs.project.coordinates,
            "lat_lng": {"lat": lat_lng[0], "lng": lat_lng[1]},
            "radius_m": radius_m,
            "requested_pixel_size_m": pixel_size_m,
            "layers": {},
        }

    mask = np.asarray(assets.mask).astype(bool)
    h, w = mask.shape if mask.ndim == 2 else (0, 0)
    span_m = radius_m * 2.0
    px_m = span_m / w if w else 0.0
    layers = {
        "rgb": {
            "available": bool(assets.rgb.size),
            "shape": list(assets.rgb.shape),
        },
        "mask": {
            "available": bool(mask.size),
            "shape": list(mask.shape),
            "true_pixels": int(mask.sum()) if mask.size else 0,
        },
        "annual_flux": {
            "available": bool(assets.annual_flux.size),
            "shape": list(assets.annual_flux.shape),
            "unit": "kWh/m^2/yr",
        },
        "dsm": {
            "available": False,
            "reason": (
                "Google Solar exposes a DSM URL, but the current cached "
                "SatelliteAssets payload does not decode/store DSM yet."
            ),
        },
    }
    target = {
        "available": component is not None,
    }
    if component is not None:
        target.update({
            "component_count": component.component_count,
            "bbox_px": list(component.bbox),
            "area_px": component.area_px,
            "distance_px2": round(float(component.distance_px2), 3),
            "target_px": [
                round(float(component.target_px[0]), 2),
                round(float(component.target_px[1]), 2),
            ],
        })
    mask_true_pixels = int(mask.sum()) if mask.size else 0
    status = "PASS" if component is not None else "WARN"
    if component is not None:
        detail = "RGB, annual flux, and mask are cached; target roof component selected."
    elif mask_true_pixels == 0:
        detail = (
            "Google Solar dataLayers were fetched and cached, but the roof "
            "mask contains zero roof pixels. This usually means the imagery "
            "or mask layer is stale for a new-construction address; use a "
            "field/EagleView roof outline or manual trace before AHJ review."
        )
    else:
        detail = "Satellite layers are cached, but no target roof mask component was found."
    return {
        "status": status,
        "detail": detail,
        "address": result.inputs.project.site_address,
        "coordinates": result.inputs.project.coordinates,
        "lat_lng": {"lat": lat_lng[0], "lng": lat_lng[1]},
        "radius_m": radius_m,
        "requested_pixel_size_m": pixel_size_m,
        "estimated_pixel_size_m": round(px_m, 4),
        "imagery": {
            "date": assets.imagery_date,
            "quality": assets.imagery_quality,
        },
        "layers": layers,
        "target_component": target,
    }


def build_satellite_roof_outline_candidate(
    result: CalculationResult,
    *,
    assets: SatelliteAssets | None,
    component: TargetMaskComponent | None,
    radius_m: float,
) -> dict[str, Any]:
    """Build a review-only EE-4 roof-outline candidate from target mask."""
    if assets is None:
        return {
            "status": "WARN",
            "detail": "Satellite assets unavailable; cannot derive roof outline.",
            "candidate": None,
            "ee4_trace_candidate": None,
        }
    if component is None:
        mask = np.asarray(assets.mask).astype(bool)
        if mask.size and int(mask.sum()) == 0:
            detail = (
                "Google Solar dataLayers returned imagery, but the mask has "
                "zero roof pixels. The address may be newer than the imagery "
                "or outside current roof-mask coverage; manual tracing or a "
                "field roof report is required."
            )
        else:
            detail = "Target roof mask component unavailable."
        return {
            "status": "WARN",
            "detail": detail,
            "candidate": None,
            "ee4_trace_candidate": None,
        }

    site = result.inputs.site
    alignment = site.satellite_alignment
    hx0, hy0, hx1, hy1 = house_bbox(site)
    house_center = ((hx0 + hx1) / 2.0, (hy0 + hy1) / 2.0)
    center_site_ft = (
        alignment.center_x_ft
        if alignment.center_x_ft is not None else house_center[0],
        alignment.center_y_ft
        if alignment.center_y_ft is not None else house_center[1],
    )

    contour = contour_from_mask(
        component.mask,
        radius_m=radius_m,
        center_site_ft=center_site_ft,
        simplify_ft=alignment.contour_simplify_ft,
        max_vertices=alignment.contour_max_vertices,
    )
    if contour is None:
        return {
            "status": "WARN",
            "detail": "Target roof mask was found, but no valid contour was extracted.",
            "candidate": None,
            "ee4_trace_candidate": None,
        }

    contour = _apply_alignment(
        contour,
        house_bbox_ft=(hx0, hy0, hx1, hy1),
        center_site_ft=center_site_ft,
        alignment=alignment,
    )
    vertices = _round_vertices(contour.site_vertices_ft)
    try:
        trace = EE4Trace(
            enabled=True,
            roof_outline=EE4TracePolygon(
                name="Satellite mask roof outline candidate",
                vertices=vertices,
            ),
            roof_facets=[],
            roof_lines=[],
            fire_pathways=[],
            symbols=[],
        )
    except ValueError as exc:
        return {
            "status": "WARN",
            "detail": f"Mask contour extracted but EE-4 trace validation failed: {exc}",
            "candidate": None,
            "ee4_trace_candidate": None,
        }

    return {
        "status": "PASS",
        "detail": (
            "Target roof mask contour extracted. Review and paste the YAML "
            "only after confirming it matches the aerial image."
        ),
        "candidate": {
            "source": contour.source,
            "vertex_count": len(vertices),
            "area_sqft": round(float(contour.area_sqft), 1),
            "vertices_ft": vertices,
            "component_bbox_px": list(component.bbox),
            "component_area_px": component.area_px,
            "alignment_mode": alignment.mode,
        },
        "ee4_trace_candidate": trace.model_dump(mode="json", exclude_none=True),
        "review_notes": [
            "Review-only candidate; not applied to inputs.yaml automatically.",
            "Roof facets, ridges/hips/valleys, fire pathways, and obstructions still need designer review.",
            "DSM is not yet decoded in the current cache, so pitch/facet inference is not part of T2.",
        ],
        "_contour_object": contour,
    }


def format_satellite_data_chain_markdown(payload: dict[str, Any]) -> str:
    layers = payload.get("layers") or {}
    target = payload.get("target_component") or {}
    lines = [
        "# Satellite Data Chain Audit",
        "",
        f"- Status: {payload.get('status', 'WARN')}",
        f"- Detail: {payload.get('detail', '-')}",
        f"- Address: {payload.get('address') or '-'}",
        f"- Coordinates: {payload.get('coordinates') or '-'}",
        f"- Radius: {payload.get('radius_m', '-')} m",
        f"- Requested pixel size: {payload.get('requested_pixel_size_m', '-')} m/px",
        f"- Estimated pixel size: {payload.get('estimated_pixel_size_m', '-')} m/px",
        "",
        "## Layers",
        "",
    ]
    for name in ("rgb", "mask", "annual_flux", "dsm"):
        info = layers.get(name) or {}
        available = "yes" if info.get("available") else "no"
        shape = info.get("shape") or "-"
        extra = info.get("reason") or info.get("unit") or ""
        lines.append(f"- {name}: {available}; shape={shape}; {extra}".rstrip())
    lines.extend([
        "",
        "## Target Component",
        "",
        f"- Available: {'yes' if target.get('available') else 'no'}",
    ])
    if target.get("available"):
        lines.extend([
            f"- Component count in mask: {target.get('component_count')}",
            f"- Target bbox px: {target.get('bbox_px')}",
            f"- Target component area px: {target.get('area_px')}",
            f"- Target pixel: {target.get('target_px')}",
        ])
    return "\n".join(lines) + "\n"


def _apply_alignment(
    candidate: MaskContourCandidate,
    *,
    house_bbox_ft: tuple[float, float, float, float],
    center_site_ft: tuple[float, float],
    alignment,
) -> MaskContourCandidate:
    origin = center_site_ft
    if alignment.mode == "fit_house_bbox":
        candidate = fit_candidate_to_bbox(
            candidate,
            house_bbox_ft,
            preserve_aspect=False,
            source_suffix="fit_house_bbox",
        )
        x0, y0, x1, y1 = house_bbox_ft
        origin = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)

    needs_manual = (
        alignment.mode == "manual"
        or abs(alignment.scale_x - 1.0) > 1e-9
        or abs(alignment.scale_y - 1.0) > 1e-9
        or abs(alignment.rotation_deg) > 1e-9
        or abs(alignment.x_offset_ft) > 1e-9
        or abs(alignment.y_offset_ft) > 1e-9
    )
    if needs_manual:
        candidate = transform_candidate(
            candidate,
            origin_ft=origin,
            scale_x=alignment.scale_x,
            scale_y=alignment.scale_y,
            rotation_deg=alignment.rotation_deg,
            offset_ft=(alignment.x_offset_ft, alignment.y_offset_ft),
            source_suffix="manual",
        )
    return candidate


def _trace_from_candidate_payload(payload: dict[str, Any]) -> EE4Trace | None:
    data = payload.get("ee4_trace_candidate")
    if not isinstance(data, dict):
        return None
    return EE4Trace.model_validate(data)


def _round_vertices(vertices: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return [
        (round(float(x), 2), round(float(y), 2))
        for x, y in vertices
    ]


def _write_outline_preview_png(
    assets: SatelliteAssets,
    component: TargetMaskComponent,
    contour: MaskContourCandidate,
    out_path: Path,
    *,
    underlay_json_path: Path | None = None,
) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rgb = np.asarray(assets.rgb).astype("uint8")
    if rgb.ndim != 3 or rgb.shape[2] < 3:
        rgb = np.zeros((*component.mask.shape, 3), dtype=np.uint8)
    y0, x0, y1, x1 = component.bbox
    side_hint = max(x1 - x0, y1 - y0)
    pad = max(14, int(round(side_hint * 0.25)))
    h, w = component.mask.shape
    crop_x0 = max(0, x0 - pad)
    crop_y0 = max(0, y0 - pad)
    crop_x1 = min(w, x1 + pad)
    crop_y1 = min(h, y1 + pad)

    crop = Image.fromarray(
        rgb[crop_y0:crop_y1, crop_x0:crop_x1, :3],
        mode="RGB",
    ).convert("RGBA")
    mask_crop = component.mask[crop_y0:crop_y1, crop_x0:crop_x1]
    overlay = np.zeros((crop.height, crop.width, 4), dtype=np.uint8)
    overlay[mask_crop] = np.array([34, 197, 94, 58], dtype=np.uint8)
    crop = Image.alpha_composite(crop, Image.fromarray(overlay, mode="RGBA"))
    draw = ImageDraw.Draw(crop)

    pts = [
        (float(px) - crop_x0, float(py) - crop_y0)
        for px, py in contour.pixel_vertices
    ]
    if len(pts) >= 3:
        draw.line(pts + [pts[0]], fill=(22, 163, 74, 255), width=3)
    tx, ty = component.target_px
    tx -= crop_x0
    ty -= crop_y0
    radius = max(8, min(crop.width, crop.height) * 0.055)
    draw.ellipse(
        (tx - radius, ty - radius, tx + radius, ty + radius),
        outline=(220, 38, 38, 255),
        width=3,
    )
    draw.line((tx - radius * 0.55, ty, tx + radius * 0.55, ty),
              fill=(220, 38, 38, 255), width=2)
    draw.line((tx, ty - radius * 0.55, tx, ty + radius * 0.55),
              fill=(220, 38, 38, 255), width=2)

    crop.convert("RGB").save(out_path)
    if underlay_json_path is not None:
        placement = _underlay_placement_from_crop(
            contour,
            crop_px=(crop_x0, crop_y0, crop_x1, crop_y1),
            image_size_px=(crop.width, crop.height),
        )
        underlay_json_path.write_text(
            json.dumps(placement, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return out_path


def _underlay_placement_from_crop(
    contour: MaskContourCandidate,
    *,
    crop_px: tuple[int, int, int, int],
    image_size_px: tuple[int, int],
) -> dict[str, Any]:
    """Map the cropped preview PNG into the site feet coordinate frame."""
    pxs = [pt[0] for pt in contour.pixel_vertices]
    pys = [pt[1] for pt in contour.pixel_vertices]
    sxs = [pt[0] for pt in contour.site_vertices_ft]
    sys = [pt[1] for pt in contour.site_vertices_ft]
    px0, px1 = min(pxs), max(pxs)
    py0, py1 = min(pys), max(pys)
    sx0, sx1 = min(sxs), max(sxs)
    sy0, sy1 = min(sys), max(sys)
    crop_x0, crop_y0, crop_x1, crop_y1 = crop_px
    scale_x = (sx1 - sx0) / max(px1 - px0, 1e-9)
    scale_y = (sy1 - sy0) / max(py1 - py0, 1e-9)
    x_min = sx0 - (px0 - crop_x0) * scale_x
    x_max = sx1 + (crop_x1 - px1) * scale_x
    # Pixel y increases downward; site y increases upward.
    y_max = sy1 + (py0 - crop_y0) * scale_y
    y_min = sy0 - (crop_y1 - py1) * scale_y
    return {
        "source": contour.source,
        "insert_ft": [round(float(x_min), 3), round(float(y_min), 3)],
        "size_ft": [
            round(float(x_max - x_min), 3),
            round(float(y_max - y_min), 3),
        ],
        "image_size_px": [int(image_size_px[0]), int(image_size_px[1])],
        "crop_px": [int(crop_x0), int(crop_y0), int(crop_x1), int(crop_y1)],
    }
