"""R8 staged roof/layout validation artifacts for the web review flow."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from ..calc.engine import CalculationResult
from .cover_maps import (
    coordinates_to_lat_lng,
    fetch_google_static_satellite,
    fetch_satellite_assets_cached,
)
from .ee4_review import render_ee4_review
from .ee4_trace_modules import ee4_module_count
from .roof_trace_status import assess_roof_trace_status
from .satellite_roof_outline import write_satellite_roof_outline_artifacts
from .structural import render_attachment_plan
from .trace_module_layout_status import assess_trace_module_layout_status


PDFTOPPM_CANDIDATES = (
    Path("/opt/homebrew/bin/pdftoppm"),
    Path("/usr/local/bin/pdftoppm"),
    Path("/usr/bin/pdftoppm"),
)
# Keep the paid dataLayers request compatible with the existing service cache.
# The review image itself is tightened by `crop_satellite_assets_to_target()`.
R8_SATELLITE_RADIUS_M = 35.0


def write_r8_validation_artifacts(
    result: CalculationResult,
    output_dir: Path,
    *,
    satellite_crop_mode: str = "tight",
    allow_paid_satellite: bool = False,
) -> dict[str, Any]:
    """Write step-by-step visual diagnostics for address/roof/layout review."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    status = build_r8_validation_status(result)

    satellite_path = output_dir / "r8-step-2-satellite-review.png"
    status["satellite_crop_mode"] = _normalized_crop_mode(satellite_crop_mode)
    satellite_status = _write_satellite_review_png(
        result,
        satellite_path,
        crop_mode=satellite_crop_mode,
        allow_network=allow_paid_satellite,
    )
    status["steps"][1].update(satellite_status)
    satellite_outline_artifacts = write_satellite_roof_outline_artifacts(
        result,
        output_dir,
        radius_m=R8_SATELLITE_RADIUS_M,
        allow_network=allow_paid_satellite,
    )
    satellite_outline_status = satellite_outline_artifacts["status"]
    status["satellite_roof_outline"] = satellite_outline_status
    _merge_step_artifact(status["steps"][1], {
        "status": str(satellite_outline_status.get("status") or "WARN"),
        "artifact": satellite_status.get("artifact", satellite_path.name),
        "preview": satellite_status.get("preview", satellite_path.name),
        "detail": str(satellite_outline_status.get("detail") or ""),
    })
    google_static_satellite_path: Path | None = None
    google_static_status: dict[str, str] = {
        "status": "SKIPPED",
        "detail": "Google Static satellite fallback not needed.",
        "artifact": "",
        "preview": "",
    }
    if (
        allow_paid_satellite
        and str(satellite_outline_status.get("status") or "") != "PASS"
    ):
        google_static_satellite_path = (
            output_dir / "r8-step-2-google-static-satellite.png"
        )
        google_static_status = _write_google_static_satellite_png(
            result,
            google_static_satellite_path,
        )
        status["google_static_satellite"] = google_static_status
        outline_detail = str(satellite_outline_status.get("detail") or "").strip()
        static_detail = str(google_static_status.get("detail") or "").strip()
        combined_detail = " ".join(
            part for part in (outline_detail, static_detail) if part
        )
        _merge_step_artifact(status["steps"][1], {
            "status": "WARN",
            "artifact": (
                google_static_satellite_path.name
                if google_static_status.get("status") == "PASS"
                else satellite_status.get("artifact", satellite_path.name)
            ),
            "preview": (
                google_static_satellite_path.name
                if google_static_status.get("status") == "PASS"
                else satellite_status.get("preview", satellite_path.name)
            ),
            "detail": combined_detail,
        })
    else:
        status["google_static_satellite"] = google_static_status

    roof_pdf = output_dir / "r8-step-3-roof-trace-layout.pdf"
    roof_png = output_dir / "r8-step-3-roof-trace-layout.png"
    render_ee4_review(result, roof_pdf)
    roof_png_written = _rasterize_pdf_page(roof_pdf, roof_png)
    _merge_step_artifact(status["steps"][2], {
        "artifact": roof_pdf.name,
        "preview": roof_png_written.name if roof_png_written else "",
        "status": "PASS" if roof_png_written else "WARN",
        "detail": (
            "Roof trace and module overlay preview generated."
            if roof_png_written
            else "Roof trace PDF generated; PNG preview unavailable."
        ),
    })

    attachment_pdf = output_dir / "r8-step-4-panel-attachment-layout.pdf"
    attachment_png = output_dir / "r8-step-4-panel-attachment-layout.png"
    render_attachment_plan(result, attachment_pdf)
    attachment_png_written = _rasterize_pdf_page(attachment_pdf, attachment_png)
    _merge_step_artifact(status["steps"][3], {
        "artifact": attachment_pdf.name,
        "preview": attachment_png_written.name if attachment_png_written else "",
        "status": "PASS" if attachment_png_written else "WARN",
        "detail": (
            "Panel attachment layout preview generated."
            if attachment_png_written
            else "Panel attachment PDF generated; PNG preview unavailable."
        ),
    })

    status["overall_status"] = _overall_status(status["steps"])

    status_json = output_dir / "r8-validation-status.json"
    status_json.write_text(
        json.dumps(status, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    status_md = output_dir / "r8-validation-guide.md"
    status_md.write_text(
        format_r8_validation_markdown(status),
        encoding="utf-8",
    )

    return {
        "status": status,
        "status_json": status_json,
        "status_markdown": status_md,
        "satellite_png": satellite_path,
        "satellite_audit_json": satellite_outline_artifacts["audit_json"],
        "satellite_audit_markdown": satellite_outline_artifacts["audit_markdown"],
        "satellite_outline_json": satellite_outline_artifacts["candidate_json"],
        "satellite_outline_yaml": satellite_outline_artifacts["candidate_yaml"],
        "satellite_outline_png": satellite_outline_artifacts["candidate_png"],
        "google_static_satellite_png": (
            google_static_satellite_path
            if (
                google_static_satellite_path is not None
                and google_static_status.get("status") == "PASS"
                and google_static_satellite_path.exists()
            )
            else None
        ),
        "roof_pdf": roof_pdf,
        "roof_png": roof_png_written,
        "attachment_pdf": attachment_pdf,
        "attachment_png": attachment_png_written,
    }


def build_r8_validation_status(result: CalculationResult) -> dict[str, Any]:
    inputs = result.inputs
    roof_trace = assess_roof_trace_status(result)
    trace_layout = assess_trace_module_layout_status(result)
    lat_lng = coordinates_to_lat_lng(inputs.project.coordinates)
    address_status = "PASS" if inputs.project.site_address and lat_lng else "WARN"
    segment_warning = _roof_segment_warning(result)
    roof_step_status = (
        "WARN" if segment_warning
        else ("PASS" if roof_trace.get("can_ahj_ready") else "WARN")
    )
    roof_step_detail = segment_warning or str(roof_trace.get("detail", ""))
    issue_detail = _issue_hint(roof_trace, trace_layout, segment_warning)
    steps = [
        {
            "step": 1,
            "title": "Confirm input address",
            "status": address_status,
            "artifact": "",
            "preview": "",
            "detail": (
                f"{inputs.project.site_address} · {inputs.project.coordinates}"
                if lat_lng else
                "Address or coordinates are missing; confirm before roof review."
            ),
        },
        {
            "step": 2,
            "title": "Review satellite image",
            "status": "WARN",
            "artifact": "r8-step-2-satellite-review.png",
            "preview": "r8-step-2-satellite-review.png",
            "detail": "Satellite review image pending.",
        },
        {
            "step": 3,
            "title": "Review roof trace overlay",
            "status": roof_step_status,
            "artifact": "",
            "preview": "",
            "detail": roof_step_detail,
        },
        {
            "step": 4,
            "title": "Review panel and attachment layout",
            "status": "PASS" if trace_layout.get("can_ahj_ready") else "WARN",
            "artifact": "",
            "preview": "",
            "detail": trace_layout.get("detail", ""),
        },
        {
            "step": 5,
            "title": "Locate the issue",
            "status": "PASS" if (
                not segment_warning
                and
                roof_trace.get("can_ahj_ready")
                and trace_layout.get("can_ahj_ready")
            ) else "WARN",
            "artifact": "",
            "preview": "",
            "detail": issue_detail,
        },
    ]
    return {
        "overall_status": _overall_status(steps),
        "project_id": inputs.project.id,
        "project_name": inputs.project.name,
        "address": inputs.project.site_address,
        "coordinates": inputs.project.coordinates,
        "roof_section_count": len(inputs.site.roof_sections),
        "trace_active": bool(inputs.site.ee4_trace.enabled),
        "target_modules": int(inputs.pv_array.modules),
        "placed_modules": ee4_module_count(result) if inputs.site.ee4_trace.enabled else sum(
            len(modules) for modules in result.module_placements.values()
        ),
        "roof_trace": roof_trace,
        "trace_module_layout": trace_layout,
        "roof_segment_warning": segment_warning,
        "google_static_satellite": {
            "status": "SKIPPED",
            "detail": "Google Static satellite fallback has not run.",
            "artifact": "",
            "preview": "",
        },
        "steps": steps,
    }


def format_r8_validation_markdown(status: dict[str, Any]) -> str:
    lines = [
        "# R8 Step-by-Step Validation",
        "",
        f"- Project: {status.get('project_name', '')}",
        f"- Address: {status.get('address', '')}",
        f"- Coordinates: {status.get('coordinates', '')}",
        f"- Overall status: **{status.get('overall_status', 'UNKNOWN')}**",
        "",
        "| Step | Check | Status | What to inspect |",
        "|---:|---|---|---|",
    ]
    for step in status.get("steps", []):
        title = str(step.get("title", ""))
        detail = str(step.get("detail", "")).replace("\n", " ")
        lines.append(
            f"| {step.get('step', '')} | {title} | "
            f"{step.get('status', '')} | {detail} |"
        )
    lines.extend([
        "",
        "## Review Order",
        "",
        "1. Confirm the address and coordinates match the real project.",
        "2. Compare the satellite image to the intended property.",
        "3. Check whether the traced roof outline matches the satellite roof.",
        "4. Check panel placement against the traced outline and fire pathways.",
        "5. If the generated package is wrong, use the first failed step as the fix target.",
        "",
    ])
    return "\n".join(lines)


def _write_satellite_review_png(
    result: CalculationResult,
    out_path: Path,
    *,
    crop_mode: str = "tight",
    allow_network: bool = False,
) -> dict[str, str]:
    lat_lng = coordinates_to_lat_lng(result.inputs.project.coordinates)
    if lat_lng is None:
        _write_placeholder_png(
            out_path,
            title="Satellite image unavailable",
            lines=[
                "Project coordinates are missing or invalid.",
                "Confirm the U.S. address and geocode before roof review.",
            ],
        )
        return {
            "status": "WARN",
            "artifact": out_path.name,
            "preview": out_path.name,
            "detail": "Satellite image unavailable because coordinates are missing.",
        }
    try:
        assets = fetch_satellite_assets_cached(
            *lat_lng,
            radius_m=R8_SATELLITE_RADIUS_M,
            cache=True,
            allow_network=(
                bool(allow_network)
                or _truthy_env("PVESS_R8_ALLOW_PAID_RENDERS")
                or _truthy_env("PVESS_ALLOW_PAID_RENDERS")
            ),
        )
    except Exception as exc:
        assets = None
        error = str(exc)[:160]
    else:
        error = ""

    if assets is None:
        _write_placeholder_png(
            out_path,
            title="Satellite image unavailable",
            lines=[
                "Google Solar imagery was not returned for this address.",
                error or "Check API coverage, key, billing, or network access.",
            ],
        )
        return {
            "status": "WARN",
            "artifact": out_path.name,
            "preview": out_path.name,
            "detail": "Satellite image unavailable; use the roof trace preview and field evidence.",
        }

    try:
        from ..customer.roof_satellite import (
            crop_satellite_assets_to_target,
            render_satellite_diagram,
        )

        sections = [
            section.model_dump(mode="json")
            for section in result.inputs.site.roof_sections
        ]
        review_assets = _crop_satellite_assets_for_mode(assets, crop_mode)
        if sections:
            render_satellite_diagram(
                sections,
                review_assets,
                out_path,
                title=f"Satellite review — {result.inputs.project.site_address}",
                subtitle=(
                    f"imagery {assets.imagery_date}, "
                    f"{assets.imagery_quality} · {crop_mode_label(crop_mode)} · red = target lat/lng"
                ),
                urban_density=result.inputs.site.urban_density,
                dpi=150,
            )
        else:
            Image.fromarray(review_assets.rgb, mode="RGB").save(out_path)
    except Exception as exc:
        _write_placeholder_png(
            out_path,
            title="Satellite render failed",
            lines=[
                "Imagery was fetched but could not be rendered.",
                str(exc)[:160],
            ],
        )
        return {
            "status": "WARN",
            "artifact": out_path.name,
            "preview": out_path.name,
            "detail": "Satellite imagery fetched but render failed.",
        }

    return {
        "status": "PASS",
        "artifact": out_path.name,
        "preview": out_path.name,
        "detail": (
            f"Satellite review generated from Google Solar imagery "
            f"{assets.imagery_date} ({assets.imagery_quality}); "
            f"{crop_mode_label(crop_mode)} applied."
        ),
    }


def _write_google_static_satellite_png(
    result: CalculationResult,
    out_path: Path,
) -> dict[str, str]:
    lat_lng = coordinates_to_lat_lng(result.inputs.project.coordinates)
    if lat_lng is None:
        return {
            "status": "WARN",
            "artifact": "",
            "preview": "",
            "detail": (
                "Google Static satellite fallback skipped because project "
                "coordinates are missing."
            ),
        }

    static = fetch_google_static_satellite(*lat_lng, cache=True, allow_network=True)
    if static.status != "PASS" or not static.png_bytes:
        return {
            "status": "WARN",
            "artifact": "",
            "preview": "",
            "detail": static.detail,
        }

    try:
        import io

        image = Image.open(io.BytesIO(static.png_bytes)).convert("RGB")
        _draw_static_satellite_marker(image)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(out_path, format="PNG")
    except Exception as exc:
        return {
            "status": "WARN",
            "artifact": "",
            "preview": "",
            "detail": f"Google Static satellite fallback fetched but render failed: {exc}",
        }

    return {
        "status": "PASS",
        "artifact": out_path.name,
        "preview": out_path.name,
        "detail": (
            f"{static.detail} If Google Solar mask is empty, compare this "
            "image against the address and trace the roof manually."
        ),
    }


def _draw_static_satellite_marker(image: Image.Image) -> None:
    draw = ImageDraw.Draw(image)
    w, h = image.size
    cx, cy = w / 2.0, h / 2.0
    radius = max(18, min(w, h) * 0.055)
    cross = max(12, min(w, h) * 0.03)
    red = "#dc2626"
    draw.ellipse(
        (cx - radius, cy - radius, cx + radius, cy + radius),
        outline=red,
        width=max(3, int(min(w, h) * 0.004)),
    )
    draw.line((cx - cross, cy, cx + cross, cy), fill=red, width=3)
    draw.line((cx, cy - cross, cx, cy + cross), fill=red, width=3)
    label_font = _font(size=max(18, int(min(w, h) * 0.022)), bold=True)
    label = "Google satellite visual fallback - manual trace only"
    padding = 12
    try:
        bbox = draw.textbbox((0, 0), label, font=label_font)
        label_w = bbox[2] - bbox[0]
        label_h = bbox[3] - bbox[1]
    except Exception:
        label_w = len(label) * 10
        label_h = 22
    draw.rectangle(
        (padding, padding, padding + label_w + 18, padding + label_h + 14),
        fill=(255, 255, 255),
        outline="#334155",
        width=2,
    )
    draw.text((padding + 9, padding + 7), label, fill="#111827", font=label_font)


def _crop_satellite_assets_for_mode(assets, crop_mode: str):
    from ..customer.roof_satellite import crop_satellite_assets_to_target

    mode = _normalized_crop_mode(crop_mode)
    if mode == "wide":
        return assets
    if mode == "target":
        return crop_satellite_assets_to_target(
            assets,
            padding_ratio=0.06,
            min_padding_px=5,
            min_side_px=44,
        )
    if mode == "standard":
        return crop_satellite_assets_to_target(
            assets,
            padding_ratio=0.35,
            min_padding_px=18,
            min_side_px=96,
        )
    return crop_satellite_assets_to_target(
        assets,
        padding_ratio=0.20,
        min_padding_px=12,
        min_side_px=72,
    )


def crop_mode_label(crop_mode: str) -> str:
    mode = _normalized_crop_mode(crop_mode)
    if mode == "target":
        return "target roof only crop"
    if mode == "wide":
        return "wide satellite context"
    if mode == "standard":
        return "standard target crop"
    return "tight target crop"


def _normalized_crop_mode(crop_mode: str) -> str:
    mode = str(crop_mode or "tight").strip().lower()
    return mode if mode in {"target", "tight", "standard", "wide"} else "tight"


def _write_placeholder_png(out_path: Path, *, title: str, lines: list[str]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (1400, 900), "white")
    draw = ImageDraw.Draw(img)
    title_font = _font(size=48, bold=True)
    body_font = _font(size=30, bold=False)
    draw.rectangle((40, 40, 1360, 860), outline="#CBD5E1", width=3)
    draw.text((90, 110), title, fill="#1F2937", font=title_font)
    y = 220
    for line in lines:
        draw.text((90, y), line, fill="#475569", font=body_font)
        y += 52
    draw.text(
        (90, 760),
        "R8 validation continues with roof trace and panel layout previews.",
        fill="#64748B",
        font=body_font,
    )
    img.save(out_path)


def _font(*, size: int, bold: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _rasterize_pdf_page(pdf_path: Path, png_path: Path) -> Path | None:
    pdftoppm = _find_pdftoppm()
    if pdftoppm is None:
        return None
    png_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as td:
        prefix = Path(td) / "r8-preview"
        try:
            subprocess.run(
                [
                    pdftoppm,
                    "-png",
                    "-singlefile",
                    "-r",
                    "144",
                    str(pdf_path),
                    str(prefix),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None
        generated = prefix.with_suffix(".png")
        if not generated.exists():
            return None
        shutil.move(str(generated), str(png_path))
    return png_path


def _find_pdftoppm() -> str | None:
    found = shutil.which("pdftoppm")
    if found:
        return found
    for candidate in PDFTOPPM_CANDIDATES:
        if candidate.is_file():
            return str(candidate)
    return None


def _overall_status(steps: list[dict[str, Any]]) -> str:
    statuses = {str(step.get("status", "")) for step in steps}
    if "FAIL" in statuses:
        return "FAIL"
    if "WARN" in statuses:
        return "WARN"
    return "PASS"


def _merge_step_artifact(step: dict[str, Any], artifact: dict[str, str]) -> None:
    current_status = str(step.get("status") or "PASS")
    artifact_status = str(artifact.get("status") or "PASS")
    step["status"] = _worse_status(current_status, artifact_status)
    existing_detail = str(step.get("detail") or "").strip()
    artifact_detail = str(artifact.get("detail") or "").strip()
    if existing_detail and artifact_detail and existing_detail != artifact_detail:
        step["detail"] = f"{existing_detail} {artifact_detail}"
    elif artifact_detail:
        step["detail"] = artifact_detail
    step["artifact"] = artifact.get("artifact", step.get("artifact", ""))
    step["preview"] = artifact.get("preview", step.get("preview", ""))


def _worse_status(a: str, b: str) -> str:
    rank = {"PASS": 0, "WARN": 1, "FAIL": 2}
    return a if rank.get(a, 1) >= rank.get(b, 1) else b


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _issue_hint(
    roof_trace: dict[str, Any],
    trace_layout: dict[str, Any],
    segment_warning: str = "",
) -> str:
    if segment_warning:
        return f"The first likely issue is roof geometry: {segment_warning}"
    if not roof_trace.get("can_ahj_ready"):
        return (
            "The first likely issue is roof geometry: "
            f"{roof_trace.get('required_action') or roof_trace.get('detail')}"
        )
    if not trace_layout.get("can_ahj_ready"):
        return (
            "The first likely issue is panel layout: "
            f"{trace_layout.get('required_action') or trace_layout.get('detail')}"
        )
    return "Address, roof trace, and panel layout checks are internally consistent."


def _roof_segment_warning(result: CalculationResult) -> str:
    sections = result.inputs.site.roof_sections
    if len(sections) <= 8:
        return ""
    placed_faces = sum(
        1 for section in sections
        if result.module_placements.get(section.name)
    )
    return (
        f"Google Solar lookup produced {len(sections)} roof segment boxes "
        f"({placed_faces} with modules). This is useful source data, but it "
        "is not a reviewed roof outline. Manually trace the real continuous "
        "roof outline from the satellite image before treating PV-1 / EE-4 "
        "as AHJ-ready."
    )
