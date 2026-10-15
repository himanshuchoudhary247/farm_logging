"""Session reuse for the ADK query agent: a chat's session keeps its history
across turns, farmers never share a session, and callers that pass no
session_id keep the old one-off behaviour."""
import asyncio
import threading

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


def test_concurrent_turns_for_same_session_do_not_race(monkeypatch):
    """Whole-dev-branch review finding: get/delete/create on a shared
    InMemorySessionService had no per-session lock. Two concurrent turns
    for the same user_id+session_id (e.g. a duplicate webhook delivery)
    could race delete_session/create_session -- one turn's delete could
    land between the other's get and create, so its create then collides
    with (or clobbers) the one just made. Forces the restart branch for
    every call (_MAX_SESSION_EVENTS=-1) and widens delete_session so a
    second thread's call overlaps if the lock does not serialize them."""
    monkeypatch.setattr(adk_agent, "_MAX_SESSION_EVENTS", -1)

    active = {"n": 0, "max": 0}
    guard = threading.Lock()

    class _SlowSessions(InMemorySessionService):
        async def delete_session(self, **kwargs):
            with guard:
                active["n"] += 1
                active["max"] = max(active["max"], active["n"])
            await asyncio.sleep(0.05)
            result = await super().delete_session(**kwargs)
            with guard:
                active["n"] -= 1
            return result

    service = _SlowSessions()
    _run(adk_agent._get_or_create_session(service, "farmer-f-001", "chat-1"))

    errors = []

    def worker():
        try:
            _run(adk_agent._get_or_create_session(service, "farmer-f-001", "chat-1"))
        except Exception as exc:  # pragma: no cover - failure path under test
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"concurrent turns for the same session must not raise: {errors}"
    assert active["max"] == 1, "per-session lock must serialize delete/create, not let them overlap"


def test_in_memory_service_is_shared_when_no_db_url(monkeypatch):
    monkeypatch.delenv("ADK_SESSION_DB_URL", raising=False)
    assert adk_agent._session_service() is adk_agent._session_service()


def test_db_mode_uses_nullpool():
    """Finding 8 of the PR #28 review: no connection pool per call."""
    from sqlalchemy.pool import NullPool
    assert adk_agent._db_engine_kwargs("postgresql+asyncpg://user:pw@host/db") == {"poolclass": NullPool}
    assert adk_agent._db_engine_kwargs("sqlite+aiosqlite:///./data/adk_sessions.db") == {"poolclass": NullPool}


def test_in_memory_sqlite_keeps_adk_default_pool():
    assert adk_agent._db_engine_kwargs("sqlite+aiosqlite:///:memory:") == {}


def test_bad_url_is_left_for_adk_to_report():
    assert adk_agent._db_engine_kwargs("not a url") == {}


def test_db_session_is_found_by_the_next_call(monkeypatch, tmp_path):
    """Real SQLite file: a session created in one call is found by the
    next call's brand-new service, i.e. memory lives in the database."""
    db_url = f"sqlite+aiosqlite:///{(tmp_path / 'adk_sessions.db').as_posix()}"
    monkeypatch.setenv("ADK_SESSION_DB_URL", db_url)
    first = adk_agent._session_service()
    _run(adk_agent._get_or_create_session(first, "farmer-f-001", "chat-1"))
    second = adk_agent._session_service()
    assert second is not first
    session = _run(second.get_session(app_name=APP, user_id="farmer-f-001", session_id="chat-1"))
    assert session is not None

