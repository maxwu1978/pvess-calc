"""K.3b — tests for online lookup providers (Mapbox geocoder, NREL
PVWatts). Every test mocks HTTP via the `responses` library so CI never
touches a real API and runs deterministically in <100 ms.

Test priorities (closing standards):
  1. Without env vars, providers gracefully return confidence='miss' —
     never crash, never block the orchestrator.
  2. With env vars + happy-path API response, the new fields populate
     and confidence is set correctly.
  3. Every failure mode (timeout / 4xx / 5xx / non-JSON / empty
     features) yields confidence='miss' with a readable note.
"""
from __future__ import annotations

import pytest
import responses
from responses import matchers

from pvess_calc.lookup.address import parse_address
from pvess_calc.lookup.config import (
    ENV_GOOGLE_SOLAR_KEY,
    ENV_MAPBOX_TOKEN,
    ENV_NREL_API_KEY,
    reset_cache_for_tests,
)
from pvess_calc.lookup.providers.google_solar import google_solar
from pvess_calc.lookup.providers.mapbox_geocode import mapbox_geocode
from pvess_calc.lookup.providers.nrel_pvwatts import nrel_pvwatts


# ─── Common fixtures ──────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def isolate_env_and_cache(monkeypatch, tmp_path):
    """Each test starts with NO env vars and a fresh cache dir."""
    monkeypatch.delenv(ENV_MAPBOX_TOKEN, raising=False)
    monkeypatch.delenv(ENV_NREL_API_KEY, raising=False)
    monkeypatch.delenv(ENV_GOOGLE_SOLAR_KEY, raising=False)
    monkeypatch.setenv("PVESS_CACHE_ROOT", str(tmp_path))
    reset_cache_for_tests()
    yield
    reset_cache_for_tests()


# ─── Mapbox: env-var absent ───────────────────────────────────────────────


def test_mapbox_no_token_returns_miss():
    """No token = clean 'miss' with actionable note."""
    addr = parse_address("Phoenix, AZ")
    r = mapbox_geocode(addr)
    assert r.confidence == "miss"
    assert r.fields == {}
    assert "PVESS_MAPBOX_TOKEN" in r.note


# ─── Mapbox: happy path ───────────────────────────────────────────────────


_PHOENIX_FEATURE = {
    "type": "FeatureCollection",
    "features": [{
        "id": "place.257902828",
        "place_type": ["place"],
        "place_name": "Phoenix, Arizona, United States",
        "text": "Phoenix",
        "geometry": {"coordinates": [-112.0740, 33.4484], "type": "Point"},
        "context": [
            {"id": "district.10227179", "text": "Maricopa County"},
            {"id": "region.2698", "short_code": "US-AZ", "text": "Arizona"},
            {"id": "country.9053", "short_code": "us", "text": "United States"},
        ],
    }]
}


@responses.activate
def test_mapbox_happy_path_returns_lat_lng_county(monkeypatch):
    monkeypatch.setenv(ENV_MAPBOX_TOKEN, "pk.fake-token-for-tests")
    reset_cache_for_tests()
    responses.get(
        "https://api.mapbox.com/geocoding/v5/mapbox.places/Phoenix%2C%20AZ.json",
        json=_PHOENIX_FEATURE, status=200,
    )

    r = mapbox_geocode(parse_address("Phoenix, AZ"))
    assert r.confidence == "high"
    assert r.fields["latitude"] == pytest.approx(33.4484)
    assert r.fields["longitude"] == pytest.approx(-112.0740)
    assert r.fields["county"] == "Maricopa County"
    assert "Phoenix" in r.fields["canonical_address"]


