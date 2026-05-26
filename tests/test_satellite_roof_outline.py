from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import yaml

from pvess_calc.calc.engine import run
from pvess_calc.customer.roof_satellite import (
    SatelliteAssets,
    target_component_from_mask,
)
from pvess_calc.permit import satellite_roof_outline
from pvess_calc.permit import r8_validation
from pvess_calc.permit.satellite_roof_outline import (
    build_satellite_roof_outline_candidate,
    write_satellite_roof_outline_artifacts,
)
from pvess_calc.schema import (
    Battery,
    Inputs,
    Inverter,
    Loads,
    ProjectMeta,
    PvArray,
    PvModule,
    Service,
)


def _result():
    inputs = Inputs(
        project=ProjectMeta(
            id="satellite-outline-test",
            name="Satellite Outline Test",
            location="Frisco, TX",
            site_address="7652 Glasshouse Walk, Frisco, TX 75035",
            coordinates="33.1414, -96.8012",
            ahj="Frisco TX",
            utility="Oncor",
        ),
        pv_array=PvArray(
            modules=8,
            strings=2,
            modules_per_string=4,
            module=PvModule(
                brand="Talesun",
                model="TP7G54M-415",
                power_w=415,
                voc_stc=37.55,
                isc_stc=13.92,
                voc_temp_coeff_pct_per_c=-0.28,
                isc_temp_coeff_pct_per_c=0.048,
            ),
            ashrae_2pct_min_c=-10,
            temp_min_c=-10,
            temp_max_c=45,
        ),
        battery=Battery(
            brand="Pytes",
            model="V16",
            quantity=0,
            nominal_voltage=48,
            capacity_kwh_each=0,
        ),
        inverter=Inverter(
            brand="Megarevo",
            model="R11KLNA",
            ac_output_v=240,
            ac_output_a=45.8,
        ),
        service=Service(
            main_panel_a=200,
            busbar_a=200,
            busbar_source="nameplate",
            voltage="120/240 split-phase",
            interconnection_methods=["supply_side_tap"],
        ),
        loads=Loads(critical_subpanel_a=100),
    )
    inputs.site.house_width_ft = 50
    inputs.site.house_depth_ft = 35
    inputs.site.satellite_alignment.contour_simplify_ft = 0.5
    inputs.site.satellite_alignment.contour_max_vertices = 12
    return run(inputs)


def _assets_with_large_neighbor_and_target() -> SatelliteAssets:
    rgb = np.full((100, 100, 3), 180, dtype=np.uint8)
    flux = np.ones((100, 100), dtype=np.float32) * 1100
    mask = np.zeros((100, 100), dtype=bool)
    mask[5:55, 5:55] = True
    mask[70:90, 70:90] = True
    return SatelliteAssets(
        rgb=rgb,
        annual_flux=flux,
        mask=mask,
        imagery_date="2024-02-06",
        imagery_quality="HIGH",
        target_px=(80.0, 80.0),
    )


def test_satellite_roof_outline_candidate_uses_target_component():
    result = _result()
    assets = _assets_with_large_neighbor_and_target()
    component = target_component_from_mask(assets.mask, assets.target_px)

    payload = build_satellite_roof_outline_candidate(
        result,
        assets=assets,
        component=component,
        radius_m=15.24,
    )

    assert payload["status"] == "PASS"
    candidate = payload["candidate"]
    assert candidate["component_bbox_px"] == [70, 70, 90, 90]
    assert candidate["vertex_count"] == 4
    assert candidate["area_sqft"] < 600


def test_satellite_roof_outline_reports_empty_google_mask():
    result = _result()
    assets = SatelliteAssets(
        rgb=np.full((50, 50, 3), 160, dtype=np.uint8),
        annual_flux=np.ones((50, 50), dtype=np.float32),
        mask=np.zeros((50, 50), dtype=bool),
        imagery_date="2019-12-04",
        imagery_quality="HIGH",
    )

    audit = satellite_roof_outline.build_satellite_data_chain_audit(
        result,
        assets=assets,
        component=None,
        lat_lng=(32.550291, -97.093689),
        radius_m=35.0,
    )
    candidate = build_satellite_roof_outline_candidate(
        result,
        assets=assets,
        component=None,
        radius_m=35.0,
    )

    assert audit["status"] == "WARN"
    assert "zero roof pixels" in audit["detail"]
    assert candidate["status"] == "WARN"
    assert "zero roof pixels" in candidate["detail"]


def test_write_satellite_roof_outline_artifacts_from_cached_assets(
    monkeypatch,
    tmp_path: Path,
):
    result = _result()
    assets = _assets_with_large_neighbor_and_target()

    monkeypatch.setattr(
        satellite_roof_outline,
        "fetch_satellite_assets_cached",
        lambda *args, **kwargs: assets,
    )

    artifacts = write_satellite_roof_outline_artifacts(
        result,
        tmp_path,
        radius_m=15.24,
    )

    assert artifacts["status"]["status"] == "PASS"
    assert (tmp_path / "satellite-data-chain-audit.json").exists()
    assert (tmp_path / "satellite-data-chain-audit.md").exists()
    assert (tmp_path / "satellite-roof-outline-candidate.json").exists()
    assert (tmp_path / "satellite-roof-outline-candidate.png").exists()
    yaml_path = tmp_path / "satellite-ee4-trace-candidate.yaml"
    assert yaml_path.exists()

    data = json.loads((tmp_path / "satellite-roof-outline-candidate.json").read_text())
    assert data["candidate"]["component_area_px"] == 400
    trace = yaml.safe_load(yaml_path.read_text())
    outline = trace["site"]["ee4_trace"]["roof_outline"]
    assert outline["name"] == "Satellite mask roof outline candidate"
    assert len(outline["vertices"]) == 4


