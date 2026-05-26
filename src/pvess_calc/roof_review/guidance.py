"""Review-only PV placement guidance for CAD roof review."""
from __future__ import annotations

import math
from typing import Any

from ..calc.engine import CalculationResult


def orientation_priority(azimuth_deg: float | int | str | None) -> dict[str, Any]:
    """Classify roof face azimuth for PV placement review.

    PVESS azimuth convention is 0/360 = north, 90 = east, 180 = south,
    270 = west. This policy follows the current business preference:
    southwest first, east second, north avoided.
    """
    try:
        az = float(azimuth_deg) % 360.0
    except (TypeError, ValueError):
        return {
            "rank": 9,
            "code": "UNKNOWN",
            "label": "Unknown azimuth",
            "color": "#64748b",
            "dxf_color": 8,
            "install_guidance": "survey required",
        }
    if 205.0 <= az <= 250.0:
        return {
            "rank": 1,
            "code": "SW_TARGET",
            "label": "P1 Southwest target",
            "color": "#16a34a",
            "dxf_color": 3,
            "install_guidance": "prefer modules here",
        }
    if 70.0 <= az <= 115.0:
        return {
            "rank": 2,
            "code": "EAST_SECONDARY",
            "label": "P2 East secondary",
            "color": "#2563eb",
            "dxf_color": 5,
            "install_guidance": "use after southwest",
        }
    if 150.0 <= az < 205.0 or 250.0 < az <= 285.0:
        return {
            "rank": 3,
            "code": "SOUTH_WEST_USABLE",
            "label": "P3 South/west usable",
            "color": "#ca8a04",
            "dxf_color": 2,
            "install_guidance": "usable if P1/P2 area is insufficient",
        }
    if az >= 315.0 or az <= 45.0:
        return {
            "rank": 5,
            "code": "NORTH_AVOID",
            "label": "P5 North avoid",
            "color": "#dc2626",
            "dxf_color": 1,
            "install_guidance": "avoid modules unless explicitly approved",
        }
    return {
        "rank": 4,
        "code": "REVIEW_ONLY",
        "label": "P4 Review only",
        "color": "#f97316",
        "dxf_color": 30,
        "install_guidance": "manual production review",
    }


def build_face_priority_sections(raw_sections: Any) -> list[dict[str, Any]]:
    sections = list(raw_sections or [])
    out: list[dict[str, Any]] = []
    for idx, raw in enumerate(sections, start=1):
        if not isinstance(raw, dict):
            if hasattr(raw, "model_dump"):
                raw = raw.model_dump(mode="json")
            else:
                continue
        priority = orientation_priority(raw.get("azimuth_deg"))
        out.append({
            "index": idx,
            "name": str(raw.get("name") or f"Face {idx}"),
            "azimuth_deg": raw.get("azimuth_deg"),
            "pitch_deg": raw.get("pitch_deg"),
            "width_ft": raw.get("width_ft"),
            "height_ft": raw.get("height_ft"),
            "priority": priority,
        })
    out.sort(key=lambda item: (
        item["priority"]["rank"],
        -float(item.get("width_ft") or 0.0) * float(item.get("height_ft") or 0.0),
        item["index"],
    ))
    return out


def build_obstruction_zones(result: CalculationResult) -> list[dict[str, Any]]:
    zones: list[dict[str, Any]] = []
    trace = result.inputs.site.ee4_trace
    for idx, symbol in enumerate(trace.symbols, start=1):
        radius = _symbol_radius_ft(symbol.kind)
        zones.append({
            "index": idx,
            "kind": symbol.kind,
            "x_ft": float(symbol.x_ft),
            "y_ft": float(symbol.y_ft),
            "radius_ft": radius,
            "source": "site.ee4_trace.symbols",
            "note": _zone_note(symbol.kind),
        })

    for section in result.inputs.site.roof_sections:
        if section.site_anchor_x_ft is None or section.site_anchor_y_ft is None:
            continue
        theta = math.radians(section.site_anchor_azimuth_deg)
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        for obs in section.obstructions:
            x = (
                float(section.site_anchor_x_ft)
                + float(obs.x_ft) * cos_t
                - float(obs.y_ft) * sin_t
            )
            y = (
                float(section.site_anchor_y_ft)
                + float(obs.x_ft) * sin_t
                + float(obs.y_ft) * cos_t
            )
            radius = max(float(obs.width_ft), float(obs.height_ft)) / 2.0
            radius += max(float(obs.setback_ft), 0.0)
            zones.append({
                "index": len(zones) + 1,
                "kind": obs.kind,
                "x_ft": x,
                "y_ft": y,
                "radius_ft": max(radius, 1.0),
                "source": f"site.roof_sections[{section.name}].obstructions",
                "note": _zone_note(obs.kind),
            })
    return zones


def _symbol_radius_ft(kind: str) -> float:
    if kind == "chimney":
        return 4.0
    if kind in {"ac", "satellite", "mast"}:
        return 3.0
    return 2.0


def _zone_note(kind: str) -> str:
    if kind == "chimney":
        return "chimney no-panel zone; redraw verified outline on ROOF_OBSTRUCTION"
    return "obstruction clearance zone; verify before module placement"
