"""Shared "is this really an off-topic question" check, reused by both
appointment_supervisor and animal_registration so a farmer can ask an
unrelated question mid-flow without losing their place. (adk_router's own
weather-location-wait branch has a similar, separate classify-then-verify
check of its own -- not yet migrated to this shared helper.)

Classify-then-verify, not classify-and-trust: the router's own classifier
misreads vague off-topic phrasing often enough (see adk_router.py's
weather-wait branch and appointment_supervisor's original CONFIRMING-only
fix) that a genuine dispatch result is required as proof before a caller
actually treats the turn as a topic switch. A classified "query" intent
that produces no real SQL/data, or a "weather" intent that produces no
real answer, is not accepted -- the caller should keep going with its own
sticky flow unchanged.

Deliberately reuses adk_router's classifier via a local (deferred) import
rather than at module level. Two independent reasons, not one -- both
must hold for both legs (this module's import of adk_router, and each
supervisor's import of this module):
  1. Circular import: adk_router.py imports both supervisor packages at
     module load time; a module-level import back into adk_router from
     here would close that cycle once the supervisors import this module
     too (verified empirically -- hoisting either side alone is safe,
     hoisting both is not, given this codebase's real import order via
     services/api_service/main.py).
  2. Test-seam correctness: a module-level import would capture
     adk_router._classify_intent_async at import time, before
     tests/test_mid_draft_escape.py's monkeypatch.setattr(adk_router, ...)
     can intercept it -- the deferred import re-resolves the name on every
     call, which is what makes the monkeypatch actually take effect.
If you're tempted to "simplify" either deferred import away, both of the
above still apply.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any, Optional

from services.query_agent.adk_agent import process_query_adk
from services.weather_alert.adk_agent import process_weather_query_adk

# Same logger setup as adk_router, so these lines print in the server
# terminal (a plain __name__ logger has no handler and stays silent).
_log = logging.getLogger("chat_orchestrator.mid_draft_escape")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)

# Prefix of the session a probe runs in. A probe only checks whether the
# farmer's text is a real off-topic question; most probes are thrown away
# (no real answer, so the caller carries on with its own flow). Running
# them in the farmer's own chat session would write those unseen questions
# and answers into the chat memory the agents read on later turns. One
# probe session per chat (not a fresh one per probe) so probe sessions do
# not pile up in memory or in the session database; the agents' own
# session cap keeps it short.
_PROBE_SESSION_PREFIX = "probe-"


def _probe_session_id(session_id: Any) -> Optional[str]:
    """The session a probe for this chat runs in -- never the chat's own.

    The chat's session id comes from the app and can be any text, so the
    probe id is a hash of it, not the id plus a suffix: "abc" + ":probe"
    would be the same as a real chat whose id is "abc:probe", and the
    probe would then write into that chat's memory. Same chat -> same
    probe session; two chats -> two probe sessions.

    No chat session (None or an empty id) keeps the agents' one-off
    session, as before. A non-text id (a number, a UUID object) is read as
    its text."""
    if session_id is None:
        return None
    session_id = str(session_id).strip()
    if not session_id:
        return None
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]
    return f"{_PROBE_SESSION_PREFIX}{digest}"


def try_switch(text: str, farmer_id: str, session_id: str, language: str = "en-IN") -> Optional[dict[str, Any]]:
    """Returns {"intent": "query"|"weather", "answer": str} when `text` is a
    genuine, answerable off-topic question; None when it isn't (the
    classifier picked something else, the dispatch came back empty, or the
    classify/dispatch call itself failed) -- callers should treat None as
    "not a topic switch, carry on." Never raises: this runs on the single
    most common "didn't understand" turn shape in both supervisors, so a
    transient classify/dispatch failure must degrade to a normal re-ask,
    not fail the whole turn.

    The probe runs in a separate per-chat probe session, never in the
    farmer's own session (see _probe_session_id). Same calls as before,
    so no extra model cost. An accepted answer is shown to the farmer but
    is not in the chat session's memory.
    """
    probe_session = None
    try:
        # Inside the try: a bad session id must degrade to a normal
        # re-ask like any other probe failure, never fail the turn.
        probe_session = _probe_session_id(session_id)
        from services.chat_orchestrator.adk_router import _classify_intent_async

        intent = asyncio.run(_classify_intent_async(text))

        if intent == "query":
            probe = process_query_adk(text, farmer_id, session_id=probe_session, app_language=language)
            if probe.get("sql") and probe.get("data"):
                _log.info("mid_draft_escape accepted query farmer=%s session=%s probe_session=%s",
                          farmer_id, session_id, probe_session)
                return {"intent": "query", "answer": probe.get("answer") or ""}
            return None

        if intent == "weather":
            weather = process_weather_query_adk(text, farmer_id, session_id=probe_session)
            answer = (weather or {}).get("answer")
            if answer:
                _log.info("mid_draft_escape accepted weather farmer=%s session=%s probe_session=%s",
                          farmer_id, session_id, probe_session)
                return {"intent": "weather", "answer": answer}
            return None

        return None
    except Exception:
        _log.warning("mid_draft_escape probe failed farmer=%s session=%s probe_session=%s text=%r",
                     farmer_id, session_id, probe_session, text[:200], exc_info=True)
        return None
