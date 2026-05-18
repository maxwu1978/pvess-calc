# `inputs.yaml` schema reference

Top-level structure (defaults shown):

```yaml
project:        {...}        # required — see ProjectMeta
pv_array:       {...}        # required — see PvArray
battery:        {...}        # required — see Battery
inverter:       {...}        # required — see Inverter
service:        {...}        # required — see Service
loads:          {...}        # required — see Loads

design_engineer: {...}       # optional (Phase B) — see DesignEngineer
installer:       {...}       # optional (Phase B) — see Installer
wire_lengths:    {...}       # optional (Phase D) — voltage drop
routing:         {...}       # optional (Phase D) — 310.15(B) derating
site:            {...}       # optional (Phase F) — site plan + roofs
optimizer:       {...}       # optional (Phase J) — module-level MLPE
```

Every field has a default that makes the yaml parseable. Skipping
optional blocks works — the calc engine falls back gracefully.

## `project`

```yaml
project:
  id: "001-jones-residence"          # str, becomes folder name
  name: "Jones Residence"            # str, shown on cover
  location: "Phoenix, AZ"            # str, "City, ST" for lookup
  ahj: "City of Phoenix"             # str
  nec_edition: "2023"                # "2023" | "2020" | "2017"

  # Phase B (permit metadata) — all optional
  client_name: ""
  site_address: ""
  coordinates: ""                    # "33.5, -112.05"
  apn: ""
  utility: ""
  drawn_by: ""
  revision: "A"
  initial_design_date: ""
  permit_profile: "internal"          # internal | tx_residential_pv | wyssling_like
  structural_letter_pdf: ""           # signed engineer PDF to prepend, if supplied

  # Stage 9.13: PV-7 site-photo inputs. Missing paths render placeholders.
  site_photos:
    - kind: "front_elevation"         # front_elevation | roof | meter | main_panel | sub_panel | attic | equipment_location | other
      path: "photos/front.jpg"        # project-relative or absolute
      caption: "Front elevation"

  # Stage 9.14: selected-equipment manufacturer PDFs appended in SPEC.
  # Do not list alternate inverter candidates here; each actual project
  # submits one selected inverter model.
  spec_sheets:
    - equipment: "selected_inverter"
      path: "cut_sheets/01-inverter.pdf"
      pages: []                       # 1-based subset; empty = all pages

  # K.12 + Stage 9.12: plan-set / field-survey metadata.
  roof_info:
    stories: 1
    type: ""
    height_ft: 0.0
    construction: ""
    condition: "unknown"              # good | fair | poor | unknown
    being_replaced: false
    flashing: ""
    framing: ""
    attic_access: "unknown"           # accessible | inaccessible | unknown
    decking_thickness_in: 0.0
    roof_layers: 0                    # 0 = unknown
  meter_info:
    number: ""
    location: ""
    esid: ""                          # Texas/ERCOT service identifier
```

`tx_residential_pv` and `wyssling_like` switch the permit package to the
reference-style PV/EE sheet numbering. Missing structural/photo/spec files do
not block rendering; the package emits draft/placeholder pages and doctor
reports a WARN so the intake gap is visible before AHJ submission.

## `pv_array`

```yaml
pv_array:
  modules: 24                        # int, total module count
  strings: 2                         # int
  modules_per_string: 12             # int — must satisfy modules = strings × this
  module:                            # PvModule
    brand: "Generic"
    model: "MONO-420-144"
    power_w: 420.0
    voc_stc: 49.5
    isc_stc: 13.8
    voc_temp_coeff_pct_per_c: -0.28  # optional (NEC 690.7)
    isc_temp_coeff_pct_per_c:  0.048 # optional
  ashrae_2pct_min_c: -5.0            # optional, preferred over temp_min_c
  temp_min_c: -5.0
  temp_max_c: 45.0

  # K.4 alternative: pull module datasheet from device library
  module_ref: "talesun_tp7g54m_415"  # see src/pvess_calc/devices/modules.py
```

## `service`

The big one. Tracks the MSP + sub-panels + interconnection methods.