@responses.activate
def test_mapbox_coords_only_is_medium_confidence(monkeypatch):
    """When Mapbox returns coords but no district context, the result
    is still useful (irradiance lookup works) → 'medium'."""
    monkeypatch.setenv(ENV_MAPBOX_TOKEN, "pk.fake")
    reset_cache_for_tests()
    responses.get(
        "https://api.mapbox.com/geocoding/v5/mapbox.places/Phoenix%2C%20AZ.json",
        # v5 feature with coords but no `district.*` entry in context.
        json={"features": [{
            "id": "place.X",
            "place_name": "Unnamed Point",
            "geometry": {"coordinates": [-112.0, 33.4], "type": "Point"},
            "context": [
                {"id": "country.9053", "text": "United States"},
            ],
        }]},
        status=200,
    )
    r = mapbox_geocode(parse_address("Phoenix, AZ"))
    assert r.confidence == "medium"
    assert r.fields["latitude"] == 33.4
    assert "county" not in r.fields


# ─── Mapbox: failure modes ────────────────────────────────────────────────


@responses.activate
def test_mapbox_4xx_returns_miss(monkeypatch):
    """401 / 403 from Mapbox (bad token) → miss with HTTP code in note."""
    monkeypatch.setenv(ENV_MAPBOX_TOKEN, "pk.bad")
    reset_cache_for_tests()
    responses.get(
        "https://api.mapbox.com/geocoding/v5/mapbox.places/Phoenix%2C%20AZ.json",
        json={"message": "Not authorized"}, status=401,
    )
    r = mapbox_geocode(parse_address("Phoenix, AZ"))
    assert r.confidence == "miss"
    assert "HTTP 401" in r.note


@responses.activate
def test_mapbox_5xx_returns_miss(monkeypatch):
    monkeypatch.setenv(ENV_MAPBOX_TOKEN, "pk.fake")
    reset_cache_for_tests()
    responses.get(
        "https://api.mapbox.com/geocoding/v5/mapbox.places/Phoenix%2C%20AZ.json",
        json={"error": "service down"}, status=503,
    )
    r = mapbox_geocode(parse_address("Phoenix, AZ"))
    assert r.confidence == "miss"
    assert "HTTP 503" in r.note


@responses.activate
def test_mapbox_empty_features_returns_miss(monkeypatch):
    monkeypatch.setenv(ENV_MAPBOX_TOKEN, "pk.fake")
    reset_cache_for_tests()
    responses.get(
        "https://api.mapbox.com/geocoding/v5/mapbox.places/"
        "Unknownburg%2C%20NX.json",
        json={"features": []}, status=200,
    )
    r = mapbox_geocode(parse_address("Unknownburg, NX"))
    assert r.confidence == "miss"
    assert "no features" in r.note.lower()


@responses.activate
def test_mapbox_timeout_returns_miss(monkeypatch):
    """ConnectionError simulates DNS failure / network down."""
    import requests
    monkeypatch.setenv(ENV_MAPBOX_TOKEN, "pk.fake")
    reset_cache_for_tests()
    responses.get(
        "https://api.mapbox.com/geocoding/v5/mapbox.places/Phoenix%2C%20AZ.json",
        body=requests.exceptions.ConnectionError("no DNS"),
    )
    r = mapbox_geocode(parse_address("Phoenix, AZ"))
    assert r.confidence == "miss"
    assert "Mapbox API failed" in r.note


@responses.activate
def test_mapbox_passes_country_us_filter(monkeypatch):
    """We deliberately scope geocoding to country=us; the request must
    carry that param so foreign hits don't pollute results. v5 puts the
    query in the URL PATH (not a `q` param) so the matcher checks the
    remaining query string only."""
    monkeypatch.setenv(ENV_MAPBOX_TOKEN, "pk.fake")
    reset_cache_for_tests()
    responses.get(
        "https://api.mapbox.com/geocoding/v5/mapbox.places/Phoenix%2C%20AZ.json",
        json=_PHOENIX_FEATURE, status=200,
        match=[matchers.query_param_matcher(
            {"country": "us", "limit": "1", "access_token": "pk.fake"})],
    )
    mapbox_geocode(parse_address("Phoenix, AZ"))
    # If the matcher didn't match, responses would have raised.


# ─── NREL PVWatts: env-var / lat-lng absent ───────────────────────────────


def test_nrel_no_key_returns_miss():
    r = nrel_pvwatts(parse_address("Phoenix, AZ"))
    assert r.confidence == "miss"
    assert "PVESS_NREL_API_KEY" in r.note


