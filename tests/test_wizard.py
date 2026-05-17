"""Tests for the Phase K.2 interactive wizard.

Strategy: feed mock stdin (one answer per line) to `run_wizard`, then
verify:
  1. The generated `inputs.yaml` parses cleanly via pydantic
  2. The flat-path → nested-dict round-trip preserves values
  3. `--resume` correctly continues from a saved state
  4. List fields (sub_panels, roof_sections) prompt count + loop
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
import yaml

from pvess_calc.wizard.field_specs import (
    DESIGN_FIELDS,
    SITE_FIELDS,
    WIZARD_FIELDS,
    WIZARD_SECTION_ORDER,
    is_list_field,
    list_prefix,
)
from pvess_calc.wizard.nesting import set_list_item, set_path
from pvess_calc.wizard.state import WizardState


# ─── Data integrity ─────────────────────────────────────────────────────────


def test_wizard_fields_include_every_design_field():
    for spec in DESIGN_FIELDS:
        assert spec in WIZARD_FIELDS, f"missing from WIZARD_FIELDS: {spec.yaml_path}"


def test_wizard_fields_include_every_site_field():
    for spec in SITE_FIELDS:
        assert spec in WIZARD_FIELDS, f"missing from WIZARD_FIELDS: {spec.yaml_path}"


def test_wizard_section_order_covers_all_sections():
    sections_in_use = {f.section for f in WIZARD_FIELDS}
    declared = set(WIZARD_SECTION_ORDER)
    assert sections_in_use <= declared, \
        f"undeclared section(s) in WIZARD_FIELDS: {sections_in_use - declared}"


def test_no_duplicate_yaml_paths_in_wizard_fields():
    paths = [f.yaml_path for f in WIZARD_FIELDS]
    assert len(paths) == len(set(paths)), \
        "duplicate yaml_path in WIZARD_FIELDS"


def test_list_prefix_helper():
    from pvess_calc.site_checklist.field_specs import FieldSpec
    spec = FieldSpec(
        yaml_path="service.sub_panels[].name",
        label="x", section="electrical",
    )
    assert is_list_field(spec)
    assert list_prefix(spec) == "service.sub_panels"


# ─── Nesting ────────────────────────────────────────────────────────────────


def test_set_path_scalar():
    out: dict = {}
    set_path(out, "project.id", "abc")
    assert out == {"project": {"id": "abc"}}


def test_set_path_nested_creates_intermediates():
    out: dict = {}
    set_path(out, "pv_array.module.brand", "Generic")
    assert out == {"pv_array": {"module": {"brand": "Generic"}}}


def test_set_list_item_creates_list():
    out: dict = {}
    set_list_item(out, "service.sub_panels", 0, "name", "Sub Panel #1")
    set_list_item(out, "service.sub_panels", 0, "rating_a", 200)
    set_list_item(out, "service.sub_panels", 1, "name", "Sub Panel #2")
    assert out == {
        "service": {"sub_panels": [
            {"name": "Sub Panel #1", "rating_a": 200},
            {"name": "Sub Panel #2"},
        ]}
    }


# ─── State (save/load) ──────────────────────────────────────────────────────


def test_state_roundtrip(tmp_path: Path):
    state = WizardState(
        answers={"project.id": "abc", "service.main_panel_a": 200.0},
        next_index=5,
    )
    path = tmp_path / "state.json"
    state.save(path)
    assert path.exists()
    loaded = WizardState.load(path)
    assert loaded.answers == state.answers
    assert loaded.next_index == 5


def test_state_load_missing_returns_empty(tmp_path: Path):
    state = WizardState.load(tmp_path / "does-not-exist.json")
    assert state.answers == {}
    assert state.next_index == 0


# ─── End-to-end wizard via mock stdin ───────────────────────────────────────


def _build_input_stream() -> str:
    """Build a stdin stream covering every WIZARD_FIELDS prompt in the
    SAME order the wizard asks: scalars first (in WIZARD_FIELDS order),
    then list-count prompts (one per unique list parent prefix). Each
    list count answers "0" to skip the per-item loop."""
    scalar_answers: list[str] = []
    list_prefixes_seen: list[str] = []
    for spec in WIZARD_FIELDS:
        if spec.yaml_path == "project.id":
            continue
        if is_list_field(spec):
            prefix = list_prefix(spec)
            if prefix not in list_prefixes_seen:
                list_prefixes_seen.append(prefix)
            continue
        # Scalar
        if spec.field_type == "choice":
            scalar_answers.append(spec.choices[0])
        elif spec.field_type == "text":
            scalar_answers.append(_mock_text_for(spec))
        else:
            # number AND integer both consume one numeric line
            scalar_answers.append(_mock_number_for(spec))

    # List counts come AFTER all scalars (matches wizard queue order).
    list_answers = ["0"] * len(list_prefixes_seen)
    return "\n".join(scalar_answers + list_answers) + "\n"


def _mock_text_for(spec) -> str:
    """Plausible mock text answer that pydantic will accept."""
    # Field-specific defaults so the generated yaml validates
    if "email" in spec.yaml_path:
        return "test@example.com"
    if "phone" in spec.yaml_path:
        return "555-0100"
    if spec.yaml_path == "service.voltage":
        return "120/240 split-phase"
    if spec.yaml_path == "service.interconnection_methods":
        return "supply_side_tap"
    if spec.yaml_path == "project.initial_design_date":
        return "2026-01-01"
    return "test"


def _mock_number_for(spec) -> str:
    # Pick values that satisfy pydantic + cross-field constraints.
    if spec.yaml_path == "pv_array.modules":
        return "10"
    if spec.yaml_path == "pv_array.strings":
        return "1"
    if spec.yaml_path == "pv_array.modules_per_string":
        return "10"
    if spec.yaml_path == "pv_array.module.power_w":
        return "420"
    if spec.yaml_path == "pv_array.module.voc_stc":
        return "50"
    if spec.yaml_path == "pv_array.module.isc_stc":
        return "13"
    if spec.yaml_path == "pv_array.temp_min_c":
        return "-2"
    if spec.yaml_path == "pv_array.temp_max_c":
        return "50"
    if spec.yaml_path == "battery.quantity":
        return "1"
    if spec.yaml_path == "battery.nominal_voltage":
        return "51.2"
    if spec.yaml_path == "battery.capacity_kwh_each":
        return "5"
    if spec.yaml_path == "inverter.ac_output_v":
        return "240"
    if spec.yaml_path == "inverter.ac_output_a":
        return "33"
    if spec.yaml_path == "inverter.quantity":
        return "1"
    if spec.yaml_path == "service.main_panel_a":
        return "200"
    if spec.yaml_path == "service.busbar_a":
        return "200"
    return "0"


def test_wizard_end_to_end_produces_valid_yaml(tmp_path: Path, monkeypatch):
    """The acceptance test: drive every prompt with a mock answer,
    verify the resulting yaml passes Inputs.model_validate."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO(_build_input_stream()))

    from pvess_calc.wizard.runner import run_wizard
    yaml_path = run_wizard("test-001")

    assert yaml_path.exists()
    data = yaml.safe_load(yaml_path.read_text())
    from pvess_calc.schema import Inputs
    inputs = Inputs.model_validate(data)
    assert inputs.project.id == "test-001"
    assert inputs.pv_array.modules == 10
    assert inputs.service.main_panel_a == 200


