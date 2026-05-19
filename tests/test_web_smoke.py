from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from pvess_calc.web.smoke import SmokeError, run_smoke, smoke_cmd


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_web_smoke_verifies_health_static_auth_and_generation():
    calls: list[tuple[str, str, bool]] = []

    def fake_json(base_url, path, token, timeout_s, payload):
        calls.append(("json", path, payload is not None))
        if path == "/api/health":
            return {
                "status": "ok",
                "version": "0.1.0",
                "storage": {
                    "status": "ok",
                    "jobs_dir": "/data/pvess-web",
                    "job_db_path": "/data/pvess-web/web-jobs.sqlite3",
                },
            }
        if path == "/api/runtime-config":
            return {"auth_required": True}
        if path == "/api/projects/sync":
            assert token == "secret"
            assert payload["outputs"] == {
                "customer": False,
                "permit": False,
                "dxf": False,
                "labels": False,
                "qet": False,
            }
            return {
                "job_id": "smoke-job",
                "project_dir": "/data/pvess-web/smoke-job",
                "files": [
                    {"label": "Inputs YAML"},
                    {"label": "Calculation JSON"},
                    {"label": "BOM + Cost JSON"},
                ],
            }
        raise AssertionError(path)

    def fake_text(base_url, path, token, timeout_s):
        calls.append(("text", path, False))
        if path == "/":
            return "<h1>TGE Solar Project Generator</h1>"
        if path == "/assets/app.js":
            return "function apiFetch() {}"
        raise AssertionError(path)

    messages = run_smoke(
        base_url="http://example.test",
        token="secret",
        request_json=fake_json,
        request_text=fake_text,
    )

    assert messages == [
        "health ok: version=0.1.0 storage=/data/pvess-web",
        "static assets ok",
        "auth mode ok: auth_required=True",
        "generation ok: job_id=smoke-job",
    ]
    assert calls == [
        ("json", "/api/health", False),
        ("text", "/", False),
        ("text", "/assets/app.js", False),
        ("json", "/api/runtime-config", False),
        ("json", "/api/projects/sync", True),
    ]


def test_web_smoke_fails_when_auth_required_without_token():
    def fake_json(base_url, path, token, timeout_s, payload):
        if path == "/api/health":
            return {
                "status": "ok",
                "version": "0.1.0",
                "storage": {
                    "status": "ok",
                    "jobs_dir": "/data/pvess-web",
                    "job_db_path": "/data/pvess-web/web-jobs.sqlite3",
                },
            }
        if path == "/api/runtime-config":
            return {"auth_required": True}
        raise AssertionError(path)

    def fake_text(base_url, path, token, timeout_s):
        return (
            "<h1>TGE Solar Project Generator</h1>"
            if path == "/" else "function apiFetch() {}"
        )

    try:
        run_smoke(
            base_url="http://example.test",
            request_json=fake_json,
            request_text=fake_text,
        )
    except SmokeError as exc:
        assert "requires auth" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected SmokeError")


def test_web_smoke_cli_help_exits_zero():
    result = CliRunner().invoke(smoke_cmd, ["--help"])

    assert result.exit_code == 0
    assert "--base-url" in result.output
    assert "--skip-generate" in result.output


def test_web_dockerfile_uses_persistent_job_volume():
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "PVESS_WEB_WORKDIR=/data/pvess-web" in dockerfile
    assert 'VOLUME ["/data/pvess-web"]' in dockerfile
    assert "uvicorn pvess_calc.web.server:app" in dockerfile
    assert "projects/*/output" in dockerignore
    assert "*.sqlite3" in dockerignore
