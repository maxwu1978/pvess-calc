from __future__ import annotations

import base64
import json
import sqlite3
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import yaml

from pvess_calc.web.server import (
    GeneratedFile,
    WebProjectRequest,
    build_ahj_gate,
    build_inputs_data,
    build_source_materials,
    create_app,
    default_qet_template,
    find_pdftoppm,
    _lookup_suggested_payload,
)
from pvess_calc.web import server as web_server
from pvess_calc.lookup.address import parse_address
from pvess_calc.web.job_store import JOB_DB_FILENAME, JobStore
from pvess_calc.web.notifications import LeadNotificationConfig, WebhookResult
from pvess_calc.schema import EE4Trace, Inputs


DFW_SIMULATED_MONTHLY_KWH = [
    880, 780, 720, 820, 1050, 1450, 1700, 1750, 1450, 1050, 820, 860,
]

MANSFIELD_SAMPLE_ADDRESSES = [
    "905 Crossvine Drive, Mansfield, TX",
    "2806 Green Circle Drive, Mansfield, TX",
]


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(jobs_dir=tmp_path))


def test_pdf_preview_finds_homebrew_pdftoppm_when_path_is_thin(monkeypatch, tmp_path: Path):
    fake = tmp_path / "opt" / "homebrew" / "bin" / "pdftoppm"
    fake.parent.mkdir(parents=True)
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(web_server.shutil, "which", lambda name: None)
    monkeypatch.setattr(web_server, "PDFTOPPM_CANDIDATES", (fake,))

    assert find_pdftoppm() == str(fake)


def test_build_inputs_auto_injects_lookup_roof_sections_when_missing(monkeypatch):
    def fake_resolve_lookup(address: str, **kwargs):
        return SimpleNamespace(fields={
            "latitude": 33.141418,
            "longitude": -96.801258,
            "roof_sections": [
                {
                    "name": "South Face",
                    "roof_type": "Comp Shingle",
                    "pitch_deg": 26.0,
                    "azimuth_deg": 181.0,
                    "width_ft": 42.0,
                    "height_ft": 18.0,
                    "module_count": 0,
                    "shape": "rect",
                },
                {
                    "name": "West Face",
                    "roof_type": "Comp Shingle",
                    "pitch_deg": 24.0,
                    "azimuth_deg": 250.0,
                    "width_ft": 30.0,
                    "height_ft": 16.0,
                    "module_count": 0,
                    "shape": "rect",
                },
            ],
        })

    monkeypatch.setattr(web_server, "resolve_lookup", fake_resolve_lookup)
    payload = WebProjectRequest.model_validate(_light_payload(
        site_address="7652 Glasshouse Walk, Frisco, TX 75035",
        coordinates="33.141418, -96.801258",
        roof_sections=[],
    ))

    data = build_inputs_data(payload, project_id="lookup-roof")

    assert data["project"]["coordinates"] == "33.141418, -96.801258"
    assert [section["name"] for section in data["site"]["roof_sections"]] == [
        "South Face",
        "West Face",
    ]
    assert data["site"]["roof_sections"][0]["module_count"] == 0


def test_build_inputs_accepts_web_ee4_trace_payload():
    trace = {
        "enabled": True,
        "roof_outline": {
            "name": "Reviewed roof outline",
            "vertices": [[0, 0], [50, 0], [50, 30], [0, 30]],
        },
        "roof_facets": [
            {
                "name": "Main roof",
                "vertices": [[4, 4], [46, 4], [46, 26], [4, 26]],
            }
        ],
        "roof_lines": [{"kind": "ridge", "points": [[4, 15], [46, 15]]}],
        "fire_pathways": [
            {
                "name": "Fire setback",
                "vertices": [[2, 2], [48, 2], [48, 28], [2, 28]],
            }
        ],
    }
    payload = WebProjectRequest.model_validate(_light_payload(ee4_trace=trace))

    data = build_inputs_data(payload, project_id="trace-web")
    inputs = Inputs.model_validate(data)

    assert inputs.site.ee4_trace.enabled is True
    assert inputs.site.ee4_trace.roof_outline is not None
    assert len(inputs.site.ee4_trace.fire_pathways) == 1


def test_web_lookup_refreshes_stale_cache_when_roof_sections_missing(monkeypatch):
    calls: list[bool] = []

    def fake_resolve_lookup(address: str, *, providers=None, use_cache: bool = True):
        calls.append(use_cache)
        fields = {}
        if not use_cache:
            fields["roof_sections"] = [
                {
                    "name": "Refreshed Face",
                    "pitch_deg": 22.0,
                    "azimuth_deg": 180.0,
                    "width_ft": 40.0,
                    "height_ft": 18.0,
                    "module_count": 0,
                }
            ]
        return SimpleNamespace(fields=fields)

    monkeypatch.setattr(web_server, "resolve_lookup", fake_resolve_lookup)

    result = web_server._resolve_lookup_for_web("7652 Glasshouse Walk, Frisco, TX")

    assert calls == [True, False]
    assert result.fields["roof_sections"][0]["name"] == "Refreshed Face"


