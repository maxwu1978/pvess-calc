#!/usr/bin/env python3
"""Generate a reviewable PVESS EE-4 roof topology proposal.

This script is intentionally deterministic by default. A vision model may
produce the `--vision-json` input, but PVESS still validates and renders the
proposal with its own geometry pipeline.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import ssl
import sys
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request

import yaml


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pvess_calc.calc.engine import run  # noqa: E402
from pvess_calc.permit.ee4_review import render_ee4_review  # noqa: E402
from pvess_calc.permit.ee4_trace import (  # noqa: E402
    build_ee4_trace_skeleton,
    complete_ee4_trace_for_review,
    ee4_trace_yaml,
)
from pvess_calc.permit.ee4_trace_modules import ee4_module_count  # noqa: E402
from pvess_calc.permit.roof_trace_status import assess_roof_trace_status  # noqa: E402
from pvess_calc.permit.trace_module_layout_status import (  # noqa: E402
    assess_trace_module_layout_status,
)
from pvess_calc.schema import EE4Trace, Inputs  # noqa: E402
from pvess_calc.web.server import WebProjectRequest, build_inputs_data  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate PVESS roof topology proposal artifacts."
    )
    parser.add_argument(
        "--job-dir",
        required=True,
        type=Path,
        help="PVESS web job/project directory containing request.json.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Artifact directory. Defaults to <job-dir>/output/roof-topology-vision.",
    )
    parser.add_argument(
        "--vision-json",
        type=Path,
        help="Optional vision-model JSON matching references/output_schema.md.",
    )
    parser.add_argument(
        "--openai-image",
        type=Path,
        help=(
            "Optional satellite crop/review image. When provided, call the "
            "OpenAI Responses API to draft topology JSON."
        ),
    )
    parser.add_argument(
        "--openai-model",
        default=os.environ.get("PVESS_ROOF_TOPOLOGY_OPENAI_MODEL", "auto"),
        help="Vision-capable OpenAI model for --openai-image, or auto.",
    )
    parser.add_argument(
        "--no-png",
        action="store_true",
        help="Skip PNG rasterization and write only the EE-4 review PDF.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero when the generated topology is not AHJ-ready.",
    )
    args = parser.parse_args(argv)

    job_dir = args.job_dir.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else job_dir / "output" / "roof-topology-vision"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = _load_request(job_dir / "request.json")
    trace, source, warnings = _select_trace(
        job_dir,
        payload,
        args.vision_json,
        args.openai_image,
        args.openai_model,
    )
    trace = complete_ee4_trace_for_review(trace)
    if not trace.enabled:
        trace = trace.model_copy(update={"enabled": True})

    proposed_payload = payload.model_copy(update={
        "ee4_trace": trace,
        "ee4_trace_reviewed": True,
    })
    project_id = proposed_payload.project_id or job_dir.name
    inputs_data = build_inputs_data(proposed_payload, project_id=project_id)
    inputs = Inputs.model_validate(inputs_data)
    result = run(inputs, ahj_profile=proposed_payload.ahj_profile or None)

    trace_yaml = output_dir / "site-ee4-trace-proposed.yaml"
    trace_yaml.write_text(ee4_trace_yaml(trace), encoding="utf-8")

    pdf_path = output_dir / "roof-topology-review.pdf"
    png_path = None if args.no_png else output_dir / "roof-topology-review.png"
    png_error = ""
    try:
        artifacts = render_ee4_review(result, pdf_path, png_path=png_path)
        png_written = artifacts.png_path
    except RuntimeError as exc:
        if args.no_png:
            raise
        png_error = str(exc)
        artifacts = render_ee4_review(result, pdf_path)
        png_written = None

    roof_status = assess_roof_trace_status(result)
    layout_status = assess_trace_module_layout_status(result)
    target_modules = int(result.inputs.pv_array.modules)
    placed_modules = int(ee4_module_count(result))
    ahj_ready = bool(
        roof_status.get("can_ahj_ready")
        and layout_status.get("can_ahj_ready")
        and placed_modules == target_modules
    )

    qa = {
        "status": "PASS" if ahj_ready else "FAIL",
        "source": source,
        "model_mode": _model_mode(source, bool(args.vision_json), bool(args.openai_image)),
        "project_id": project_id,
        "target_modules": target_modules,
        "placed_modules": placed_modules,
        "ahj_ready": ahj_ready,
        "roof_trace": roof_status,
        "trace_module_layout": layout_status,
        "artifacts": {
            "trace_yaml": str(trace_yaml),
            "review_pdf": str(artifacts.pdf_path),
            "review_png": str(png_written) if png_written else "",
        },
        "warnings": warnings + ([png_error] if png_error else []),
    }
    qa_json = output_dir / "roof-topology-qa.json"
    qa_json.write_text(
        json.dumps(qa, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    qa_md = output_dir / "roof-topology-qa.md"
    qa_md.write_text(_qa_markdown(qa), encoding="utf-8")

    print(f"status={qa['status']}")
    print(f"source={source}")
    print(f"trace_yaml={trace_yaml}")
    print(f"review_pdf={artifacts.pdf_path}")
    if png_written:
        print(f"review_png={png_written}")
    if png_error:
        print(f"png_warning={png_error}")
    print(f"qa_json={qa_json}")

    return 1 if args.strict and not ahj_ready else 0


def _load_request(path: Path) -> WebProjectRequest:
    if not path.exists():
        raise FileNotFoundError(f"Missing request.json: {path}")
    return WebProjectRequest.model_validate_json(path.read_text(encoding="utf-8"))


def _select_trace(
    job_dir: Path,
    payload: WebProjectRequest,
    vision_json: Path | None,
    openai_image: Path | None,
    model: str,
) -> tuple[EE4Trace, str, list[str]]:
    if vision_json is not None:
        base_trace, _base_source, base_warnings = _select_trace(
            job_dir,
            payload,
            None,
            None,
            model,
        )
        trace = _sanitize_model_trace(_trace_from_yaml_or_json(vision_json), base_trace)
        return trace, "vision_json", base_warnings

    if openai_image is not None:
        try:
            base_trace, _base_source, base_warnings = _select_trace(
                job_dir,
                payload,
                None,
                None,
                model,
            )
            trace = _trace_from_openai_image(
                image_path=openai_image,
                payload=payload,
                base_trace=base_trace,
                model=model,
            )
            return trace, "openai_vision", base_warnings
        except Exception as exc:
            fallback, source, fallback_warnings = _select_trace(
                job_dir,
                payload,
                None,
                None,
                model,
            )
            fallback_warnings.append(
                f"OpenAI vision fallback used after {type(exc).__name__}: {exc}"
            )
            return fallback, source, fallback_warnings

    candidate = job_dir / "output" / "satellite-ee4-trace-candidate.yaml"
    if candidate.exists():
        return _trace_from_yaml_or_json(candidate), "satellite_candidate", []

    if payload.ee4_trace is not None and payload.ee4_trace.has_geometry:
        return payload.ee4_trace, "request_payload", []

    draft = job_dir / "output" / "ee4-trace-draft.yaml"
    if draft.exists():
        return _trace_from_yaml_or_json(draft), "ee4_trace_draft", []

    inputs_data = build_inputs_data(payload, project_id=payload.project_id or job_dir.name)
    result = run(Inputs.model_validate(inputs_data), ahj_profile=payload.ahj_profile or None)
    return build_ee4_trace_skeleton(result), "generated_skeleton", []


def _model_mode(source: str, has_vision_json: bool, has_openai_image: bool) -> str:
    if has_vision_json:
        return "vision_json"
    if source == "openai_vision":
        return "openai_vision"
    if has_openai_image:
        return "deterministic_fallback_after_openai_attempt"
    return "deterministic_fallback"


def _trace_from_openai_image(
    *,
    image_path: Path,
    payload: WebProjectRequest,
    base_trace: EE4Trace,
    model: str,
) -> EE4Trace:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    if not image_path.exists():
        raise FileNotFoundError(f"OpenAI image not found: {image_path}")

    prompt = _openai_prompt(payload, base_trace)
    image_data_url = _image_data_url(image_path)
    errors: list[str] = []
    for resolved_model in _resolve_openai_models(model):
        for endpoint in ("responses", "chat_completions"):
            try:
                if endpoint == "responses":
                    response_data = _post_openai_json(
                        _openai_responses_url(),
                        _responses_body(resolved_model, prompt, image_data_url),
                        api_key,
                    )
                    text = _extract_openai_text(response_data)
                else:
                    response_data = _post_openai_json(
                        _openai_chat_completions_url(),
                        _chat_body(resolved_model, prompt, image_data_url),
                        api_key,
                    )
                    text = _extract_chat_text(response_data)
                data = _parse_json_text(text)
                return _model_trace_from_data(data, base_trace)
            except Exception as exc:
                errors.append(
                    f"{endpoint}/{resolved_model}: {type(exc).__name__}: {exc}"
                )
                continue
    raise RuntimeError("; ".join(errors[:4]))


def _openai_prompt(payload: WebProjectRequest, base_trace: EE4Trace) -> str:
    base_json = json.dumps(
        {"site": {"ee4_trace": base_trace.model_dump(mode="json", exclude_none=True)}},
        ensure_ascii=False,
        indent=2,
    )
    return f"""You are drafting roof topology for a North American residential PV permit sheet.

