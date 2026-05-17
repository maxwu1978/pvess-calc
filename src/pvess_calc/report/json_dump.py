"""Serialize CalculationResult to calculation.json."""
from __future__ import annotations

import json
from pathlib import Path

from ..calc.engine import CalculationResult


def write_json(result: CalculationResult, path: Path) -> None:
    path.write_text(
        json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
