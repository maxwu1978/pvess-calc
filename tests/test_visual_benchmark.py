"""R9.0 — visual benchmark artifact generation."""
from __future__ import annotations

import shutil
from pathlib import Path

from click.testing import CliRunner
from PIL import Image, ImageDraw

from pvess_calc.cli_root import pvess
from pvess_calc.permit.visual_benchmark import run_visual_benchmark


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRISCO_MERGED = (
    PROJECT_ROOT
    / "projects"
    / "003-frisco-glasshouse-roof-merged"
    / "inputs.yaml"
)


def test_visual_benchmark_generates_metrics_and_comparison(tmp_path: Path):
    project_dir = _copy_project(tmp_path)
    target = _target_png(tmp_path)

    result = run_visual_benchmark(project_dir, target, sheet="PV-2")
    out_dir = result["paths"].output_dir

    assert (out_dir / "target-crop.png").exists()
    assert (out_dir / "current-pv2-crop.png").exists()
    assert (out_dir / "overlay-diff-pv2.png").exists()
    assert result["paths"].metrics_json.exists()
    assert result["paths"].comparison_md.exists()
    assert result["metrics"]["overall_score"] > 0
    assert "roof_facet_clarity_score" in result["metrics"]
    assert "Visual Benchmark Comparison" in (
        result["paths"].comparison_md.read_text()
    )


def test_visual_benchmark_cli_writes_expected_outputs(tmp_path: Path):
    project_dir = _copy_project(tmp_path)
    target = _target_png(tmp_path)

    result = CliRunner().invoke(
        pvess,
        [
            "visual-benchmark",
            str(project_dir),
            "--target",
            str(target),
            "--sheet",
            "PV-2",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "overall_score=" in result.output
    assert (project_dir / "output" / "visual-benchmark" / "metrics.json").exists()
    assert (
        project_dir
        / "output"
        / "roof-review"
        / "panel-placement-qa.md"
    ).exists()


def _copy_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "frisco-merged"
    project_dir.mkdir()
    shutil.copyfile(FRISCO_MERGED, project_dir / "inputs.yaml")
    return project_dir


def _target_png(tmp_path: Path) -> Path:
    path = tmp_path / "reference-roof-plan.png"
    img = Image.new("RGB", (900, 520), "white")
    d = ImageDraw.Draw(img)
    d.polygon([(50, 80), (820, 80), (860, 430), (100, 430)],
              outline="black", fill=None, width=3)
    d.line([(180, 80), (260, 220), (180, 430)], fill="black", width=2)
    for col in range(9):
        for row in range(3):
            x = 390 + col * 45
            y = 250 + row * 48
            d.rectangle((x, y, x + 40, y + 44), outline="blue", width=2)
    d.rectangle((350, 150, 800, 178), outline=(245, 130, 35), width=2)
    img.save(path)
    return path
