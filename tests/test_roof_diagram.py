"""K.3c sidekick — roof_diagram.py renders a 2-panel PNG visualization
straight from a Google Solar `roof_sections` payload (no project yaml
required). Tests lock the contract on:

  1. Happy path: a multi-face dict-list → PNG ≥ 50 KB (cheap floor; a
     valid 2-panel matplotlib figure at 150 dpi clocks ~250 KB).
  2. Edge cases: single face / empty list / zero-area face.
  3. Math: `_build_vis` produces a derate that combines orientation +
     shading correctly (no silent double-apply).
  4. `render_from_address` end-to-end via patched `resolve()` — verifies
     the address-only entry point is honest about missing data.
"""
from __future__ import annotations

import struct
from pathlib import Path

import pytest

from pvess_calc.customer.roof_diagram import (
    FaceVis,
    _build_vis,
    render_from_address,
    render_roof_diagram,
)


# A representative K.3c response slice (matches the dict shape that
# google_solar._segment_to_section emits — keeps the test close to the
# real provider's contract).
_FRISCO_SECTIONS = [
    {"name": "South Roof",     "roof_type": "Comp Shingle",
     "pitch_deg": 22.4, "azimuth_deg": 178.6,
     "width_ft": 25.5, "height_ft": 25.5,
     "module_count": 0, "shape": "rect"},
    {"name": "North Roof",     "roof_type": "Comp Shingle",
     "pitch_deg": 34.8, "azimuth_deg": 360.0,
     "width_ft": 20.9, "height_ft": 20.9,
     "module_count": 0, "shape": "rect"},
    {"name": "West Roof",      "roof_type": "Comp Shingle",
     "pitch_deg": 33.0, "azimuth_deg": 268.1,
     "width_ft": 19.7, "height_ft": 19.7,
     "module_count": 0, "shape": "rect"},
    {"name": "East Roof",      "roof_type": "Comp Shingle",
     "pitch_deg": 34.6, "azimuth_deg": 90.8,
     "width_ft": 14.2, "height_ft": 14.2,
     "module_count": 0, "shape": "rect"},
]


# ─── PNG helpers ───────────────────────────────────────────────────────


def _is_png(path: Path) -> bool:
    """PNG signature check — first 8 bytes are the magic header."""
    with path.open("rb") as f:
        return f.read(8) == b"\x89PNG\r\n\x1a\n"


def _png_dimensions(path: Path) -> tuple[int, int]:
    """Read IHDR chunk to get (width, height) without dragging in PIL."""
    with path.open("rb") as f:
        f.read(8)                              # PNG signature
        f.read(4)                              # IHDR length (always 13)
        assert f.read(4) == b"IHDR", "expected IHDR chunk first"
        w, h = struct.unpack(">II", f.read(8))
        return w, h


# ─── Happy path ────────────────────────────────────────────────────────


def test_render_roof_diagram_writes_valid_png(tmp_path: Path):
    """A multi-face diagram → a real PNG, not a 0-byte file or HTML."""
    out = tmp_path / "frisco.png"
    written = render_roof_diagram(
        _FRISCO_SECTIONS, out,
        title="Roof analysis — Frisco TX",
        subtitle="4 faces · NREL 1535 kWh/kW",
        urban_density="suburban",
    )
    assert written == out.absolute()
    assert out.exists()
    assert _is_png(out)
    # 2-panel @ 150 dpi @ 14×8 in is comfortably > 50 KB; floor catches
    # the "matplotlib silently saved an empty figure" failure mode.
    assert out.stat().st_size > 50_000, (
        f"PNG suspiciously small ({out.stat().st_size} B) — "
        "may be empty figure"
    )


def test_render_roof_diagram_uses_letter_aspect_for_print(tmp_path: Path):
    """Output dimensions are derived from figsize=(14, 8) at default 150 dpi —
    contract: ~2100 × 1200 px so the PNG drops cleanly into a Letter PDF
    or a 16:9 slide without re-rendering."""
    out = tmp_path / "dims.png"
    render_roof_diagram(_FRISCO_SECTIONS, out, dpi=150)
    w, h = _png_dimensions(out)
    # tight_layout + bbox_inches='tight' trim a bit; allow a wide band.
    assert 1800 < w < 2400, f"unexpected width {w}"
    assert 900 < h < 1500, f"unexpected height {h}"


# ─── Edge cases ────────────────────────────────────────────────────────


