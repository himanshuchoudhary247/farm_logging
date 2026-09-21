"""Tests for the ADK-native weather agent (Phase 2 of the orchestration
migration, see /Users/sudhanshu/.claude/plans/elegant-roaming-river.md).

Same convention as test_query_agent_adk.py: google-adk needs Python 3.10+
(only in the project's venv), and no test here makes a live Bedrock/network
call -- only the deterministic, farmer-scoped tool closure is exercised
directly.
"""
from __future__ import annotations

import pytest

pytest.importorskip("google.adk")

from services.weather_alert import adk_agent


def test_weather_tool_falls_back_to_farmer_default_location(monkeypatch):
    monkeypatch.setattr(adk_agent, "get_farmer_by_id", lambda farmer_id: type("F", (), {"weather_location": "583101"})())
    seen = {}

    def fake_get_pincode_data(pin):
        seen["pin"] = pin
        return {"pin": pin, "weather": {}}

    monkeypatch.setattr(adk_agent, "get_pincode_data", fake_get_pincode_data)
    tool = adk_agent._make_get_weather_context_tool("f-default-loc")
    result = tool(location="")
    assert seen["pin"] == "583101"
    assert result["pin"] == "583101"


def test_weather_tool_prefers_explicit_location_over_default(monkeypatch):
    monkeypatch.setattr(adk_agent, "get_farmer_by_id", lambda farmer_id: type("F", (), {"weather_location": "583101"})())
    seen = {}
    monkeypatch.setattr(adk_agent, "get_pincode_data", lambda pin: seen.setdefault("pin", pin) or {"pin": pin})
    tool = adk_agent._make_get_weather_context_tool("f-explicit-loc")
    tool(location="560001")
    assert seen["pin"] == "560001"


def test_weather_tool_returns_no_location_error_when_nothing_available(monkeypatch):
    monkeypatch.setattr(adk_agent, "get_farmer_by_id", lambda farmer_id: None)
    tool = adk_agent._make_get_weather_context_tool("f-no-loc")
    result = tool(location="")
    assert result == {"error": "no_location", "message": "Need a PIN code or place name to check the weather."}


def test_build_weather_agent_wires_model_and_tool():
    agent = adk_agent.build_weather_agent("f-build")
    assert agent.name == "weather_agent"
    assert len(agent.tools) == 1
    assert "bedrock/" in agent.model.model
