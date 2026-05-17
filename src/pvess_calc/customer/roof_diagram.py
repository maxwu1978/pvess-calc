"""K.3c sidekick — rooftop visualization from address.

Renders a 2-panel PNG diagram of every roof face Google Solar returned:

  ┌──────────────────────────────────────────────────────────┐
  │  Roof analysis — <address>                              │
  │  N faces, A m² total, NREL X kWh/kW · imagery YYYY-MM   │
  │  ┌─────────────────┐   ┌─────────────────────────────┐  │
  │  │  COMPASS ROSE   │   │  BAR CHART, sorted by       │  │
  │  │   each face =   │   │  orientation × shading      │  │
  │  │   wedge by az,  │   │  derate (best at top).      │  │
  │  │   length = area,│   │  Colour = derate (R→G).     │  │
  │  │   colour=derate │   │  Length = face area (ft²).  │  │
  │  └─────────────────┘   └─────────────────────────────┘  │
  └──────────────────────────────────────────────────────────┘

Driven entirely by the dict-list emitted by `lookup.providers.google_solar`
— no project yaml required. Bring just the address.

Why this isn't part of the permit PDF: PV-4 (attachment plan) lives in
the permit pipeline and assumes a fully-distributed yaml with
`module_count` per face. This module is the upstream cousin — a sales /
quoting tool that runs the moment K.3c resolves.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import matplotlib
matplotlib.use("Agg")   # non-interactive (no DISPLAY needed)
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import cm
from matplotlib.colors import Normalize

from ..calc.orientation import orientation_derate, resolve_shading_factor


# Each compass label gets a derate sanity hint in the docstring of the
# function — keep the colour map sympathetic to real-world quality:
#   derate ≥ 0.95 → emerald (premium S-facing latitude tilt)
#   derate 0.80   → yellow (W / E)
#   derate 0.50   → orange (steep N-facing)
#   derate ≤ 0.30 → deep red (sub-arctic-grade)
_DERATE_CMAP = cm.RdYlGn
_DERATE_NORM = Normalize(vmin=0.30, vmax=1.00)


@dataclass
class FaceVis:
    """Light view-model — what the renderer needs from one face."""
    name: str
    azimuth_deg: float
    pitch_deg: float
    area_ft2: float
    derate: float            # orientation × shading combined
    orientation_derate: float
    shading_factor: float


def _build_vis(
    roof_sections: Sequence[dict],
    *,
    urban_density: str = "unknown",
) -> list[FaceVis]:
    """Convert K.3c roof_sections dicts → FaceVis view-models. Computes
    orientation × shading derate using the same code path the K.8
    engine uses, so visualization and calc never disagree."""
    out: list[FaceVis] = []
    for s in roof_sections:
        w = float(s.get("width_ft", 0))
        h = float(s.get("height_ft", 0))
        area = w * h
        az = float(s.get("azimuth_deg", 180))
        pitch = float(s.get("pitch_deg", 22))
        face_shading = float(s.get("shading_factor", 1.0))
        od = orientation_derate(az, pitch)
        sh = resolve_shading_factor(face_shading, urban_density)
        out.append(FaceVis(
            name=s.get("name", "Unnamed Face"),
            azimuth_deg=az, pitch_deg=pitch, area_ft2=area,
            derate=od * sh, orientation_derate=od, shading_factor=sh,
        ))
    return out


def render_roof_diagram(
    roof_sections: Sequence[dict],
    out_path: Path,
    *,
    title: str = "Roof analysis",
    subtitle: str = "",
    urban_density: str = "unknown",
    dpi: int = 150,
) -> Path:
    """Render the 2-panel diagram + write to `out_path` (PNG).

    Returns the absolute path written.
    """
    faces = _build_vis(roof_sections, urban_density=urban_density)
    if not faces:
        raise ValueError("render_roof_diagram: empty roof_sections — "
                         "did Google Solar return zero segments?")

    # Figure size scales with face count: more faces need taller bars
    # panel so the y-tick labels don't crowd. 14 in wide stays; 8 in
    # tall for ≤ 6 faces, +0.4 per additional face up to a 14 in cap.
    n = len(faces)
    fig_height = min(14.0, max(8.0, 6.0 + 0.4 * n))
    fig = plt.figure(figsize=(14, fig_height))
    # 2-column layout: left = compass rose, right = bar chart.
    ax_polar = fig.add_subplot(1, 2, 1, projection="polar")
    ax_bar = fig.add_subplot(1, 2, 2)

    _draw_compass_rose(ax_polar, faces)
    _draw_face_bars(ax_bar, faces)

    # Top title strip.
    fig.suptitle(title, fontsize=15, fontweight="bold", y=0.97)
    if subtitle:
        fig.text(0.5, 0.92, subtitle, ha="center", fontsize=10,
                 color="#475569")

    # Footer note: how derate was computed.
    fig.text(
        0.5, 0.015,
        "Derate = Sandia 30°-45° lat orientation table × site-density "
        "shading factor.  Areas are sqrt-of-Google-Solar segment area "
        "(designer fine-tunes per site survey).",
        ha="center", fontsize=8, color="#64748b",
    )

    fig.tight_layout(rect=(0, 0.03, 1, 0.91))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    return out_path.absolute()


# ─── Panel renderers ───────────────────────────────────────────────────


def _draw_compass_rose(ax, faces: list[FaceVis]) -> None:
    """Polar bar chart: each face at its azimuth, bar length proportional
    to area, colour by derate. Compass labels N/E/S/W at perimeter."""
    # Standard compass convention: 0° at TOP (north), clockwise.
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)

    # Bars: position at azimuth, bar width spans a small wedge so
    # adjacent faces don't overlap visually.
    max_area = max(f.area_ft2 for f in faces) or 1.0
    bar_width = np.deg2rad(18)   # 18° wedges; 20+ overlap on dense roofs
    for f in faces:
        theta = np.deg2rad(f.azimuth_deg)
        height = f.area_ft2
        colour = _DERATE_CMAP(_DERATE_NORM(f.derate))
        ax.bar(theta, height, width=bar_width, bottom=0,
               color=colour, alpha=0.85,
               edgecolor="#1f2937", linewidth=0.6)

    # Compass axis labels.
    ax.set_xticks(np.deg2rad([0, 45, 90, 135, 180, 225, 270, 315]))
    ax.set_xticklabels(
        ["N", "NE", "E", "SE", "S", "SW", "W", "NW"],
        fontsize=11, fontweight="bold",
    )
    # Hide radial labels (they'd just say ft²; not informative on a
    # crowded polar plot).
    ax.set_yticks([max_area * 0.5, max_area])
    ax.set_yticklabels([f"{int(max_area * 0.5)}", f"{int(max_area)} ft²"],
                       fontsize=7, color="#94a3b8")
    ax.set_rlabel_position(135)

    # `pad=28` keeps the title clear of the N compass label even when
    # the polar bars push to max-area (overlap reported 2026-05-16).
    ax.set_title("By orientation", fontsize=11, pad=28,
                 color="#1f2937", fontweight="600")

    # Add a colourbar inset for the derate scale.
    cbar = plt.colorbar(
        cm.ScalarMappable(norm=_DERATE_NORM, cmap=_DERATE_CMAP),
        ax=ax, fraction=0.04, pad=0.10,
        ticks=[0.3, 0.5, 0.7, 0.9, 1.0],
    )
    cbar.ax.set_yticklabels(["30%", "50%", "70%", "90%", "100%"],
                            fontsize=8)
    cbar.set_label("Orientation × shading derate", fontsize=9,
                   color="#475569")


def _draw_face_bars(ax, faces: list[FaceVis]) -> None:
    """Horizontal bar chart: each face ranked by derate (best at top).
    Bar length = area ft²; colour = derate.

    Label layout (post 2026-05-16 v2 polish):
      * Y-axis tick: ONE LINE — face name only. Compact, no wrap.
      * Right-of-bar annotation (single block):
            "412 ft²  ·  22° / 178°  ·  96%"
        — area, pitch/azimuth, derate all together. Single source of
        truth keeps wide and narrow panels equally readable.

    Pre-v2 history: an "inline white pitch/az hint" lived ON the bar
    fill, which looked clean on the wide single-panel layout but
    collided with y-tick face names on the narrower bar panel inside
    the 2×2 satellite layout. The v2 fix is to drop the inline hint
    entirely and concentrate the metadata on one outside-right column
    — no double-printing, no panel-width sensitivity.
    """
    # Sort best → worst, top of chart = best (so we plot in reverse).
    faces_sorted = sorted(faces, key=lambda f: f.derate)

    y = np.arange(len(faces_sorted))
    colours = [_DERATE_CMAP(_DERATE_NORM(f.derate)) for f in faces_sorted]
    widths = [f.area_ft2 for f in faces_sorted]
    bar_height = 0.72   # < 1.0 leaves whitespace between rows
    ax.barh(y, widths, height=bar_height,
            color=colours, edgecolor="#1f2937", linewidth=0.6,
            alpha=0.85)

    # Y-axis: face name only, single line.
    ax.set_yticks(y)
    ax.set_yticklabels([f.name for f in faces_sorted],
                       fontsize=9, color="#1f2937")
    # Y-tick padding so the bar doesn't kiss the label.
    ax.tick_params(axis="y", pad=4)

    # Single outside-right annotation per bar: area · pitch/az · derate.
    for i, f in enumerate(faces_sorted):
        ax.annotate(
            f"{f.area_ft2:.0f} ft²   ·   {f.pitch_deg:.0f}° / "
            f"{f.azimuth_deg:.0f}°   ·   {f.derate*100:.0f}%",
            xy=(f.area_ft2, i), xytext=(8, 0),
            textcoords="offset points", va="center",
            fontsize=8.5, color="#1f2937",
        )

    # Cosmetics.
    ax.set_xlabel("Face area (ft²)", fontsize=10, color="#475569")
    ax.set_title("Ranked by derate (best on top)", fontsize=11,
                 color="#1f2937", fontweight="600", pad=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", color="#e5e7eb", linewidth=0.5, alpha=0.6)
    ax.set_axisbelow(True)
    # Pad x-limit so the longer annotation ("999 ft²  ·  90° / 359°
    # ·  100%") fits without truncation. 50 % padding tested with
    # 13-face Frisco roof at multiple figsize ratios.
    if widths:
        ax.set_xlim(0, max(widths) * 1.50)
    # Pad y-limits so the top + bottom bars aren't flush against the
    # axes (matches the bar_height < 1 visual gap).
    ax.set_ylim(-0.6, len(faces_sorted) - 0.4)


# ─── Convenience entry: from a raw address ────────────────────────────


def render_from_address(
    address: str,
    out_path: Path,
    *,
    urban_density: str = "unknown",
) -> Optional[Path]:
    """End-to-end helper: run the lookup chain on `address`, pull the
    google_solar block out of the result, render the diagram.

    Returns the written path on success, or None when Google Solar
    didn't contribute (missing key / no building / network down) —
    caller can decide whether to abort or fall back.
    """
    from ..lookup import resolve
    r = resolve(address)
    roof_sections = r.fields.get("roof_sections")
    if not roof_sections:
        return None

    quality = r.fields.get("google_solar_imagery_quality", "—")
    imagery_date = r.fields.get("google_solar_imagery_date", "—")
    annual_kwh_per_kw = r.fields.get("annual_energy_kwh_per_kw", None)
    whole_area = r.fields.get("google_solar_whole_roof_area_m2", None)
    canonical = r.fields.get("canonical_address", address)

    # Build the subtitle line.
    subtitle_parts = [f"{len(roof_sections)} faces"]
    if whole_area is not None:
        subtitle_parts.append(f"{whole_area:.1f} m² total roof")
    if annual_kwh_per_kw is not None:
        subtitle_parts.append(f"NREL {annual_kwh_per_kw:.0f} kWh/kW/yr")
    subtitle_parts.append(f"Google Solar {quality}, imagery {imagery_date}")
    subtitle = "   ·   ".join(subtitle_parts)

    return render_roof_diagram(
        roof_sections, out_path,
        title=f"Roof analysis — {canonical}",
        subtitle=subtitle,
        urban_density=urban_density,
    )
