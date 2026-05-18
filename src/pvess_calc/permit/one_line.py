"""Compatibility wrapper for the EE-2.1 one-line sheet.

The production EE-2.1 renderer is DXF-based (`pvess_calc.dxf.one_line`).
This module is kept only so older imports do not silently emit the retired
ReportLab flow-chart page.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from ..calc.engine import CalculationResult
from ..dxf.one_line import render_one_line_dxf
from .builder import _dxf_to_pdf


def render_one_line_diagram(result: CalculationResult, out_path: Path) -> None:
    """Render the current DXF one-line sheet to PDF for legacy callers."""
    with TemporaryDirectory() as tmp:
        dxf_path = Path(tmp) / f"{out_path.stem}.dxf"
        render_one_line_dxf(result, dxf_path)
        _dxf_to_pdf(dxf_path, out_path)
