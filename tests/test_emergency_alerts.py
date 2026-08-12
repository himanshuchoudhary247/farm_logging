from __future__ import annotations

import json

import pytest

from services.emergency_alerts import config, insight, scan, storage
from services.emergency_alerts.fetch_kisansuvidha import _pick_advisory_paragraphs, _clean_text
from services.emergency_alerts.fetch_icar import advisory_digest as _icar_digest


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


class TestFetchers:
    def test_pick_paragraphs_ignores_script_and_short(self):
        html = (
            "<script>evil()</script>"
            "This is a long agromet advisory paragraph about rainfall for Jaipur district and livestock safety."
            "Short."
        )
        picked = _pick_advisory_paragraphs(_clean_text(html), "Jaipur")
        assert picked
        assert "script" not in picked[0].lower()

    def test_kisan_suvidha_network_failure_degrades(self, monkeypatch):
        monkeypatch.setattr(
            "services.emergency_alerts.fetch_kisansuvidha.requests.get",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")),
        )
        from services.emergency_alerts.fetch_kisansuvidha import advisory_digest as _ks_digest
        digest = _ks_digest("Jaipur", "Rajasthan")
        assert digest["advisory"] is None
        assert "note" in digest

    def test_icar_advisory_returns_data(self):
        digest = _icar_digest("Jaipur", "Rajasthan", "hi")
        assert digest["source"] == "ICAR-NIVEDI NADRES"
        # Jaipur/Rajasthan has active diseases per catalogue
        assert digest.get("advisory") is not None
        assert len(digest.get("active_diseases", [])) > 0

    def test_imd_unavailable_degrades_gracefully(self, monkeypatch):
        monkeypatch.setattr(
            "services.emergency_alerts.fetch_imd.requests.get",
            lambda *a, **k: _FakeResponse("{}", status_code=404),
        )
        from services.emergency_alerts.fetch_imd import fetch_imd_warnings
        result = fetch_imd_warnings("Jaipur", "Rajasthan")
        assert result["status"] == "unavailable"
        assert result["warnings"] == []

    def test_wttr_severe_weather_classified(self, monkeypatch):
        from services.emergency_alerts.fetch_wttr import fetch_wttr

        class _FakeResp:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {"current_condition": [{"weatherCode": "302", "temp_C": "20", "weatherDesc": [{"value": "Heavy rain"}]}]}

        monkeypatch.setattr("services.emergency_alerts.fetch_wttr.requests.get", lambda *a, **k: _FakeResp())
        result = fetch_wttr("302001", "Jaipur", "Rajasthan")
        assert result["status"] == "ok"
        assert result["alert"] is not None
        assert result["alert"]["level"] == "high"

    def test_wttr_clear_returns_no_alert(self, monkeypatch):
        from services.emergency_alerts.fetch_wttr import fetch_wttr

        class _FakeResp:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {"current_condition": [{"weatherCode": "113", "temp_C": "30", "weatherDesc": [{"value": "Clear"}]}]}

        monkeypatch.setattr("services.emergency_alerts.fetch_wttr.requests.get", lambda *a, **k: _FakeResp())
        result = fetch_wttr("302001", "Jaipur", "Rajasthan")
        assert result["status"] == "ok"
        assert result["alert"] is None


class TestScan:
    def test_scan_pin_produces_alerts_from_all_sources(self, monkeypatch):
        monkeypatch.setattr(scan, "get_weather_alert", _fake_weather_alert_factory({
            "risk_level": "high",
            "resolved_location": {"display_name": "Jaipur, Rajasthan, India"},
            "alerts": [
                {"date": "2026-08-13", "level": "high",
                 "reasons": ["Thunderstorm risk", "Heavy rainfall forecast (40.0 mm)"],
                 "weather_code": 95, "rain_mm": 40.0, "wind_kph": 55.0},
            ],
        }))
        monkeypatch.setattr(scan, "_icar_digest", lambda d, s, l: {
            "source": "ICAR-NIVEDI NADRES", "district": d, "state": s,
            "advisory": "Bluetongue risk in monsoon. Vaccinate sheep.",
            "active_diseases": ["Bluetongue"],
        })
        monkeypatch.setattr(scan, "_fetch_imd", lambda d, s: {
            "source": "IMD", "status": "ok",
            "warnings": [{"title": "Heavy rain warning Jaipur", "description": "test"}],
        })
        monkeypatch.setattr(scan, "_fetch_wttr", lambda p, d, s: {
            "source": "wttr.in", "status": "ok",
            "alert": {"level": "high", "type": "Heavy rain", "weather_code": "302"},
        })
        monkeypatch.setattr(insight, "_invoke_bedrock", lambda prompt: None)

        result = scan.scan_pin({"pin": "302001", "district": "Jaipur", "state": "Rajasthan", "language": "hi"}, generate=False)
        assert result["risk_level"] == "high"
        # Open-Meteo alert
        om = [a for a in result["alerts"] if a["source"] == "Open-Meteo forecast"]
        assert len(om) == 1
        assert om[0]["type"] == "Thunderstorm risk"
        assert om[0]["date"] == "2026-08-13"
        # ICAR disease advisory
        icar = [a for a in result["alerts"] if a["source"] == "ICAR-NIVEDI NADRES"]
        assert len(icar) == 1
        assert icar[0]["type"] == "ICAR disease advisory"
        # IMD warning
        imd = [a for a in result["alerts"] if a["source"] == "IMD"]
        assert len(imd) == 1
        assert imd[0]["level"] == "high"
        # wttr.in alert
        wttr = [a for a in result["alerts"] if a["source"] == "wttr.in"]
        assert len(wttr) == 1
        assert wttr[0]["level"] == "high"
        # Source status
        assert result["sources"]["imd"] == "ok"
        assert result["sources"]["wttr_in"] == "ok"

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
        monkeypatch.setattr(scan, "_icar_digest", lambda d, s, l: {"advisory": None, "note": "none"})
        monkeypatch.setattr(scan, "_fetch_imd", lambda d, s: {"status": "unavailable", "warnings": []})
        monkeypatch.setattr(scan, "_fetch_wttr", lambda p, d, s: {"status": "unavailable", "alert": None})
        monkeypatch.setattr(insight, "_invoke_bedrock", lambda prompt: None)
        monkeypatch.setattr(storage, "sleep_seconds", lambda: 0.0)

        out1 = scan.scan_all_pins(generate=False)
        assert out1["run"]["pins_processed"] == 10
        assert out1["run"]["new_alerts"] == 10  # 1 open-meteo alert per pin

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
            "Jaipur", "hi",
        )
        assert "Jaipur" in text
        assert "Hindi text not generated" in text

    def test_rule_based_english_no_note(self):
        text = insight._rule_based_insight(
            {"level": "low", "reasons": []}, "Pune", "en",
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