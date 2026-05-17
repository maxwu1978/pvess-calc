"""K.5 — existing GES vs NEC 250.66 comparison + electrode inventory.

What this guards:
  * `compare_gec_to_required` correctly ranks AWG sizes (e.g. #8 < #6 < #4).
  * 200 A service → NEC 250.66 wants #4 AWG GEC; #8 existing is UNDERSIZED.
  * Backward compat: yaml without `grounding_electrode_system` block
    still produces a GroundingResult, just with `gec_comparison=None`.
  * Electrode summary text reflects actual installed components.
"""
from __future__ import annotations

from pvess_calc.calc.grounding import (
    compare_gec_to_required,
    compute_grounding,
)
from pvess_calc.schema import (
    GroundingElectrodeSystem,
    GroundRod,
    MetalWaterPipeBond,
    UferElectrode,
)


# ─── compare_gec_to_required ──────────────────────────────────────────


def test_actual_4awg_meets_required_4awg_passes():
    r = compare_gec_to_required("4", "4")
    assert r.status == "PASS"
    assert "#4 AWG" in r.note


def test_actual_2awg_exceeds_required_4awg_passes():
    """Bigger conductor (lower AWG number) is fine."""
    r = compare_gec_to_required("2", "4")
    assert r.status == "PASS"


def test_actual_8awg_below_required_4awg_undersized():
    """Classic K.5 case: older home GEC is #8 but NEC 250.66 wants #4
    for a 200 A service. Doctor must FAIL."""
    r = compare_gec_to_required("8", "4")
    assert r.status == "UNDERSIZED"
    assert "smaller than" in r.note
    assert "#8" in r.note and "#4" in r.note


def test_blank_actual_yields_unknown_status():
    """No declared existing GEC → UNKNOWN with the required-size note."""
    r = compare_gec_to_required("", "4")
    assert r.status == "UNKNOWN"
    assert "not recorded" in r.note


# ─── compute_grounding with GES ───────────────────────────────────────


def test_compute_grounding_without_ges_keeps_legacy_behaviour():
    """K.5 backward-compat contract: callers that don't pass `ges`
    still get a GroundingResult; `gec_comparison` is None and the
    electrode summary falls back to the standard 3-electrode text."""
    r = compute_grounding(
        service_amps=200, pv_source_amps=17.2,
        pv_ocpd_a=25, per_inverter_ocpd_a=45,
        aggregate_ac_ocpd_a=125, ess_ocpd_a=125,
    )
    assert r.ac_gec_size == "4"           # NEC 250.66 for 200A → 2/0 → #4
    assert r.gec_comparison is None
    assert r.actual_electrodes == []
    # Legacy electrode summary still works:
    summary = r.electrode_summary
    assert any("Ground rod" in s for s in summary)
    assert any("water pipe" in s for s in summary)
    assert any("Ufer" in s for s in summary)


def test_compute_grounding_with_undersized_existing_gec():
    """Phoenix-style real case: 200 A service, existing GEC #8 →
    UNDERSIZED finding."""
    ges = GroundingElectrodeSystem(
        rods=[GroundRod(length_ft=8, location="SE corner")],
        gec_main_size_awg="8",
    )
    r = compute_grounding(
        service_amps=200, pv_source_amps=17.2,
        pv_ocpd_a=25, per_inverter_ocpd_a=45,
        aggregate_ac_ocpd_a=125, ess_ocpd_a=125,
        ges=ges,
    )
    assert r.gec_comparison is not None
    assert r.gec_comparison.status == "UNDERSIZED"
    assert r.gec_comparison.actual_size == "8"
    assert r.gec_comparison.required_size == "4"


def test_compute_grounding_with_compliant_existing_gec():
    ges = GroundingElectrodeSystem(
        rods=[GroundRod()],
        gec_main_size_awg="4",
    )
    r = compute_grounding(
        service_amps=200, pv_source_amps=17.2,
        pv_ocpd_a=25, per_inverter_ocpd_a=45,
        aggregate_ac_ocpd_a=125, ess_ocpd_a=125,
        ges=ges,
    )
    assert r.gec_comparison is not None
    assert r.gec_comparison.status == "PASS"


# ─── electrode_summary reflects actual GES ────────────────────────────


def test_actual_electrodes_renders_real_components_only():
    """K.5 — when the yaml says only rod + water pipe (no Ufer), the
    summary contains exactly those two and skips the Ufer line that
    the legacy assumed-default summary always printed."""
    ges = GroundingElectrodeSystem(
        rods=[GroundRod(length_ft=8, location="N exterior wall")],
        metal_water_pipe=MetalWaterPipeBond(
            underground_length_ft=12, location="basement service entry",
        ),
    )
    r = compute_grounding(
        service_amps=200, pv_source_amps=17.2,
        pv_ocpd_a=25, per_inverter_ocpd_a=45,
        aggregate_ac_ocpd_a=125, ess_ocpd_a=125,
        ges=ges,
    )
    summary = r.electrode_summary
    assert any("Ground rod #1" in s and "8 ft" in s for s in summary)
    assert any("Metal water pipe" in s and "12 ft" in s for s in summary)
    # No Ufer because the yaml didn't declare one:
    assert not any("Ufer" in s for s in summary)


def test_pex_water_pipe_does_not_qualify():
    """Metal-water-pipe with `confirmed_metal_underground=False`
    (typical of homes where the service has been re-piped in PEX)
    renders as a 'DOES NOT qualify' note instead of an electrode.
    """
    ges = GroundingElectrodeSystem(
        rods=[GroundRod()],
        metal_water_pipe=MetalWaterPipeBond(
            confirmed_metal_underground=False,
        ),
    )
    r = compute_grounding(
        service_amps=200, pv_source_amps=17.2,
        pv_ocpd_a=25, per_inverter_ocpd_a=45,
        aggregate_ac_ocpd_a=125, ess_ocpd_a=125,
        ges=ges,
    )
    text = " ".join(r.electrode_summary)
    assert "DOES NOT qualify" in text


def test_ufer_is_listed_with_conductor_detail():
    ges = GroundingElectrodeSystem(
        ufer=UferElectrode(
            conductor="copper", conductor_size="4 AWG copper",
            location="south foundation",
        ),
    )
    r = compute_grounding(
        service_amps=200, pv_source_amps=17.2,
        pv_ocpd_a=25, per_inverter_ocpd_a=45,
        aggregate_ac_ocpd_a=125, ess_ocpd_a=125,
        ges=ges,
    )
    text = " ".join(r.electrode_summary)
    assert "Ufer" in text
    assert "4 AWG copper" in text


# ─── NEC 250.50 electrode count ───────────────────────────────────────


def test_electrode_count_property():
    """Helper used by the doctor: how many qualifying electrodes does
    the GES contain (PEX-replaced water pipe doesn't count)."""
    ges = GroundingElectrodeSystem(
        rods=[GroundRod(), GroundRod()],
        metal_water_pipe=MetalWaterPipeBond(confirmed_metal_underground=True),
        ufer=UferElectrode(),
    )
    assert ges.electrode_count == 4

    ges_no_pex = GroundingElectrodeSystem(
        rods=[GroundRod()],
        metal_water_pipe=MetalWaterPipeBond(confirmed_metal_underground=False),
    )
    assert ges_no_pex.electrode_count == 1