def test_wizard_resume_continues_from_state(tmp_path: Path, monkeypatch):
    """Verify --resume picks up partial state: save state mid-way,
    then resume with remaining answers."""
    monkeypatch.chdir(tmp_path)

    # 1. Pre-seed a partial state — pretend the user answered the first
    # 5 fields then ctrl-C'd.
    state_file = WizardState.file_for("test-resume")
    partial = WizardState()
    partial.answers["project.id"] = "test-resume"
    partial.answers["project.name"] = "Pre-saved name"
    partial.answers["project.location"] = "Pre-saved loc"
    partial.answers["project.nec_edition"] = "2023"
    partial.answers["project.revision"] = "A"
    partial.save(state_file)

    # 2. Feed remaining answers via mock stdin.
    full_stream = _build_input_stream().split("\n")
    # Drop the first 4 answers (they're already in state — project.id
    # is handled by CLI, then 4 of the 6 admin project.* fields).
    remaining = "\n".join(full_stream[4:]) + "\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(remaining))

    from pvess_calc.wizard.runner import run_wizard
    yaml_path = run_wizard("test-resume", resume=True)

    data = yaml.safe_load(yaml_path.read_text())
    # The pre-saved values survived:
    assert data["project"]["name"] == "Pre-saved name"
    assert data["project"]["location"] == "Pre-saved loc"
    assert data["project"]["id"] == "test-resume"
    # State file cleaned up after success:
    assert not state_file.exists()


