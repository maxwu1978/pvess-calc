"""Provider contract.

Each provider is just a function `(ParsedAddress) -> ProviderResult`.
We use a Protocol instead of a base class so static dataset providers
can be plain functions (no class boilerplate).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..address import ParsedAddress


@dataclass
class ProviderResult:
    """One provider's contribution. The orchestrator merges these
    across all providers (declared order = priority order)."""
    source: str                                 # "ashrae-offline", "mapbox", ...
    fields: dict[str, Any] = field(default_factory=dict)
    confidence: str = "low"                     # "high" | "medium" | "low" | "miss"
    note: str = ""

    @property
    def hit(self) -> bool:
        return self.confidence != "miss" and bool(self.fields)


class Provider(Protocol):
    """A provider is callable. Implementations may be functions OR
    instances with `__call__`."""

    def __call__(self, address: ParsedAddress) -> ProviderResult: ...


# ─── Helpers shared by static (JSON-backed) providers ───────────────────────

_DATA_DIR = Path(__file__).parent.parent / "data"


def load_dataset(filename: str) -> dict[str, Any]:
    """Load one of `lookup/data/*.json`, stripping the README key."""
    path = _DATA_DIR / filename
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}
