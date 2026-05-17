"""Authority Having Jurisdiction (AHJ) offline lookup. Keyed by 'city, st'."""
from __future__ import annotations

from ..address import ParsedAddress
from .base import ProviderResult, load_dataset


_DATA = load_dataset("ahj.json")


def static_ahj(address: ParsedAddress) -> ProviderResult:
    key = address.city_state_key
    if key and key in _DATA:
        row = _DATA[key]
        fields = {"ahj_name": row["ahj_name"]}
        if "permit_portal" in row:
            fields["ahj_permit_portal"] = row["permit_portal"]
        return ProviderResult(
            source="ahj-offline",
            fields=fields,
            confidence="medium",
            note=row.get("note", "")
                 or ("AHJ is usually the city building dept inside city limits, "
                     "or the county building dept for unincorporated areas — "
                     "confirm if the site address is just outside the city."),
        )
    return ProviderResult(
        source="ahj-offline",
        confidence="miss",
        note=("City not in offline AHJ table. Default rule: city building "
              "dept inside city limits, county building dept otherwise."),
    )