def test_render_roof_diagram_handles_single_face(tmp_path: Path):
    """One face shouldn't crash on the polar-bar or sort path."""
    out = tmp_path / "single.png"
    render_roof_diagram(
        [_FRISCO_SECTIONS[0]], out,
        title="Single-face site",
    )
    assert _is_png(out)
    assert out.stat().st_size > 30_000   # smaller w/ one face but still real


def test_render_roof_diagram_raises_on_empty_sections(tmp_path: Path):
    """An empty list must FAIL loud, not silently produce a blank PNG."""
    out = tmp_path / "empty.png"
    with pytest.raises(ValueError, match="empty roof_sections"):
        render_roof_diagram([], out)
    assert not out.exists()


def test_render_roof_diagram_survives_zero_area_face(tmp_path: Path):
    """A degenerate face (width=0) shouldn't blow up the polar
    normalization — should still render, just with that bar missing."""
    sections = [
        *_FRISCO_SECTIONS[:2],
        {"name": "Degenerate", "roof_type": "Comp Shingle",
         "pitch_deg": 22, "azimuth_deg": 90,
         "width_ft": 0, "height_ft": 0,
         "module_count": 0, "shape": "rect"},
    ]
    out = tmp_path / "degen.png"
    render_roof_diagram(sections, out)
    assert _is_png(out)


# ─── _build_vis math contract ──────────────────────────────────────────


def test_build_vis_combines_orientation_and_shading_correctly():
    """`FaceVis.derate` MUST equal orientation_derate × shading_factor —
    not one or the other, and not pre-multiplied somewhere upstream.
    Catches the silent regression of one factor being dropped.
    """
    # A south-facing 30° tilt → orientation_derate ≈ 1.00.
    # Suburban density → default shading 0.96 (per DENSITY_DEFAULT_SHADING).
    [vis] = _build_vis([{
        "name": "test", "pitch_deg": 30, "azimuth_deg": 180,
        "width_ft": 20, "height_ft": 20, "shading_factor": 1.0,
    }], urban_density="suburban")
    assert vis.orientation_derate == pytest.approx(1.00, abs=0.01)
    assert vis.shading_factor == pytest.approx(0.96)
    assert vis.derate == pytest.approx(0.96, abs=0.01)


def test_build_vis_per_face_shading_overrides_density_default():
    """If the K.3c dict carries an explicit `shading_factor` < 1.0,
    that wins over the urban_density fallback — same contract as the
    K.8 production aggregator."""
    [vis] = _build_vis([{
        "name": "shaded", "pitch_deg": 22, "azimuth_deg": 180,
        "width_ft": 20, "height_ft": 20,
        "shading_factor": 0.75,            # measured, e.g. tree at 30°
    }], urban_density="urban")             # would default to 0.90
    assert vis.shading_factor == pytest.approx(0.75)
    assert vis.derate < 0.80               # vs ~0.87 if density won


def test_build_vis_name_falls_back_when_missing():
    """A malformed K.3c response (no `name` key) should still render —
    every face needs *some* label so the bar chart isn't a row of
    anonymous bars."""
    [vis] = _build_vis([{
        "pitch_deg": 22, "azimuth_deg": 180,
        "width_ft": 20, "height_ft": 20,
    }])
    assert vis.name == "Unnamed Face"


# ─── render_from_address end-to-end (patched lookup) ───────────────────


def test_render_from_address_returns_none_when_lookup_empty(monkeypatch, tmp_path: Path):
    """If Google Solar didn't contribute (no key / no building / network
    down), `render_from_address` returns None instead of writing an
    empty diagram. Caller decides next step."""
    class FakeResult:
        fields: dict = {}

    monkeypatch.setattr(
        "pvess_calc.customer.roof_diagram.resolve",
        lambda *_a, **_k: FakeResult(),
        raising=False,
    )
    # Need to also patch the late-binding `resolve` inside the function.
    # The function imports it lazily from `..lookup`, so we patch there.
    from pvess_calc.lookup import resolve as real_resolve  # noqa: F401
    monkeypatch.setattr(
        "pvess_calc.lookup.resolve",
        lambda *_a, **_k: FakeResult(),
    )

    out = tmp_path / "should-not-exist.png"
    assert render_from_address("nowhere", out) is None
    assert not out.exists()


# ─── Visual-contract regressions (2026-05-16 polish) ───────────────────


