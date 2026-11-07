"""Tests for the shared mid-draft/mid-wait off-topic escape check
(services/chat_orchestrator/mid_draft_escape.py), reused by
appointment_supervisor and animal_registration. Same importorskip
convention and LLM-boundary mocking style as test_chat_orchestrator_adk.py.
"""
from __future__ import annotations

import uuid

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


def test_classifier_failure_is_swallowed_not_raised(monkeypatch):
    """Real bug, found in deep review: this probe now runs on the single
    most common "didn't understand" turn shape in both supervisors (any
    COLLECTING turn that extracts nothing). A transient Bedrock/ADK error
    must degrade to "not a genuine switch", not crash the whole turn --
    on WhatsApp specifically, an uncaught exception here left the farmer
    with no reply at all."""
    async def boom(text):
        raise RuntimeError("Bedrock throttled")
    monkeypatch.setattr(adk_router, "_classify_intent_async", boom)
    assert mid_draft_escape.try_switch("umm", "f-001", "s1", "en-IN") is None


def test_dispatch_failure_is_swallowed_not_raised(monkeypatch):
    monkeypatch.setattr(adk_router, "_classify_intent_async", _classify_as("query"))

    def boom(text, farmer_id, session_id=None, app_language=None):
        raise RuntimeError("query_agent down")
    monkeypatch.setattr(mid_draft_escape, "process_query_adk", boom)
    assert mid_draft_escape.try_switch("how many animals do I have", "f-001", "s1", "en-IN") is None


# The app sends a UUID session id; the probe must never run in it.
_REAL_SESSION = "24666232-6a23-4471-9fef-0c89e366ddbe"


@pytest.mark.parametrize("answer,sql,data", [
    ("You have 12 animals registered.", "SELECT COUNT(*) ...", [{"count": 12}]),  # accepted
    (None, None, None),                                                         # thrown away
], ids=["accepted", "rejected"])
def test_query_probe_never_runs_in_the_farmers_own_session(monkeypatch, answer, sql, data):
    seen = []
    monkeypatch.setattr(adk_router, "_classify_intent_async", _classify_as("query"))

    def fake(text, farmer_id, session_id=None, app_language=None):
        seen.append(session_id)
        return {"answer": answer, "sql": sql, "data": data}
    monkeypatch.setattr(mid_draft_escape, "process_query_adk", fake)
    mid_draft_escape.try_switch("how many animals do I have", "f-001", _REAL_SESSION, "hi-IN")
    assert seen == [mid_draft_escape._probe_session_id(_REAL_SESSION)]
    assert seen[0] != _REAL_SESSION


@pytest.mark.parametrize("answer", ["Expect light rain tomorrow.", None], ids=["accepted", "rejected"])
def test_weather_probe_never_runs_in_the_farmers_own_session(monkeypatch, answer):
    seen = []
    monkeypatch.setattr(adk_router, "_classify_intent_async", _classify_as("weather"))

    def fake(text, farmer_id, session_id=None):
        seen.append(session_id)
        return {"answer": answer}
    monkeypatch.setattr(mid_draft_escape, "process_weather_query_adk", fake)
    mid_draft_escape.try_switch("will it rain tomorrow", "f-001", _REAL_SESSION, "en-IN")
    assert seen == [mid_draft_escape._probe_session_id(_REAL_SESSION)]
    assert seen[0] != _REAL_SESSION


def test_one_probe_session_per_chat_not_one_per_probe(monkeypatch):
    """Repeated probes in one chat reuse one probe session, so they do not
    pile up; two chats never share one."""
    seen = []
    monkeypatch.setattr(adk_router, "_classify_intent_async", _classify_as("weather"))
    monkeypatch.setattr(mid_draft_escape, "process_weather_query_adk",
                        lambda text, farmer_id, session_id=None: seen.append(session_id) or {"answer": None})
    for _ in range(3):
        mid_draft_escape.try_switch("umm", "f-001", "chat-a", "en-IN")
    mid_draft_escape.try_switch("umm", "f-001", "chat-b", "en-IN")
    probe_a, probe_b = (mid_draft_escape._probe_session_id(s) for s in ("chat-a", "chat-b"))
    assert seen == [probe_a] * 3 + [probe_b]
    assert probe_a != probe_b


@pytest.mark.parametrize("session_id", ["", "   ", None])
def test_no_chat_session_keeps_the_one_off_session(monkeypatch, session_id):
    seen = []
    monkeypatch.setattr(adk_router, "_classify_intent_async", _classify_as("weather"))
    monkeypatch.setattr(mid_draft_escape, "process_weather_query_adk",
                        lambda text, farmer_id, session_id=None: seen.append(session_id) or {"answer": "ok"})
    assert mid_draft_escape.try_switch("will it rain", "f-001", session_id, "en-IN") == {"intent": "weather", "answer": "ok"}
    assert seen == [None]


def test_probe_session_cannot_be_another_real_chat():
    """A real chat id can be any text from the app, even one that looks
    like a probe id; the probe of one chat must never be another chat."""
    probe = mid_draft_escape._probe_session_id
    for real in ("abc", "abc:probe", _REAL_SESSION, probe("abc")):
        assert probe(real) != real
    assert probe("abc") != "abc:probe"
    assert probe("abc") != probe("abc:probe")
    assert probe("abc") == probe(" abc "), "same chat, same probe session"


@pytest.mark.parametrize("session_id", [12345, uuid.UUID(_REAL_SESSION), {"id": "s1"}], ids=["int", "uuid", "dict"])
def test_a_non_text_session_id_still_probes(monkeypatch, session_id):
    seen = []
    monkeypatch.setattr(adk_router, "_classify_intent_async", _classify_as("weather"))
    monkeypatch.setattr(mid_draft_escape, "process_weather_query_adk",
                        lambda text, farmer_id, session_id=None: seen.append(session_id) or {"answer": "ok"})
    assert mid_draft_escape.try_switch("will it rain", "f-001", session_id, "en-IN") == {"intent": "weather", "answer": "ok"}
    assert seen == [mid_draft_escape._probe_session_id(str(session_id))]

