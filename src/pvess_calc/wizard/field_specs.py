"""Wizard field manifest — extends SITE_FIELDS (on-site/lookup, used by
the K.1 site-survey checklist) with DESIGN_FIELDS (project metadata,
engineer/installer info, equipment selection, design choices) to cover
every input the `pvess-calc` engine needs to run successfully.

Adding a new wizard prompt = appending a `FieldSpec` here OR in
`site_checklist/field_specs.py`. The wizard iterates the combined list
in the order defined by `WIZARD_FIELDS` (which is the section order
declared below, then the within-section order of each contributing
file).

Field reuse: `FieldSpec` is the same dataclass used by K.1 — keeps
labels / hints / yaml paths consistent between the printed survey form
and the interactive CLI wizard.
"""
from __future__ import annotations

from ..site_checklist.field_specs import FieldSpec, SITE_FIELDS


# ─────────────────────────────────────────────────────────────────────────────
# DESIGN_FIELDS — the prompts the wizard asks that AREN'T on-site survey
# items. These are engineering choices (NEC edition, equipment refs,
# interconnection methods) or admin (project ID, engineer firm).
# ─────────────────────────────────────────────────────────────────────────────

DESIGN_FIELDS: tuple[FieldSpec, ...] = (
    # ── Project meta (asked first; project.id becomes the folder name) ──
    FieldSpec(
        yaml_path="project.id",
        label="Project ID (folder name, e.g. 003-jones-residence)",
        field_type="text",
        section="admin",
    ),
    FieldSpec(
        yaml_path="project.name",
        label="Project display name (used on cover sheet)",
        field_type="text",
        section="admin",
    ),
    FieldSpec(
        yaml_path="project.location",
        label="Project city + state (e.g. Phoenix, AZ)",
        field_type="text",
        section="admin",
    ),
    FieldSpec(
        yaml_path="project.nec_edition",
        label="NEC edition",
        field_type="choice",
        choices=("2023", "2020", "2017"),
        section="admin",
    ),
    FieldSpec(
        yaml_path="project.revision",
        label="Drawing revision letter (A, B, …)",
        field_type="text",
        section="admin",
    ),
    FieldSpec(
        yaml_path="project.drawn_by",
        label="Drawn by (initials or name)",
        field_type="text",
        section="admin",
    ),
    FieldSpec(
        yaml_path="project.initial_design_date",
        label="Initial design date (YYYY-MM-DD)",
        field_type="text",
        section="admin",
    ),
    # ── Design engineer ──
    FieldSpec(
        yaml_path="design_engineer.firm",
        label="Design engineer firm name",
        field_type="text",
        section="admin",
    ),
    FieldSpec(
        yaml_path="design_engineer.address",
        label="Engineer firm address",
        field_type="text",
        section="admin",
    ),
    FieldSpec(
        yaml_path="design_engineer.contact_email",
        label="Engineer contact email",
        field_type="text",
        section="admin",
    ),
    FieldSpec(
        yaml_path="design_engineer.contact_phone",
        label="Engineer contact phone",
        field_type="text",
        section="admin",
    ),
    FieldSpec(
        yaml_path="design_engineer.firm_number",
        label="Engineer firm number / PE license #",
        field_type="text",
        section="admin",
    ),
    # ── Installer ──
    FieldSpec(
        yaml_path="installer.company",
        label="Installer company name",
        field_type="text",
        section="admin",
    ),
    FieldSpec(
        yaml_path="installer.address",
        label="Installer address",
        field_type="text",
        section="admin",
    ),
    # ── PV array equipment ──
    FieldSpec(
        yaml_path="pv_array.modules",
        label="Total PV module count",
        field_type="integer",
        section="equipment",
    ),
    FieldSpec(
        yaml_path="pv_array.strings",
        label="Number of strings",
        field_type="integer",
        section="equipment",
    ),
    FieldSpec(
        yaml_path="pv_array.modules_per_string",
        label="Modules per string",
        field_type="integer",
        section="equipment",
    ),
    FieldSpec(
        yaml_path="pv_array.module.brand",
        label="PV module brand (e.g. 'Generic', 'Q CELLS')",
        field_type="text",
        section="equipment",
    ),
    FieldSpec(
        yaml_path="pv_array.module.model",
        label="PV module model (e.g. 'MONO-420-144')",
        field_type="text",
        section="equipment",
    ),
    FieldSpec(
        yaml_path="pv_array.module.power_w",
        label="Module rated power",
        unit="W",
        section="equipment",
    ),
    FieldSpec(
        yaml_path="pv_array.module.voc_stc",
        label="Module Voc at STC",
        unit="V",
        section="equipment",
    ),
    FieldSpec(
        yaml_path="pv_array.module.isc_stc",
        label="Module Isc at STC",
        unit="A",
        section="equipment",
    ),
    # ── Battery (ESS) ──
    FieldSpec(
        yaml_path="battery.brand",
        label="Battery brand (e.g. 'EG4', 'Tesla')",
        field_type="text",
        section="equipment",
    ),
    FieldSpec(
        yaml_path="battery.model",
        label="Battery model (e.g. 'LifePower4 V2')",
        field_type="text",
        section="equipment",
    ),
    FieldSpec(
        yaml_path="battery.quantity",
        label="Battery quantity (number of units)",
        field_type="integer",
        section="equipment",
    ),
    FieldSpec(
        yaml_path="battery.nominal_voltage",
        label="Battery nominal voltage",
        unit="V",
        section="equipment",
    ),
    FieldSpec(
        yaml_path="battery.capacity_kwh_each",
        label="Battery capacity per unit",
        unit="kWh",
        section="equipment",
    ),
    # ── K.2.6b: ESS physical install location & setbacks ────────────────
    FieldSpec(
        yaml_path="battery.install_location",
        label="ESS install location",
        explanation=("Determines applicable code: IRC R328 governs "
                     "residential indoor / garage installs; outdoor "
                     "follows NEC 706 only. 'outdoor_protected' = "
                     "weather-rated enclosure (better thermal behavior)."),
        field_type="choice",
        choices=("indoor", "garage", "outdoor",
                 "outdoor_protected", "unknown"),
        section="electrical",
    ),
    FieldSpec(
        yaml_path="battery.distance_to_doorway_ft",
        label="Distance from ESS to nearest doorway",
        unit="ft",
        explanation=("IRC R328.5 requires ≥3 ft from doors leading to "
                     "occupiable spaces (indoor / garage installs)."),
        where_to_find="Measured along the wall from ESS centerline to door jamb.",
        section="electrical",
    ),
    FieldSpec(
        yaml_path="battery.distance_to_window_ft",
        label="Distance from ESS to nearest operable window",
        unit="ft",
        explanation="IRC R328.5 requires ≥3 ft from windows that open into occupiable spaces.",
        section="electrical",
    ),
    FieldSpec(
        yaml_path="battery.distance_to_egress_ft",
        label="Distance from ESS to nearest egress path",
        unit="ft",
        explanation=("IRC R328.4 requires clear egress; minimum 3 ft "
                     "from any required emergency egress path."),
        section="electrical",
    ),
    # ── Inverter ──
    FieldSpec(
        yaml_path="inverter.brand",
        label="Inverter brand (e.g. 'Generic', 'Sol-Ark')",
        field_type="text",
        section="equipment",
    ),
    FieldSpec(
        yaml_path="inverter.model",
        label="Inverter model (e.g. '8K Hybrid')",
        field_type="text",
        section="equipment",
    ),
    FieldSpec(
        yaml_path="inverter.ac_output_v",
        label="Inverter AC output voltage",
        unit="V",
        section="equipment",
    ),
    FieldSpec(
        yaml_path="inverter.ac_output_a",
        label="Inverter AC output current per unit",
        unit="A",
        section="equipment",
    ),
    FieldSpec(
        yaml_path="inverter.quantity",
        label="Inverter quantity (number of inverters in parallel)",
        field_type="integer",
        section="equipment",
    ),
    # ── Interconnection (design choice based on busbar) ──
    FieldSpec(
        yaml_path="service.interconnection_methods",
        label="Candidate interconnection methods (comma-separated)",
        explanation="Engine will validate each; first PASS becomes the recommendation.",
        where_to_find="Choose from: 120%_rule, sum_rule, supply_side_tap, center_fed",
        field_type="text",
        section="electrical",
    ),
    # ── K.2.5: household demand context ──
    FieldSpec(
        yaml_path="loads.hvac_type",
        label="HVAC type",
        explanation=("Drives ESS backup-runtime estimate. heat_pump = highest "
                     "winter load; gas_furnace_ac = moderate; "
                     "electric_resistance = highest peak."),
        field_type="choice",
        choices=("heat_pump", "gas_furnace_ac", "electric_resistance", "unknown"),
        section="admin",
    ),
    FieldSpec(
        yaml_path="loads.has_ev",
        label="Does the home currently have an EV charger?",
        field_type="choice",
        choices=("no", "yes"),
        section="admin",
    ),
    FieldSpec(
        yaml_path="loads.planned_ev",
        label="Plan to add EV charger in next 2 years?",
        field_type="choice",
        choices=("no", "yes"),
        section="admin",
    ),
    FieldSpec(
        yaml_path="loads.planned_electrification",
        label="Plan to add heat pump / induction / heat-pump water heater?",
        explanation="If yes, sizing recommendation reserves headroom for future load.",
        field_type="choice",
        choices=("no", "yes"),
        section="admin",
    ),
    # K.7 [2-3/4]: export tariff model drives K.4 customer-summary ROI.
    # `pvess init --address` auto-fills this per state (CA→ca_nem3,
    # HI→hi_self_consumption, else→1to1_nem) via the K.3 lookup chain.
    FieldSpec(
        yaml_path="loads.export_tariff_model",
        label="Export tariff model (utility's payment for exported kWh)",
        explanation=("1to1_nem = most US states / 1:1 credit at retail. "
                     "ca_nem3 = California post-2023-04 (~25-30% of retail). "
                     "hi_self_consumption = Hawaii Rule 14H CSS / Smart Export."),
        where_to_find=("Confirm with utility (recent bill / interconnection "
                       "approval letter). `pvess init --address` pre-fills "
                       "this per state automatically."),
        field_type="choice",
        choices=("1to1_nem", "ca_nem3", "hi_self_consumption"),
        section="admin",
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# WIZARD_FIELDS — the union, ordered: design first (admin/equipment) then
# survey (electrical/roof/routing/climate from SITE_FIELDS). The wizard
# walks this list and prompts for every entry.
# ─────────────────────────────────────────────────────────────────────────────

# Sections render in this order:
WIZARD_SECTION_ORDER: tuple[str, ...] = (
    "admin",         # project meta, engineer, installer, client (from both)
    "equipment",     # PV / battery / inverter selection
    "electrical",    # MSP, busbar, sub-panels, critical loads (mostly survey)
    "roof",          # per-roof-face measurements
    "routing",       # wire lengths + conduit fill
    "climate",       # ambient temps, ASHRAE
)


def _ordered_fields() -> tuple[FieldSpec, ...]:
    """Concatenate DESIGN_FIELDS + SITE_FIELDS in WIZARD_SECTION_ORDER,
    preserving the within-section declaration order in each source list."""
    combined = list(DESIGN_FIELDS) + list(SITE_FIELDS)
    out: list[FieldSpec] = []
    for section in WIZARD_SECTION_ORDER:
        out.extend(f for f in combined if f.section == section)
    return tuple(out)


WIZARD_FIELDS: tuple[FieldSpec, ...] = _ordered_fields()


def is_list_field(spec: FieldSpec) -> bool:
    """True if this field is one row inside a list (e.g.
    `service.sub_panels[].name`). The wizard handles the parent list
    first (ask count, then loop)."""
    return "[]" in spec.yaml_path


def list_prefix(spec: FieldSpec) -> str:
    """For `service.sub_panels[].name` → `service.sub_panels`."""
    idx = spec.yaml_path.find("[]")
    return spec.yaml_path[:idx] if idx >= 0 else spec.yaml_path
