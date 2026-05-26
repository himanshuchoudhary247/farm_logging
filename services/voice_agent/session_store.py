from typing import Any, Dict


_sessions: Dict[str, Dict[str, Any]] = {}


def get_session(session_id: str) -> Dict[str, Any]:
    return _sessions.setdefault(
        session_id,
        {
            "intent": None,
            "entities": {},
            "pending_questions": [],
        },
    )


def update_session(session_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    session = get_session(session_id)
    session.update(data)
    return session


def clear_session(session_id: str) -> None:
    _sessions.pop(session_id, None)