def test_nrel_without_lat_lng_returns_miss(monkeypatch):
    """Key set but no coords supplied → still miss with a 'needs lat/lng'
    note. PVWatts is useless without coords."""
    monkeypatch.setenv(ENV_NREL_API_KEY, "fake-key")
    reset_cache_for_tests()
    r = nrel_pvwatts(parse_address("Phoenix, AZ"))   # lat_lng=None
    assert r.confidence == "miss"
    assert "lat/lng" in r.note


# ─── NREL PVWatts: happy path ─────────────────────────────────────────────


_PVWATTS_OK_PAYLOAD = {
    "station_info": {"location": "722780", "city": "Phoenix Sky Harbor"},
    "outputs": {
        "ac_annual": 1750.4,        # kWh per 1 kW DC per year
        "solrad_annual": 5.74,      # kWh/m²/day
        "ac_monthly": [125, 140, 160, 170, 180, 175,
                       165, 160, 150, 140, 120, 110],
    },
}


@responses.activate
def test_nrel_happy_path_returns_annual_energy(monkeypatch):
    monkeypatch.setenv(ENV_NREL_API_KEY, "fake-key")
    reset_cache_for_tests()
    responses.get(
        "https://developer.nrel.gov/api/pvwatts/v8.json",
        json=_PVWATTS_OK_PAYLOAD, status=200,
    )

    r = nrel_pvwatts(parse_address("Phoenix, AZ"),
                     lat_lng=(33.4484, -112.0740))
    assert r.confidence == "high"
    assert r.fields["annual_energy_kwh_per_kw"] == pytest.approx(1750.4)
    assert r.fields["solar_irradiance_kwh_m2_day"] == pytest.approx(5.74)
    assert "PVWatts" in r.note


@responses.activate
def test_nrel_5xx_returns_miss(monkeypatch):
    monkeypatch.setenv(ENV_NREL_API_KEY, "fake-key")
    reset_cache_for_tests()
    responses.get(
        "https://developer.nrel.gov/api/pvwatts/v8.json",
        json={"errors": ["overloaded"]}, status=503,
    )
    r = nrel_pvwatts(parse_address("Phoenix, AZ"),
                     lat_lng=(33.4484, -112.0740))
    assert r.confidence == "miss"
    assert "503" in r.note


@responses.activate
def test_nrel_out_of_coverage_returns_miss(monkeypatch):
    """A response missing the expected `outputs` keys (PVWatts behavior
    for non-US queries) → miss with the 'out-of-coverage' note."""
    monkeypatch.setenv(ENV_NREL_API_KEY, "fake-key")
    reset_cache_for_tests()
    responses.get(
        "https://developer.nrel.gov/api/pvwatts/v8.json",
        json={"errors": ["lat outside coverage"], "outputs": {}},
        status=200,
    )
    r = nrel_pvwatts(parse_address("Anchorage, AK"),
                     lat_lng=(61.2181, -149.9003))
    assert r.confidence == "miss"
    assert "out-of-coverage" in r.note


@responses.activate
def test_nrel_passes_residential_defaults(monkeypatch):
    """Closing standard: PVWatts call carries the documented residential
    defaults (south-facing, 20° tilt, fixed roof, 14% loss). Locks the
    contract so a future change is intentional."""
    monkeypatch.setenv(ENV_NREL_API_KEY, "fake-key")
    reset_cache_for_tests()
    responses.get(
        "https://developer.nrel.gov/api/pvwatts/v8.json",
        json=_PVWATTS_OK_PAYLOAD, status=200,
        match=[matchers.query_param_matcher({
            "api_key": "fake-key",
            "lat": "33.4484", "lon": "-112.0740",
            "system_capacity": "1", "azimuth": "180", "tilt": "20",
            "array_type": "1", "module_type": "1",
            "losses": "14", "timeframe": "monthly",
        })],
    )
    nrel_pvwatts(parse_address("Phoenix, AZ"),
                 lat_lng=(33.4484, -112.0740))


# ─── Orchestrator integration: K.3a + K.3b in the default chain ──────────


def test_default_chain_with_no_env_vars_matches_offline_only(monkeypatch):
    """Closing standard #1: when no API keys are set, the default chain
    is functionally identical to the K.3a offline-only chain.
    Online providers slot in but contribute nothing."""
    from pvess_calc.lookup import resolve

    r_default = resolve("Phoenix, AZ")
    # Online providers ran but missed:
    online_sources = {"mapbox-geocode", "nrel-pvwatts"}
    for pr in r_default.provider_results:
        if pr.source in online_sources:
            assert pr.confidence == "miss"
    # And contributed zero fields:
    for k in r_default.field_sources.values():
        assert k not in online_sources


@responses.activate
def test_full_chain_with_keys_supplies_lat_lng_to_pvwatts(monkeypatch):
    """Integration: Mapbox geocoder runs → lat/lng populate result.fields
    → nrel_pvwatts then receives those coords via the _call_provider
    sniffer. This guards the lat/lng plumbing — drop it and online
    enrichment regresses to two independent providers."""
    monkeypatch.setenv(ENV_MAPBOX_TOKEN, "pk.fake")
    monkeypatch.setenv(ENV_NREL_API_KEY, "fake-key")
    reset_cache_for_tests()

    responses.get(
        "https://api.mapbox.com/geocoding/v5/mapbox.places/Phoenix%2C%20AZ.json",
        json=_PHOENIX_FEATURE, status=200,
    )
    # PVWatts is called only if Mapbox's lat/lng flows through — and
    # the query string MUST carry those coords.
    responses.get(
        "https://developer.nrel.gov/api/pvwatts/v8.json",
        json=_PVWATTS_OK_PAYLOAD, status=200,
        match=[matchers.query_param_matcher({
            "api_key": "fake-key",
            "lat": "33.4484", "lon": "-112.0740",
            "system_capacity": "1", "azimuth": "180", "tilt": "20",
            "array_type": "1", "module_type": "1",
            "losses": "14", "timeframe": "monthly",
        })],
    )

    from pvess_calc.lookup import resolve
    r = resolve("Phoenix, AZ")
    # K.3a fields still present:
    assert r.fields["utility_name"] == "Arizona Public Service (APS)"
    # K.3b fields newly added:
    assert r.fields["latitude"] == pytest.approx(33.4484)
    assert r.fields["county"] == "Maricopa County"
    assert r.fields["annual_energy_kwh_per_kw"] == pytest.approx(1750.4)
    # Provenance:
    assert r.field_sources["latitude"] == "mapbox-geocode"
    assert r.field_sources["annual_energy_kwh_per_kw"] == "nrel-pvwatts"


# ─── K.3c Google Solar API: env-var absent + degraded paths ─────────────


def test_google_solar_no_key_returns_miss():
    """No key = clean 'miss' with actionable note; offline chain untouched."""
    r = google_solar(parse_address("Frisco, TX"))
    assert r.confidence == "miss"
    assert r.fields == {}
    assert "PVESS_GOOGLE_SOLAR_KEY" in r.note


def test_google_solar_without_lat_lng_returns_miss(monkeypatch):
    """Solar API requires lat/lng — when Mapbox didn't run / failed,
    we 'miss' cleanly with a note that names the upstream dependency."""
    monkeypatch.setenv(ENV_GOOGLE_SOLAR_KEY, "AIza-fake")
    reset_cache_for_tests()
    r = google_solar(parse_address("Frisco, TX"))    # lat_lng=None
    assert r.confidence == "miss"
    assert "Mapbox" in r.note or "lat/lng" in r.note


# ─── K.3c Google Solar API: happy path ──────────────────────────────────


