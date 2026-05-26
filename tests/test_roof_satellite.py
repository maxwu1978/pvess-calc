"""K.3c+ — Google Solar dataLayers wrapper + satellite renderer tests.

Three layers of coverage:

  1. **`google_solar_data_layers`** HTTP wrapper — happy path, key
     absent, HTTP 404 (building not found), 5xx, malformed payload.
  2. **`roof_satellite`** renderer — fed synthetic numpy arrays, asserts
     PNG is valid + correct dimensions.
  3. **CLI gate** — `--satellite` without `--confirm-cost` exits 4 with
     pricing warning; with confirm-cost or env-flag, proceeds.
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest
import responses
from PIL import Image

from pvess_calc.lookup.config import (
    ENV_GOOGLE_MAPS_KEY,
    ENV_GOOGLE_SOLAR_KEY,
    reset_cache_for_tests,
)
from pvess_calc.lookup.providers.google_solar_data_layers import (
    DataLayersError,
    DataLayersResult,
    download_layer_bytes,
    fetch_data_layers,
)


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    monkeypatch.delenv(ENV_GOOGLE_MAPS_KEY, raising=False)
    monkeypatch.delenv(ENV_GOOGLE_SOLAR_KEY, raising=False)
    monkeypatch.delenv("PVESS_ALLOW_PAID_RENDERS", raising=False)
    reset_cache_for_tests()
    yield
    reset_cache_for_tests()


# ─── PNG helpers (shared with test_roof_diagram) ──────────────────────


def _is_png(p: Path) -> bool:
    with p.open("rb") as f:
        return f.read(8) == b"\x89PNG\r\n\x1a\n"


# ─── dataLayers HTTP wrapper ──────────────────────────────────────────


_LAYERS_OK_PAYLOAD = {
    "imageryDate": {"year": 2024, "month": 2, "day": 6},
    "imageryProcessedDate": {"year": 2024, "month": 3, "day": 12},
    "imageryQuality": "HIGH",
    "rgbUrl":
        "https://solar.googleapis.com/v1/geoTiff:get?id=rgb-abc",
    "annualFluxUrl":
        "https://solar.googleapis.com/v1/geoTiff:get?id=flux-abc",
    "maskUrl":
        "https://solar.googleapis.com/v1/geoTiff:get?id=mask-abc",
    "dsmUrl":
        "https://solar.googleapis.com/v1/geoTiff:get?id=dsm-abc",
}


def test_fetch_data_layers_raises_without_key():
    """No key set → DataLayersError mentions PVESS_GOOGLE_SOLAR_KEY +
    .env.example. Catches the "user thought they were running the free
    path" confusion early."""
    with pytest.raises(DataLayersError, match="PVESS_GOOGLE_SOLAR_KEY"):
        fetch_data_layers(33.14, -96.80)


@responses.activate
def test_fetch_data_layers_happy_path_parses_urls(monkeypatch):
    """A canonical Google response → 4 layer URLs + imagery metadata."""
    monkeypatch.setenv(ENV_GOOGLE_SOLAR_KEY, "AIza-fake")
    reset_cache_for_tests()
    responses.get(
        "https://solar.googleapis.com/v1/dataLayers:get",
        json=_LAYERS_OK_PAYLOAD, status=200,
    )
    r: DataLayersResult = fetch_data_layers(33.14, -96.80)
    assert r.rgb_url.endswith("rgb-abc")
    assert r.annual_flux_url.endswith("flux-abc")
    assert r.mask_url.endswith("mask-abc")
    assert r.dsm_url.endswith("dsm-abc")
    assert r.imagery_date == "2024-02-06"
    assert r.imagery_processed_date == "2024-03-12"
    assert r.imagery_quality == "HIGH"


@responses.activate
def test_fetch_data_layers_404_surfaces_coverage_note(monkeypatch):
    """A signed-customer build run against a no-coverage rural address
    needs a more actionable error than "HTTP 404"."""
    monkeypatch.setenv(ENV_GOOGLE_SOLAR_KEY, "AIza-fake")
    reset_cache_for_tests()
    responses.get(
        "https://solar.googleapis.com/v1/dataLayers:get",
        json={"error": {"code": 404}}, status=404,
    )
    with pytest.raises(DataLayersError, match="no building"):
        fetch_data_layers(31.0, -100.0)


@responses.activate
def test_fetch_data_layers_5xx_raises_clean_error(monkeypatch):
    monkeypatch.setenv(ENV_GOOGLE_SOLAR_KEY, "AIza-fake")
    reset_cache_for_tests()
    responses.get(
        "https://solar.googleapis.com/v1/dataLayers:get",
        json={"error": "overloaded"}, status=503,
    )
    with pytest.raises(DataLayersError, match="503"):
        fetch_data_layers(33.14, -96.80)


