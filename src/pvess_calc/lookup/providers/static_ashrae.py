"""ASHRAE 2% extreme min/max design temperatures (offline).

Lookup key: lowercased 'city, st'. On a miss we still report the source
and confidence='miss' so the orchestrator can show the user 'not in our
table' rather than silently dropping the field.
"""
from __future__ import annotations

from ..address import ParsedAddress
from .base import ProviderResult, load_dataset


_DATA = load_dataset("ashrae.json")


def static_ashrae(address: ParsedAddress) -> ProviderResult:
    key = address.city_state_key
    if key and key in _DATA:
        row = _DATA[key]
        return ProviderResult(
            source="ashrae-offline",
            fields={
                "ashrae_2pct_min_c": row["min_c"],
                "ashrae_2pct_max_c": row["max_c"],
            },
            confidence="high",
            note=f"ASHRAE 2% extremes for {row.get('city_official', address.city)}.",
        )
    return ProviderResult(
        source="ashrae-offline",
        confidence="miss",
        note=("City not in offline ASHRAE table. Look up manually in ASHRAE "
              "Handbook of Fundamentals Ch. 14 or NREL design-condition tables."),
    )
