"""NEC grounding and bonding (Article 250 + 690.41–50).

Implements the size-lookup tables most relevant to residential PV+ESS:

- **NEC 250.66** — AC grounding electrode conductor (GEC) sizing, indexed by
  the size of the largest ungrounded service-entrance conductor.
- **NEC 250.122 (Table 250.122)** — equipment grounding conductor (EGC)
  sizing, indexed by upstream OCPD rating.
- **NEC 250.166** — DC GEC sizing (mostly aligned with 250.66 for PV
  systems in dwellings; we use the same table since AC and DC GECs commonly
  share a single GEC bonded at the equipment ground bar per 690.47).

The data is conservative copper-conductor values; aluminum requires upsize per
250.66/.122 notes and is out of scope here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


# NEC Table 250.66 — AC GEC sizing for copper service-entrance conductors.
# Key = largest ungrounded service-entrance conductor (per phase).
# Sequence is ordered smallest → largest so we can walk and pick the row.
TABLE_250_66_CU: list[tuple[str, str]] = [
    # (largest service-entrance conductor, min CU GEC)
    ("2",   "8"),     # ≤ 2 AWG  → 8 AWG GEC
    ("1/0", "6"),     # 1 or 1/0 AWG → 6 AWG
    ("3/0", "4"),     # 2/0 or 3/0 AWG → 4 AWG
    ("350", "2"),     # Over 3/0 through 350 kcmil → 2 AWG
    ("600", "1/0"),   # Over 350 through 600 kcmil → 1/0 AWG
    ("1100", "2/0"),  # Over 600 through 1100 kcmil → 2/0 AWG
]

# Service-entrance conductor size lookup by service ampacity (CU @ 75°C),
# derived from NEC 310.16 with typical residential values. Used to pick the
# 250.66 GEC when the user doesn't supply the conductor size directly.
SERVICE_CONDUCTOR_BY_AMPS: list[tuple[int, str]] = [
    # (max amps, conductor size at 75°C)
    (100, "3"),
    (115, "2"),
    (150, "1"),
    (175, "1/0"),
    (200, "2/0"),       # standard residential 200A → 2/0 CU
    (230, "3/0"),
    (255, "4/0"),
    (285, "250"),
    (310, "300"),
    (335, "350"),
    (380, "400"),
    (475, "500"),
]


# NEC Table 250.122 — minimum equipment grounding conductor (EGC) for
# copper, indexed by upstream OCPD rating.
TABLE_250_122_CU: list[tuple[int, str]] = [
    (15,    "14"),
    (20,    "12"),
    (60,    "10"),
    (100,   "8"),
    (200,   "6"),
    (300,   "4"),
    (400,   "3"),
    (500,   "2"),
    (600,   "1"),
    (800,   "1/0"),
    (1100,  "2/0"),
    (1200,  "3/0"),
    (1600,  "4/0"),
    (2000,  "250"),
    (2500,  "350"),
]


def service_conductor_size(service_amps: float) -> str:
    """Pick a typical residential service-entrance conductor size (CU 75°C)
    for the given service ampacity. Used as the input to NEC 250.66."""
    for limit, size in SERVICE_CONDUCTOR_BY_AMPS:
        if service_amps <= limit:
            return size
    return SERVICE_CONDUCTOR_BY_AMPS[-1][1]


# Canonical ordering of NEC conductor sizes (smallest → largest). The rank
# is used to compare arbitrary sizes against each row's upper bound.
_NEC_SIZE_ORDER: list[str] = [
    "14", "12", "10", "8", "6", "4", "3", "2", "1",
    "1/0", "2/0", "3/0", "4/0",
    "250", "300", "350", "400", "500", "600",
    "700", "750", "800", "900", "1000", "1100",
]


def _conductor_rank(size: str) -> int:
    """Position of a conductor size in the AWG/kcmil ordering. Unknown sizes
    rank at -1 so they fall into the smallest table row."""
    try:
        return _NEC_SIZE_ORDER.index(size)
    except ValueError:
        return -1


def _row_index(size: str, sequence: list[tuple[str, str]]) -> int:
    """Find the row whose upper-bound size is the smallest one ≥ given size."""
    target_rank = _conductor_rank(size)
    for idx, (upper, _) in enumerate(sequence):
        if _conductor_rank(upper) >= target_rank:
            return idx
    return len(sequence) - 1


def select_ac_gec(service_amps: float) -> tuple[str, str]:
    """Apply NEC 250.66 → return (service conductor size, GEC size) in AWG."""
    cond_size = service_conductor_size(service_amps)
    idx = _row_index(cond_size, TABLE_250_66_CU)
    return cond_size, TABLE_250_66_CU[idx][1]


def select_dc_gec(pv_source_amps: float) -> str:
    """NEC 250.166 — for residential PV systems we follow 250.66 sized from
    the DC source-circuit conductor (which is at most a few AWG). In practice
    most residential PV installs use 6 AWG or 8 AWG bare CU GEC.
    """
    # Map PV source amps to an equivalent "service conductor" lookup so the
    # 250.66 table picks a sensible row. For residential PV source circuits
    # the GEC almost always lands at 6 or 8 AWG.
    if pv_source_amps <= 30:
        return "8"
    if pv_source_amps <= 50:
        return "6"
    cond_size = service_conductor_size(pv_source_amps)
    idx = _row_index(cond_size, TABLE_250_66_CU)
    return TABLE_250_66_CU[idx][1]


def select_egc(upstream_ocpd_a: float) -> str:
    """NEC Table 250.122 — equipment grounding conductor size by OCPD."""
    for limit, size in TABLE_250_122_CU:
        if upstream_ocpd_a <= limit:
            return size
    return TABLE_250_122_CU[-1][1]


@dataclass
class GecComparison:
    """K.5 — existing GEC vs NEC 250.66 required size.

    `status`:
      * `PASS`        — actual size ≥ required, all good.
      * `UNDERSIZED`  — actual size < required, install must upsize.
      * `UNKNOWN`     — yaml didn't declare an existing GEC; report shows
                        the required size as the recommendation.
    """
    actual_size: str             # what's installed (or "")
    required_size: str           # what NEC 250.66 wants
    status: Literal["PASS", "UNDERSIZED", "UNKNOWN"]
    note: str


def compare_gec_to_required(
    actual_size_awg: str, required_size_awg: str,
) -> GecComparison:
    """K.5 — rank-compare the existing GEC to the NEC 250.66 requirement.

    Returns UNKNOWN when actual is blank (homeowner didn't measure or
    yaml omitted the field); UNDERSIZED when actual rank < required rank;
    PASS otherwise.
    """
    if not actual_size_awg:
        return GecComparison(
            actual_size="",
            required_size=required_size_awg,
            status="UNKNOWN",
            note=("Existing GEC size not recorded. NEC 250.66 requires "
                  f"#{required_size_awg} AWG Cu — confirm at site visit."),
        )
    actual_rank = _conductor_rank(actual_size_awg)
    required_rank = _conductor_rank(required_size_awg)
    if actual_rank < required_rank:
        return GecComparison(
            actual_size=actual_size_awg,
            required_size=required_size_awg,
            status="UNDERSIZED",
            note=(f"Existing #{actual_size_awg} AWG GEC is smaller than "
                  f"NEC 250.66 required #{required_size_awg} AWG. "
                  "Upsize before energizing the new PV/ESS."),
        )
    return GecComparison(
        actual_size=actual_size_awg,
        required_size=required_size_awg,
        status="PASS",
        note=(f"Existing #{actual_size_awg} AWG GEC meets NEC 250.66 "
              f"(≥ #{required_size_awg} AWG)."),
    )


@dataclass
class GroundingResult:
    """Resolved grounding sizes for a project, ready for the EE-2 sheet."""
    service_conductor_size: str    # e.g. "2/0"
    ac_gec_size: str               # e.g. "4"
    dc_gec_size: str               # e.g. "6"
    egc_pv_source: str             # e.g. "10"
    egc_inverter_ac: str           # e.g. "10"
    egc_aggregate_ac: str          # e.g. "6"
    egc_ess: str                   # e.g. "6"
    # K.5: existing GES inspection. `None` only when the GES block is
    # entirely default + no data was supplied — engine still emits the
    # NEC 250.66 required size in `ac_gec_size`.
    gec_comparison: GecComparison | None = None
    actual_electrodes: list[str] = None   # type: ignore[assignment]

    def __post_init__(self):
        if self.actual_electrodes is None:
            self.actual_electrodes = []

    @property
    def electrode_summary(self) -> list[str]:
        """K.5 — actual electrodes if the yaml declared them; otherwise
        fall back to the legacy "assume the standard combo" text so
        old yaml renders bit-identical."""
        if self.actual_electrodes:
            return self.actual_electrodes
        return [
            "Ground rod (8 ft min, 250.52(A)(5)) — primary",
            "Metal underground water pipe ≥10 ft (250.52(A)(1)) — if available",
            "Concrete-encased electrode / Ufer (250.52(A)(3)) — new construction",
        ]


def _electrode_summary_from_ges(ges) -> list[str]:
    """Render the actual GES inventory as a list of human-readable lines
    matching the existing `electrode_summary` shape."""
    lines: list[str] = []
    for i, rod in enumerate(ges.rods, 1):
        loc = f" at {rod.location}" if rod.location else ""
        lines.append(
            f"Ground rod #{i} ({rod.length_ft:.0f} ft "
            f"{rod.diameter_in:.3g}\" {rod.material}{loc}) — NEC 250.52(A)(5)"
        )
    if ges.metal_water_pipe:
        mwp = ges.metal_water_pipe
        if mwp.confirmed_metal_underground:
            loc = f" at {mwp.location}" if mwp.location else ""
            lines.append(
                f"Metal water pipe (≥{mwp.underground_length_ft:.0f} ft "
                f"underground{loc}) — NEC 250.52(A)(1)"
            )
        else:
            lines.append(
                "Metal water pipe present but NOT continuous underground "
                "(PEX-replaced?) — DOES NOT qualify per NEC 250.52(A)(1)"
            )
    if ges.ufer:
        u = ges.ufer
        loc = f" at {u.location}" if u.location else ""
        lines.append(
            f"Ufer / concrete-encased electrode ({u.length_ft:.0f} ft "
            f"{u.conductor_size}{loc}) — NEC 250.52(A)(3)"
        )
    return lines


def compute_grounding(
    *,
    service_amps: float,
    pv_source_amps: float,
    pv_ocpd_a: float,
    per_inverter_ocpd_a: float,
    aggregate_ac_ocpd_a: float,
    ess_ocpd_a: float,
    ges=None,
) -> GroundingResult:
    """Compute every conductor size that lands on the EE-2 sheet schedule.

    K.5: when `ges` (a `GroundingElectrodeSystem`) is supplied, the
    result also carries a `GecComparison` against NEC 250.66 and a
    list of ACTUAL electrodes for EE-2 to render. When omitted, the
    legacy 'assume standard 3-electrode combo' behaviour is preserved.
    """
    cond, ac_gec = select_ac_gec(service_amps)
    comparison: GecComparison | None = None
    electrodes: list[str] = []
    if ges is not None:
        comparison = compare_gec_to_required(ges.gec_main_size_awg, ac_gec)
        electrodes = _electrode_summary_from_ges(ges)
    return GroundingResult(
        service_conductor_size=cond,
        ac_gec_size=ac_gec,
        dc_gec_size=select_dc_gec(pv_source_amps),
        egc_pv_source=select_egc(pv_ocpd_a),
        egc_inverter_ac=select_egc(per_inverter_ocpd_a),
        egc_aggregate_ac=select_egc(aggregate_ac_ocpd_a),
        egc_ess=select_egc(ess_ocpd_a),
        gec_comparison=comparison,
        actual_electrodes=electrodes,
    )
