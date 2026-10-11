"""Weather chat tool adds this farmer's own animals and issues, without
touching the shared cached weather data."""
from types import SimpleNamespace

import pytest

from services.weather_alert import adk_agent

WEATHER = {"pin": "411001", "weather": {"summary": "Hot", "risk_level": "medium"}}


@pytest.fixture(autouse=True)
def _clear_farm_context_cache():
    """_farm_context caches per farmer_id (see adk_agent.py); every test
    here uses the same farmer_id "f-1" with different mocked data, so a
    stale entry from a previous test would otherwise leak in."""
    adk_agent._farm_context_cache.clear()
    yield
    adk_agent._farm_context_cache.clear()


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


def test_farm_context_is_cached_within_ttl(monkeypatch):
    """A farmer's own animals/health logs change far less often than they
    ask weather questions -- recomputing on every turn (e.g. the sticky
    "still waiting for a PIN" re-ask in adk_router.py) hit storage for no
    reason. Found in review of the weather flow."""
    calls = {"n": 0}

    def counting_animals(fid):
        calls["n"] += 1
        return [_goat(2)]

    monkeypatch.setattr(adk_agent, "animals_for_farmer", counting_animals)
    monkeypatch.setattr(adk_agent, "health_logs_for_farmer", lambda fid: [])

    first = adk_agent._farm_context("f-1")
    second = adk_agent._farm_context("f-1")
    assert first == second
    assert calls["n"] == 1, "second call within the TTL must hit the cache, not storage"


def test_farm_context_cache_expires_after_ttl(monkeypatch):
    calls = {"n": 0}

    def counting_animals(fid):
        calls["n"] += 1
        return [_goat(2)]

    monkeypatch.setattr(adk_agent, "animals_for_farmer", counting_animals)
    monkeypatch.setattr(adk_agent, "health_logs_for_farmer", lambda fid: [])

    adk_agent._farm_context("f-1")
    cached_at, value = adk_agent._farm_context_cache["f-1"]
    adk_agent._farm_context_cache["f-1"] = (cached_at - adk_agent._FARM_CONTEXT_TTL_SEC - 1, value)
    adk_agent._farm_context("f-1")
    assert calls["n"] == 2, "must refetch once the cached entry is older than the TTL"


def test_farm_context_cache_is_scoped_per_farmer(monkeypatch):
    animals_by_farmer = {"f-1": [_goat(2)], "f-2": []}
    monkeypatch.setattr(adk_agent, "animals_for_farmer", lambda fid: animals_by_farmer[fid])
    monkeypatch.setattr(adk_agent, "health_logs_for_farmer", lambda fid: [])

    assert adk_agent._farm_context("f-1") is not None
    assert adk_agent._farm_context("f-2") is None, "one farmer's cached context must never leak to another"
    