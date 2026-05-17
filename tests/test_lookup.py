"""Tests for the Phase K.3 lookup service.

What we're guarding:
  * Address parsing handles the common US shapes (full street, city/state,
    city ST without comma) AND gracefully returns None fields for
    non-US / empty input.
  * The default provider chain returns ≥8 fields for a metro on every
    dataset (Phoenix).
  * The cache is 24-hour TTL: a second resolve() hits the cache (no
    provider re-call) but an expired entry causes a refresh.
  * A crashing provider does not bring down the orchestrator.
  * Wizard --address pre-fill plumbs lookup output into prompt defaults.
"""
from __future__ import annotations

import io
import json
import os
import time
from pathlib import Path

import pytest

from pvess_calc.lookup import (
    DEFAULT_PROVIDERS,
    LookupResult,
    LOOKUP_FIELD_TO_YAML_PATH,
    parse_address,
    resolve,
)
from pvess_calc.lookup import cache as lookup_cache
from pvess_calc.lookup.providers import ProviderResult


# ─── Cache isolation ────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Every K.3a test runs as if no API keys are configured + has a
    fresh cache dir. Without the token-strip the developer's local .env
    (loaded by `lookup.config`) would make online providers hit real
    APIs and inflate `hit_count`, breaking the K.3a-only contract these
    tests guard."""
    from pvess_calc.lookup.config import (
        ENV_MAPBOX_TOKEN, ENV_NREL_API_KEY, reset_cache_for_tests,
    )
    monkeypatch.setenv("PVESS_CACHE_ROOT", str(tmp_path / "pvess"))
    monkeypatch.delenv(ENV_MAPBOX_TOKEN, raising=False)
    monkeypatch.delenv(ENV_NREL_API_KEY, raising=False)
    reset_cache_for_tests()
    yield
    reset_cache_for_tests()


# ─── Address parsing ────────────────────────────────────────────────────────


def test_parse_full_street_address():
    p = parse_address("2500 Hollow Hill Lane, Lewisville, TX 75067")
    assert p.street == "2500 Hollow Hill Lane"
    assert p.city == "Lewisville"
    assert p.state == "TX"
    assert p.zip_code == "75067"
    assert p.city_state_key == "lewisville, tx"


def test_parse_city_state_with_zip():
    p = parse_address("San Francisco, CA 94110")
    assert p.city == "San Francisco"
    assert p.state == "CA"
    assert p.zip_code == "94110"
    assert p.street is None


def test_parse_city_state_no_comma():
    p = parse_address("Phoenix AZ")
    assert p.city == "Phoenix"
    assert p.state == "AZ"


def test_parse_multi_word_city():
    """'Fort Worth, TX' must keep 'Fort Worth' as one city."""
    p = parse_address("Fort Worth, TX")
    assert p.city == "Fort Worth"
    assert p.state == "TX"
    assert p.city_state_key == "fort worth, tx"


def test_parse_empty_returns_all_none():
    p = parse_address("")
    assert p.city is None and p.state is None and p.zip_code is None


def test_parse_non_us_state():
    """Canadian province 'AB' is not a US state — graceful None."""
    p = parse_address("Calgary, AB")
    assert p.state is None


# ─── Provider hit-rates on the curated dataset ─────────────────────────────


def test_phoenix_returns_at_least_eight_fields():
    """Closing criterion #1: ≥8 fields for a covered metro."""
    r = resolve("Phoenix, AZ")
    assert len(r.fields) >= 8, (
        f"Phoenix should return ≥8 fields, got {len(r.fields)}: {list(r.fields)}"
    )
    # Spot-check the major categories all appeared:
    assert r.fields["utility_name"] == "Arizona Public Service (APS)"
    assert r.fields["nec_edition"] == "2017"
    assert r.fields["iecc_climate_zone"] == "2B"
    assert "ahj_name" in r.fields
    assert "ashrae_2pct_min_c" in r.fields
    assert "ashrae_2pct_max_c" in r.fields


def test_lewisville_full_address():
    """User's own real project address — must hit all six offline
    datasets (ashrae + utility + utility_rate + ahj + climate + nec)."""
    r = resolve("2500 Hollow Hill Lane, Lewisville, TX 75067")
    assert r.hit_count == 6
    assert r.fields["utility_name"] == "Oncor Electric Delivery"
    assert r.fields["nec_edition"] == "2020"
    assert r.fields["iecc_climate_zone"] == "3A"
    # K.4 utility rate dataset
    assert r.fields["avg_residential_rate_usd_per_kwh"] == pytest.approx(0.142)


def test_unknown_city_graceful_miss():
    """Unrecognised city → state-level providers still hit, city-level miss."""
    r = resolve("Smallville, KS")
    # KS is in nec_adoption + climate_zone; not in ashrae/utility/ahj.
    assert "nec_edition" in r.fields
    assert "iecc_climate_zone" in r.fields
    assert "utility_name" not in r.fields
    assert "ahj_name" not in r.fields


def test_non_us_returns_zero_fields():
    r = resolve("Calgary, AB")
    assert r.hit_count == 0
    assert r.fields == {}


def test_field_sources_populated():
    """Every field must carry source provenance."""
    r = resolve("Phoenix, AZ")
    for field_name in r.fields:
        assert field_name in r.field_sources, f"missing source for {field_name}"
        assert field_name in r.field_confidence


def test_export_tariff_recommendation_ca_is_nem3():
    """K.7 [3/4] — California cities default to CA NEM 3.0 because
    NEM 1.0 / 2.0 are closed to new applicants post-2023-04."""
    r = resolve("Los Angeles, CA")
    assert r.fields.get("recommended_export_tariff") == "ca_nem3"
    r = resolve("San Diego, CA")
    assert r.fields.get("recommended_export_tariff") == "ca_nem3"


def test_export_tariff_recommendation_hi_is_self_consumption():
    """K.7 [3/4] — Hawaii defaults to Customer Self-Supply / Smart Export.
    HI closed NEM in 2015; Rule 14H CSS / Smart Export are the only paths
    open to new applicants."""
    r = resolve("Honolulu, HI")
    assert r.fields.get("recommended_export_tariff") == "hi_self_consumption"


def test_export_tariff_recommendation_other_states_default_1to1():
    """Most US states still operate 1:1 NEM (or close approximations).
    AZ, TX, FL, NY etc. all default to the same tariff model."""
    for city in ("Phoenix, AZ", "Austin, TX", "Miami, FL", "New York, NY"):
        r = resolve(city)
        assert r.fields.get("recommended_export_tariff") == "1to1_nem", (
            f"{city} should default to 1to1_nem, got "
            f"{r.fields.get('recommended_export_tariff')}"
        )


def test_climate_zone_city_override_wins_over_state_default():
    """Phoenix should report 2B (city override), not 3B (AZ state default)."""
    r = resolve("Phoenix, AZ")
    assert r.fields["iecc_climate_zone"] == "2B"
    assert r.field_confidence["iecc_climate_zone"] == "medium"


# ─── Cache TTL ──────────────────────────────────────────────────────────────


def test_resolve_hits_cache_second_time():
    """Closing criterion #3: cache short-circuits providers."""
    calls = {"n": 0}

    def counting_provider(addr):
        calls["n"] += 1
        return ProviderResult(
            source="counting",
            fields={"counted": calls["n"]},
            confidence="high",
        )

    r1 = resolve("Phoenix, AZ", providers=[counting_provider])
    r2 = resolve("Phoenix, AZ", providers=[counting_provider])
    assert calls["n"] == 1, "second resolve should have hit the cache"
    assert r1.fields["counted"] == r2.fields["counted"] == 1


def test_cache_expiry_triggers_refresh(monkeypatch):
    """Closing criterion #3b: expired entries are NOT served stale."""
    calls = {"n": 0}

    def counting_provider(addr):
        calls["n"] += 1
        return ProviderResult(
            source="counting",
            fields={"counted": calls["n"]},
            confidence="high",
        )

    resolve("Phoenix, AZ", providers=[counting_provider])
    assert calls["n"] == 1

    # Rewind the cached entry's timestamp past the TTL.
    for f in lookup_cache.cache_root().glob("*.json"):
        data = json.loads(f.read_text())
        data["timestamp"] = time.time() - 48 * 3600   # 2 days old
        f.write_text(json.dumps(data))

    resolve("Phoenix, AZ", providers=[counting_provider])
    assert calls["n"] == 2, "expired cache entry should not be reused"


def test_use_cache_false_bypasses(monkeypatch):
    calls = {"n": 0}

    def counting_provider(addr):
        calls["n"] += 1
        return ProviderResult(source="x", fields={"c": calls["n"]}, confidence="high")

    resolve("Phoenix, AZ", providers=[counting_provider], use_cache=False)
    resolve("Phoenix, AZ", providers=[counting_provider], use_cache=False)
    assert calls["n"] == 2


def test_cache_clear():
    resolve("Phoenix, AZ")
    assert any(lookup_cache.cache_root().glob("*.json"))
    n = lookup_cache.clear()
    assert n >= 1
    assert not any(lookup_cache.cache_root().glob("*.json"))


# ─── Failure resilience ────────────────────────────────────────────────────


def test_crashing_provider_does_not_abort_chain():
    """Closing criterion #4: one bad provider must not break the rest."""
    def good(addr):
        return ProviderResult(
            source="good", fields={"x": 1}, confidence="high",
        )

    def crashy(addr):
        raise ValueError("intentional test crash")

    r = resolve("Phoenix, AZ", providers=[good, crashy])
    # Good provider still contributed:
    assert r.fields["x"] == 1
    # Crashy provider's result is recorded as a miss with the error msg:
    crashy_result = r.provider_results[1]
    assert crashy_result.confidence == "miss"
    assert "intentional" in crashy_result.note


