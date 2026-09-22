"""Voice-turn session state.

Before 2026-09-13 this was a process-local dict — any uvicorn restart lost
every in-flight booking, and multi-worker deployments couldn't share
session state at all. This version persists each session as a JSON file
under data/voice_sessions/<sha1(session_id)>.json guarded by the same
FileLock pattern appointment_supervisor already uses for its intake
drafts, so sessions survive restarts and (when the deployment goes
multi-worker) worker boundaries.

Interface is unchanged (get_session / update_session / clear_session)
so orchestrator.py needs no edits.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Dict

from filelock import FileLock


_DEFAULT_SESSION: Dict[str, Any] = {
    "intent": None,
    "entities": {},
    "pending_questions": [],
}

_MEMORY_FALLBACK: Dict[str, Dict[str, Any]] = {}
_MEMORY_LOCK = threading.Lock()


def _sessions_dir() -> Path:
    """Storage directory. Env override for tests; otherwise data/voice_sessions
    under whatever get_data_dir resolves to (test suites monkeypatch that)."""
    override = os.getenv("VOICE_SESSIONS_DIR")
    if override:
        return Path(override)
    from storage import get_data_dir
    return get_data_dir() / "voice_sessions"


def _session_path(session_id: str) -> Path:
    """Filesystem path for a session. Hashing keeps arbitrary session id
    contents (any script, any punctuation, any length) safe as a filename."""
    safe = hashlib.sha1(session_id.encode("utf-8")).hexdigest()
    return _sessions_dir() / f"{safe}.json"


def _use_memory_fallback() -> bool:
    """Fall back to the in-memory dict when the filesystem can't be used —
    for a read-only sandbox, a unit test that hasn't set VOICE_SESSIONS_DIR,
    or any environment where get_data_dir() itself fails. Detected once at
    the point of first attempted write."""
    return os.getenv("VOICE_SESSIONS_MEMORY", "").lower() in {"1", "true", "yes", "on"}


def _load_from_disk(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(_DEFAULT_SESSION)


def get_session(session_id: str) -> Dict[str, Any]:
    if _use_memory_fallback():
        with _MEMORY_LOCK:
            return _MEMORY_FALLBACK.setdefault(session_id, dict(_DEFAULT_SESSION))
    try:
        path = _session_path(session_id)
        if path.exists():
            return _load_from_disk(path)
        return dict(_DEFAULT_SESSION)
    except Exception:
        # Filesystem unreachable — degrade to in-memory rather than crash.
        with _MEMORY_LOCK:
            return _MEMORY_FALLBACK.setdefault(session_id, dict(_DEFAULT_SESSION))


def update_session(session_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    # Bug found in a robustness audit: this used to read (get_session, no
    # lock) then write (_write_to_disk, locked) as two separate steps --
    # two concurrent turns on the same session_id could both read the same
    # starting state, then each write back their own version, one silently
    # clobbering the other's update (lost update). Now the read, merge, and
    # write all happen inside one lock acquisition.
    if _use_memory_fallback():
        with _MEMORY_LOCK:
            session = _MEMORY_FALLBACK.setdefault(session_id, dict(_DEFAULT_SESSION))
            session.update(data)
            _MEMORY_FALLBACK[session_id] = session
            return session
    try:
        path = _session_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(path) + ".lock"):
            session = _load_from_disk(path) if path.exists() else dict(_DEFAULT_SESSION)
            session.update(data)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(session, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        return session
    except Exception:
        with _MEMORY_LOCK:
            session = _MEMORY_FALLBACK.setdefault(session_id, dict(_DEFAULT_SESSION))
            session.update(data)
            _MEMORY_FALLBACK[session_id] = session
            return session


def clear_session(session_id: str) -> None:
    with _MEMORY_LOCK:
        _MEMORY_FALLBACK.pop(session_id, None)
    try:
        path = _session_path(session_id)
        if path.exists():
            path.unlink()
        lock_path = path.with_suffix(path.suffix + ".lock")
        if lock_path.exists():
            try:
                lock_path.unlink()
            except OSError:
                pass
    except Exception:
        pass
