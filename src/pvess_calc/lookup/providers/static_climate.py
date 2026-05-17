"""IECC climate zone offline lookup.

State-level default, with a per-city override map for states that span
multiple zones (FL, TX, CA, AZ, …). For the cases we care about — solar
sizing in moderate-to-hot residential markets — the override list
covers the projects this tool is likely to encounter.
"""
from __future__ import annotations

from ..address import ParsedAddress
from .base import ProviderResult, load_dataset


_DATA = load_dataset("climate_zone.json")


def static_climate(address: ParsedAddress) -> ProviderResult:
    state = address.state_key
    if state and state in _DATA:
        row = _DATA[state]
        zone = row["zone"]
        confidence = "low"   # state-level default
        note = row.get("note", "")

        # City-level override?
        if address.city and "by_city" in row:
            city_key = address.city.lower()
            if city_key in row["by_city"]:
                zone = row["by_city"][city_key]
                confidence = "medium"
                note = f"City-specific IECC zone for {address.city}."

        return ProviderResult(
            source="climate-zone-offline",
            fields={"iecc_climate_zone": zone},
            confidence=confidence,
            note=note,
        )
    return ProviderResult(
        source="climate-zone-offline",
        confidence="miss",
        note="State not in IECC zone table — non-US address?",
    )
