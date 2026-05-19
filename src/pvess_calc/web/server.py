"""Local web app for generating PV + ESS project artifacts.

The web layer is intentionally thin: it turns browser JSON into the same
`inputs.yaml` schema used by the CLI, then calls the existing calculation
and rendering modules. That keeps the website aligned with the permit
toolchain instead of creating a second calculation path.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import csv
import io
import json
import os
import re
import shutil
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import click
import yaml
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError, model_validator

from ..calc.engine import run
from ..compare.bom import compute_bom
from ..customer.economics import compute_economics
from ..customer.pdf import render_customer_summary
from ..devices.batteries import get_battery
from ..devices.inverters import get_inverter
from ..devices.modules import get_module
from ..dxf.grounding_sheet import render_grounding_dxf
from ..dxf.one_line import render_one_line_dxf
from ..dxf.render import export_preview_png, render_for_result as render_dxf
from ..labels.render import render_for_result as render_labels
from ..lookup import resolve as resolve_lookup
from ..lookup.providers import (
    static_ahj,
    static_ashrae,
    static_climate,
    static_nec,
    static_utility,
    static_utility_rate,
)
from ..permit.builder import _should_emit_one_line, build_permit_package
from ..permit.readiness import (
    assess_reference_profile_readiness,
    format_real_data_checklist_markdown,
    format_reference_readiness_markdown,
)
from ..permit.site_photos import REQUIRED_PHOTOS
from ..qet.inject import inject_from_result
from ..report.json_dump import write_json
from ..report.markdown import write_markdown
from ..schema import Inputs
from .job_store import JobStore
from .quote import categorize_bom, installed_breakdown, quote_tiers_for_result


WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
QET_TEMPLATE = PROJECT_ROOT / "library" / "templates" / "residential-ess-v1.qet"

WEB_MODULE_OPTIONS: dict[str, dict[str, str]] = {
    "talesun_tp7g54m_415": {
        "ref": "talesun_tp7g54m_415",
        "label": "Talesun TP7G54M-415 (415 W)",
    },
    "rec_alpha_pure_410": {
        "ref": "rec_alpha_pure_410",
        "label": "REC Alpha Pure REC410AA (410 W)",
    },
    "canadian_solar_hiku7_595": {
        "ref": "canadian_solar_hiku7_595",
        "label": "Canadian Solar HiKu7 CS7N-595MS (595 W)",
    },
    "generic_420": {
        "ref": "generic_420",
        "label": "Generic MONO-420-144 (420 W)",
    },
}

WEB_INVERTER_OPTIONS: dict[str, dict[str, str]] = {
    "megarova": {
        "ref": "megarevo_r11klna",
        "label": "Megarova / Megarevo R11KLNA (US 11 kW)",
    },
    "hoymile": {
        "ref": "hoymiles_hys_11_5lv_usg1",
        "label": "Hoymile / Hoymiles HYS-11.5LV-USG1 (US 11.5 kW)",
    },
    "growatt": {
        "ref": "growatt_min11400tl_xh_us",
        "label": "Growatt MIN 11400TL-XH-US (US 11.4 kW)",
    },
}

WEB_BATTERY_OPTIONS: dict[str, dict[str, str]] = {
    "none": {
        "ref": "",
        "label": "No battery (PV-only)",
    },
    "inhouse_16kwh_hv": {
        "ref": "inhouse_16kwh_hv",
        "label": "InHouse HV-16 (16 kWh)",
    },
    "growatt_apx_20kwh": {
        "ref": "growatt_apx_20kwh",
        "label": "Growatt APX HV 20K (20 kWh)",
    },
    "tesla_powerwall_3": {
        "ref": "tesla_powerwall_3",
        "label": "Tesla Powerwall 3 (13.5 kWh)",
    },
    "eg4_lifepower4_v2": {
        "ref": "eg4_lifepower4_v2",
        "label": "EG4 LifePower4 V2 (5.12 kWh)",
    },
    "franklinwh_apower": {
        "ref": "franklinwh_apower",
        "label": "FranklinWH aPower (13.6 kWh)",
    },
    "enphase_iq_battery_5p": {
        "ref": "enphase_iq_battery_5p",
        "label": "Enphase IQ Battery 5P (5 kWh)",
    },
}

SITE_PHOTO_LABELS: dict[str, str] = dict(REQUIRED_PHOTOS)
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
WEB_OFFLINE_LOOKUP_PROVIDERS = (
    static_ashrae,
    static_utility,
    static_utility_rate,
    static_ahj,
    static_climate,
    static_nec,
)


class UploadedMaterial(BaseModel):
    filename: str
    content_type: str = ""
    content: bytes


class WebSitePhotoRef(BaseModel):
    kind: Literal[
        "front_elevation", "roof", "meter", "main_panel", "sub_panel",
        "attic", "equipment_location", "other",
    ] = "other"
    path: str = ""
    caption: str = ""


class WebSpecSheetRef(BaseModel):
    equipment: Literal[
        "module", "inverter", "optimizer", "battery", "racking", "other",
    ] = "other"
    path: str = ""
    pages: list[int] = Field(default_factory=list)


class OutputOptions(BaseModel):
    customer: bool = True
    permit: bool = True
    dxf: bool = True
    labels: bool = True
    qet: bool = True


class WebProjectRequest(BaseModel):
    project_id: str = ""
    project_name: str = "Residential PV + ESS Package"
    client_name: str = ""
    site_address: str = ""
    coordinates: str = ""
    apn: str = ""
    location: str = "Dallas, TX"
    ahj: str = "Authority Having Jurisdiction"
    ahj_profile: str = ""
    utility: str = "Utility TBD"
    nec_edition: Literal["2023", "2020", "2017"] = "2023"
    permit_profile: Literal[
        "internal", "tx_residential_pv", "wyssling_like",
    ] = "wyssling_like"

    meter_number: str = ""
    meter_location: str = ""
    meter_esid: str = ""

    engineer_firm: str = ""
    engineer_address: str = ""
    engineer_email: str = ""
    engineer_phone: str = ""
    engineer_firm_number: str = ""

    installer_company: str = "Texas Green Eco Power"
    installer_address: str = ""

    modules: int = Field(default=32, ge=1, le=200)
    strings: int = Field(default=4, ge=1, le=24)
    module_choice: Literal[
        "talesun_tp7g54m_415", "rec_alpha_pure_410",
        "canadian_solar_hiku7_595", "generic_420",
    ] = "talesun_tp7g54m_415"
    module_brand: str = "Talesun"
    module_model: str = "TP7G54M 415"
    module_power_w: float = Field(default=415.0, gt=0, le=800)
    module_voc_stc: float = Field(default=49.5, gt=0, le=100)
    module_isc_stc: float = Field(default=13.8, gt=0, le=30)
    temp_min_c: float = -10.0
    temp_max_c: float = 50.0

    optimizer_brand: str = "Tigo"
    optimizer_model: str = "TS4-A-O"

    inverter_choice: Literal["megarova", "hoymile", "growatt"] = "growatt"
    inverter_brand: str = "Growatt"
    inverter_model: str = "MIN 11400TL-XH-US"
    inverter_quantity: int = Field(default=1, ge=1, le=12)
    inverter_ac_output_a: float = Field(default=48.0, gt=0, le=250)
    inverter_ac_output_v: float = Field(default=240.0, gt=0, le=600)

    battery_brand: str = "In-house"
    battery_model: str = "16 kWh HV"
    battery_choice: Literal[
        "none", "inhouse_16kwh_hv", "growatt_apx_20kwh",
        "tesla_powerwall_3", "eg4_lifepower4_v2",
        "franklinwh_apower", "enphase_iq_battery_5p",
    ] = "inhouse_16kwh_hv"
    battery_quantity: int = Field(default=1, ge=0, le=12)
    battery_capacity_kwh_each: float = Field(default=16.0, ge=0, le=100)
    battery_nominal_voltage: float = Field(default=400.0, gt=0, le=1000)
    battery_install_location: Literal[
        "indoor", "garage", "outdoor", "outdoor_protected", "unknown",
    ] = "unknown"
    distance_to_doorway_ft: float = Field(default=0.0, ge=0, le=200)
    distance_to_window_ft: float = Field(default=0.0, ge=0, le=200)
    distance_to_egress_ft: float = Field(default=0.0, ge=0, le=200)

    main_panel_a: float = Field(default=200.0, gt=0, le=1200)
    busbar_a: float = Field(default=200.0, gt=0, le=1200)
    service_voltage: str = "240/120V 1PH"
    interconnection_method: Literal[
        "120%_rule", "sum_rule", "supply_side_tap", "center_fed",
    ] = "supply_side_tap"

    monthly_kwh: list[float] = Field(default_factory=list)
    export_tariff_model: Literal[
        "1to1_nem", "ca_nem3", "hi_self_consumption",
        "tx_default_oncor", "tx_txu_buyback", "tx_green_mountain",
        "tx_reliant_sun", "tx_rhythm_pure",
    ] = "tx_default_oncor"
    self_consumption_fraction: float = Field(default=0.55, ge=0, le=1)

    pv_turnkey_usd_per_w: float = Field(default=2.40, gt=0, le=10)
    inverter_cost_usd_total: float | None = Field(default=None, ge=0)
    battery_cost_usd_total: float | None = Field(default=None, ge=0)

    roof_pitch_deg: float = Field(default=22.0, ge=0, le=60)
    roof_azimuth_deg: float = Field(default=180.0, ge=0, le=360)
    roof_width_ft: float = Field(default=54.0, gt=0, le=200)
    roof_height_ft: float = Field(default=24.0, gt=0, le=200)
    roof_info_type: str = "Comp Shingle"
    roof_info_height_ft: float = Field(default=0.0, ge=0, le=120)
    roof_construction: str = ""
    roof_condition: Literal["good", "fair", "poor", "unknown"] = "unknown"
    roof_framing: str = ""
    roof_attic_access: Literal[
        "accessible", "inaccessible", "unknown",
    ] = "unknown"
    decking_thickness_in: float = Field(default=0.0, ge=0, le=5)
    roof_layers: int = Field(default=0, ge=0, le=10)

    msp_x_ft: float | None = None
    msp_y_ft: float | None = None
    inverter_x_ft: float | None = None
    inverter_y_ft: float | None = None
    ac_disconnect_x_ft: float | None = None
    ac_disconnect_y_ft: float | None = None
    ess_x_ft: float | None = None
    ess_y_ft: float | None = None
    attic_drop_x_ft: float | None = None
    attic_drop_y_ft: float | None = None
    attic_to_eq_height_ft: float = Field(default=10.0, ge=0, le=80)

    site_data_source: Literal["simulated", "real"] = "simulated"
    site_photo_refs: list[WebSitePhotoRef] = Field(default_factory=list)
    utility_bill_path: str = ""
    structural_letter_path: str = ""
    spec_sheet_refs: list[WebSpecSheetRef] = Field(default_factory=list)

    outputs: OutputOptions = Field(default_factory=OutputOptions)

    @model_validator(mode="after")
    def _check_string_count(self) -> "WebProjectRequest":
        if self.modules % self.strings != 0:
            raise ValueError(
                "modules must be divisible by strings so modules_per_string "
                "is exact"
            )
        if self.monthly_kwh and len(self.monthly_kwh) != 12:
            raise ValueError("monthly_kwh must contain exactly 12 values")
        if self.battery_choice == "none" and self.battery_quantity > 0:
            raise ValueError(
                "battery_quantity must be 0 when battery_choice is 'none'"
            )
        if self.battery_quantity == 0 and self.battery_capacity_kwh_each != 0:
            # Keep the yaml explicit and avoid confusing cost output.
            self.battery_capacity_kwh_each = 0.0
        return self


class GeneratedFile(BaseModel):
    label: str
    path: str
    url: str
    bytes: int
    category: Literal[
        "Input", "Engineering", "Permit", "CAD", "Cost", "Readiness",
        "Manifest", "Archive", "Other",
    ] = "Other"
    kind: str = "other"


class PreflightIssue(BaseModel):
    severity: Literal["error", "warning"]
    field: str
    message: str


class WebPreflightResponse(BaseModel):
    status: Literal["PASS", "WARN", "FAIL"]
    summary: dict[str, Any]
    estimate: dict[str, Any]
    intake: dict[str, Any]
    issues: list[PreflightIssue]


class WebLookupProvider(BaseModel):
    source: str
    confidence: str
    hit: bool
    note: str = ""
    fields: list[str] = Field(default_factory=list)


class WebAddressLookupResponse(BaseModel):
    status: Literal["PASS", "WARN"]
    mode: Literal["offline", "online"]
    address: dict[str, Any]
    suggested_payload: dict[str, Any]
    fields: dict[str, Any]
    field_sources: dict[str, str]
    field_confidence: dict[str, str]
    providers: list[WebLookupProvider]
    roof_summary: dict[str, Any]


class WebJobResponse(BaseModel):
    job_id: str
    project_dir: str
    status: Literal["done"]
    summary: dict[str, Any]
    bom: dict[str, Any]
    source_materials: dict[str, Any]
    readiness: dict[str, Any]
    files: list[GeneratedFile]


class WebJobState(BaseModel):
    job_id: str
    project_dir: str
    status: Literal["queued", "running", "done", "failed"]
    progress: int = 0
    stage: str = "queued"
    message: str = ""
    created_at: str
    updated_at: str
    result: dict[str, Any] | None = None
    error: str | None = None


def create_app(
    *,
    jobs_dir: Path | None = None,
    access_token: str | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    app = FastAPI(title="PVESS Web Generator", version="0.1.0")
    app.state.jobs_dir = jobs_dir or default_jobs_dir()
    app.state.access_token = access_token if access_token is not None else default_access_token()
    app.state.jobs: dict[str, WebJobState] = {}
    app.state.job_lock = threading.Lock()
    app.state.job_store = JobStore(app.state.jobs_dir)
    app.state.executor = ThreadPoolExecutor(max_workers=2)

    origins = cors_origins if cors_origins is not None else default_cors_origins()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-PVESS-Token"],
        )

    @app.middleware("http")
    async def optional_access_token_auth(request: Request, call_next):
        if _request_requires_token(request.url.path):
            expected = str(app.state.access_token or "").strip()
            if expected and not _token_matches(request, expected):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "PVESS web access token required"},
                )
        return await call_next(request)

    app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/api/catalog")
    def catalog() -> dict[str, Any]:
        return {
            "modules": _catalog_options(WEB_MODULE_OPTIONS, get_module),
            "inverters": _catalog_options(WEB_INVERTER_OPTIONS, _get_inverter_by_ref),
            "batteries": _battery_catalog_options(),
            "templates": ["pv_ess", "pv_only", "retrofit_existing_pv"],
        }

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "app": "TGE Solar Project Generator",
            "jobs_dir": str(app.state.jobs_dir),
            "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
            "auth_required": bool(app.state.access_token),
        }

    @app.get("/api/runtime-config")
    def runtime_config() -> dict[str, Any]:
        return {
            "app": "TGE Solar Project Generator",
            "auth_required": bool(app.state.access_token),
            "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
            "lookup_modes": ["online", "offline"],
        }

    @app.get("/api/lookup/address", response_model=WebAddressLookupResponse)
    def lookup_address(
        address: str = Query(..., min_length=2),
        mode: Literal["offline", "online"] = Query("online"),
    ) -> WebAddressLookupResponse:
        try:
            return build_address_lookup_response(address, mode=mode)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - surfaced in UI.
            raise HTTPException(status_code=500, detail=repr(exc)) from exc

    @app.post("/api/preflight", response_model=WebPreflightResponse)
    def preflight_project(payload: WebProjectRequest) -> WebPreflightResponse:
        try:
            return build_preflight_response(payload)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - exercised by UI as 500.
            raise HTTPException(status_code=500, detail=repr(exc)) from exc

    @app.post("/api/projects", response_model=WebJobState)
    def create_project(payload: WebProjectRequest) -> WebJobState:
        try:
            return enqueue_project(payload, app)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - exercised by UI as 500.
            raise HTTPException(status_code=500, detail=repr(exc)) from exc

    @app.post("/api/projects/form", response_model=WebJobState)
    async def create_project_form(
        payload: str = Form(...),
        front_elevation: UploadFile | None = File(None),
        roof: UploadFile | None = File(None),
        meter: UploadFile | None = File(None),
        main_panel: UploadFile | None = File(None),
        sub_panel: UploadFile | None = File(None),
        equipment_location: UploadFile | None = File(None),
        utility_bill: UploadFile | None = File(None),
        structural_letter: UploadFile | None = File(None),
        spec_module: UploadFile | None = File(None),
        spec_inverter: UploadFile | None = File(None),
        spec_battery: UploadFile | None = File(None),
        spec_racking: UploadFile | None = File(None),
        spec_optimizer: UploadFile | None = File(None),
    ) -> WebJobState:
        try:
            request = WebProjectRequest.model_validate(json.loads(payload))
            site_uploads = {
                kind: material
                for kind, upload in {
                    "front_elevation": front_elevation,
                    "roof": roof,
                    "meter": meter,
                    "main_panel": main_panel,
                    "sub_panel": sub_panel,
                    "equipment_location": equipment_location,
                }.items()
                if (material := await _read_upload(upload)) is not None
            }
            utility = await _read_upload(utility_bill)
            structural = await _read_upload(structural_letter)
            spec_uploads = {
                equipment: material
                for equipment, upload in {
                    "module": spec_module,
                    "inverter": spec_inverter,
                    "battery": spec_battery,
                    "racking": spec_racking,
                    "optimizer": spec_optimizer,
                }.items()
                if (material := await _read_upload(upload)) is not None
            }
            return enqueue_project(
                request,
                app,
                site_uploads=site_uploads,
                utility_bill_upload=utility,
                structural_upload=structural,
                spec_uploads=spec_uploads,
            )
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail="invalid payload JSON") from exc
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - exercised by UI as 500.
            raise HTTPException(status_code=500, detail=repr(exc)) from exc

    @app.post("/api/projects/sync", response_model=WebJobResponse)
    def create_project_sync(payload: WebProjectRequest) -> WebJobResponse:
        try:
            result = generate_project(payload, app.state.jobs_dir)
            now = datetime.now(timezone.utc).isoformat()
            state = WebJobState(
                job_id=result.job_id,
                project_dir=result.project_dir,
                status="done",
                progress=100,
                stage="done",
                message="Package generation complete.",
                created_at=now,
                updated_at=now,
                result=result.model_dump(mode="json"),
            )
            _set_job_state(app, state, payload=payload)
            return result
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - exercised by UI as 500.
            raise HTTPException(status_code=500, detail=repr(exc)) from exc

    @app.get("/api/jobs")
    def list_jobs(
        status: Literal["queued", "running", "done", "failed"] | None = Query(None),
        q: str = Query("", max_length=120),
        created_from: str = Query("", max_length=40),
        created_to: str = Query("", max_length=40),
        limit: int = Query(25, ge=1, le=100),
    ) -> dict[str, Any]:
        jobs = app.state.job_store.list_jobs(
            status=status,
            query=q,
            created_from=created_from,
            created_to=created_to,
            limit=limit,
        )
        return {
            "jobs": jobs,
            "filters": {
                "status": status,
                "q": q,
                "created_from": created_from,
                "created_to": created_to,
                "limit": limit,
            },
        }

    @app.get("/api/jobs/{job_id}", response_model=WebJobState)
    def get_job(job_id: str) -> WebJobState:
        return load_job_state(app, job_id)

    @app.get("/api/jobs/{job_id}/payload")
    def get_job_payload(job_id: str) -> dict[str, Any]:
        project_dir = _job_project_dir(app, job_id)
        request_path = project_dir / "request.json"
        if not request_path.exists():
            raise HTTPException(status_code=404, detail="job payload not found")
        return json.loads(request_path.read_text(encoding="utf-8"))

    @app.post("/api/jobs/{job_id}/rerun", response_model=WebJobState)
    def rerun_job(job_id: str) -> WebJobState:
        project_dir = _job_project_dir(app, job_id)
        request_path = project_dir / "request.json"
        if not request_path.exists():
            raise HTTPException(status_code=404, detail="job payload not found")
        payload = WebProjectRequest.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
        return enqueue_project(payload, app)

    @app.delete("/api/jobs/{job_id}")
    def delete_job(job_id: str) -> dict[str, str]:
        project_dir = _job_project_dir(app, job_id)
        with app.state.job_lock:
            app.state.jobs.pop(job_id, None)
        app.state.job_store.delete_job(job_id)
        shutil.rmtree(project_dir)
        return {"deleted": job_id}

    @app.get("/files/{job_id}/{file_path:path}", include_in_schema=False)
    def download(
        job_id: str,
        file_path: str,
        download: bool = Query(False),
    ) -> FileResponse:
        path = resolve_job_file(app.state.jobs_dir, job_id, file_path)
        filename = path.name if download else None
        return FileResponse(path, filename=filename)

    return app


def default_jobs_dir() -> Path:
    raw = os.environ.get("PVESS_WEB_WORKDIR")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".pvess" / "web_jobs"


def default_access_token() -> str:
    return os.environ.get("PVESS_WEB_ACCESS_TOKEN", "").strip()


def default_cors_origins() -> list[str]:
    raw = os.environ.get("PVESS_WEB_CORS_ORIGINS", "").strip()
    if not raw:
        return []
    if raw == "*":
        return ["*"]
    return [item.strip() for item in raw.split(",") if item.strip()]


def _request_requires_token(path: str) -> bool:
    if path in {"/api/health", "/api/runtime-config"}:
        return False
    return path.startswith("/api/") or path.startswith("/files/")


def _token_matches(request: Request, expected: str) -> bool:
    header_token = request.headers.get("X-PVESS-Token", "").strip()
    auth = request.headers.get("Authorization", "").strip()
    bearer_token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    query_token = request.query_params.get("token", "").strip()
    return expected in {header_token, bearer_token, query_token}


app = create_app()


def enqueue_project(
    payload: WebProjectRequest,
    app: FastAPI,
    *,
    site_uploads: dict[str, UploadedMaterial] | None = None,
    utility_bill_upload: UploadedMaterial | None = None,
    structural_upload: UploadedMaterial | None = None,
    spec_uploads: dict[str, UploadedMaterial] | None = None,
) -> WebJobState:
    app.state.jobs_dir.mkdir(parents=True, exist_ok=True)
    job_id = _make_job_id(payload)
    project_dir = app.state.jobs_dir / job_id
    project_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    state = WebJobState(
        job_id=job_id,
        project_dir=str(project_dir),
        status="queued",
        progress=0,
        stage="queued",
        message="Queued for generation.",
        created_at=now,
        updated_at=now,
    )
    _set_job_state(app, state, payload=payload)
    app.state.executor.submit(
        _run_job,
        app,
        payload,
        job_id,
        site_uploads or {},
        utility_bill_upload,
        structural_upload,
        spec_uploads or {},
    )
    return state


def _job_project_dir(app: FastAPI, job_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", job_id):
        raise HTTPException(status_code=404, detail="job not found")
    project_dir = (app.state.jobs_dir / job_id).resolve()
    jobs_dir = app.state.jobs_dir.resolve()
    if not project_dir.is_relative_to(jobs_dir) or not project_dir.exists():
        raise HTTPException(status_code=404, detail="job not found")
    return project_dir


def load_job_state(app: FastAPI, job_id: str) -> WebJobState:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", job_id):
        raise HTTPException(status_code=404, detail="job not found")
    with app.state.job_lock:
        if job_id in app.state.jobs:
            return app.state.jobs[job_id]
    stored = app.state.job_store.get_state(job_id)
    if stored is not None:
        return WebJobState.model_validate(stored)
    path = app.state.jobs_dir / job_id / "job-status.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="job not found")
    return WebJobState.model_validate_json(path.read_text(encoding="utf-8"))


def _run_job(
    app: FastAPI,
    payload: WebProjectRequest,
    job_id: str,
    site_uploads: dict[str, UploadedMaterial] | None = None,
    utility_bill_upload: UploadedMaterial | None = None,
    structural_upload: UploadedMaterial | None = None,
    spec_uploads: dict[str, UploadedMaterial] | None = None,
) -> None:
    def progress(stage: str, message: str, pct: int) -> None:
        state = load_job_state(app, job_id).model_copy(update={
            "status": "running",
            "stage": stage,
            "message": message,
            "progress": pct,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        _set_job_state(app, state)

    try:
        progress("start", "Preparing project inputs.", 5)
        result = generate_project(
            payload,
            app.state.jobs_dir,
            job_id=job_id,
            site_uploads=site_uploads or {},
            utility_bill_upload=utility_bill_upload,
            structural_upload=structural_upload,
            spec_uploads=spec_uploads or {},
            progress=progress,
        )
        now = datetime.now(timezone.utc).isoformat()
        state = load_job_state(app, job_id).model_copy(update={
            "status": "done",
            "stage": "done",
            "message": "Package generation complete.",
            "progress": 100,
            "result": result.model_dump(mode="json"),
            "updated_at": now,
        })
        _set_job_state(app, state)
    except Exception as exc:  # pragma: no cover - failure path is UI-facing.
        now = datetime.now(timezone.utc).isoformat()
        state = load_job_state(app, job_id).model_copy(update={
            "status": "failed",
            "stage": "failed",
            "message": "Package generation failed.",
            "progress": 100,
            "error": repr(exc),
            "updated_at": now,
        })
        _set_job_state(app, state)


def _set_job_state(
    app: FastAPI,
    state: WebJobState,
    *,
    payload: WebProjectRequest | None = None,
) -> None:
    with app.state.job_lock:
        app.state.jobs[state.job_id] = state
    project_dir = Path(state.project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "job-status.json").write_text(
        state.model_dump_json(indent=2),
        encoding="utf-8",
    )
    app.state.job_store.upsert_state(
        state.model_dump(mode="json"),
        payload=payload.model_dump(mode="json") if payload is not None else None,
    )


def generate_project(
    payload: WebProjectRequest,
    jobs_dir: Path,
    *,
    job_id: str | None = None,
    site_uploads: dict[str, UploadedMaterial] | None = None,
    utility_bill_upload: UploadedMaterial | None = None,
    structural_upload: UploadedMaterial | None = None,
    spec_uploads: dict[str, UploadedMaterial] | None = None,
    progress=None,
) -> WebJobResponse:
    jobs_dir.mkdir(parents=True, exist_ok=True)
    job_id = job_id or _make_job_id(payload)
    project_dir = jobs_dir / job_id
    output_dir = project_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    if progress:
        progress("inputs", "Writing inputs.yaml.", 10)
    payload = _attach_site_materials(
        payload,
        project_dir,
        site_uploads or {},
        utility_bill_upload,
        structural_upload,
        spec_uploads or {},
        create_mock_photos=payload.outputs.permit,
    )
    (project_dir / "request.json").write_text(
        payload.model_dump_json(indent=2),
        encoding="utf-8",
    )
    inputs_data = build_inputs_data(payload, project_id=job_id)
    inputs_path = project_dir / "inputs.yaml"
    inputs_path.write_text(
        yaml.safe_dump(inputs_data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    if progress:
        progress("calc", "Running NEC calculations.", 20)
    inputs = Inputs.model_validate(inputs_data)
    result = run(inputs, ahj_profile=payload.ahj_profile or None)

    files: list[GeneratedFile] = []

    if progress:
        progress("report", "Writing calculation and engineering report.", 30)
    write_json(result, output_dir / "calculation.json")
    write_markdown(result, output_dir / "report.md")
    files.extend([
        _file(project_dir, job_id, "Inputs YAML", inputs_path),
        _file(project_dir, job_id, "Calculation JSON", output_dir / "calculation.json"),
        _file(project_dir, job_id, "Engineering Report", output_dir / "report.md"),
    ])

    if payload.outputs.customer:
        if progress:
            progress("customer", "Rendering customer summary PDF.", 42)
        customer_pdf = output_dir / "customer-summary.pdf"
        render_customer_summary(result, customer_pdf)
        files.append(_file(project_dir, job_id, "Customer Summary PDF", customer_pdf))

    if payload.outputs.permit:
        if progress:
            progress("permit", "Rendering permit package PDF.", 55)
        permit_pdf = output_dir / f"permit-package-{inputs.project.id}.pdf"
        pages = build_permit_package(
            result,
            permit_pdf,
            ahj_name=payload.ahj_profile or None,
            package_profile=payload.permit_profile,
            project_dir=project_dir,
        )
        files.append(_file(
            project_dir,
            job_id,
            f"Permit Package PDF ({pages} pages)",
            permit_pdf,
        ))

    if payload.outputs.dxf:
        if progress:
            progress("dxf", "Rendering DXF sheets and PNG previews.", 72)
        ee1 = output_dir / "sheet-EE-1.dxf"
        ee2 = output_dir / "sheet-EE-2.dxf"
        render_dxf(result, ee1)
        render_grounding_dxf(result, ee2)
        _add_dxf_with_preview(project_dir, job_id, files, "EE-1 Three-line DXF", ee1)
        _add_dxf_with_preview(project_dir, job_id, files, "EE-2 Grounding DXF", ee2)
        if _should_emit_one_line(result):
            ee21 = output_dir / "sheet-EE-2.1.dxf"
            render_one_line_dxf(result, ee21)
            _add_dxf_with_preview(
                project_dir, job_id, files, "EE-2.1 One-line DXF", ee21,
            )

    if payload.outputs.labels:
        if progress:
            progress("labels", "Rendering NEC labels.", 84)
        labels_pdf = output_dir / "labels.pdf"
        count = render_labels(result, labels_pdf)
        files.append(_file(project_dir, job_id, f"NEC Labels PDF ({count})", labels_pdf))

    if payload.outputs.qet:
        if progress:
            progress("qet", "Injecting QET single-line project.", 90)
        qet_path = output_dir / "system.qet"
        inject_from_result(result, template_path=QET_TEMPLATE, output_path=qet_path)
        files.append(_file(project_dir, job_id, "QET Single-line Project", qet_path))

    if progress:
        progress("bom", "Computing BOM and cost summary.", 92)
    bom_payload = build_bom_payload(result)
    bom_path = output_dir / "bom-cost.json"
    bom_path.write_text(
        json.dumps(bom_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    files.append(_file(project_dir, job_id, "BOM + Cost JSON", bom_path))
    bom_csv_path = output_dir / "bom-cost.csv"
    write_bom_csv(bom_payload, bom_csv_path)
    files.append(_file(project_dir, job_id, "BOM + Cost CSV", bom_csv_path))

    if progress:
        progress("readiness", "Writing source-data readiness reports.", 96)
    readiness_payload = write_readiness_artifacts(result, project_dir, output_dir)
    files.extend([
        _file(
            project_dir,
            job_id,
            "Reference Readiness Report",
            output_dir / "reference-readiness.md",
        ),
        _file(
            project_dir,
            job_id,
            "Real Data Checklist",
            output_dir / "real-data-checklist.md",
        ),
    ])

    summary = build_summary(result, bom_payload)
    source_materials = build_source_materials(payload)
    manifest = {
        "job_id": job_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_name": inputs.project.name,
        "project_dir": str(project_dir),
        "system_kw_dc": summary["system_kw_dc"],
        "installed_cost_usd": bom_payload["installed_cost_usd"],
        "site_data_source": source_materials["site_data_source"],
        "readiness": readiness_payload,
        "status": "done",
    }
    manifest_path = project_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    files.append(_file(project_dir, job_id, "Project Manifest JSON", manifest_path))

    artifact_manifest_path = output_dir / "artifact-manifest.json"
    artifact_manifest_path.write_text(
        json.dumps(
            build_artifact_manifest(
                files,
                summary=summary,
                bom=bom_payload,
                source_materials=source_materials,
                readiness=readiness_payload,
            ),
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    files.append(_file(
        project_dir, job_id, "Artifact Manifest JSON", artifact_manifest_path,
    ))

    if progress:
        progress("archive", "Creating complete project ZIP.", 98)
    archive_path = create_project_archive(project_dir, job_id)
    files.append(_file(project_dir, job_id, "Complete Project ZIP", archive_path))

    return WebJobResponse(
        job_id=job_id,
        project_dir=str(project_dir),
        status="done",
        summary=summary,
        bom=bom_payload,
        source_materials=source_materials,
        readiness=readiness_payload,
        files=files,
    )


def build_inputs_data(payload: WebProjectRequest, *, project_id: str) -> dict[str, Any]:
    module = _selected_module(payload)
    inverter = _selected_inverter(payload)
    battery = _selected_battery(payload)
    cost_override: dict[str, Any] = {
        "pv_turnkey_usd_per_w": payload.pv_turnkey_usd_per_w,
        "inverter_ref": _inverter_ref(payload.inverter_choice),
    }
    if payload.battery_quantity > 0 and payload.battery_choice != "none":
        cost_override["battery_ref"] = _battery_ref(payload.battery_choice)
    if payload.inverter_cost_usd_total is not None:
        cost_override["inverter_cost_usd_total"] = payload.inverter_cost_usd_total
    if payload.battery_cost_usd_total is not None:
        cost_override["battery_cost_usd_total"] = payload.battery_cost_usd_total

    interconnection_methods = [payload.interconnection_method]
    for method in ("120%_rule", "sum_rule", "supply_side_tap"):
        if method not in interconnection_methods:
            interconnection_methods.append(method)

    modules_per_string = payload.modules // payload.strings
    return {
        "project": {
            "id": project_id,
            "name": payload.project_name,
            "location": payload.location,
            "ahj": payload.ahj,
            "ahj_profile": payload.ahj_profile,
            "nec_edition": payload.nec_edition,
            "client_name": payload.client_name,
            "site_address": payload.site_address,
            "coordinates": payload.coordinates,
            "apn": payload.apn,
            "utility": payload.utility,
            "permit_profile": payload.permit_profile,
            "structural_letter_pdf": payload.structural_letter_path,
            "installer_cost_overrides": cost_override,
            "roof_info": {
                "type": payload.roof_info_type,
                "height_ft": payload.roof_info_height_ft,
                "construction": payload.roof_construction,
                "condition": payload.roof_condition,
                "framing": payload.roof_framing,
                "attic_access": payload.roof_attic_access,
                "decking_thickness_in": payload.decking_thickness_in,
                "roof_layers": payload.roof_layers,
            },
            "meter_info": {
                "number": payload.meter_number,
                "location": payload.meter_location,
                "esid": payload.meter_esid,
            },
            "site_photos": [
                {
                    "kind": ref.kind,
                    "path": ref.path,
                    "caption": ref.caption,
                }
                for ref in payload.site_photo_refs
                if ref.path
            ],
            "spec_sheets": [
                {
                    "equipment": ref.equipment,
                    "path": ref.path,
                    "pages": ref.pages,
                }
                for ref in payload.spec_sheet_refs
                if ref.path
            ],
        },
        "design_engineer": {
            "firm": payload.engineer_firm,
            "address": payload.engineer_address,
            "contact_email": payload.engineer_email,
            "contact_phone": payload.engineer_phone,
            "firm_number": payload.engineer_firm_number,
        },
        "installer": {
            "company": payload.installer_company,
            "address": payload.installer_address,
        },
        "pv_array": {
            "modules": payload.modules,
            "strings": payload.strings,
            "modules_per_string": modules_per_string,
            "temp_min_c": payload.temp_min_c,
            "temp_max_c": payload.temp_max_c,
            "module": {
                "brand": module.brand,
                "model": module.model,
                "power_w": module.power_w,
                "voc_stc": module.voc_stc,
                "isc_stc": module.isc_stc,
                "voc_temp_coeff_pct_per_c": module.voc_temp_coeff_pct_per_c,
                "isc_temp_coeff_pct_per_c": module.isc_temp_coeff_pct_per_c,
                "length_in": module.length_in,
                "width_in": module.width_in,
                "weight_lbs": module.weight_lbs,
            },
        },
        "battery": {
            "brand": battery.brand,
            "model": battery.model,
            "quantity": payload.battery_quantity,
            "nominal_voltage": battery.nominal_voltage,
            "capacity_kwh_each": (
                battery.capacity_kwh_each if payload.battery_quantity > 0 else 0.0
            ),
            "install_location": payload.battery_install_location,
            "distance_to_doorway_ft": payload.distance_to_doorway_ft,
            "distance_to_window_ft": payload.distance_to_window_ft,
            "distance_to_egress_ft": payload.distance_to_egress_ft,
        },
        "inverter": {
            "brand": inverter.brand,
            "model": inverter.model,
            "quantity": payload.inverter_quantity,
            "ac_output_v": inverter.ac_output_v,
            "ac_output_a": inverter.ac_output_a,
            "dc_afci": inverter.dc_afci,
            "ul1699b_listed": inverter.ul1699b_listed,
        },
        "optimizer": {
            "brand": payload.optimizer_brand,
            "model": payload.optimizer_model,
            "count": "per_module",
            "type": "pass_through",
        },
        "service": {
            "main_panel_a": payload.main_panel_a,
            "busbar_a": payload.busbar_a,
            "busbar_source": "nameplate",
            "voltage": payload.service_voltage,
            "interconnection_methods": interconnection_methods,
        },
        "loads": {
            "monthly_kwh": payload.monthly_kwh,
            "export_tariff_model": payload.export_tariff_model,
            "self_consumption_fraction": payload.self_consumption_fraction,
        },
        "site": {
            "roof_pitch_deg": payload.roof_pitch_deg,
            "array_azimuth_deg": payload.roof_azimuth_deg,
            "roof_sections": [
                {
                    "name": "Primary Roof",
                    "shape": "rect",
                    "roof_type": payload.roof_info_type or "Comp Shingle",
                    "pitch_deg": payload.roof_pitch_deg,
                    "azimuth_deg": payload.roof_azimuth_deg,
                    "width_ft": payload.roof_width_ft,
                    "height_ft": payload.roof_height_ft,
                    "module_count": payload.modules,
                }
            ],
            "equipment_locations": _equipment_locations_payload(payload),
        },
    }


def build_preflight_response(payload: WebProjectRequest) -> WebPreflightResponse:
    inputs_data = build_inputs_data(payload, project_id="web-preflight")
    inputs = Inputs.model_validate(inputs_data)
    result = run(inputs, ahj_profile=payload.ahj_profile or None)
    bom_payload = build_bom_payload(result)
    summary = build_summary(result, bom_payload)
    issues = _preflight_issues(payload, result, bom_payload)
    errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [issue for issue in issues if issue.severity == "warning"]
    status: Literal["PASS", "WARN", "FAIL"] = (
        "FAIL" if errors else ("WARN" if warnings else "PASS")
    )
    return WebPreflightResponse(
        status=status,
        summary=summary,
        estimate={
            "parts_subtotal_usd": bom_payload["parts_subtotal_usd"],
            "installed_cost_usd": bom_payload["installed_cost_usd"],
            "cost_after_itc_usd": bom_payload["cost_after_itc_usd"],
            "annual_bill_savings_usd": bom_payload["annual_bill_savings_usd"],
            "payback_after_itc_years": bom_payload["payback_after_itc_years"],
            "quote_tiers": bom_payload["quote_tiers"],
            "cost_source": bom_payload["cost_source"],
        },
        intake=_preflight_intake(payload),
        issues=issues,
    )


def build_address_lookup_response(
    address: str,
    *,
    mode: Literal["offline", "online"] = "online",
) -> WebAddressLookupResponse:
    raw = address.strip()
    if not raw:
        raise ValueError("address is required")
    providers = WEB_OFFLINE_LOOKUP_PROVIDERS if mode == "offline" else None
    result = resolve_lookup(raw, providers=providers)
    suggested = _lookup_suggested_payload(result.fields, result.address)
    roof_sections = result.fields.get("roof_sections") or []
    roof_summary = {
        "section_count": len(roof_sections) if isinstance(roof_sections, list) else 0,
        "imagery_quality": result.fields.get("google_solar_imagery_quality", ""),
        "imagery_date": result.fields.get("google_solar_imagery_date", ""),
        "max_panels": result.fields.get("google_solar_max_panels"),
        "whole_roof_area_m2": result.fields.get("google_solar_whole_roof_area_m2"),
        "selected_section": _best_roof_section(roof_sections) or {},
    }
    providers_payload = [
        WebLookupProvider(
            source=provider.source,
            confidence=provider.confidence,
            hit=provider.hit,
            note=provider.note,
            fields=sorted(provider.fields),
        )
        for provider in result.provider_results
    ]
    return WebAddressLookupResponse(
        status="PASS" if suggested else "WARN",
        mode=mode,
        address={
            "raw": result.address.raw,
            "street": result.address.street,
            "city": result.address.city,
            "state": result.address.state,
            "zip_code": result.address.zip_code,
        },
        suggested_payload=suggested,
        fields=result.fields,
        field_sources=result.field_sources,
        field_confidence=result.field_confidence,
        providers=providers_payload,
        roof_summary=roof_summary,
    )


def _lookup_suggested_payload(fields: dict[str, Any], address) -> dict[str, Any]:
    suggested: dict[str, Any] = {}
    canonical = fields.get("canonical_address")
    if canonical:
        suggested["site_address"] = canonical
    elif address.raw:
        suggested["site_address"] = address.raw
    if address.city and address.state:
        suggested["location"] = f"{address.city}, {address.state}"
    if "latitude" in fields and "longitude" in fields:
        suggested["coordinates"] = (
            f"{float(fields['latitude']):.6f}, {float(fields['longitude']):.6f}"
        )
    if utility := fields.get("utility_name"):
        suggested["utility"] = utility
    if ahj := fields.get("ahj_name"):
        suggested["ahj"] = ahj
    if str(fields.get("nec_edition", "")) in {"2017", "2020", "2023"}:
        suggested["nec_edition"] = str(fields["nec_edition"])
    if tariff := fields.get("recommended_export_tariff"):
        suggested["export_tariff_model"] = tariff

    section = _best_roof_section(fields.get("roof_sections") or [])
    if section:
        suggested["roof_pitch_deg"] = section["pitch_deg"]
        suggested["roof_azimuth_deg"] = section["azimuth_deg"]
        suggested["roof_width_ft"] = section["width_ft"]
        suggested["roof_height_ft"] = section["height_ft"]
        suggested["roof_info_type"] = section.get("roof_type") or "Comp Shingle"
    return suggested


def _best_roof_section(sections: Any) -> dict[str, Any] | None:
    if not isinstance(sections, list):
        return None
    candidates = [
        section for section in sections
        if isinstance(section, dict)
        and isinstance(section.get("width_ft"), (int, float))
        and isinstance(section.get("height_ft"), (int, float))
    ]
    if not candidates:
        return None

    def score(section: dict[str, Any]) -> float:
        area = float(section.get("width_ft", 0)) * float(section.get("height_ft", 0))
        azimuth = float(section.get("azimuth_deg", 180)) % 360
        # Favor larger southerly faces in the northern hemisphere.
        south_delta = abs(((azimuth - 180 + 180) % 360) - 180)
        orientation_score = max(0.35, 1.0 - south_delta / 180.0)
        return area * orientation_score

    selected = max(candidates, key=score)
    return {
        "name": selected.get("name", "Roof Section"),
        "pitch_deg": selected.get("pitch_deg"),
        "azimuth_deg": selected.get("azimuth_deg"),
        "width_ft": selected.get("width_ft"),
        "height_ft": selected.get("height_ft"),
        "roof_type": selected.get("roof_type", "Comp Shingle"),
    }


def _preflight_issues(
    payload: WebProjectRequest,
    result,
    bom_payload: dict[str, Any],
) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []

    def warn(field: str, message: str) -> None:
        issues.append(PreflightIssue(
            severity="warning", field=field, message=message,
        ))

    def error(field: str, message: str) -> None:
        issues.append(PreflightIssue(
            severity="error", field=field, message=message,
        ))

    if not any(payload.outputs.model_dump().values()):
        warn("outputs", "No optional deliverables selected; only core JSON/report will be generated.")
    if result.interconnect.overall_status != "PASS":
        warn(
            "service.interconnection_method",
            f"Interconnection status is {result.interconnect.overall_status}; review {result.interconnect.recommended}.",
        )
    if payload.site_data_source == "simulated":
        warn("site_data_source", "Simulated source materials are fine for preview, but not AHJ-ready.")
    if not payload.monthly_kwh:
        warn("monthly_kwh", "12-month usage is missing; savings and payback use fallback assumptions.")
    if payload.battery_quantity > 0 and payload.battery_install_location == "unknown":
        warn("battery_install_location", "ESS install location is unknown; IRC/NEC placement review remains open.")
    if payload.battery_quantity > 0 and payload.battery_install_location in {"indoor", "garage"}:
        for field, value in (
            ("distance_to_doorway_ft", payload.distance_to_doorway_ft),
            ("distance_to_window_ft", payload.distance_to_window_ft),
            ("distance_to_egress_ft", payload.distance_to_egress_ft),
        ):
            if value and value < 3.0:
                warn(field, "ESS clearance is below 3 ft; verify IRC R328/AHJ requirements.")
    if payload.permit_profile in {"tx_residential_pv", "wyssling_like"}:
        for field, value in (
            ("coordinates", payload.coordinates),
            ("apn", payload.apn),
            ("meter_number", payload.meter_number),
            ("meter_location", payload.meter_location),
            ("engineer_firm", payload.engineer_firm),
            ("engineer_firm_number", payload.engineer_firm_number),
            ("engineer_email", payload.engineer_email),
            ("engineer_phone", payload.engineer_phone),
            ("installer_address", payload.installer_address),
        ):
            if not str(value or "").strip():
                warn(field, "Reference-profile permit package is missing this field.")
    if "TX" in (payload.site_address or payload.location).upper() and not payload.meter_esid:
        warn("meter_esid", "Texas ESID is missing.")
    if not payload.structural_letter_path:
        warn("structural_letter", "No signed structural packet is attached yet.")
    if len(payload.spec_sheet_refs) == 0:
        warn("spec_sheets", "No manufacturer spec sheets are attached yet.")
    if bom_payload["installed_cost_usd"] <= 0:
        error("cost", "Installed cost evaluated to zero or below.")
    return issues


def _preflight_intake(payload: WebProjectRequest) -> dict[str, Any]:
    checks = [
        ("Project identity", bool(payload.project_name and payload.site_address)),
        ("Coordinates", bool(payload.coordinates)),
        ("APN", bool(payload.apn)),
        ("Meter", bool(payload.meter_number and payload.meter_location)),
        ("ESID", bool(payload.meter_esid) or "TX" not in (payload.site_address or payload.location).upper()),
        ("Engineer", bool(payload.engineer_firm and payload.engineer_firm_number and payload.engineer_email and payload.engineer_phone)),
        ("Installer", bool(payload.installer_company and payload.installer_address)),
        ("Roof survey", bool(
            payload.roof_info_type
            and payload.roof_info_height_ft > 0
            and (payload.roof_construction or payload.roof_framing)
            and payload.roof_condition != "unknown"
            and payload.roof_attic_access != "unknown"
            and payload.decking_thickness_in > 0
            and payload.roof_layers > 0
        )),
        ("Monthly usage", len(payload.monthly_kwh) == 12),
        ("Equipment coordinates", bool(
            payload.msp_x_ft is not None
            and payload.msp_y_ft is not None
            and payload.inverter_x_ft is not None
            and payload.inverter_y_ft is not None
        )),
        ("Structural packet", bool(payload.structural_letter_path)),
        ("Spec sheets", bool(payload.spec_sheet_refs)),
    ]
    ready = sum(1 for _label, passed in checks if passed)
    return {
        "ready": ready,
        "total": len(checks),
        "percent": round(ready / len(checks) * 100, 1),
        "items": [
            {"label": label, "ready": bool(passed)}
            for label, passed in checks
        ],
    }


def _equipment_locations_payload(payload: WebProjectRequest) -> dict[str, Any]:
    data: dict[str, Any] = {}

    msp = _equipment_point("MSP", payload.msp_x_ft, payload.msp_y_ft)
    if msp:
        data["msp"] = msp

    inverter = _equipment_point(
        "INV-1", payload.inverter_x_ft, payload.inverter_y_ft,
    )
    if inverter:
        data["inverters"] = [inverter]

    ac_disconnect = _equipment_point(
        "AC-DISC-1", payload.ac_disconnect_x_ft, payload.ac_disconnect_y_ft,
    )
    if ac_disconnect:
        data["ac_disconnect"] = ac_disconnect

    ess = _equipment_point("ESS-1", payload.ess_x_ft, payload.ess_y_ft)
    if ess and payload.battery_quantity > 0:
        data["ess_units"] = [ess]

    if payload.attic_drop_x_ft is not None:
        data["attic_drop_x_ft"] = payload.attic_drop_x_ft
    if payload.attic_drop_y_ft is not None:
        data["attic_drop_y_ft"] = payload.attic_drop_y_ft
    data["attic_to_eq_height_ft"] = payload.attic_to_eq_height_ft
    return data


def _equipment_point(
    label: str,
    x_ft: float | None,
    y_ft: float | None,
) -> dict[str, Any] | None:
    if x_ft is None or y_ft is None:
        return None
    return {"label": label, "x_ft": x_ft, "y_ft": y_ft}


async def _read_upload(upload: UploadFile | None) -> UploadedMaterial | None:
    if upload is None or not upload.filename:
        return None
    content = await upload.read()
    if not content:
        return None
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError(f"{upload.filename} exceeds 20 MB upload limit")
    return UploadedMaterial(
        filename=upload.filename,
        content_type=upload.content_type or "",
        content=content,
    )


def _attach_site_materials(
    payload: WebProjectRequest,
    project_dir: Path,
    site_uploads: dict[str, UploadedMaterial],
    utility_bill_upload: UploadedMaterial | None,
    structural_upload: UploadedMaterial | None,
    spec_uploads: dict[str, UploadedMaterial],
    *,
    create_mock_photos: bool,
) -> WebProjectRequest:
    photo_refs = [
        ref
        for ref in payload.site_photo_refs
        if ref.path
    ]
    by_kind = {ref.kind: ref for ref in photo_refs}
    photos_dir = project_dir / "source_materials" / "photos"

    for kind, upload in site_uploads.items():
        if kind not in SITE_PHOTO_LABELS:
            continue
        photos_dir.mkdir(parents=True, exist_ok=True)
        path = photos_dir / _safe_filename(upload.filename, default=f"{kind}.jpg")
        path.write_bytes(upload.content)
        ref = WebSitePhotoRef(
            kind=kind,  # type: ignore[arg-type]
            path=str(path.resolve()),
            caption=SITE_PHOTO_LABELS[kind],
        )
        by_kind[kind] = ref

    if payload.site_data_source == "simulated" and create_mock_photos:
        photos_dir.mkdir(parents=True, exist_ok=True)
        for kind, label in REQUIRED_PHOTOS:
            if kind in by_kind:
                continue
            path = photos_dir / f"mock-{kind.replace('_', '-')}.png"
            if not path.exists():
                _write_mock_photo(path, label)
            by_kind[kind] = WebSitePhotoRef(
                kind=kind,  # type: ignore[arg-type]
                path=str(path.resolve()),
                caption=f"{label} (simulated)",
            )

    utility_path = payload.utility_bill_path
    if utility_bill_upload is not None:
        docs_dir = project_dir / "source_materials" / "utility"
        docs_dir.mkdir(parents=True, exist_ok=True)
        path = docs_dir / _safe_filename(
            utility_bill_upload.filename,
            default="utility-bill.pdf",
        )
        path.write_bytes(utility_bill_upload.content)
        utility_path = str(path.resolve())

    structural_path = payload.structural_letter_path
    if structural_upload is not None:
        structural_dir = project_dir / "source_materials" / "structural"
        structural_dir.mkdir(parents=True, exist_ok=True)
        path = structural_dir / _safe_filename(
            structural_upload.filename,
            default="structural-letter.pdf",
        )
        path.write_bytes(structural_upload.content)
        structural_path = str(path.resolve())

    spec_refs = [
        ref
        for ref in payload.spec_sheet_refs
        if ref.path
    ]
    by_equipment = {ref.equipment: ref for ref in spec_refs}
    if spec_uploads:
        specs_dir = project_dir / "source_materials" / "spec_sheets"
        specs_dir.mkdir(parents=True, exist_ok=True)
        for equipment, upload in spec_uploads.items():
            path = specs_dir / _safe_filename(
                upload.filename,
                default=f"{equipment}-spec.pdf",
            )
            path.write_bytes(upload.content)
            by_equipment[equipment] = WebSpecSheetRef(
                equipment=equipment,  # type: ignore[arg-type]
                path=str(path.resolve()),
                pages=[],
            )

    updated_refs = [
        by_kind[kind]
        for kind, _label in REQUIRED_PHOTOS
        if kind in by_kind
    ]
    updated_refs.extend(
        ref for ref in photo_refs
        if ref.kind not in {kind for kind, _label in REQUIRED_PHOTOS}
    )
    updated = payload.model_copy(update={
        "site_photo_refs": updated_refs,
        "utility_bill_path": utility_path,
        "structural_letter_path": structural_path,
        "spec_sheet_refs": list(by_equipment.values()),
    })
    _write_source_pack(project_dir, updated)
    return updated


def _write_source_pack(project_dir: Path, payload: WebProjectRequest) -> None:
    photo_files = [
        _project_relative(project_dir, Path(ref.path))
        for ref in payload.site_photo_refs
        if ref.path
    ]
    required_kinds = {kind for kind, _label in REQUIRED_PHOTOS}
    supplied_kinds = {ref.kind for ref in payload.site_photo_refs if ref.path}
    missing_kinds = sorted(required_kinds - supplied_kinds)
    photo_status = (
        "missing"
        if missing_kinds
        else ("simulated" if payload.site_data_source == "simulated" else "ready")
    )
    utility_files = (
        [_project_relative(project_dir, Path(payload.utility_bill_path))]
        if payload.utility_bill_path else []
    )
    usage_status = "ready" if payload.monthly_kwh else "missing"
    structural_files = (
        [_project_relative(project_dir, Path(payload.structural_letter_path))]
        if payload.structural_letter_path else []
    )
    spec_files = [
        _project_relative(project_dir, Path(ref.path))
        for ref in payload.spec_sheet_refs
        if ref.path
    ]
    roof_status = (
        "ready"
        if (
            payload.roof_info_type
            and payload.roof_info_height_ft > 0
            and (payload.roof_construction or payload.roof_framing)
            and payload.roof_condition != "unknown"
            and payload.roof_attic_access != "unknown"
            and payload.decking_thickness_in > 0
            and payload.roof_layers > 0
        )
        else "missing"
    )
    equipment_status = (
        "ready"
        if (
            payload.msp_x_ft is not None
            and payload.msp_y_ft is not None
            and payload.inverter_x_ft is not None
            and payload.inverter_y_ft is not None
        )
        else "missing"
    )
    engineer_status = (
        "ready"
        if (
            payload.engineer_firm
            and payload.engineer_firm_number
            and payload.engineer_email
            and payload.engineer_phone
        )
        else "missing"
    )
    installer_status = (
        "ready"
        if payload.installer_company and payload.installer_address
        else "missing"
    )
    data = {
        "version": 1,
        "name": f"{payload.project_name or 'web-project'}-web-source-data",
        "updated": datetime.now(timezone.utc).date().isoformat(),
        "purpose": (
            "Web project source-material manifest for distinguishing uploaded "
            "field data from simulated intake defaults."
        ),
        "sources": {
            "project.site_photos": {
                "status": photo_status,
                "source": (
                    "web-generated mock photos"
                    if payload.site_data_source == "simulated"
                    else "web-uploaded site-survey photos"
                ),
                "replacement": "actual site-survey photos from installer/homeowner",
                "files": photo_files,
            },
            "loads.monthly_kwh": {
                "status": usage_status,
                "source": (
                    "web form monthly usage values"
                    if payload.monthly_kwh else "no utility usage uploaded"
                ),
                "replacement": "12-month utility bill history or Smart Meter export",
                "files": utility_files,
            },
            "project.structural_letter_pdf": {
                "status": "ready" if structural_files else "missing",
                "source": (
                    "web-uploaded structural packet"
                    if structural_files else "no structural packet uploaded"
                ),
                "replacement": "signed/sealed structural letter PDF",
                "files": structural_files,
            },
            "project.spec_sheets": {
                "status": "ready" if spec_files else "missing",
                "source": (
                    "web-uploaded manufacturer PDFs"
                    if spec_files else "no manufacturer PDFs uploaded"
                ),
                "replacement": "manufacturer cut sheets for selected equipment",
                "files": spec_files,
            },
            "project.roof_info": {
                "status": roof_status,
                "source": "web field-intake roof survey values",
                "replacement": "field-verified roof type/framing/decking/attic data",
                "files": [],
            },
            "site.equipment_locations": {
                "status": equipment_status,
                "source": "web field-intake site coordinate values",
                "replacement": "field-verified equipment coordinates",
                "files": [],
            },
            "design_engineer": {
                "status": engineer_status,
                "source": "web field-intake engineer metadata",
                "replacement": "engineer-of-record metadata",
                "files": [],
            },
            "installer": {
                "status": installer_status,
                "source": "web field-intake installer metadata",
                "replacement": "contracted installer company/address",
                "files": [],
            },
        },
    }
    (project_dir / "simulated-site-data.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def build_source_materials(payload: WebProjectRequest) -> dict[str, Any]:
    required_kinds = {kind for kind, _label in REQUIRED_PHOTOS}
    supplied_kinds = {ref.kind for ref in payload.site_photo_refs if ref.path}
    spec_files = [
        {
            "equipment": ref.equipment,
            "file": Path(ref.path).name,
        }
        for ref in payload.spec_sheet_refs
        if ref.path
    ]
    return {
        "site_data_source": payload.site_data_source,
        "site_photo_count": len(supplied_kinds & required_kinds),
        "required_site_photo_count": len(required_kinds),
        "missing_photo_kinds": sorted(required_kinds - supplied_kinds),
        "utility_bill_uploaded": bool(payload.utility_bill_path),
        "structural_letter_uploaded": bool(payload.structural_letter_path),
        "spec_sheet_count": len(spec_files),
        "monthly_kwh_count": len(payload.monthly_kwh),
        "equipment_locations_ready": (
            payload.msp_x_ft is not None
            and payload.msp_y_ft is not None
            and payload.inverter_x_ft is not None
            and payload.inverter_y_ft is not None
        ),
        "site_photos": [
            {
                "kind": ref.kind,
                "caption": ref.caption,
                "file": Path(ref.path).name if ref.path else "",
            }
            for ref in payload.site_photo_refs
        ],
        "spec_sheets": spec_files,
    }


def write_readiness_artifacts(result, project_dir: Path, output_dir: Path) -> dict[str, Any]:
    readiness = assess_reference_profile_readiness(result, project_dir)
    report_path = output_dir / "reference-readiness.md"
    checklist_path = output_dir / "real-data-checklist.md"
    report_path.write_text(
        format_reference_readiness_markdown(readiness),
        encoding="utf-8",
    )
    checklist_path.write_text(
        format_real_data_checklist_markdown(readiness),
        encoding="utf-8",
    )
    counts = readiness.counts
    review_items = [
        item for item in readiness.items
        if item.status in {"missing", "simulated"}
    ]
    return {
        "status": "WARN" if readiness.needs_review else "PASS",
        "needs_review": readiness.needs_review,
        "detail": readiness.doctor_detail(limit=10),
        "counts": {
            "ready": counts["ready"],
            "simulated": counts["simulated"],
            "missing": counts["missing"],
            "not_applicable": counts["not_applicable"],
        },
        "review_items": [
            {
                "key": item.key,
                "status": item.status,
                "detail": item.detail,
            }
            for item in review_items[:10]
        ],
        "source_pack": (
            readiness.source_pack.path.name
            if readiness.source_pack is not None else ""
        ),
    }


def write_bom_csv(bom_payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Item", "Quantity", "Unit Price USD", "Total USD", "Note"])
    for line in bom_payload["lines"]:
        writer.writerow([
            line["label"],
            line["quantity"],
            line["unit_price_usd"],
            line["total_usd"],
            line.get("note", ""),
        ])
    writer.writerow([])
    writer.writerow(["Parts subtotal", "", "", bom_payload["parts_subtotal_usd"], ""])
    writer.writerow([
        "Estimated labor and soft costs",
        "",
        "",
        bom_payload["estimated_labor_soft_costs_usd"],
        "",
    ])
    writer.writerow(["Installed cost", "", "", bom_payload["installed_cost_usd"], ""])
    writer.writerow(["Cost after ITC", "", "", bom_payload["cost_after_itc_usd"], ""])
    path.write_text(buffer.getvalue(), encoding="utf-8", newline="")


def build_artifact_manifest(
    files: list[GeneratedFile],
    *,
    summary: dict[str, Any],
    bom: dict[str, Any],
    source_materials: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    by_category: dict[str, int] = {}
    for file in files:
        by_category[file.category] = by_category.get(file.category, 0) + 1
    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_name": summary["project_name"],
        "system_kw_dc": summary["system_kw_dc"],
        "installed_cost_usd": bom["installed_cost_usd"],
        "cost_after_itc_usd": bom["cost_after_itc_usd"],
        "readiness_status": readiness.get("status"),
        "site_data_source": source_materials.get("site_data_source"),
        "category_counts": by_category,
        "files": [
            {
                "label": file.label,
                "path": file.path,
                "category": file.category,
                "kind": file.kind,
                "bytes": file.bytes,
            }
            for file in files
        ],
    }


def create_project_archive(project_dir: Path, job_id: str) -> Path:
    archive_path = project_dir / "output" / f"project-package-{job_id}.zip"
    include_roots = [
        project_dir / "request.json",
        project_dir / "inputs.yaml",
        project_dir / "manifest.json",
        project_dir / "simulated-site-data.yaml",
        project_dir / "output",
        project_dir / "source_materials",
    ]
    with zipfile.ZipFile(
        archive_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as zf:
        for root in include_roots:
            if not root.exists():
                continue
            if root.is_file():
                _zip_write(project_dir, zf, root, archive_path)
                continue
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    _zip_write(project_dir, zf, path, archive_path)
    return archive_path


def _zip_write(
    project_dir: Path,
    zf: zipfile.ZipFile,
    path: Path,
    archive_path: Path,
) -> None:
    if path.resolve() == archive_path.resolve():
        return
    zf.write(path, path.relative_to(project_dir).as_posix())


def _safe_filename(filename: str, *, default: str) -> str:
    raw_name = Path(filename or default).name
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", Path(raw_name).stem).strip(".-")
    suffix = re.sub(r"[^A-Za-z0-9.]+", "", Path(raw_name).suffix.lower())
    default_suffix = Path(default).suffix
    return f"{stem[:48] or Path(default).stem}{suffix or default_suffix}"


def _project_relative(project_dir: Path, path: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(project_dir.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _write_mock_photo(path: Path, label: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    fig = plt.figure(figsize=(6.4, 4.0), dpi=120)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.add_patch(Rectangle((0, 0), 1, 1, facecolor="#eef3f8", edgecolor="#9aa8b8"))
    ax.add_patch(Rectangle((0.04, 0.08), 0.92, 0.84, fill=False, edgecolor="#1f5fbf", linewidth=2))
    ax.text(
        0.5,
        0.56,
        "SIMULATED SITE PHOTO",
        ha="center",
        va="center",
        fontsize=16,
        fontweight="bold",
        color="#1d2430",
    )
    ax.text(
        0.5,
        0.43,
        label,
        ha="center",
        va="center",
        fontsize=12,
        color="#596273",
    )
    fig.savefig(path, format="png")
    plt.close(fig)


def build_bom_payload(result) -> dict[str, Any]:
    bom = compute_bom(result)
    economics = compute_economics(result.inputs)
    categories = categorize_bom(bom)
    soft_costs = max(economics.installed_cost_usd - bom.subtotal_usd, 0.0)
    return {
        "parts_subtotal_usd": round(bom.subtotal_usd, 2),
        "estimated_labor_soft_costs_usd": round(soft_costs, 2),
        "installed_cost_usd": round(economics.installed_cost_usd, 2),
        "cost_after_itc_usd": round(economics.cost_after_itc_usd, 2),
        "itc_rate": economics.itc_rate_used,
        "monthly_bill_savings_usd": round(economics.monthly_bill_savings_usd, 2),
        "annual_bill_savings_usd": round(economics.annual_bill_savings_usd, 2),
        "payback_years": _round_optional(economics.payback_period_years),
        "payback_after_itc_years": _round_optional(economics.payback_after_itc_years),
        "cost_source": economics.cost_source,
        "note": bom.note,
        "categories": categories,
        "installed_breakdown": installed_breakdown(
            categories,
            installed_cost_usd=economics.installed_cost_usd,
        ),
        "quote_tiers": quote_tiers_for_result(result),
        "lines": [
            {
                "label": line.label,
                "quantity": line.quantity,
                "unit_price_usd": round(line.unit_price_usd, 2),
                "total_usd": round(line.total_usd, 2),
                "note": line.note,
            }
            for line in bom.lines
        ],
    }


def build_summary(result, bom_payload: dict[str, Any]) -> dict[str, Any]:
    inputs = result.inputs
    return {
        "project_name": inputs.project.name,
        "system_kw_dc": round(
            inputs.pv_array.modules * inputs.pv_array.module.power_w / 1000.0,
            3,
        ),
        "modules": inputs.pv_array.modules,
        "strings": inputs.pv_array.strings,
        "module_brand": inputs.pv_array.module.brand,
        "module_model": inputs.pv_array.module.model,
        "battery_kwh": round(inputs.battery.total_kwh, 2),
        "battery_brand": inputs.battery.brand,
        "battery_model": inputs.battery.model,
        "inverter_count": inputs.inverter.count(inputs.battery.quantity),
        "inverter_brand": inputs.inverter.brand,
        "inverter_model": inputs.inverter.model,
        "interconnect_status": result.interconnect.overall_status,
        "recommended_interconnection": result.interconnect.recommended,
        "pv_ocpd_a": result.pv_ocpd_a,
        "installed_cost_usd": bom_payload["installed_cost_usd"],
        "cost_after_itc_usd": bom_payload["cost_after_itc_usd"],
        "annual_bill_savings_usd": bom_payload["annual_bill_savings_usd"],
    }


def resolve_job_file(jobs_dir: Path, job_id: str, file_path: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", job_id):
        raise HTTPException(status_code=404, detail="job not found")
    base = (jobs_dir / job_id).resolve()
    path = (base / file_path).resolve()
    if not path.is_relative_to(base):
        raise HTTPException(status_code=403, detail="path outside job")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return path


def _inverter_ref(choice: str) -> str:
    return WEB_INVERTER_OPTIONS[choice]["ref"]


def _module_ref(choice: str) -> str:
    return WEB_MODULE_OPTIONS[choice]["ref"]


def _battery_ref(choice: str) -> str:
    return WEB_BATTERY_OPTIONS[choice]["ref"]


def _selected_module(payload: WebProjectRequest):
    return get_module(_module_ref(payload.module_choice))


def _selected_inverter(payload: WebProjectRequest):
    return get_inverter(_inverter_ref(payload.inverter_choice))


def _selected_battery(payload: WebProjectRequest):
    if payload.battery_choice == "none":
        return get_battery("inhouse_16kwh_hv").model_copy(update={
            "brand": "None",
            "model": "PV-only",
            "capacity_kwh_each": 0.0,
        })
    return get_battery(_battery_ref(payload.battery_choice))


def _get_inverter_by_ref(ref: str):
    return get_inverter(ref)


def _catalog_options(options: dict[str, dict[str, str]], loader) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, option in options.items():
        ref = option["ref"]
        device = loader(ref)
        rows.append({
            "key": key,
            "ref": ref,
            "label": option["label"],
            "brand": device.brand,
            "model": device.model,
            "power_w": getattr(device, "power_w", None),
            "ac_output_a": getattr(device, "ac_output_a", None),
            "ac_output_v": getattr(device, "ac_output_v", None),
        })
    return rows


def _battery_catalog_options() -> list[dict[str, Any]]:
    rows = [{"key": "none", "ref": "", "label": WEB_BATTERY_OPTIONS["none"]["label"]}]
    for key, option in WEB_BATTERY_OPTIONS.items():
        if key == "none":
            continue
        device = get_battery(option["ref"])
        rows.append({
            "key": key,
            "ref": option["ref"],
            "label": option["label"],
            "brand": device.brand,
            "model": device.model,
            "capacity_kwh_each": device.capacity_kwh_each,
            "nominal_voltage": device.nominal_voltage,
        })
    return rows


def _add_dxf_with_preview(
    project_dir: Path,
    job_id: str,
    files: list[GeneratedFile],
    label: str,
    dxf_path: Path,
) -> None:
    files.append(_file(project_dir, job_id, label, dxf_path))
    png_path = dxf_path.with_suffix(".png")
    export_preview_png(dxf_path, png_path)
    files.append(_file(project_dir, job_id, label.replace("DXF", "PNG Preview"), png_path))


def _file(project_dir: Path, job_id: str, label: str, path: Path) -> GeneratedFile:
    rel = path.relative_to(project_dir)
    category, kind = _classify_artifact(label, path)
    return GeneratedFile(
        label=label,
        path=rel.as_posix(),
        url=f"/files/{job_id}/{rel.as_posix()}",
        bytes=path.stat().st_size,
        category=category,
        kind=kind,
    )


def _classify_artifact(label: str, path: Path) -> tuple[str, str]:
    lower = label.lower()
    suffix = path.suffix.lower()
    if "inputs" in lower or path.name == "request.json":
        return "Input", "yaml" if suffix in {".yaml", ".yml"} else "json"
    if "bom" in lower:
        return "Cost", "csv" if suffix == ".csv" else "json"
    if "readiness" in lower or "checklist" in lower:
        return "Readiness", "markdown"
    if "manifest" in lower:
        return "Manifest", "json"
    if "complete project zip" in lower:
        return "Archive", "zip"
    if "permit" in lower or "labels" in lower or "customer" in lower:
        return "Permit", "pdf"
    if "dxf" in lower:
        return "CAD", "dxf"
    if "png preview" in lower:
        return "CAD", "preview"
    if "qet" in lower:
        return "CAD", "qet"
    if "calculation" in lower or "engineering report" in lower:
        return "Engineering", "json" if suffix == ".json" else "markdown"
    return "Other", suffix.lstrip(".") or "other"


def _make_job_id(payload: WebProjectRequest) -> str:
    seed = payload.project_id or payload.project_name or "pvess-web"
    slug = re.sub(r"[^A-Za-z0-9]+", "-", seed).strip("-").lower()
    slug = slug[:36] or "pvess-web"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{slug}-{stamp}-{uuid4().hex[:6]}"


def _round_optional(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 2)


@click.command(name="pvess-serve")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8765, show_default=True, type=int)
@click.option(
    "--workdir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Generated-job directory. Default: ~/.pvess/web_jobs",
)
@click.option(
    "--access-token",
    default=None,
    help="Optional shared token required for /api and /files requests.",
)
@click.option("--reload", is_flag=True, help="Enable uvicorn auto-reload.")
def serve_cmd(
    host: str,
    port: int,
    workdir: Path | None,
    access_token: str | None,
    reload: bool,
) -> None:
    """Run the local browser UI for PV + ESS project packages."""
    if workdir is not None:
        os.environ["PVESS_WEB_WORKDIR"] = str(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
    if access_token is not None:
        os.environ["PVESS_WEB_ACCESS_TOKEN"] = access_token
    import uvicorn

    app.state.jobs_dir = default_jobs_dir()
    app.state.access_token = default_access_token()
    app.state.job_store = JobStore(app.state.jobs_dir)
    app.state.job_store.ensure_ready()
    click.echo(f"PVESS web UI: http://{host}:{port}")
    click.echo(f"Jobs directory: {default_jobs_dir()}")
    if app.state.access_token:
        click.echo("Access token: enabled")
    uvicorn.run(
        "pvess_calc.web.server:app",
        host=host,
        port=port,
        reload=reload,
    )
