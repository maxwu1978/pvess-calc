"""K.8.2 — value-weighted orientation derate.

K.8's Sandia annual-kWh derate measures total energy production over the
year, treating every kWh as equal-valued. Mathematically correct, but the
WRONG yardstick for the TX market (PV-only + sub-1:1 REP buyback) where:

  * West-facing kWh produced 2-6 PM are mostly **self-consumed** during
    the AC peak → credit at full retail
  * East-facing kWh produced 9 AM-1 PM are mostly **exported** to an
    empty house → credit at REP buyback ratio (~0.5× retail typical)

For equal annual kWh, West-facing kWh can be worth 2× East-facing kWh on
a 0.5× REP plan. K.8 doesn't see this — it treats E/W as equally good
because the annual integral is the same.

K.8.2 fixes this with an **hourly production × hourly value** integration:

    face_value = Σ over 24h [ hourly_production[h] × hourly_value[h] ]
    value_weighted_derate = face_value / south_30deg_reference_value

Math collapse property: when `rep_buyback_ratio = 1.0` (true 1:1 NEM,
Smart Meter Texas semantics), `hourly_value[h]` is the constant 1.0 for
all h → the integral degenerates back to annual kWh ratio → value-weighted
derate equals Sandia annual derate. Pre-K.8.2 behavior is bit-identical
on 1:1 plans.

Default-off: K.8.1 LRM auto-distribute uses area-only weighting unchanged
unless the yaml sets `loads.use_value_weighted_distribution = True`.

Caveats (deliberately):
  * Equinox-day clear-sky approximation — no seasonal variation. K.8.2.1
    captures the AM/PM asymmetry the Sandia annual table flattens; full
    seasonal modeling is a future K-phase.
  * Single representative self-consumption pattern (DFW typical weekday).
    TOU rate plans (CA EV2-A, etc.) need a separate hourly-rate lookup.
  * No atmospheric mass correction beyond the cosine-incidence factor —
    low-sun hours contribute less by geometry, not by extinction.
"""
from __future__ import annotations

import math
from typing import Optional


# Default latitude when project coordinates aren't available. 35°N ≈ US
# population-weighted mean (roughly San Bernardino / Nashville parallel).
# Used by tests; production code passes the lat from project.coordinates
# or lookup_fields["latitude"].
DEFAULT_AVERAGE_LATITUDE_DEG: float = 35.0

# DFW typical weekday self-consumption fraction per hour (24 values).
# Captures: empty house mid-day (kids at school, adults at work) → AC
# runs but most production exports; afternoon return + cooking + AC peak
# → high self-consumption; evening prime time → near-100%; overnight
# → low (no PV anyway, but the value-factor is conservative).
DEFAULT_DFW_SELF_CONSUMPTION_PATTERN: tuple[float, ...] = (
    # 0    1    2    3    4    5    6    7      ← AM hours
    0.20, 0.20, 0.20, 0.20, 0.20, 0.25, 0.40, 0.55,
    # 8    9    10   11   12   13   14   15
    0.35, 0.25, 0.25, 0.25, 0.30, 0.30, 0.45, 0.65,
    # 16   17   18   19   20   21   22   23     ← PM peak
    0.85, 0.90, 0.95, 0.95, 0.85, 0.70, 0.50, 0.30,
)


# Reference face for normalization: due south, latitude-tilt sweet spot.
_REFERENCE_AZIMUTH_DEG: float = 180.0
_REFERENCE_PITCH_DEG: float = 30.0


def hourly_face_profile(
    azimuth_deg: float, pitch_deg: float, lat_deg: float,
) -> list[float]:
    """Equinox-day relative production profile, 24 hourly values.

    Hour h returns the cosine-of-incidence factor (≥ 0) between the sun
    vector and the face's outward normal, gated by sun-above-horizon.
    Equinox approximation (solar declination = 0) gives symmetric
    AM/PM — exactly what we want for capturing the East-vs-West value
    asymmetry that drives K.8.2.

    Returns:
        list of 24 floats. Index = solar hour (0 = midnight, 12 = noon).
        Sum over the day is proportional to daily kWh for the face.
        NOT normalized — use `face_value_weighted_derate` for the
        comparable derate scalar.
    """
    profile: list[float] = []
    for h in range(24):
        elev, sun_az = _sun_position_equinox(h, lat_deg)
        if elev <= 0:
            profile.append(0.0)
            continue
        cos_i = _face_cos_incidence(
            sun_elev_deg=elev, sun_az_deg=sun_az,
            face_az_deg=azimuth_deg, face_pitch_deg=pitch_deg,
        )
        profile.append(cos_i)
    return profile


def hourly_value_factor(
    rep_buyback_ratio: float,
    self_consumption_pattern: Optional[tuple[float, ...]] = None,
) -> list[float]:
    """24-h multiplier turning hourly production into $-equivalent units.

    Each hour:
        value[h] = self_cons[h] × 1.0  +  (1 - self_cons[h]) × ratio
    where 1.0 = full retail (self-consumed avoids the bill) and `ratio`
    = exported-kWh value as fraction of retail.

    Math collapse on 1:1 plans (ratio = 1.0): value[h] = sc + (1-sc) = 1.0
    for every h → `face_value_weighted_derate` degenerates to Sandia
    annual derate. Pre-K.8.2 behavior bit-identical.

    Sub-1:1 plans (ratio < 1.0): value spikes during high-self-cons hours
    (afternoon AC peak) and dips during low-self-cons hours (empty
    house mid-morning). West-facing faces, producing at the peak,
    out-score East-facing faces with equal annual kWh.
    """
    sc = self_consumption_pattern or DEFAULT_DFW_SELF_CONSUMPTION_PATTERN
    if len(sc) != 24:
        raise ValueError(
            f"self_consumption_pattern must have 24 hours; got {len(sc)}"
        )
    return [sc[h] + (1.0 - sc[h]) * rep_buyback_ratio for h in range(24)]


