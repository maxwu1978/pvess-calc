"""Production smoke check for the Web generator."""
from __future__ import annotations

import json
import os
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import click


JsonRequester = Callable[[str, str, str, float, dict[str, Any] | None], dict[str, Any]]
TextRequester = Callable[[str, str, str, float], str]


class SmokeError(RuntimeError):
    """Raised when a production smoke check fails."""


def run_smoke(
    *,
    base_url: str,
    token: str = "",
    timeout_s: float = 30.0,
    generate: bool = True,
    request_json: JsonRequester | None = None,
    request_text: TextRequester | None = None,
) -> list[str]:
    """Verify health, static assets, auth mode, and optional package output."""
    base = base_url.rstrip("/") + "/"
    get_json = request_json or _request_json
    get_text = request_text or _request_text
    messages: list[str] = []

    health = get_json(base, "/api/health", "", timeout_s, None)
    _require(health.get("status") == "ok", "health status is not ok")
    _require(health.get("version"), "health response is missing version")
    storage = health.get("storage") if isinstance(health.get("storage"), dict) else {}
    _require(storage.get("status") == "ok", "storage status is not ok")
    _require(storage.get("job_db_path"), "health response is missing job DB path")
    messages.append(
        f"health ok: version={health['version']} storage={storage['jobs_dir']}"
    )

    html = get_text(base, "/", "", timeout_s)
    _require("TGE Solar Project Generator" in html, "static index title missing")
    app_js = get_text(base, "/assets/app.js", "", timeout_s)
    _require("apiFetch" in app_js, "static app.js did not load")
    messages.append("static assets ok")

    runtime = get_json(base, "/api/runtime-config", "", timeout_s, None)
    auth_required = bool(runtime.get("auth_required"))
    if auth_required and not token:
        raise SmokeError("server requires auth; pass --token or PVESS_WEB_ACCESS_TOKEN")
    messages.append(f"auth mode ok: auth_required={auth_required}")

    if generate:
        result = get_json(base, "/api/projects/sync", token, timeout_s, _smoke_payload())
        _require(result.get("job_id"), "smoke generation did not return job_id")
        files = result.get("files") if isinstance(result.get("files"), list) else []
        labels = {str(file.get("label", "")) for file in files if isinstance(file, dict)}
        for label in ("Inputs YAML", "Calculation JSON", "BOM + Cost JSON"):
            _require(label in labels, f"smoke generation missing {label}")
        _require(
            result.get("project_dir"),
            "smoke generation did not return persistent project_dir",
        )
        messages.append(f"generation ok: job_id={result['job_id']}")

    return messages


def _smoke_payload() -> dict[str, Any]:
    return {
        "project_name": "Production Smoke PV Package",
        "location": "Mansfield, TX",
        "site_address": "905 Crossvine Drive, Mansfield, TX",
        "ahj": "City of Mansfield Building Safety",
        "utility": "Oncor Electric Delivery",
        "modules": 8,
        "strings": 2,
        "module_power_w": 415,
        "battery_choice": "none",
        "battery_quantity": 0,
        "battery_capacity_kwh_each": 0,
        "site_data_source": "simulated",
        "outputs": {
            "customer": False,
            "permit": False,
            "dxf": False,
            "labels": False,
            "qet": False,
        },
    }


def _request_json(
    base_url: str,
    path: str,
    token: str,
    timeout_s: float,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    data = None
    method = "GET"
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        method = "POST"
        headers["Content-Type"] = "application/json"
    if token:
        headers["X-PVESS-Token"] = token
    response = _open(base_url, path, timeout_s, method=method, headers=headers, data=data)
    try:
        return json.loads(response)
    except json.JSONDecodeError as exc:
        raise SmokeError(f"{path} returned non-JSON response") from exc


def _request_text(base_url: str, path: str, token: str, timeout_s: float) -> str:
    headers: dict[str, str] = {}
    if token:
        headers["X-PVESS-Token"] = token
    return _open(base_url, path, timeout_s, method="GET", headers=headers)


def _open(
    base_url: str,
    path: str,
    timeout_s: float,
    *,
    method: str,
    headers: dict[str, str],
    data: bytes | None = None,
) -> str:
    url = urljoin(base_url, path.lstrip("/"))
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - user URL.
            return response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SmokeError(f"{method} {path} failed with HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise SmokeError(f"{method} {path} failed: {exc.reason}") from exc


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise SmokeError(message)


@click.command(name="pvess-web-smoke")
@click.option(
    "--base-url",
    default="http://127.0.0.1:8765",
    show_default=True,
    help="Base URL of the running Web service.",
)
@click.option(
    "--token",
    default=lambda: os.environ.get("PVESS_WEB_ACCESS_TOKEN", ""),
    help="Admin or operator token when the Web service requires auth.",
)
@click.option("--timeout", "timeout_s", default=30.0, show_default=True, type=float)
@click.option(
    "--skip-generate",
    is_flag=True,
    help="Only check health/static/auth; do not create a smoke job.",
)
def smoke_cmd(
    base_url: str,
    token: str,
    timeout_s: float,
    skip_generate: bool,
) -> None:
    """Smoke-test a running production Web deployment."""
    try:
        messages = run_smoke(
            base_url=base_url,
            token=token.strip(),
            timeout_s=timeout_s,
            generate=not skip_generate,
        )
    except SmokeError as exc:
        raise click.ClickException(str(exc)) from exc
    for message in messages:
        click.echo(click.style(f"PASS {message}", fg="green"))
