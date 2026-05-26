"""K.3c+ — satellite + flux overlay variant of the rooftop diagram.

Distinct from the analytical `roof_diagram.py` because:

  * **Network-heavy**: $0.50 per dataLayers:get call + ~3-5 MB of
    GeoTIFFs downloaded. Costs add up over a sales cycle, so this is
    NOT the default path.
  * **Doesn't degrade gracefully**: needs a Google Solar key; needs
    the building to be in coverage; doesn't fall back to a "you have
    a roof somewhere" diagram. Caller (CLI) must gate access.
  * **Designed for signed clients**: per-call cost is high relative to
    a tire-kicker lead; sales gate is `--satellite` opt-in + a price
    confirmation prompt.

The 2×2 layout:

  ┌────────────────────────────────────────────────────────────┐
  │  Roof analysis — <address>                                 │
  │  imagery 2024-02-06 HIGH, N faces, NREL X kWh/kW/yr        │
  │                                                            │
  │  ┌───────────────┐  ┌───────────────────────────────────┐  │
  │  │ RGB           │  │  Compass rose                     │  │
  │  │ (real photo)  │  │  (orientation × derate)           │  │
  │  └───────────────┘  └───────────────────────────────────┘  │
  │                                                            │
  │  ┌───────────────┐  ┌───────────────────────────────────┐  │
  │  │ ANNUAL FLUX   │  │  Bar chart, ranked by derate      │  │
  │  │ (kWh/m²/yr,   │  │  (face area on x-axis)            │  │
  │  │  masked to    │  │                                   │  │
  │  │  building)    │  │                                   │  │
  │  └───────────────┘  └───────────────────────────────────┘  │
  └────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import cm
from matplotlib.colors import Normalize
from PIL import Image

from ..lookup.providers.google_solar_data_layers import (
    DataLayersError,
    DataLayersResult,
    download_layer_bytes,
    fetch_data_layers,
)
from .roof_diagram import (
    FaceVis,
    _build_vis,
    _draw_compass_rose,
    _draw_face_bars,
)


# Annual flux colormap. Hot tones (red-yellow) for high-irradiance
# pixels, cool (blue-purple) for shaded — same convention Google's
# Project Sunroof and the Aurora Solar tools use, so the visual
# language is familiar to anyone who's seen a solar heat map.
_FLUX_CMAP = cm.inferno
# Annual flux range in kWh/m²/yr. Realistic residential values span
# 200-1800 across the US; clip at these bounds so the heatmap doesn't
# get squashed by one obstruction-dark pixel or an over-bright cap.
_FLUX_CLIP_MIN_KWH = 200.0
_FLUX_CLIP_MAX_KWH = 1800.0


@dataclass
class SatelliteAssets:
    """Decoded image arrays ready to plot. Separating fetch from
    render lets tests inject fake arrays without needing to mock
    full GeoTIFF bytes."""
    rgb: np.ndarray              # (H, W, 3) uint8
    annual_flux: np.ndarray      # (H, W) float32 kWh/m²/yr
    mask: np.ndarray             # (H, W) bool — True = roof
    imagery_date: str
    imagery_quality: str
    target_px: Optional[tuple[float, float]] = None


@dataclass(frozen=True)
class TargetMaskComponent:
    """Connected Google Solar mask component selected for the project roof."""
    mask: np.ndarray
    bbox: tuple[int, int, int, int]  # y0, x0, y1, x1
    area_px: int
    component_count: int
    target_px: tuple[float, float]
    distance_px2: float


def _decode_tiff(buf: bytes) -> np.ndarray:
    """Bytes → numpy array via Pillow. Handles single-band float32
    (flux) AND 3-band uint8 (RGB) AND single-band uint8 (mask)."""
    img = Image.open(io.BytesIO(buf))
    arr = np.array(img)
    # Some Google GeoTIFFs come back as (H, W, 3) but with bands stored
    # in a non-standard order; Pillow handles the common cases. For
    # single-band float32 the result is (H, W) float; for mask uint8
    # it's (H, W) uint8 (cast to bool downstream).
    return arr


def fetch_satellite_assets(
    lat: float, lng: float, *,
    radius_m: float = 25.0,
    pixel_size_m: float = 0.25,
    api_key: Optional[str] = None,
) -> SatelliteAssets:
    """End-to-end network helper: dataLayers:get → download 3 layers →
    decode → return ready-to-plot arrays. Costs $0.50 + ~3-5 MB
    bandwidth in production. Default 25 m radius / 0.25 m pixels keeps
    the target building centred in dense subdivisions; bump radius for
    rural lots where the property fills more space.
    """
    layers: DataLayersResult = fetch_data_layers(
        lat, lng, radius_m=radius_m,
        pixel_size_m=pixel_size_m, api_key=api_key,
    )
    if not layers.rgb_url or not layers.annual_flux_url or not layers.mask_url:
        raise DataLayersError(
            "dataLayers response missing rgb/annualFlux/mask — "
            "the `view` parameter may not have requested all 3 layers."
        )
    rgb_bytes = download_layer_bytes(layers.rgb_url, api_key=api_key)
    flux_bytes = download_layer_bytes(layers.annual_flux_url, api_key=api_key)
    mask_bytes = download_layer_bytes(layers.mask_url, api_key=api_key)

    rgb = _decode_tiff(rgb_bytes)
    flux = _decode_tiff(flux_bytes).astype(np.float32)
    mask_raw = _decode_tiff(mask_bytes)
    mask = mask_raw.astype(bool) if mask_raw.ndim == 2 else mask_raw[..., 0].astype(bool)

    return SatelliteAssets(
        rgb=rgb, annual_flux=flux, mask=mask,
        imagery_date=layers.imagery_date or "—",
        imagery_quality=layers.imagery_quality,
    )


def render_satellite_diagram(
    roof_sections: Sequence[dict],
    assets: SatelliteAssets,
    out_path: Path,
    *,
    title: str = "Roof analysis (satellite)",
    subtitle: str = "",
    urban_density: str = "unknown",
    dpi: int = 150,
) -> Path:
    """Render the 2x2 figure. Take assets pre-fetched — tests pass
    synthetic arrays, the CLI passes the real Google Solar response."""
    faces = _build_vis(roof_sections, urban_density=urban_density)
    if not faces:
        raise ValueError(
            "render_satellite_diagram: empty roof_sections — "
            "buildingInsights returned nothing to overlay"
        )

    # Same scaling rule as roof_diagram: taller figure as N grows so
    # the bar panel can breathe. Satellite version starts taller (15×11
    # for ≤6 faces) because each panel column has 2 panels stacked.
    n = len(faces)
    fig_height = min(16.0, max(11.0, 9.0 + 0.4 * n))
    # 18 in wide (vs 15 pre-polish) gives the bar panel enough room for
    # the new long single-line annotation "412 ft²  ·  34° / 180°  ·  96%"
    # without the y-tick face names getting visually clipped at the
    # left edge of the bar panel. width_ratios[1] = 1.4 biases space
    # toward the bar panel (which has more text to render than the
    # imagery panel — square photos don't need extra width).
    fig = plt.figure(figsize=(18, fig_height))
    gs = fig.add_gridspec(2, 2, width_ratios=[1, 1.4], hspace=0.18, wspace=0.12)

    ax_rgb = fig.add_subplot(gs[0, 0])
    ax_flux = fig.add_subplot(gs[1, 0])
    ax_compass = fig.add_subplot(gs[0, 1], projection="polar")
    ax_bars = fig.add_subplot(gs[1, 1])

    _draw_rgb(ax_rgb, assets)
    _draw_flux(ax_flux, assets)
    _draw_compass_rose(ax_compass, faces)
    _draw_face_bars(ax_bars, faces)

    fig.suptitle(title, fontsize=15, fontweight="bold", y=0.97)
    if subtitle:
        fig.text(0.5, 0.93, subtitle, ha="center", fontsize=10,
                 color="#475569")

    fig.text(
        0.5, 0.012,
        "Imagery + flux: Google Solar dataLayers (~$0.50 per render).  "
        "Compass + bars: Sandia 30°-45° lat orientation table × site-density shading.",
        ha="center", fontsize=8, color="#64748b",
    )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path.absolute()


def crop_satellite_assets_to_target(
    assets: SatelliteAssets,
    *,
    padding_ratio: float = 0.20,
    min_padding_px: int = 12,
    min_side_px: int = 72,
) -> SatelliteAssets:
    """Crop Google Solar layers around the target building mask.

    The raw dataLayers frame is a square around the geocoded lat/lng, which
    often includes several neighboring homes in dense subdivisions. For the
    R8 review step, the useful view is the connected roof-mask component that
    contains, or is nearest to, the target center point.
    """
    mask = np.asarray(assets.mask).astype(bool)
    if mask.ndim != 2 or not mask.any():
        return assets
    if assets.rgb.shape[:2] != mask.shape or assets.annual_flux.shape[:2] != mask.shape:
        return assets

    component = target_component_from_mask(mask, assets.target_px)
    if component is None:
        return assets
    bbox = component.bbox
    y0, x0, y1, x1 = bbox
    h, w = mask.shape
    target_x, target_y = component.target_px
    side_hint = max(x1 - x0, y1 - y0)
    pad = max(min_padding_px, int(round(side_hint * padding_ratio)))

    crop_x0 = max(0, min(x0 - pad, int(target_x) - pad))
    crop_y0 = max(0, min(y0 - pad, int(target_y) - pad))
    crop_x1 = min(w, max(x1 + pad, int(target_x) + pad))
    crop_y1 = min(h, max(y1 + pad, int(target_y) + pad))
    crop_x0, crop_x1 = _expand_interval(crop_x0, crop_x1, w, min_side_px)
    crop_y0, crop_y1 = _expand_interval(crop_y0, crop_y1, h, min_side_px)

    if (crop_x1 - crop_x0) >= w * 0.92 and (crop_y1 - crop_y0) >= h * 0.92:
        return assets

    return SatelliteAssets(
        rgb=assets.rgb[crop_y0:crop_y1, crop_x0:crop_x1, :],
        annual_flux=assets.annual_flux[crop_y0:crop_y1, crop_x0:crop_x1],
        mask=component.mask[crop_y0:crop_y1, crop_x0:crop_x1],
        imagery_date=assets.imagery_date,
        imagery_quality=assets.imagery_quality,
        target_px=(target_x - crop_x0, target_y - crop_y0),
    )


def target_component_from_mask(
    mask: np.ndarray,
    target_px: Optional[tuple[float, float]] = None,
) -> TargetMaskComponent | None:
    """Return the mask component containing/nearest the target point.

    Google Solar dataLayers frames often include neighboring roofs. The
    project roof is the connected component that contains the geocoded target
    pixel, falling back to nearest component and then larger area when the
    point lands in a small gap.
    """
    arr = np.asarray(mask).astype(bool)
    if arr.ndim != 2 or not arr.any():
        return None
    h, w = arr.shape
    target_x, target_y = target_px or (w / 2.0, h / 2.0)
    visited = np.zeros(arr.shape, dtype=bool)
    best: tuple[
        tuple[float, int],
        tuple[int, int, int, int],
        int,
        list[tuple[int, int]],
    ] | None = None
    component_count = 0
    for y in range(h):
        for x in range(w):
            if not arr[y, x] or visited[y, x]:
                continue
            bbox, area, pixels = _flood_component(arr, visited, x, y)
            component_count += 1
            y0, x0, y1, x1 = bbox
            distance = _distance_to_bbox(target_x, target_y, x0, y0, x1, y1)
            score = (distance, -area)
            if best is None or score < best[0]:
                best = (score, bbox, area, pixels)
    if best is None:
        return None
    score, bbox, area, pixels = best
    component_mask = np.zeros(arr.shape, dtype=bool)
    for px, py in pixels:
        component_mask[py, px] = True
    return TargetMaskComponent(
        mask=component_mask,
        bbox=bbox,
        area_px=area,
        component_count=component_count,
        target_px=(target_x, target_y),
        distance_px2=score[0],
    )


def _target_component_bbox(
    mask: np.ndarray,
    target_px: Optional[tuple[float, float]] = None,
) -> tuple[int, int, int, int] | None:
    component = target_component_from_mask(mask, target_px)
    return component.bbox if component is not None else None


def _flood_component(
    mask: np.ndarray,
    visited: np.ndarray,
    start_x: int,
    start_y: int,
) -> tuple[tuple[int, int, int, int], int, list[tuple[int, int]]]:
    h, w = mask.shape
    stack = [(start_x, start_y)]
    visited[start_y, start_x] = True
    min_x = max_x = start_x
    min_y = max_y = start_y
    area = 0
    pixels: list[tuple[int, int]] = []
    while stack:
        x, y = stack.pop()
        area += 1
        pixels.append((x, y))
        min_x = min(min_x, x)
        max_x = max(max_x, x)
        min_y = min(min_y, y)
        max_y = max(max_y, y)
        for ny in range(max(0, y - 1), min(h, y + 2)):
            for nx in range(max(0, x - 1), min(w, x + 2)):
                if visited[ny, nx] or not mask[ny, nx]:
                    continue
                visited[ny, nx] = True
                stack.append((nx, ny))
    return (min_y, min_x, max_y + 1, max_x + 1), area, pixels


def _distance_to_bbox(
    x: float,
    y: float,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
) -> float:
    dx = 0.0 if x0 <= x < x1 else min(abs(x - x0), abs(x - (x1 - 1)))
    dy = 0.0 if y0 <= y < y1 else min(abs(y - y0), abs(y - (y1 - 1)))
    return dx * dx + dy * dy


def _expand_interval(start: int, end: int, limit: int, minimum: int) -> tuple[int, int]:
    size = end - start
    if size >= minimum or size >= limit:
        return start, end
    extra = minimum - size
    left = extra // 2
    right = extra - left
    start = max(0, start - left)
    end = min(limit, end + right)
    if end - start < minimum:
        if start == 0:
            end = min(limit, minimum)
        elif end == limit:
            start = max(0, limit - minimum)
    return start, end


# ─── Panel renderers ───────────────────────────────────────────────────


def _draw_target_marker(
    ax,
    h: int,
    w: int,
    target_px: Optional[tuple[float, float]] = None,
) -> None:
    """Pin the target building's lat/lng centre with a red ring + cross.
    Critical UX: in dense subdivisions a 50 m × 50 m frame still shows
    3-5 neighbouring houses, and without a marker the viewer can't
    identify the actual project. The centre is by construction
    Google's reported lat/lng (= Mapbox-resolved address) ± half a
    pixel of round-off.
    """
    cx, cy = target_px or (w / 2.0, h / 2.0)
    # Outer ring — large enough to stand out, thin enough not to obscure
    # the target itself.
    ax.add_patch(plt.Circle(
        (cx, cy), radius=max(8, min(h, w) * 0.06),
        edgecolor="#dc2626", facecolor="none",
        linewidth=1.8, zorder=5,
    ))
    # Inner crosshair: short lines so the centre pixel stays visible.
    cross_len = max(4, min(h, w) * 0.03)
    ax.plot([cx - cross_len, cx + cross_len], [cy, cy],
            color="#dc2626", linewidth=1.4, zorder=5)
    ax.plot([cx, cx], [cy - cross_len, cy + cross_len],
            color="#dc2626", linewidth=1.4, zorder=5)
    # Tiny inner dot so the exact centre is unambiguous.
    ax.plot(cx, cy, marker=".", markersize=3,
            color="#dc2626", zorder=6)


def _draw_rgb(ax, assets: SatelliteAssets) -> None:
    ax.imshow(assets.rgb)
    h, w = assets.rgb.shape[:2]
    _draw_target_marker(ax, h, w, assets.target_px)
    ax.set_title(
        f"Aerial imagery  ·  {assets.imagery_date}  ·  {assets.imagery_quality}"
        "   (red = target lat/lng)",
        fontsize=10, color="#1f2937", pad=6,
    )
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color("#94a3b8")
        spine.set_linewidth(0.5)


def _draw_flux(ax, assets: SatelliteAssets) -> None:
    """Annual flux as a heatmap, masked to the building outline. Pixels
    outside the mask show through as a soft grey so the building
    silhouette stands out without being hard-clipped."""
    flux = np.clip(assets.annual_flux,
                   _FLUX_CLIP_MIN_KWH, _FLUX_CLIP_MAX_KWH)
    # Normalize for colormap.
    norm = Normalize(vmin=_FLUX_CLIP_MIN_KWH, vmax=_FLUX_CLIP_MAX_KWH)
    # Build an RGBA image from the colormap; punch out non-roof pixels
    # via the mask so background isn't a misleading colour blob.
    rgba = _FLUX_CMAP(norm(flux))
    rgba[..., 3] = np.where(assets.mask, 1.0, 0.18)   # roof opaque, ground faded

    ax.imshow(rgba)
    h, w = assets.annual_flux.shape[:2]
    _draw_target_marker(ax, h, w, assets.target_px)
    ax.set_title("Annual flux (kWh/m²/yr)  ·  building only",
                 fontsize=10, color="#1f2937", pad=6)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color("#94a3b8")
        spine.set_linewidth(0.5)

    # Colourbar — placed to the right of the panel so the layout stays
    # rectangular even when the flux extents differ from RGB.
    cbar = plt.colorbar(
        cm.ScalarMappable(norm=norm, cmap=_FLUX_CMAP),
        ax=ax, fraction=0.04, pad=0.02,
        ticks=[200, 600, 1000, 1400, 1800],
    )
    cbar.ax.tick_params(labelsize=7, colors="#475569")


# ─── End-to-end address entry ──────────────────────────────────────────


def render_from_address(
    address: str,
    out_path: Path,
    *,
    urban_density: str = "unknown",
    dpi: int = 150,
) -> Optional[Path]:
    """End-to-end: lookup address → buildingInsights face list → dataLayers
    fetch → render. Returns the written path, or None when the
    buildingInsights leg already had no roof_sections (saves a $0.50
    dataLayers call we'd waste anyway).

    Raises `DataLayersError` if buildingInsights succeeded but
    dataLayers failed — that's a paid-for crash and the caller
    deserves to know.
    """
    from ..lookup import resolve
    r = resolve(address)
    roof_sections = r.fields.get("roof_sections")
    if not roof_sections:
        return None

    lat = r.fields.get("latitude")
    lng = r.fields.get("longitude")
    if lat is None or lng is None:
        raise DataLayersError(
            "Mapbox didn't supply lat/lng — cannot call dataLayers."
        )

    assets = fetch_satellite_assets(float(lat), float(lng))

    quality = r.fields.get("google_solar_imagery_quality", "—")
    imagery_date = r.fields.get("google_solar_imagery_date",
                                assets.imagery_date)
    annual_kwh_per_kw = r.fields.get("annual_energy_kwh_per_kw")
    whole_area = r.fields.get("google_solar_whole_roof_area_m2")
    canonical = r.fields.get("canonical_address", address)

    subtitle_parts = [f"{len(roof_sections)} faces"]
    if whole_area is not None:
        subtitle_parts.append(f"{whole_area:.1f} m² total")
    if annual_kwh_per_kw is not None:
        subtitle_parts.append(f"NREL {annual_kwh_per_kw:.0f} kWh/kW/yr")
    subtitle_parts.append(f"imagery {imagery_date}, {quality}")
    subtitle = "   ·   ".join(subtitle_parts)

    return render_satellite_diagram(
        roof_sections, assets, out_path,
        title=f"Roof analysis — {canonical}",
        subtitle=subtitle,
        urban_density=urban_density,
        dpi=dpi,
    )
