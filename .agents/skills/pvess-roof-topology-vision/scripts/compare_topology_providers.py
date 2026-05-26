#!/usr/bin/env python3
"""Compare roof-topology providers and direct drawing output.

This runner intentionally keeps final PVESS drawing generation deterministic.
Providers are only asked for structured topology or an illustrative SVG.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

from openai import OpenAI


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import generate_topology_proposal as proposal  # noqa: E402


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    env_key: str
    base_url_env: str
    default_base_url: str
    model_env: str
    default_model: str
    supports_vision: bool = True


PROVIDERS = [
    ProviderSpec(
        name="openai_gateway",
        env_key="OPENAI_API_KEY",
        base_url_env="OPENAI_BASE_URL",
        default_base_url="https://api.openai.com/v1",
        model_env="PVESS_OPENAI_VISION_MODEL",
        default_model="auto",
    ),
    ProviderSpec(
        name="deepseek",
        env_key="DEEPSEEK_API_KEY",
        base_url_env="DEEPSEEK_BASE_URL",
        default_base_url="https://api.deepseek.com",
        model_env="PVESS_DEEPSEEK_MODEL",
        default_model="deepseek-v4-flash",
    ),
    ProviderSpec(
        name="minimax",
        env_key="MINIMAX_API_KEY",
        base_url_env="MINIMAX_BASE_URL",
        default_base_url="https://api.minimaxi.com/v1",
        model_env="PVESS_MINIMAX_MODEL",
        default_model="MiniMax-M2.7",
        supports_vision=False,
    ),
    ProviderSpec(
        name="kimi",
        env_key="MOONSHOT_API_KEY",
        base_url_env="MOONSHOT_BASE_URL",
        default_base_url="https://api.moonshot.ai/v1",
        model_env="PVESS_KIMI_MODEL",
        default_model="kimi-k2.5",
    ),
    ProviderSpec(
        name="gemini",
        env_key="GEMINI_API_KEY",
        base_url_env="GEMINI_BASE_URL",
        default_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        model_env="PVESS_GEMINI_MODEL",
        default_model="gemini-2.5-flash",
    ),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare model-assisted PVESS roof topology approaches."
    )
    parser.add_argument("--job-dir", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--providers",
        default="openai_gateway,deepseek,minimax,kimi,gemini",
        help="Comma-separated provider names.",
    )
    parser.add_argument(
        "--skip-direct-svg",
        action="store_true",
        help="Only run structured topology comparisons.",
    )
    args = parser.parse_args(argv)

    job_dir = args.job_dir.resolve()
    image_path = args.image.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else job_dir / "output" / "roof-topology-provider-comparison"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = proposal._load_request(job_dir / "request.json")
    base_trace, base_source, base_warnings = proposal._select_trace(
        job_dir,
        payload,
        None,
        None,
        "auto",
    )
    base_trace = proposal.complete_ee4_trace_for_review(base_trace)

    rows: list[dict[str, Any]] = []
    algorithm_dir = output_dir / "algorithm"
    algorithm_result = _run_algorithm_baseline(job_dir, algorithm_dir)
    rows.append(algorithm_result)

    wanted = {item.strip() for item in args.providers.split(",") if item.strip()}
    for spec in PROVIDERS:
        if spec.name not in wanted:
            continue
        rows.append(_run_provider(
            spec=spec,
            job_dir=job_dir,
            image_path=image_path,
            output_dir=output_dir / spec.name,
            payload=payload,
            base_trace=base_trace,
            base_source=base_source,
            base_warnings=base_warnings,
            direct_svg=not args.skip_direct_svg,
        ))

    report_json = output_dir / "provider-comparison.json"
    report_json.write_text(
        json.dumps(rows, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    report_md = output_dir / "provider-comparison.md"
    report_md.write_text(_report_markdown(rows), encoding="utf-8")

    print(f"report={report_md}")
    print(f"json={report_json}")
    for row in rows:
        print(
            f"{row['provider']}: topology={row.get('topology_status')} "
            f"direct={row.get('direct_status')} score={row.get('score')}"
        )
    return 0


def _run_algorithm_baseline(job_dir: Path, output_dir: Path) -> dict[str, Any]:
    start = time.monotonic()
    status = "FAIL"
    error = ""
    try:
        code = proposal.main([
            "--job-dir", str(job_dir),
            "--output-dir", str(output_dir),
            "--strict",
        ])
        if code == 0:
            status = "PASS"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    qa = _load_json(output_dir / "roof-topology-qa.json")
    score = _score_topology(status, qa)
    return {
        "provider": "algorithm",
        "model": "deterministic",
        "base_url": "",
        "topology_status": status,
        "topology_error": error,
        "direct_status": "not_applicable",
        "direct_error": "",
        "score": score,
        "elapsed_s": round(time.monotonic() - start, 2),
        "artifacts": _artifact_paths(output_dir),
        "qa": qa,
        "notes": "No model. Uses satellite mask + deterministic completion/rendering.",
    }


def _run_provider(
    *,
    spec: ProviderSpec,
    job_dir: Path,
    image_path: Path,
    output_dir: Path,
    payload,
    base_trace,
    base_source: str,
    base_warnings: list[str],
    direct_svg: bool,
) -> dict[str, Any]:
    start = time.monotonic()
    output_dir.mkdir(parents=True, exist_ok=True)
    api_key = os.environ.get(spec.env_key)
    base_url = os.environ.get(spec.base_url_env, spec.default_base_url)
    model = os.environ.get(spec.model_env, spec.default_model)
    if not api_key:
        return {
            "provider": spec.name,
            "model": model,
            "base_url": base_url,
            "topology_status": "SKIPPED",
            "topology_error": f"Missing {spec.env_key}",
            "direct_status": "SKIPPED",
            "direct_error": f"Missing {spec.env_key}",
            "score": 0,
            "elapsed_s": round(time.monotonic() - start, 2),
            "artifacts": {},
            "qa": {},
            "notes": "Provider key not present in environment.",
        }
    if not spec.supports_vision:
        return {
            "provider": spec.name,
            "model": model,
            "base_url": base_url,
            "topology_status": "SKIPPED",
            "topology_error": "Provider OpenAI-compatible chat endpoint does not support image input.",
            "direct_status": "SKIPPED",
            "direct_error": "Provider OpenAI-compatible chat endpoint does not support image input.",
            "score": 0,
            "elapsed_s": round(time.monotonic() - start, 2),
            "artifacts": {},
            "qa": {},
            "notes": "Skipped for rooftop vision comparison; use text-only tasks or a provider-specific image API.",
        }

    provider_model = _resolve_model_for_provider(spec, api_key, base_url, model)
    topology_status = "FAIL"
    topology_error = ""
    direct_status = "not_run"
    direct_error = ""
    try:
        trace, raw_text = _call_structured_topology(
            api_key=api_key,
            base_url=base_url,
            model=provider_model,
            image_path=image_path,
            payload=payload,
            base_trace=base_trace,
        )
        (output_dir / "structured-raw.txt").write_text(raw_text, encoding="utf-8")
        vision_json = output_dir / "vision-trace.json"
        vision_json.write_text(
            json.dumps(
                {"site": {"ee4_trace": trace.model_dump(mode="json", exclude_none=True)}},
                indent=2,
            ),
            encoding="utf-8",
        )
        code = proposal.main([
            "--job-dir", str(job_dir),
            "--output-dir", str(output_dir),
            "--vision-json", str(vision_json),
            "--strict",
        ])
        topology_status = "PASS" if code == 0 else "FAIL"
    except Exception as exc:
        topology_error = f"{type(exc).__name__}: {exc}"

    if direct_svg:
        try:
            svg, raw_svg = _call_direct_svg(
                api_key=api_key,
                base_url=base_url,
                model=provider_model,
                image_path=image_path,
                payload=payload,
                base_trace=base_trace,
            )
            (output_dir / "direct-raw.txt").write_text(raw_svg, encoding="utf-8")
            svg_path = output_dir / "direct-drawing.svg"
            svg_path.write_text(svg, encoding="utf-8")
            direct_status = "PASS" if _looks_like_svg(svg) else "FAIL"
            if direct_status == "FAIL":
                direct_error = "Model response did not look like standalone SVG."
        except Exception as exc:
            direct_status = "FAIL"
            direct_error = f"{type(exc).__name__}: {exc}"

    qa = _load_json(output_dir / "roof-topology-qa.json")
    score = _score_topology(topology_status, qa)
    if direct_status == "PASS":
        score += 1
    return {
        "provider": spec.name,
        "model": provider_model,
        "base_url": base_url,
        "topology_status": topology_status,
        "topology_error": topology_error,
        "direct_status": direct_status,
        "direct_error": direct_error,
        "score": score,
        "elapsed_s": round(time.monotonic() - start, 2),
        "artifacts": _artifact_paths(output_dir),
        "qa": qa,
        "notes": (
            f"Base trace source: {base_source}. "
            f"{'; '.join(base_warnings) if base_warnings else ''}"
        ).strip(),
    }


def _call_structured_topology(
    *,
    api_key: str,
    base_url: str,
    model: str,
    image_path: Path,
    payload,
    base_trace,
):
    prompt = proposal._openai_prompt(payload, base_trace)
    text = _chat_completion_text(api_key, base_url, model, prompt, image_path)
    data = proposal._parse_json_text(text)
    trace = proposal._model_trace_from_data(data, base_trace)
    return trace, text


def _call_direct_svg(
    *,
    api_key: str,
    base_url: str,
    model: str,
    image_path: Path,
    payload,
    base_trace,
) -> tuple[str, str]:
    base_json = json.dumps(
        {"site": {"ee4_trace": base_trace.model_dump(mode="json", exclude_none=True)}},
        ensure_ascii=False,
        indent=2,
    )
    prompt = f"""Return a standalone SVG only. No markdown.

