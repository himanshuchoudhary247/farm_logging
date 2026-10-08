from __future__ import annotations

import time

import pytest

from services.weather_alert import service


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self):
        return self._payload


def test_get_weather_alert_from_pin(monkeypatch):
    def _fake_get(url, params=None, headers=None, timeout=0):
        if "nominatim" in url:
            assert "q" in (params or {})
            return _FakeResponse(
                [
                    {
                        "display_name": "Pune, Maharashtra, India",
                        "lat": "18.5204",
                        "lon": "73.8567",
                    }
                ]
            )
        if "open-meteo" in url:
            return _FakeResponse(
                {
                    "daily": {
                        "time": ["2026-06-23", "2026-06-24"],
                        "weather_code": [95, 3],
                        "precipitation_sum": [20.0, 0.0],
                        "wind_speed_10m_max": [55.0, 10.0],
                        "temperature_2m_max": [33.0, 32.0],
                        "temperature_2m_min": [24.0, 23.0],
                    }
                }
            )
        raise AssertionError("Unexpected URL")

    monkeypatch.setattr(service.requests, "get", _fake_get)

    out = service.get_weather_alert("411001", country_code="in", days=2)
    assert out["risk_level"] == "high"
    assert out["alerts"]
    assert out["resolved_location"]["display_name"].startswith("Pune")
    assert out["resolved_location"]["state"] == "Maharashtra"


def test_get_weather_alert_handles_no_geo_match(monkeypatch):
    def _fake_get(url, params=None, headers=None, timeout=0):
        if "nominatim" in url:
            return _FakeResponse([])
        raise AssertionError("Unexpected URL")

    monkeypatch.setattr(service.requests, "get", _fake_get)

    with pytest.raises(ValueError):
        service.get_weather_alert("unknown-place", country_code="in", days=2)


def test_get_weather_alert_low_risk(monkeypatch):
    def _fake_get(url, params=None, headers=None, timeout=0):
        if "nominatim" in url:
            return _FakeResponse(
                [
                    {
                        "display_name": "Belagavi, Karnataka, India",
                        "lat": "15.8497",
                        "lon": "74.4977",
                    }
                ]
            )
        if "open-meteo" in url:
            return _FakeResponse(
                {
                    "daily": {
                        "time": ["2026-06-23"],
                        "weather_code": [2],
                        "precipitation_sum": [0.2],
                        "wind_speed_10m_max": [9.0],
                        "temperature_2m_max": [30.0],
                        "temperature_2m_min": [21.0],
                    }
                }
            )
        raise AssertionError("Unexpected URL")

    monkeypatch.setattr(service.requests, "get", _fake_get)

    out = service.get_weather_alert("Belagavi", country_code="in", days=1)
    assert out["risk_level"] == "low"
    assert out["alerts"] == []
    assert out["resolved_location"]["state"] == "Karnataka"


def test_is_pin_code_rejects_non_ascii_digits():
    """Real bug, found in a robustness audit: str.isdigit() is True for
    non-ASCII digits too (Devanagari, superscripts, etc.) -- a PIN typed
    in Devanagari script took the PIN branch, got sent to the geocoder
    verbatim, resolved to nothing, and the farmer got "could not resolve
    location" instead of their PIN being read correctly."""
    assert service._is_pin_code("560001") is True
    assert service._is_pin_code("५६०००१") is False, "Devanagari digits must not be treated as a valid PIN"
    assert service._is_pin_code("") is False
    assert service._is_pin_code("1234") is False, "too short to be a PIN"
    assert service._is_pin_code("123456789") is False, "too long to be a PIN"


def test_weather_cache_evicts_oldest_beyond_cap():
    """Real bug, found in a robustness audit: _cache was unbounded and had
    no lock at all. Now an LRU-bounded, locked OrderedDict."""
    service._cache.clear()
    original_cap = service._MAX_CACHE_ENTRIES
    service._MAX_CACHE_ENTRIES = 3
    try:
        for i in range(5):
            service._cache_set(f"key{i}", i)
        assert len(service._cache) == 3, "cache must not grow past the cap"
        assert "key0" not in service._cache, "oldest entry must be evicted first"
        assert service._cache_get("key4") == 4
    finally:
        service._MAX_CACHE_ENTRIES = original_cap
        service._cache.clear()


def test_weather_cache_access_refreshes_lru_order():
    service._cache.clear()
    original_cap = service._MAX_CACHE_ENTRIES
    service._MAX_CACHE_ENTRIES = 3
    try:
        for i in range(3):
            service._cache_set(f"lru{i}", i)
        service._cache_get("lru0")  # touch -- should no longer be the oldest
        service._cache_set("lru3", 3)  # forces one eviction
        assert "lru0" in service._cache, "recently touched entry must survive eviction"
        assert "lru1" not in service._cache, "lru1, never touched again, is now the oldest"
    finally:
        service._MAX_CACHE_ENTRIES = original_cap
        service._cache.clear()


def test_historical_weather_fetches_all_years_concurrently(monkeypatch):
    """5 independent past-year archive calls ran one after another before
    (found in review of the weather flow) -- now via ThreadPoolExecutor.
    5 calls at 0.15s sequentially would take >= 0.75s; concurrently, ~0.15s.
    A generous 0.5s bound catches a regression back to sequential without
    being flaky on a slow CI box."""
    service._cache.clear()
    seen_ranges = []

    def _fake_request_json(url, *, params, headers=None):
        time.sleep(0.15)
        seen_ranges.append((params["start_date"], params["end_date"]))
        return {
            "daily": {
                "temperature_2m_max": [30.0],
                "temperature_2m_min": [20.0],
                "precipitation_sum": [5.0],
                "wind_speed_10m_max": [10.0],
            }
        }

    monkeypatch.setattr(service, "_request_json", _fake_request_json)

    start = time.monotonic()
    result = service.get_historical_weather(18.52, 73.86)
    elapsed = time.monotonic() - start

    assert elapsed < 0.5, f"took {elapsed:.2f}s -- looks sequential, not concurrent"
    assert len(result["years"]) == service.HISTORICAL_YEARS
    assert len(seen_ranges) == service.HISTORICAL_YEARS
    # Order preserved (most-recent-year first), independent of which
    # thread's HTTP call actually finished first.
    years_in_result = [y["year"] for y in result["years"]]
    assert years_in_result == sorted(years_in_result, reverse=True), "years must stay in date_ranges order"
    assert all("error" not in y for y in result["years"])


def test_historical_weather_one_year_failing_does_not_drop_the_others(monkeypatch):
    service._cache.clear()
    call_count = {"n": 0}

    def _fake_request_json(url, *, params, headers=None):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("archive API down for this year")
        return {
            "daily": {
                "temperature_2m_max": [30.0],
                "temperature_2m_min": [20.0],
                "precipitation_sum": [5.0],
                "wind_speed_10m_max": [10.0],
            }
        }

    monkeypatch.setattr(service, "_request_json", _fake_request_json)

    result = service.get_historical_weather(28.6, 77.2)
    assert len(result["years"]) == service.HISTORICAL_YEARS
    ok_years = [y for y in result["years"] if "error" not in y]
    failed_years = [y for y in result["years"] if "error" in y]
    assert len(failed_years) == 1
    assert len(ok_years) == service.HISTORICAL_YEARS - 1
    # The failure in one thread must not corrupt another year's data.
    assert all(y["avg_temp_max"] == 30.0 for y in ok_years)
