# Add a lookup provider

A provider is a function that takes a `ParsedAddress` and returns a
`ProviderResult` — a set of fields the wizard / customer-summary can use
to pre-fill or refine the project. K.3 offline shipped 6 providers
(ASHRAE / utility / utility-rate / AHJ / climate zone / NEC adoption);
K.3b added 2 online (Mapbox + NREL).

This recipe walks through adding a 7th: **EIA utility-bill-history
data** (online, env-var key) as a hypothetical example.

## Provider contract

```python
# src/pvess_calc/lookup/providers/base.py (already defined)
class Provider(Protocol):
    def __call__(self, address: ParsedAddress) -> ProviderResult: ...

@dataclass
class ProviderResult:
    source: str                       # "eia-utility-history" etc.
    fields: dict[str, Any] = field(default_factory=dict)
    confidence: str = "low"            # "high" | "medium" | "low" | "miss"
    note: str = ""
```

`fields` is whatever data you want surfaced; the orchestrator merges
results across providers (later in chain wins on conflict).

## Step 1: Write the provider

```python
# src/pvess_calc/lookup/providers/eia_utility_history.py
"""EIA Form 861 utility-history provider — average monthly kWh
consumption for a residential customer in a given utility territory."""
from __future__ import annotations

from ..address import ParsedAddress
from ..config import get_eia_api_key   # see Step 3
from ._http import ProviderError, http_get_json
from .base import ProviderResult


_EIA_URL = "https://api.eia.gov/v2/electricity/retail-sales/data"


def eia_utility_history(address: ParsedAddress) -> ProviderResult:
    key = get_eia_api_key()
    if not key:
        return ProviderResult(
            source="eia-utility-history",
            confidence="miss",
            note="PVESS_EIA_API_KEY env var not set — get a key at "
                 "https://www.eia.gov/opendata/.",
        )
    if not address.state:
        return ProviderResult(
            source="eia-utility-history",
            confidence="miss",
            note="EIA query needs a state.",
        )
    try:
        payload = http_get_json(_EIA_URL, params={
            "api_key": key,
            "frequency": "monthly",
            "data[0]": "sales",
            "facets[stateid][]": address.state,
            "facets[sectorid][]": "RES",
            "length": 12,
        })
    except ProviderError as exc:
        return ProviderResult(
            source="eia-utility-history",
            confidence="miss",
            note=f"EIA API failed: {exc}",
        )
    # ... transform payload, compute avg residential monthly kWh ...
    avg_kwh = ...
    return ProviderResult(
        source="eia-utility-history",
        fields={"state_avg_monthly_kwh": avg_kwh},
        confidence="medium",
        note=f"EIA Form 861 state average for {address.state}.",
    )
```

## Step 2: Register in the chain

```python
# src/pvess_calc/lookup/__init__.py
from .providers.eia_utility_history import eia_utility_history

DEFAULT_PROVIDERS: tuple[Provider, ...] = (
    static_ashrae,
    static_utility,
    static_utility_rate,
    static_ahj,
    static_climate,
    static_nec,
    mapbox_geocode,
    nrel_pvwatts,
    eia_utility_history,    # ← new
)
```

Provider ordering matters: later providers win on conflicting keys.
Online providers run after offline so a network failure never invalidates
the offline fallback.

## Step 3: Env-var config (if online provider)

```python
# src/pvess_calc/lookup/config.py
ENV_EIA_API_KEY: str = "PVESS_EIA_API_KEY"

@lru_cache(maxsize=1)
def get_eia_api_key() -> Optional[str]:
    val = os.environ.get(ENV_EIA_API_KEY, "").strip()
    return val or None

def reset_cache_for_tests() -> None:
    get_mapbox_token.cache_clear()
    get_nrel_api_key.cache_clear()
    get_eia_api_key.cache_clear()    # ← new
```

## Step 4: Map field → wizard yaml_path (if relevant)

If the new field should pre-fill a wizard prompt:

```python
# src/pvess_calc/lookup/__init__.py
LOOKUP_FIELD_TO_YAML_PATH: dict[str, str] = {
    "utility_name":              "project.utility",
    # ...
    "state_avg_monthly_kwh":     None,   # informational only — no yaml path
}
```

`None` means "available in lookup but not auto-injected into yaml" —
typically true for online enrichment fields.

## Step 5: Test with `responses`

```python
# tests/test_lookup_online.py
@responses.activate
def test_eia_utility_history_happy_path(monkeypatch):
    monkeypatch.setenv("PVESS_EIA_API_KEY", "fake-key")
    reset_cache_for_tests()
    responses.get(
        "https://api.eia.gov/v2/electricity/retail-sales/data",
        json=_FAKE_EIA_PAYLOAD, status=200,
    )
    r = eia_utility_history(parse_address("Phoenix, AZ"))
    assert r.confidence == "medium"
    assert r.fields["state_avg_monthly_kwh"] == pytest.approx(...)
```

Always cover:

1. Missing env var → `confidence="miss"`
2. Happy path → expected fields
3. HTTP 4xx → `confidence="miss"` with status code in note
4. HTTP 5xx → same
5. Malformed payload → safe fallback

The orchestrator's per-provider try/except already catches crashes —
your job is just to never raise unintentionally.

## Step 6: Update `pvess lookup` discoverability

The verify command auto-discovers all keys via
`_check_lookup_offline_works_without_keys` and prints fingerprints for
any env-var-driven provider. No code change needed — the new provider
will appear in `pvess lookup` output automatically.

## Verification

```bash
# Offline path still works
unset PVESS_EIA_API_KEY
pvess lookup "Phoenix, AZ"

# Online path
export PVESS_EIA_API_KEY=...
pvess lookup "Phoenix, AZ"   # should now show state_avg_monthly_kwh
```

The doctor's `lookup_offline_works_without_keys` continues to enforce
offline-first behaviour — your provider being added doesn't reduce the
offline field count.