Draw a compact black-and-white North American PV permit roof/site-plan style drawing
from the provided satellite crop. Include a roof outline, visible ridges/hips,
blue PV module rectangles for {payload.modules} modules, orange fire setback
hatching, and minimal labels. Use viewBox coordinates. This is for visual
comparison only, not AHJ-ready.

Keep it compact: use <pattern> for hatching, use grouped repeated modules,
and keep the SVG under 120 elements.

Current traced geometry:
{base_json}
"""
    text = _chat_completion_text(
        api_key,
        base_url,
        model,
        prompt,
        image_path,
        max_tokens=6000,
    )
    return _extract_svg(text), text


def _chat_completion_text(
    api_key: str,
    base_url: str,
    model: str,
    prompt: str,
    image_path: Path,
    max_tokens: int = 2400,
) -> str:
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=90)
    temperature = 1 if "kimi" in model.lower() else 0.1
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": proposal._image_data_url(image_path)},
                    },
                ],
            }
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    content = response.choices[0].message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(getattr(item, "text", "") or item.get("text", ""))
            for item in content
            if item
        )
    raise ValueError("Provider returned empty message content")


def _resolve_model_for_provider(
    spec: ProviderSpec,
    api_key: str,
    base_url: str,
    requested: str,
) -> str:
    if requested != "auto":
        return requested
    if spec.name == "openai_gateway":
        models = proposal._resolve_openai_models("auto")
        return models[0]
    try:
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=30)
        available = {item.id for item in client.models.list().data}
    except Exception:
        return spec.default_model
    if spec.default_model in available:
        return spec.default_model
    for model_id in sorted(available):
        lower = model_id.lower()
        if "vl" in lower or "vision" in lower or "omni" in lower:
            return model_id
    return spec.default_model


def _extract_svg(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.removeprefix("```svg").removeprefix("```").strip()
        if stripped.endswith("```"):
            stripped = stripped[:-3].strip()
    start = stripped.lower().find("<svg")
    end = stripped.lower().rfind("</svg>")
    if start != -1 and end != -1:
        return stripped[start:end + len("</svg>")]
    return stripped


def _looks_like_svg(text: str) -> bool:
    lower = text.lower()
    return "<svg" in lower and "</svg>" in lower


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact_paths(output_dir: Path) -> dict[str, str]:
    names = [
        "roof-topology-review.png",
        "roof-topology-review.pdf",
        "roof-topology-qa.json",
        "site-ee4-trace-proposed.yaml",
        "vision-trace.json",
        "direct-drawing.svg",
        "structured-raw.txt",
        "direct-raw.txt",
    ]
    return {
        name: str(output_dir / name)
        for name in names
        if (output_dir / name).exists()
    }


def _score_topology(status: str, qa: dict[str, Any]) -> int:
    score = 0
    if status == "PASS":
        score += 4
    if qa.get("roof_trace", {}).get("status") == "PASS":
        score += 2
    if qa.get("trace_module_layout", {}).get("can_ahj_ready"):
        score += 2
    if qa.get("placed_modules") == qa.get("target_modules") and qa.get("target_modules"):
        score += 1
    return score


def _report_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Roof Topology Provider Comparison",
        "",
        "| Provider | Model | Structured topology | Direct SVG | Score | Time | Notes |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for row in sorted(rows, key=lambda item: item.get("score", 0), reverse=True):
        notes = row.get("topology_error") or row.get("direct_error") or row.get("notes", "")
        lines.append(
            "| {provider} | `{model}` | {topology_status} | {direct_status} | "
            "{score} | {elapsed_s}s | {notes} |".format(
                provider=row.get("provider", ""),
                model=row.get("model", ""),
                topology_status=row.get("topology_status", ""),
                direct_status=row.get("direct_status", ""),
                score=row.get("score", 0),
                elapsed_s=row.get("elapsed_s", 0),
                notes=str(notes).replace("|", "/")[:220],
            )
        )
    lines.extend([
        "",
        "## Interpretation",
        "",
        "- Structured topology + deterministic rendering is the only path that can be gated for AHJ readiness.",
        "- Direct SVG output is useful as a visual reference only. It cannot prove scale, setbacks, module count, collision-free layout, or code compliance.",
        "- If a provider fails image input, keep it out of the roof-topology path unless a separate image-capable model is available.",
    ])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
