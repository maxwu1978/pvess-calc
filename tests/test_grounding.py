"""Tests for the NEC grounding/bonding tables and the EE-2 sheet renderer."""
from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest

from pvess_calc.calc.engine import run
from pvess_calc.calc.grounding import (
    select_ac_gec,
    select_dc_gec,
    select_egc,
    service_conductor_size,
)
from pvess_calc.dxf.grounding_sheet import render_grounding_dxf
from tests.conftest import make_inputs


# --- NEC 250.66 / 250.122 selection tables ---------------------------------

def test_service_conductor_size_200a_residential():
    """A standard 200A residential service uses 2/0 CU @ 75°C per 310.16."""
    assert service_conductor_size(200) == "2/0"


def test_service_conductor_smaller_amps():
    """310.16 @ 75°C: 3 AWG = 100A, 2 AWG = 115A, 1 AWG = 130A, 1/0 = 150A.
    A 125A service needs ≥125A ampacity, so 2 AWG (115A) is short and the
    selection lands on 1 AWG."""
    assert service_conductor_size(100) == "3"
    assert service_conductor_size(115) == "2"
    assert service_conductor_size(125) == "1"
    assert service_conductor_size(175) == "1/0"


def test_ac_gec_for_200a_service_is_4_awg():
    """200A → 2/0 SE conductor → 4 AWG GEC per Table 250.66."""
    cond, gec = select_ac_gec(200)
    assert cond == "2/0"
    assert gec == "4"


def test_ac_gec_for_400a_service():
    """400A → larger SE conductor → larger GEC."""
    _, gec = select_ac_gec(400)
    # 400A → 500 kcmil SE → 1/0 GEC
    assert gec == "1/0"


def test_dc_gec_residential_pv_lands_at_8_or_6_awg():
    """Typical residential PV source circuits (Isc×1.25 ≤ 30A) → 8 AWG GEC."""
    assert select_dc_gec(17.25) == "8"   # Phoenix: 13.8 × 1.25 = 17.25
    assert select_dc_gec(40) == "6"      # bigger array bumps to 6 AWG


def test_egc_table_250_122_key_rows():
    """Spot-check rows that residential PV+ESS systems actually hit."""
    assert select_egc(15)  == "14"
    assert select_egc(20)  == "12"
    assert select_egc(25)  == "10"   # falls into ≤60A bucket
    assert select_egc(45)  == "10"
    assert select_egc(100) == "8"
    assert select_egc(125) == "6"    # ≤200A
    assert select_egc(200) == "6"
    assert select_egc(225) == "4"


def test_compute_grounding_phoenix_scenario():
    """End-to-end: run() on a 3×8kW system → grounding fields fully populated."""
    inputs = make_inputs(battery_qty=8, per_unit=False, inverter_a=33)
    inputs.inverter.quantity = 3
    result = run(inputs)
    g = result.grounding

    assert g.service_conductor_size == "2/0"
    assert g.ac_gec_size == "4"        # 200A service → 4 AWG GEC
    assert g.dc_gec_size == "8"        # PV source ≤30A → 8 AWG
    assert g.egc_pv_source == "10"     # 25A OCPD → 10 AWG
    assert g.egc_inverter_ac == "10"   # 45A OCPD per inverter → 10 AWG
    assert g.egc_aggregate_ac == "6"   # 125A OCPD → 6 AWG
    assert g.egc_ess == "6"


# --- EE-2 sheet rendering ---------------------------------------------------

@pytest.fixture
def rendered_ee2(tmp_path: Path):
    result = run(make_inputs())
    out = tmp_path / "sheet-EE-2.dxf"
    render_grounding_dxf(result, out)
    return out, ezdxf.readfile(str(out))


def test_ee2_sheet_is_valid_dxf(rendered_ee2):
    out, doc = rendered_ee2
    assert out.exists()
    assert out.stat().st_size > 0
    assert doc.dxfversion >= "AC1027"


def test_ee2_title_block_says_grounding(rendered_ee2):
    _, doc = rendered_ee2
    msp = doc.modelspace()
    text = " ".join(
        e.dxf.text for e in msp
        if e.dxftype() == "TEXT" and e.dxf.layer == "TITLE_BLOCK"
    )
    assert "EE-2" in text
    assert "GROUNDING" in text.upper()


def test_ee2_schedule_references_nec_clauses(rendered_ee2):
    """The grounding schedule should cite 250.66, 250.122, 250.166, 690.45."""
    _, doc = rendered_ee2
    msp = doc.modelspace()
    text = " ".join(
        e.dxf.text for e in msp
        if e.dxftype() == "TEXT" and e.dxf.layer == "SCHEDULE"
    )
    assert "250.66" in text
    assert "250.122" in text
    assert "690.47" in text or "250.166" in text


def test_ee2_diagram_has_three_grounding_electrodes(rendered_ee2):
    """The electrode cluster should label rod / water pipe / Ufer."""
    _, doc = rendered_ee2
    msp = doc.modelspace()
    text = " ".join(
        e.dxf.text for e in msp
        if e.dxftype() == "TEXT" and e.dxf.layer == "ANNOTATION"
    ).upper()
    assert "GROUND ROD" in text
    assert "WATER PIPE" in text
    assert "UFER" in text or "CONCRETE" in text


def test_ee2_equipment_grounding_bus_drawn(rendered_ee2):
    """A horizontal polyline on the WIRE_GROUND layer represents the bus."""
    _, doc = rendered_ee2
    msp = doc.modelspace()
    polys = [
        e for e in msp
        if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "WIRE_GROUND"
    ]
    # bus + GEC vertical + GES bus + 3 electrodes ≈ 7+ polylines
    assert len(polys) >= 5
