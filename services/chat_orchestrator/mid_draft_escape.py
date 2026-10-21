"""Shared "is this really an off-topic question" check, reused by every
sticky mid-flow state (appointment_supervisor, animal_registration, and
adk_router's own weather-location-wait) so a farmer can ask an unrelated
question mid-flow without losing their place.

Classify-then-verify, not classify-and-trust: the router's own classifier
misreads vague off-topic phrasing often enough (see adk_router.py's
weather-wait branch and appointment_supervisor's original CONFIRMING-only
fix) that a genuine dispatch result is required as proof before a caller
actually treats the turn as a topic switch. A classified "query" intent
that produces no real SQL/data, or a "weather" intent that produces no
real answer, is not accepted -- the caller should keep going with its own
sticky flow unchanged.

Deliberately reuses adk_router's classifier via a local (deferred) import
rather than at module level: adk_router imports both supervisor packages
at module load time, so a module-level import back into adk_router from
here would be circular once the supervisors import this module too.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from services.query_agent.adk_agent import process_query_adk
from services.weather_alert.adk_agent import process_weather_query_adk


def try_switch(text: str, farmer_id: str, session_id: str, language: str = "en-IN") -> Optional[dict[str, Any]]:
    """Returns {"intent": "query"|"weather", "answer": str} when `text` is a
    genuine, answerable off-topic question; None when it isn't (the
    classifier picked something else, or the dispatch came back empty) --
    callers should treat None as "not a topic switch, carry on."
    """
    from services.chat_orchestrator.adk_router import _classify_intent_async

    intent = asyncio.run(_classify_intent_async(text))

    if intent == "query":
        probe = process_query_adk(text, farmer_id, session_id=session_id, app_language=language)
        if probe.get("sql") and probe.get("data"):
            return {"intent": "query", "answer": probe.get("answer") or ""}
        return None

    if intent == "weather":
        weather = process_weather_query_adk(text, farmer_id, session_id=session_id)
        answer = (weather or {}).get("answer")
        if answer:
            return {"intent": "weather", "answer": answer}
        return None

    return None
