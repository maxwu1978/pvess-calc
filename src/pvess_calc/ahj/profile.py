"""AHJ profile schema + loader.

Each AHJ has its own submittal expectations: which sheets are required, which
NEC labels must be present, what local-form blanks to include. Profiles live
in `ahj/profiles/*.yaml` and load via `get_ahj_profile(name)`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, Field


SheetCode = str


class SpdPolicy(BaseModel):
    """AHJ-specific surge-protection requirements.

    Profiles may only make the base NEC result stricter. A profile cannot
    relax NEC 230.67 when the selected NEC edition already requires service
    SPD protection.
    """

    service_spd_required: bool | None = None
    dc_spd_required: bool = False
    ess_spd_required: bool = False
    spd_type: Literal["Type 1", "Type 2", "Type 3"] | None = None
    required_locations: list[str] = Field(default_factory=list)
    recommended_locations: list[str] = Field(default_factory=list)
    note: str = ""


class AhjProfile(BaseModel):
    name: str
    region: str = ""
    required_sheets: list[SheetCode] = Field(
        default_factory=lambda: [
            "cover", "ee-1", "ee-2", "ee-3", "ee-4", "ee-4a", "ee-5",
            "pv-4", "pv-5", "pv-6", "notes", "labels",
        ]
    )
    label_set: list[str] = Field(default_factory=list)   # NEC clauses to include
    inspector_checklist: list[str] = Field(default_factory=list)
    form_blanks: list[str] = Field(default_factory=list)
    spd_policy: SpdPolicy | None = None
    notes: str = ""


PROFILES_DIR = Path(__file__).parent / "profiles"


def list_ahj_profiles() -> list[str]:
    """Return all available AHJ profile names (yaml filenames sans extension)."""
    if not PROFILES_DIR.exists():
        return []
    return sorted(p.stem for p in PROFILES_DIR.glob("*.yaml"))


def get_ahj_profile(name: str) -> AhjProfile:
    """Load an AHJ profile by name. Raises if not found."""
    path = PROFILES_DIR / f"{name}.yaml"
    if not path.exists():
        raise KeyError(
            f"Unknown AHJ profile {name!r}. "
            f"Available: {list_ahj_profiles()}"
        )
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return AhjProfile.model_validate(data)
