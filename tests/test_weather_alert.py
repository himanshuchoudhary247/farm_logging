from __future__ import annotations

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
