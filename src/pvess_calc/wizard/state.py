"""Wizard state — persisted to JSON so the user can ctrl-C mid-prompt
and resume later with `pvess-init --resume <id>`.

Stored at `projects/<id>/.wizard-state.json`. Just a flat
`{yaml_path: value}` map plus the index of the next un-asked field.
Removed automatically once the wizard completes successfully.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class WizardState:
    answers: dict[str, Any] = field(default_factory=dict)
    next_index: int = 0     # index into WIZARD_FIELDS for the next prompt

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, default=str))

    @classmethod
    def load(cls, path: Path) -> "WizardState":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        return cls(
            answers=data.get("answers", {}),
            next_index=data.get("next_index", 0),
        )

    @staticmethod
    def file_for(project_id: str) -> Path:
        return Path("projects") / project_id / ".wizard-state.json"
