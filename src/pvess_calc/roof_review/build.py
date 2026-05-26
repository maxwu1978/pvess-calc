"""Build the roof-review package consumed by CAD drafters."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any

from PIL import Image
import yaml

from ..calc.engine import run
from ..lookup import resolve
from ..schema import EE4Trace, Inputs
from .candidates import build_roof_line_candidates
from .dxf_export import render_roof_review_dxf
from .guidance import build_face_priority_sections, build_obstruction_zones
from .preview import write_placeholder_underlay, write_roof_review_preview


def build_roof_review_package(
    project_dir: Path,
    *,
    address: str | None = None,
    allow_paid_satellite: bool = False,
) -> dict[str, Path]:
    """Create the CAD roof-review package under output/roof-review."""
    project_dir = Path(project_dir)
    inputs = Inputs.from_yaml(project_dir / "inputs.yaml")
    result = run(inputs)
    output_dir = project_dir / "output" / "roof-review"
    output_dir.mkdir(parents=True, exist_ok=True)

    lookup_fields: dict[str, Any] = {}
    lookup_note = "No address lookup was requested."
    if address:
        try:
            resolved = resolve(address)
            lookup_fields = resolved.fields
            lookup_note = _lookup_summary(resolved)
        except Exception as exc:
            lookup_note = f"Address lookup failed: {exc!r}"

    satellite_paths = _write_satellite_candidates(
        result,
        output_dir,
        allow_network=allow_paid_satellite,
        pixel_size_m=0.10 if allow_paid_satellite else 0.25,
    )
    candidate_json = output_dir / "roof-mask-outline-candidate.json"
    underlay_placement_json = output_dir / "roof-underlay-placement.json"
    if satellite_paths.get("candidate_json") and satellite_paths["candidate_json"].exists():
        shutil.copyfile(satellite_paths["candidate_json"], candidate_json)
    else:
        candidate_json.write_text(
            json.dumps(
                {
                    "status": "WARN",
                    "detail": (
                        "No cached Google Solar dataLayers mask was available. "
                        "CAD review can proceed from the blank DXF template."
                    ),
                    "candidate": None,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    underlay = output_dir / "roof-underlay.png"
    if satellite_paths.get("candidate_png") and satellite_paths["candidate_png"].exists():
        shutil.copyfile(satellite_paths["candidate_png"], underlay)
        _ensure_min_image_side(underlay, min_side_px=500)
        if (
            satellite_paths.get("candidate_underlay_json")
            and satellite_paths["candidate_underlay_json"].exists()
        ):
            shutil.copyfile(
                satellite_paths["candidate_underlay_json"],
                underlay_placement_json,
            )
            _refresh_underlay_image_size(
                underlay_placement_json,
                image_path=underlay,
            )
    else:
        if not _write_static_satellite_underlay(
            underlay,
            lookup_fields=lookup_fields,
            allow_network=allow_paid_satellite,
        ):
            write_placeholder_underlay(
                underlay,
                title="Roof review underlay unavailable",
                detail=(
                    "No cached paid satellite mask/imagery was available. "
                    "Use CAD aerial reference or field roof report."
                ),
            )
    underlay_placement = _read_json(underlay_placement_json)
    line_candidates_json = output_dir / "roof-line-candidates.json"
    line_candidates = build_roof_line_candidates(
        candidate_json,
        line_candidates_json,
        underlay_path=underlay,
        underlay_placement=underlay_placement,
    )
    face_priorities = build_face_priority_sections(
        lookup_fields.get("roof_sections") or [
            section.model_dump(mode="json")
            for section in result.inputs.site.roof_sections
        ]
    )
    obstruction_zones = build_obstruction_zones(result)
    design_guidance_json = output_dir / "roof-design-guidance.json"
    design_guidance_json.write_text(
        json.dumps(
            {
                "panel_priority_policy": (
                    "Prefer southwest roof faces first, east faces second; "
                    "avoid north-facing faces unless engineering approves."
                ),
                "face_priorities": face_priorities,
                "obstruction_zones": obstruction_zones,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    audit_md = output_dir / "roof-review-audit.md"
    audit_md.write_text(
        _audit_markdown(
            inputs,
            address=address,
            lookup_note=lookup_note,
            lookup_fields=lookup_fields,
            satellite_paths=satellite_paths,
            line_candidates=line_candidates,
            face_priorities=face_priorities,
            obstruction_zones=obstruction_zones,
        ),
        encoding="utf-8",
    )

    review_dxf = output_dir / "roof-review.dxf"
    source_note = _source_note(lookup_fields=lookup_fields, lookup_note=lookup_note)
    satellite_trace = _read_candidate_trace(satellite_paths.get("candidate_yaml"))
    render_roof_review_dxf(
        result,
        review_dxf,
        lookup_roof_sections=lookup_fields.get("roof_sections"),
        candidate_trace=satellite_trace,
        roof_line_candidates=line_candidates,
        face_priorities=face_priorities,
        obstruction_zones=obstruction_zones,
        underlay_image_path=underlay if underlay_placement else None,
        underlay_placement=underlay_placement,
        source_note=source_note,
    )
    review_preview = output_dir / "roof-review.png"
    write_roof_review_preview(
        underlay,
        candidate_json,
        review_preview,
        line_candidates=line_candidates,
        face_priorities=face_priorities,
        obstruction_zones=obstruction_zones,
        underlay_placement=underlay_placement,
    )

    return {
        "output_dir": output_dir,
        "underlay": underlay,
        "candidate_json": candidate_json,
        "line_candidates_json": line_candidates_json,
        "design_guidance_json": design_guidance_json,
        "review_dxf": review_dxf,
        "review_preview": review_preview,
        "audit_markdown": audit_md,
    }


def _write_satellite_candidates(
    result,
    output_dir: Path,
    *,
    allow_network: bool,
    pixel_size_m: float,
) -> dict[str, Path]:
    """Reuse satellite outline code; network calls are explicit opt-in."""
    try:
        from ..permit.satellite_roof_outline import (
            write_satellite_roof_outline_artifacts,
        )

        artifacts = write_satellite_roof_outline_artifacts(
            result,
            output_dir,
            radius_m=25.0,
            pixel_size_m=pixel_size_m,
            allow_network=allow_network,
        )
        paths: dict[str, Path] = {}
        for key in (
            "candidate_json",
            "candidate_png",
            "candidate_yaml",
            "candidate_underlay_json",
            "audit_markdown",
        ):
            value = artifacts.get(key)
            if isinstance(value, Path):
                paths[key] = value
        return paths
    except Exception:
        return {}


def _audit_markdown(
    inputs: Inputs,
    *,
    address: str | None,
    lookup_note: str,
    lookup_fields: dict[str, Any],
    satellite_paths: dict[str, Path],
    line_candidates: dict[str, Any],
    face_priorities: list[dict[str, Any]],
    obstruction_zones: list[dict[str, Any]],
) -> str:
    lines = [
        "# Roof CAD Review Audit",
        "",
        f"- Project: {inputs.project.id} - {inputs.project.name}",
        f"- Address argument: {address or '-'}",
        f"- Project address: {inputs.project.site_address or inputs.project.location or '-'}",
        f"- Coordinates: {inputs.project.coordinates or '-'}",
        f"- Lookup: {lookup_note}",
        "",
        "## Generated Files",
        "",
        "- roof-review.dxf: CAD review template.",
        "- roof-review.png: human preview of the review underlay and candidates.",
        "- roof-underlay.png: satellite/mask preview when cached; placeholder otherwise.",
        "- roof-mask-outline-candidate.json: review-only mask contour candidate.",
        "- roof-line-candidates.json: review-only ridge/hip/valley starter lines.",
        "- roof-design-guidance.json: face orientation priority and no-panel zones.",
        "",
        "## Lookup Fields",
        "",
    ]
    if not lookup_fields:
        lines.append("- none")
    else:
        for key in sorted(lookup_fields):
            value = lookup_fields[key]
            if key == "roof_sections":
                value = f"{len(value)} face(s)"
            lines.append(f"- {key}: {value}")
    lines.extend([
        "",
        "## CAD Import Contract",
        "",
        "- Draw one closed ROOF_OUTLINE polyline.",
        "- Draw one or more closed ROOF_FACET polylines.",
        "- Optional labels on TEXT_ROOF_LABEL may use NAME=South PITCH=22 AZ=180.",
        "- Do not rely on reference candidate layers until a designer reviews them.",
    ])
    lines.extend([
        "",
        "## Roof-Line Candidates",
        "",
        f"- status: {line_candidates.get('status', '-')}",
        f"- source: {line_candidates.get('source', '-')}",
        f"- method: {line_candidates.get('method', '-')}",
        f"- confidence: {line_candidates.get('confidence', '-')}",
        f"- count: {len(line_candidates.get('lines') or [])}",
        f"- image candidate count: {line_candidates.get('image_candidate_count', '-')}",
        f"- fallback candidate count: {line_candidates.get('fallback_candidate_count', '-')}",
        f"- detail: {line_candidates.get('detail', '-')}",
        "",
        "## Placement Guidance",
        "",
        "- policy: prefer southwest faces first; east second; avoid north.",
        f"- face priority count: {len(face_priorities)}",
        f"- no-panel obstruction zones: {len(obstruction_zones)}",
    ])
    if satellite_paths:
        lines.extend([
            "",
            "## Reused Satellite Artifacts",
            "",
        ])
        for key, path in satellite_paths.items():
            lines.append(f"- {key}: {path}")
    return "\n".join(lines) + "\n"


def _source_note(*, lookup_fields: dict[str, Any], lookup_note: str) -> str:
    if lookup_fields.get("roof_sections"):
        return f"Candidate faces from lookup: {lookup_note}"
    return "Blank CAD review template; draw reviewed roof geometry manually."


def _ensure_min_image_side(path: Path, *, min_side_px: int) -> None:
    try:
        with Image.open(path) as img:
            w, h = img.size
            longest = max(w, h)
            if longest >= min_side_px or longest <= 0:
                return
            scale = min_side_px / longest
            resized = img.resize(
                (max(1, round(w * scale)), max(1, round(h * scale))),
                Image.Resampling.LANCZOS,
            )
            resized.save(path)
    except Exception:
        return


def _refresh_underlay_image_size(path: Path, *, image_path: Path) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        with Image.open(image_path) as img:
            data["image_size_px"] = [int(img.size[0]), int(img.size[1])]
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        return


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _read_candidate_trace(path: Path | None) -> EE4Trace | None:
    if path is None or not path.exists():
        return None
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return EE4Trace.model_validate(payload["site"]["ee4_trace"])
    except Exception:
        return None


def _write_static_satellite_underlay(
    output_path: Path,
    *,
    lookup_fields: dict[str, Any],
    allow_network: bool,
) -> bool:
    lat = lookup_fields.get("latitude")
    lng = lookup_fields.get("longitude")
    if lat is None or lng is None:
        return False
    try:
        from ..permit.cover_maps import fetch_google_static_satellite_png

        png = fetch_google_static_satellite_png(
            float(lat),
            float(lng),
            allow_network=allow_network,
        )
    except Exception:
        return False
    if not png:
        return False
    output_path.write_bytes(png)
    return True


def _lookup_summary(resolved) -> str:
    notes = [
        result.note for result in resolved.provider_results
        if result.note and result.confidence != "miss"
    ]
    if notes:
        return "; ".join(notes[:3])
    return f"{len(resolved.fields)} field(s) from {resolved.hit_count} provider(s)."
