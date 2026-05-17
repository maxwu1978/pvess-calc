"""NEC reference tables. Independent of code edition."""
from __future__ import annotations

from typing import Literal

Insulation = Literal["60C", "75C", "90C"]

# NEC 240.6(A) standard OCPD ratings (A).
STANDARD_OCPD_RATINGS: tuple[int, ...] = (
    15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100, 110,
    125, 150, 175, 200, 225, 250, 300, 350, 400, 450, 500, 600,
    700, 800, 1000, 1200,
)

# NEC Table 310.16 — copper conductor ampacities, 30°C ambient,
# not more than 3 current-carrying conductors.
# Keys: AWG / kcmil. Values: A at 60/75/90°C.
COPPER_AMPACITY_TABLE_310_16: dict[str, dict[Insulation, int]] = {
    "14": {"60C": 15, "75C": 20, "90C": 25},
    "12": {"60C": 20, "75C": 25, "90C": 30},
    "10": {"60C": 30, "75C": 35, "90C": 40},
    "8":  {"60C": 40, "75C": 50, "90C": 55},
    "6":  {"60C": 55, "75C": 65, "90C": 75},
    "4":  {"60C": 70, "75C": 85, "90C": 95},
    "3":  {"60C": 85, "75C": 100, "90C": 115},
    "2":  {"60C": 95, "75C": 115, "90C": 130},
    "1":  {"60C": 110, "75C": 130, "90C": 145},
    "1/0": {"60C": 125, "75C": 150, "90C": 170},
    "2/0": {"60C": 145, "75C": 175, "90C": 195},
    "3/0": {"60C": 165, "75C": 200, "90C": 225},
    "4/0": {"60C": 195, "75C": 230, "90C": 260},
    "250": {"60C": 215, "75C": 255, "90C": 290},
    "300": {"60C": 240, "75C": 285, "90C": 320},
    "350": {"60C": 260, "75C": 310, "90C": 350},
    "400": {"60C": 280, "75C": 335, "90C": 380},
    "500": {"60C": 320, "75C": 380, "90C": 430},
}

# Conductor sequence used when stepping up to the next size.
COPPER_SIZE_SEQUENCE: tuple[str, ...] = tuple(COPPER_AMPACITY_TABLE_310_16.keys())

# Approximate DC resistance (ohm / 1000 ft) for copper at 75°C.
# Source: NEC Chapter 9, Table 8 (approximated for voltage-drop estimation).
COPPER_RESISTANCE_OHM_PER_KFT: dict[str, float] = {
    "14": 3.07, "12": 1.93, "10": 1.21, "8": 0.764, "6": 0.491,
    "4": 0.308, "3": 0.245, "2": 0.194, "1": 0.154,
    "1/0": 0.122, "2/0": 0.0967, "3/0": 0.0766, "4/0": 0.0608,
    "250": 0.0515, "300": 0.0429, "350": 0.0367, "400": 0.0321, "500": 0.0258,
}

# NEC Table 690.7 — Voc temperature correction factors (no datasheet βVoc).
# Lookup by ambient low temperature (°C).
# Used when module datasheet does not provide a temperature coefficient.
TABLE_690_7_VOC_CORRECTION: list[tuple[float, float]] = [
    (25.0, 1.00),
    (20.0, 1.02),
    (15.0, 1.04),
    (10.0, 1.06),
    (5.0, 1.08),
    (0.0, 1.10),
    (-5.0, 1.12),
    (-10.0, 1.14),
    (-15.0, 1.16),
    (-20.0, 1.18),
    (-25.0, 1.20),
    (-30.0, 1.21),
    (-35.0, 1.23),
    (-40.0, 1.25),
]


def table_690_7_factor(low_temp_c: float) -> float:
    """Look up the Table 690.7 Voc correction factor for the given low temperature.

    Picks the row whose threshold is the closest value at or below `low_temp_c`,
    matching the conservative interpretation used in NEC examples.
    """
    factor = 1.00
    for threshold_c, f in TABLE_690_7_VOC_CORRECTION:
        if low_temp_c <= threshold_c:
            factor = f
    return factor


