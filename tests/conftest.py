"""Shared pytest fixtures and helpers."""
from __future__ import annotations

from pathlib import Path

import pytest

from pvess_calc.schema import (
    Battery,
    Inputs,
    Inverter,
    Loads,
    PvArray,
    PvModule,
    ProjectMeta,
    Service,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


def make_inputs(
    *,
    modules: int = 24,
    strings: int = 2,
    main_panel_a: float = 200,
    busbar_a: float = 200,
    inverter_a: float = 30,
    battery_qty: int = 2,
    per_unit: bool = True,
    voc_temp_coeff: float | None = -0.28,
    design_low_c: float = -5.0,
    interconnection_methods: list[str] | None = None,
    # K.2.5: pre-existing PV/ESS already on the service (busbar load).
    existing_solar_breaker_a_msp: float = 0.0,
    sub_panels: list[dict] | None = None,
    # K.7: NEC edition override (for cross-version integration tests).
    nec_edition: str = "2023",
) -> Inputs:
    methods = interconnection_methods or ["120%_rule", "sum_rule", "supply_side_tap"]
    service_kwargs: dict = dict(
        main_panel_a=main_panel_a, busbar_a=busbar_a,
        busbar_source="nameplate", voltage="120/240 split-phase",
        interconnection_methods=methods,
        existing_solar_breaker_a_msp=existing_solar_breaker_a_msp,
    )
    if sub_panels:
        service_kwargs["sub_panels"] = sub_panels
    return Inputs(
        project=ProjectMeta(
            id="test", name="Test", location="Anywhere",
            ahj="Test", nec_edition=nec_edition,
        ),
        pv_array=PvArray(
            modules=modules,
            strings=strings,
            modules_per_string=modules // strings,
            module=PvModule(
                brand="X", model="Y", power_w=420,
                voc_stc=49.5, isc_stc=13.8,
                voc_temp_coeff_pct_per_c=voc_temp_coeff,
                isc_temp_coeff_pct_per_c=0.048,
            ),
            ashrae_2pct_min_c=design_low_c,
            temp_min_c=design_low_c,
            temp_max_c=45.0,
        ),
        battery=Battery(
            brand="Tesla", model="PW3", quantity=battery_qty,
            nominal_voltage=48, capacity_kwh_each=13.5,
        ),
        inverter=Inverter(
            brand="Tesla", model="PW3", ac_output_v=240,
            ac_output_a=inverter_a, per_unit=per_unit,
        ),
        service=Service(**service_kwargs),
        loads=Loads(critical_subpanel_a=100, whole_home_backup=True),
    )