def test_r8_mask_zero_uses_static_fallback_without_auto_outline(
    monkeypatch,
    tmp_path: Path,
):
    result = _result()

    def fake_satellite_review(result, out_path, **kwargs):
        out_path.write_bytes(b"\x89PNG\r\n\x1a\nsolar-review")
        return {
            "status": "PASS",
            "artifact": out_path.name,
            "preview": out_path.name,
            "detail": "Google Solar imagery fetched.",
        }

    def fake_outline_artifacts(result, output_dir, **kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        audit_json = output_dir / "satellite-data-chain-audit.json"
        audit_md = output_dir / "satellite-data-chain-audit.md"
        candidate_json = output_dir / "satellite-roof-outline-candidate.json"
        audit_json.write_text("{}", encoding="utf-8")
        audit_md.write_text("# audit\n", encoding="utf-8")
        candidate_json.write_text(
            json.dumps({
                "status": "WARN",
                "detail": "Google Solar dataLayers returned imagery, but the mask has zero roof pixels.",
                "candidate": None,
            }),
            encoding="utf-8",
        )
        return {
            "status": {
                "status": "WARN",
                "detail": "Google Solar dataLayers returned imagery, but the mask has zero roof pixels.",
                "vertex_count": 0,
                "area_sqft": 0.0,
                "audit_status": "WARN",
                "audit_detail": "mask contains zero roof pixels",
            },
            "audit_json": audit_json,
            "audit_markdown": audit_md,
            "candidate_json": candidate_json,
            "candidate_yaml": None,
            "candidate_png": None,
        }

    def fake_static(result, out_path):
        out_path.write_bytes(b"\x89PNG\r\n\x1a\nstatic-fallback")
        return {
            "status": "PASS",
            "artifact": out_path.name,
            "preview": out_path.name,
            "detail": "Google Static satellite fallback generated. Use for visual manual tracing only.",
        }

    monkeypatch.setattr(
        r8_validation,
        "_write_satellite_review_png",
        fake_satellite_review,
    )
    monkeypatch.setattr(
        r8_validation,
        "write_satellite_roof_outline_artifacts",
        fake_outline_artifacts,
    )
    monkeypatch.setattr(
        r8_validation,
        "_write_google_static_satellite_png",
        fake_static,
    )

    artifacts = r8_validation.write_r8_validation_artifacts(
        result,
        tmp_path,
        allow_paid_satellite=True,
    )
    status = artifacts["status"]

    assert artifacts["satellite_outline_yaml"] is None
    assert artifacts["google_static_satellite_png"].exists()
    assert status["satellite_roof_outline"]["status"] == "WARN"
    assert status["google_static_satellite"]["status"] == "PASS"
    assert status["steps"][1]["status"] == "WARN"
    assert "zero roof pixels" in status["steps"][1]["detail"]
    assert "manual tracing" in status["steps"][1]["detail"]


def test_r8_good_mask_skips_static_fallback(
    monkeypatch,
    tmp_path: Path,
):
    result = _result()

    def fake_satellite_review(result, out_path, **kwargs):
        out_path.write_bytes(b"\x89PNG\r\n\x1a\nsolar-review")
        return {
            "status": "PASS",
            "artifact": out_path.name,
            "preview": out_path.name,
            "detail": "Google Solar imagery fetched.",
        }

    def fake_outline_artifacts(result, output_dir, **kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        audit_json = output_dir / "satellite-data-chain-audit.json"
        audit_md = output_dir / "satellite-data-chain-audit.md"
        candidate_json = output_dir / "satellite-roof-outline-candidate.json"
        candidate_yaml = output_dir / "satellite-ee4-trace-candidate.yaml"
        candidate_png = output_dir / "satellite-roof-outline-candidate.png"
        audit_json.write_text("{}", encoding="utf-8")
        audit_md.write_text("# audit\n", encoding="utf-8")
        candidate_json.write_text(
            json.dumps({"status": "PASS", "candidate": {"vertex_count": 4}}),
            encoding="utf-8",
        )
        candidate_yaml.write_text("site:\n  ee4_trace:\n    enabled: true\n", encoding="utf-8")
        candidate_png.write_bytes(b"\x89PNG\r\n\x1a\noutline")
        return {
            "status": {
                "status": "PASS",
                "detail": "Target roof mask contour extracted.",
                "vertex_count": 4,
                "area_sqft": 900.0,
                "audit_status": "PASS",
                "audit_detail": "target roof component selected",
            },
            "audit_json": audit_json,
            "audit_markdown": audit_md,
            "candidate_json": candidate_json,
            "candidate_yaml": candidate_yaml,
            "candidate_png": candidate_png,
        }

    def fail_static(*args, **kwargs):
        raise AssertionError("static fallback should not run when mask candidate passes")

    monkeypatch.setattr(
        r8_validation,
        "_write_satellite_review_png",
        fake_satellite_review,
    )
    monkeypatch.setattr(
        r8_validation,
        "write_satellite_roof_outline_artifacts",
        fake_outline_artifacts,
    )
    monkeypatch.setattr(
        r8_validation,
        "_write_google_static_satellite_png",
        fail_static,
    )

    artifacts = r8_validation.write_r8_validation_artifacts(
        result,
        tmp_path,
        allow_paid_satellite=True,
    )

    assert artifacts["status"]["satellite_roof_outline"]["status"] == "PASS"
    assert artifacts["status"]["google_static_satellite"]["status"] == "SKIPPED"
    assert artifacts["google_static_satellite_png"] is None