def test_job_store_migrates_campaign_columns_before_indexes(tmp_path: Path):
    db_path = tmp_path / JOB_DB_FILENAME
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE web_leads (
                lead_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'new',
                contact_name TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                site_address TEXT NOT NULL DEFAULT '',
                project_type TEXT NOT NULL DEFAULT 'pv_ess',
                utility TEXT NOT NULL DEFAULT '',
                monthly_kwh_json TEXT NOT NULL DEFAULT '[]',
                notes TEXT NOT NULL DEFAULT '',
                utility_bill_path TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'public_form',
                converted_job_id TEXT NOT NULL DEFAULT '',
                last_contacted_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

    JobStore(tmp_path).ensure_ready()

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(web_leads)")}
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(web_leads)")}
    assert "campaign_source" in columns
    assert "campaign_name" in columns
    assert "idx_web_leads_campaign_source" in indexes
    assert "idx_web_leads_campaign_name" in indexes


def _light_payload(**overrides):
    payload = {
        "project_name": "Web Smoke Test",
        "location": "Frisco, TX",
        "site_address": "7652 Glasshouse Walk, Frisco, TX",
        "ahj": "Frisco TX",
        "utility": "Oncor",
        "modules": 8,
        "strings": 2,
        "module_power_w": 415,
        "battery_quantity": 0,
        "battery_capacity_kwh_each": 0,
        "outputs": {
            "customer": False,
            "permit": False,
            "dxf": False,
            "labels": False,
            "qet": False,
        },
    }
    payload.update(overrides)
    return payload


def _mansfield_payload(address: str, **overrides):
    payload = _light_payload(
        project_name=f"{address.split(',')[0]} PV + ESS Package",
        location="Mansfield, TX",
        site_address=address,
        ahj="City of Mansfield Building Safety",
        utility="Oncor Electric Delivery",
        monthly_kwh=DFW_SIMULATED_MONTHLY_KWH,
        site_data_source="simulated",
    )
    payload.update(overrides)
    return payload


def _complete_real_payload(**overrides):
    payload = _light_payload(
        outputs={
            "customer": False,
            "permit": True,
            "dxf": True,
            "labels": True,
            "qet": False,
        },
        site_data_source="real",
        coordinates="32.568900, -97.141000",
        apn="R-12345",
        meter_number="153468971",
        meter_location="Exterior garage wall",
        meter_esid="10443720007628433",
        engineer_firm="Wyssling Consulting",
        engineer_address="76 N Meadowbrook Dr, Alpine UT",
        engineer_email="engineer@example.com",
        engineer_phone="(201) 874-3483",
        engineer_firm_number="20109",
        installer_company="Texas Green Eco Power",
        installer_address="2806 Green Cir Dr, Mansfield, TX",
        roof_info_type="Comp Shingle",
        roof_info_height_ft=25,
        roof_construction="Prefabricated trusses",
        roof_condition="good",
        roof_framing='2x4 @ 24" O.C.',
        roof_attic_access="accessible",
        decking_thickness_in=0.5,
        roof_layers=1,
        monthly_kwh=DFW_SIMULATED_MONTHLY_KWH,
        monthly_kwh_source="utility_file",
        utility_bill_path="/evidence/utility.csv",
        structural_letter_path="/evidence/structural.pdf",
        msp_x_ft=72,
        msp_y_ft=34,
        inverter_x_ft=64,
        inverter_y_ft=34,
        ac_disconnect_x_ft=68,
        ac_disconnect_y_ft=34,
        site_photo_refs=[
            {"kind": "front_elevation", "path": "/evidence/front.jpg", "caption": "Front elevation"},
            {"kind": "roof", "path": "/evidence/roof.jpg", "caption": "Roof"},
            {"kind": "meter", "path": "/evidence/meter.jpg", "caption": "Meter"},
            {"kind": "main_panel", "path": "/evidence/main.jpg", "caption": "Main panel"},
            {"kind": "sub_panel", "path": "/evidence/sub.jpg", "caption": "Sub-panel"},
            {"kind": "equipment_location", "path": "/evidence/equipment.jpg", "caption": "Equipment location"},
        ],
        spec_sheet_refs=[
            {"equipment": "module", "path": "/evidence/module.pdf"},
            {"equipment": "inverter", "path": "/evidence/inverter.pdf"},
            {"equipment": "optimizer", "path": "/evidence/optimizer.pdf"},
            {"equipment": "racking", "path": "/evidence/racking.pdf"},
        ],
    )
    payload.update(overrides)
    return payload


def _gate_files(tmp_path: Path, job_id: str = "gate-job") -> list[GeneratedFile]:
    project_dir = tmp_path / job_id
    output_dir = project_dir / "output"
    output_dir.mkdir(parents=True)
    paths = {
        "Permit Package PDF (12 pages)": output_dir / "permit-package.pdf",
        "NEC Labels PDF (8)": output_dir / "labels.pdf",
        "EE-1 Three-line DXF": output_dir / "sheet-EE-1.dxf",
        "EE-1 Three-line PNG Preview": output_dir / "sheet-EE-1.png",
    }
    files: list[GeneratedFile] = []
    for label, path in paths.items():
        path.write_bytes(b"x")
        files.append(GeneratedFile(
            label=label,
            path=path.relative_to(project_dir).as_posix(),
            url=f"/files/{job_id}/{path.relative_to(project_dir).as_posix()}",
            bytes=1,
            category="Permit" if "PDF" in label else "CAD",
            kind="pdf" if "PDF" in label else ("preview" if path.suffix == ".png" else "dxf"),
        ))
    return files


def _approved_reviews(files: list[GeneratedFile]) -> dict[str, dict[str, str]]:
    return {
        file.path: {
            "path": file.path,
            "status": "approved_internal",
            "note": "checked",
        }
        for file in files
    }


def _submit_and_wait(
    client: TestClient,
    payload: dict,
    *,
    headers: dict[str, str] | None = None,
    timeout_s: float = 20.0,
):
    response = client.post("/api/projects", json=payload, headers=headers or {})
    assert response.status_code == 200, response.text
    state = response.json()
    assert state["status"] in {"queued", "running", "done"}
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status = client.get(f"/api/jobs/{state['job_id']}", headers=headers or {})
        assert status.status_code == 200, status.text
        state = status.json()
        if state["status"] == "done":
            assert state["result"] is not None
            return state
        if state["status"] == "failed":
            raise AssertionError(state.get("error"))
        time.sleep(0.1)
    raise AssertionError(f"job did not finish: {state}")


def _wait_for_job(
    client: TestClient,
    job_id: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_s: float = 20.0,
):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status = client.get(f"/api/jobs/{job_id}", headers=headers or {})
        assert status.status_code == 200, status.text
        state = status.json()
        if state["status"] == "done":
            assert state["result"] is not None
            return state
        if state["status"] == "failed":
            raise AssertionError(state.get("error"))
        time.sleep(0.1)
    raise AssertionError(f"job did not finish: {state}")


def _submit_form_and_wait(
    client: TestClient,
    payload: dict,
    *,
    files: dict | None = None,
    timeout_s: float = 20.0,
):
    response = client.post(
        "/api/projects/form",
        data={"payload": json.dumps(payload)},
        files=files or {},
    )
    assert response.status_code == 200, response.text
    state = response.json()
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status = client.get(f"/api/jobs/{state['job_id']}")
        assert status.status_code == 200, status.text
        state = status.json()
        if state["status"] == "done":
            assert state["result"] is not None
            return state
        if state["status"] == "failed":
            raise AssertionError(state.get("error"))
        time.sleep(0.1)
    raise AssertionError(f"job did not finish: {state}")


def _token_headers(token: str) -> dict[str, str]:
    return {"X-PVESS-Token": token}


def _basic_headers(user: str, password: str) -> dict[str, str]:
    raw = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {raw}"}


def test_web_index_serves_static_page(tmp_path: Path):
    client = _client(tmp_path)
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert "TGE Solar Project Generator" in response.text
    assert "Project basics" in response.text
    assert "System type" in response.text
    assert "Talesun TP7G54M-415" in response.text
    assert "Pytes V16" in response.text
    assert "Hoymiles HBX-10LV-USG1" in response.text
    assert "Megarevo" in response.text
    assert "Hoymiles" in response.text
    assert "Growatt" in response.text
    assert "PV modules" in response.text
    assert "Inverter" in response.text
    assert "Battery package follows the inverter brand" in response.text
    assert "Roof and usage" in response.text
    assert "Roof confirmation" in response.text
    assert "Build roof preview" in response.text
    assert 'id="roof-preview-panel"' in response.text
    assert 'name="roof_satellite_image"' in response.text
    assert response.text.count('name="satellite_crop_mode"') == 1
    assert "Usage source" in response.text
    assert "Average monthly kWh" in response.text
    assert "Roof material" in response.text
    assert "Electrical and cost assumptions" in response.text
    assert "Electrical service" in response.text
    assert "Existing solar" in response.text
    assert "Usage behavior" in response.text
    assert "Advanced roof geometry" in response.text
    assert "Advanced cost overrides" in response.text
    assert "We will verify battery clearances" in response.text
    assert "Doorway setback ft" not in response.text
    assert "Window setback ft" not in response.text
    assert "Egress setback ft" not in response.text
    assert "Source materials and evidence" in response.text
    assert "Evidence mode" in response.text
    assert "Quick estimate - use simulated evidence" in response.text
    assert "Use uploaded field evidence" in response.text
    assert "Upload site photos" in response.text
    assert "PV-7 photo targets" in response.text
    assert "Engineering and manufacturer documents" in response.text
    assert "Signed structural letter" in response.text
    assert "Upload missing manufacturer documents" in response.text
    assert "Module spec sheet" not in response.text
    assert "Inverter spec sheet" not in response.text
    assert "Battery spec sheet" not in response.text
    assert "Check readiness" in response.text
    assert "Readiness check" in response.text
    assert "Step status" in response.text
    assert "Review and generate" in response.text
    assert "Operator tools" in response.text
    assert "Current step" in response.text
    assert "Package QA" in response.text
    assert "Final project summary" in response.text
    assert "Package type" in response.text
    assert "Customer estimate" in response.text
    assert "Engineering review" in response.text
    assert "AHJ-ready candidate" in response.text
    assert "Selected deliverables" in response.text
    assert "Advanced files" in response.text
    assert "Package review workspace" in response.text
    assert "Generated files are reviewed one page at a time" in response.text
    assert "Status details" in response.text
    assert "Readiness, warnings, Package QA, and required approvals" in response.text
    assert "Review preview" in response.text
    assert "Review checklist" in response.text
    assert "Save draft" in response.text
    assert "Continue" in response.text
    assert "Back" in response.text
    assert "Operator access token" not in response.text
    assert "Open public request page" in response.text
    assert response.text.count('name="engineer_phone"') == 1
    assert "Check address" in response.text
    assert "Address check result" in response.text
    assert "Advanced project settings" not in response.text
    assert 'id="lookup-mode"' in response.text
    assert 'id="address-sample" hidden' in response.text
    assert "Street address" in response.text
    assert "Unit / suite" in response.text
    assert "ZIP code" in response.text
    assert "905 Crossvine Drive, Mansfield, TX" in response.text
    assert "2806 Green Circle Drive, Mansfield, TX" in response.text
    assert "Public leads" in response.text
    assert "Lead status filter" in response.text
    assert "Export CSV" in response.text
    assert "Email follow-up draft" in response.text
    assert "What needs attention" in response.text
    assert "Filter" in response.text
    assert "Generate package" in response.text
    assert "Frisco PV + ESS Estimate" not in response.text
    assert "Project Estimator" not in response.text
    assert client.get("/favicon.ico").status_code == 204


def test_lookup_suggested_payload_maps_parcel_identifier_to_apn():
    suggested = _lookup_suggested_payload(
        {"parcel_id": "R-12345", "utility_name": "Oncor Electric Delivery"},
        parse_address("905 Crossvine Drive, Mansfield, TX 76063"),
    )

    assert suggested["apn"] == "R-12345"


def test_web_generation_uses_lookup_roof_sections_when_present():
    payload = WebProjectRequest.model_validate(
        _light_payload(
            roof_pitch_deg=20,
            roof_azimuth_deg=180,
            roof_width_ft=40,
            roof_height_ft=20,
            roof_sections=[
                {
                    "name": "Southeast Roof",
                    "roof_type": "Comp Shingle",
                    "pitch_deg": 32.8,
                    "azimuth_deg": 126.0,
                    "width_ft": 17.5,
                    "height_ft": 17.5,
                    "module_count": 0,
                    "shape": "rect",
                },
                {
                    "name": "Southwest Roof",
                    "roof_type": "Comp Shingle",
                    "pitch_deg": 28.4,
                    "azimuth_deg": 224.0,
                    "width_ft": 19.0,
                    "height_ft": 16.0,
                    "module_count": 0,
                    "shape": "rect",
                },
            ],
        )
    )

    data = build_inputs_data(payload, project_id="lookup-roof-test")

    sections = data["site"]["roof_sections"]
    assert [section["name"] for section in sections] == [
        "Southeast Roof",
        "Southwest Roof",
    ]
    assert all(section["module_count"] == 0 for section in sections)
    assert sections[0]["pitch_deg"] == 32.8
    assert sections[1]["azimuth_deg"] == 224.0


def test_web_draft_api_round_trip(tmp_path: Path):
    client = _client(tmp_path)

    response = client.post(
        "/api/drafts",
        json={
            "draft_id": "draft-unit-test",
            "step": "system-equipment",
            "payload": {
                "project_name": "Draft Test",
                "site_address": "905 Crossvine Drive, Mansfield, TX",
                "modules": 32,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["draft_id"] == "draft-unit-test"
    assert data["owner_id"] == "local"
    assert data["step"] == "system-equipment"
    assert data["payload"]["modules"] == 32
    assert data["created_at"]
    assert data["updated_at"]

    readback = client.get("/api/drafts/draft-unit-test")
    assert readback.status_code == 200
    assert readback.json()["payload"]["site_address"].startswith("905 Crossvine")


def test_web_health_endpoint(tmp_path: Path):
    client = _client(tmp_path)
    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "TGE Solar Project Generator"
    assert data["version"] == "0.1.0"
    assert data["jobs_dir"] == str(tmp_path)
    assert data["storage"]["status"] == "ok"
    assert data["storage"]["jobs_dir"] == str(tmp_path)
    assert data["storage"]["job_db_path"] == str(tmp_path / "web-jobs.sqlite3")
    assert data["storage"]["job_db_exists"] is True
    assert data["storage"]["writable"] is True
    assert data["auth_required"] is False


def test_web_runtime_config_reports_auth_mode(tmp_path: Path):
    client = TestClient(create_app(jobs_dir=tmp_path, access_token="secret"))
    response = client.get("/api/runtime-config")

    assert response.status_code == 200
    data = response.json()
    assert data["auth_required"] is True
    assert data["lookup_modes"] == ["online", "offline"]


def test_web_default_qet_template_resolves_for_source_checkout():
    assert default_qet_template().exists()
    assert default_qet_template().name == "residential-ess-v1.qet"


def test_web_catalog_exposes_device_options(tmp_path: Path):
    client = _client(tmp_path)
    response = client.get("/api/catalog")

    assert response.status_code == 200
    data = response.json()
    assert {m["key"] for m in data["modules"]} >= {
        "talesun_tp7g54m_415",
        "rec_alpha_pure_410",
    }
    assert {i["key"] for i in data["inverters"]} >= {
        "megarevo",
        "hoymiles",
        "growatt",
    }
    assert {b["key"] for b in data["batteries"]} >= {
        "none",
        "pytes_v16",
        "hoymiles_hbx_10lv_usg1",
        "growatt_apx_20kwh",
    }


def test_web_address_lookup_offline_prefills_known_city(tmp_path: Path):
    client = _client(tmp_path)
    response = client.get(
        "/api/lookup/address",
        params={"address": "Phoenix, AZ", "mode": "offline"},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    suggested = data["suggested_payload"]
    assert data["status"] == "PASS"
    assert data["mode"] == "offline"
    assert suggested["location"] == "Phoenix, AZ"
    assert suggested["utility"] == "Arizona Public Service (APS)"
    assert suggested["ahj"] == "City of Phoenix Planning & Development Dept"
    assert suggested["nec_edition"] == "2017"
    assert suggested["export_tariff_model"] == "1to1_nem"
    assert data["field_sources"]["utility_name"] == "utility-offline"
    assert any(provider["source"] == "utility-offline" and provider["hit"] for provider in data["providers"])


def test_web_mansfield_sample_addresses_generate_with_simulated_usage(tmp_path: Path):
    client = _client(tmp_path)

    for address in MANSFIELD_SAMPLE_ADDRESSES:
        state = _submit_and_wait(client, _mansfield_payload(address))
        data = state["result"]
        project_dir = Path(data["project_dir"])
        inputs = yaml.safe_load((project_dir / "inputs.yaml").read_text(encoding="utf-8"))

        assert inputs["project"]["site_address"] == address
        assert inputs["project"]["location"] == "Mansfield, TX"
        assert inputs["project"]["utility"] == "Oncor Electric Delivery"
        assert inputs["loads"]["monthly_kwh"] == DFW_SIMULATED_MONTHLY_KWH
        assert data["source_materials"]["monthly_kwh_count"] == 12
        assert data["source_materials"]["site_data_source"] == "simulated"
        assert data["bom"]["annual_bill_savings_usd"] > 0


def test_web_mansfield_preflight_treats_usage_as_present_but_simulated(tmp_path: Path):
    client = _client(tmp_path)
    response = client.post(
        "/api/preflight",
        json=_mansfield_payload(MANSFIELD_SAMPLE_ADDRESSES[0]),
    )

    assert response.status_code == 200, response.text
    data = response.json()
    issue_fields = {issue["field"] for issue in data["issues"]}
    assert "monthly_kwh" not in issue_fields
    assert "site_data_source" in issue_fields
    assert data["estimate"]["annual_bill_savings_usd"] > 0


def test_web_optional_access_token_protects_api_and_files(tmp_path: Path):
    client = TestClient(create_app(jobs_dir=tmp_path, access_token="secret"))

    assert client.get("/").status_code == 200
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/jobs").status_code == 401

    response = client.post(
        "/api/projects",
        json=_light_payload(),
        headers={"X-PVESS-Token": "secret"},
    )
    assert response.status_code == 200, response.text
    state = response.json()
    deadline = time.time() + 20.0
    while time.time() < deadline:
        status = client.get(
            f"/api/jobs/{state['job_id']}",
            headers={"Authorization": "Bearer secret"},
        )
        assert status.status_code == 200, status.text
        state = status.json()
        if state["status"] == "done":
            break
        if state["status"] == "failed":
            raise AssertionError(state.get("error"))
        time.sleep(0.1)
    assert state["status"] == "done"

    assert client.get(f"/files/{state['job_id']}/inputs.yaml").status_code == 401
    file_response = client.get(f"/files/{state['job_id']}/inputs.yaml?token=secret")
    assert file_response.status_code == 200
    assert "Web Smoke Test" in file_response.text


def test_web_basic_auth_protects_static_and_health_pages(tmp_path: Path):
    client = TestClient(
        create_app(
            jobs_dir=tmp_path,
            access_token="secret",
            basic_auth=("site-user", "site-pass"),
        )
    )

    assert client.get("/").status_code == 401
    assert client.get("/assets/app.js").status_code == 401
    assert client.get("/api/health").status_code == 401

    headers = _basic_headers("site-user", "site-pass")
    assert client.get("/", headers=headers).status_code == 200
    health = client.get("/api/health", headers=headers)
    assert health.status_code == 200
    assert health.json()["site_auth_required"] is True
    assert "basic_auth" in health.json()["auth_modes"]

    jobs = client.get("/api/jobs", headers=headers)
    assert jobs.status_code == 200
    session = client.get("/api/session", headers=headers)
    assert session.status_code == 200
    assert session.json()["operator_id"] == "local"
    assert session.json()["is_admin"] is True

    api_headers = {**headers, "X-PVESS-Token": "secret"}
    assert client.get("/api/jobs", headers=api_headers).status_code == 200


def test_web_public_lead_page_and_submission_bypass_auth(tmp_path: Path):
    client = TestClient(
        create_app(
            jobs_dir=tmp_path,
            access_token="secret",
            basic_auth=("site-user", "site-pass"),
        )
    )

    assert client.get("/").status_code == 401
    lead_page = client.get("/lead")
    assert lead_page.status_code == 200
    assert "Request a solar + battery estimate" in lead_page.text
    assert client.get("/favicon.ico").status_code == 204

    response = client.post(
        "/api/leads",
        data={
            "contact_name": "Li Liu",
            "email": "li.liutexas@yahoo.com",
            "phone": "817-555-0100",
            "site_address": "905 Crossvine Drive, Mansfield, TX",
            "project_type": "pv_ess",
            "utility": "Oncor Electric Delivery",
            "monthly_kwh_text": "1,200",
            "notes": "Public lead smoke test",
            "campaign_source": "google",
            "campaign_medium": "cpc",
            "campaign_name": "dfw-solar",
            "campaign_content": "battery-copy",
            "referrer": "https://google.com/search?q=tge+solar",
            "landing_url": "https://tge.reelamate.com/lead?utm_source=google",
        },
    )

    assert response.status_code == 200, response.text
    lead = response.json()["lead"]
    assert lead["email"] == "li.liutexas@yahoo.com"
    assert lead["status"] == "new"
    assert lead["site_address"] == "905 Crossvine Drive, Mansfield, TX"
    assert lead["utility"] == "Oncor Electric Delivery"
    assert lead["monthly_kwh"] == [1200.0] * 12
    assert lead["campaign_source"] == "google"
    assert lead["campaign_medium"] == "cpc"
    assert lead["campaign_name"] == "dfw-solar"
    assert lead["campaign_content"] == "battery-copy"
    assert lead["referrer"] == "https://google.com/search?q=tge+solar"
    assert lead["landing_url"].endswith("utm_source=google")

    assert client.get("/api/leads").status_code == 401
    assert client.get("/api/leads/metrics").status_code == 401
    headers = _basic_headers("site-user", "site-pass")
    listed = client.get("/api/leads", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["leads"][0]["lead_id"] == lead["lead_id"]

    metrics = client.get("/api/leads/metrics", headers=headers)
    assert metrics.status_code == 200, metrics.text
    metrics_data = metrics.json()
    assert metrics_data["total"] == 1
    assert metrics_data["converted"] == 0
    assert metrics_data["by_source"] == [{"key": "google", "count": 1}]
    assert metrics_data["by_campaign"] == [{"key": "dfw-solar", "count": 1}]


def test_web_lead_lifecycle_update_archive_and_export(tmp_path: Path):
    client = TestClient(create_app(jobs_dir=tmp_path, access_token="secret"))
    headers = _token_headers("secret")
    lead_response = client.post(
        "/api/leads",
        data={
            "contact_name": "Lifecycle Lead",
            "email": "lifecycle@example.com",
            "phone": "817-555-0123",
            "site_address": "905 Crossvine Drive, Mansfield, TX",
            "project_type": "not_sure",
            "monthly_kwh_text": "880 780 720 820 1050 1450 1700 1750 1450 1050 820 860",
        },
    )
    assert lead_response.status_code == 200, lead_response.text
    lead = lead_response.json()["lead"]

    no_auth_update = client.patch(
        f"/api/leads/{lead['lead_id']}",
        json={"status": "contacted"},
    )
    assert no_auth_update.status_code == 401

    update = client.patch(
        f"/api/leads/{lead['lead_id']}",
        headers=headers,
        json={
            "status": "contacted",
            "notes": "Called homeowner; bill requested.",
            "mark_contacted": True,
        },
    )
    assert update.status_code == 200, update.text
    updated = update.json()
    assert updated["status"] == "contacted"
    assert updated["notes"] == "Called homeowner; bill requested."
    assert updated["last_contacted_at"]

    contacted = client.get(
        "/api/leads",
        params={"status": "contacted", "q": "lifecycle"},
        headers=headers,
    )
    assert contacted.status_code == 200
    assert [item["lead_id"] for item in contacted.json()["leads"]] == [lead["lead_id"]]

    export = client.get(
        "/api/leads/export.csv",
        params={"status": "active"},
        headers=headers,
    )
    assert export.status_code == 200
    assert "text/csv" in export.headers["content-type"]
    assert "lifecycle@example.com" in export.text
    assert "Called homeowner; bill requested." in export.text
    assert "monthly_kwh_avg" in export.text
    assert "campaign_source" in export.text

    archive = client.post(
        f"/api/leads/{lead['lead_id']}/archive",
        headers=headers,
    )
    assert archive.status_code == 200, archive.text
    assert archive.json()["status"] == "archived"

    active = client.get("/api/leads", params={"status": "active"}, headers=headers)
    assert active.status_code == 200
    assert lead["lead_id"] not in [item["lead_id"] for item in active.json()["leads"]]

    archived = client.get("/api/leads", params={"status": "archived"}, headers=headers)
    assert archived.status_code == 200
    assert [item["lead_id"] for item in archived.json()["leads"]] == [lead["lead_id"]]


def test_web_lead_digest_draft_and_payload_are_protected(tmp_path: Path):
    client = TestClient(create_app(jobs_dir=tmp_path, access_token="secret"))
    headers = _token_headers("secret")
    lead_response = client.post(
        "/api/leads",
        data={
            "contact_name": "Digest Homeowner",
            "email": "digest@example.com",
            "phone": "817-555-0144",
            "site_address": "905 Crossvine Drive, Mansfield, TX",
            "project_type": "pv_ess",
            "monthly_kwh_text": "1200",
        },
    )
    assert lead_response.status_code == 200, lead_response.text
    lead = lead_response.json()["lead"]

    assert client.get("/api/leads/digest").status_code == 401
    digest = client.get("/api/leads/digest", headers=headers)
    assert digest.status_code == 200, digest.text
    digest_data = digest.json()
    assert digest_data["total"] == 1
    assert digest_data["counts"]["new"] == 1
    assert digest_data["new_leads"][0]["lead_id"] == lead["lead_id"]
    assert "1 new" in digest_data["summary"]

    draft = client.get(
        f"/api/leads/{lead['lead_id']}/followup-draft",
        headers=headers,
    )
    assert draft.status_code == 200, draft.text
    draft_data = draft.json()
    assert draft_data["lead_id"] == lead["lead_id"]
    assert "905 Crossvine Drive" in draft_data["subject"]
    assert "Hi Digest" in draft_data["body"]
    assert "average 1200 kWh/month" in draft_data["body"]
    assert draft_data["mailto_url"].startswith("mailto:digest%40example.com")

    payload = client.get(
        f"/api/leads/{lead['lead_id']}/payload",
        headers=headers,
    )
    assert payload.status_code == 200, payload.text
    payload_data = payload.json()
    assert payload_data["client_name"] == "Digest Homeowner"
    assert payload_data["site_address"] == "905 Crossvine Drive, Mansfield, TX"
    assert payload_data["battery_choice"] == "growatt_apx_20kwh"
    assert payload_data["outputs"]["customer"] is True
    assert payload_data["outputs"]["permit"] is False


def test_web_lead_notifications_are_recorded_and_protected(tmp_path: Path):
    app = create_app(jobs_dir=tmp_path, access_token="secret")
    client = TestClient(app)
    headers = _token_headers("secret")

    lead_response = client.post(
        "/api/leads",
        data={
            "contact_name": "Notify Homeowner",
            "email": "notify@example.com",
            "phone": "817-555-0177",
            "site_address": "2806 Green Circle Drive, Mansfield, TX",
            "project_type": "not_sure",
            "monthly_kwh_text": "1000",
        },
    )
    assert lead_response.status_code == 200, lead_response.text
    lead = lead_response.json()["lead"]

    assert client.get("/api/leads/notifications").status_code == 401
    response = client.get("/api/leads/notifications", headers=headers)
    assert response.status_code == 200, response.text
    notifications = response.json()["notifications"]
    assert len(notifications) == 1
    notification = notifications[0]
    assert notification["lead_id"] == lead["lead_id"]
    assert notification["event"] == "new_lead"
    assert notification["channel"] == "dry_run"
    assert notification["status"] == "sent"
    assert notification["attempts"] == 1
    assert "New TGE Solar lead" in notification["subject"]
    assert notification["payload"]["lead"]["email"] == "notify@example.com"


def test_web_lead_notification_webhook_failure_and_retry(
    tmp_path: Path,
    monkeypatch,
):
    app = create_app(jobs_dir=tmp_path, access_token="secret")
    app.state.lead_notification_config = LeadNotificationConfig(
        mode="webhook",
        webhook_url="https://hooks.example.test/tge-leads",
        timeout_s=0.5,
    )
    client = TestClient(app)
    headers = _token_headers("secret")
    calls: list[dict] = []

    def failing_webhook(url: str, payload: dict, *, timeout_s: float):
        calls.append(payload)
        raise RuntimeError("webhook unavailable")

    monkeypatch.setattr(
        "pvess_calc.web.notifications.post_webhook_json",
        failing_webhook,
    )
    lead_response = client.post(
        "/api/leads",
        data={
            "contact_name": "Webhook Homeowner",
            "email": "webhook@example.com",
            "site_address": "905 Crossvine Drive, Mansfield, TX",
            "project_type": "pv_ess",
        },
    )
    assert lead_response.status_code == 200, lead_response.text
    notifications = client.get("/api/leads/notifications", headers=headers)
    assert notifications.status_code == 200, notifications.text
    notification = notifications.json()["notifications"][0]
    assert notification["status"] == "failed"
    assert notification["channel"] == "webhook"
    assert notification["attempts"] == 1
    assert "webhook unavailable" in notification["error"]
    assert calls[0]["lead"]["email"] == "webhook@example.com"

    def successful_webhook(url: str, payload: dict, *, timeout_s: float):
        calls.append(payload)
        return WebhookResult(status_code=202, body="accepted")

    monkeypatch.setattr(
        "pvess_calc.web.notifications.post_webhook_json",
        successful_webhook,
    )
    retry = client.post(
        f"/api/leads/notifications/{notification['notification_id']}/retry",
        headers=headers,
    )
    assert retry.status_code == 200, retry.text
    retried = retry.json()
    assert retried["status"] == "sent"
    assert retried["attempts"] == 2
    assert "HTTP 202" in retried["response_text"]
    assert calls[-1]["notification_id"] == notification["notification_id"]


def test_web_lead_conversion_creates_customer_estimate_job(tmp_path: Path):
    client = TestClient(create_app(jobs_dir=tmp_path, access_token="secret"))
    headers = _token_headers("secret")
    lead_response = client.post(
        "/api/leads",
        data={
            "contact_name": "Solar Homeowner",
            "email": "homeowner@example.com",
            "site_address": "2806 Green Circle Drive, Mansfield, TX",
            "project_type": "pv_only",
            "monthly_kwh_text": ",".join(str(value) for value in DFW_SIMULATED_MONTHLY_KWH),
        },
    )
    assert lead_response.status_code == 200, lead_response.text
    lead = lead_response.json()["lead"]

    response = client.post(
        f"/api/leads/{lead['lead_id']}/convert",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["lead"]["status"] == "converted"
    assert data["lead"]["converted_job_id"] == data["job"]["job_id"]

    metrics = client.get("/api/leads/metrics", headers=headers)
    assert metrics.status_code == 200, metrics.text
    assert metrics.json()["converted"] == 1

    payload = client.get(
        f"/api/jobs/{data['job']['job_id']}/payload",
        headers=headers,
    )
    assert payload.status_code == 200, payload.text
    stored = payload.json()
    assert stored["client_name"] == "Solar Homeowner"
    assert stored["project_name"] == "2806 Green Circle Drive Estimate Package"
    assert stored["site_address"] == "2806 Green Circle Drive, Mansfield, TX"
    assert stored["location"] == "Mansfield, TX"
    assert stored["battery_choice"] == "none"
    assert stored["battery_quantity"] == 0
    assert stored["monthly_kwh_source"] == "form"
    assert stored["site_data_source"] == "simulated"
    assert stored["outputs"] == {
        "customer": True,
        "permit": False,
        "dxf": False,
        "labels": False,
        "qet": False,
    }

    state = _wait_for_job(
        client,
        data["job"]["job_id"],
        headers=headers,
        timeout_s=30.0,
    )
    assert state["result"]["files"]


def test_web_admin_can_create_operator_tokens(tmp_path: Path):
    client = TestClient(create_app(jobs_dir=tmp_path, access_token="admin-secret"))

    unauthorized = client.post(
        "/api/operators",
        json={"operator_id": "alice", "display_name": "Alice"},
    )
    assert unauthorized.status_code == 401
    assert str(tmp_path) not in unauthorized.text

    response = client.post(
        "/api/operators",
        json={"operator_id": "alice", "display_name": "Alice"},
        headers=_token_headers("admin-secret"),
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["operator_id"] == "alice"
    assert data["display_name"] == "Alice"
    assert data["token"].startswith("op_")

    operator_forbidden = client.post(
        "/api/operators",
        json={"operator_id": "bob", "display_name": "Bob"},
        headers=_token_headers(data["token"]),
    )
    assert operator_forbidden.status_code == 403
    assert str(tmp_path) not in operator_forbidden.text


def test_web_operator_tokens_scope_jobs_payloads_reruns_deletes_and_files(tmp_path: Path):
    client = TestClient(create_app(jobs_dir=tmp_path, access_token="admin-secret"))
    admin_headers = _token_headers("admin-secret")
    alice = client.post(
        "/api/operators",
        json={"operator_id": "alice", "display_name": "Alice"},
        headers=admin_headers,
    ).json()["token"]
    bob = client.post(
        "/api/operators",
        json={"operator_id": "bob", "display_name": "Bob"},
        headers=admin_headers,
    ).json()["token"]
    alice_headers = _token_headers(alice)
    bob_headers = _token_headers(bob)

    alice_state = _submit_and_wait(
        client,
        _light_payload(project_name="Alice Project"),
        headers=alice_headers,
    )
    bob_state = _submit_and_wait(
        client,
        _light_payload(project_name="Bob Project"),
        headers=bob_headers,
    )

    alice_jobs = client.get("/api/jobs", headers=alice_headers).json()["jobs"]
    bob_jobs = client.get("/api/jobs", headers=bob_headers).json()["jobs"]
    assert [job["job_id"] for job in alice_jobs] == [alice_state["job_id"]]
    assert [job["job_id"] for job in bob_jobs] == [bob_state["job_id"]]

    all_jobs = client.get(
        "/api/jobs",
        params={"all_jobs": "true"},
        headers=admin_headers,
    ).json()["jobs"]
    assert {job["job_id"] for job in all_jobs} == {
        alice_state["job_id"],
        bob_state["job_id"],
    }

    bob_job = bob_state["job_id"]
    for method, path in [
        ("get", f"/api/jobs/{bob_job}"),
        ("get", f"/api/jobs/{bob_job}/payload"),
        ("post", f"/api/jobs/{bob_job}/rerun"),
        ("delete", f"/api/jobs/{bob_job}"),
        ("get", f"/files/{bob_job}/inputs.yaml"),
    ]:
        response = getattr(client, method)(path, headers=alice_headers)
        assert response.status_code == 403
        assert str(tmp_path) not in response.text

    admin_payload = client.get(
        f"/api/jobs/{bob_job}/payload",
        headers=admin_headers,
    )
    assert admin_payload.status_code == 200
    assert admin_payload.json()["project_name"] == "Bob Project"

    bob_file = client.get(f"/files/{bob_job}/inputs.yaml", headers=bob_headers)
    assert bob_file.status_code == 200
    assert "Bob Project" in bob_file.text

    alice_all_jobs = client.get(
        "/api/jobs",
        params={"all_jobs": "true"},
        headers=alice_headers,
    )
    assert alice_all_jobs.status_code == 403
    assert str(tmp_path) not in alice_all_jobs.text

    delete_response = client.delete(f"/api/jobs/{bob_job}", headers=bob_headers)
    assert delete_response.status_code == 200
    assert client.get(f"/api/jobs/{bob_job}", headers=bob_headers).status_code == 404


def test_web_project_generation_writes_core_outputs(tmp_path: Path):
    client = _client(tmp_path)
    state = _submit_and_wait(client, _light_payload())
    data = state["result"]
    project_dir = Path(data["project_dir"])

    assert data["status"] == "done"
    assert data["summary"]["modules"] == 8
    assert data["summary"]["system_kw_dc"] == 3.32
    assert data["bom"]["parts_subtotal_usd"] > 0
    assert {c["name"] for c in data["bom"]["categories"]} >= {
        "Major equipment",
        "Electrical BOS",
        "Racking & mounting",
    }
    assert {c["name"] for c in data["bom"]["installed_breakdown"]} >= {
        "Labor, permitting & soft costs",
    }
    assert [tier["name"] for tier in data["bom"]["quote_tiers"]] == [
        "PV-only",
        "Base backup",
        "Large backup",
    ]
    assert (project_dir / "inputs.yaml").exists()
    assert (project_dir / "output" / "calculation.json").exists()
    assert (project_dir / "output" / "report.md").exists()
    assert (project_dir / "output" / "bom-cost.json").exists()
    assert (project_dir / "output" / "bom-cost.csv").exists()
    assert (project_dir / "output" / "artifact-manifest.json").exists()
    assert (project_dir / "output" / "reference-readiness.md").exists()
    assert (project_dir / "output" / "real-data-checklist.md").exists()
    assert (project_dir / "output" / "roof-trace-status.json").exists()
    assert (project_dir / "output" / "roof-trace-status.md").exists()
    assert (project_dir / "output" / "ee4-trace-draft.yaml").exists()
    assert (project_dir / "output" / "trace-module-layout-status.json").exists()
    assert (project_dir / "output" / "trace-module-layout-status.md").exists()
    assert (project_dir / "output" / "r8-validation-status.json").exists()
    assert (project_dir / "output" / "r8-validation-guide.md").exists()
    assert (project_dir / "output" / "roof-workflow-validation.json").exists()
    assert (project_dir / "output" / "roof-workflow-validation.md").exists()
    assert (project_dir / "output" / "r8-step-2-satellite-review.png").exists()
    assert (project_dir / "output" / "satellite-data-chain-audit.json").exists()
    assert (project_dir / "output" / "satellite-data-chain-audit.md").exists()
    assert (project_dir / "output" / "satellite-roof-outline-candidate.json").exists()
    assert (project_dir / "output" / "r8-step-3-roof-trace-layout.pdf").exists()
    assert (project_dir / "output" / "r8-step-4-panel-attachment-layout.pdf").exists()
    archive_path = project_dir / "output" / f"project-package-{state['job_id']}.zip"
    assert archive_path.exists()
    assert {f["label"] for f in data["files"]} >= {
        "Inputs YAML",
        "Calculation JSON",
        "Engineering Report",
        "BOM + Cost JSON",
        "BOM + Cost CSV",
        "Reference Readiness Report",
        "Real Data Checklist",
        "Roof Trace Status JSON",
        "Roof Trace Readiness Report",
        "EE-4 Trace Draft YAML",
        "Trace Module Layout Status JSON",
        "Trace Module Layout Readiness Report",
        "R8 Step 1 Address Confirmation",
        "R8 Validation Status JSON",
        "Roof Workflow Validation JSON",
        "Roof Workflow Validation Report",
        "R8 Step 2 Satellite Review PNG",
        "Satellite Data Chain Audit JSON",
        "Satellite Data Chain Audit Report",
        "Satellite Roof Outline Candidate JSON",
        "R8 Step 3 Roof Trace Layout PDF",
        "R8 Step 4 Panel Attachment Layout PDF",
        "Artifact Manifest JSON",
        "Complete Project ZIP",
    }
    assert {f["category"] for f in data["files"]} >= {
        "Input",
        "Engineering",
        "Cost",
        "Readiness",
        "Verification",
        "Manifest",
        "Archive",
    }
    assert data["source_materials"]["site_data_source"] == "simulated"
    assert data["source_materials"]["roof_trace"]["mode"] == "coarse_roof_sections"
    assert data["source_materials"]["trace_module_layout"]["mode"] == "waiting_for_trace"
    assert data["source_materials"]["r8_validation"]["overall_status"] in {
        "PASS",
        "WARN",
    }
    assert data["source_materials"]["roof_topology"]["stage"] in {
        "needs_roof_evidence",
        "evidence_ready_needs_outline",
        "outline_ready_needs_topology",
    }
    assert data["readiness"]["status"] == "WARN"
    assert data["readiness"]["roof_trace"]["can_ahj_ready"] is False
    assert data["readiness"]["trace_module_layout"]["can_ahj_ready"] is False
    assert [step["code"] for step in data["readiness"]["roof_topology"]["steps"]] == [
        "OSR3",
        "OSR4",
        "OSR5",
        "OSR6",
    ]
    assert data["readiness"]["roof_topology"]["editor"]["available"] is True
    assert data["readiness"]["roof_topology"]["editor"]["trace"]["roof_outline"]
    assert len(data["readiness"]["r8_validation"]["steps"]) == 5
    assert data["readiness"]["counts"]["missing"] > 0

    with zipfile.ZipFile(archive_path) as zf:
        names = set(zf.namelist())
    assert {
        "inputs.yaml",
        "manifest.json",
        "request.json",
        "simulated-site-data.yaml",
        "output/calculation.json",
        "output/report.md",
        "output/bom-cost.json",
        "output/bom-cost.csv",
        "output/artifact-manifest.json",
        "output/reference-readiness.md",
        "output/real-data-checklist.md",
        "output/roof-trace-status.json",
        "output/roof-trace-status.md",
        "output/ee4-trace-draft.yaml",
        "output/trace-module-layout-status.json",
        "output/trace-module-layout-status.md",
        "output/r8-validation-status.json",
        "output/r8-validation-guide.md",
        "output/roof-workflow-validation.json",
        "output/roof-workflow-validation.md",
        "output/r8-step-2-satellite-review.png",
        "output/satellite-data-chain-audit.json",
        "output/satellite-data-chain-audit.md",
        "output/satellite-roof-outline-candidate.json",
        "output/r8-step-3-roof-trace-layout.pdf",
        "output/r8-step-4-panel-attachment-layout.pdf",
    }.issubset(names)

    artifact_manifest = json.loads(
        (project_dir / "output" / "artifact-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert artifact_manifest["project_name"] == "Web Smoke Test"
    assert artifact_manifest["category_counts"]["Cost"] >= 2
    assert any(file["label"] == "BOM + Cost CSV" for file in artifact_manifest["files"])


def test_web_generation_passes_paid_satellite_flag(monkeypatch, tmp_path: Path):
    captured: list[bool] = []

    def fake_r8_artifacts(
        result,
        output_dir: Path,
        *,
        satellite_crop_mode: str = "tight",
        allow_paid_satellite: bool = False,
    ):
        captured.append(allow_paid_satellite)
        output_dir.mkdir(parents=True, exist_ok=True)
        status = {
            "overall_status": "WARN",
            "satellite_crop_mode": satellite_crop_mode,
            "satellite_roof_outline": {
                "status": "WARN",
                "detail": "fake satellite outline",
            },
            "steps": [
                {
                    "step": index,
                    "title": f"Step {index}",
                    "status": "WARN",
                    "artifact": "",
                    "preview": "",
                    "detail": "fake",
                }
                for index in range(1, 6)
            ],
        }
        paths = {
            "status_json": output_dir / "r8-validation-status.json",
            "status_markdown": output_dir / "r8-validation-guide.md",
            "satellite_png": output_dir / "r8-step-2-satellite-review.png",
            "satellite_audit_json": output_dir / "satellite-data-chain-audit.json",
            "satellite_audit_markdown": output_dir / "satellite-data-chain-audit.md",
            "satellite_outline_json": output_dir / "satellite-roof-outline-candidate.json",
            "roof_pdf": output_dir / "r8-step-3-roof-trace-layout.pdf",
            "attachment_pdf": output_dir / "r8-step-4-panel-attachment-layout.pdf",
        }
        paths["status_json"].write_text(json.dumps(status), encoding="utf-8")
        paths["status_markdown"].write_text("# fake\n", encoding="utf-8")
        paths["satellite_png"].write_bytes(b"png")
        paths["satellite_audit_json"].write_text("{}", encoding="utf-8")
        paths["satellite_audit_markdown"].write_text("# audit\n", encoding="utf-8")
        paths["satellite_outline_json"].write_text("{}", encoding="utf-8")
        paths["roof_pdf"].write_bytes(b"%PDF fake")
        paths["attachment_pdf"].write_bytes(b"%PDF fake")
        return {
            "status": status,
            **paths,
            "satellite_outline_yaml": None,
            "satellite_outline_png": None,
            "roof_png": None,
            "attachment_png": None,
        }

    monkeypatch.setattr(web_server, "write_r8_validation_artifacts", fake_r8_artifacts)

    web_server.generate_project(
        WebProjectRequest.model_validate(_light_payload(allow_paid_satellite=True)),
        tmp_path,
        job_id="paid-satellite-on",
    )
    web_server.generate_project(
        WebProjectRequest.model_validate(_light_payload(allow_paid_satellite=False)),
        tmp_path,
        job_id="paid-satellite-off",
    )

    assert captured == [True, False]


def test_web_form_uploads_step2_roof_satellite_image(tmp_path: Path):
    client = _client(tmp_path)
    state = _submit_form_and_wait(
        client,
        _light_payload(),
        files={
            "roof_satellite_image": (
                "recent-satellite.png",
                b"\x89PNG\r\n\x1a\nfake-uploaded-satellite",
                "image/png",
            )
        },
    )
    data = state["result"]
    project_dir = Path(data["project_dir"])

    assert data["source_materials"]["roof_satellite_image_uploaded"] is True
    assert data["source_materials"]["roof_satellite_image_file"] == (
        "recent-satellite.png"
    )
    assert data["readiness"]["roof_topology"]["roof_satellite_image_uploaded"] is True
    assert data["readiness"]["roof_topology"]["evidence_status"] == "PASS"
    uploaded = project_dir / "source_materials" / "roof" / "recent-satellite.png"
    assert uploaded.exists()
    assert any(
        file["label"] == "Uploaded Roof Satellite Image"
        for file in data["files"]
    )


def test_web_accept_roof_trace_draft_updates_inputs_and_gate(tmp_path: Path):
    client = _client(tmp_path)
    state = _submit_and_wait(client, _light_payload())
    job_id = state["job_id"]
    first = state["result"]
    project_dir = Path(first["project_dir"])

    assert first["readiness"]["roof_trace"]["can_ahj_ready"] is False

    response = client.post(
        f"/api/jobs/{job_id}/roof-trace/accept-draft",
        json={"source": "draft_yaml", "rerun": True},
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["job_id"] == job_id
    assert data["readiness"]["roof_trace"]["mode"] == "traced"
    assert data["readiness"]["roof_trace"]["can_ahj_ready"] is True
    assert data["readiness"]["trace_module_layout"]["mode"] == "traced_layout"
    assert data["readiness"]["trace_module_layout"]["can_ahj_ready"] is True
    assert data["readiness"]["roof_topology"]["stage"] == "panel_layout_confirmed"
    assert data["readiness"]["roof_topology"]["can_use_for_internal_layout"] is True
    assert data["source_materials"]["roof_topology"]["target_modules"] == (
        data["source_materials"]["roof_topology"]["placed_modules"]
    )
    assert data["readiness"]["r8_validation"]["steps"][2]["status"] in {"PASS", "WARN"}
    assert data["readiness"]["r8_validation"]["steps"][3]["status"] in {"PASS", "WARN"}
    assert not any(
        blocker["key"] == "site.ee4_trace"
        for blocker in data["readiness"]["gate"]["blockers"]
    )
    assert not any(
        blocker["key"] == "site.trace_module_layout"
        for blocker in data["readiness"]["gate"]["blockers"]
    )

    request_payload = json.loads(
        (project_dir / "request.json").read_text(encoding="utf-8")
    )
    assert request_payload["ee4_trace"]["enabled"] is True
    assert request_payload["ee4_trace_reviewed"] is True
    inputs = Inputs.from_yaml(project_dir / "inputs.yaml")
    assert inputs.site.ee4_trace.enabled is True
    assert inputs.site.ee4_trace.roof_outline is not None
    assert len(inputs.site.roof_sections) == 1
    assert inputs.site.roof_sections[0].shape == "polygon"
    assert inputs.site.roof_sections[0].name == "Trace skeleton roof outline"


def test_web_accepts_manual_roof_trace_json(tmp_path: Path):
    client = _client(tmp_path)
    state = _submit_and_wait(client, _light_payload())
    job_id = state["job_id"]
    project_dir = Path(state["result"]["project_dir"])
    manual_trace = {
        "enabled": True,
        "roof_outline": {
            "name": "Manual reviewed roof outline",
            "vertices": [[-30, -30], [120, -30], [120, 90], [-30, 90]],
        },
        "roof_lines": [{"kind": "ridge", "points": [[-30, 30], [120, 30]]}],
        "fire_pathways": [
            {
                "name": "Manual fire setback",
                "vertices": [[-30, 89], [120, 89], [120, 90], [-30, 90]],
            }
        ],
        "symbols": [],
    }

    response = client.post(
        f"/api/jobs/{job_id}/roof-trace/accept-draft",
        json={"source": "manual", "trace": manual_trace, "rerun": True},
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["readiness"]["roof_trace"]["mode"] == "traced"
    assert data["readiness"]["trace_module_layout"]["mode"] == "traced_layout"
    request_payload = json.loads(
        (project_dir / "request.json").read_text(encoding="utf-8")
    )
    assert request_payload["ee4_trace"]["enabled"] is True
    assert request_payload["ee4_trace_reviewed"] is True
    assert request_payload["ee4_trace"]["roof_outline"]["name"] == (
        "Manual reviewed roof outline"
    )
    inputs = Inputs.from_yaml(project_dir / "inputs.yaml")
    assert inputs.site.ee4_trace.roof_outline is not None
    assert inputs.site.ee4_trace.roof_outline.name == (
        "Manual reviewed roof outline"
    )


def test_web_accepts_edited_roof_outline_only_and_completes_topology(tmp_path: Path):
    client = _client(tmp_path)
    state = _submit_and_wait(client, _light_payload())
    job_id = state["job_id"]
    project_dir = Path(state["result"]["project_dir"])
    edited_trace = {
        "enabled": True,
        "roof_outline": {
            "name": "Reviewed Step 2 roof outline",
            "vertices": [[0, 0], [90, 0], [90, 55], [0, 55]],
        },
    }

    response = client.post(
        f"/api/jobs/{job_id}/roof-trace/accept-draft",
        json={"source": "manual", "trace": edited_trace, "rerun": True},
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["readiness"]["roof_topology"]["stage"] == "panel_layout_confirmed"
    request_payload = json.loads(
        (project_dir / "request.json").read_text(encoding="utf-8")
    )
    assert request_payload["ee4_trace"]["roof_lines"]
    assert request_payload["ee4_trace"]["fire_pathways"]
    inputs = Inputs.from_yaml(project_dir / "inputs.yaml")
    assert inputs.site.roof_sections[0].shape == "polygon"
    assert inputs.site.roof_sections[0].module_count == request_payload["modules"]


def test_web_accepts_satellite_roof_outline_candidate_yaml(tmp_path: Path):
    client = _client(tmp_path)
    state = _submit_and_wait(client, _light_payload())
    job_id = state["job_id"]
    project_dir = Path(state["result"]["project_dir"])
    candidate_yaml = project_dir / "output" / "satellite-ee4-trace-candidate.yaml"
    candidate_yaml.write_text(
        yaml.safe_dump({
            "site": {
                "ee4_trace": {
                    "enabled": True,
                    "roof_outline": {
                        "name": "Satellite mask roof outline candidate",
                        "vertices": [
                            [-20, -10],
                            [80, -10],
                            [80, 45],
                            [35, 65],
                            [-20, 45],
                        ],
                    },
                    "roof_facets": [],
                    "roof_lines": [],
                    "fire_pathways": [],
                    "symbols": [],
                }
            }
        }, sort_keys=False),
        encoding="utf-8",
    )

    response = client.post(
        f"/api/jobs/{job_id}/roof-trace/accept-draft",
        json={"source": "satellite_candidate", "rerun": True},
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["readiness"]["roof_trace"]["mode"] == "traced"
    assert data["readiness"]["trace_module_layout"]["mode"] == "traced_layout"
    assert data["readiness"]["trace_module_layout"]["can_ahj_ready"] is True
    request_payload = json.loads(
        (project_dir / "request.json").read_text(encoding="utf-8")
    )
    assert request_payload["ee4_trace_reviewed"] is True
    assert request_payload["ee4_trace"]["roof_outline"]["name"] == (
        "Satellite mask roof outline candidate"
    )
    assert request_payload["ee4_trace"]["roof_lines"]
    assert request_payload["ee4_trace"]["fire_pathways"]
    inputs = Inputs.from_yaml(project_dir / "inputs.yaml")
    assert inputs.site.ee4_trace.enabled is True
    assert inputs.site.ee4_trace.roof_outline is not None
    assert inputs.site.ee4_trace.roof_outline.name == (
        "Satellite mask roof outline candidate"
    )


def test_web_updates_satellite_review_range_and_regenerates(tmp_path: Path):
    client = _client(tmp_path)
    state = _submit_and_wait(
        client,
        _light_payload(satellite_crop_mode="wide"),
    )
    job_id = state["job_id"]
    project_dir = Path(state["result"]["project_dir"])

    response = client.post(
        f"/api/jobs/{job_id}/satellite-review-range",
        json={"satellite_crop_mode": "target", "rerun": True},
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["job_id"] == job_id
    assert data["readiness"]["r8_validation"]["satellite_crop_mode"] == "target"
    request_payload = json.loads(
        (project_dir / "request.json").read_text(encoding="utf-8")
    )
    assert request_payload["satellite_crop_mode"] == "target"


def test_web_generates_roof_topology_skill_proposal(tmp_path: Path):
    client = _client(tmp_path)
    state = _submit_and_wait(client, _light_payload())
    job_id = state["job_id"]
    project_dir = Path(state["result"]["project_dir"])

    response = client.post(
        f"/api/jobs/{job_id}/roof-topology/proposal",
        json={"mode": "deterministic", "strict": False},
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["job_id"] == job_id
    assert data["qa"]["source"] in {
        "satellite_candidate",
        "request_payload",
        "ee4_trace_draft",
        "generated_skeleton",
    }
    assert (project_dir / "output" / "roof-topology-vision" / "roof-topology-qa.json").exists()
    assert (project_dir / "output" / "roof-topology-vision" / "site-ee4-trace-proposed.yaml").exists()
    assert {
        "Roof Topology Proposal YAML",
        "Roof Topology Proposal QA JSON",
        "Roof Topology Proposal QA Report",
        "Roof Topology Proposal Review PDF",
    }.issubset({file["label"] for file in data["files"]})


def test_web_preflight_returns_cost_and_intake_warnings(tmp_path: Path):
    client = _client(tmp_path)
    response = client.post("/api/preflight", json=_light_payload())

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "WARN"
    assert data["summary"]["system_kw_dc"] == 3.32
    assert data["estimate"]["installed_cost_usd"] > 0
    assert data["intake"]["ready"] < data["intake"]["total"]
    assert {
        issue["field"] for issue in data["issues"]
    } >= {"site_data_source", "monthly_kwh", "structural_letter", "spec_sheets"}


def test_web_cost_override_is_reflected_in_bom_payload(tmp_path: Path):
    client = _client(tmp_path)
    state = _submit_and_wait(
        client,
        _light_payload(
            pv_turnkey_usd_per_w=2.0,
            inverter_cost_usd_total=1000,
            battery_quantity=1,
            battery_capacity_kwh_each=5,
            battery_cost_usd_total=3000,
        ),
    )

    bom = state["result"]["bom"]
    assert bom["installed_cost_usd"] == 10640.0
    assert bom["cost_after_itc_usd"] == 7448.0
    assert bom["cost_source"] == "installer-override"
    assert len(bom["quote_tiers"]) == 3


def test_web_quote_tiers_are_monotonic_by_backup_size(tmp_path: Path):
    client = _client(tmp_path)
    state = _submit_and_wait(client, _light_payload())

    tiers = state["result"]["bom"]["quote_tiers"]
    after_itc = [tier["cost_after_itc_usd"] for tier in tiers]
    assert after_itc == sorted(after_itc)
    assert tiers[0]["backup_summary"] == "none (grid-tied)"
    assert tiers[1]["battery_kwh_total"] == 16.0
    assert tiers[2]["battery_kwh_total"] == 20.0


def test_web_inverter_choice_maps_to_us_model(tmp_path: Path):
    client = _client(tmp_path)
    state = _submit_and_wait(
        client,
        _light_payload(inverter_choice="hoymiles"),
    )

    data = state["result"]
    project_dir = Path(data["project_dir"])
    inputs_yaml = (project_dir / "inputs.yaml").read_text(encoding="utf-8")
    assert "brand: Hoymiles" in inputs_yaml
    assert "model: HYS-11.5LV-USG1" in inputs_yaml
    assert data["summary"]["inverter_brand"] == "Hoymiles"
    assert data["summary"]["inverter_model"] == "HYS-11.5LV-USG1"


def test_web_module_and_battery_choices_map_to_device_library(tmp_path: Path):
    client = _client(tmp_path)
    state = _submit_and_wait(
        client,
        _light_payload(
            modules=6,
            strings=2,
            module_choice="rec_alpha_pure_410",
            battery_choice="growatt_apx_20kwh",
            battery_quantity=1,
        ),
    )

    data = state["result"]
    project_dir = Path(data["project_dir"])
    inputs_yaml = (project_dir / "inputs.yaml").read_text(encoding="utf-8")
    assert "brand: REC" in inputs_yaml
    assert "model: Alpha Pure REC410AA" in inputs_yaml
    assert "brand: Growatt" in inputs_yaml
    assert "model: APX HV 20K" in inputs_yaml
    assert data["summary"]["module_model"] == "Alpha Pure REC410AA"
    assert data["summary"]["battery_model"] == "APX HV 20K"


def test_web_rejects_non_divisible_string_count(tmp_path: Path):
    client = _client(tmp_path)
    response = client.post("/api/projects", json=_light_payload(modules=9, strings=2))

    assert response.status_code == 422
    assert "modules must be divisible by strings" in response.text


def test_web_download_rejects_path_traversal(tmp_path: Path):
    client = _client(tmp_path)
    state = _submit_and_wait(client, _light_payload())
    job_id = state["job_id"]

    traversal = client.get(f"/files/{job_id}/%2E%2E/inputs.yaml")
    assert traversal.status_code in {403, 404}


def test_web_form_upload_injects_site_photos_and_source_manifest(tmp_path: Path):
    client = _client(tmp_path)
    state = _submit_form_and_wait(
        client,
        _light_payload(site_data_source="real"),
        files={
            "front_elevation": ("../../front.jpg", b"fake image bytes", "image/jpeg"),
            "utility_bill": ("bill.pdf", b"%PDF-1.4\n", "application/pdf"),
        },
    )

    data = state["result"]
    project_dir = Path(data["project_dir"])
    inputs = yaml.safe_load((project_dir / "inputs.yaml").read_text(encoding="utf-8"))
    photos = inputs["project"]["site_photos"]

    assert data["source_materials"]["site_data_source"] == "real"
    assert data["source_materials"]["site_photo_count"] == 1
    assert data["source_materials"]["utility_bill_uploaded"] is True
    assert data["readiness"]["needs_review"] is True
    assert any(
        item["key"] == "project.site_photos"
        for item in data["readiness"]["review_items"]
    )
    assert photos == [{
        "kind": "front_elevation",
        "path": photos[0]["path"],
        "caption": "Front elevation",
    }]
    saved_photo = Path(photos[0]["path"])
    assert saved_photo.exists()
    assert saved_photo.name == "front.jpg"
    assert saved_photo.is_relative_to(project_dir)
    assert (project_dir / "source_materials" / "utility" / "bill.pdf").exists()

    source_pack = yaml.safe_load(
        (project_dir / "simulated-site-data.yaml").read_text(encoding="utf-8")
    )
    assert source_pack["sources"]["project.site_photos"]["status"] == "missing"
    assert source_pack["sources"]["project.site_photos"]["files"] == [
        "source_materials/photos/front.jpg"
    ]


def test_web_form_parses_utility_csv_and_classifies_unsorted_uploads(tmp_path: Path):
    client = _client(tmp_path)
    csv_rows = "month,kwh\n" + "\n".join(
        f"2025-{idx:02d},{value}"
        for idx, value in enumerate(DFW_SIMULATED_MONTHLY_KWH, start=1)
    )
    state = _submit_form_and_wait(
        client,
        _light_payload(
            site_data_source="real",
            monthly_kwh=[1] * 12,
            outputs={
                "customer": False,
                "permit": False,
                "dxf": False,
                "labels": False,
                "qet": False,
            },
        ),
        files={
            "utility_bill": ("smart-meter-usage.csv", csv_rows.encode(), "text/csv"),
            "site_photos_auto": ("roof-array-photo.jpg", b"image", "image/jpeg"),
            "spec_sheets_auto": ("growatt-inverter-spec.pdf", b"%PDF", "application/pdf"),
        },
    )

    data = state["result"]
    project_dir = Path(data["project_dir"])
    inputs = yaml.safe_load((project_dir / "inputs.yaml").read_text(encoding="utf-8"))

    assert inputs["loads"]["monthly_kwh"] == DFW_SIMULATED_MONTHLY_KWH
    assert data["source_materials"]["monthly_kwh_source"] == "utility_file"
    assert data["source_materials"]["utility_bill_parse"]["status"] == "parsed"
    assert data["source_materials"]["site_photo_count"] == 1
    assert data["source_materials"]["photo_classifications"][0]["classified_kind"] == "roof"
    assert data["source_materials"]["spec_classifications"][0]["classified_equipment"] == "inverter"


def test_web_real_intake_maps_to_inputs_yaml_and_readiness(tmp_path: Path):
    client = _client(tmp_path)
    monthly = [820, 740, 690, 780, 1020, 1350, 1480, 1520, 1380, 1010, 760, 790]
    state = _submit_and_wait(
        client,
        _light_payload(
            coordinates="33.1414, -96.8012",
            apn="R-12345",
            meter_number="153468971",
            meter_location="Exterior garage wall",
            meter_esid="10443720007628433",
            engineer_firm="Wyssling Consulting",
            engineer_address="76 N Meadowbrook Dr, Alpine UT",
            engineer_email="engineer@example.com",
            engineer_phone="(201) 874-3483",
            engineer_firm_number="20109",
            installer_company="Texas Green Eco Power",
            installer_address="2806 Green Cir Dr, Mansfield, TX",
            roof_info_type="Comp Shingle",
            roof_info_height_ft=25,
            roof_construction="Prefabricated trusses",
            roof_condition="good",
            roof_framing='2x4 @ 24" O.C.',
            roof_attic_access="accessible",
            decking_thickness_in=0.5,
            roof_layers=1,
            battery_quantity=1,
            battery_capacity_kwh_each=16,
            battery_install_location="garage",
            distance_to_doorway_ft=4.5,
            distance_to_window_ft=6,
            distance_to_egress_ft=5,
            monthly_kwh=monthly,
            msp_x_ft=72,
            msp_y_ft=34,
            inverter_x_ft=64,
            inverter_y_ft=34,
            ac_disconnect_x_ft=68,
            ac_disconnect_y_ft=34,
            ess_x_ft=60,
            ess_y_ft=32,
        ),
    )

    data = state["result"]
    project_dir = Path(data["project_dir"])
    inputs = yaml.safe_load((project_dir / "inputs.yaml").read_text(encoding="utf-8"))

    assert inputs["project"]["coordinates"] == "33.1414, -96.8012"
    assert inputs["project"]["apn"] == "R-12345"
    assert inputs["project"]["meter_info"]["number"] == "153468971"
    assert inputs["project"]["meter_info"]["esid"] == "10443720007628433"
    assert inputs["project"]["roof_info"]["condition"] == "good"
    assert inputs["design_engineer"]["firm"] == "Wyssling Consulting"
    assert inputs["installer"]["company"] == "Texas Green Eco Power"
    assert inputs["battery"]["install_location"] == "garage"
    assert inputs["loads"]["monthly_kwh"] == monthly
    assert inputs["site"]["equipment_locations"]["msp"]["label"] == "MSP"
    assert inputs["site"]["equipment_locations"]["inverters"][0]["label"] == "INV-1"
    assert data["source_materials"]["monthly_kwh_count"] == 12
    assert data["source_materials"]["equipment_locations_ready"] is True
    assert not any(
        item["key"] == "site.equipment_locations"
        for item in data["readiness"]["review_items"]
    )


def test_web_form_uploads_structural_and_spec_sheets(tmp_path: Path):
    client = _client(tmp_path)
    state = _submit_form_and_wait(
        client,
        _light_payload(site_data_source="real"),
        files={
            "structural_letter": (
                "structural.pdf", b"%PDF-1.4\nstructural", "application/pdf",
            ),
            "spec_module": (
                "talesun.pdf", b"%PDF-1.4\nmodule", "application/pdf",
            ),
            "spec_inverter": (
                "growatt.pdf", b"%PDF-1.4\ninverter", "application/pdf",
            ),
        },
    )

    data = state["result"]
    project_dir = Path(data["project_dir"])
    inputs = yaml.safe_load((project_dir / "inputs.yaml").read_text(encoding="utf-8"))

    structural = Path(inputs["project"]["structural_letter_pdf"])
    specs = inputs["project"]["spec_sheets"]
    assert structural.exists()
    assert structural.is_relative_to(project_dir)
    assert {spec["equipment"] for spec in specs} == {"module", "inverter"}
    assert all(Path(spec["path"]).exists() for spec in specs)
    assert data["source_materials"]["structural_letter_uploaded"] is True
    assert data["source_materials"]["spec_sheet_count"] == 2

    archive_path = project_dir / "output" / f"project-package-{state['job_id']}.zip"
    with zipfile.ZipFile(archive_path) as zf:
        names = set(zf.namelist())
    assert "source_materials/structural/structural.pdf" in names
    assert "source_materials/spec_sheets/talesun.pdf" in names
    assert "source_materials/spec_sheets/growatt.pdf" in names


def test_web_form_simulated_mode_creates_mock_photos_for_permit(tmp_path: Path):
    client = _client(tmp_path)
    payload = _light_payload(
        outputs={
            "customer": False,
            "permit": True,
            "dxf": False,
            "labels": False,
            "qet": False,
        },
    )
    state = _submit_form_and_wait(client, payload, timeout_s=40.0)

    data = state["result"]
    project_dir = Path(data["project_dir"])
    inputs = yaml.safe_load((project_dir / "inputs.yaml").read_text(encoding="utf-8"))
    photos = inputs["project"]["site_photos"]

    assert data["source_materials"]["site_photo_count"] == 6
    assert data["source_materials"]["missing_photo_kinds"] == []
    assert len(photos) == 6
    assert all(Path(photo["path"]).exists() for photo in photos)
    assert (project_dir / "simulated-site-data.yaml").exists()
    archive_path = project_dir / "output" / f"project-package-{state['job_id']}.zip"
    with zipfile.ZipFile(archive_path) as zf:
        names = set(zf.namelist())
    assert "source_materials/photos/mock-front-elevation.png" in names
    assert "source_materials/photos/mock-equipment-location.png" in names


def test_web_job_history_lists_completed_job(tmp_path: Path):
    client = _client(tmp_path)
    state = _submit_and_wait(client, _light_payload(project_name="History Smoke"))

    response = client.get("/api/jobs")
    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert jobs
    assert jobs[0]["job_id"] == state["job_id"]
    assert jobs[0]["status"] == "done"
    assert jobs[0]["result"]["summary"]["project_name"] == "History Smoke"


def test_web_job_history_empty_database_returns_empty_list(tmp_path: Path):
    client = _client(tmp_path)

    response = client.get("/api/jobs")

    assert response.status_code == 200
    assert response.json()["jobs"] == []
    assert (tmp_path / "web-jobs.sqlite3").exists()


def test_web_job_history_imports_legacy_status_json(tmp_path: Path):
    now = datetime.now(timezone.utc).isoformat()
    legacy_dir = tmp_path / "legacy-job"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "request.json").write_text(
        json.dumps({
            "project_name": "Legacy Imported",
            "site_address": "101 Legacy Lane, Mansfield, TX",
            "location": "Mansfield, TX",
        }),
        encoding="utf-8",
    )
    (legacy_dir / "job-status.json").write_text(
        json.dumps({
            "job_id": "legacy-job",
            "project_dir": str(legacy_dir),
            "status": "done",
            "progress": 100,
            "stage": "done",
            "message": "legacy complete",
            "created_at": now,
            "updated_at": now,
            "result": {
                "summary": {"project_name": "Legacy Imported"},
                "bom": {"installed_cost_usd": 12345},
                "source_materials": {"site_data_source": "simulated"},
                "readiness": {"status": "WARN"},
                "files": [
                    {
                        "label": "Inputs YAML",
                        "path": "inputs.yaml",
                        "url": "/files/legacy-job/inputs.yaml",
                        "bytes": 100,
                        "category": "Input",
                        "kind": "yaml",
                    }
                ],
            },
            "error": None,
        }),
        encoding="utf-8",
    )
    client = _client(tmp_path)

    response = client.get("/api/jobs", params={"q": "Legacy Lane"})

    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["job_id"] == "legacy-job"
    assert jobs[0]["result"]["summary"]["project_name"] == "Legacy Imported"
    artifacts = client.app.state.job_store.list_artifacts("legacy-job")
    assert [artifact["path"] for artifact in artifacts] == ["inputs.yaml"]


def test_web_static_readiness_surfaces_artifact_review_counts():
    script = Path("src/pvess_calc/web/static/app.js").read_text(encoding="utf-8")

    assert "Artifact reviews" in script
    assert "required_artifact_reviews" in script
    assert "pending_required_artifact_review_count" in script
    assert "Package map" in script
    assert "Permit drawing set" in script
    assert "Evidence readiness" in script
    assert "Advanced downloads" in script
    assert "Final handoff" in script
    assert "artifactReviewPageIndex" in script
    assert "review-focus-mode" in script
    assert "buildPermitPdfReviewPages" in script
    assert "wide-review" in script
    assert "Status details" in script
    assert "reviewPageNavCode" in script
    assert "navSubtitle" in script
    assert "Structural review draft" in script
    assert "D1" in script
    assert "core" in script
    assert "hydrateMarkdownPreviews" in script
    assert "markdown-preview" in script
    assert "function requestUrl" in script
    assert "target.username = \"\"" in script
    assert "fetch(requestUrl(url)" in script
    assert "fetch(requestUrl(node.dataset.markdownUrl)" in script
    assert "runRoofPreview" in script
    assert "renderRoofPreviewResult" in script
    assert "data-roof-preview-action" in script
    assert "Roof topology draft" in script
    assert "Accept full topology and regenerate preview" in script
    assert "Accept satellite topology and regenerate preview" in script
    assert "Editable roof outline" in script
    assert "Tighten 5%" in script
    assert "Save edited outline" in script
    assert "Generate skill topology proposal" in script


def test_web_static_file_upload_controls_use_english_labels():
    script = Path("src/pvess_calc/web/static/app.js").read_text(encoding="utf-8")

    assert "Choose file" in script
    assert "Choose files" in script
    assert "No file selected" in script


def test_web_static_step5_quick_estimate_is_not_a_blocking_warning():
    script = Path("src/pvess_calc/web/static/app.js").read_text(encoding="utf-8")
    index = Path("src/pvess_calc/web/static/index.html").read_text(encoding="utf-8")

    assert "Quick estimate evidence selected." in script
    assert "AHJ-ready handoff requires uploaded field evidence." in script
    assert "Quick estimate mode can proceed, but AHJ-ready review needs uploaded field evidence." not in script
    assert "20260523-step5-evidence" in index
    assert "No files selected" in script


def test_web_job_history_filters_and_indexes_artifacts(tmp_path: Path):
    client = _client(tmp_path)
    state = _submit_and_wait(
        client,
        _light_payload(
            project_name="Filtered History",
            site_address="905 Crossvine Drive, Mansfield, TX",
        ),
    )
    _submit_and_wait(
        client,
        _light_payload(
            project_name="Other History",
            site_address="2806 Green Circle Drive, Mansfield, TX",
        ),
    )
    today = datetime.now(timezone.utc).date().isoformat()

    filtered = client.get(
        "/api/jobs",
        params={
            "status": "done",
            "q": "Crossvine",
            "created_from": today,
            "created_to": today,
        },
    )

    assert filtered.status_code == 200
    jobs = filtered.json()["jobs"]
    assert [job["job_id"] for job in jobs] == [state["job_id"]]
    artifacts = client.app.state.job_store.list_artifacts(state["job_id"])
    assert len(artifacts) == len(state["result"]["files"])
    assert {artifact["path"] for artifact in artifacts} == {
        file["path"] for file in state["result"]["files"]
    }


def test_web_job_payload_rerun_and_delete(tmp_path: Path):
    client = _client(tmp_path)
    state = _submit_and_wait(
        client,
        _light_payload(project_name="Rerun Source", coordinates="33.1,-96.8"),
    )
    job_id = state["job_id"]

    payload_response = client.get(f"/api/jobs/{job_id}/payload")
    assert payload_response.status_code == 200
    assert payload_response.json()["project_name"] == "Rerun Source"
    assert payload_response.json()["coordinates"] == "33.1,-96.8"

    rerun_response = client.post(f"/api/jobs/{job_id}/rerun")
    assert rerun_response.status_code == 200, rerun_response.text
    rerun_state = rerun_response.json()
    assert rerun_state["job_id"] != job_id
    deadline = time.time() + 20.0
    while time.time() < deadline:
        status = client.get(f"/api/jobs/{rerun_state['job_id']}")
        assert status.status_code == 200, status.text
        rerun_state = status.json()
        if rerun_state["status"] == "done":
            break
        if rerun_state["status"] == "failed":
            raise AssertionError(rerun_state.get("error"))
        time.sleep(0.1)
    assert rerun_state["status"] == "done"
    assert rerun_state["result"]["summary"]["project_name"] == "Rerun Source"

    delete_response = client.delete(f"/api/jobs/{job_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] == job_id
    assert client.get(f"/api/jobs/{job_id}").status_code == 404
    assert client.app.state.job_store.get_state(job_id) is None
    assert not Path(state["project_dir"]).exists()


def test_web_artifact_reviews_persist_with_job(tmp_path: Path):
    client = _client(tmp_path)
    state = _submit_and_wait(client, _light_payload(project_name="Reviewable Job"))
    job_id = state["job_id"]

    update = client.post(
        f"/api/jobs/{job_id}/reviews",
        json={
            "path": "inputs.yaml",
            "status": "approved_internal",
            "note": "checked",
        },
    )

    assert update.status_code == 200, update.text
    assert update.json()["reviews"]["inputs.yaml"]["status"] == "approved_internal"

    revision = client.post(
        f"/api/jobs/{job_id}/reviews",
        json={
            "path": "inputs.yaml",
            "status": "needs_revision",
            "note": "fix inputs",
        },
    )

    assert revision.status_code == 200, revision.text
    assert revision.json()["gate"]["can_submit_to_ahj"] is False
    assert any(
        blocker["field"] == "artifact_reviews"
        for blocker in revision.json()["gate"]["blockers"]
    )

    reloaded = _client(tmp_path)
    response = reloaded.get(f"/api/jobs/{job_id}/reviews")

    assert response.status_code == 200
    assert response.json()["reviews"]["inputs.yaml"]["note"] == "fix inputs"
    assert (Path(state["project_dir"]) / "review-status.json").exists()


def test_web_sync_project_writes_status_json_and_sqlite(tmp_path: Path):
    client = _client(tmp_path)

    response = client.post("/api/projects/sync", json=_light_payload(project_name="Sync Job"))

    assert response.status_code == 200, response.text
    data = response.json()
    project_dir = Path(data["project_dir"])
    assert (project_dir / "job-status.json").exists()
    stored = client.app.state.job_store.get_state(data["job_id"])
    assert stored is not None
    assert stored["status"] == "done"
    assert stored["result"]["summary"]["project_name"] == "Sync Job"


def test_web_package_qa_runs_and_persists_outputs(tmp_path: Path):
    client = _client(tmp_path)
    state = _submit_and_wait(client, _light_payload(project_name="QA Job"))
    job_id = state["job_id"]

    response = client.post(f"/api/jobs/{job_id}/qa")

    assert response.status_code == 200, response.text
    data = response.json()
    qa = data["package_qa"]
    project_dir = Path(state["project_dir"])
    assert qa["status"] in {"PASS", "WARN"}
    assert qa["doctor"]["total"] > 0
    assert qa["archive"]["status"] == "PASS"
    assert (project_dir / "output" / "package-qa.json").exists()
    assert (project_dir / "output" / "package-qa.md").exists()
    assert any(file["label"] == "Package QA JSON" for file in data["files"])
    assert any(file["category"] == "QA" for file in data["files"])

    archive = next(
        file for file in data["files"]
        if file["label"] == "Complete Project ZIP"
    )
    with zipfile.ZipFile(project_dir / archive["path"]) as zf:
        names = set(zf.namelist())
    assert "output/package-qa.json" in names
    assert "output/package-qa.md" in names

    reloaded = _client(tmp_path)
    status = reloaded.get(f"/api/jobs/{job_id}")
    assert status.status_code == 200
    result = status.json()["result"]
    assert result["package_qa"]["archive"]["status"] == "PASS"
    assert result["readiness"]["gate"]["package_qa_status"] == qa["status"]

    jobs = reloaded.get("/api/jobs").json()["jobs"]
    listed = next(job for job in jobs if job["job_id"] == job_id)
    assert listed["result"]["package_qa"]["archive"]["status"] == "PASS"


def test_web_ahj_gate_blocks_simulated_source_materials(tmp_path: Path):
    payload = WebProjectRequest.model_validate(_light_payload(site_data_source="simulated"))
    gate = build_ahj_gate(
        payload=payload,
        source_materials=build_source_materials(payload),
        readiness={"status": "WARN"},
        files=[],
        review_state={},
    )

    assert gate["level"] == "Estimate only"
    assert gate["can_submit_to_ahj"] is False
    assert any(blocker["field"] == "site_data_source" for blocker in gate["blockers"])


def test_web_ahj_gate_allows_real_pv_only_candidate(tmp_path: Path):
    payload = WebProjectRequest.model_validate(
        _complete_real_payload(
            battery_choice="none",
            battery_quantity=0,
            battery_capacity_kwh_each=0,
        )
    )
    files = _gate_files(tmp_path)
    gate = build_ahj_gate(
        payload=payload,
        source_materials=build_source_materials(payload),
        readiness={"status": "PASS"},
        package_qa={"status": "PASS"},
        files=files,
        review_state=_approved_reviews(files),
    )

    assert gate["level"] == "AHJ-ready candidate"
    assert gate["can_submit_to_ahj"] is True
    assert gate["blockers"] == []
    assert gate["required_artifact_review_count"] == 4
    assert gate["pending_required_artifact_review_count"] == 0
    assert [
        item["status"] for item in gate["required_artifact_reviews"]
    ] == ["approved_internal"] * 4


def test_web_ahj_gate_blocks_unverified_roof_trace(tmp_path: Path):
    payload = WebProjectRequest.model_validate(
        _complete_real_payload(
            battery_choice="none",
            battery_quantity=0,
            battery_capacity_kwh_each=0,
        )
    )
    files = _gate_files(tmp_path)
    roof_trace = {
        "status": "WARN",
        "mode": "schematic_segments",
        "label": "Schematic roof segments",
        "can_ahj_ready": False,
        "detail": "The roof outline is not traced.",
    }
    gate = build_ahj_gate(
        payload=payload,
        source_materials=build_source_materials(payload, roof_trace=roof_trace),
        readiness={"status": "PASS", "roof_trace": roof_trace},
        package_qa={"status": "PASS"},
        files=files,
        review_state=_approved_reviews(files),
    )

    assert gate["level"] == "Internal review"
    assert gate["can_submit_to_ahj"] is False
    assert any(
        blocker["key"] == "site.ee4_trace"
        and blocker["field"] == "site.ee4_trace"
        for blocker in gate["blockers"]
    )


def test_web_ahj_gate_blocks_unverified_trace_module_layout(tmp_path: Path):
    payload = WebProjectRequest.model_validate(
        _complete_real_payload(
            battery_choice="none",
            battery_quantity=0,
            battery_capacity_kwh_each=0,
        )
    )
    files = _gate_files(tmp_path)
    roof_trace = {
        "status": "PASS",
        "mode": "traced",
        "label": "Verified traced roof",
        "can_ahj_ready": True,
        "detail": "The roof outline is traced.",
    }
    trace_module_layout = {
        "status": "FAIL",
        "mode": "traced_layout_blocked",
        "label": "Trace module layout needs revision",
        "can_ahj_ready": False,
        "detail": "module rectangles overlap fire pathway",
    }
    gate = build_ahj_gate(
        payload=payload,
        source_materials=build_source_materials(
            payload,
            roof_trace=roof_trace,
            trace_module_layout=trace_module_layout,
        ),
        readiness={
            "status": "PASS",
            "roof_trace": roof_trace,
            "trace_module_layout": trace_module_layout,
        },
        package_qa={"status": "PASS"},
        files=files,
        review_state=_approved_reviews(files),
    )

    assert gate["level"] == "Internal review"
    assert gate["can_submit_to_ahj"] is False
    assert any(
        blocker["key"] == "site.trace_module_layout"
        and blocker["field"] == "site.trace_module_layout"
        for blocker in gate["blockers"]
    )


def test_web_ahj_gate_blocks_r8_validation_warning(tmp_path: Path):
    payload = WebProjectRequest.model_validate(
        _complete_real_payload(
            battery_choice="none",
            battery_quantity=0,
            battery_capacity_kwh_each=0,
        )
    )
    files = _gate_files(tmp_path)
    roof_trace = {
        "status": "PASS",
        "mode": "traced",
        "label": "Verified traced roof",
        "can_ahj_ready": True,
        "detail": "The roof outline is traced.",
    }
    trace_module_layout = {
        "status": "PASS",
        "mode": "traced_layout",
        "label": "Trace module layout verified",
        "can_ahj_ready": True,
        "detail": "All modules fit traced geometry.",
    }
    r8_validation = {
        "overall_status": "WARN",
        "steps": [
            {"step": 1, "title": "Confirm input address", "status": "PASS"},
            {
                "step": 3,
                "title": "Review roof trace overlay",
                "status": "WARN",
                "detail": "Google Solar lookup produced many roof segment boxes.",
            },
        ],
    }
    gate = build_ahj_gate(
        payload=payload,
        source_materials=build_source_materials(
            payload,
            roof_trace=roof_trace,
            trace_module_layout=trace_module_layout,
            r8_validation=r8_validation,
        ),
        readiness={
            "status": "PASS",
            "roof_trace": roof_trace,
            "trace_module_layout": trace_module_layout,
            "r8_validation": r8_validation,
        },
        package_qa={"status": "PASS"},
        files=files,
        review_state=_approved_reviews(files),
    )

    assert gate["level"] == "Internal review"
    assert gate["can_submit_to_ahj"] is False
    assert any(
        blocker["key"] == "site.r8_validation"
        and blocker["field"] == "site.ee4_trace"
        for blocker in gate["blockers"]
    )


def test_manual_trace_review_clears_r8_segment_box_warning():
    status = {
        "overall_status": "WARN",
        "roof_segment_warning": "Google Solar lookup produced 13 roof segment boxes.",
        "roof_trace": {
            "can_ahj_ready": True,
            "detail": "Trace active with outline and fire pathways.",
        },
        "trace_module_layout": {"can_ahj_ready": True},
        "steps": [
            {"step": 1, "title": "Confirm input address", "status": "PASS"},
            {"step": 2, "title": "Review satellite image", "status": "PASS"},
            {
                "step": 3,
                "title": "Review roof trace overlay",
                "status": "WARN",
                "detail": "Google Solar lookup produced 13 roof segment boxes.",
            },
            {
                "step": 4,
                "title": "Review panel and attachment layout",
                "status": "PASS",
            },
            {"step": 5, "title": "Locate the issue", "status": "WARN"},
        ],
    }

    updated = web_server._apply_manual_trace_review_to_r8(status)

    assert updated["manual_trace_reviewed"] is True
    assert updated["roof_segment_warning"] == ""
    assert updated["overall_status"] == "PASS"
    assert [step["status"] for step in updated["steps"]] == ["PASS"] * 5


def test_web_ahj_gate_blocks_unapproved_required_artifacts(tmp_path: Path):
    payload = WebProjectRequest.model_validate(
        _complete_real_payload(
            battery_choice="none",
            battery_quantity=0,
            battery_capacity_kwh_each=0,
        )
    )
    gate = build_ahj_gate(
        payload=payload,
        source_materials=build_source_materials(payload),
        readiness={"status": "PASS"},
        package_qa={"status": "PASS"},
        files=_gate_files(tmp_path),
        review_state={},
    )

    assert gate["level"] == "Internal review"
    assert gate["can_submit_to_ahj"] is False
    assert gate["required_artifact_review_count"] == 4
    assert gate["pending_required_artifact_review_count"] == 4
    assert [
        item["status"] for item in gate["required_artifact_reviews"]
    ] == ["not_reviewed"] * 4
    assert any(
        blocker["key"] == "review.required_artifacts"
        and blocker["field"] == "artifact_reviews"
        for blocker in gate["blockers"]
    )


def test_web_ahj_gate_blocks_missing_package_qa(tmp_path: Path):
    payload = WebProjectRequest.model_validate(
        _complete_real_payload(
            battery_choice="none",
            battery_quantity=0,
            battery_capacity_kwh_each=0,
        )
    )
    gate = build_ahj_gate(
        payload=payload,
        source_materials=build_source_materials(payload),
        readiness={"status": "PASS"},
        files=_gate_files(tmp_path),
        review_state={},
    )

    assert gate["level"] == "Internal review"
    assert gate["can_submit_to_ahj"] is False
    assert gate["package_qa_status"] == "NOT_RUN"
    assert any(blocker["field"] == "package_qa" for blocker in gate["blockers"])


def test_web_ahj_gate_blocks_pv_ess_missing_battery_spec(tmp_path: Path):
    payload = WebProjectRequest.model_validate(
        _complete_real_payload(
            battery_choice="growatt_apx_20kwh",
            battery_quantity=1,
            battery_capacity_kwh_each=20,
            battery_install_location="garage",
            distance_to_doorway_ft=4,
            distance_to_window_ft=4,
            distance_to_egress_ft=4,
        )
    )
    gate = build_ahj_gate(
        payload=payload,
        source_materials=build_source_materials(payload),
        readiness={"status": "WARN"},
        files=_gate_files(tmp_path),
        review_state={},
    )

    assert gate["level"] == "Internal review"
    assert any(
        blocker["field"] == "spec_sheets" and "battery" in blocker["detail"]
        for blocker in gate["blockers"]
    )


def test_web_ahj_gate_blocks_strict_readiness_review_items(tmp_path: Path):
    payload = WebProjectRequest.model_validate(_complete_real_payload())
    gate = build_ahj_gate(
        payload=payload,
        source_materials=build_source_materials(payload),
        readiness={
            "status": "WARN",
            "review_items": [
                {
                    "key": "site.plan_geometry",
                    "status": "missing",
                    "detail": "EE-4 trace or property context is missing.",
                },
                {
                    "key": "project.site_photos",
                    "status": "simulated",
                    "detail": "Mock PV-7 photos are present.",
                },
            ],
        },
        files=_gate_files(tmp_path),
        review_state={},
    )

    assert gate["level"] == "Internal review"
    assert gate["can_submit_to_ahj"] is False
    assert any(
        blocker["field"] == "site.plan_geometry"
        and "MISSING" in blocker["detail"]
        for blocker in gate["blockers"]
    )
    assert any(
        blocker["field"] == "project.site_photos"
        and "SIMULATED" in blocker["detail"]
        for blocker in gate["blockers"]
    )
