"""Layer standard for CAD-reviewed roof geometry."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LayerSpec:
    name: str
    color: int
    description: str
    required_for_import: bool = False


ROOF_OUTLINE = "ROOF_OUTLINE"
ROOF_FACET = "ROOF_FACET"
ROOF_RIDGE = "ROOF_RIDGE"
ROOF_HIP = "ROOF_HIP"
ROOF_VALLEY = "ROOF_VALLEY"
ROOF_EAVE = "ROOF_EAVE"
ROOF_RAKE = "ROOF_RAKE"
ROOF_OBSTRUCTION = "ROOF_OBSTRUCTION"
FIRE_SETBACK = "FIRE_SETBACK"
PV_MODULE_ZONE = "PV_MODULE_ZONE"
TEXT_ROOF_LABEL = "TEXT_ROOF_LABEL"

REFERENCE_FRAME = "REFERENCE_FRAME"
REFERENCE_CANDIDATE = "REFERENCE_CANDIDATE"
REFERENCE_UNDERLAY = "REFERENCE_UNDERLAY"
REFERENCE_TEXT = "REFERENCE_TEXT"
REFERENCE_FACE_PRIORITY = "REFERENCE_FACE_PRIORITY"
REFERENCE_EXCLUSION = "REFERENCE_EXCLUSION"


IMPORT_LAYER_SPECS: tuple[LayerSpec, ...] = (
    LayerSpec(
        ROOF_OUTLINE, 1,
        "Closed polyline for the reviewed overall roof outline.",
        required_for_import=True,
    ),
    LayerSpec(
        ROOF_FACET, 3,
        "Closed polylines for reviewed roof planes/facets.",
        required_for_import=True,
    ),
    LayerSpec(ROOF_RIDGE, 5, "Open linework for ridges."),
    LayerSpec(ROOF_HIP, 30, "Open linework for hips."),
    LayerSpec(ROOF_VALLEY, 6, "Open linework for valleys."),
    LayerSpec(ROOF_EAVE, 4, "Open linework for eaves."),
    LayerSpec(ROOF_RAKE, 2, "Open linework for rakes."),
    LayerSpec(
        ROOF_OBSTRUCTION, 40,
        "Closed polylines for chimneys, skylights, vents, and roof objects.",
    ),
    LayerSpec(FIRE_SETBACK, 140, "Optional closed fire pathway polygons."),
    LayerSpec(PV_MODULE_ZONE, 92, "Optional reviewed PV module zones."),
    LayerSpec(
        TEXT_ROOF_LABEL, 7,
        "Optional facet labels, e.g. NAME=South PITCH=22 AZ=180.",
    ),
)

REFERENCE_LAYER_SPECS: tuple[LayerSpec, ...] = (
    LayerSpec(REFERENCE_FRAME, 8, "Reference frame, scale bar, and north arrow."),
    LayerSpec(REFERENCE_UNDERLAY, 8, "Satellite/raster underlay image."),
    LayerSpec(
        REFERENCE_CANDIDATE, 9,
        "Auto-generated candidate geometry; review before copying to import layers.",
    ),
    LayerSpec(REFERENCE_TEXT, 8, "Instructions and source notes."),
    LayerSpec(
        REFERENCE_FACE_PRIORITY, 3,
        "Review-only roof face orientation priority zones.",
    ),
    LayerSpec(
        REFERENCE_EXCLUSION, 1,
        "Review-only no-panel obstruction/setback reference zones.",
    ),
)

ALL_LAYER_SPECS: tuple[LayerSpec, ...] = (
    IMPORT_LAYER_SPECS + REFERENCE_LAYER_SPECS
)

REQUIRED_IMPORT_LAYERS = {
    spec.name for spec in IMPORT_LAYER_SPECS if spec.required_for_import
}

ROOF_LINE_KIND_BY_LAYER = {
    ROOF_RIDGE: "ridge",
    ROOF_HIP: "hip",
    ROOF_VALLEY: "valley",
    ROOF_EAVE: "eave",
    ROOF_RAKE: "edge",
}


def configure_layers(doc) -> None:
    """Create the roof-review layers on an ezdxf document."""
    existing = {layer.dxf.name for layer in doc.layers}
    for spec in ALL_LAYER_SPECS:
        if spec.name not in existing:
            doc.layers.add(spec.name, color=spec.color)
