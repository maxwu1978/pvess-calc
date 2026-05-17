"""Tests for the Phase 2 DXF generator."""
from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest

from pvess_calc.calc.engine import run
from pvess_calc.dxf.render import LAYERS, render_dxf, render_for_result
from tests.conftest import make_inputs


@pytest.fixture
def rendered_dxf(tmp_path: Path):
    result = run(make_inputs())
    out = tmp_path / "sheet.dxf"
    render_dxf(result, out)
    return out, ezdxf.readfile(str(out))


def test_dxf_file_is_valid_autocad_format(rendered_dxf):
    """ezdxf.readfile would raise on invalid DXF — opening it round-trip is
    the strongest portability check we have without a CAD app."""
    out, doc = rendered_dxf
    assert out.exists()
    assert out.stat().st_size > 0
    assert doc.dxfversion >= "AC1027"  # R2013+


def test_dxf_units_are_inches(rendered_dxf):
    """ACADE / AutoCAD defaults: $INSUNITS = 1 means inches."""
    _, doc = rendered_dxf
    assert doc.header["$INSUNITS"] == 1


def test_dxf_has_all_expected_layers(rendered_dxf):
    _, doc = rendered_dxf
    present = {l.dxf.name for l in doc.layers}
    for name in LAYERS:
        assert name in present, f"layer {name} missing"


def test_dxf_device_count_matches_inverter_quantity(rendered_dxf):
    """N PV strings + 6 fixed (COMB/RSD/AC-DISC/MSP/METER/ESS) + N inverters.
    Default fixture: 2 strings, 2 PW3 batteries with per_unit=True → 2 inv.
    """
    _, doc = rendered_dxf
    msp = doc.modelspace()
    inserts = [e for e in msp if e.dxftype() == "INSERT"]
    # 2 PV strings + 6 fixed (Phase B added meter) + 2 inverters = 10
    assert len(inserts) == 10


def test_dxf_renders_three_inverters_in_parallel(tmp_path: Path):
    """Schema's `inverter.quantity` should produce N inverter blocks regardless
    of battery count when per_unit=False."""
    inputs = make_inputs(
        battery_qty=8, per_unit=False, inverter_a=33,
    )
    inputs.inverter.quantity = 3
    result = run(inputs)
    out = tmp_path / "sheet.dxf"
    render_dxf(result, out)
    doc = ezdxf.readfile(str(out))
    msp = doc.modelspace()
    inserts = [e for e in msp if e.dxftype() == "INSERT"]
    # 2 PV strings + 6 fixed + 3 inverters = 11
    assert len(inserts) == 11
    inv_tags = {
        a.dxf.text
        for e in inserts for a in e.attribs
        if a.dxf.tag == "TAG1" and a.dxf.text.startswith("INV-")
    }
    assert inv_tags == {"INV-1", "INV-2", "INV-3"}


def test_dxf_pv_string_count_matches_array_strings(tmp_path: Path):
    """When pv_array.strings > 1, the renderer emits one PV block per string."""
    inputs = make_inputs(modules=60, strings=6)
    inputs.pv_array.modules_per_string = 10
    result = run(inputs)
    out = tmp_path / "sheet.dxf"
    render_dxf(result, out)
    doc = ezdxf.readfile(str(out))
    msp = doc.modelspace()
    pv_tags = {
        a.dxf.text
        for e in msp if e.dxftype() == "INSERT"
        for a in e.attribs
        if a.dxf.tag == "TAG1" and a.dxf.text.startswith("PV-S")
    }
    assert pv_tags == {f"PV-S{k}" for k in range(1, 7)}


def test_dxf_single_string_pv_stays_aggregated(tmp_path: Path):
    """A 1-string array still renders as a single PV-1 block (legacy layout)."""
    inputs = make_inputs(modules=12, strings=1)
    inputs.pv_array.modules_per_string = 12
    result = run(inputs)
    out = tmp_path / "sheet.dxf"
    render_dxf(result, out)
    doc = ezdxf.readfile(str(out))
    msp = doc.modelspace()
    pv_tags = {
        a.dxf.text
        for e in msp if e.dxftype() == "INSERT"
        for a in e.attribs
        if a.dxf.tag == "TAG1" and a.dxf.text.startswith("PV-")
    }
    assert pv_tags == {"PV-1"}


def test_device_blocks_carry_acade_attributes(rendered_dxf):
    """Each inserted device should have TAG1/DESC1 attribute values so ACADE
    recognizes them as components on import."""
    _, doc = rendered_dxf
    msp = doc.modelspace()
    inserts = [e for e in msp if e.dxftype() == "INSERT"]
    for ins in inserts:
        tags = {a.dxf.tag: a.dxf.text for a in ins.attribs}
        assert "TAG1" in tags
        assert tags["TAG1"]  # non-empty
        assert "DESC1" in tags


def test_wires_use_dc_and_ac_layers(rendered_dxf):
    """Conductor polylines should be split across WIRE_DC / WIRE_AC layers."""
    _, doc = rendered_dxf
    msp = doc.modelspace()
    layers_used = {
        e.dxf.layer
        for e in msp
        if e.dxftype() == "LWPOLYLINE"
    }
    assert "WIRE_DC" in layers_used
    assert "WIRE_AC" in layers_used


def test_conductor_schedule_has_tag_rows(rendered_dxf):
    """The schedule should reference tags A/B/C/D matching the wire tags."""
    _, doc = rendered_dxf
    msp = doc.modelspace()
    schedule_text = " ".join(
        e.dxf.text
        for e in msp
        if e.dxftype() == "TEXT" and e.dxf.layer == "SCHEDULE"
    )
    for tag in ("A", "B", "C", "D"):
        assert f" {tag} " in f" {schedule_text} " or schedule_text.startswith(tag) or f" {tag}" in schedule_text


def test_title_block_includes_project_metadata(rendered_dxf):
    """Title block should embed project name and AHJ from inputs."""
    _, doc = rendered_dxf
    msp = doc.modelspace()
    tb_text = " ".join(
        e.dxf.text
        for e in msp
        if e.dxftype() == "TEXT" and e.dxf.layer == "TITLE_BLOCK"
    )
    assert "Test" in tb_text       # default project name from make_inputs
    assert "2023" in tb_text       # NEC edition


def test_render_for_result_returns_device_count(tmp_path: Path):
    """Default fixture: 2 strings + 6 fixed + 2 inverters = 10 devices."""
    result = run(make_inputs())
    n = render_for_result(result, tmp_path / "x.dxf")
    assert n == 10