# A realistic Frisco-style 4-face response: south + north + east + west
# rectangular hip-roof. Real Solar API responses are larger (sunshine
# quantiles, panel coordinates, etc) — we keep only what the provider
# actually reads.
_FRISCO_SOLAR_RESPONSE = {
    "name": "buildings/ChIJabc123",
    "center": {"latitude": 33.141418, "longitude": -96.801258},
    "boundingBox": {
        "sw": {"latitude": 33.141, "longitude": -96.802},
        "ne": {"latitude": 33.142, "longitude": -96.800},
    },
    "imageryDate": {"year": 2023, "month": 4, "day": 15},
    "imageryQuality": "HIGH",
    "solarPotential": {
        "maxArrayPanelsCount": 38,
        "maxArrayAreaMeters2": 76.4,
        "wholeRoofStats": {
            "areaMeters2": 234.5,
            "sunshineQuantiles": [1200, 1450, 1600, 1750, 1900],
        },
        "roofSegmentStats": [
            # South-facing main roof
            {"pitchDegrees": 22.4, "azimuthDegrees": 178.2,
             "stats": {"areaMeters2": 38.6}},
            # North-facing main roof
            {"pitchDegrees": 22.4, "azimuthDegrees": 358.0,
             "stats": {"areaMeters2": 35.2}},
            # East gable
            {"pitchDegrees": 22.0, "azimuthDegrees": 88.5,
             "stats": {"areaMeters2": 13.5}},
            # West gable
            {"pitchDegrees": 22.0, "azimuthDegrees": 272.1,
             "stats": {"areaMeters2": 13.5}},
        ],
    },
}


@responses.activate
def test_google_solar_happy_path_returns_4_faces(monkeypatch):
    """Closing standard: a 4-face Frisco rooftop response populates
    `roof_sections` with 4 entries, each carrying pitch + azimuth +
    estimated width/height (sqrt(area)) and a compass-named label."""
    monkeypatch.setenv(ENV_GOOGLE_SOLAR_KEY, "AIza-fake")
    reset_cache_for_tests()
    responses.get(
        "https://solar.googleapis.com/v1/buildingInsights:findClosest",
        json=_FRISCO_SOLAR_RESPONSE, status=200,
    )

    r = google_solar(parse_address("7652 Glasshouse Walk, Frisco TX"),
                     lat_lng=(33.141418, -96.801258))
    assert r.confidence == "high"

    sections = r.fields["roof_sections"]
    assert len(sections) == 4
    names = [s["name"] for s in sections]
    assert "South Roof" in names
    assert "North Roof" in names
    assert "East Roof" in names
    assert "West Roof" in names

    south = next(s for s in sections if s["name"] == "South Roof")
    assert south["pitch_deg"] == pytest.approx(22.4)
    assert south["azimuth_deg"] == pytest.approx(178.2)
    # sqrt(38.6 m² × 10.764 ft²/m²) ≈ 20.4 ft per side
    assert south["width_ft"] == pytest.approx(20.4, abs=0.5)
    assert south["height_ft"] == south["width_ft"]   # square-equivalent
    assert south["shape"] == "rect"
    assert south["module_count"] == 0                 # designer fills

    # Metadata fields also populated
    assert r.fields["google_solar_imagery_quality"] == "HIGH"
    assert r.fields["google_solar_imagery_date"] == "2023-04-15"
    assert r.fields["google_solar_max_panels"] == 38
    assert r.fields["google_solar_whole_roof_area_m2"] == pytest.approx(234.5)


@responses.activate
def test_google_solar_low_quality_downgrades_confidence(monkeypatch):
    """LOW imageryQuality → confidence='low' (wizard surfaces as
    REVIEW-ME). Verifies we don't silently treat photogrammetry-derived
    LOW-confidence responses as authoritative."""
    monkeypatch.setenv(ENV_GOOGLE_SOLAR_KEY, "AIza-fake")
    reset_cache_for_tests()
    payload = {**_FRISCO_SOLAR_RESPONSE, "imageryQuality": "LOW"}
    responses.get(
        "https://solar.googleapis.com/v1/buildingInsights:findClosest",
        json=payload, status=200,
    )
    r = google_solar(parse_address("Frisco, TX"),
                     lat_lng=(33.141418, -96.801258))
    assert r.confidence == "low"
    assert r.fields["google_solar_imagery_quality"] == "LOW"
    # Faces still emitted — LOW isn't a miss, just less trustworthy.
    assert len(r.fields["roof_sections"]) == 4