# NEC 240.4(D) — small conductor rule, max OCPD per copper conductor size.
SMALL_CONDUCTOR_OCPD_LIMITS: dict[str, int] = {
    "14": 15,
    "12": 20,
    "10": 30,
}


# NEC Table 310.15(B)(2)(a) — ambient temperature correction factors for
# 30°C base ambient, 75°C insulation. Coarse but standard residential set.
# Lookup by (ambient_low_c, ambient_high_c) bracket → multiplier.
TEMPERATURE_CORRECTION_75C: list[tuple[float, float]] = [
    # (max ambient °C, multiplier)
    (25,  1.05),
    (30,  1.00),
    (35,  0.94),
    (40,  0.88),
    (45,  0.82),
    (50,  0.75),
    (55,  0.67),
    (60,  0.58),
    (65,  0.47),
    (70,  0.33),
]

# NEC Table 310.15(B)(3)(a)(1) — adjustment factor for >3 current-carrying
# conductors in the same raceway / cable / earth.
CONDUIT_FILL_ADJUSTMENT: list[tuple[int, float]] = [
    # (max number of current-carrying conductors, factor)
    (3,   1.00),
    (6,   0.80),
    (9,   0.70),
    (20,  0.50),
    (30,  0.45),
    (40,  0.40),
    (1000, 0.35),
]


def temperature_correction_75c(ambient_c: float) -> float:
    """Return the NEC 310.15(B)(2)(a) temperature correction factor for 75°C
    conductors at the given ambient. Conservative: picks the lower factor
    of the bracket the ambient falls into."""
    for limit_c, factor in TEMPERATURE_CORRECTION_75C:
        if ambient_c <= limit_c:
            return factor
    return TEMPERATURE_CORRECTION_75C[-1][1]


def conduit_fill_adjustment(n_conductors: int) -> float:
    """NEC 310.15(B)(3)(a)(1) adjustment for N current-carrying conductors."""
    for limit_n, factor in CONDUIT_FILL_ADJUSTMENT:
        if n_conductors <= limit_n:
            return factor
    return CONDUIT_FILL_ADJUSTMENT[-1][1]


def small_conductor_ocpd_limit(size: str) -> int | None:
    """Return max OCPD (A) per NEC 240.4(D), or None if the size is unrestricted."""
    return SMALL_CONDUCTOR_OCPD_LIMITS.get(size)


def next_standard_ocpd(min_amps: float) -> int:
    """Return the smallest standard OCPD rating ≥ min_amps (NEC 240.6)."""
    for rating in STANDARD_OCPD_RATINGS:
        if rating >= min_amps:
            return rating
    raise ValueError(f"No standard OCPD rating ≥ {min_amps} A in table.")


def smallest_copper_for_ampacity(
    required_a: float,
    insulation: Insulation = "75C",
    upstream_ocpd_a: int | None = None,
    derating_factor: float = 1.0,
) -> tuple[str, int]:
    """Return (size_label, ampacity_a) for the smallest copper conductor that:
      (a) meets Table 310.16 ampacity × derating_factor ≥ required_a, and
      (b) honors NEC 240.4(D) (small conductor rule) given upstream_ocpd_a.

    `derating_factor` is the product of NEC 310.15(B)(2)(a) temperature
    correction and 310.15(B)(3)(a)(1) conduit-fill adjustment; the conductor's
    nominal 310.16 ampacity is multiplied by this before comparison.

    Returns the *derated* ampacity (what the conductor can actually carry in
    its environment), not the raw 310.16 nominal value.
    """
    for size in COPPER_SIZE_SEQUENCE:
        nominal = COPPER_AMPACITY_TABLE_310_16[size][insulation]
        derated = nominal * derating_factor
        if derated < required_a:
            continue
        if upstream_ocpd_a is not None:
            limit = small_conductor_ocpd_limit(size)
            if limit is not None and upstream_ocpd_a > limit:
                continue
        return size, int(derated)
    raise ValueError(
        f"No copper size in table 310.16 supports {required_a} A at {insulation} "
        f"(derating={derating_factor}) with upstream OCPD {upstream_ocpd_a}."
    )
