"""Stage 9.3 — fast EE-4 review artifacts.

This module keeps the manual trace loop short: render just EE-4 as a
single-page PDF and optionally rasterize page 1 to PNG for quick visual
inspection, without rebuilding the full permit package.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from ..calc.engine import CalculationResult
from .site_plan import render_site_plan


@dataclass(frozen=True)
class EE4ReviewArtifacts:
    pdf_path: Path
    png_path: Path | None = None


def render_ee4_review(
    result: CalculationResult,
    pdf_path: Path,
    *,
    png_path: Path | None = None,
    dpi: int = 180,
) -> EE4ReviewArtifacts:
    """Render EE-4 PDF and optionally a PNG preview."""
    pdf_path = Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    render_site_plan(result, pdf_path)

    written_png: Path | None = None
    if png_path is not None:
        written_png = rasterize_pdf_page(pdf_path, Path(png_path), dpi=dpi)

    return EE4ReviewArtifacts(pdf_path=pdf_path, png_path=written_png)


def rasterize_pdf_page(pdf_path: Path, png_path: Path, *, dpi: int = 180) -> Path:
    """Rasterize page 1 of a PDF to PNG using Poppler's `pdftoppm`."""
    if dpi <= 0:
        raise ValueError("dpi must be positive")

    pdf_path = Path(pdf_path)
    png_path = Path(png_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory() as td:
        prefix = Path(td) / "ee4-preview"
        try:
            subprocess.run(
                [
                    "pdftoppm",
                    "-png",
                    "-singlefile",
                    "-r",
                    str(dpi),
                    str(pdf_path),
                    str(prefix),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "pdftoppm not found; install Poppler or rerun with --no-png"
            ) from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            raise RuntimeError(f"pdftoppm failed: {detail}") from exc

        generated = prefix.with_suffix(".png")
        if not generated.exists():
            raise RuntimeError("pdftoppm completed but did not create a PNG")
        shutil.move(str(generated), str(png_path))

    return png_path
