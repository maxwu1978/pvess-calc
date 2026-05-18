"""Pydantic models for inputs.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field, model_validator


class InstallerCostOverrides(BaseModel):
    """K.4.6.3 — real installer BOM costs replacing the NREL Q1-2026
    benchmark (PV $3.50/W bundling everything + ESS $950/kWh
    incremental). Opt-in: when this block is absent the economics
    engine falls back to the benchmark unchanged (zero regression for
    pre-K.4.6 yamls).

    When present, the cost stack becomes:

        pv_turnkey_usd_per_w × system_kW × 1000   (modules + racking
                                                   + labor + permit
                                                   + soft costs)
      + inverter_cost                             (see precedence below)
      + battery_cost                              (see precedence below)

    Per-component price precedence (most → least specific):
      1. `inverter_cost_usd_total` / `battery_cost_usd_total` — explicit
         override, wins everything. Use for one-off custom equipment.
      2. `inverter_ref` / `battery_ref` — look up wholesale price from
         `devices.INVERTER_PRICES_USD` / `BATTERY_PRICES_USD`, multiply
         by the corresponding quantity from `inverter.quantity` /
         `battery.quantity`.
      3. (nothing set) — component cost = 0. The pv_turnkey rate is
         expected to already include it.

    For the DFW installer's actual stack:
      pv_turnkey_usd_per_w: 2.40           # excludes inverter & battery
      inverter_ref: "megarevo_r11klna"     # $2,000 wholesale × qty
      battery_ref: "inhouse_16kwh_hv"      # $6,000 × qty (omit for PV-only)
    """
    pv_turnkey_usd_per_w: float            # required when block present
    inverter_ref: Optional[str] = None     # devices.INVERTERS key
    battery_ref: Optional[str] = None      # devices.BATTERIES key
    inverter_cost_usd_total: Optional[float] = None
    battery_cost_usd_total: Optional[float] = None

    @model_validator(mode="after")
    def _check_pv_turnkey_in_range(self) -> "InstallerCostOverrides":
        if self.pv_turnkey_usd_per_w <= 0:
            raise ValueError(
                f"pv_turnkey_usd_per_w must be > 0; got "
                f"{self.pv_turnkey_usd_per_w}"
            )
        if self.pv_turnkey_usd_per_w > 10.0:
            raise ValueError(
                f"pv_turnkey_usd_per_w {self.pv_turnkey_usd_per_w} > $10/W "
                "looks like a unit error (dollars vs cents). Typical "
                "installer range: $1.50-$4.50/W."
            )
        return self


class RoofInfo(BaseModel):
    """K.12.1 — building / roof attributes that show up on the cover
    sheet's `ROOF` block. None of these affect NEC calculation; they're
    pure AHJ-submittal context. All fields optional with sensible
    defaults so every pre-K.12 yaml continues to validate."""
    stories: int = 1                       # e.g. 1 / 2 / 3
    type: str = ""                         # "Comp Shingle", "Tile", ...
    height_ft: float = 0.0                 # roof apex height above grade
    construction: str = ""                 # "Prefabricated trusses", ...
    condition: Literal["good", "fair", "poor", "unknown"] = "unknown"
    being_replaced: bool = False           # tear-off + re-roof before PV?
    flashing: str = ""                     # IronRidge FlashFoot 2, ...
    framing: str = ""                      # "2x4 @ 24 in O.C. trusses"
    attic_access: Literal["accessible", "inaccessible", "unknown"] = "unknown"
    decking_thickness_in: float = 0.0
    roof_layers: int = 0                   # 0 = unknown


class SitePhoto(BaseModel):
    """9.13 — one site-survey photo for the PV-7 sheet.

    `path` is project-relative or absolute. Missing paths are allowed so
    intake can declare required shots before the installer uploads them; the
    renderer emits a clearly labeled placeholder instead of failing.
    """
    kind: Literal[
        "front_elevation", "roof", "meter", "main_panel", "sub_panel",
        "attic", "equipment_location", "other",
    ] = "other"
    path: str = ""
    caption: str = ""


class SpecSheetRef(BaseModel):
    """9.14 — manufacturer cut/spec sheet reference.

    `path` is project-relative or absolute. `equipment` should be a stable
    human key such as `module`, `inverter`, `optimizer`, `racking`.
    """
    equipment: str
    path: str = ""
    pages: list[int] = Field(default_factory=list)  # 1-based page subset; empty = all


class BuildingCodes(BaseModel):
    """K.12.1 — non-NEC governing codes that AHJ profiles surface on the
    cover sheet's `GOVERNING CODES` block. NEC version stays on
    `ProjectMeta.nec_edition`; the rest (IBC / IRC / IFC / IECC / etc.)
    live here. Defaults to 2021 IBC/IRC/IFC/etc. — the dominant
    residential cycle in the US as of 2026."""
    ibc: str = "2021 IBC"                  # International Building Code
    irc: str = "2021 IRC"                  # International Residential Code
    ifc: str = "2021 IFC"                  # International Fire Code
    ifgc: str = "2021 IFGC"                # International Fuel Gas Code
    iebc: str = "2021 IEBC"                # International Existing Bldg Code
    iecc: str = "2021 IECC"                # Int'l Energy Conservation Code
    imc: str = "2021 IMC"                  # International Mechanical Code
    ipc: str = "2021 IPC"                  # International Plumbing Code


class DesignCriteria(BaseModel):
    """K.12.1 — ASCE / wind / snow load context. Standard cover-sheet
    block at every Wyssling-style permit. Default values are TX-DFW
    typical (115 mph wind, 5 psf snow). AHJ profile can override per
    region (CA: 110 mph + earthquake; CO: 30 psf snow; FL: 175 mph)."""
    wind_speed_mph: int = 115              # 3-sec gust, ASCE 7
    ground_snow_load_psf: int = 5
    asce_version: str = "7-16"
    exposure_category: Literal["B", "C", "D"] = "C"
    occupancy: str = "R-3"                 # IBC table 1604.5
    construction_type: str = "Type V-B"    # IBC 602
    sprinklers: bool = False


class MeterInfo(BaseModel):
    """K.12.1 — utility meter identifying info. ESID is Texas-specific
    (Oncor unique service identifier); other markets leave blank."""
    number: str = ""                       # utility meter serial #
    location: str = ""                     # "1st floor garage", ...
    esid: str = ""                         # Oncor/ERCOT-specific


class RevisionEntry(BaseModel):
    """K.12.1 — one row of the cover sheet's revision history table.
    The current revision letter stays on `ProjectMeta.revision`; this
    list is the full history."""
    date: str                              # ISO 8601 preferred
    revision: str                          # "A", "B", "C", ...
    comment: str = ""


class ProjectMeta(BaseModel):
    id: str
    name: str
    location: str
    ahj: str
    nec_edition: Literal["2023", "2020", "2017"] = "2023"

    # Optional permit-drawing metadata (Phase B). Defaults keep older
    # inputs.yaml files valid; the renderer falls back gracefully when blank.
    client_name: str = ""
    site_address: str = ""
    coordinates: str = ""        # "33.035, -96.902"
    apn: str = ""                # assessor's parcel number
    utility: str = ""            # utility company short name
    drawn_by: str = ""
    revision: str = "A"
    initial_design_date: str = ""
    permit_profile: Literal[
        "internal", "tx_residential_pv", "wyssling_like",
    ] = "internal"
    structural_letter_pdf: str = ""          # signed PDF to prepend if supplied
    site_photos: list[SitePhoto] = Field(default_factory=list)
    spec_sheets: list[SpecSheetRef] = Field(default_factory=list)

    # K.4.6.3: installer BOM cost overrides (opt-in; benchmark fallback)
    installer_cost_overrides: Optional[InstallerCostOverrides] = None

    # K.12.1: cover-sheet metadata blocks. Every field optional; renderer
    # shows "—" or skips the block when defaults are in play (zero
    # regression for every pre-K.12 yaml).
    roof_info: RoofInfo = Field(default_factory=RoofInfo)
    building_codes: BuildingCodes = Field(default_factory=BuildingCodes)
    design_criteria: DesignCriteria = Field(default_factory=DesignCriteria)
    meter_info: MeterInfo = Field(default_factory=MeterInfo)
    revision_history: list[RevisionEntry] = Field(default_factory=list)


class DesignEngineer(BaseModel):
    """Design engineer / firm of record (appears in DXF title block)."""
    firm: str = ""
    address: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    firm_number: str = ""


class Installer(BaseModel):
    """Solar/electrical company installing the system."""
    company: str = ""
    address: str = ""


class InternalBreaker(BaseModel):
    """A single breaker position inside a panel (shown as a small horizontal
    bar in the SLD)."""
    rating_a: int
    poles: int = 2
    label: str = ""               # e.g. "INV-1 backfeed" or "MAIN"
    kind: Literal["main", "backfeed", "feeder", "branch"] = "branch"


class SubPanel(BaseModel):
    """An AC sub-panel — either in the PV path (aggregation) or branched off
    the MSP as a critical-loads / backup panel.

    `role` determines how the SLD renders the panel:
      - `pv_aggregation` — drawn in series in the AC chain
        (AC-DISC → Sub #N → ... → MSP). Used for the panel where the
        inverter backfeed breakers land before consolidating into the MSP.
      - `critical_loads` — drawn as a separate branch *below* the MSP, fed
        from MSP (or from an ESS backup port). Out of the PV→grid path.

    `breakers` is an optional list of internal breakers. If empty, the
    renderer auto-derives a sensible default from the panel's role + the
    project's inverter count.

    **Phase K.2.5 additions** (all default-zero / False; old yaml stays valid):
      - `service_rated` — Does this panel act as the service disconnect
        (NEC 230.71)? Service-rated sub-panels limit how many other
        disconnects can be present and influence supply_side_tap routing.
      - `available_slots` / `used_slots` — Physical breaker positions in
        the panel. `available_slots == 0` is treated as "unknown" by the
        feasibility check. When known, the doctor flags projects whose
        new PV+ESS breakers don't fit (panel swap required).
      - `existing_solar_breaker_a` — Sum of any backfed PV/ESS breakers
        ALREADY installed on this bus. The 705.12 evaluator adds this
        to the new system's backfeed when applying sum / 120% rules
        (NEC 2023 705.12(B)(3) bus-load principle).
      - `enclosure_rating` — "NEMA 1" (indoor) / "NEMA 3R" (outdoor).
        Affects breaker selection and conduit transition.
    """
    name: str                    # e.g. "Sub Panel #2"
    rating_a: float
    busbar_a: float
    location: str = ""
    backfeed_breaker_a: float = 0  # backfed OCPD upstream of this panel
    role: Literal["pv_aggregation", "critical_loads"] = "pv_aggregation"
    breakers: list[InternalBreaker] = Field(default_factory=list)

    # K.2.5: physical / electrical feasibility fields
    service_rated: bool = False
    available_slots: int = 0      # 0 means "unknown" — slots check skipped
    used_slots: int = 0
    existing_solar_breaker_a: float = 0.0  # already-installed PV/ESS backfeed
    enclosure_rating: Literal["NEMA 1", "NEMA 3R", "unknown"] = "unknown"

    # K.2.6a: physical distance from this sub-panel to the MSP. Needed
    # for per-segment voltage-drop math when 2+ sub-panels are chained
    # (the global `wire_lengths.ac_disc_to_msp_ft` is the FINAL hop;
    # this is the per-panel intermediate). 0.0 = unknown → engine
    # falls back to the global default.
    distance_to_msp_ft: float = 0.0

    @property
    def free_slots(self) -> Optional[int]:
        """Open breaker slots, or None if total is unknown."""
        if self.available_slots <= 0:
            return None
        return max(0, self.available_slots - self.used_slots)


class GroundRod(BaseModel):
    """K.5 — one ground rod electrode (NEC 250.52(A)(5)).

    NEC requires 8 ft minimum length, 5/8" minimum diameter for
    copper-clad steel rods (5/8" or 3/4" common). The driven rod is
    the most common single electrode but NEC 250.50 requires 2 rods
    spaced ≥6 ft apart when no other qualifying electrode exists.
    """
    length_ft: float = 8.0                    # NEC 250.52(A)(5) min 8 ft
    material: Literal[
        "copper_clad_steel", "stainless_steel", "galvanized",
    ] = "copper_clad_steel"
    diameter_in: float = 0.625                # 5/8" most common
    location: str = ""                        # e.g. "SE corner of garage"


class MetalWaterPipeBond(BaseModel):
    """K.5 — metal-underground-water-pipe electrode (NEC 250.52(A)(1)).

    A bonded metal water pipe in direct contact with the earth for 10 ft
    or more qualifies as an electrode. PEX or plastic-supplied lines
    do NOT qualify even if there's a metal segment inside the house.
    """
    bond_size_awg: str = "6"                  # most common GEC to water pipe
    underground_length_ft: float = 10.0       # NEC 250.52(A)(1) min 10 ft
    location: str = ""                        # e.g. "where service enters basement"
    confirmed_metal_underground: bool = True  # PEX-replaced services should be False


class UferElectrode(BaseModel):
    """K.5 — concrete-encased electrode (NEC 250.52(A)(3)).

    A 20 ft (≥1/2" rebar) or 20 ft (≥4 AWG bare copper) embedded in
    concrete in direct contact with the earth. Standard on new houses
    built post-2008 (NEC 250.50 reference) but rare to retrofit since
    the foundation has to be poured around the conductor.
    """
    length_ft: float = 20.0                   # NEC 250.52(A)(3) min 20 ft
    conductor: Literal["rebar", "copper"] = "rebar"
    conductor_size: str = "1/2 in rebar"      # e.g. "1/2 in rebar" or "4 AWG copper"
    location: str = ""                        # e.g. "south foundation footing"


class GroundingElectrodeSystem(BaseModel):
    """K.5 — site's actual grounding electrode system (GES).

    Replaces the pre-K.5 'assume the standard 3-electrode combo' model.
    Engine + EE-2 sheet now render only what's actually installed.

    NEC 250.50 requires either:
      * A single rod/pipe/plate if NO other qualifying electrode exists
        AND the rod alone has resistance ≤25 Ω (NEC 250.53(A)(2)), OR
      * Two electrodes if no resistance test (most common path), OR
      * Any combination of the NEC 250.52(A) electrode types when they
        are present at the building.

    `gec_main_size_awg` is the EXISTING grounding-electrode conductor
    from MSP to the electrode system. The engine compares this against
    the NEC 250.66 required size (function of service ampacity) and
    flags UNDERSIZED in EE-2 if the existing GEC is below code.

    `bonded_to_neutral_at_service = False` is common in older homes —
    a real but invisible compliance issue. Doctor surfaces it.

    `pv_separate_ground = True` means the PV DC system has its own
    ground rod (NEC 690.47(B), now discouraged in NEC 2017+; bonded
    EGC back to MSP is preferred). Recording this lets the engine
    flag legacy separate-ground installs.
    """
    rods: list[GroundRod] = Field(default_factory=list)
    metal_water_pipe: Optional[MetalWaterPipeBond] = None
    ufer: Optional[UferElectrode] = None
    gec_main_size_awg: str = ""               # existing main GEC; "" = unknown
    # NEC 250.24 main bonding jumper status. `unknown` preserves the
    # data-missing case from a yes/no bool — the grounding compliance
    # check treats `unknown` as WARN (not silent PASS / FAIL).
    bonded_to_neutral_at_service: Literal[
        "yes", "no", "unknown"
    ] = "unknown"
    pv_separate_ground: bool = False
    # Free-text capture for surveyors (mirrors K.2.6c obstructions_note).
    # Engineer translates this to structured rods/water_pipe/ufer
    # during hand-yaml edit. Doesn't drive any calculation.
    existing_grounding_summary: str = ""

    @property
    def electrode_count(self) -> int:
        """Total qualifying electrodes per NEC 250.50."""
        n = len(self.rods)
        if self.metal_water_pipe and self.metal_water_pipe.confirmed_metal_underground:
            n += 1
        if self.ufer:
            n += 1
        return n


class WireLengths(BaseModel):
    """One-way wire lengths (ft) for each conductor run.

    Used for NEC 215.2 / 210.19 voltage-drop validation. Any field left at 0
    falls back to the calc engine's conservative default (50 ft each).
    """
    pv_string_one_way_ft: float = 0.0       # PV module → first combiner
    pv_to_combiner_ft: float = 0.0          # alias / total PV source run
    combiner_to_inverter_ft: float = 0.0    # combiner → inverter DC input
    inverter_to_ac_disc_ft: float = 0.0     # each inverter → AC trunk → AC disc
    ac_disc_to_msp_ft: float = 0.0          # AC disc → MSP (through sub-panels)
    ess_to_inverter_ft: float = 0.0         # ESS DC → inverter battery port

    @property
    def has_data(self) -> bool:
        return any(getattr(self, f) > 0 for f in type(self).model_fields)


class UtilityTransformer(BaseModel):
    """Service-feeding transformer parameters for NEC 110.24 fault current."""
    kva: float = 25.0                       # residential default
    impedance_pct: float = 2.0              # typical pole-mount
    secondary_voltage: float = 240.0        # split-phase residence


class Routing(BaseModel):
    """Conduit routing context for NEC 310.15(B) derating."""
    ambient_temp_c: float = 30.0            # default ambient (NEC 310.15(B)(2)(a) base)
    pv_conduit_fill_count: int = 3          # current-carrying conductors in PV conduit
    ac_conduit_fill_count: int = 3          # current-carrying conductors in AC conduit


class Optimizer(BaseModel):
    """Module-level power electronics (MLPE) — per-module or per-string DC
    optimizer.  Common in residential to satisfy NEC 690.12 rapid shutdown.

    `count` = "per_module" auto-sizes to pv_array.modules; an explicit integer
    overrides. `type` distinguishes pass-through (no MPPT) from full MPPT
    optimizers — affects whether per-string Voc math holds.
    """
    brand: str = ""
    model: str = ""
    type: Literal["pass_through", "mppt"] = "pass_through"
    count: Literal["per_module", "per_string"] | int = "per_module"
    max_input_v: float = 80.0
    max_output_a: float = 15.0

    def effective_count(self, n_modules: int, n_strings: int) -> int:
        if isinstance(self.count, int):
            return self.count
        if self.count == "per_module":
            return n_modules
        return n_strings


class RoofObstruction(BaseModel):
    """K.2.6c — a single roof obstruction the PV array must NOT cover.

    `x_ft` / `y_ft` are offsets from the section's bottom-left corner
    (looking at the section in elevation: x = left→right along the
    eave, y = bottom→top toward the ridge / apex). For triangular
    sections the same local coords apply with origin at the eave-left
    vertex.

    `setback_ft` is the minimum clear-space around the obstruction
    that the PV array must respect (NEC 690.12 fire access default
    18" = 1.5 ft; AHJs sometimes require 3 ft).
    """
    kind: Literal[
        "chimney", "skylight", "vent_pipe", "hvac_unit",
        "fan_vent", "access_hatch", "satellite_dish", "other",
    ]
    x_ft: float
    y_ft: float
    width_ft: float
    height_ft: float
    setback_ft: float = 1.5
    note: str = ""


class EdgeSetback(BaseModel):
    """K.2.6c — minimum array setback from one named edge of the roof
    face. NEC 690.12 + IRC fire-access defaults are 18" (1.5 ft) on
    eaves / ridges / valleys / hips; CA Title 24 requires 36" (3 ft)
    on some accessible-pathway edges — set per-AHJ in `edge_setbacks`.

    `edge_type` is the topological role of the edge, NOT its compass
    direction — that's because a single 'eave' setback applies to the
    bottom edge regardless of whether the roof faces N or S.

    Valid types:
      * `eave`   — bottom edge (horizontal at the gutter line)
      * `ridge`  — top edge (where two opposing faces meet)
      * `rake`   — sloped side edges of a gable face
      * `valley` — concave interior junction between two faces
      * `hip`    — convex exterior junction between two faces
                   (hip roofs only)
      * `apex`   — point at the top of a triangular hip face
    """
    edge_type: Literal["eave", "ridge", "rake", "valley", "hip", "apex"]
    setback_ft: float = 1.5


class RoofSection(BaseModel):
    """One contiguous roof area (per Wyssling-style PV-2/PV-4 roof table).
    Multiple sections allowed for hip / gable / complex roofs.

    **K.2.6c shape polymorphism.** `shape='rect'` is a standard gable
    or shed face (width × height). `shape='tri'` is a triangular hip-
    roof face — `width_ft` is the base (along the eave) and
    `height_ft` is the slant-height to the apex; `apex_x_ratio`
    locates the apex along the base (0 = left, 0.5 = centred /
    isosceles, 1 = right).

    K.2.6c additions are all-optional: a yaml with no `shape` /
    `obstructions` / `edge_setbacks` behaves exactly as Phase J
    (rectangular gable, no obstructions modelled, default 18" setback
    everywhere).
    """
    name: str = "Roof A"
    roof_type: str = "Comp Shingle"
    pitch_deg: float = 22.0
    azimuth_deg: float = 180.0
    module_count: int = 0                   # how many modules sit on this face
    width_ft: float = 24.0                  # rect: width / tri: base length
    height_ft: float = 16.0                 # rect: height / tri: slant-height
    attachment_count: int = 0               # # of roof attachments on this face

    # K.8: per-face production derate. 1.0 = no shading; 0.85 = typical
    # urban site w/ neighboring tree at 30° elevation; 0.7 = heavily
    # shaded face (only morning sun). Set per site survey. Site-level
    # default flows from `Site.urban_density` if this stays at 1.0.
    shading_factor: float = 1.0

    # K.2.6c: shape + obstructions + per-edge setbacks
    # K.2.7: `polygon` shape — arbitrary N-gon described by `vertices`.
    # Width/height still required (used by site_checklist + PV-4 bbox
    # fallback) but the polygon's vertices override them for area /
    # inset / point-in-polygon math.
    shape: Literal["rect", "tri", "polygon"] = "rect"
    apex_x_ratio: float = 0.5               # tri only; 0..1 along base
    # K.2.7: polygon vertices in local face coordinates (ft). Origin at
    # eave-left; +x along eave, +y toward ridge / apex. Order MUST be
    # counter-clockwise (so signed area > 0). Polygon must be SIMPLE
    # (edges don't self-intersect) — validator enforces both invariants.
    # Length 0 (default) is only valid for shape='rect' or 'tri'.
    vertices: list[tuple[float, float]] = Field(default_factory=list)
    obstructions: list[RoofObstruction] = Field(default_factory=list)
    edge_setbacks: list[EdgeSetback] = Field(default_factory=list)
    default_setback_ft: float = 1.5         # NEC 690.12 fire access default
    # Free-text capture for site surveyors — engineer translates this
    # to the structured `obstructions[]` list during hand-yaml edit.
    # Doesn't drive any calculation; preserved for archive only.
    obstructions_note: str = ""

    # K.11 — site-plan placement of this face. Eave-left corner is the
    # roof-local origin (0, 0); `site_anchor_x_ft` / `_y_ft` give its
    # position on the EE-4 site plan (origin = front-left of lot).
    # `site_anchor_azimuth_deg` is the compass direction of the +x axis
    # (the eave direction); 0 = east, 90 = north, 180 = west, 270 = south.
    # When `azimuth_deg` differs from `array_azimuth_deg` we keep the
    # ROOF azimuth and rotate the site footprint accordingly.
    # Defaults all 0/None → K.11 wire routing falls back to the manual
    # `wire_lengths` block, so this is fully additive.
    site_anchor_x_ft: Optional[float] = None
    site_anchor_y_ft: Optional[float] = None
    site_anchor_azimuth_deg: float = 0.0

    # K.11 — where the string-trunk conduit penetrates this face (in
    # roof-local ft, same origin as `vertices` / module placements).
    # Defaults to the ridge midpoint when None (the typical install).
    roof_penetration_x_ft: Optional[float] = None
    roof_penetration_y_ft: Optional[float] = None

    @model_validator(mode="after")
    def _check_shape_constraints(self) -> "RoofSection":
        if self.shape == "tri" and not (0.0 <= self.apex_x_ratio <= 1.0):
            raise ValueError(
                f"apex_x_ratio must be in [0,1]; got {self.apex_x_ratio}"
            )
        if self.shape == "polygon":
            if len(self.vertices) < 3:
                raise ValueError(
                    f"polygon roof section needs ≥3 vertices; "
                    f"got {len(self.vertices)}"
                )
            # Self-intersect check FIRST — a bow-tie polygon often has
            # signed area = 0 which would also trigger the CCW error;
            # the self-intersect message is more useful for fixing the
            # underlying problem.
            if _polygon_self_intersects(self.vertices):
                raise ValueError(
                    "polygon vertices form a self-intersecting outline; "
                    "K.2.7 requires simple (non-self-intersecting) polygons"
                )
            # CCW check via signed area (shoelace)
            signed_area = _signed_polygon_area(self.vertices)
            if signed_area <= 0:
                raise ValueError(
                    "polygon vertices must be counter-clockwise "
                    "(signed area ≤ 0 detected); reverse the order"
                )
        return self

    @property
    def gross_area_sqft(self) -> float:
        """Gross face area (ft²) ignoring setbacks and obstructions.

        * rect: width × height
        * tri: ½ × base × height
        * polygon: shoelace formula on `vertices` (CCW → positive)
        """
        if self.shape == "tri":
            return 0.5 * self.width_ft * self.height_ft
        if self.shape == "polygon":
            return _signed_polygon_area(self.vertices)
        return self.width_ft * self.height_ft

    def edge_setback_for(self, edge_type: str) -> float:
        """Return the configured setback for an edge type, falling back
        to `default_setback_ft` when no override is present."""
        for es in self.edge_setbacks:
            if es.edge_type == edge_type:
                return es.setback_ft
        return self.default_setback_ft


# ─── Polygon helpers (used by the validator + K.2.7 calc/polygon.py) ────


def _signed_polygon_area(vertices: list[tuple[float, float]]) -> float:
    """Shoelace formula. Positive when vertices wind counter-clockwise.

    The validator uses this both for area > 0 (rules out degenerate /
    collinear polygons) AND for the CCW orientation check. The roof-
    layout engine reads the same value via `RoofSection.gross_area_sqft`.
    """
    n = len(vertices)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x0, y0 = vertices[i]
        x1, y1 = vertices[(i + 1) % n]
        s += (x0 * y1) - (x1 * y0)
    return s / 2.0


def _polygon_self_intersects(vertices: list[tuple[float, float]]) -> bool:
    """O(n²) test for self-intersection — checks every non-adjacent
    edge pair. Residential roof polygons are 3-12 vertices; the
    quadratic cost is negligible. Adjacent edges share an endpoint by
    definition and don't count as intersection."""
    n = len(vertices)
    if n < 4:
        return False    # 3-vertex (triangle) can't self-intersect
    for i in range(n):
        a1 = vertices[i]
        a2 = vertices[(i + 1) % n]
        # Compare against every edge except `i` itself and the two
        # adjacent edges (which share a vertex with `i`).
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            b1 = vertices[j]
            b2 = vertices[(j + 1) % n]
            if _segments_cross(a1, a2, b1, b2):
                return True
    return False


def _segments_cross(p1, p2, p3, p4) -> bool:
    """Standard segment-segment intersection test using orientation
    cross-products. Returns True iff the two open segments cross
    (touching at a single shared endpoint does NOT count)."""
    def _ccw(a, b, c) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1 = _ccw(p3, p4, p1)
    d2 = _ccw(p3, p4, p2)
    d3 = _ccw(p1, p2, p3)
    d4 = _ccw(p1, p2, p4)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) \
            and ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True
    return False


class Mounting(BaseModel):
    """Module mounting system used in the attachment plan (PV-4 / PV-5)."""
    rail_system: str = "IronRidge XR100"
    flashing: str = "IronRidge FlashFoot 2"
    max_x_spacing_in: float = 48.0          # rail span (max along-array)
    max_y_spacing_in: float = 32.0          # cross-array spacing
    max_cantilever_in: float = 18.0
    fastener: str = "5/16\" lag screw, 3\" embedment"
    lag_screw_length_in: float = 4.25       # PV-5 detail callout
    min_embedment_in: float = 2.5           # structural/PV-5 minimum
    max_roof_surface_gap_in: float = 6.0    # PV-5 rail/module height note


class EquipmentLocation(BaseModel):
    """K.11 — site-plan position of one piece of equipment.

    Coordinates are 2D site plan ft, origin = front-left corner of the
    LOT (not the house). +x = right (street-facing view); +y = away
    from the street toward the back of the lot. Same frame as
    `Site.lot_width_ft` / `lot_depth_ft`.

    `label` is the identifier used by the routing algorithm + DXF
    callouts (e.g. "INV-1", "SUB-PANEL-1", "ESS-1"). Defaults are
    empty — caller supplies meaningful labels matching the SLD.
    """
    label: str = ""
    x_ft: float = 0.0
    y_ft: float = 0.0


class EquipmentLocations(BaseModel):
    """K.11 — 2D site-plan coordinates for every wire-trunk endpoint.

    Used by `calc/wire_routing.py` to compute real per-segment conduit
    lengths (replacing the manual `wire_lengths` yaml block when full
    data is provided). Every field is optional; when `msp` is None the
    routing engine falls back to manual `wire_lengths` and DXF EE-1
    keeps the legacy stylised east-wall column.

    Manhattan-distance routing assumption: equipment lives along the
    house perimeter, conduit runs sit at 90° angles. For a v1 this
    over-estimates by ~5-10 % vs a true L-shaped routing optimiser,
    which is conservative on the safe side for NEC 215.2 voltage-drop.

    `attic_drop_x_ft` / `_y_ft` is the single point where roof-trunk
    conduit penetrates from the attic down the wall into the equipment
    column. Each roof_section's `roof_penetration` routes to this point.
    """
    msp: Optional[EquipmentLocation] = None              # main service panel
    inverters: list[EquipmentLocation] = Field(default_factory=list)
    sub_panels: list[EquipmentLocation] = Field(default_factory=list)
    ess_units: list[EquipmentLocation] = Field(default_factory=list)
    ac_disconnect: Optional[EquipmentLocation] = None
    # Attic-to-wall transition point. When None the routing engine
    # uses the inverter's site coords (a reasonable proxy for a
    # garage-mounted inverter with rooftop attic access nearby).
    attic_drop_x_ft: Optional[float] = None
    attic_drop_y_ft: Optional[float] = None
    # Vertical rise from attic floor down to equipment column. Includes
    # the eave-line height ABOVE the attic floor (typical 10 ft for
    # single-story residential).
    attic_to_eq_height_ft: float = 10.0

    @property
    def has_data(self) -> bool:
        """True when at least MSP + one inverter location is set —
        the minimum for end-to-end auto-routing."""
        return self.msp is not None and len(self.inverters) > 0


class SatelliteAlignment(BaseModel):
    """Stage 8 — EE-4 satellite/mask review alignment.

    This block calibrates the optional Google Solar dataLayers underlay
    and mask-contour candidate into the EE-4 site-plan coordinate
    frame. It is intentionally review-only: it does not replace
    `house_outline_vertices` or any `roof_sections[].vertices` until a
    designer accepts the overlay.
    """
    mode: Literal["raw", "fit_house_bbox", "manual"] = "raw"
    center_x_ft: Optional[float] = None
    center_y_ft: Optional[float] = None
    x_offset_ft: float = 0.0
    y_offset_ft: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation_deg: float = 0.0
    contour_simplify_ft: float = 2.0
    contour_max_vertices: int = 32

    @model_validator(mode="after")
    def _check_alignment_values(self) -> "SatelliteAlignment":
        if self.scale_x <= 0 or self.scale_y <= 0:
            raise ValueError(
                "satellite_alignment scale_x/scale_y must be positive"
            )
        if self.contour_simplify_ft < 0:
            raise ValueError(
                "satellite_alignment contour_simplify_ft must be >= 0"
            )
        if self.contour_max_vertices < 3:
            raise ValueError(
                "satellite_alignment contour_max_vertices must be >= 3"
            )
        return self


class EE4TracePolygon(BaseModel):
    """Stage 9 — one hand/vector-traced EE-4 polygon in site feet."""
    name: str = ""
    vertices: list[tuple[float, float]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_polygon(self) -> "EE4TracePolygon":
        if len(self.vertices) < 3:
            raise ValueError("EE4 trace polygon needs >=3 vertices")
        if _polygon_self_intersects(self.vertices):
            raise ValueError("EE4 trace polygon self-intersects")
        if _signed_polygon_area(self.vertices) <= 0:
            raise ValueError("EE4 trace polygon vertices must be CCW")
        return self


class EE4TraceLine(BaseModel):
    """Stage 9 — roof ridge/hip/valley/equipment trace line."""
    kind: Literal["ridge", "hip", "valley", "eave", "edge", "dormer"] = "edge"
    points: list[tuple[float, float]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_points(self) -> "EE4TraceLine":
        if len(self.points) < 2:
            raise ValueError("EE4 trace line needs >=2 points")
        return self


class EE4TraceSymbol(BaseModel):
    """Stage 9 — traced roof obstruction symbol in site feet."""
    kind: Literal[
        "roof_vent", "plumbing", "ac", "satellite", "mast", "chimney",
    ] = "roof_vent"
    x_ft: float
    y_ft: float


class EE4Trace(BaseModel):
    """Stage 9 — vector-traced EE-4 site-plan layer.

    This is the layer that can visually match a permit drafter's site
    plan: full roof outline, roof planes/facets, ridge/hip/valley lines,
    fire pathway polygons, and traced obstruction symbols. It is
    additive and opt-in; projects without it keep the K.13 auto layout.
    """
    enabled: bool = False
    roof_outline: Optional[EE4TracePolygon] = None
    roof_facets: list[EE4TracePolygon] = Field(default_factory=list)
    roof_lines: list[EE4TraceLine] = Field(default_factory=list)
    fire_pathways: list[EE4TracePolygon] = Field(default_factory=list)
    symbols: list[EE4TraceSymbol] = Field(default_factory=list)

    @property
    def has_geometry(self) -> bool:
        return bool(
            self.roof_outline
            or self.roof_facets
            or self.roof_lines
            or self.fire_pathways
        )


class PropertyContextLine(BaseModel):
    """Stage 9.9 — site-context linework such as fences or survey ties.

    Coordinates are in the same site-plan feet frame used by EE-4 trace:
    +x right on sheet, +y up sheet. This keeps hand-surveyed context,
    traced roof linework, and module rectangles in one frame.
    """
    label: str = ""
    kind: Literal["fence", "property", "setback", "utility", "other"] = "other"
    points: list[tuple[float, float]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_points(self) -> "PropertyContextLine":
        if len(self.points) < 2:
            raise ValueError("property_context line needs >=2 points")
        return self


class PropertyDimension(BaseModel):
    """Stage 9.9 — explicit survey-style dimension annotation.

    If `label` is blank, the renderer computes the feet/inches text from
    start/end. A non-empty label preserves survey strings such as 98'-10".
    `offset_ft` moves the dimension line normal to the measured segment.
    """
    label: str = ""
    start: tuple[float, float]
    end: tuple[float, float]
    offset_ft: float = 3.0


class PropertyContext(BaseModel):
    """Stage 9.9 — data-driven EE-4A property context layer.

    This block replaces the Stage 9.8 visual fallback with true input
    geometry when survey / GIS / satellite-reviewed context is available.
    Every field is optional; an empty block preserves the generated
    rectangle / driveway fallback used by older projects.
    """
    lot_outline: list[tuple[float, float]] = Field(default_factory=list)
    driveway_polygon: list[tuple[float, float]] = Field(default_factory=list)
    fence_lines: list[PropertyContextLine] = Field(default_factory=list)
    property_dimensions: list[PropertyDimension] = Field(default_factory=list)
    note: str = ""

    @model_validator(mode="after")
    def _check_polygons(self) -> "PropertyContext":
        for name, vertices in (
            ("lot_outline", self.lot_outline),
            ("driveway_polygon", self.driveway_polygon),
        ):
            if not vertices:
                continue
            if len(vertices) < 3:
                raise ValueError(f"property_context.{name} needs >=3 vertices")
            if _polygon_self_intersects(vertices):
                raise ValueError(f"property_context.{name} self-intersects")
            if _signed_polygon_area(vertices) <= 0:
                raise ValueError(
                    f"property_context.{name} vertices must be CCW"
                )
        return self

    @property
    def has_data(self) -> bool:
        return bool(
            self.lot_outline
            or self.driveway_polygon
            or self.fence_lines
            or self.property_dimensions
        )


class Site(BaseModel):
    """Phase F: physical layout for the site plan (EE-4)."""
    roof_pitch_deg: float = 22.0            # typical residential pitch
    array_azimuth_deg: float = 180.0        # 180 = due south (US convention)
    array_width_ft: float = 24.0            # PV array footprint
    array_depth_ft: float = 16.0
    lot_width_ft: float = 80.0
    lot_depth_ft: float = 120.0
    house_width_ft: float = 50.0
    house_depth_ft: float = 35.0
    # K.11.7f — optional polygon outline for L/T/irregular houses.
    # Coordinates in 2D site ft (origin = lot front-left, +x right,
    # +y away from street). When non-empty, the EE-4 renderer draws
    # the polygon instead of the `house_width × house_depth` rect.
    # Same invariants as RoofSection polygon: ≥3 verts, CCW, simple.
    # Default empty list → legacy rectangular house outline.
    house_outline_vertices: list[tuple[float, float]] = Field(
        default_factory=list
    )
    # Phase J: per-roof-face data for attachment plan (PV-4) + string plan (PV-6)
    roof_sections: list[RoofSection] = Field(default_factory=list)
    mounting: Mounting = Field(default_factory=Mounting)
    satellite_alignment: SatelliteAlignment = Field(
        default_factory=SatelliteAlignment
    )
    ee4_trace: EE4Trace = Field(default_factory=EE4Trace)
    property_context: PropertyContext = Field(default_factory=PropertyContext)

    @model_validator(mode="after")
    def _check_house_polygon(self) -> "Site":
        if not self.house_outline_vertices:
            return self
        if len(self.house_outline_vertices) < 3:
            raise ValueError(
                "Site.house_outline_vertices: need ≥3 vertices, got "
                f"{len(self.house_outline_vertices)}"
            )
        if _polygon_self_intersects(self.house_outline_vertices):
            raise ValueError(
                "Site.house_outline_vertices: polygon self-intersects "
                "(simple polygons only)"
            )
        if _signed_polygon_area(self.house_outline_vertices) <= 0:
            raise ValueError(
                "Site.house_outline_vertices: vertices must be CCW "
                "(signed area ≤ 0 detected); reverse the order"
            )
        return self

    # K.11 — equipment site-plan positions for auto wire-trunk routing.
    # When fully populated (`has_data == True`) the calc engine computes
    # per-segment conduit lengths from real distances and overrides any
    # values in `inputs.wire_lengths`. Empty / partial → keeps legacy
    # behaviour (manual wire_lengths or 50ft DEFAULT_LENGTH_FT fallback).
    equipment_locations: EquipmentLocations = Field(
        default_factory=EquipmentLocations
    )

    # K.8: site density drives default shading when a roof_section
    # has `shading_factor = 1.0` (the "I didn't measure" default).
    # rural ≈ no obstructions; suburban ≈ light tree / neighbor cover;
    # urban ≈ tight lots, frequent partial-day shading.
    urban_density: Literal["rural", "suburban", "urban", "unknown"] = "unknown"


class PvModule(BaseModel):
    brand: str
    model: str
    power_w: float
    voc_stc: float
    isc_stc: float
    voc_temp_coeff_pct_per_c: Optional[float] = Field(
        default=None,
        description="βVoc as %/°C (negative). If None, fall back to NEC Table 690.7.",
    )
    isc_temp_coeff_pct_per_c: Optional[float] = Field(
        default=None, description="αIsc as %/°C (positive)."
    )
    # K.9.1: physical dimensions for PV-4 placement engine. Defaults to
    # Talesun TP7G54M 415 (the 2026-05-17 Frisco reference); most modern
    # 410-450W modules are within ±2" of this on each edge. Datasheet
    # convention: length = long edge, width = short edge.
    length_in: float = 67.80
    width_in: float = 44.65
    weight_lbs: float = 47.40


class PvArray(BaseModel):
    modules: int
    strings: int
    modules_per_string: int
    module: PvModule
    ashrae_2pct_min_c: Optional[float] = None
    temp_min_c: float
    temp_max_c: float

    @model_validator(mode="after")
    def _check_module_count(self) -> "PvArray":
        if self.strings * self.modules_per_string != self.modules:
            raise ValueError(
                f"modules ({self.modules}) != strings × modules_per_string "
                f"({self.strings} × {self.modules_per_string} = "
                f"{self.strings * self.modules_per_string})"
            )
        return self

    @property
    def design_low_temp_c(self) -> float:
        return self.ashrae_2pct_min_c if self.ashrae_2pct_min_c is not None else self.temp_min_c


class Battery(BaseModel):
    brand: str
    model: str
    quantity: int
    nominal_voltage: float
    capacity_kwh_each: float

    # K.2.6b: physical install location & setbacks.
    # NEC 706.10 governs ESS disconnect placement. IRC R328 (residential
    # building code) governs storage system installation in dwelling
    # units — caps energy capacity per location, requires minimum
    # setbacks from doors/windows/egress paths, and dictates separation
    # from combustibles.
    #
    # Most stringent (R328 §R328.5 Indoor installations):
    #   * Installed in attached or detached garage, accessory structure,
    #     OR utility / storage closet built per R328.5 ratings.
    #   * Min 3 ft from doors / windows that lead to occupiable spaces.
    #   * Total capacity in any one location ≤ 40 kWh (residential
    #     IRC 2021); newer 2024 IRC allows up to 80 kWh with extra
    #     listing.
    #
    # `install_location='unknown'` defers everything to the engineer;
    # the doctor flags it as a missing-data WARN (not FAIL).
    install_location: Literal[
        "indoor", "garage", "outdoor", "outdoor_protected", "unknown",
    ] = "unknown"
    distance_to_doorway_ft: float = 0.0
    distance_to_window_ft: float = 0.0
    distance_to_egress_ft: float = 0.0

    @property
    def total_kwh(self) -> float:
        return self.quantity * self.capacity_kwh_each

    @property
    def installed(self) -> bool:
        """K.4.6.1: clean True/False flag for downstream consumers
        (customer PDF, doctor, ess_install check) to gate on. PV-only
        TX-market projects use `quantity = 0`; this property reads as
        False without any consumer having to know about the count.

        Why a property and not a yaml field: backward compat — every
        existing project's `Battery.quantity` already encodes
        installed-vs-not, and we don't want to double-source the
        truth. K.4.6 future-proof: if we add `Battery.install: bool`
        as an explicit yaml field, this property becomes the single
        read path that hides whichever is authoritative.
        """
        return self.quantity > 0


class Inverter(BaseModel):
    brand: str
    model: str
    ac_output_v: float
    ac_output_a: float       # per-unit AC output current
    quantity: int = 1        # number of inverters in parallel
    per_unit: bool = False   # legacy: if true, count = battery.quantity
                             #   (used by integrated inverter-battery systems
                             #    like Tesla Powerwall 3)

    def count(self, battery_quantity: int) -> int:
        """Effective number of inverters. `per_unit=True` forces count to
        match battery quantity (integrated-inverter assemblies); otherwise
        use the explicit `quantity` field."""
        return battery_quantity if self.per_unit else self.quantity


InterconnectMethod = Literal["120%_rule", "sum_rule", "supply_side_tap", "center_fed"]


class Service(BaseModel):
    main_panel_a: float
    busbar_a: float
    busbar_source: Literal["nameplate", "measured"] = "nameplate"
    voltage: str
    interconnection_methods: list[InterconnectMethod]
    # Optional: intermediate AC panels between the inverter bus and the MSP.
    # Drawn in series in the DXF; left empty for simple direct-to-MSP layouts.
    sub_panels: list[SubPanel] = Field(default_factory=list)
    # Service-feeding utility transformer (Phase D, NEC 110.24 AIC).
    utility_transformer: UtilityTransformer = Field(default_factory=UtilityTransformer)
    # OCPD interrupting rating assumption (kA). Residential breakers default 10 kAIC.
    default_ocpd_aic_ka: float = 10.0

    # K.2.5: existing PV/ESS already backfed AT THE MSP (not via a sub-panel).
    # The 705.12 evaluator adds this to the new system's backfeed when applying
    # sum / 120% rules. Default 0 = greenfield install.
    existing_solar_breaker_a_msp: float = 0.0

    # K.2.5: MSP physical breaker slots (mirrors SubPanel.available_slots).
    msp_available_slots: int = 0    # 0 = unknown, skip feasibility check
    msp_used_slots: int = 0

    # K.5: site's actual grounding electrode system. Default empty →
    # legacy 'assume the 3-electrode standard combo' behaviour preserved
    # at the renderer level. When populated, EE-2 + grounding checks
    # use the real GES data.
    grounding_electrode_system: GroundingElectrodeSystem = Field(
        default_factory=GroundingElectrodeSystem
    )

    @property
    def msp_free_slots(self) -> Optional[int]:
        if self.msp_available_slots <= 0:
            return None
        return max(0, self.msp_available_slots - self.msp_used_slots)

    @property
    def total_existing_solar_a(self) -> float:
        """Total of ALL pre-existing PV/ESS backfeed breakers on this
        service — MSP-level + every sub-panel's existing solar. Used by
        705.12 to apply sum-rule and 120%-rule against the EXISTING bus
        load before the new system is added."""
        return self.existing_solar_breaker_a_msp + sum(
            sp.existing_solar_breaker_a for sp in self.sub_panels
        )


class BackupOption(BaseModel):
    """K.4.6.5 — one battery upgrade option for the customer-PDF 3-tier
    quote table.

    Listed in `loads.backup_options[]`. The "base" tier is implicit:
    whatever the project's top-level `battery` block carries (typically
    `quantity=0` PV-only for the TX-market default). Each option here
    becomes one ADDITIONAL column in the 3-tier table:

        ┌──────────┬───────────┬───────────┐
        │ PV-only  │ Option 1  │ Option 2  │  ← list `backup_options`
        │  (base)  │           │           │
        └──────────┴───────────┴───────────┘

    Economics for each option run a `Battery.model_copy(update=…)`
    swapping in `battery_ref`'s library entry at `quantity` units; the
    PV cost stays identical (same array), so the only delta vs base
    is battery cost + backup capability.

    Why this isn't just a duplicate Battery block: the customer PDF
    needs CONCURRENT 3-column rendering, not pick-one-and-recompute.
    The yaml expresses "here are 2-3 upgrade tiers" declaratively.
    """
    name: str                          # "+ 16 kWh in-house battery"
    battery_ref: str                   # devices.BATTERIES key (must resolve)
    quantity: int = 1                  # how many of this battery in this tier


class Loads(BaseModel):
    """Household electrical demand context.

    Phase 0/B fields (`critical_subpanel_a`, `whole_home_backup`) drive
    the backup-side SLD and EE-3 critical-loads routing.

    **Phase K.2.5 additions** — historical & projected energy use. The
    calc engine uses these for:
      * Sizing reality-check ("12 mo avg = 950 kWh → 6 kW PV is undersized")
      * NEC 220.83 dwelling-load calc (when present)
      * ESS backup-runtime estimate ("hvac_type = heat_pump" → assume
        peak winter load X kW)
    All defaults preserve old yaml: empty `monthly_kwh` skips the
    reality-check, `hvac_type='unknown'` defers to engineer assumption.
    """
    critical_subpanel_a: Optional[float] = None
    whole_home_backup: bool = False

    # K.2.5 historical / projected demand
    monthly_kwh: list[float] = Field(
        default_factory=list,
        description=("Last-12-months kWh from utility bill, oldest first. "
                     "Empty list = unknown; engine skips sizing check."),
    )
    hvac_type: Literal[
        "heat_pump", "gas_furnace_ac", "electric_resistance", "unknown",
    ] = "unknown"
    has_ev: bool = False                # current EV charger on premises
    planned_ev: bool = False            # homeowner plans to add an EV
    planned_electrification: bool = False  # heat-pump / induction / HPWH upgrade

    # K.7 [2/4] + K.4.6.4: export tariff model. Drives K.4 customer-summary ROI.
    #   "1to1_nem"            — classic 1:1 net metering (most US states)
    #   "ca_nem3"             — California NEM 3.0 (post-2023-04):
    #                           exports paid at ~25-30% of retail (ACC tariff)
    #   "hi_self_consumption" — Hawaii Customer Self-Supply / Smart Export:
    #                           exports paid at ~14¢/kWh fixed
    #
    # K.4.6.4 TX REP presets (Texas deregulated market — every REP plan
    # gives a different buyback rate, and the SAME PV system can have
    # 50% variance in monthly savings depending on which REP the
    # homeowner picks). Numbers from 2026 plan filings; see
    # `customer/economics.py::EXPORT_RATIOS` for the exact values.
    #   "tx_default_oncor"   — generic Oncor REP, ~0.50× retail buyback
    #   "tx_txu_buyback"     — TXU Home Solar Buyback, 1:1 retail
    #   "tx_green_mountain"  — GME Renewable Rewards, 1:1 retail
    #   "tx_reliant_sun"     — Reliant Sun Sustainability, ~0.95× retail
    #   "tx_rhythm_pure"     — Rhythm Pure Energy, ~0.70× retail
    #
    # `self_consumption_fraction`: portion of PV production consumed onsite
    # vs exported. Defaults 0.45 (NREL residential average without ESS);
    # with ESS, real-world 0.6-0.8. Engineers override per project.
    #
    # K.4.6.6 SMT semantics note:
    #   * On 1:1 plans (1to1_nem / tx_green_mountain / tx_txu_buyback) the
    #     effective_rate equation collapses to `retail × 1.0` regardless
    #     of self_consumption_fraction. With Smart Meter Texas net metering,
    #     EVERY kWh produced offsets the bill — timing is irrelevant.
    #   * On sub-1:1 plans (tx_default_oncor 0.50× etc.), self_consumption
    #     matters a lot. Smart Meter Texas + load-shifting (dishwasher,
    #     EV charging, pool pump scheduled to PV hours) typically raises
    #     self-consumption from passive 0.30 to active 0.55-0.70. doctor
    #     check `self_consumption_realistic_for_rep_plan` flags projects
    #     that haven't accounted for this.
    export_tariff_model: Literal[
        "1to1_nem", "ca_nem3", "hi_self_consumption",
        "tx_default_oncor", "tx_txu_buyback", "tx_green_mountain",
        "tx_reliant_sun", "tx_rhythm_pure",
    ] = "1to1_nem"
    self_consumption_fraction: float = 0.45

    # K.4.6.4 escape hatch: when a specific TX REP plan isn't in our
    # preset list (or rates change mid-year), set the buyback ratio
    # directly. When `rep_buyback_ratio` is non-None, it overrides
    # `export_tariff_model`. `rep_plan_name` is informational only —
    # surfaces in the customer-PDF footer for the homeowner to verify.
    rep_buyback_ratio: Optional[float] = None
    rep_plan_name: str = ""

    # K.4.6.5: upgrade tiers for the customer-PDF 3-tier quote table.
    # Each entry renders as an additional column next to the base
    # (PV-only or current-battery) configuration. Empty list = no
    # 3-tier block (backward compat for every pre-K.4.6.5 yaml).
    backup_options: list[BackupOption] = Field(default_factory=list)

    # K.8.2: opt-in switch for value-weighted module distribution.
    # When True, the K.8.1 LRM auto-distribute weights faces by
    # `area × face_value_weighted_derate` (hourly production × hourly
    # value pattern) instead of `area × Sandia_annual_derate`. The
    # difference:
    #   * On 1:1 REP plans → math collapses, value_weighted == Sandia,
    #     distribution unchanged (Frisco GME case)
    #   * On sub-1:1 plans → West-facing faces boost ~10%, East-facing
    #     drop ~5%; automates the SW-quadrant installation strategy
    #     without manually pruning yaml faces
    # Default False keeps every pre-K.8.2 yaml unchanged.
    use_value_weighted_distribution: bool = False

    @model_validator(mode="after")
    def _check_rep_buyback_in_range(self) -> "Loads":
        if self.rep_buyback_ratio is not None:
            if not (0.0 <= self.rep_buyback_ratio <= 1.0):
                raise ValueError(
                    f"rep_buyback_ratio must be in [0.0, 1.0] "
                    f"(fraction of retail); got {self.rep_buyback_ratio}"
                )
        return self

    @property
    def annual_kwh(self) -> Optional[float]:
        """Sum of monthly_kwh if 12 months provided, else None."""
        if len(self.monthly_kwh) == 12:
            return sum(self.monthly_kwh)
        return None

    @property
    def peak_month_kwh(self) -> Optional[float]:
        if not self.monthly_kwh:
            return None
        return max(self.monthly_kwh)


class Inputs(BaseModel):
    project: ProjectMeta
    pv_array: PvArray
    battery: Battery
    inverter: Inverter
    service: Service
    loads: Loads
    # Optional top-level blocks (Phase B); empty defaults keep old yaml valid.
    design_engineer: DesignEngineer = Field(default_factory=DesignEngineer)
    installer: Installer = Field(default_factory=Installer)
    # Optional Phase D blocks
    wire_lengths: WireLengths = Field(default_factory=WireLengths)
    routing: Routing = Field(default_factory=Routing)
    # Phase F site layout for EE-4 site plan
    site: Site = Field(default_factory=Site)
    # Phase J: optional module-level optimizer (Tigo TS4-A-O, SolarEdge etc.)
    optimizer: Optimizer = Field(default_factory=Optimizer)

    @classmethod
    def from_yaml(cls, path: Path) -> "Inputs":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        data = _expand_device_refs(data)
        return cls.model_validate(data)


def _expand_device_refs(data: dict) -> dict:
    """Resolve `module_ref` / `inverter_ref` / `battery_ref` / `optimizer_ref`
    keys into full datasheet dicts using the `pvess_calc.devices` registry.
    Inline definitions keep working — refs only fire when the corresponding
    `_ref` field is set.
    """
    from .devices import get_battery, get_inverter, get_module, get_optimizer

    pv = data.get("pv_array", {}) or {}
    ref = pv.pop("module_ref", None)
    if ref is not None:
        pv["module"] = get_module(ref).model_dump()
    data["pv_array"] = pv

    inv_ref = data.get("inverter", {}).pop("ref", None) if "inverter" in data else None
    if inv_ref is not None:
        ds = get_inverter(inv_ref).model_dump()
        data["inverter"] = {**ds, **data.get("inverter", {})}

    bat_ref = data.get("battery", {}).pop("ref", None) if "battery" in data else None
    if bat_ref is not None:
        ds = get_battery(bat_ref).model_dump()
        data["battery"] = {**ds, **data.get("battery", {})}

    opt_ref = data.get("optimizer", {}).pop("ref", None) if "optimizer" in data else None
    if opt_ref is not None:
        ds = get_optimizer(opt_ref).model_dump()
        data["optimizer"] = {**ds, **data.get("optimizer", {})}

    return data
