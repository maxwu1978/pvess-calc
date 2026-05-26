from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

from pvess_calc.web.server import WebProjectRequest


def test_roof_topology_vision_script_generates_reviewable_trace(tmp_path):
    job_dir = _write_satellite_job(tmp_path)
    script = (
        Path.cwd()
        / ".agents/skills/pvess-roof-topology-vision/scripts/generate_topology_proposal.py"
    )
    proposal_dir = tmp_path / "proposal"
    subprocess.run(
        [
            sys.executable,
            str(script),
            "--job-dir",
            str(job_dir),
            "--output-dir",
            str(proposal_dir),
            "--no-png",
            "--strict",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    qa = json.loads((proposal_dir / "roof-topology-qa.json").read_text())
    assert qa["status"] == "PASS"
    assert qa["source"] == "satellite_candidate"
    assert qa["placed_modules"] == qa["target_modules"] == 8
    assert qa["roof_trace"]["status"] == "PASS"
    assert qa["trace_module_layout"]["can_ahj_ready"] is True
    assert (proposal_dir / "site-ee4-trace-proposed.yaml").exists()
    assert (proposal_dir / "roof-topology-review.pdf").stat().st_size > 1000


def test_roof_topology_vision_sanitizes_model_json(tmp_path):
    job_dir = _write_satellite_job(tmp_path)
    vision_json = tmp_path / "vision.json"
    vision_json.write_text(
        json.dumps({
            "site": {
                "ee4_trace": {
                    "enabled": True,
                    "roof_outline": {
                        "name": "Model should not replace satellite outline",
                        "vertices": [[0, 0], [20, 0], [20, 10], [0, 10]],
                    },
                    "roof_lines": [
                        {"kind": "ridge", "points": [[10, 10], [70, 10]]},
                    ],
                    "fire_pathways": [
                        {
                            "name": "Model fire path should be replaced",
                            "vertices": [[0, 0], [80, 0], [80, 42], [0, 42]],
                        },
                    ],
                    "symbols": [
                        {"kind": "chimney", "x_ft": 999, "y_ft": 999},
                    ],
                },
            },
        }),
        encoding="utf-8",
    )
    proposal_dir = tmp_path / "proposal"
    script = (
        Path.cwd()
        / ".agents/skills/pvess-roof-topology-vision/scripts/generate_topology_proposal.py"
    )
    subprocess.run(
        [
            sys.executable,
            str(script),
            "--job-dir",
            str(job_dir),
            "--output-dir",
            str(proposal_dir),
            "--vision-json",
            str(vision_json),
            "--no-png",
            "--strict",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    proposed = yaml.safe_load(
        (proposal_dir / "site-ee4-trace-proposed.yaml").read_text()
    )["site"]["ee4_trace"]
    assert proposed["roof_outline"]["name"] == "Satellite roof outline"
    assert proposed["symbols"] == []
    assert proposed["fire_pathways"][0]["name"] != "Model fire path should be replaced"


def test_provider_comparison_skips_missing_key(tmp_path):
    job_dir = _write_satellite_job(tmp_path)
    script = (
        Path.cwd()
        / ".agents/skills/pvess-roof-topology-vision/scripts/compare_topology_providers.py"
    )
    out_dir = tmp_path / "comparison"
    env = os.environ.copy()
    env.pop("GEMINI_API_KEY", None)
    subprocess.run(
        [
            sys.executable,
            str(script),
            "--job-dir",
            str(job_dir),
            "--image",
            str(job_dir / "output" / "satellite-ee4-trace-candidate.yaml"),
            "--output-dir",
            str(out_dir),
            "--providers",
            "gemini",
            "--skip-direct-svg",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    rows = json.loads((out_dir / "provider-comparison.json").read_text())
    assert rows[0]["provider"] == "algorithm"
    assert rows[0]["topology_status"] == "PASS"
    assert rows[1]["provider"] == "gemini"
    assert rows[1]["topology_status"] == "SKIPPED"


def _write_satellite_job(tmp_path):
    job_dir = tmp_path / "job"
    output_dir = job_dir / "output"
    output_dir.mkdir(parents=True)

    payload = WebProjectRequest.model_validate({
        "project_id": "skill-smoke",
        "project_name": "Skill Smoke PV",
        "location": "Frisco, TX",
        "site_address": "",
        "ahj": "Frisco TX",
        "utility": "Oncor",
        "modules": 8,
        "strings": 2,
        "battery_quantity": 0,
        "battery_capacity_kwh_each": 0,
        "outputs": {
            "customer": False,
            "permit": False,
            "dxf": False,
            "labels": False,
            "qet": False,
        },
    })
    (job_dir / "request.json").write_text(
        payload.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (output_dir / "satellite-ee4-trace-candidate.yaml").write_text(
        yaml.safe_dump(
            {
                "site": {
                    "ee4_trace": {
                        "enabled": True,
                        "roof_outline": {
                            "name": "Satellite roof outline",
                            "vertices": [
                                [0.0, 0.0],
                                [80.0, 0.0],
                                [80.0, 42.0],
                                [0.0, 42.0],
                            ],
                        },
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return job_dir
