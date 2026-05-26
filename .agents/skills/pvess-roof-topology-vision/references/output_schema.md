# Roof Topology Vision Output Schema

The model must return JSON only. The preferred shape is:

```json
{
  "site": {
    "ee4_trace": {
      "enabled": true,
      "roof_outline": {
        "name": "Satellite vision roof outline",
        "vertices": [[0, 0], [60, 0], [60, 28], [0, 28]]
      },
      "roof_lines": [
        {"kind": "ridge", "points": [[4, 14], [56, 14]]},
        {"kind": "hip", "points": [[4, 14], [0, 28]]}
      ],
      "fire_pathways": [
        {
          "name": "North roof-edge fire pathway candidate",
          "vertices": [[0, 27], [60, 27], [60, 28], [0, 28]]
        }
      ],
      "symbols": [
        {"kind": "plumbing", "x_ft": 32.5, "y_ft": 16.0}
      ]
    }
  }
}
```

Rules:

- Coordinates are plan-view feet in one local sheet coordinate system.
- When a current `site.ee4_trace` is provided in the prompt, keep that coordinate system and preserve the roof outline unless the image clearly proves it is wrong.
- Polygon vertices must be counterclockwise and non-self-intersecting.
- `roof_outline` is required.
- `roof_lines` should include ridges, hips, valleys, and dormer/eave lines visible in the satellite image.
- `fire_pathways` should be conservative candidate strips along roof edges; do not cover the whole roof.
- `symbols` may include `roof_vent`, `plumbing`, `ac`, `satellite`, `mast`, or `chimney`.
- Do not include PV modules in this JSON. PVESS will place modules and validate count/clearance deterministically.
