from __future__ import annotations

import json
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
import yaml

from pvess_calc.web.server import create_app


DFW_SIMULATED_MONTHLY_KWH = [
    880, 780, 720, 820, 1050, 1450, 1700, 1750, 1450, 1050, 820, 860,
]

MANSFIELD_SAMPLE_ADDRESSES = [
    "905 Crossvine Drive, Mansfield, TX",
    "2806 Green Circle Drive, Mansfield, TX",
]


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(jobs_dir=tmp_path))


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


def _submit_and_wait(client: TestClient, payload: dict, *, timeout_s: float = 20.0):
    response = client.post("/api/projects", json=payload)
    assert response.status_code == 200, response.text
    state = response.json()
    assert state["status"] in {"queued", "running", "done"}
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


def test_web_index_serves_static_page(tmp_path: Path):
    client = _client(tmp_path)
    response = client.get("/")

    assert response.status_code == 200
    assert "TGE Solar Project Generator" in response.text
    assert "Project template" in response.text
    assert "Talesun TP7G54M-415" in response.text
    assert "InHouse HV-16" in response.text
    assert "Megarova / Megarevo" in response.text
    assert "Hoymile / Hoymiles" in response.text
    assert "Growatt" in response.text
    assert "Field intake" in response.text
    assert "Source materials" in response.text
    assert "Structural letter" in response.text
    assert "Run preflight" in response.text
    assert "Preflight" in response.text
    assert "Preview" in response.text
    assert "Access token" in response.text
    assert "Lookup address" in response.text
    assert "Lookup: online if configured" in response.text
    assert "Address sample" in response.text
    assert "905 Crossvine Drive, Mansfield, TX" in response.text
    assert "2806 Green Circle Drive, Mansfield, TX" in response.text
    assert "Error detail" in response.text
    assert "Filter" in response.text
    assert "Generate package" in response.text
    assert "Frisco PV + ESS Estimate" not in response.text
    assert "Project Estimator" not in response.text
    assert client.get("/favicon.ico").status_code == 204


def test_web_health_endpoint(tmp_path: Path):
    client = _client(tmp_path)
    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "TGE Solar Project Generator"
    assert data["jobs_dir"] == str(tmp_path)
    assert data["auth_required"] is False


def test_web_runtime_config_reports_auth_mode(tmp_path: Path):
    client = TestClient(create_app(jobs_dir=tmp_path, access_token="secret"))
    response = client.get("/api/runtime-config")

    assert response.status_code == 200
    data = response.json()
    assert data["auth_required"] is True
    assert data["lookup_modes"] == ["online", "offline"]


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
        "megarova",
        "hoymile",
        "growatt",
    }
    assert {b["key"] for b in data["batteries"]} >= {
        "none",
        "inhouse_16kwh_hv",
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
        "Artifact Manifest JSON",
        "Complete Project ZIP",
    }
    assert {f["category"] for f in data["files"]} >= {
        "Input",
        "Engineering",
        "Cost",
        "Readiness",
        "Manifest",
        "Archive",
    }
    assert data["source_materials"]["site_data_source"] == "simulated"
    assert data["readiness"]["status"] == "WARN"
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
    }.issubset(names)

    artifact_manifest = json.loads(
        (project_dir / "output" / "artifact-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert artifact_manifest["project_name"] == "Web Smoke Test"
    assert artifact_manifest["category_counts"]["Cost"] >= 2
    assert any(file["label"] == "BOM + Cost CSV" for file in artifact_manifest["files"])


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
        _light_payload(inverter_choice="hoymile"),
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
