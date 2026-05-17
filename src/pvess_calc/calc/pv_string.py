"""PV source-circuit calculations (NEC 690.7, 690.8)."""
from __future__ import annotations

from dataclasses import dataclass

from ..nec import get_rules
from ..nec.tables import table_690_7_factor
from ..schema import PvArray


@dataclass
class PvStringResult:
    voc_stc_per_module: float
    voc_cold_per_module: float
    voc_correction_method: str       # "datasheet_beta" or "table_690_7"
    voc_correction_factor: float     # multiplier vs STC
    string_voc_cold: float
    isc_stc: float
    isc_690_8_a: float               # Isc × 1.25 per 690.8(A)(1)
    conductor_required_a: float      # Isc × 1.25 × 1.25 per 690.8(B)
    ocpd_minimum_a: float            # Isc × 1.25 × 1.25 per 690.9(B)
    exceeds_max_system_voltage: bool


def compute_pv_string(array: PvArray, *, nec_edition: str = "2023") -> PvStringResult:
    module = array.module
    voc_stc = module.voc_stc
    isc_stc = module.isc_stc
    rules = get_rules(nec_edition)

    design_low_c = array.design_low_temp_c

    if module.voc_temp_coeff_pct_per_c is not None:
        beta = module.voc_temp_coeff_pct_per_c / 100.0
        voc_correction = 1.0 + beta * (design_low_c - 25.0)
        method = "datasheet_beta"
    else:
        voc_correction = table_690_7_factor(design_low_c)
        method = "table_690_7"

    voc_cold_per_module = voc_stc * voc_correction
    string_voc_cold = voc_cold_per_module * array.modules_per_string
    isc_690_8a = isc_stc * rules.PV_SOURCE_CURRENT_FACTOR
    conductor_a = isc_690_8a * rules.PV_CONDUCTOR_AMPACITY_FACTOR
    ocpd_min = isc_690_8a * rules.PV_OCPD_FACTOR

    return PvStringResult(
        voc_stc_per_module=voc_stc,
        voc_cold_per_module=voc_cold_per_module,
        voc_correction_method=method,
        voc_correction_factor=voc_correction,
        string_voc_cold=string_voc_cold,
        isc_stc=isc_stc,
        isc_690_8_a=isc_690_8a,
        conductor_required_a=conductor_a,
        ocpd_minimum_a=ocpd_min,
        exceeds_max_system_voltage=(
            string_voc_cold > rules.PV_MAX_SYSTEM_VOLTAGE_DWELLING
        ),
    )
