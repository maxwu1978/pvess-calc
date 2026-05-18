"""Stage 6/7 — optional satellite underlay + mask contour on EE-4.

The underlay is deliberately opt-in because Google Solar dataLayers is
paid. These tests lock the billing gate and the render-visible marker.
"""
from __future__ import annotations

import io
from pathlib import Path

import pypdf
import numpy as np
from PIL import Image

from pvess_calc.calc.engine import run
from pvess_calc.permit.site_plan import render_site_plan
from pvess_calc.schema import Inputs


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRISCO = PROJECT_ROOT / "projects" / "003-frisco-glasshouse" / "inputs.yaml"


def _ee4_text(tmp_path: Path, inputs: Inputs) -> str:
    out = tmp_path / "ee4.pdf"
    render_site_plan(run(inputs), out)
    return "\n".join(p.extract_text() or ""
                     for p in pypdf.PdfReader(str(out)).pages)


def _tiny_png() -> bytes:
    img = Image.new("RGB", (24, 24), (120, 150, 130))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _fake_assets():
    from pvess_calc.customer.roof_satellite import SatelliteAssets

    rgb = np.zeros((48, 48, 3), dtype=np.uint8)
    rgb[:, :, 0] = 120
    rgb[:, :, 1] = 150
    rgb[:, :, 2] = 130
    flux = np.ones((48, 48), dtype=np.float32) * 1000
    mask = np.zeros((48, 48), dtype=bool)
    mask[12:36, 14:34] = True
    return SatelliteAssets(
        rgb=rgb,
        annual_flux=flux,
        mask=mask,
        imagery_date="2024-02-06",
        imagery_quality="HIGH",
    )


def test_satellite_underlay_is_opt_in(monkeypatch, tmp_path: Path):
    """Default EE-4 render must not even try to fetch the paid aerial."""
    from pvess_calc.permit import cover_maps

    def _fail(*args, **kwargs):
        raise AssertionError("satellite fetch should be gated off")

    monkeypatch.delenv("PVESS_EE4_SATELLITE", raising=False)
    monkeypatch.delenv("PVESS_ALLOW_PAID_RENDERS", raising=False)
    monkeypatch.setattr(cover_maps, "fetch_aerial_map_png", _fail)
    monkeypatch.setattr(cover_maps, "fetch_satellite_assets_cached", _fail)

    text = _ee4_text(tmp_path, Inputs.from_yaml(FRISCO))
    assert "SATELLITE UNDERLAY" not in text


def test_satellite_underlay_cache_only_without_paid_gate(
    monkeypatch, tmp_path: Path,
):
    """Satellite opt-in without paid confirmation may read cache but
    must pass allow_network=False to the aerial fetcher."""
    from pvess_calc.permit import cover_maps

    calls: list[tuple[str, bool]] = []

    def _fake_assets_fetch(*args, **kwargs):
        calls.append(("assets", kwargs["allow_network"]))
        return None

    def _fake_png_fetch(*args, **kwargs):
        calls.append(("png", kwargs["allow_network"]))
        return None

    monkeypatch.setenv("PVESS_EE4_SATELLITE", "1")
    monkeypatch.delenv("PVESS_ALLOW_PAID_RENDERS", raising=False)
    monkeypatch.setattr(
        cover_maps, "fetch_satellite_assets_cached", _fake_assets_fetch,
    )
    monkeypatch.setattr(cover_maps, "fetch_aerial_map_png", _fake_png_fetch)

    text = _ee4_text(tmp_path, Inputs.from_yaml(FRISCO))
    assert calls == [("assets", False), ("png", False)]
    assert "SATELLITE UNDERLAY" not in text


def test_satellite_underlay_draws_mask_contour_when_assets_available(
    monkeypatch, tmp_path: Path,
):
    """When both gates are open and assets are returned, the EE-4 sheet
    includes the satellite underlay and Stage 7 mask contour labels."""
    from pvess_calc.permit import cover_maps

    calls: list[bool] = []

    def _fake_assets_fetch(*args, **kwargs):
        calls.append(kwargs["allow_network"])
        return _fake_assets()

    def _fail_png(*args, **kwargs):
        raise AssertionError("assets path should not need PNG fallback")

    monkeypatch.setenv("PVESS_EE4_SATELLITE", "1")
    monkeypatch.setenv("PVESS_ALLOW_PAID_RENDERS", "1")
    monkeypatch.setattr(
        cover_maps, "fetch_satellite_assets_cached", _fake_assets_fetch,
    )
    monkeypatch.setattr(cover_maps, "fetch_aerial_map_png", _fail_png)

    text = _ee4_text(tmp_path, Inputs.from_yaml(FRISCO))
    assert calls == [True]
    assert "SATELLITE UNDERLAY" in text
    assert "MASK CONTOUR CANDIDATE" in text
    assert "FIT HOUSE BBOX" in text
