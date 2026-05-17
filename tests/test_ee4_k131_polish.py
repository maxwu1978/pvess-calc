"""K.13.1 — EE-4 visual-collision polish.

Locks the 4 layout fixes that close the post-K.13 visual review:

  P0 — Optimizer leader endpoint moved from outside-lot-right
        (overlapping SITE INFORMATION) to inside-lot top-right
  P1 — PV ARRAY caption moved from bottom margin (overlapping
        leader callout column when stacked_below) to top banner
  P2 — auto_anchor_sections inset cursor starts by perpendicular
        orientation's max height (avoid corner double-claim)
  P3 — PROPERTY LINE label moved from bottom-right to top-left
        outside the lot (away from leader column + setback dims)
"""
from __future__ import annotations

import re
from pathlib import Path

import pypdf

from pvess_calc.calc.engine import run
from pvess_calc.calc.site_layout import auto_anchor_sections
from pvess_calc.permit.site_plan import render_site_plan
from pvess_calc.schema import Inputs, RoofSection, Site


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUSTIN = PROJECT_ROOT / "projects" / "001-demo-austin" / "inputs.yaml"
PHOENIX = PROJECT_ROOT / "projects" / "002-phoenix-25kw" / "inputs.yaml"
FRISCO = PROJECT_ROOT / "projects" / "003-frisco-glasshouse" / "inputs.yaml"


def _ee4_text(tmp_path: Path, inputs: Inputs, *, suffix: str = "ee4") -> str:
    out = tmp_path / f"{suffix}.pdf"
    render_site_plan(run(inputs), out)
    return "\n".join(p.extract_text() or ""
                     for p in pypdf.PdfReader(str(out)).pages)


SRC = (PROJECT_ROOT / "src" / "pvess_calc" / "permit"
       / "site_plan.py").read_text()


# ─── P0: optimizer leader endpoint moved inside lot ─────────────────────


def test_p0_optimizer_endpoint_inside_lot():
    """The optimizer leader endpoint must be inside the lot
    (lot_x + lot_w_pt - margin), NOT outside-right where SITE
    INFORMATION column starts."""
    assert "end_x = lot_x + lot_w_pt - 1.70 * inch" in SRC
    # The legacy outside-right placement must be gone
    assert "end_x = lot_x + lot_w_pt + 0.20 * inch" not in SRC


def test_p0_optimizer_text_renders_for_frisco(tmp_path: Path):
    """Frisco has Tigo optimizers configured — the callout text
    must appear in the rendered EE-4 PDF."""
    text = _ee4_text(tmp_path, Inputs.from_yaml(FRISCO), suffix="fri-opt")
    assert "PV MODULE EQUIPPED W/" in text
    assert "OPTIMIZER" in text


# ─── P1: PV ARRAY caption moved to top banner ───────────────────────────


def test_p1_caption_in_top_banner():
    """Caption placement now uses `caption_y = lot_y + lot_h_pt + 0.22`
    (banner above the lot), no longer `lot_y - 0.48 * inch` (bottom)."""
    assert "caption_y = lot_y + lot_h_pt + 0.22 * inch" in SRC
    assert "caption_y = lot_y - 0.48 * inch" not in SRC


def test_p1_caption_text_still_present(tmp_path: Path):
    """The caption text itself is unchanged."""
    text = _ee4_text(tmp_path, Inputs.from_yaml(PHOENIX), suffix="phx-cap")
    assert "PV ARRAY" in text
    assert "60 MODULES" in text
    assert "25.20" in text


def test_p1_conduit_legend_right_anchored(tmp_path: Path):
    """When routed, conduit legend chip sits on the RIGHT of the
    same banner (caption on left + legend on right, no overlap)."""
    text = _ee4_text(tmp_path, Inputs.from_yaml(FRISCO), suffix="fri-leg")
    # Both pieces of the banner present
    assert "PV ARRAY" in text
    assert "conduit" in text.lower()
    # Source-string check on the right-anchoring math
    assert "row_left = legend_right - total_w" in SRC


# ─── P2: auto-anchor corner inset ───────────────────────────────────────


def test_p2_inset_eliminates_overlap_phoenix():
    """Phoenix has 2 large faces (South 38×24 + West 38×24) on a
    50×35 ft house. Pre-K.13.1 they geometrically overlapped at the
    SW corner. Post-K.13.1 inset, South cursor starts at x_min + 24
    so the SW corner is reserved for West's eastward extent."""
    site = Inputs.from_yaml(PHOENIX).site
    anchors = auto_anchor_sections(site)
    south_x, south_y, _ = anchors["South Roof"]
    west_x, west_y, _ = anchors["West Roof"]
    # West anchor stays at SW corner (15, 77.5)
    assert (west_x, west_y) == (15.0, 77.5)
    # South anchor is INSET east by West's height (24)
    assert south_x == 15.0 + 24.0   # = 39.0


