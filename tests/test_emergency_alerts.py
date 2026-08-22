from __future__ import annotations

import json

import pytest

from services.emergency_alerts import config, insight, scan, storage
from services.emergency_alerts.fetch_kisansuvidha import advisory_digest, _pick_advisory_paragraphs, _clean_text


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")

    @property
    def text(self):
        return self._payload


def _fake_weather_alert_factory(payload):
    def _fake(pin, country_code="in", days=3):
        assert country_code == "in"
        return payload
    return _fake


class TestConfig:
    def test_ten_demo_pins(self):
        assert len(config.DEMO_PINS) == 10
        pins = [p["pin"] for p in config.DEMO_PINS]
        assert len(set(pins)) == 10
        for p in config.DEMO_PINS:
            assert p["pin"].isdigit()
            assert p["district"]
            assert p["state"]
            assert p["language"] in config.LANG_NAMES

    def test_pins_for_state(self):
        rajasthan = config.pins_for_state("Rajasthan")
        assert all(p["state"] == "Rajasthan" for p in rajasthan)
        assert len(rajasthan) >= 1


class TestAdvisoryDigest:
    def test_pick_paragraphs_ignores_script_and_short(self):
        html = (
            "<script>evil()</script>"
            "This is a long agromet advisory paragraph about rainfall for Jaipur district and livestock safety."
            "Short."
        )
        picked = _pick_advisory_paragraphs(_clean_text(html), "Jaipur")
        assert picked
        assert "script" not in picked[0].lower()

    def test_advisory_digest_no_network_failure(self, monkeypatch):
        monkeypatch.setattr(
            "services.emergency_alerts.fetch_kisansuvidha.requests.get",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")),
        )
        digest = advisory_digest("Jaipur", "Rajasthan")
        assert digest["advisory"] is None
        assert "note" in digest


class TestScan:
    def test_scan_pin_produces_alerts_and_digest(self, monkeypatch):
        payload = {
            "risk_level": "high",
            "resolved_location": {"display_name": "Jaipur, Rajasthan, India"},
            "alerts": [
                {
                    "date": "2026-08-13",
                    "level": "high",
                    "reasons": ["Thunderstorm risk", "Heavy rainfall forecast (40.0 mm)"],
                    "weather_code": 95,
                    "rain_mm": 40.0,
                    "wind_kph": 55.0,
                }
            ],
        }
        monkeypatch.setattr(scan, "get_weather_alert", _fake_weather_alert_factory(payload))
        monkeypatch.setattr(
            "services.emergency_alerts.fetch_kisansuvidha.requests.get",
            lambda *a, **k: _FakeResponse("Advisory for Jaipur district: protect livestock from heavy rain."),
        )
        monkeypatch.setattr(insight, "_invoke_bedrock", lambda prompt: None)

        result = scan.scan_pin({"pin": "302001", "district": "Jaipur", "state": "Rajasthan", "language": "hi"}, generate=False)
        assert result["risk_level"] == "high"
        assert result["alerts"][0]["type"] == "Thunderstorm risk"
        assert result["alerts"][0]["pin"] == "302001"
        assert result["alerts"][0]["date"] == "2026-08-13"
        assert result["digest"]["advisory"]
        assert result["digest_insight"] is None  # generate=False

    def test_scan_all_pins_persists_dedupe(self, monkeypatch, tmp_path):
        monkeypatch.setattr(storage, "get_data_dir", lambda: tmp_path)
        monkeypatch.setattr(scan, "get_weather_alert", _fake_weather_alert_factory({
            "risk_level": "low",
            "resolved_location": {"display_name": "X, India"},
            "alerts": [
                {"date": "2026-08-13", "level": "low", "reasons": ["Windy conditions (32.0 km/h)"],
                 "weather_code": 2, "rain_mm": 0.0, "wind_kph": 32.0},
            ],
        }))
        monkeypatch.setattr(
            "services.emergency_alerts.fetch_kisansuvidha.requests.get",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")),
        )
        monkeypatch.setattr(insight, "_invoke_bedrock", lambda prompt: None)
        monkeypatch.setattr(storage, "sleep_seconds", lambda: 0.0)

        out1 = scan.scan_all_pins(generate=False)
        assert out1["run"]["pins_processed"] == 10
        assert out1["run"]["new_alerts"] == 10

        out2 = scan.scan_all_pins(generate=False)
        assert out2["run"]["new_alerts"] == 0  # all deduped

        feed = storage.load_feed()
        assert len(feed["302001"]) == 1
        runs = storage.load_runs()
        assert len(runs) == 2
        assert runs[-1]["pins_failed"] == 0


class TestInsight:
    def test_rule_based_fallback_with_language_note(self):
        text = insight._rule_based_insight(
            {"level": "high", "reasons": ["Heavy rainfall forecast (40.0 mm)"]},
            "Jaipur",
            "hi",
        )
        assert "Jaipur" in text
        assert "Hindi text not generated" in text

    def test_rule_based_english_no_note(self):
        text = insight._rule_based_insight(
            {"level": "low", "reasons": []},
            "Pune",
            "en",
        )
        assert "Pune" in text
        assert "not generated" not in text

    def test_generate_alert_insight_llm_path(self, monkeypatch):
        monkeypatch.setattr(insight, "_invoke_bedrock", lambda prompt: "Shelter animals tonight.")
        out = insight.generate_alert_insight({"level": "high", "reasons": ["Thunderstorm risk"]}, "Jaipur", "hi")
        assert out == "Shelter animals tonight."

    def test_generate_alert_insight_fallback(self, monkeypatch):
        monkeypatch.setattr(insight, "_invoke_bedrock", lambda prompt: None)
        out = insight.generate_alert_insight({"level": "high", "reasons": ["Thunderstorm risk"]}, "Jaipur", "en")
        assert "Jaipur" in out
        assert "shelter" in out.lower()

    def test_digest_insight_empty(self, monkeypatch):
        monkeypatch.setattr(insight, "_invoke_bedrock", lambda prompt: None)
        out = insight.generate_digest_insight("", "Jaipur", "hi")
        assert "Jaipur" in out