```yaml
service:
  main_panel_a: 200                  # float, MSP main breaker
  busbar_a: 200                      # float
  busbar_source: "nameplate"         # "nameplate" | "measured"
  voltage: "120/240 split-phase"
  interconnection_methods:           # list of methods to evaluate
    - "120%_rule"
    - "sum_rule"
    - "supply_side_tap"

  # K.2.5: existing PV/ESS already on the service
  existing_solar_breaker_a_msp: 0.0
  msp_available_slots: 0             # 0 = unknown
  msp_used_slots: 0

  # Sub-panels (PV aggregation OR critical-loads backup)
  sub_panels:
    - name: "Sub Panel #2"
      role: "pv_aggregation"          # | "critical_loads"
      rating_a: 200
      busbar_a: 200
      location: "NW exterior wall"
      backfeed_breaker_a: 50
      # K.2.5 additions:
      service_rated: false
      available_slots: 0
      used_slots: 0
      existing_solar_breaker_a: 0.0
      enclosure_rating: "unknown"     # "NEMA 1" | "NEMA 3R" | "unknown"
      # K.2.6a additions:
      distance_to_msp_ft: 0.0
      # K.2.6c additions (manual breakers schedule):
      breakers: []                    # list of InternalBreaker

  # Phase D: utility-feeding transformer (NEC 110.24 AIC)
  utility_transformer:
    kva: 25.0
    impedance_pct: 2.0
    secondary_voltage: 240.0
  default_ocpd_aic_ka: 10.0

  # K.5: grounding electrode system
  grounding_electrode_system:
    rods: []                         # list of GroundRod
    metal_water_pipe: null           # MetalWaterPipeBond | null
    ufer: null                       # UferElectrode | null
    gec_main_size_awg: ""            # "" | "8" | "6" | "4" | ...
    bonded_to_neutral_at_service: "unknown"   # "yes" | "no" | "unknown"
    pv_separate_ground: false
    existing_grounding_summary: ""
```

## `battery`

```yaml
battery:
  brand: "EG4"
  model: "LifePower4 V2"
  quantity: 8
  nominal_voltage: 51.2
  capacity_kwh_each: 5.12

  # K.2.6b: ESS install location (NEC 706.10 + IRC R328)
  install_location: "unknown"        # indoor | garage | outdoor | outdoor_protected | unknown
  distance_to_doorway_ft: 0.0        # IRC R328.5 requires ≥3 ft indoor/garage
  distance_to_window_ft: 0.0
  distance_to_egress_ft: 0.0

  # K.4 alternative: device-library reference
  ref: "tesla_powerwall_3"
```

## `inverter`

```yaml
inverter:
  brand: "Generic"
  model: "8K Hybrid"
  ac_output_v: 240
  ac_output_a: 33
  quantity: 3                        # parallel inverters
  per_unit: false                    # true → count = battery.quantity (PW3-style)
  dc_afci: "unknown"                 # integrated | external_required | unknown
  ul1699b_listed: false              # Phase H: NEC 690.11 evidence flag

  ref: "megarevo_r8klna"             # K.4 device-library ref
```

## `loads`

```yaml
loads:
  critical_subpanel_a: 100           # optional (Phase 0)
  whole_home_backup: false

  # K.2.5 — demand context (sizing reality-check + ESS runtime estimate)
  monthly_kwh: []                    # 12 values for full sizing check
  hvac_type: "unknown"               # heat_pump | gas_furnace_ac | electric_resistance | unknown
  has_ev: false
  planned_ev: false
  planned_electrification: false

  # K.7 [2/4] — drives K.4 customer-summary ROI
  export_tariff_model: "1to1_nem"    # 1to1_nem | ca_nem3 | hi_self_consumption
  self_consumption_fraction: 0.45    # 0..1, baseline ~0.45, ESS-aware ~0.6-0.8
```

## `site` (optional, Phase F+)

