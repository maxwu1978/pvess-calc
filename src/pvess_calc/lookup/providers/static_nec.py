"""NEC adoption offline lookup.

Returns the state-default NEC edition. The result is `confidence=low`
because individual AHJ frequently enforce a later edition — the wizard
must still confirm with the homeowner / local building dept.
"""
from __future__ import annotations

from ..address import ParsedAddress
from .base import ProviderResult, load_dataset


_DATA = load_dataset("nec_adoption.json")


def static_nec(address: ParsedAddress) -> ProviderResult:
    state = address.state_key
    if state and state in _DATA:
        row = _DATA[state]
        return ProviderResult(
            source="nec-adoption-offline",
            fields={"nec_edition": row["edition"]},
            confidence="low",
            note=row.get("note", "")
                 or ("State-default NEC edition. Individual AHJ may enforce a "
                     "later edition — confirm with the local building dept."),
        )
    return ProviderResult(
        source="nec-adoption-offline",
        confidence="miss",
    )
