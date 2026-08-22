from __future__ import annotations

import json
import os
import time

from services.cache_refresh import service as cache_service


def _write_yaml(path, content):
    path.write_text(content, encoding="utf-8")


def test_refresh_all_pins_writes_cached_alerts(tmp_path, monkeypatch):
    profiles_path = tmp_path / "pins.yaml"
    settings_path = tmp_path / "settings.yaml"
    cache_root = tmp_path / "cache"

    _write_yaml(
        profiles_path,
        """
pins:
  - pin: "123456"
    name: "Test Cluster"
    district: "Demo"
    state: "TestState"
    default_animals:
      - type: "sheep"
        count: 50
""".strip()
    )
    _write_yaml(
        settings_path,
        """
weather:
  refresh_hours: 2
  alert_days: 2
  seasonal_days: 5

market:
  refresh_hours: 6
""".strip()
    )

    fake_weather = {
        "risk_level": "medium",
        "summary": "Rain and heat alerts",
        "advisories": ["Check sheds"],
        "alerts": [
            {
                "date": "2026-08-15",
                "level": "high",
                "heat_stress_level": "high",
                "heat_stress_reason": "THI 86",
            }
        ],
        "forecast_days": [
            {
                "date": "2026-08-15",
                "thi": 86.2,
                "heat_stress_level": "high",
            }
        ],
        "resolved_location": {"display_name": "Demo", "state": "TestState"},
    }
    fake_seasonal = {"historical": {"summary": {"avg_high_temp": 34}}}
    fake_feed = {
        "state": "TestState",
        "latest_fetched_at": "2026-08-15T00:00:00+00:00",
        "commodities": [{"commodity": "Maize", "modal_price_avg": 1800, "modal_price_min": 1700, "modal_price_max": 1900}],
    }

    monkeypatch.setattr(cache_service.weather_service, "get_weather_alert", lambda pin, days=3: fake_weather)
    monkeypatch.setattr(cache_service.weather_service, "get_seasonal_advisory_data", lambda pin, days=7: fake_seasonal)
    monkeypatch.setattr(cache_service, "get_feed_price_snapshot", lambda state: fake_feed)

    results = cache_service.refresh_all_pins(
        pin_profiles_path=profiles_path,
        cache_settings_path=settings_path,
        cache_root=cache_root,
    )

    assert results and results[0]["pin"] == "123456"
    general_path = cache_root / "123456" / "general_alert.json"
    assert general_path.exists()
    payload = json.loads(general_path.read_text(encoding="utf-8"))
    assert payload["heat"]["level"] == "high"
    assert payload["feed_market"]["commodities"][0]["commodity"] == "Maize"

    profiles = cache_service.load_pin_profiles(profiles_path)
    settings = cache_service.load_cache_settings(settings_path)
    ensured = cache_service.ensure_general_alert(
        "123456",
        settings,
        profiles,
        cache_root=cache_root,
    )
    assert ensured["pin"] == "123456"


def test_cache_file_freshness_uses_each_api_ttl(tmp_path):
    path = tmp_path / "weather.json"
    path.write_text("{}", encoding="utf-8")
    now = cache_service.datetime.now(cache_service.timezone.utc)

    assert cache_service._cache_file_is_fresh(path, 2, now)

    old = time.time() - (3 * 60 * 60)
    os.utime(path, (old, old))
    assert not cache_service._cache_file_is_fresh(path, 2, now)
    assert cache_service._cache_file_is_fresh(path, 6, now)


def test_refresh_can_target_one_api_service(tmp_path, monkeypatch):
    profile = cache_service.PinProfile(
        pin="123456",
        name="Test Cluster",
        district="Demo",
        state="TestState",
        default_animals=[],
        farm_notes=[],
        raw={"pin": "123456"},
    )
    settings = {
        "weather": {"refresh_hours": 2, "alert_days": 2, "seasonal_days": 5},
        "market": {"refresh_hours": 6},
    }
    fake_feed = {"state": "TestState", "commodities": []}

    monkeypatch.setattr(
        cache_service,
        "get_feed_price_snapshot",
        lambda state: fake_feed,
    )
    monkeypatch.setattr(
        cache_service.weather_service,
        "get_weather_alert",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("weather should not run")),
    )
    monkeypatch.setattr(
        cache_service.weather_service,
        "get_seasonal_advisory_data",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("seasonal should not run")),
    )

    result = cache_service.refresh_pin_cache(
        profile,
        settings,
        cache_root=tmp_path,
        services=["feed_prices"],
    )

    assert result["feed_market"]["state"] == "TestState"
    assert (tmp_path / "123456" / "feed_prices.json").exists()