@responses.activate
def test_google_solar_duplicate_directions_get_suffixed_names(monkeypatch):
    """Two south-facing dormers → 'South Roof' + 'South Roof #2'.
    Prevents silent collision when a complex roof has multiple
    same-direction faces (common on hip + gable combos)."""
    monkeypatch.setenv(ENV_GOOGLE_SOLAR_KEY, "AIza-fake")
    reset_cache_for_tests()
    responses.get(
        "https://solar.googleapis.com/v1/buildingInsights:findClosest",
        json={
            **_FRISCO_SOLAR_RESPONSE,
            "solarPotential": {
                **_FRISCO_SOLAR_RESPONSE["solarPotential"],
                "roofSegmentStats": [
                    {"pitchDegrees": 22, "azimuthDegrees": 178,
                     "stats": {"areaMeters2": 38.6}},
                    {"pitchDegrees": 30, "azimuthDegrees": 182,
                     "stats": {"areaMeters2": 12.0}},   # second south face
                    {"pitchDegrees": 22, "azimuthDegrees": 270,
                     "stats": {"areaMeters2": 13.5}},
                ],
            },
        },
        status=200,
    )
    r = google_solar(parse_address("Frisco, TX"),
                     lat_lng=(33.141418, -96.801258))
    names = [s["name"] for s in r.fields["roof_sections"]]
    assert names == ["South Roof", "South Roof #2", "West Roof"]


# ─── K.3c Google Solar API: every error path returns miss ───────────────


@responses.activate
def test_google_solar_404_returns_miss_with_coverage_note(monkeypatch):
    """Solar API returns 404 when no building found at the lat/lng
    (rural / new construction). The miss note must be more helpful
    than a generic 'HTTP 404' — point the user at EagleView fallback."""
    monkeypatch.setenv(ENV_GOOGLE_SOLAR_KEY, "AIza-fake")
    reset_cache_for_tests()
    responses.get(
        "https://solar.googleapis.com/v1/buildingInsights:findClosest",
        json={"error": {"code": 404, "message": "Building not found"}},
        status=404,
    )
    r = google_solar(parse_address("Empty Field Rd, Nowhere TX"),
                     lat_lng=(31.0, -100.0))
    assert r.confidence == "miss"
    assert "no building" in r.note.lower() or "coverage" in r.note.lower()
    assert "EagleView" in r.note


@responses.activate
def test_google_solar_5xx_returns_miss(monkeypatch):
    monkeypatch.setenv(ENV_GOOGLE_SOLAR_KEY, "AIza-fake")
    reset_cache_for_tests()
    responses.get(
        "https://solar.googleapis.com/v1/buildingInsights:findClosest",
        json={"error": "internal"}, status=503,
    )
    r = google_solar(parse_address("Frisco, TX"),
                     lat_lng=(33.141418, -96.801258))
    assert r.confidence == "miss"
    assert "503" in r.note


@responses.activate
def test_google_solar_empty_segments_returns_miss(monkeypatch):
    """A building was found but has no roofSegmentStats (multi-family
    / commercial typically). Miss — don't write an empty roof_sections
    list that would later confuse the calc engine."""
    monkeypatch.setenv(ENV_GOOGLE_SOLAR_KEY, "AIza-fake")
    reset_cache_for_tests()
    responses.get(
        "https://solar.googleapis.com/v1/buildingInsights:findClosest",
        json={
            "name": "buildings/X", "imageryQuality": "HIGH",
            "solarPotential": {"roofSegmentStats": []},
        },
        status=200,
    )
    r = google_solar(parse_address("Frisco, TX"),
                     lat_lng=(33.141418, -96.801258))
    assert r.confidence == "miss"
    assert "roofSegmentStats" in r.note


