"""Weather agent reuses the chat's ADK session, so a follow-up knows the
place given earlier in the chat. Seen live: "बारिश होगी क्या?" right after
"411001 में मौसम कैसा है?" asked for the PIN again."""
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("google.adk")

from google.adk.sessions import InMemorySessionService

from services.chat_orchestrator import adk_router
from services.weather_alert import adk_agent


class _CountingSessions(InMemorySessionService):
    def __init__(self):
        super().__init__()
        self.deleted = 0

    async def delete_session(self, **kwargs):
        self.deleted += 1
        return await super().delete_session(**kwargs)


def _session(service, user_id, session_id):
    return asyncio.run(adk_agent._get_or_create_session(service, user_id, session_id))


def test_same_chat_gets_the_same_session():
    service = InMemorySessionService()
    first = _session(service, "farmer-f1", "chat-1")
    second = _session(service, "farmer-f1", "chat-1")
    assert first.id == second.id == "chat-1"


def test_no_session_id_gets_a_fresh_session_each_time():
    service = InMemorySessionService()
    assert _session(service, "farmer-f1", None).id != _session(service, "farmer-f1", None).id


def test_another_farmer_never_gets_this_farmers_session():
    service = InMemorySessionService()
    _session(service, "farmer-f1", "chat-1")
    other = _session(service, "farmer-f2", "chat-1")
    assert other.user_id == "farmer-f2"
    kept = asyncio.run(service.get_session(app_name=adk_agent._APP_NAME, user_id="farmer-f1", session_id="chat-1"))
    assert kept is not None


def test_long_session_is_restarted(monkeypatch):
    monkeypatch.setattr(adk_agent, "_MAX_SESSION_EVENTS", -1)
    service = _CountingSessions()
    _session(service, "farmer-f1", "chat-1")
    again = _session(service, "farmer-f1", "chat-1")
    assert service.deleted == 1
    assert again.id == "chat-1"


def test_weather_sessions_are_kept_apart_from_query_sessions():
    assert adk_agent._APP_NAME == "farmer_chat_weather_agent"


def test_process_weather_query_passes_the_session_on(monkeypatch):
    seen = {}

    async def fake_run(query, farmer_id, session_id=None):
        seen.update(query=query, farmer_id=farmer_id, session_id=session_id)
        return {"result": {}, "answer": "", "speech_text": ""}

    monkeypatch.setattr(adk_agent, "_run_weather_async", fake_run)
    adk_agent.process_weather_query_adk("बारिश होगी क्या?", "f1", session_id="chat-1")
    assert seen == {"query": "बारिश होगी क्या?", "farmer_id": "f1", "session_id": "chat-1"}


def test_router_sends_the_chat_session_to_weather(monkeypatch):
    seen = {}

    def fake_weather(text, farmer_id, session_id=None):
        seen["session_id"] = session_id
        return {"result": {"weather": {}}, "answer": "ok", "speech_text": None}

    monkeypatch.setattr(adk_router, "process_weather_query_adk", fake_weather)
    monkeypatch.setattr(adk_router, "update_session", lambda key, data: None)
    adk_router._run_weather("f-1", "chat-1", "बारिश होगी क्या?", "weather", False, "hi-IN")
    assert seen["session_id"] == "chat-1"