```yaml
site:
  # Coarse geometry — used for EE-4 site plan when no roof_sections supplied
  roof_pitch_deg: 22.0
  array_azimuth_deg: 180.0
  array_width_ft: 24.0
  array_depth_ft: 16.0
  lot_width_ft: 80.0
  lot_depth_ft: 120.0
  house_width_ft: 50.0
  house_depth_ft: 35.0
  house_outline_vertices: []          # optional site-ft polygon, CCW

  # Stage 9.9: optional data-driven property context for EE-4A.
  # Coordinates use the same local ft frame as `ee4_trace`; when omitted,
  # EE-4A falls back to a generated property rectangle / driveway strip.
  property_context:
    lot_outline:
      - [-7.0, 28.0]
      - [106.0, 28.0]
      - [106.0, 94.0]
      - [-7.0, 94.0]
    driveway_polygon:
      - [91.0, 28.0]
      - [106.0, 28.0]
      - [106.0, 94.0]
      - [91.0, 94.0]
    fence_lines:
      - label: "FENCE"
        kind: "fence"                # fence | property | setback | utility | other
        points: [[91.0, 94.0], [106.0, 94.0]]
    property_dimensions:
      - start: [-7.0, 94.0]
        end: [106.0, 94.0]
        offset_ft: 8.0               # blank label → renderer computes 113'
      - label: "66'-0\""             # optional survey string override
        start: [106.0, 28.0]
        end: [106.0, 94.0]
        offset_ft: -3.0

  # K.2.6c–K.2.8: per-roof-face geometry (overrides coarse fields)
  roof_sections:
    - name: "South Roof"
      shape: "rect"                  # "rect" | "tri" | "polygon"
      roof_type: "Comp Shingle"
      pitch_deg: 22.0
      azimuth_deg: 180.0
      width_ft: 38.0
      height_ft: 24.0
      module_count: 30
      attachment_count: 40
      # K.2.6c additions:
      apex_x_ratio: 0.5              # tri only — apex along the base
      obstructions:                  # list of RoofObstruction
        - kind: "chimney"            # chimney | skylight | vent_pipe | hvac_unit | ...
          x_ft: 8
          y_ft: 10
          width_ft: 3
          height_ft: 3
          setback_ft: 1.5
      edge_setbacks:                 # per-edge override
        - edge_type: "eave"          # eave | ridge | rake | valley | hip | apex
          setback_ft: 3.0            # CA Title 24 uses 3 ft
      default_setback_ft: 1.5
      obstructions_note: ""
      # K.2.7 polygon vertices (when shape="polygon"):
      vertices: []                   # list[(x, y)], CCW, simple polygon
      # K.11: map roof-local coordinates into EE-4 site feet:
      site_anchor_x_ft: 50.0
      site_anchor_y_ft: 35.0
      site_anchor_azimuth_deg: 180.0

  # Stage 8: optional satellite/mask review alignment for EE-4 overlays.
  # `raw` uses the Google Solar raster frame as-is; `fit_house_bbox`
  # scales the underlay into the drawn house bbox; `manual` applies
  # center / offset / scale / rotation values directly.
  satellite_alignment:
    mode: "raw"                      # raw | fit_house_bbox | manual
    center_x_ft: null
    center_y_ft: null
    x_offset_ft: 0.0
    y_offset_ft: 0.0
    scale_x: 1.0
    scale_y: 1.0
    rotation_deg: 0.0
    contour_simplify_ft: 2.0
    contour_max_vertices: 32

  # Stage 9: optional hand/vector-traced EE-4 layer. Generate a starting
  # block with `pvess ee4-trace projects/<id>/`, paste it here, then tune
  # points against the rendered EE-4 preview.
  ee4_trace:
    enabled: false
    roof_outline:
      name: "main roof outline"
      vertices: [[0, 0], [80, 0], [80, 40], [0, 40]]
    roof_facets: []
    roof_lines:
      - kind: "ridge"                # ridge | hip | valley | eave | edge | dormer
        points: [[20, 20], [60, 20]]
    fire_pathways:
      - name: "18 in fire offset"
        vertices: [[20, 10], [70, 10], [70, 16], [20, 16]]
    symbols:
      - kind: "plumbing"             # roof_vent | plumbing | ac | satellite | mast | chimney
        x_ft: 42.0
        y_ft: 22.0

  mounting:
    rail_system: "IronRidge XR100"
    flashing: "IronRidge FlashFoot 2"
    max_x_spacing_in: 48.0
    max_y_spacing_in: 32.0
    max_cantilever_in: 18.0
    fastener: "5/16\" lag screw, 3\" embedment"
```

## `wire_lengths` (Phase D)

```yaml
wire_lengths:
  pv_string_one_way_ft: 60           # roof to combiner
  pv_to_combiner_ft: 15              # alias / total PV source run
  combiner_to_inverter_ft: 25
  inverter_to_ac_disc_ft: 8
  ac_disc_to_msp_ft: 12              # K.2.6a: LAST-hop only when sub-panels supply distances
  ess_to_inverter_ft: 5
```

Any `0.0` value falls back to a 50 ft default (engine emits `DEFAULT`
status on that segment).

## `routing` (Phase D)

```yaml
routing:
  ambient_temp_c: 45                 # NEC 310.15(B)(2)(a)
  pv_conduit_fill_count: 6           # NEC 310.15(B)(3)(a)(1)
  ac_conduit_fill_count: 3
```

## Validation

Every yaml is validated via pydantic on load. Pre-flight check:

```bash
python -c "from pvess_calc.schema import Inputs; \
           Inputs.from_yaml('projects/X/inputs.yaml')"
```

The doctor's `inputs_load` check runs this implicitly before every
other check.
