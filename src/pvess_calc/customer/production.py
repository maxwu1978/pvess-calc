"""K.8 — annual production aggregator.

Bridge between NREL's "south-facing latitude-tilt baseline" PVWatts
output and the per-face reality of a multi-face residential array.

When the project has `site.roof_sections`, we:

  1. Pull the baseline `annual_energy_kwh_per_kw` from lookup
     (NREL PVWatts, queried at a fixed reference orientation).
  2. For each roof_section, compute:
        face_kw     = section.module_count × pv_array.module.power_w / 1000
        derate      = orientation_derate(face.azimuth_deg, face.pitch_deg)
        shading     = resolve_shading_factor(face.shading_factor,
                                              site.urban_density)
        face_kwh    = baseline × face_kw × derate × shading
  3. Sum across all faces.

When the project has NO roof_sections, fall back to the legacy
"baseline × system_kw_dc" calculation — exactly the K.4 behaviour.
This keeps every pre-K.8 project bit-identical.

Returns a `ProductionResult` carrying both the aggregate number and
the per-face breakdown (for K.4 customer-summary's optional breakdown
table when multi-face).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..calc.orientation import orientation_derate, resolve_shading_factor
from ..schema import Inputs


@dataclass
class FaceProduction:
    name: str
    kw_dc: float            # this face's DC kW capacity
    azimuth_deg: float
    tilt_deg: float
    orientation_derate: float       # 0..1 vs reference orientation
    shading_factor: float           # 0..1 effective shading
    annual_production_kwh: float    # face_kw × baseline × derate × shading


@dataclass
class ProductionResult:
    annual_production_kwh: float    # total across all faces
    baseline_kwh_per_kw: float      # NREL or latitude-fallback baseline
    method: str                     # "per_face" — designer-distributed
                                    # "per_face_auto_distributed" — K.3c
                                    #     handoff, modules spread by area
                                    # "system_aggregate" — single orient.
    faces: list[FaceProduction] = field(default_factory=list)

    @property
    def is_per_face(self) -> bool:
        """True for ALL per-face methods (manual + K.8.1 auto-distributed
        area-only + K.8.2 auto-distributed value-weighted). Downstream
        (customer PDF, doctor check) treats them the same: a face
        breakdown exists."""
        return self.method in (
            "per_face",
            "per_face_auto_distributed",
            "per_face_auto_distributed_value_weighted",
        )

    @property
    def blended_derate(self) -> Optional[float]:
        """Average orientation × shading derate across all faces,
        weighted by face capacity. `None` when there's no per-face
        breakdown (single-aggregate method)."""
        if not self.faces:
            return None
        total_kw = sum(f.kw_dc for f in self.faces)
        if total_kw <= 0:
            return None
        weighted = sum(
            f.kw_dc * f.orientation_derate * f.shading_factor
            for f in self.faces
        )
        return weighted / total_kw


def compute_annual_production(
    inputs: Inputs,
    *,
    baseline_kwh_per_kw: float,
    baseline_method: str,
    latitude_deg: Optional[float] = None,
) -> ProductionResult:
    """K.8 — orchestrate the per-face vs aggregate decision.

    Args:
        inputs: Project Inputs.
        baseline_kwh_per_kw: From lookup_fields (NREL PVWatts annual
            energy per 1 kW DC) OR a latitude-fallback estimate.
        baseline_method: "nrel-pvwatts" / "latitude-fallback" /
            "us-average-fallback" — passed through into `method` for
            traceability.
        latitude_deg: K.8.2 — project latitude (from Mapbox lookup or
            `project.coordinates`). Used by the value-weighted LRM
            path when `loads.use_value_weighted_distribution=True`.
            None falls back to the K.8.1 area-only LRM unchanged.

    Returns:
        ProductionResult with aggregate kWh + per-face breakdown
        (when applicable).
    """
    sections = inputs.site.roof_sections
    site_density = inputs.site.urban_density
    module_w = inputs.pv_array.module.power_w
    total_modules = inputs.pv_array.modules
    system_kw = total_modules * module_w / 1000.0

    # K.8: short-circuit when there's no PV at all. A yaml with
    # `pv_array.modules = 0` but stale `roof_sections.module_count` from
    # a scenario sweep would otherwise still produce face-level kWh —
    # honest answer is "no array, no production". Matches the degraded
    # "0-savings → None payback" customer contract.
    if total_modules <= 0:
        return ProductionResult(
            annual_production_kwh=0.0,
            baseline_kwh_per_kw=baseline_kwh_per_kw,
            method="system_aggregate",
            faces=[],
        )

    if not sections:
        # Legacy path — single orientation, no per-face math.
        return ProductionResult(
            annual_production_kwh=baseline_kwh_per_kw * system_kw,
            baseline_kwh_per_kw=baseline_kwh_per_kw,
            method="system_aggregate",
            faces=[],
        )

    # Per-face aggregation. Modules declared at the section level use
    # the section count.
    declared_modules = sum(s.module_count for s in sections)

    # K.8.1 — K.3c handoff. When sections come from Google Solar but the
    # designer hasn't manually distributed `pv_array.modules` across faces
    # yet (every `module_count = 0`), DON'T fall back to the optimistic
    # single-orientation baseline — that silently over-promises ~5-10%
    # in the customer summary PDF. Instead, distribute the total modules
    # across faces proportionally to gross face area (designer can later
    # hand-tune per yaml).
    #
    # Allocation algorithm: Largest Remainder Method (Hamilton 1792,
    # used for US House apportionment 1850-1900). For each face:
    #   1. fair_share_i = total_modules × area_i / Σ areas
    #   2. floor_i      = math.floor(fair_share_i)
    # Then remainder = total_modules − Σ floor_i. Distribute the
    # remainder one-by-one to the faces with the largest fractional
    # parts of their fair share. Properties:
    #   * Conservation: Σ allocated == total_modules exactly.
    #   * Fairness: no face gets >1 from rounding error, no face is
    #     unjustly zeroed (the K.8.1-v1 "last-face-remainder" bug
    #     uncovered by Frisco's 13-face E2E test: cumulative rounding
    #     drove the last face's residual to 0 even when its area-
    #     proportional share was ~0.7 modules ≈ deserved 1).
    distribution_method = "per_face"
    if declared_modules <= 0:
        # K.9.2: distribution math extracted to `calc/face_distribution.py`
        # so engine + customer paths see byte-identical counts. K.8.2
        # value-weighting is applied inside that helper when the yaml
        # flag is on AND latitude is known.
        face_areas = [s.gross_area_sqft for s in sections]
        total_area = sum(face_areas)
        if total_area <= 0:
            return ProductionResult(
                annual_production_kwh=baseline_kwh_per_kw * system_kw,
                baseline_kwh_per_kw=baseline_kwh_per_kw,
                method="system_aggregate",
                faces=[],
            )
        from ..calc.face_distribution import distribute_modules_to_faces
        face_counts = distribute_modules_to_faces(
            inputs, latitude_deg=latitude_deg,
        )
        # Apply the distribution to the in-memory sections (NOT the
        # original yaml — designer's job to commit a distribution if
        # they like ours).
        sections = [
            s.model_copy(update={"module_count": face_counts.get(s.name, 0)})
            for s in sections
        ]
        # Method-string contract for ProductionResult.is_per_face and
        # the doctor check. Tag with the value-weighted suffix when
        # the K.8.2 flag drove the distribution.
        use_value_weight = (
            inputs.loads.use_value_weighted_distribution
            and latitude_deg is not None
        )
        distribution_method = (
            "per_face_auto_distributed_value_weighted"
            if use_value_weight else "per_face_auto_distributed"
        )

    faces: list[FaceProduction] = []
    total_kwh = 0.0
    for s in sections:
        if s.module_count <= 0:
            continue
        face_kw = s.module_count * module_w / 1000.0
        derate = orientation_derate(s.azimuth_deg, s.pitch_deg)
        shading = resolve_shading_factor(s.shading_factor, site_density)
        face_kwh = baseline_kwh_per_kw * face_kw * derate * shading
        total_kwh += face_kwh
        faces.append(FaceProduction(
            name=s.name, kw_dc=face_kw,
            azimuth_deg=s.azimuth_deg, tilt_deg=s.pitch_deg,
            orientation_derate=derate, shading_factor=shading,
            annual_production_kwh=face_kwh,
        ))

    return ProductionResult(
        annual_production_kwh=total_kwh,
        baseline_kwh_per_kw=baseline_kwh_per_kw,
        method=distribution_method,
        faces=faces,
    )
