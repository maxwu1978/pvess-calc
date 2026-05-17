"""K.8 — azimuth/tilt orientation derate for PV production.

Given a roof face's azimuth (compass direction) and tilt (pitch from
horizontal), return a multiplier 0..1 vs the "optimal" reference
orientation (south-facing, latitude tilt). Used to convert NREL
PVWatts's "annual_energy_kwh_per_kw" baseline (queried at south-facing
20° tilt) into a per-face number for multi-face arrays.

Math: this is the standard "Annual Solar Insolation Factor" used in
residential PV sizing — a coarse-but-honest table replacement for
running PVWatts N times. The table comes from the Sandia 2015
"Solar Tilt and Azimuth Factor" charts averaged across US latitudes
30°-45° (covers contiguous-US residential).

Caveats:
  * Single table covers all US lats; ≤5% error in any single cell.
  * Doesn't model partial shading (use `shading_factor` for that).
  * Doesn't account for snow / soiling losses (rolled into the PVWatts
    14% baseline loss factor).
  * For Alaska / Hawaii / Puerto Rico, the table is approximate;
    flag those cases with a future K.8.5 lat-bin extension.
"""
from __future__ import annotations


# Tilt × azimuth-offset-from-south derate table. Values are multipliers
# vs the reference: south-facing, latitude tilt (~30°) = 1.00.
# Rows: tilt 0° / 10° / 20° / 30° / 40° / 50° / 60° (typical residential
# pitches 14° = 4:12, 22° = 5:12, 27° = 6:12, 34° = 8:12, 45° = 12:12).
# Cols: azimuth offset from due south, 0° / 30° / 60° / 90° / 120° / 180°.
# Symmetric around south, so a 90° east-facing face uses the same value
# as 90° west.
_TILT_DEG = [0, 10, 20, 30, 40, 50, 60]
_AZIMUTH_OFFSET_DEG = [0, 30, 60, 90, 120, 150, 180]
_TABLE: list[list[float]] = [
    # 0° tilt (flat roof) — orientation doesn't matter much
    [0.89, 0.89, 0.89, 0.89, 0.89, 0.89, 0.89],
    # 10° tilt
    [0.95, 0.94, 0.92, 0.88, 0.83, 0.79, 0.77],
    # 20° tilt (~5:12, typical residential)
    [0.98, 0.97, 0.93, 0.86, 0.78, 0.70, 0.66],
    # 30° tilt (~7:12, latitude-tilt sweet spot)
    [1.00, 0.98, 0.92, 0.83, 0.71, 0.60, 0.55],
    # 40° tilt (~10:12, steep)
    [0.99, 0.97, 0.89, 0.78, 0.64, 0.51, 0.45],
    # 50° tilt
    [0.96, 0.94, 0.85, 0.72, 0.56, 0.43, 0.36],
    # 60° tilt (very steep, rare residential)
    [0.91, 0.88, 0.79, 0.65, 0.48, 0.35, 0.28],
]


def orientation_derate(
    azimuth_deg: float, tilt_deg: float,
) -> float:
    """Bilinear interpolation into the Sandia-style derate table.

    Args:
        azimuth_deg: 0..360, 180 = due south (US convention).
        tilt_deg: 0..90, 0 = flat, 90 = vertical wall.

    Returns:
        Multiplier in roughly [0.25, 1.00] applied to the reference
        production.  1.00 = south-facing at latitude tilt.
    """
    # Convert azimuth to "offset from south" in [0, 180] (symmetric).
    az_offset = abs(azimuth_deg - 180.0) % 360.0
    if az_offset > 180.0:
        az_offset = 360.0 - az_offset

    tilt = max(0.0, min(60.0, tilt_deg))

    # Bilinear interp: find bracketing rows + cols, weight by distance.
    def _bracket(value: float, breakpoints: list[float]) -> tuple[int, int, float]:
        """Returns (lower_idx, upper_idx, t) where t ∈ [0, 1] is the
        fractional position between the two breakpoints."""
        for i in range(len(breakpoints) - 1):
            if breakpoints[i] <= value <= breakpoints[i + 1]:
                lo, hi = breakpoints[i], breakpoints[i + 1]
                t = (value - lo) / (hi - lo) if hi > lo else 0.0
                return i, i + 1, t
        # Out of range — clamp to nearest edge
        if value <= breakpoints[0]:
            return 0, 0, 0.0
        return len(breakpoints) - 1, len(breakpoints) - 1, 0.0

    ti_lo, ti_hi, ti_t = _bracket(tilt, _TILT_DEG)
    ai_lo, ai_hi, ai_t = _bracket(az_offset, _AZIMUTH_OFFSET_DEG)

    v00 = _TABLE[ti_lo][ai_lo]
    v01 = _TABLE[ti_lo][ai_hi]
    v10 = _TABLE[ti_hi][ai_lo]
    v11 = _TABLE[ti_hi][ai_hi]

    # Bilinear: interpolate within row first, then between rows.
    v_lo = v00 * (1 - ai_t) + v01 * ai_t
    v_hi = v10 * (1 - ai_t) + v11 * ai_t
    return v_lo * (1 - ti_t) + v_hi * ti_t


# K.8: site-density default shading factor when a roof_section's
# `shading_factor` is left at the 1.0 "didn't measure" default. Rural
# = no obstructions; urban = typical-city partial shading.
DENSITY_DEFAULT_SHADING: dict[str, float] = {
    "rural":    1.00,
    "suburban": 0.96,
    "urban":    0.90,
    "unknown":  1.00,    # don't penalize when missing data
}


def resolve_shading_factor(
    face_shading: float, site_density: str,
) -> float:
    """Pick the effective shading factor for a face.

    Per-face value wins when it's been explicitly set (i.e. anything
    other than 1.0). When still at the 1.0 default, fall back to the
    site-density default — captures the "I didn't measure each face
    but I know it's a suburban lot" case.
    """
    if face_shading < 1.0:
        return face_shading
    return DENSITY_DEFAULT_SHADING.get(site_density, 1.0)
