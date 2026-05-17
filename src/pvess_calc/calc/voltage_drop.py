"""Per-segment voltage drop calculation (NEC 215.2 / 210.19 informational notes).

NEC doesn't set a hard limit, but the Informational Note to 210.19(A)(1) and
215.2(A)(1) recommends:

  - Branch circuit conductors: voltage drop ≤ 3%
  - Feeder + branch circuit combined: voltage drop ≤ 5%

For PV/ESS sizing, industry practice tightens this further:

  - PV DC source/output: ≤ 2%
  - AC feeders: ≤ 3%
  - End-to-end PV → MSP: ≤ 5%

This module computes per-segment Vd from real wire lengths in inputs.yaml and
flags any segment that exceeds the recommended limit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..nec.tables import COPPER_RESISTANCE_OHM_PER_KFT
from ..schema import Inputs


SegmentKind = Literal["DC", "AC"]


# NEC informational note thresholds (percent) — industry tight version.
LIMIT_DC_PCT = 2.0
LIMIT_AC_PCT = 3.0
LIMIT_TOTAL_PCT = 5.0

# Fallback length when the user doesn't provide one. Used so older yaml files
# still produce a (clearly best-effort) voltage-drop section.
DEFAULT_LENGTH_FT = 50.0


@dataclass
class VdSegment:
    label: str
    kind: SegmentKind
    one_way_ft: float
    current_a: float
    voltage: float
    conductor_size: str
    drop_v: float
    drop_pct: float
    limit_pct: float
    status: Literal["PASS", "FAIL", "DEFAULT"]


@dataclass
class VoltageDropAnalysis:
    segments: list[VdSegment] = field(default_factory=list)
    total_dc_pct: float = 0.0
    total_ac_pct: float = 0.0
    total_end_to_end_pct: float = 0.0
    overall_status: Literal["PASS", "FAIL", "DEFAULT"] = "PASS"


def _segment(
    label: str, kind: SegmentKind, length_ft: float, *,
    current_a: float, voltage: float, conductor_size: str,
    default_fallback: bool,
) -> VdSegment:
    r = COPPER_RESISTANCE_OHM_PER_KFT.get(conductor_size)
    if r is None:
        # Shouldn't happen for sizes we picked; fall back to 0.
        r = 0.0
    drop_v = 2 * length_ft * current_a * r / 1000.0
    drop_pct = (drop_v / voltage * 100.0) if voltage > 0 else 0.0
    limit = LIMIT_DC_PCT if kind == "DC" else LIMIT_AC_PCT
    if default_fallback:
        status: Literal["PASS", "FAIL", "DEFAULT"] = "DEFAULT"
    elif drop_pct <= limit:
        status = "PASS"
    else:
        status = "FAIL"
    return VdSegment(
        label=label, kind=kind, one_way_ft=length_ft,
        current_a=current_a, voltage=voltage,
        conductor_size=conductor_size,
        drop_v=drop_v, drop_pct=drop_pct,
        limit_pct=limit, status=status,
    )


def _ac_trunk_segments(
    sub_panels: list, msp_len: float, msp_default: bool,
    *, current_a: float, voltage: float, conductor_size: str,
) -> list[VdSegment]:
    """K.2.6a — emit AC-trunk segments for the AC-DISC→MSP path.

    When ANY sub-panel carries `distance_to_msp_ft > 0`, build a chain
    of segments — one per sub-panel as the wire hops through the
    series — plus a final hop using the global `ac_disc_to_msp_ft`
    (which is now interpreted as `last-sub-panel→MSP`, not the whole
    trunk). The order in `sub_panels` is the chain order from AC-DISC
    towards the MSP.

    When no sub-panel has distance data (legacy yaml), fall back to a
    single 'D · AC-DISC→MSP' segment exactly as before — bit-identical
    output for old projects.
    """
    chain = [sp for sp in sub_panels if sp.distance_to_msp_ft > 0]
    if not chain:
        return [_segment(
            "D · AC-DISC→MSP", "AC", msp_len,
            current_a=current_a, voltage=voltage,
            conductor_size=conductor_size,
            default_fallback=msp_default,
        )]

    out: list[VdSegment] = []
    for i, sp in enumerate(chain):
        from_node = "AC-DISC" if i == 0 else (
            chain[i - 1].name or f"Sub#{i}"
        )
        to_node = sp.name or f"Sub#{i + 1}"
        out.append(_segment(
            f"D{i + 1} · {from_node}→{to_node}", "AC",
            sp.distance_to_msp_ft,
            current_a=current_a, voltage=voltage,
            conductor_size=conductor_size,
            default_fallback=False,
        ))
    # Final hop: last sub-panel → MSP (uses the global ac_disc_to_msp_ft).
    last_name = chain[-1].name or f"Sub#{len(chain)}"
    out.append(_segment(
        f"D{len(chain) + 1} · {last_name}→MSP", "AC", msp_len,
        current_a=current_a, voltage=voltage,
        conductor_size=conductor_size,
        default_fallback=msp_default,
    ))
    return out


def compute_voltage_drop(
    inputs: Inputs,
    *,
    pv_string_voc_cold: float,
    pv_source_current_a: float,
    pv_conductor_size: str,
    per_inverter_current_a: float,
    per_inverter_conductor_size: str,
    aggregate_ac_current_a: float,
    aggregate_ac_conductor_size: str,
    ess_dc_current_a: float = 0.0,
) -> VoltageDropAnalysis:
    """Build a 5- or 6-segment voltage drop table. Each segment uses the real
    wire length from inputs.wire_lengths when available, otherwise falls back
    to DEFAULT_LENGTH_FT with status='DEFAULT'.
    """
    wl = inputs.wire_lengths
    fallback = not wl.has_data

    def length_or_default(value: float) -> tuple[float, bool]:
        if value > 0:
            return value, False
        return DEFAULT_LENGTH_FT, True

    pv_src_len, pv_src_default = length_or_default(wl.pv_string_one_way_ft)
    pv_home_len, pv_home_default = length_or_default(wl.pv_to_combiner_ft or wl.combiner_to_inverter_ft)
    inv_ac_len, inv_ac_default = length_or_default(wl.inverter_to_ac_disc_ft)
    msp_len, msp_default = length_or_default(wl.ac_disc_to_msp_ft)
    ess_len, ess_default = length_or_default(wl.ess_to_inverter_ft)

    ac_voltage = inputs.inverter.ac_output_v  # 240 split-phase

    segments = [
        _segment(
            "A · PV source", "DC", pv_src_len,
            current_a=pv_source_current_a,
            voltage=pv_string_voc_cold,
            conductor_size=pv_conductor_size,
            default_fallback=pv_src_default,
        ),
        _segment(
            "B · DC home run", "DC", pv_home_len,
            current_a=pv_source_current_a,
            voltage=pv_string_voc_cold,
            conductor_size=pv_conductor_size,
            default_fallback=pv_home_default,
        ),
        _segment(
            "C · INV→AC trunk", "AC", inv_ac_len,
            current_a=per_inverter_current_a,
            voltage=ac_voltage,
            conductor_size=per_inverter_conductor_size,
            default_fallback=inv_ac_default,
        ),
    ]
    segments.extend(_ac_trunk_segments(
        inputs.service.sub_panels, msp_len, msp_default,
        current_a=aggregate_ac_current_a, voltage=ac_voltage,
        conductor_size=aggregate_ac_conductor_size,
    ))
    if ess_dc_current_a > 0:
        segments.append(_segment(
            "ESS · battery DC", "DC", ess_len,
            current_a=ess_dc_current_a,
            voltage=inputs.battery.nominal_voltage,
            conductor_size=aggregate_ac_conductor_size,  # rough proxy
            default_fallback=ess_default,
        ))

    total_dc = sum(s.drop_pct for s in segments if s.kind == "DC" and s.label != "ESS · battery DC")
    total_ac = sum(s.drop_pct for s in segments if s.kind == "AC")
    total_e2e = total_dc + total_ac

    if fallback:
        overall = "DEFAULT"
    elif any(s.status == "FAIL" for s in segments):
        overall = "FAIL"
    elif total_e2e > LIMIT_TOTAL_PCT:
        overall = "FAIL"
    else:
        overall = "PASS"

    return VoltageDropAnalysis(
        segments=segments,
        total_dc_pct=total_dc,
        total_ac_pct=total_ac,
        total_end_to_end_pct=total_e2e,
        overall_status=overall,
    )
