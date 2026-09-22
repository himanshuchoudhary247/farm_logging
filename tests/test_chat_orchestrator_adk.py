"""Tests for the ADK-native chat_orchestrator coordinator (Phase 3 of the
orchestration migration, see /Users/sudhanshu/.claude/plans/
elegant-roaming-river.md).

Same importorskip convention as Phases 1/2. The classifier's own live-LLM
call is mocked at the _classify_intent_async boundary -- this tests the
dispatch logic (this migration's actual new code), not ADK's tool-calling
internals, matching this suite's existing convention of mocking at the LLM
boundary rather than the network.
"""
from __future__ import annotations

import pytest

pytest.importorskip("google.adk")

from services.chat_orchestrator import adk_router


def test_sticky_routing_bypasses_classifier_entirely(tmp_path, monkeypatch):
    """A farmer mid-booking must stay routed to appointment_supervisor
    regardless of what the classifier would say -- this is a deterministic
    guard (adk_router.py's own _has_active_booking_draft), not an LLM
    decision, and must never invoke the classifier at all."""
    monkeypatch.setattr(adk_router, "_has_active_booking_draft", lambda farmer_id, session_id: True)
    called = {"classifier": False}

    async def fail_if_called(text):
        called["classifier"] = True
        return "query"

    monkeypatch.setattr(adk_router, "_classify_intent_async", fail_if_called)
    monkeypatch.setattr(
        adk_router._appointment_supervisor, "turn",
        lambda farmer_id, session_id, text, language, include_audio=True: {"response_text": "sticky reply", "state": "COLLECTING", "response_audio_base64": None},
    )
    result = adk_router.route_turn_adk("f-001", "sticky-session", "TAG-001-11")
    assert called["classifier"] is False
    assert result["agent"] == "appointment_supervisor"
    assert result["intent"] is None
    assert result["reply_text"] == "sticky reply"


def test_sticky_registration_routing_bypasses_classifier_entirely(tmp_path, monkeypatch):
    """Same guard as booking's sticky check, for a farmer mid-animal-
    registration -- must route straight back to animal_registration and
    never touch the classifier, and must not regress the booking sticky
    check (both are checked in sequence in route_turn_adk)."""
    monkeypatch.setattr(adk_router, "_has_active_booking_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "_has_active_registration_draft", lambda farmer_id, session_id: True)
    called = {"classifier": False}

    async def fail_if_called(text):
        called["classifier"] = True
        return "query"

    monkeypatch.setattr(adk_router, "_classify_intent_async", fail_if_called)
    monkeypatch.setattr(
        adk_router._animal_registration_supervisor, "turn",
        lambda farmer_id, session_id, text, language, include_audio=True: {"response_text": "sticky registration reply", "state": "COLLECTING", "response_audio_base64": None},
    )
    result = adk_router.route_turn_adk("f-001", "sticky-registration-session", "a goat")
    assert called["classifier"] is False
    assert result["agent"] == "animal_registration"
    assert result["intent"] is None
    assert result["reply_text"] == "sticky registration reply"


def test_classified_add_animal_routes_to_animal_registration(monkeypatch):
    monkeypatch.setattr(adk_router, "_has_active_booking_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "_has_active_registration_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "_classify_intent_async", _async_returning("add_animal"))
    monkeypatch.setattr(
        adk_router._animal_registration_supervisor, "turn",
        lambda farmer_id, session_id, text, language, include_audio=True: {"response_text": "let's register it", "state": "COLLECTING", "response_audio_base64": None},
    )
    result = adk_router.route_turn_adk("f-001", "classify-add-animal", "I got a new goat, add it")
    assert result["agent"] == "animal_registration"
    assert result["intent"] == "add_animal"
    assert result["reply_text"] == "let's register it"


def test_classified_appointment_routes_to_appointment_supervisor(monkeypatch):
    monkeypatch.setattr(adk_router, "_has_active_booking_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "_has_active_registration_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "_classify_intent_async", _async_returning("appointment"))
    monkeypatch.setattr(
        adk_router._appointment_supervisor, "turn",
        lambda farmer_id, session_id, text, language, include_audio=True: {"response_text": "let's book it", "state": "COLLECTING", "response_audio_base64": None},
    )
    result = adk_router.route_turn_adk("f-001", "classify-appt", "I'd like to book an appointment")
    assert result["agent"] == "appointment_supervisor"
    assert result["intent"] == "appointment"
    assert result["reply_text"] == "let's book it"


def test_classified_weather_routes_to_weather_agent(monkeypatch):
    monkeypatch.setattr(adk_router, "_has_active_booking_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "_has_active_registration_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "_classify_intent_async", _async_returning("weather"))
    monkeypatch.setattr(
        adk_router, "process_weather_query_adk",
        lambda text, farmer_id: {"result": {"weather": {}}, "answer": "it will rain"},
    )
    result = adk_router.route_turn_adk("f-001", "classify-weather", "will it rain today")
    assert result["agent"] == "weather_alert"
    assert result["intent"] == "weather"
    assert result["reply_text"] == "it will rain"


def test_classified_query_routes_to_query_agent(monkeypatch):
    monkeypatch.setattr(adk_router, "_has_active_booking_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "_has_active_registration_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "_classify_intent_async", _async_returning("query"))
    monkeypatch.setattr(
        adk_router, "process_query_adk",
        lambda query, farmer_id: {"answer": "you have 53 animals", "sql": "SELECT COUNT(*)...", "data": {}},
    )
    result = adk_router.route_turn_adk("f-001", "classify-query", "how many animals do I have")
    assert result["agent"] == "query_agent"
    assert result["intent"] == "query"
    assert result["reply_text"] == "you have 53 animals"


def test_record_route_tool_rejects_invalid_intent_defaults_to_query():
    """Deterministic backstop: if the model somehow calls record_route with
    something outside the 3 valid categories, never let that propagate as
    a routing key an unbounded downstream branch could choke on."""
    captured: dict[str, str] = {}
    tool = adk_router._make_record_route_tool(captured)
    tool(intent="something_the_model_made_up")
    assert captured["intent"] == "query"


def _async_returning(value):
    async def _inner(text):
        return value

    return _inner