def test_wizard_generated_yaml_passes_pvess_calc(tmp_path: Path, monkeypatch):
    """Integration: yaml from the wizard must be acceptable by the
    actual calc engine, not just pydantic. This guards against schema
    fields the wizard "satisfies" but with semantically-wrong values."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO(_build_input_stream()))

    from pvess_calc.calc.engine import run
    from pvess_calc.schema import Inputs
    from pvess_calc.wizard.runner import run_wizard

    yaml_path = run_wizard("test-calc")
    inputs = Inputs.from_yaml(yaml_path)
    result = run(inputs)
    # Sanity: engine ran without crashing + produced PV calc.
    assert result.pv_string.string_voc_cold > 0
    assert result.pv_ocpd_a > 0


# ─── K.3c integration (Fix #1) ──────────────────────────────────────────


def test_wizard_writes_roof_sections_from_google_solar(tmp_path: Path, monkeypatch):
    """K.3c regression-bait: when `_prefill_from_address` returns a
    Google Solar roof_sections list, the wizard MUST inject it into
    `site.roof_sections` of the written yaml. Pre-Fix-#1 the list was
    silently dropped because the wizard's scalar prompt path doesn't
    handle list pre-fills.

    Patches `_prefill_from_address` to bypass real network/API and
    returns a deterministic 3-face Google Solar payload."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO(_build_input_stream()))

    fake_sections = [
        {"name": "South Roof", "roof_type": "Comp Shingle",
         "pitch_deg": 22.4, "azimuth_deg": 178.2,
         "width_ft": 20.4, "height_ft": 20.4,
         "module_count": 0, "shape": "rect"},
        {"name": "West Roof", "roof_type": "Comp Shingle",
         "pitch_deg": 22.0, "azimuth_deg": 270.0,
         "width_ft": 12.0, "height_ft": 12.0,
         "module_count": 0, "shape": "rect"},
        {"name": "North Roof", "roof_type": "Comp Shingle",
         "pitch_deg": 22.4, "azimuth_deg": 358.0,
         "width_ft": 19.5, "height_ft": 19.5,
         "module_count": 0, "shape": "rect"},
    ]
    fake_prefills = {
        "project.location": "Frisco, TX",
        "project.nec_edition": "2020",
        "__k3c_roof_sections": fake_sections,
    }
    monkeypatch.setattr(
        "pvess_calc.wizard.runner._prefill_from_address",
        lambda _addr: fake_prefills,
    )

    from pvess_calc.schema import Inputs
    from pvess_calc.wizard.runner import run_wizard

    yaml_path = run_wizard("test-k3c", address="7652 Glasshouse Walk, Frisco TX")

    data = yaml.safe_load(yaml_path.read_text())
    # The 3 K.3c faces survived end-to-end into the yaml:
    assert "site" in data
    assert "roof_sections" in data["site"]
    sections = data["site"]["roof_sections"]
    assert len(sections) == 3
    names = [s["name"] for s in sections]
    assert names == ["South Roof", "West Roof", "North Roof"]
    # And pydantic accepts the result:
    inputs = Inputs.model_validate(data)
    assert len(inputs.site.roof_sections) == 3
    assert inputs.site.roof_sections[0].pitch_deg == 22.4