@responses.activate
def test_google_solar_max_panels_accepts_float_and_int(monkeypatch):
    """Fix #5 regression-bait: some JSON serializers emit whole numbers
    as floats (76.0 instead of 76). The provider must coerce both into
    an int for the wizard yaml. Also: negative values get rejected as
    nonsense (defensive against malformed API responses)."""
    monkeypatch.setenv(ENV_GOOGLE_SOLAR_KEY, "AIza-fake")
    reset_cache_for_tests()

    # Case A: max_panels arrives as float 76.0 → should become int 76
    payload_float = {
        **_FRISCO_SOLAR_RESPONSE,
        "solarPotential": {
            **_FRISCO_SOLAR_RESPONSE["solarPotential"],
            "maxArrayPanelsCount": 76.0,   # float, not int
        },
    }
    responses.get(
        "https://solar.googleapis.com/v1/buildingInsights:findClosest",
        json=payload_float, status=200,
    )
    r = google_solar(parse_address("Frisco, TX"),
                     lat_lng=(33.141418, -96.801258))
    assert r.fields["google_solar_max_panels"] == 76
    assert isinstance(r.fields["google_solar_max_panels"], int)


@responses.activate
def test_google_solar_passes_required_params(monkeypatch):
    """Closing standard: the request URL carries lat/lng (6-decimal
    precision) + `requiredQuality=LOW` (we want EVERY building, we'll
    re-downgrade confidence later) + the API key. Locks the contract."""
    monkeypatch.setenv(ENV_GOOGLE_SOLAR_KEY, "AIza-fake")
    reset_cache_for_tests()
    responses.get(
        "https://solar.googleapis.com/v1/buildingInsights:findClosest",
        json=_FRISCO_SOLAR_RESPONSE, status=200,
        match=[matchers.query_param_matcher({
            # provider formats both with 6-decimal precision
            "location.latitude":  "33.141418",
            "location.longitude": "-96.801258",
            "requiredQuality":    "LOW",
            "key":                "AIza-fake",
        })],
    )
    r = google_solar(parse_address("Frisco, TX"),
                     lat_lng=(33.141418, -96.801258))
    # If the matcher rejected the call we'd get a miss; assert hit
    # so failure mode is obvious instead of silently passing.
    assert r.confidence != "miss", f"matcher rejected: {r.note}"


# ─── K.3c orchestrator: zero-config behaves like K.3b ───────────────────


def test_default_chain_no_keys_skips_google_solar(monkeypatch):
    """Three online providers, no env vars set → all 'miss', and the
    chain still returns a usable LookupResult from offline-only data."""
    from pvess_calc.lookup import resolve

    r = resolve("Frisco, TX")
    online = {"mapbox-geocode", "nrel-pvwatts", "google-solar"}
    for pr in r.provider_results:
        if pr.source in online:
            assert pr.confidence == "miss", (
                f"{pr.source} unexpectedly hit without an env var: {pr.note}"
            )
    # And no online source ended up authoritative for any field
    for src in r.field_sources.values():
        assert src not in online


@responses.activate
def test_full_chain_threads_lat_lng_into_google_solar(monkeypatch):
    """Integration closing standard: Mapbox lat/lng → google_solar
    (via the same `lat_lng` sniffer as nrel_pvwatts). Drop this plumbing
    and Google Solar can never resolve from an address — would be a
    silent regression."""
    monkeypatch.setenv(ENV_MAPBOX_TOKEN, "pk.fake")
    monkeypatch.setenv(ENV_GOOGLE_SOLAR_KEY, "AIza-fake")
    reset_cache_for_tests()

    responses.get(
        "https://api.mapbox.com/geocoding/v5/mapbox.places/Phoenix%2C%20AZ.json",
        json=_PHOENIX_FEATURE, status=200,
    )
    responses.get(
        "https://solar.googleapis.com/v1/buildingInsights:findClosest",
        json=_FRISCO_SOLAR_RESPONSE, status=200,
        match=[matchers.query_param_matcher({
            # 6-decimal precision: matches provider's f"{lat:.6f}" format
            "location.latitude":  "33.448400",
            "location.longitude": "-112.074000",
            "requiredQuality":    "LOW",
            "key":                "AIza-fake",
        })],
    )
    from pvess_calc.lookup import resolve
    r = resolve("Phoenix, AZ")
    assert r.field_sources["latitude"] == "mapbox-geocode"
    assert r.field_sources["roof_sections"] == "google-solar"
    assert len(r.fields["roof_sections"]) == 4
