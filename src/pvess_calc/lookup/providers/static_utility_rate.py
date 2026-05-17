"""Average residential utility rate offline lookup. Keyed by 'city, st'.

Drives the K.4 customer-summary monthly-savings figure. When a city
isn't in our hand-curated dataset, we fall back to a state-level mean —
which is poor but better than the USA average ($0.165/kWh).

K.7 [3/4] addition: also emits a `recommended_export_tariff` field
based on the state — `ca_nem3` for California (post-2023-04 NEM 3.0),
`hi_self_consumption` for Hawaii (Rule 14H / Customer Self-Supply /
Smart Export), `1to1_nem` everywhere else. The wizard's --address
pre-fill maps this to `loads.export_tariff_model`, so a CA project
gets the realistic NEM 3.0 ROI from day one without engineer override.
"""
from __future__ import annotations

from ..address import ParsedAddress
from .base import ProviderResult, load_dataset


_DATA = load_dataset("utility_rate.json")


# State → recommended export tariff. Updated as more states adopt
# similar successor tariffs (NV S.B. 358 export rate, ME Rule 313, etc.).
_STATE_EXPORT_TARIFF: dict[str, str] = {
    "CA": "ca_nem3",                # NEM 3.0 effective 2023-04
    "HI": "hi_self_consumption",    # Rule 14H CSS / Smart Export
    # Everything else → 1:1 net metering (default in 30+ states).
}


def static_utility_rate(address: ParsedAddress) -> ProviderResult:
    key = address.city_state_key
    state = address.state_key
    if key and key in _DATA:
        row = _DATA[key]
        fields = {"avg_residential_rate_usd_per_kwh": float(row["rate_usd_per_kwh"])}
        if "utility" in row:
            fields["utility_rate_attribution"] = row["utility"]
        if state in _STATE_EXPORT_TARIFF:
            fields["recommended_export_tariff"] = _STATE_EXPORT_TARIFF[state]
        else:
            fields["recommended_export_tariff"] = "1to1_nem"
        return ProviderResult(
            source="utility-rate-offline",
            fields=fields,
            confidence="medium",
            note=row.get("note", "")
                 or ("Regional-average residential rate. Actual bill depends "
                     "on the specific tariff (TOU / fixed / demand) and "
                     "seasonal blocks."),
        )
    return ProviderResult(
        source="utility-rate-offline",
        confidence="miss",
        note=("City not in offline rate table. K.4 summary will fall back "
              "to USA-average $0.165/kWh."),
    )
