"""Main orchestrator agent (OA): single entry point for any farmer query
(weather, appointment booking, health logging, farm data questions).
Classifies intent via the existing extraction agent
(voice_agent.orchestrator.process_text_input, DeepSeek V3, one call), then
dispatches to the dedicated sub-agent/handler for that intent.

Deliberately does NOT add a second "classify, then re-extract" LLM hop —
this session's own eval proved combining intent+entity extraction into one
call is both faster and more accurate than splitting it. The intent field
already produced by process_text_input IS the routing decision.

Dispatch table, matching the real intent enum in bedrock_adapter.py's
extraction tool spec (WEATHER_ALERT, FETCH_ANIMAL_DETAILS, CREATE_ANIMAL,
UPDATE_ANIMAL, LOG_HEALTH, CREATE_APPOINTMENT):

  CREATE_APPOINTMENT, LOG_HEALTH  -> appointment_supervisor (real,
                                      multi-turn state machine, tested)
  WEATHER_ALERT                   -> weather_alert.get_weather_alert
  everything else (FETCH_ANIMAL_DETAILS, CREATE_ANIMAL, UPDATE_ANIMAL,
  general farm questions, advisory/recommendation asks -- none of which
  have a real intent value today, see below) -> query_agent as a
  best-effort fallback.

Known limitation, not hidden: query_agent is read-only (NL -> SQL ->
answer). Routing CREATE_ANIMAL/UPDATE_ANIMAL here means chat can't
actually create/update an animal record yet -- it can only answer
questions about existing ones. No new intent was added for
advisory/recommendations either (that would need its own golden-set eval
before shipping, same rigor as every other intent in this schema) --
those also fall through to query_agent for now.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from services.appointment_supervisor import AppointmentSupervisor
from services.query_agent.agent import process_query
from services.voice_agent.orchestrator import process_text_input
from services.weather_alert.service import get_weather_alert
from storage import get_farmer_by_id

_log = logging.getLogger("chat_orchestrator")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)

_BOOKING_INTENTS = {"CREATE_APPOINTMENT", "LOG_HEALTH"}

_appointment_supervisor = AppointmentSupervisor()


def _has_active_booking_draft(farmer_id: str, session_id: str) -> bool:
    """Cheap file-existence check, no LLM call -- an in-progress
    (unsubmitted) appointment/health-log draft always routes straight back
    to appointment_supervisor, so a mid-flow "yes"/"tomorrow morning" isn't
    reclassified by the router and doesn't risk being sent somewhere else."""
    path = _appointment_supervisor._path(session_id)
    if not path.exists():
        return False
    try:
        draft = _appointment_supervisor._load(session_id, farmer_id, "en-IN")
        return not draft.get("submitted", False)
    except Exception:
        return False


def route_turn(
    farmer_id: str,
    session_id: str,
    text: str,
    language: str = "en-IN",
    include_audio: bool = True,
) -> dict[str, Any]:
    if get_farmer_by_id(farmer_id) is None:
        raise ValueError("Farmer not found")

    if _has_active_booking_draft(farmer_id, session_id):
        result = _appointment_supervisor.turn(farmer_id, session_id, text, language, include_audio=include_audio)
        return {"agent": "appointment_supervisor", "intent": None, "result": result}

    # One classification call, same one that would run anyway on the first
    # real turn of a booking/health-log flow -- appointment_supervisor.turn()
    # below re-runs it under its own session key, so the very first turn of
    # a booking conversation costs two Bedrock calls, not one. Every
    # subsequent turn in that conversation hits the draft-exists shortcut
    # above and costs one, same as before this router existed.
    classification = process_text_input(text, session_id=f"{farmer_id}:{session_id}:route")
    intent = classification.get("intent")
    _log.info("chat_orchestrator route farmer=%s session=%s intent=%s", farmer_id, session_id, intent)

    if intent in _BOOKING_INTENTS:
        result = _appointment_supervisor.turn(farmer_id, session_id, text, language, include_audio=include_audio)
        return {"agent": "appointment_supervisor", "intent": intent, "result": result}

    if intent == "WEATHER_ALERT":
        entities = classification.get("entities") or {}
        location = entities.get("weather_location")
        if not location:
            farmer = get_farmer_by_id(farmer_id)
            location = getattr(farmer, "weather_location", "") if farmer else ""
        if not location:
            return {
                "agent": "weather_alert", "intent": intent,
                "result": {"error": "no_location", "message": "Need a PIN code or place name to check the weather."},
            }
        days = entities.get("forecast_days") or 3
        try:
            result = get_weather_alert(str(location), days=int(days))
            return {"agent": "weather_alert", "intent": intent, "result": result}
        except Exception as exc:
            _log.warning("weather_alert failed farmer=%s location=%s err=%s", farmer_id, location, exc)
            return {"agent": "weather_alert", "intent": intent, "result": {"error": str(exc)}}

    # Fallback for everything else: FETCH_ANIMAL_DETAILS, CREATE_ANIMAL,
    # UPDATE_ANIMAL (read-only here, see module docstring), general farm
    # questions, and advisory/recommendation asks (no dedicated intent yet).
    result = process_query(text, farmer_id)
    return {"agent": "query_agent", "intent": intent, "result": result}