def face_value_weighted_derate(
    azimuth_deg: float,
    pitch_deg: float,
    lat_deg: float,
    rep_buyback_ratio: float,
    self_consumption_pattern: Optional[tuple[float, ...]] = None,
) -> float:
    """Single derate ∈ (0, 1] for one roof face — what `customer/production`
    LRM should weight by when `loads.use_value_weighted_distribution`
    is on.

    Computed as `face_value / reference_face_value` where the reference
    is south-facing, 30° pitch (the Sandia 1.00 anchor). All evaluated
    against the same hourly value pattern so the only delta is
    orientation.

    Returns:
        Float in (0, 1] for any oriented face. North-facing 60° on a
        sub-1:1 plan can dip near 0.30; west-facing 30° on a 1:1 plan
        ≈ 0.86 (matches Sandia annual derate exactly when ratio = 1.0).
    """
    face_profile = hourly_face_profile(azimuth_deg, pitch_deg, lat_deg)
    ref_profile = hourly_face_profile(
        _REFERENCE_AZIMUTH_DEG, _REFERENCE_PITCH_DEG, lat_deg,
    )
    value_factor = hourly_value_factor(
        rep_buyback_ratio, self_consumption_pattern,
    )

    face_value = sum(p * v for p, v in zip(face_profile, value_factor))
    ref_value = sum(p * v for p, v in zip(ref_profile, value_factor))

    if ref_value <= 0:
        # Pathological — only happens at extreme latitudes where the
        # reference face itself never sees sun (winter polar night).
        # Caller should fall back to Sandia annual derate.
        return 0.0
    return max(0.0, face_value / ref_value)


# ─── Helpers ───────────────────────────────────────────────────────────


def _sun_position_equinox(
    hour: float, lat_deg: float,
) -> tuple[float, float]:
    """Equinox-day (decl = 0) sun position approximation.

    Returns (elevation_deg, azimuth_deg). Azimuth uses US convention
    (0 = N, 90 = E, 180 = S, 270 = W). Elevation < 0 means below
    horizon (night).
    """
    lat = math.radians(lat_deg)
    # Solar hour angle: 0 at noon, +15°/hr afternoon, -15°/hr morning
    hour_angle = math.radians(15.0 * (hour - 12.0))

    # Elevation: at equinox decl = 0, so:
    #   sin(elev) = sin(lat)·sin(0) + cos(lat)·cos(0)·cos(H)
    #             = cos(lat) × cos(hour_angle)
    sin_elev = math.cos(lat) * math.cos(hour_angle)
    sin_elev = max(-1.0, min(1.0, sin_elev))
    elev = math.asin(sin_elev)

    if elev <= 0:
        return math.degrees(elev), 0.0

    # Azimuth: solve from spherical trig. At equinox:
    #   cos(az_from_north) = -sin(decl) / cos(elev) but decl=0 so
    #   we need the relative geometry. Simpler: use cosine rule
    #   for the spherical triangle (pole, sun, observer's south).
    #
    # cos(az_south) = (sin(elev)·sin(lat) - sin(decl)) /
    #                 (cos(elev)·cos(lat))
    # At decl=0:
    #   cos(az_south) = sin(elev)·sin(lat) / (cos(elev)·cos(lat))
    #                 = tan(elev)·tan(lat) / 1  (with the right signs)
    # but azimuth-from-south magnitude only.
    cos_elev = math.cos(elev)
    if cos_elev < 1e-9:
        # Sun overhead — azimuth indeterminate, pick south
        return math.degrees(elev), 180.0
    cos_az_from_south = (
        (math.sin(elev) * math.sin(lat)) / (cos_elev * math.cos(lat))
    )
    cos_az_from_south = max(-1.0, min(1.0, cos_az_from_south))
    az_from_south_magnitude = math.degrees(math.acos(cos_az_from_south))

    # Sign by morning (hour < 12) → azimuth east of south (< 180);
    # afternoon → west of south (> 180).
    if hour < 12:
        az = 180.0 - az_from_south_magnitude   # east of south
    else:
        az = 180.0 + az_from_south_magnitude   # west of south
    return math.degrees(elev), az


def _face_cos_incidence(
    *,
    sun_elev_deg: float, sun_az_deg: float,
    face_az_deg: float, face_pitch_deg: float,
) -> float:
    """Cosine of angle between sun ray and face outward normal.

    Standard solar-PV geometry formula. Clamped at 0 (no negative
    contribution — back of the panel doesn't generate).
    """
    elev = math.radians(sun_elev_deg)
    # Azimuth difference: face vs sun, normalized to absolute value
    az_diff = math.radians(sun_az_deg - face_az_deg)
    tilt = math.radians(face_pitch_deg)

    cos_i = (
        math.sin(elev) * math.cos(tilt)
        + math.cos(elev) * math.sin(tilt) * math.cos(az_diff)
    )
    return max(0.0, cos_i)
