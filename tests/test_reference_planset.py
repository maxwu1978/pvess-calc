"""Stage 9.11-9.17 reference-style permit package tests."""
from __future__ import annotations

from pathlib import Path

import pypdf
import ezdxf

from pvess_calc.calc.engine import run
from pvess_calc.doctor import (
    _check_ee21_dxf_cad_geometry,
    _check_ee21_no_phantom_ocpd,
    _check_ee21_no_wire_text_overlap,
    _check_ee21_one_line_complete,
    _check_ee21_topology_consistent,
    _check_mounting_data_consistent,
    _check_pv5_mounting_detail_complete,
    _check_reference_profile_attachments_ready,
    _check_reference_profile_site_intake_complete,
)
from pvess_calc.dxf.one_line import render_one_line_dxf
from pvess_calc.electrical.topology import build_electrical_topology
from pvess_calc.permit.builder import _selected_sheets, build_permit_package
from pvess_calc.permit.one_line import render_one_line_diagram
from pvess_calc.permit.sheet_registry import registry_for_profile
from pvess_calc.schema import Inputs


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRISCO = PROJECT_ROOT / "projects" / "003-frisco-glasshouse" / "inputs.yaml"


def _pdf_text(path: Path) -> str:
    return "\n".join(page.extract_text() or ""
                     for page in pypdf.PdfReader(str(path)).pages)


def _dxf_text(path: Path) -> str:
    doc = ezdxf.readfile(str(path))
    texts: list[str] = []
    for entity in doc.modelspace():
        if entity.dxftype() == "TEXT":
            texts.append(entity.dxf.text)
        elif entity.dxftype() == "INSERT":
            texts.extend(attr.dxf.text for attr in entity.attribs)
    return " ".join(" ".join(texts).split())


def test_stage911_reference_registry_matches_target_sheet_order():
    sheets = registry_for_profile("tx_residential_pv")

    assert [s.display_code for s in sheets] == [
        "PV-1",
        "PV-2",
        "PV-3",
        "PV-4",
        "PV-5",
        "EE-1",
        "EE-2",
        "EE-2.1",
        "EE-3",
        "EE-4",
        "EE-5",
        "PV-6",
        "PV-7",
        "SPEC",
    ]
    assert registry_for_profile("wyssling_like") == sheets
    one_line = next(s for s in sheets if s.code == "one-line")
    assert one_line.output_kind == "dxf"
    assert one_line.renderer == "pvess_calc.dxf.one_line:render_one_line_dxf"


def test_stage912_one_line_sheet_is_only_emitted_for_line_side_paths():
    inputs = Inputs.from_yaml(FRISCO)
    line_side = run(inputs)

    line_side_codes = [
        s.code for s in _selected_sheets(
            line_side, package_profile="tx_residential_pv", ahj_name=None,
        )
    ]
    assert "one-line" in line_side_codes

    load_side_inputs = inputs.model_copy(deep=True)
    load_side_inputs.service.interconnection_methods = ["120%_rule"]
    load_side_inputs.service.busbar_a = 225
    load_side = run(load_side_inputs)

    load_side_codes = [
        s.code for s in _selected_sheets(
            load_side, package_profile="tx_residential_pv", ahj_name=None,
        )
    ]
    assert load_side.interconnect.recommended == "120%_rule"
    assert "one-line" not in load_side_codes


def test_stage913_to_916_reference_package_adds_draft_photos_specs(tmp_path: Path):
    result = run(Inputs.from_yaml(FRISCO))
    out = tmp_path / "reference-package.pdf"

    n_pages = build_permit_package(result, out)
    text = _pdf_text(out)

    assert n_pages >= 21
    assert "STRUCTURAL REVIEW DRAFT" in text
    assert "Min embedment:\n2.5 in" in text
    assert "PV-2 · SITE PLAN" in text
    assert "PV-3 · PROPERTY PLAN" in text
    assert "MOUNTING DETAILS" in text
    assert "PV-5" in text
    assert "GENERAL ROOF MOUNT DETAIL" in text
    assert "ROOF MOUNT CROSS SECTION DETAIL" in text
    assert "ROOF MOUNT PLAN VIEW DETAIL" in text
    assert "6\" MAX SPACE FROM ROOF SURFACE" in text
    assert "MIN EMBEDMENT DEPTH SEE TABLE ON PV-4" in text
    assert "EE-1 · STRING PLAN" in text
    assert "EE-3 · ELECTRICAL NOTES" in text
    assert "EE-2.1" in text
    assert "PV-7 · SITE PHOTOS" in text
    assert "PHOTO REQUIRED" not in text
    assert "Proposed inverter/equipment wall" in text
    assert "MIN 8200~11400TL-XH-US" in text
    assert "HYS-11.5LV-USG1" in text
    assert "R8KLNA" in text