def test_p2_no_inset_when_single_orientation():
    """A yaml with only south faces (no west/north/east faces)
    must NOT inset (max_h["west"] = 0 → cursor stays at x_min)."""
    site = Site(
        lot_width_ft=80, lot_depth_ft=120,
        house_width_ft=50, house_depth_ft=35,
        roof_sections=[
            RoofSection(name="S1", azimuth_deg=180, width_ft=24, height_ft=16),
            RoofSection(name="S2", azimuth_deg=180, width_ft=15, height_ft=10),
        ],
    )
    anchors = auto_anchor_sections(site)
    # Cursor starts at x_min = 15 because no west/east sections
    assert anchors["S1"][0] == 15.0


def test_p2_inset_falls_back_when_over_half_wall():
    """When the perpendicular orientation's max H exceeds 50% of the
    wall length, fall back to flush placement — the data is too
    over-packed for the inset to help; overlap is the right signal."""
    # House 20×20 ft, west face with H=15 (75% of house_w). Inset
    # would push south past the east edge — fall back to no inset.
    site = Site(
        lot_width_ft=80, lot_depth_ft=120,
        house_width_ft=20, house_depth_ft=20,
        roof_sections=[
            RoofSection(name="S", azimuth_deg=180, width_ft=15, height_ft=10),
            RoofSection(name="W", azimuth_deg=270, width_ft=15, height_ft=15),
        ],
    )
    anchors = auto_anchor_sections(site)
    # Both cursors start at corners (15, 15) and (15, 45) — no inset
    house_x_min, _, _, _ = (30.0, 50.0, 50.0, 70.0)  # (80-20)/2
    assert anchors["S"][0] == 30.0   # flush
    assert anchors["W"][1] == 70.0   # flush


def test_p2_engine_run_phoenix_no_overlap_in_canvas(tmp_path: Path):
    """End-to-end: Phoenix's South and West faces no longer share
    canvas-space footprint after Stage K.13.1."""
    inputs = Inputs.from_yaml(PHOENIX)
    result = run(inputs)
    # The result.inputs.site has the patched anchors
    sec_south = next(s for s in result.inputs.site.roof_sections
                     if "South" in s.name)
    sec_west = next(s for s in result.inputs.site.roof_sections
                    if "West" in s.name)
    # South starts inset to 39 (not 15); West stays at 15
    assert sec_south.site_anchor_x_ft == 39.0
    assert sec_west.site_anchor_x_ft == 15.0


# ─── P3: PROPERTY LINE label position ───────────────────────────────────


def test_p3_property_line_label_moved_to_top():
    """PROPERTY LINE label now sits at the top-left of the lot
    (lot_y + lot_h_pt + 0.06"), no longer at the bottom-right
    where it competed with the leader callout column."""
    assert 'lot_y + lot_h_pt + 0.06 * inch' in SRC
    # The legacy bottom-right placement is gone
    assert 'lot_y - 0.14 * inch, pl_text' not in SRC


def test_p3_property_line_still_rendered(tmp_path: Path):
    """The label text itself is unchanged — only position moved."""
    text = _ee4_text(tmp_path, Inputs.from_yaml(FRISCO), suffix="fri-pl")
    assert "PROPERTY LINE" in text


# ─── End-to-end smoke ────────────────────────────────────────────────────


def test_all_three_projects_render_clean(tmp_path: Path):
    """K.13.1 must not crash any of the 3 sample projects."""
    for yaml_path in (AUSTIN, PHOENIX, FRISCO):
        out = tmp_path / f"ee4-{yaml_path.parent.name}.pdf"
        render_site_plan(run(Inputs.from_yaml(yaml_path)), out)
        assert out.stat().st_size > 2_000


def test_doctor_still_passes_after_k131_polish():
    """The K.13 doctor check `ee4_focuses_on_site_geometry` must
    still PASS for all 3 sample projects after the visual polish."""
    from pvess_calc.doctor import _check_ee4_focuses_on_site_geometry
    for yaml_path in (AUSTIN, PHOENIX, FRISCO):
        result = run(Inputs.from_yaml(yaml_path))
        checks = _check_ee4_focuses_on_site_geometry(result)
        assert all(r.ok for r in checks), (
            f"doctor failed for {yaml_path.parent.name}: "
            f"{[r.detail for r in checks]}"
        )