# ─── Wizard integration ───────────────────────────────────────────────────


def test_lookup_field_to_yaml_path_maps_only_existing_yaml_paths():
    """Pre-fill map keys must reference real WIZARD_FIELDS yaml paths
    — otherwise pre-fill writes a default the wizard never asks about."""
    from pvess_calc.wizard.field_specs import WIZARD_FIELDS
    wizard_paths = {f.yaml_path for f in WIZARD_FIELDS}
    for lookup_key, yaml_path in LOOKUP_FIELD_TO_YAML_PATH.items():
        assert yaml_path in wizard_paths, (
            f"LOOKUP_FIELD_TO_YAML_PATH[{lookup_key!r}] = {yaml_path!r} "
            f"is not a wizard field"
        )


def test_wizard_address_prefill_seeds_utility(tmp_path, monkeypatch):
    """End-to-end: pvess-init --address 'Phoenix, AZ' pre-fills the
    utility / NEC / ASHRAE fields. The user just accepts every default
    by pressing <enter> at each pre-filled prompt."""
    monkeypatch.chdir(tmp_path)

    # Build the same stdin stream the existing wizard test uses, but
    # the prefilled scalar prompts now accept a default — meaning a
    # blank line takes the default. We construct a stream that accepts
    # the default for every prefilled field, and supplies a value for
    # the rest.
    from pvess_calc.wizard.field_specs import (
        WIZARD_FIELDS, is_list_field, list_prefix,
    )
    from pvess_calc.wizard.runner import _prefill_from_address

    prefills = _prefill_from_address("Phoenix, AZ")
    assert prefills, "lookup must yield at least one pre-fill for Phoenix"

    scalar_answers: list[str] = []
    list_prefixes_seen: list[str] = []
    for spec in WIZARD_FIELDS:
        if spec.yaml_path == "project.id":
            continue
        if is_list_field(spec):
            prefix = list_prefix(spec)
            if prefix not in list_prefixes_seen:
                list_prefixes_seen.append(prefix)
            continue
        if spec.yaml_path in prefills:
            # accept the default → blank line
            scalar_answers.append("")
            continue
        # Otherwise the standard mock answer.
        if spec.field_type == "choice":
            scalar_answers.append(spec.choices[0])
        elif spec.field_type == "integer":
            scalar_answers.append(_int_mock(spec))
        elif spec.field_type == "number":
            scalar_answers.append(_num_mock(spec))
        else:
            scalar_answers.append(_text_mock(spec))

    list_answers = ["0"] * len(list_prefixes_seen)
    stream = "\n".join(scalar_answers + list_answers) + "\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(stream))

    from pvess_calc.wizard.runner import run_wizard
    yaml_path = run_wizard("test-phx", address="Phoenix, AZ")
    assert yaml_path.exists()

    import yaml
    data = yaml.safe_load(yaml_path.read_text())
    # Address pre-fill made it through to inputs.yaml:
    assert data["project"]["utility"] == "Arizona Public Service (APS)"
    assert data["project"]["nec_edition"] == "2017"
    assert data["pv_array"]["ashrae_2pct_min_c"] == -2.0
    assert data["routing"]["ambient_temp_c"] == 43.5
    # And project.location was auto-formatted from the address:
    assert data["project"]["location"] == "Phoenix, AZ"


# ─── Helpers (mirror test_wizard's mock helpers, kept local to avoid
# coupling) ────────────────────────────────────────────────────────────────


def _text_mock(spec) -> str:
    if "email" in spec.yaml_path:
        return "test@example.com"
    if "phone" in spec.yaml_path:
        return "555-0100"
    if spec.yaml_path == "service.voltage":
        return "120/240 split-phase"
    if spec.yaml_path == "service.interconnection_methods":
        return "supply_side_tap"
    if spec.yaml_path == "project.initial_design_date":
        return "2026-01-01"
    return "test"


def _num_mock(spec) -> str:
    table = {
        "pv_array.module.power_w": "420",
        "pv_array.module.voc_stc": "50",
        "pv_array.module.isc_stc": "13",
        "pv_array.temp_min_c": "-2",
        "pv_array.temp_max_c": "50",
        "battery.nominal_voltage": "51.2",
        "battery.capacity_kwh_each": "5",
        "inverter.ac_output_v": "240",
        "inverter.ac_output_a": "33",
        "service.main_panel_a": "200",
        "service.busbar_a": "200",
    }
    return table.get(spec.yaml_path, "0")


def _int_mock(spec) -> str:
    table = {
        "pv_array.modules": "10",
        "pv_array.strings": "1",
        "pv_array.modules_per_string": "10",
        "battery.quantity": "1",
        "inverter.quantity": "1",
    }
    return table.get(spec.yaml_path, "0")