def test_stage101_ee21_topology_drives_dxf_one_line(tmp_path: Path):
    result = run(Inputs.from_yaml(FRISCO))
    topology = build_electrical_topology(result)
    out = tmp_path / "ee21.dxf"

    render_one_line_dxf(result, out)
    doc = ezdxf.readfile(str(out))
    msp = doc.modelspace()
    text = _dxf_text(out)

    rows = topology.schedule_by_tag()
    assert set(rows) == {"A", "B", "C", "D"}
    assert topology.edge_by_schedule_tag().keys() == rows.keys()
    assert rows["A"].ocpd_a == result.pv_ocpd_a
    assert rows["D"].ocpd_a == result.ess.ac_disconnect_ocpd_a
    assert rows["D"].size == f"{result.ess_conductor.size} AWG"
    for token in [
        "EE-2.1 - ONE LINE DIAGRAM",
        "PV DC OCPD",
        "CONDUCTOR / OCPD SCHEDULE",
        "RACEWAY",
        "LINE SIDE TAP",
        "SUPPLY-SIDE CONNECTION AHEAD OF MAIN SERVICE DISCONNECT",
        "DC-COMB-1",
        "AC-DISC-1",
        "TAP-1",
    ]:
        assert token in text
    forbidden_wire_layers = {
        "WIRE_DC_POS", "WIRE_DC_NEG", "WIRE_AC_L1", "WIRE_AC_L2", "WIRE_AC_N",
    }
    assert not [
        e.dxf.layer for e in msp.query("LWPOLYLINE LINE")
        if e.dxf.layer in forbidden_wire_layers
    ]
    assert len([
        e for e in msp.query("LWPOLYLINE LINE")
        if e.dxf.layer == "WIRE_ONE_LINE"
    ]) >= 8


def test_stage101_legacy_one_line_wrapper_uses_temp_dxf(tmp_path: Path):
    result = run(Inputs.from_yaml(FRISCO))
    out = tmp_path / "legacy-one-line.pdf"

    render_one_line_diagram(result, out)

    assert out.exists()
    assert out.stat().st_size > 1000
    assert not out.with_suffix(".dxf").exists()


def test_stage917_reference_profile_doctor_guards_for_frisco():
    result = run(Inputs.from_yaml(FRISCO))

    [site] = _check_reference_profile_site_intake_complete(result)
    [attachments] = _check_reference_profile_attachments_ready(result)
    [mounting] = _check_mounting_data_consistent(result)
    [pv5] = _check_pv5_mounting_detail_complete(result)
    [ee21] = _check_ee21_one_line_complete(result)
    [phantom] = _check_ee21_no_phantom_ocpd(result)
    [topology] = _check_ee21_topology_consistent(result)
    [geometry] = _check_ee21_dxf_cad_geometry(result)
    [wire_text] = _check_ee21_no_wire_text_overlap(result)

    assert site.status == "PASS", site.detail
    assert attachments.status == "WARN"
    assert "signed structural letter missing" in attachments.detail
    assert "PV-7 photo placeholders" not in attachments.detail
    assert "SPEC manufacturer PDFs missing" not in attachments.detail
    assert mounting.status == "PASS", mounting.detail
    assert pv5.status == "PASS", pv5.detail
    assert ee21.status == "PASS", ee21.detail
    assert phantom.status == "PASS", phantom.detail
    assert topology.status == "PASS", topology.detail
    assert geometry.status == "PASS", geometry.detail
    assert wire_text.status == "PASS", wire_text.detail


def test_stage101_mounting_lint_catches_flashvue_flashfoot_mix():
    inputs = Inputs.from_yaml(FRISCO).model_copy(deep=True)
    inputs.project.roof_info.flashing = "IronRidge FlashVue Flashing"
    inputs.site.mounting.flashing = "IronRidge FlashFoot 2"
    result = run(inputs)

    [check] = _check_mounting_data_consistent(result)

    assert check.status == "FAIL"
    assert "conflicts" in check.detail