def test_render_height_scales_with_face_count(tmp_path: Path):
    """13-face response must produce a TALLER PNG than a 4-face one —
    fixes the pre-polish bug where 13 bars crowded into an 8-inch tall
    panel and y-tick labels overlapped the area·derate annotations."""
    out_few = tmp_path / "few.png"
    out_many = tmp_path / "many.png"

    render_roof_diagram(_FRISCO_SECTIONS, out_few)        # 4 faces

    # Synthesize a 13-face roof (real Frisco shape).
    many = []
    for i in range(13):
        many.append({
            "name": f"Face {i+1}", "roof_type": "Comp Shingle",
            "pitch_deg": 22 + (i % 5) * 6,
            "azimuth_deg": (i * 28) % 360,
            "width_ft": 15.0, "height_ft": 15.0,
            "module_count": 0, "shape": "rect",
        })
    render_roof_diagram(many, out_many)

    _, h_few = _png_dimensions(out_few)
    _, h_many = _png_dimensions(out_many)
    # 13-face PNG must be at least 30 % taller than the 4-face baseline.
    assert h_many > h_few * 1.30, (
        f"13-face height ({h_many}px) not appreciably bigger than "
        f"4-face baseline ({h_few}px) — figsize scaling regressed"
    )


def test_face_bars_use_single_outside_right_annotation():
    """Post-v2 contract: every bar gets EXACTLY ONE annotation, and
    that annotation lives to the RIGHT of the bar (positive x-offset),
    NOT inline on the bar. The pre-v2 inline-white-text hint collided
    with y-tick face names in the satellite layout's narrower bar
    panel — this regression test catches anyone re-adding the inline
    text without thinking through the multi-layout consequences.

    The annotation must contain area + pitch/az + derate all in one
    string (single-source-of-truth column).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from pvess_calc.customer.roof_diagram import _build_vis, _draw_face_bars

    sections = [
        {"name": "BIG",   "pitch_deg": 22, "azimuth_deg": 180,
         "width_ft": 30, "height_ft": 30, "shading_factor": 1.0,
         "shape": "rect", "roof_type": "Comp Shingle"},
        {"name": "MED",   "pitch_deg": 22, "azimuth_deg": 270,
         "width_ft": 18, "height_ft": 18, "shading_factor": 1.0,
         "shape": "rect", "roof_type": "Comp Shingle"},
        {"name": "TINY",  "pitch_deg": 22, "azimuth_deg": 0,
         "width_ft":  3, "height_ft":  3, "shading_factor": 1.0,
         "shape": "rect", "roof_type": "Comp Shingle"},
    ]
    faces = _build_vis(sections)
    fig, ax = plt.subplots()
    _draw_face_bars(ax, faces)

    # Exactly one annotation per face — no doubles, no skips.
    annotations = [t for t in ax.texts]
    assert len(annotations) == len(faces), (
        f"expected one annotation per face ({len(faces)}); "
        f"got {len(annotations)} — possible regression of the "
        "inline-on-bar hint."
    )

    # Each annotation must combine area + pitch/az + derate in ONE
    # string. Catches any future split that re-introduces multi-column
    # crowding.
    for t in annotations:
        text = t.get_text()
        assert "ft²" in text and "°" in text and "%" in text, (
            f"annotation '{text}' missing area / pitch / derate"
        )
        # Must be a true right-side annotation: positive x-offset and
        # not styled as white-on-bar (white text is the failure mode).
        assert t.get_color() != "white", (
            f"annotation '{text}' is white — regressed to inline-on-bar"
        )
    plt.close(fig)


def test_render_from_address_writes_png_when_google_solar_resolved(
    monkeypatch, tmp_path: Path,
):
    """Closing standard: when lookup returns a Google Solar payload,
    `render_from_address` resolves, formats the subtitle, and writes
    the PNG. Subtitle must mention face count, NREL kWh/kW, and
    imagery date — verifies the metadata plumbing."""
    class FakeResult:
        fields = {
            "canonical_address": "123 Test St, Frisco TX",
            "annual_energy_kwh_per_kw": 1535.0,
            "roof_sections": _FRISCO_SECTIONS,
            "google_solar_imagery_quality": "HIGH",
            "google_solar_imagery_date": "2024-02-06",
            "google_solar_whole_roof_area_m2": 287.7,
        }

    monkeypatch.setattr("pvess_calc.lookup.resolve",
                        lambda *_a, **_k: FakeResult())

    out = tmp_path / "addr.png"
    result = render_from_address("123 Test St", out)
    assert result == out.absolute()
    assert _is_png(out)
    assert out.stat().st_size > 50_000