Return JSON only. No markdown. Use this exact contract:
{{"site": {{"ee4_trace": {{"enabled": true, "roof_outline": {{"name": "...", "vertices": [[x, y], ...]}}, "roof_lines": [{{"kind": "ridge|hip|valley|eave|edge|dormer", "points": [[x, y], [x, y]]}}], "fire_pathways": [{{"name": "...", "vertices": [[x, y], ...]}}], "symbols": [{{"kind": "roof_vent|plumbing|ac|satellite|mast|chimney", "x_ft": 0, "y_ft": 0}}]}}}}}}

Project context:
- Address: {payload.site_address or payload.location}
- PV module target count: {payload.modules}
- Module dimensions: 67.80 in x 44.65 in unless clearly overridden.

Current traced candidate is in site-plan feet. Preserve this coordinate system.
Keep the roof_outline vertices unless the satellite image clearly shows the outline is wrong.
Improve roof_lines using visible ridges, hips, valleys, dormers, and roof plane seams.
Fire pathway polygons should be narrow edge strips only, never a full-roof fill.
Do not include module rectangles; PVESS will place and QA modules deterministically.

Current candidate:
{base_json}
"""


def _image_data_url(image_path: Path) -> str:
    ext = image_path.suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/png")
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _openai_responses_url() -> str:
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    if base.endswith("/responses"):
        return base
    return f"{base}/responses"


def _openai_chat_completions_url() -> str:
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    if base.endswith("/responses"):
        base = base[: -len("/responses")]
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _openai_models_url() -> str:
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    if base.endswith("/responses"):
        base = base[: -len("/responses")]
    return f"{base}/models"


def _resolve_openai_models(requested: str) -> list[str]:
    if requested and requested != "auto":
        return [requested]
    candidates = [
        "gpt-4.1-mini",
        "gpt-4o",
        "gpt-4o-mini",
        "qwen3-vl-plus",
        "qwen3-vl-flash",
        "qwen-vl-max-latest",
        "qwen-vl-plus-latest",
        "qwen-vl-max",
        "qwen-vl-plus",
        "qwen3.5-omni-plus",
    ]
    try:
        request = urllib.request.Request(
            _openai_models_url(),
            headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
            method="GET",
        )
        with urllib.request.urlopen(
            request,
            timeout=30,
            context=_ssl_context(),
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        available = {
            str(item.get("id"))
            for item in payload.get("data", [])
            if isinstance(item, dict)
        }
    except Exception:
        return ["gpt-4.1-mini"]
    ordered = [candidate for candidate in candidates if candidate in available]
    for model_id in sorted(available):
        lower = model_id.lower()
        if (
            ("vl" in lower or "vision" in lower or "omni" in lower)
            and model_id not in ordered
        ):
            ordered.append(model_id)
    return ordered or ["gpt-4.1-mini"]


def _responses_body(model: str, prompt: str, image_data_url: str) -> dict[str, Any]:
    return {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_image",
                        "image_url": image_data_url,
                        "detail": "high",
                    },
                ],
            }
        ],
        "temperature": 0.1,
        "max_output_tokens": 2400,
    }


def _chat_body(model: str, prompt: str, image_data_url: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_data_url},
                    },
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 2400,
    }


def _post_openai_json(
    url: str,
    body: dict[str, Any],
    api_key: str,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=90,
            context=_ssl_context(),
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"OpenAI HTTP {exc.code}: {detail}") from exc


def _ssl_context() -> ssl.SSLContext | None:
    try:
        import certifi  # type: ignore[import-not-found]
    except Exception:
        return None
    return ssl.create_default_context(cafile=certifi.where())


def _extract_openai_text(response_data: dict[str, Any]) -> str:
    direct = response_data.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    parts: list[str] = []
    for item in response_data.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") in {"output_text", "text"}:
                text = content.get("text")
                if isinstance(text, str):
                    parts.append(text)
    text = "\n".join(parts).strip()
    if not text:
        raise ValueError("OpenAI response did not contain output text")
    return text


def _extract_chat_text(response_data: dict[str, Any]) -> str:
    choices = response_data.get("choices") or []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            parts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict)
            ]
            text = "\n".join(part for part in parts if part).strip()
            if text:
                return text
    raise ValueError("Chat completions response did not contain message text")


def _parse_json_text(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(stripped[start:end + 1])


def _trace_from_yaml_or_json(path: Path) -> EE4Trace:
    data = _load_structured(path)
    raw = _extract_trace_payload(data)
    trace = EE4Trace.model_validate(raw)
    if not trace.enabled:
        trace = trace.model_copy(update={"enabled": True})
    return trace


def _load_structured(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def _extract_trace_payload(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Topology payload must be a JSON/YAML object")
    if "site" in data and isinstance(data["site"], dict) and "ee4_trace" in data["site"]:
        raw = data["site"]["ee4_trace"]
    elif "ee4_trace" in data:
        raw = data["ee4_trace"]
    else:
        raw = data
    if not isinstance(raw, dict):
        raise ValueError("Topology payload does not contain an ee4_trace object")
    return raw


def _model_trace_from_data(data: Any, base_trace: EE4Trace) -> EE4Trace:
    raw = dict(_extract_trace_payload(data))
    deterministic_base = complete_ee4_trace_for_review(base_trace)
    if deterministic_base.roof_outline is not None:
        raw["roof_outline"] = deterministic_base.roof_outline.model_dump(
            mode="json",
            exclude_none=True,
        )
    raw["enabled"] = True
    raw["fire_pathways"] = [
        item.model_dump(mode="json", exclude_none=True)
        for item in deterministic_base.fire_pathways
    ]
    raw["symbols"] = []
    return _sanitize_model_trace(EE4Trace.model_validate(raw), base_trace)


def _sanitize_model_trace(trace: EE4Trace, base_trace: EE4Trace) -> EE4Trace:
    """Keep model output useful but bounded by deterministic satellite geometry."""
    outline = base_trace.roof_outline or trace.roof_outline
    if outline is None:
        return trace
    deterministic_base = complete_ee4_trace_for_review(base_trace)
    return trace.model_copy(update={
        "enabled": True,
        "roof_outline": outline,
        "fire_pathways": deterministic_base.fire_pathways,
        "symbols": [],
    })


def _qa_markdown(qa: dict[str, Any]) -> str:
    lines = [
        f"# Roof topology QA — {qa['project_id']}",
        "",
        f"- Status: **{qa['status']}**",
        f"- Source: `{qa['source']}`",
        f"- Mode: `{qa['model_mode']}`",
        f"- Modules: {qa['placed_modules']} / {qa['target_modules']}",
        f"- AHJ-ready: {qa['ahj_ready']}",
        "",
        "## Roof Trace",
        "",
        f"- {qa['roof_trace'].get('status')}: {qa['roof_trace'].get('detail')}",
        "",
        "## Module Layout",
        "",
        (
            f"- {qa['trace_module_layout'].get('status')}: "
            f"{qa['trace_module_layout'].get('detail')}"
        ),
    ]
    if qa.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {item}" for item in qa["warnings"])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
