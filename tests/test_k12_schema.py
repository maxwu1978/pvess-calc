"""K.12.1 — schema additions for the industry-standard cover page.

Closing standards:
  1. Every new model accepts construction with NO arguments (all
     optional fields default sensibly) — guarantees zero regression
     for every pre-K.12 yaml.
  2. Defaults track 2026 reality (2021 IBC/IRC/IFC/etc.; ASCE 7-16;
     DFW wind/snow). Drift sentry — if NREL updates the default
     residential cycle, these tests fail loud.
  3. Each block plugs onto `ProjectMeta` without breaking existing
     fields. Round-trip through yaml load is contract-preserving.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pvess_calc.schema import (
    BuildingCodes,
    DesignCriteria,
    Inputs,
    MeterInfo,
    ProjectMeta,
    RevisionEntry,
    RoofInfo,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHOENIX_YAML = PROJECT_ROOT / "projects" / "002-phoenix-25kw" / "inputs.yaml"


# ─── Default constructor — zero-config validation ───────────────────────


def test_roof_info_defaults_to_unknown_state():
    """`RoofInfo()` with no args = single-story / unknown / not-replaced.
    Old yaml without `roof_info` block must produce this default."""
    r = RoofInfo()
    assert r.stories == 1
    assert r.type == ""
    assert r.height_ft == 0.0
    assert r.condition == "unknown"
    assert r.being_replaced is False


def test_building_codes_defaults_to_2021_cycle():
    """Defaults track the dominant US residential code cycle (2021).
    AHJ profile can override per region (CA / FL stay on different
    cycles); but the default protects the 80% case."""
    c = BuildingCodes()
    assert "2021" in c.ibc
    assert "2021" in c.irc
    assert "2021" in c.iecc


def test_design_criteria_defaults_to_dfw_typical():
    """115 mph wind / 5 psf snow / ASCE 7-16 / R-3 occupancy / V-B
    construction / no sprinklers — DFW middle-of-the-road residential."""
    d = DesignCriteria()
    assert d.wind_speed_mph == 115
    assert d.ground_snow_load_psf == 5
    assert d.asce_version == "7-16"
    assert d.exposure_category == "C"
    assert d.occupancy == "R-3"
    assert d.sprinklers is False


def test_meter_info_defaults_to_empty():
    """ESID + meter number / location all blank by default. Cover
    renderer falls back to "—" placeholders for missing fields."""
    m = MeterInfo()
    assert m.number == ""
    assert m.location == ""
    assert m.esid == ""


def test_revision_entry_requires_date_and_revision():
    """`RevisionEntry` has 2 required fields: date + revision letter.
    Comment is optional (some installers don't fill it)."""
    r = RevisionEntry(date="2026-05-17", revision="A")
    assert r.comment == ""
    with pytest.raises(Exception):    # pydantic ValidationError
        RevisionEntry()    # no date / no revision


# ─── ProjectMeta integration ────────────────────────────────────────────


def test_project_meta_accepts_k12_blocks():
    """ProjectMeta wires the 5 new optional blocks. With all blocks
    omitted, the meta still validates — backward-compat contract."""
    p = ProjectMeta(id="x", name="X", location="Frisco, TX",
                    ahj="City of Frisco")
    # All blocks present as defaulted instances
    assert isinstance(p.roof_info, RoofInfo)
    assert isinstance(p.building_codes, BuildingCodes)
    assert isinstance(p.design_criteria, DesignCriteria)
    assert isinstance(p.meter_info, MeterInfo)
    assert p.revision_history == []


def test_project_meta_accepts_explicit_k12_blocks():
    """K.12.1 happy path: explicit yaml supplies all 5 blocks → they
    flow through pydantic round-trip without crashes."""
    p = ProjectMeta(
        id="x", name="X", location="Frisco, TX", ahj="City of Frisco",
        roof_info=RoofInfo(stories=2, type="Comp Shingle",
                           height_ft=25, condition="good"),
        building_codes=BuildingCodes(ibc="2024 IBC"),
        design_criteria=DesignCriteria(wind_speed_mph=125,
                                       sprinklers=True),
        meter_info=MeterInfo(number="153468971", esid="1044372000762"),
        revision_history=[
            RevisionEntry(date="2026-05-15", revision="A",
                          comment="initial design"),
            RevisionEntry(date="2026-05-17", revision="B",
                          comment="SW concentration"),
        ],
    )
    assert p.roof_info.stories == 2
    assert p.building_codes.ibc == "2024 IBC"
    assert p.design_criteria.sprinklers is True
    assert p.meter_info.esid == "1044372000762"
    assert len(p.revision_history) == 2


def test_legacy_yaml_loads_without_k12_blocks():
    """Closing standard: every pre-K.12 yaml MUST validate without
    touching the new blocks. Phoenix yaml is the canary fixture."""
    inputs = Inputs.from_yaml(PHOENIX_YAML)
    # The new blocks must be there as defaults, not missing attrs
    assert hasattr(inputs.project, "roof_info")
    assert hasattr(inputs.project, "building_codes")
    assert hasattr(inputs.project, "design_criteria")
    assert hasattr(inputs.project, "meter_info")
    assert hasattr(inputs.project, "revision_history")
    # And they match the K.12.1 defaults
    assert inputs.project.roof_info.condition == "unknown"
    assert inputs.project.design_criteria.exposure_category == "C"
