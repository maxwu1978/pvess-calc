"""Utility company offline lookup. Keyed by 'city, st'."""
from __future__ import annotations

from ..address import ParsedAddress
from .base import ProviderResult, load_dataset


_DATA = load_dataset("utility.json")


def static_utility(address: ParsedAddress) -> ProviderResult:
    key = address.city_state_key
    if key and key in _DATA:
        row = _DATA[key]
        fields = {"utility_name": row["utility_name"]}
        if "territory_type" in row:
            fields["utility_territory_type"] = row["territory_type"]
        if "interconnection_doc" in row:
            fields["utility_interconnection_doc"] = row["interconnection_doc"]
        return ProviderResult(
            source="utility-offline",
            fields=fields,
            confidence="medium",   # multi-utility metros need a homeowner-bill check
            note=row.get("note", "")
                 or "Confirm against the homeowner's electric bill.",
        )
    return ProviderResult(
        source="utility-offline",
        confidence="miss",
        note="City not in offline utility table — check homeowner's bill.",
    )
