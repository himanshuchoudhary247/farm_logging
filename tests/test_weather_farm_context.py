"""Weather chat tool adds this farmer's own animals and issues, without
touching the shared cached weather data."""
from types import SimpleNamespace

from services.weather_alert import adk_agent

WEATHER = {"pin": "411001", "weather": {"summary": "Hot", "risk_level": "medium"}}


def _goat(age):
    return SimpleNamespace(species="goat", breed="Osmanabadi", sex="female", age_years=age, birth_date=None, status="active")


def _log(issue):
    return SimpleNamespace(issue=issue, recorded_at="2026-10-01", id="h1")


def _tool(monkeypatch, animals, logs, shared=None):
    shared = shared if shared is not None else dict(WEATHER)
    monkeypatch.setattr(adk_agent, "get_pincode_data", lambda loc: shared)
    monkeypatch.setattr(adk_agent, "animals_for_farmer", lambda fid: animals)
    monkeypatch.setattr(adk_agent, "health_logs_for_farmer", lambda fid: logs)
    return adk_agent._make_get_weather_context_tool("f-1"), shared


def test_tool_adds_this_farmers_animals_and_issues(monkeypatch):
    tool, _ = _tool(monkeypatch, [_goat(0.5), _goat(3)], [_log("Fever")])
    result = tool("411001")
    assert result["weather"]["summary"] == "Hot"
    farm = result["your_farm"]
    assert farm["livestock"][0]["type"] == "goat"
    assert farm["livestock"][0]["count"] == 2
    assert farm["livestock"][0]["under_1_year"] == 1
    assert farm["recent_health_issues"] == ["Fever"]


def test_shared_cached_weather_is_not_changed(monkeypatch):
    shared = dict(WEATHER)
    tool, shared = _tool(monkeypatch, [_goat(2)], [], shared=shared)
    tool("411001")
    assert "your_farm" not in shared


def test_no_animals_or_issues_gives_plain_weather(monkeypatch):
    tool, _ = _tool(monkeypatch, [], [])
    assert "your_farm" not in tool("411001")


def test_storage_error_still_gives_weather(monkeypatch):
    tool, _ = _tool(monkeypatch, [], [])

    def boom(fid):
        raise OSError("disk")

    monkeypatch.setattr(adk_agent, "animals_for_farmer", boom)
    result = tool("411001")
    assert result["weather"]["summary"] == "Hot"
    assert "your_farm" not in result
    