@responses.activate
def test_download_layer_bytes_returns_raw_payload(monkeypatch):
    """The follow-up TIFF fetch returns binary GeoTIFF; the wrapper
    just shuttles bytes through (decoding is the renderer's job)."""
    monkeypatch.setenv(ENV_GOOGLE_SOLAR_KEY, "AIza-fake")
    reset_cache_for_tests()
    # 8 bytes of fake "TIFF" payload (valid PNG header so PIL would
    # also accept it — but we're testing the byte passthrough, not
    # decoding).
    fake_payload = b"\x49\x49\x2A\x00fake-tiff-data"
    responses.get(
        "https://solar.googleapis.com/v1/geoTiff:get",
        body=fake_payload, status=200,
        content_type="image/tiff",
    )
    out = download_layer_bytes(
        "https://solar.googleapis.com/v1/geoTiff:get?id=test"
    )
    assert out == fake_payload


@responses.activate
def test_fetch_google_static_satellite_visual_fallback(monkeypatch):
    from pvess_calc.permit.cover_maps import fetch_google_static_satellite

    monkeypatch.setenv(ENV_GOOGLE_MAPS_KEY, "maps-fake")
    reset_cache_for_tests()
    fake_png = b"\x89PNG\r\n\x1a\nfake-static-map"
    responses.get(
        "https://maps.googleapis.com/maps/api/staticmap",
        body=fake_png,
        status=200,
        content_type="image/png",
    )

    result = fetch_google_static_satellite(
        32.550291,
        -97.093689,
        cache=False,
    )

    assert result.status == "PASS"
    assert result.png_bytes == fake_png
    assert "manual tracing" in result.detail
    request_url = responses.calls[0].request.url
    assert "maptype=satellite" in request_url
    assert "center=32.550291%2C-97.093689" in request_url


@responses.activate
def test_fetch_google_static_satellite_reports_account_block(monkeypatch):
    from pvess_calc.permit.cover_maps import fetch_google_static_satellite

    monkeypatch.setenv(ENV_GOOGLE_MAPS_KEY, "maps-fake")
    reset_cache_for_tests()
    responses.get(
        "https://maps.googleapis.com/maps/api/staticmap",
        body=(
            "Your request cannot be served because satellite and hybrid map "
            "types are not available for your account and region."
        ),
        status=403,
        content_type="text/plain",
    )

    result = fetch_google_static_satellite(
        32.550291,
        -97.093689,
        cache=False,
    )

    assert result.status == "WARN"
    assert result.png_bytes is None
    assert "HTTP 403" in result.detail
    assert "satellite and hybrid map types" in result.detail


# ─── roof_satellite renderer ──────────────────────────────────────────


def _fake_assets() -> object:
    """Build a synthetic SatelliteAssets for renderer tests — bypasses
    the network entirely and exercises only the matplotlib pipeline."""
    from pvess_calc.customer.roof_satellite import SatelliteAssets
    # 64×64 px synthetic site — small enough that the test is fast,
    # large enough that imshow doesn't degenerate.
    rgb = (np.random.default_rng(42).integers(50, 200, size=(64, 64, 3))
           .astype(np.uint8))
    flux = np.linspace(200, 1700, 64 * 64,
                       dtype=np.float32).reshape(64, 64)
    mask = np.zeros((64, 64), dtype=bool)
    mask[16:48, 16:48] = True   # 32x32 "building" in the middle
    return SatelliteAssets(
        rgb=rgb, annual_flux=flux, mask=mask,
        imagery_date="2024-02-06", imagery_quality="HIGH",
    )


def test_render_satellite_diagram_writes_valid_png(tmp_path: Path):
    """Synthetic 64×64 assets + 4 K.3c sections → valid PNG."""
    from pvess_calc.customer.roof_satellite import render_satellite_diagram

    sections = [
        {"name": "South Roof", "pitch_deg": 22, "azimuth_deg": 178,
         "width_ft": 20, "height_ft": 20, "shading_factor": 1.0,
         "shape": "rect", "roof_type": "Comp Shingle"},
        {"name": "West Roof", "pitch_deg": 22, "azimuth_deg": 270,
         "width_ft": 15, "height_ft": 15, "shading_factor": 1.0,
         "shape": "rect", "roof_type": "Comp Shingle"},
        {"name": "North Roof", "pitch_deg": 30, "azimuth_deg": 0,
         "width_ft": 18, "height_ft": 18, "shading_factor": 1.0,
         "shape": "rect", "roof_type": "Comp Shingle"},
        {"name": "East Roof", "pitch_deg": 22, "azimuth_deg": 90,
         "width_ft": 12, "height_ft": 12, "shading_factor": 1.0,
         "shape": "rect", "roof_type": "Comp Shingle"},
    ]
    out = tmp_path / "frisco-sat.png"
    written = render_satellite_diagram(sections, _fake_assets(), out,
                                       title="Test",
                                       subtitle="synthetic")
    assert written == out.absolute()
    assert _is_png(out)
    # 4 panels at 150 dpi @ 15×9 in → ≥ 80 KB realistically
    assert out.stat().st_size > 80_000


