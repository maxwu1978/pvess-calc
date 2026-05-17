"""Single source of truth for site-survey checklist fields.

Each `FieldSpec` describes ONE blank on the printed checklist. The PDF
renderer (`builder.py`) iterates this list; the doctor check
(`site_checklist_covers_schema`) cross-references it against the
`Inputs` pydantic schema to make sure no on-site-only field is missing.

Adding a new on-site field is a one-step change: append a FieldSpec
to `SITE_FIELDS`. Doctor will verify the `yaml_path` resolves to a real
schema field and the PDF actually renders the label.

Sections render in this order on the checklist:
  1. admin      — client info, lookup data (utility, AHJ, APN, GPS)
  2. electrical — MSP + sub-panel nameplates
  3. roof       — per-roof-section measurements
  4. routing    — wire-length measurements + conduit context
  5. climate    — ambient temps, ASHRAE extremes
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class FieldSpec:
    yaml_path: str       # dotted path into inputs.yaml (e.g. "service.main_panel_a")
                         # use "list[].field" to indicate "this repeats per list element"
    label: str           # display label printed on the form
    unit: str = ""       # "A" / "V" / "ft" / "°" / "°C" etc.
    explanation: str = ""    # one-sentence "what is this?"
    where_to_find: str = ""  # one-sentence "how to obtain on-site"
    field_type: Literal["number", "integer", "text", "choice"] = "number"
    choices: tuple[str, ...] = ()
    section: Literal["admin", "electrical", "roof", "routing", "climate"] = "admin"


# ─────────────────────────────────────────────────────────────────────────────
# Section labels (rendered as the colored bar above each group)
# ─────────────────────────────────────────────────────────────────────────────

SECTION_TITLES: dict[str, str] = {
    "admin":      "1 · CLIENT & ADMIN",
    "electrical": "2 · ELECTRICAL SERVICE",
    "roof":       "3 · ROOF SECTIONS  (repeat block per face)",
    "routing":    "4 · ROUTING & WIRE LENGTHS",
    "climate":    "5 · CLIMATE & SITE ENVIRONMENT",
}


# ─────────────────────────────────────────────────────────────────────────────
# The list. SECTION ORDER (admin → electrical → roof → routing → climate) is
# what's used by builder.py; within a section the order here is the render
# order.
# ─────────────────────────────────────────────────────────────────────────────

SITE_FIELDS: tuple[FieldSpec, ...] = (
    # ── Section 1: admin / lookup ────────────────────────────────────────────
    FieldSpec(
        yaml_path="project.client_name",
        label="Client name",
        field_type="text",
        section="admin",
    ),
    FieldSpec(
        yaml_path="project.site_address",
        label="Site street address",
        field_type="text",
        section="admin",
    ),
    FieldSpec(
        yaml_path="project.coordinates",
        label="GPS coordinates",
        field_type="text",
        explanation="Format: lat, lng. Used for solar irradiance & ASHRAE lookup.",
        where_to_find="Phone GPS at the property, or geocode the address.",
        section="admin",
    ),
    FieldSpec(
        yaml_path="project.apn",
        label="APN (Assessor's Parcel Number)",
        field_type="text",
        where_to_find="Look up at county assessor's site using the address.",
        section="admin",
    ),
    FieldSpec(
        yaml_path="project.utility",
        label="Electric utility company",
        field_type="text",
        where_to_find="Recent electric bill, top of page.",
        section="admin",
    ),
    FieldSpec(
        yaml_path="project.ahj",
        label="AHJ (Authority Having Jurisdiction)",
        field_type="text",
        explanation="Local agency that issues the electrical permit (usually city or county building dept).",
        section="admin",
    ),
    # ── Section 2: electrical service ────────────────────────────────────────
    FieldSpec(
        yaml_path="service.main_panel_a",
        label="Main breaker rating",
        unit="A",
        explanation="Amp rating of the main service disconnect breaker.",
        where_to_find="MSP front: the largest 2-pole breaker at the top (usually 100/150/200/400 A).",
        section="electrical",
    ),
    FieldSpec(
        yaml_path="service.busbar_a",
        label="Busbar rating",
        unit="A",
        explanation="Internal busbar current rating — critical for NEC 705.12 (sum / 120% / supply-side tap selection).",
        where_to_find="MSP nameplate (often inside the deadfront cover) — look for 'Main Lugs' or 'Bus Rating'.",
        section="electrical",
    ),
    FieldSpec(
        yaml_path="service.busbar_source",
        label="Busbar reading source",
        field_type="choice",
        choices=("nameplate", "measured"),
        section="electrical",
    ),
    FieldSpec(
        yaml_path="service.voltage",
        label="Service voltage",
        field_type="choice",
        choices=("120/240 split-phase", "120/208 3-phase"),
        section="electrical",
    ),
    FieldSpec(
        yaml_path="service.sub_panels[].name",
        label="Sub-panel name (if any existing)",
        field_type="text",
        explanation="Identify any existing sub-panel that will be in the PV path or backed up by ESS.",
        section="electrical",
    ),
    FieldSpec(
        yaml_path="service.sub_panels[].rating_a",
        label="Sub-panel main breaker rating",
        unit="A",
        section="electrical",
    ),
    FieldSpec(
        yaml_path="service.sub_panels[].busbar_a",
        label="Sub-panel busbar rating",
        unit="A",
        section="electrical",
    ),
    FieldSpec(
        yaml_path="service.sub_panels[].location",
        label="Sub-panel physical location",
        field_type="text",
        section="electrical",
    ),
    FieldSpec(
        yaml_path="service.sub_panels[].distance_to_msp_ft",
        label="Distance from this sub-panel to MSP",
        unit="ft",
        explanation=("Wire-run length back to the main service panel. "
                     "Used for per-segment NEC 215.2 voltage-drop. "
                     "0 = unknown → engine uses global default."),
        where_to_find=("Measure along the actual conduit path (attic / "
                       "exterior wall), not straight-line distance."),
        section="electrical",
    ),
    # ── K.2.5 additions: existing PV/ESS + slot feasibility ───────────────
    FieldSpec(
        yaml_path="service.sub_panels[].existing_solar_breaker_a",
        label="Existing solar/ESS backfeed breaker on this sub-panel",
        unit="A",
        explanation=("Sum of any PV/ESS backfeed breakers ALREADY installed "
                     "in this sub-panel. NEC 705.12 sums these with the "
                     "new system when applying the busbar rules. 0 if none."),
        where_to_find="Look at the front of the sub-panel; PV/ESS breakers are usually labelled 'SOLAR' or 'PV'.",
        section="electrical",
    ),
    FieldSpec(
        yaml_path="service.sub_panels[].available_slots",
        label="Sub-panel total breaker slots (capacity)",
        explanation=("Maximum single-pole positions on the panel's nameplate "
                     "(common values: 16, 20, 24, 30, 40, 42)."),
        where_to_find="Panel nameplate, typically shows 'X spaces' or 'X-circuit'.",
        field_type="integer",
        section="electrical",
    ),
    FieldSpec(
        yaml_path="service.sub_panels[].used_slots",
        label="Sub-panel breaker slots currently used",
        explanation="Count occupied positions. Used to check we can fit the new PV/ESS breaker.",
        field_type="integer",
        section="electrical",
    ),
    FieldSpec(
        yaml_path="service.sub_panels[].service_rated",
        label="Is this sub-panel service-rated?",
        explanation=("Service-rated panels can serve as the service disconnect "
                     "(NEC 230.71). Most residential sub-panels are NOT."),
        field_type="choice",
        choices=("no", "yes"),
        section="electrical",
    ),
    # ── MSP-level existing solar + slot capacity ──────────────────────────
    FieldSpec(
        yaml_path="service.existing_solar_breaker_a_msp",
        label="Existing solar/ESS backfeed breaker ALREADY on MSP",
        unit="A",
        explanation=("Total of any PV/ESS backfeed breakers currently on the "
                     "MAIN service panel itself (NOT a sub-panel). NEC 705.12 "
                     "adds this to the new system in the bus-load sum. "
                     "0 for greenfield (no existing solar)."),
        where_to_find="MSP front: look for breakers labelled 'SOLAR', 'PV', or 'ESS'.",
        section="electrical",
    ),
    FieldSpec(
        yaml_path="service.msp_available_slots",
        label="MSP total breaker slots (capacity)",
        explanation="Maximum single-pole positions on the MSP nameplate.",
        where_to_find="MSP nameplate, e.g. '42-circuit', '40 spaces'.",
        field_type="integer",
        section="electrical",
    ),
    FieldSpec(
        yaml_path="service.msp_used_slots",
        label="MSP breaker slots currently used",
        explanation="Count occupied positions. Determines whether new PV/ESS breakers fit without a panel swap.",
        field_type="integer",
        section="electrical",
    ),
    FieldSpec(
        yaml_path="loads.critical_subpanel_a",
        label="Critical-loads sub-panel rating (if backup desired)",
        unit="A",
        explanation="Empty if not branching critical loads to a separate backup panel.",
        section="electrical",
    ),
    # ── K.5 additions: existing grounding electrode system ───────────────
    FieldSpec(
        yaml_path="service.grounding_electrode_system.gec_main_size_awg",
        label="Existing main GEC size (AWG)",
        explanation=("Grounding electrode conductor from MSP to ground rod / "
                     "water pipe / Ufer. NEC 250.66 requires #4 AWG Cu for "
                     "200 A service, #6 for 100 A. Engine compares actual "
                     "vs required and flags UNDERSIZED in EE-2."),
        where_to_find=("MSP front: green/bare-copper conductor leaving "
                       "the bottom of the panel to the GES."),
        field_type="text",
        section="electrical",
    ),
    FieldSpec(
        yaml_path="service.grounding_electrode_system.bonded_to_neutral_at_service",
        label="MSP main bonding jumper present (NEC 250.24)?",
        explanation=("Neutral-to-ground bond at the service entrance. "
                     "Required at exactly one point (typically the MSP). "
                     "Older homes occasionally missing this bond → "
                     "compliance gap."),
        field_type="choice",
        choices=("yes", "no", "unknown"),
        section="electrical",
    ),
    FieldSpec(
        yaml_path="service.grounding_electrode_system.existing_grounding_summary",
        label="Grounding electrode system inventory",
        explanation=("Free-text record of GES components present on site: "
                     "ground rods (count, length, location), metal water "
                     "pipe (confirmed metal underground? PEX-replaced?), "
                     "Ufer (concrete-encased rebar). Engineer translates "
                     "to yaml `rods[]` / `metal_water_pipe` / `ufer`."),
        where_to_find=("Walk around MSP exterior + crawlspace / basement. "
                       "Verify metal water service hasn't been replaced "
                       "with PEX (which disqualifies the water pipe as "
                       "an electrode per NEC 250.52(A)(1))."),
        field_type="text",
        section="electrical",
    ),
    # ── Section 3: roof sections ─────────────────────────────────────────────
    FieldSpec(
        yaml_path="site.roof_sections[].name",
        label="Roof face name (e.g. 'South Roof')",
        field_type="text",
        section="roof",
    ),
    FieldSpec(
        yaml_path="site.roof_sections[].roof_type",
        label="Roof material",
        field_type="choice",
        choices=("Comp Shingle", "Tile", "Metal", "Flat (TPO/EPDM)"),
        section="roof",
    ),
    FieldSpec(
        yaml_path="site.roof_sections[].pitch_deg",
        label="Roof pitch",
        unit="°",
        explanation="Angle from horizontal. 22° is typical residential.",
        where_to_find="Pitch meter, smartphone level app, or satellite imagery.",
        section="roof",
    ),
    FieldSpec(
        yaml_path="site.roof_sections[].azimuth_deg",
        label="Roof azimuth",
        unit="° (180 = due south)",
        explanation="Compass direction the roof faces; 0=N, 90=E, 180=S, 270=W.",
        where_to_find="Compass app standing on the roof, or satellite imagery.",
        section="roof",
    ),
    FieldSpec(
        yaml_path="site.roof_sections[].width_ft",
        label="Roof face width",
        unit="ft",
        section="roof",
    ),
    # ── K.2.6c additions: shape + setbacks + free-text obstruction note ──
    FieldSpec(
        yaml_path="site.roof_sections[].shape",
        label="Roof face shape",
        explanation=("rect = standard gable / shed face (width × height). "
                     "tri = hip-roof triangular face (base × slant-height)."),
        field_type="choice",
        choices=("rect", "tri"),
        section="roof",
    ),
    FieldSpec(
        yaml_path="site.roof_sections[].apex_x_ratio",
        label="Triangle apex position (0 = left, 0.5 = centered, 1 = right)",
        explanation=("Only for shape=tri. Locates the apex along the base. "
                     "0.5 = isosceles (most hip roofs)."),
        section="roof",
    ),
    FieldSpec(
        yaml_path="site.roof_sections[].default_setback_ft",
        label="Default edge setback (NEC 690.12 fire access)",
        unit="ft",
        explanation=("Minimum array setback from eaves / ridges / hips. "
                     "NEC 690.12 default 1.5 ft (18\"); some AHJs require 3 ft."),
        where_to_find="AHJ-specific. CA Title 24 typically 3 ft; rest of US 1.5 ft.",
        section="roof",
    ),
    # Obstructions are list-of-list which the wizard doesn't yet support
    # (K.2.6c-Full deferred that). Free-text capture so site surveyors
    # can write them on paper; engineer hand-edits inputs.yaml after.
    FieldSpec(
        yaml_path="site.roof_sections[].obstructions_note",
        label="Obstructions (chimneys / skylights / vent pipes / HVAC)",
        field_type="text",
        explanation=("Record each obstruction's approximate position from "
                     "eave-left corner + size. Engineer translates to "
                     "yaml `obstructions[]` after the survey."),
        where_to_find=("Walk the roof or examine satellite imagery. "
                       "Note position (x_ft, y_ft) + width × height."),
        section="roof",
    ),
    FieldSpec(
        yaml_path="site.roof_sections[].height_ft",
        label="Roof face height (rake-to-rake)",
        unit="ft",
        section="roof",
    ),
    # ── Section 4: routing & wire lengths ────────────────────────────────────
    FieldSpec(
        yaml_path="wire_lengths.pv_string_one_way_ft",
        label="PV string → combiner — one-way length",
        unit="ft",
        explanation="From farthest PV module to the combiner box.",
        section="routing",
    ),
    FieldSpec(
        yaml_path="wire_lengths.combiner_to_inverter_ft",
        label="Combiner → inverter",
        unit="ft",
        section="routing",
    ),
    FieldSpec(
        yaml_path="wire_lengths.inverter_to_ac_disc_ft",
        label="Inverter → AC disconnect",
        unit="ft",
        section="routing",
    ),
    FieldSpec(
        yaml_path="wire_lengths.ac_disc_to_msp_ft",
        label="AC disconnect → MSP",
        unit="ft",
        section="routing",
    ),
    FieldSpec(
        yaml_path="wire_lengths.ess_to_inverter_ft",
        label="ESS → inverter battery port",
        unit="ft",
        section="routing",
    ),
    FieldSpec(
        yaml_path="routing.pv_conduit_fill_count",
        label="PV current-carrying conductors per shared conduit",
        explanation="Counts toward NEC 310.15(B)(3)(a) fill-derating. 3 or fewer = no derate.",
        field_type="integer",
        section="routing",
    ),
    FieldSpec(
        yaml_path="routing.ac_conduit_fill_count",
        label="AC current-carrying conductors per shared conduit",
        field_type="integer",
        section="routing",
    ),
    # ── Section 5: climate ───────────────────────────────────────────────────
    FieldSpec(
        yaml_path="pv_array.ashrae_2pct_min_c",
        label="ASHRAE 2 % extreme min temperature",
        unit="°C",
        explanation="Per-city 'lowest 2-percentile' winter design temp — drives NEC 690.7(A) Voc cold correction.",
        where_to_find="ASHRAE Handbook of Fundamentals (Chapter 14) or NREL design-condition tables.",
        section="climate",
    ),
    FieldSpec(
        yaml_path="pv_array.temp_min_c",
        label="Recorded historical min temperature",
        unit="°C",
        explanation="Used as the 690.7(A) fallback if ASHRAE 2% value is unknown.",
        section="climate",
    ),
    FieldSpec(
        yaml_path="pv_array.temp_max_c",
        label="Module operating max temperature",
        unit="°C",
        explanation="Typically 50 °C for residential roof-mount; affects Voc/Isc working-point estimates.",
        section="climate",
    ),
    FieldSpec(
        yaml_path="routing.ambient_temp_c",
        label="Attic / conduit summer max ambient",
        unit="°C",
        explanation="Hottest air inside the conduit run. Phoenix attics commonly hit 45–50 °C.",
        where_to_find="Thermometer in the attic on a hot afternoon, or ASHRAE 2 % max design temp for the city.",
        section="climate",
    ),
)


def fields_for_section(section: str) -> list[FieldSpec]:
    """All fields belonging to one section, in declared order."""
    return [f for f in SITE_FIELDS if f.section == section]


def all_yaml_paths() -> list[str]:
    """Flat list of every yaml_path declared in SITE_FIELDS."""
    return [f.yaml_path for f in SITE_FIELDS]
