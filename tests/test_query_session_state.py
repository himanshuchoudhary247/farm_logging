"""Session reuse for the ADK query agent: a chat's session keeps its history
across turns, farmers never share a session, and callers that pass no
session_id keep the old one-off behaviour."""
import asyncio

from google.adk.sessions import InMemorySessionService

from services.query_agent import adk_agent

APP = adk_agent._APP_NAME


def _run(coro):
    return asyncio.run(coro)


def test_same_session_id_reuses_the_session():
    service = InMemorySessionService()
    first = _run(adk_agent._get_or_create_session(service, "farmer-f-001", "chat-1"))
    second = _run(adk_agent._get_or_create_session(service, "farmer-f-001", "chat-1"))
    assert first.id == second.id == "chat-1"


def test_state_is_kept_for_the_same_chat():
    service = InMemorySessionService()
    _run(service.create_session(app_name=APP, user_id="farmer-f-001", session_id="chat-1",
                                state={"last_query_answer": "You have 12 goats."}))
    session = _run(adk_agent._get_or_create_session(service, "farmer-f-001", "chat-1"))
    assert session.state.get("last_query_answer") == "You have 12 goats."


def test_other_farmer_with_same_session_id_gets_a_separate_session():
    service = InMemorySessionService()
    _run(service.create_session(app_name=APP, user_id="farmer-f-001", session_id="chat-1",
                                state={"last_query_answer": "secret"}))
    other = _run(adk_agent._get_or_create_session(service, "farmer-f-002", "chat-1"))
    assert "last_query_answer" not in other.state


def test_no_session_id_creates_a_new_session_every_time():
    service = InMemorySessionService()
    a = _run(adk_agent._get_or_create_session(service, "farmer-f-001", None))
    b = _run(adk_agent._get_or_create_session(service, "farmer-f-001", None))
    assert a.id != b.id


def test_session_over_the_event_cap_is_restarted(monkeypatch):
    monkeypatch.setattr(adk_agent, "_MAX_SESSION_EVENTS", -1)
    service = InMemorySessionService()
    _run(service.create_session(app_name=APP, user_id="farmer-f-001", session_id="chat-1",
                                state={"last_query_answer": "old"}))
    session = _run(adk_agent._get_or_create_session(service, "farmer-f-001", "chat-1"))
    assert session.id == "chat-1"
    assert "last_query_answer" not in session.state


def test_in_memory_service_is_shared_when_no_db_url(monkeypatch):
    monkeypatch.delenv("ADK_SESSION_DB_URL", raising=False)
    assert adk_agent._session_service() is adk_agent._session_service()