def test_render_satellite_diagram_raises_on_empty_sections(tmp_path: Path):
    """Empty roof_sections → fail loud, like roof_diagram."""
    from pvess_calc.customer.roof_satellite import render_satellite_diagram
    with pytest.raises(ValueError, match="empty roof_sections"):
        render_satellite_diagram([], _fake_assets(), tmp_path / "x.png")


def test_render_satellite_includes_target_crosshair():
    """2026-05-16 polish — dense subdivisions show 3-5 houses in a
    50 m × 50 m frame; a red crosshair at image centre tells the viewer
    which house is the actual project. Walks the matplotlib axes and
    asserts crosshair patches exist on both RGB and flux panels."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle

    from pvess_calc.customer.roof_satellite import _draw_rgb, _draw_flux

    assets = _fake_assets()

    # RGB panel
    fig, ax = plt.subplots()
    _draw_rgb(ax, assets)
    circles = [p for p in ax.patches if isinstance(p, Circle)]
    assert len(circles) >= 1, "RGB panel missing target circle"
    plt.close(fig)

    # Flux panel
    fig, ax = plt.subplots()
    _draw_flux(ax, assets)
    circles = [p for p in ax.patches if isinstance(p, Circle)]
    assert len(circles) >= 1, "Flux panel missing target circle"
    plt.close(fig)


def test_satellite_crop_targets_central_roof_mask_component():
    """R8 satellite review should zoom to the target building, not every
    neighboring roof inside the raw Google dataLayers square."""
    from pvess_calc.customer.roof_satellite import (
        SatelliteAssets,
        crop_satellite_assets_to_target,
    )

    rgb = np.zeros((120, 120, 3), dtype=np.uint8)
    flux = np.ones((120, 120), dtype=np.float32) * 1000
    mask = np.zeros((120, 120), dtype=bool)
    mask[5:20, 5:20] = True
    mask[50:70, 50:70] = True
    mask[95:110, 95:110] = True
    assets = SatelliteAssets(
        rgb=rgb,
        annual_flux=flux,
        mask=mask,
        imagery_date="2024-02-06",
        imagery_quality="HIGH",
    )

    cropped = crop_satellite_assets_to_target(assets)

    assert cropped.rgb.shape[0] < assets.rgb.shape[0]
    assert cropped.rgb.shape[1] < assets.rgb.shape[1]
    tx, ty = cropped.target_px or (-1, -1)
    assert 0 <= tx < cropped.rgb.shape[1]
    assert 0 <= ty < cropped.rgb.shape[0]
    assert bool(cropped.mask[int(ty), int(tx)]) is True


def test_target_component_prefers_nearest_roof_over_largest_neighbor():
    from pvess_calc.customer.roof_satellite import target_component_from_mask

    mask = np.zeros((120, 120), dtype=bool)
    mask[5:60, 5:60] = True
    mask[75:92, 75:92] = True

    component = target_component_from_mask(mask, target_px=(82.0, 82.0))

    assert component is not None
    assert component.component_count == 2
    assert component.bbox == (75, 75, 92, 92)
    assert component.area_px == 17 * 17
    assert component.mask[82, 82]
    assert not component.mask[20, 20]


def test_r8_satellite_crop_modes_control_context_width():
    from pvess_calc.customer.roof_satellite import SatelliteAssets
    from pvess_calc.permit.r8_validation import _crop_satellite_assets_for_mode

    rgb = np.zeros((120, 120, 3), dtype=np.uint8)
    flux = np.ones((120, 120), dtype=np.float32) * 1000
    mask = np.zeros((120, 120), dtype=bool)
    mask[50:70, 50:70] = True
    assets = SatelliteAssets(
        rgb=rgb,
        annual_flux=flux,
        mask=mask,
        imagery_date="2024-02-06",
        imagery_quality="HIGH",
    )

    target = _crop_satellite_assets_for_mode(assets, "target")
    tight = _crop_satellite_assets_for_mode(assets, "tight")
    standard = _crop_satellite_assets_for_mode(assets, "standard")
    wide = _crop_satellite_assets_for_mode(assets, "wide")

    assert (
        target.rgb.shape[0]
        < tight.rgb.shape[0]
        < standard.rgb.shape[0]
        < wide.rgb.shape[0]
    )
    assert (
        target.rgb.shape[1]
        < tight.rgb.shape[1]
        < standard.rgb.shape[1]
        < wide.rgb.shape[1]
    )


def test_fetch_data_layers_default_radius_is_tight_for_subdivisions(monkeypatch):
    """2026-05-16 polish — default radius shrank from 50 m to 25 m so
    the target building fills more of the frame in dense subdivisions.
    Locks the value so it can't be silently bumped back without
    deliberation."""
    import inspect
    sig = inspect.signature(fetch_data_layers)
    assert sig.parameters["radius_m"].default == 25.0, (
        "default radius regressed from the 25 m subdivision-friendly value"
    )
    assert sig.parameters["pixel_size_m"].default == 0.25, (
        "default pixel_size regressed from 0.25 m"
    )


def test_decode_tiff_handles_uint8_rgb(tmp_path: Path):
    """Renderer decodes PIL-readable bytes → numpy array. Use a real
    in-memory TIFF created via Pillow to verify the contract."""
    from pvess_calc.customer.roof_satellite import _decode_tiff
    import io
    img = Image.new("RGB", (16, 16), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="TIFF")
    arr = _decode_tiff(buf.getvalue())
    assert arr.shape == (16, 16, 3)
    assert arr.dtype == np.uint8
    # Center pixel matches the colour we wrote.
    assert tuple(arr[8, 8]) == (100, 150, 200)


def test_decode_tiff_handles_single_band_float(tmp_path: Path):
    """Annual flux TIFFs are single-band float32 — PIL returns (H, W)
    array. Renderer treats this shape distinctly from RGB."""
    from pvess_calc.customer.roof_satellite import _decode_tiff
    import io
    # PIL's "F" mode is 32-bit float, single band.
    img = Image.new("F", (16, 16), color=500.0)
    buf = io.BytesIO()
    img.save(buf, format="TIFF")
    arr = _decode_tiff(buf.getvalue())
    assert arr.shape == (16, 16)
    assert arr.dtype == np.float32
    assert arr[8, 8] == pytest.approx(500.0)


# ─── CLI tier gate ─────────────────────────────────────────────────────


def test_cli_satellite_without_confirm_cost_exits_4(monkeypatch):
    """Calling `pvess-roof-vis ... --satellite` without --confirm-cost
    must exit 4 with the pricing warning. Single most important gate
    in the whole feature — protects against accidental $0.50 charges
    when running roof-vis in a batch script."""
    from click.testing import CliRunner
    from pvess_calc.cli import roof_vis_cmd

    monkeypatch.setenv(ENV_GOOGLE_SOLAR_KEY, "AIza-fake")
    reset_cache_for_tests()

    runner = CliRunner()
    result = runner.invoke(
        roof_vis_cmd,
        ["7652 Glasshouse Walk, Frisco TX 75035", "--satellite"],
    )
    assert result.exit_code == 4, result.output
    assert "0.50" in result.output or "$0.50" in result.output
    assert "--confirm-cost" in result.output


def test_cli_satellite_with_env_allow_skips_gate(monkeypatch):
    """`PVESS_ALLOW_PAID_RENDERS=1` is the session-level override for
    sales reps who've already acknowledged the cost. The gate doesn't
    fire — but lookup still might (we mock it to early-exit before
    a real HTTP call)."""
    from click.testing import CliRunner
    from pvess_calc.cli import roof_vis_cmd

    monkeypatch.setenv(ENV_GOOGLE_SOLAR_KEY, "AIza-fake")
    monkeypatch.setenv("PVESS_ALLOW_PAID_RENDERS", "1")
    reset_cache_for_tests()

    # Short-circuit the actual lookup so we don't hit the network.
    # The renderer returns None → CLI exits 3 ("no roof_sections"),
    # NOT 4 (gate) — proving the gate was bypassed.
    monkeypatch.setattr(
        "pvess_calc.customer.roof_satellite.render_from_address",
        lambda *_a, **_k: None,
    )

    runner = CliRunner()
    result = runner.invoke(
        roof_vis_cmd,
        ["test address", "--satellite"],
    )
    assert result.exit_code == 3, result.output   # past the gate
    assert "no roof_sections" in result.output or "Solar" in result.output
