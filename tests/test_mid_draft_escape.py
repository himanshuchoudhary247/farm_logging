"""Tests for the shared mid-draft/mid-wait off-topic escape check
(services/chat_orchestrator/mid_draft_escape.py), reused by
appointment_supervisor and animal_registration. Same importorskip
convention and LLM-boundary mocking style as test_chat_orchestrator_adk.py.
"""
from __future__ import annotations

import pytest

pytest.importorskip("google.adk")

from services.chat_orchestrator import adk_router, mid_draft_escape


def _classify_as(intent):
    async def fake(text):
        return intent
    return fake


def test_query_intent_with_genuine_sql_and_data_is_accepted(monkeypatch):
    monkeypatch.setattr(adk_router, "_classify_intent_async", _classify_as("query"))
    monkeypatch.setattr(
        mid_draft_escape, "process_query_adk",
        lambda text, farmer_id, session_id=None, app_language=None: {
            "answer": "You have 12 animals registered.", "sql": "SELECT COUNT(*) ...", "data": [{"count": 12}],
        },
    )
    result = mid_draft_escape.try_switch("how many animals do I have", "f-001", "s1", "en-IN")
    assert result == {"intent": "query", "answer": "You have 12 animals registered."}


def test_query_intent_without_genuine_data_is_rejected(monkeypatch):
    """The classifier calling it "query" is not enough proof on its own --
    this is exactly the case a vague off-topic phrase ("any animal with
    ram") gets misclassified, or where query_agent genuinely has no
    SQL/data answer for the text. Must not be treated as a real switch."""
    monkeypatch.setattr(adk_router, "_classify_intent_async", _classify_as("query"))
    monkeypatch.setattr(
        mid_draft_escape, "process_query_adk",
        lambda text, farmer_id, session_id=None, app_language=None: {"answer": None, "sql": None, "data": None},
    )
    assert mid_draft_escape.try_switch("any animal with ram", "f-001", "s1", "en-IN") is None


def test_weather_intent_with_an_answer_is_accepted(monkeypatch):
    monkeypatch.setattr(adk_router, "_classify_intent_async", _classify_as("weather"))
    monkeypatch.setattr(
        mid_draft_escape, "process_weather_query_adk",
        lambda text, farmer_id, session_id=None: {"answer": "Expect light rain tomorrow."},
    )
    result = mid_draft_escape.try_switch("will it rain tomorrow", "f-001", "s1", "en-IN")
    assert result == {"intent": "weather", "answer": "Expect light rain tomorrow."}


def test_weather_intent_with_no_answer_is_rejected(monkeypatch):
    monkeypatch.setattr(adk_router, "_classify_intent_async", _classify_as("weather"))
    monkeypatch.setattr(
        mid_draft_escape, "process_weather_query_adk",
        lambda text, farmer_id, session_id=None: {"answer": None},
    )
    assert mid_draft_escape.try_switch("some vague text", "f-001", "s1", "en-IN") is None


@pytest.mark.parametrize("intent", ["appointment", "add_animal"])
def test_other_intents_are_never_treated_as_a_switch(monkeypatch, intent):
    """Scoped deliberately to query + weather only (read-only/stateless to
    dispatch) -- switching mid-draft into a SECOND stateful flow is an
    explicitly separate, later decision, not this fix's job."""
    monkeypatch.setattr(adk_router, "_classify_intent_async", _classify_as(intent))
    assert mid_draft_escape.try_switch("register a goat instead", "f-001", "s1", "en-IN") is None
