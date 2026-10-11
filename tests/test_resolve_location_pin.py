"""Local PIN -> lat/lon fast-path (services/weather_alert/data/pincode_latlon.csv):
an exact PIN farmers are likely to give must resolve without ever calling
Nominatim. Free-text place names, PINs missing from the table, and
non-India country codes must still go through Nominatim exactly as
before (found in review of the weather flow)."""
from __future__ import annotations

import pytest

from services.weather_alert import service


def _fail_if_called(url, params=None, headers=None, timeout=0):
    raise AssertionError(f"must not call the network for a local-index hit: {url}")


def test_known_pin_resolves_without_any_network_call(monkeypatch):
    service._cache.clear()
    monkeypatch.setattr(service.requests, "get", _fail_if_called)

    loc = service.resolve_location("411001", country_code="in")
    assert loc.lat == pytest.approx(18.52322, abs=1e-3)
    assert loc.lon == pytest.approx(73.87586, abs=1e-3)
    assert "Pune" in loc.display_name
    assert "Maharashtra" in loc.display_name


def test_local_index_has_the_expected_shape():
    index = service._local_pin_index()
    assert len(index) > 15000, "sanity check: the bundled dataset must have loaded"
    lat, lon, district, state = index["560001"]
    assert district == "Bengaluru Urban"
    assert state == "Karnataka"
    assert 12.0 < lat < 14.0 and 77.0 < lon < 78.0


def test_pin_not_in_local_table_falls_back_to_nominatim(monkeypatch):
    service._cache.clear()
    calls = []

    def _fake_get(url, params=None, headers=None, timeout=0):
        calls.append(url)
        if "nominatim" in url:
            return _FakeResponseForFallback([{"display_name": "Somewhere, Some State, India", "lat": "10.0", "lon": "80.0"}])
        raise AssertionError("Unexpected URL")

    monkeypatch.setattr(service, "_local_pin_index", lambda: {})  # simulate a PIN missing from the table
    monkeypatch.setattr(service.requests, "get", _fake_get)

    loc = service.resolve_location("999999", country_code="in")
    assert calls, "a PIN missing from the local table must still hit Nominatim"
    assert loc.lat == 10.0


def test_place_name_always_uses_nominatim_even_if_text_is_a_known_pin_prefix(monkeypatch):
    """Not a PIN at all (_is_pin_code rejects non-digit strings) -- must
    never consult the local index."""
    service._cache.clear()
    calls = []

    def _fake_get(url, params=None, headers=None, timeout=0):
        calls.append(url)
        return _FakeResponseForFallback([{"display_name": "Pune, Maharashtra, India", "lat": "18.5", "lon": "73.8"}])

    monkeypatch.setattr(service.requests, "get", _fake_get)
    service.resolve_location("Pune", country_code="in")
    assert calls, "a free-text place name must always go through Nominatim"


def test_non_india_country_code_bypasses_the_local_index(monkeypatch):
    """The dataset is India-only -- a PIN-shaped query for another
    country must not be resolved against it."""
    service._cache.clear()
    calls = []

    def _fake_get(url, params=None, headers=None, timeout=0):
        calls.append(url)
        return _FakeResponseForFallback([{"display_name": "Somewhere, Some Country", "lat": "1.0", "lon": "1.0"}])

    monkeypatch.setattr(service.requests, "get", _fake_get)
    service.resolve_location("411001", country_code="us")
    assert calls, "a non-India country code must always go through Nominatim"


class _FakeResponseForFallback:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload
