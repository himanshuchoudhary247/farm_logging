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
  WEATHER_ALERT                   -> pincode_store.get_pincode_data (in-memory
                                      cache, shared with every other agent
                                      that needs weather/feed-market context
                                      for the same PIN)
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

import json
import logging
from typing import Any, Optional

from services.appointment_supervisor import AppointmentSupervisor
from services.llm_service.bedrock_adapter import BedrockTextAdapter, TaskTier
from services.pincode_store import get_pincode_data
from services.query_agent.agent import process_query
from services.voice_agent.orchestrator import process_text_input
from storage import get_farmer_by_id

_log = logging.getLogger("chat_orchestrator")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)

_BOOKING_INTENTS = {"CREATE_APPOINTMENT", "LOG_HEALTH"}

_appointment_supervisor = AppointmentSupervisor()

_WEATHER_QA_SYSTEM = """You are a livestock weather and farm-advisory assistant. Given pre-computed weather, seasonal, and feed-market data for a farmer's location, answer the farmer's specific question.

Rules:
- Keep it short, 1-3 sentences.
- Base your answer only on the data given. Do not invent numbers, prices, or facts not present in the data.
- If the data does not contain what the question asks, say so simply, then give the closest relevant fact from the data instead of repeating an unrelated summary.
- Do NOT mention JSON, fields, or technical details.
- Return only the answer text, nothing else."""


def _answer_weather_question(query: str, pincode_data: dict[str, Any]) -> str:
    """query_agent already has this pattern (_format_result): feed the raw
    structured data plus the farmer's actual question to a generation-tier
    model instead of returning a fixed lookup string regardless of what was
    asked. Without this, every follow-up in a weather conversation ("should
    I move them indoors?", "what about feed prices?") got back the exact
    same canned risk-level summary -- a real bug, not just a tone issue,
    since get_weather_alert()'s summary/advisories are a static table keyed
    only on risk_level (services/weather_alert/service.py), with no
    awareness of the question text at all.
    English-only for now: the underlying weather/seasonal data itself is
    English-only (no translated summaries exist to draw from), so this adds
    no new per-language quality risk."""
    data_str = json.dumps(pincode_data, indent=2, default=str)
    prompt = f"""Farmer asked: "{query}"

Weather/seasonal/feed-market data for their location:
{data_str}

Give a short, clear answer in natural language."""
    try:
        adapter = BedrockTextAdapter(task=TaskTier.GENERATION)
        return adapter.complete(messages=[{"role": "user", "content": prompt}], system=_WEATHER_QA_SYSTEM).strip()
    except Exception as exc:
        _log.warning("weather QA formatting failed, falling back to raw summary: %s", exc)
        weather = pincode_data.get("weather") or {}
        return str(weather.get("summary") or "No weather data available right now.")


def _reply_text(agent: str, result: dict[str, Any]) -> str:
    """One canonical display string per turn, regardless of which agent
    handled it or which state it ended in -- mirrors how chat APIs (OpenAI,
    Claude) expose a single content field independent of which tool ran
    underneath, so the UI never needs per-agent/per-shape branching to know
    what to show. Falls back to a generic line rather than raising -- a
    missing field here should degrade the display, not break the turn that
    already succeeded."""
    if "response_text" in result:
        return str(result["response_text"])
    if agent == "query_agent":
        return str(result.get("answer") or "")
    if agent == "weather_alert":
        return str(result.get("message") or result.get("error") or "")
    return ""


def _envelope(agent: str, intent: Optional[str], result: dict[str, Any], reply_text: str,
              farmer_id: str, session_id: str, text: str) -> dict[str, Any]:
    """Single exit point for route_turn -- logs the actual question/answer
    text (previously only routing/latency/status lines were logged, so
    debugging a bad reply meant reconstructing the conversation by hand from
    a separate UI transcript) and builds the response envelope in one place."""
    _log.info(
        "chat_orchestrator turn farmer=%s session=%s agent=%s intent=%s text=%r reply=%r",
        farmer_id, session_id, agent, intent, text[:200], reply_text[:200],
    )
    return {"agent": agent, "intent": intent, "result": result, "reply_text": reply_text}


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
    if _has_active_booking_draft(farmer_id, session_id):
        result = _appointment_supervisor.turn(farmer_id, session_id, text, language, include_audio=include_audio)
        reply = _reply_text("appointment_supervisor", result)
        return _envelope("appointment_supervisor", None, result, reply, farmer_id, session_id, text)

    # One classification call, same one that would run anyway on the first
    # real turn of a booking/health-log flow -- appointment_supervisor.turn()
    # below re-runs it under its own session key, so the very first turn of
    # a booking conversation costs two Bedrock calls, not one. Every
    # subsequent turn in that conversation hits the draft-exists shortcut
    # above and costs one, same as before this router existed.
    classification = process_text_input(text, session_id=f"{farmer_id}:{session_id}:route")
    intent = classification.get("intent")

    if intent in _BOOKING_INTENTS:
        result = _appointment_supervisor.turn(farmer_id, session_id, text, language, include_audio=include_audio)
        reply = _reply_text("appointment_supervisor", result)
        return _envelope("appointment_supervisor", intent, result, reply, farmer_id, session_id, text)

    if intent == "WEATHER_ALERT":
        entities = classification.get("entities") or {}
        location = entities.get("weather_location")
        if not location:
            farmer = get_farmer_by_id(farmer_id)
            location = getattr(farmer, "weather_location", "") if farmer else ""
        if not location:
            result = {"error": "no_location", "message": "Need a PIN code or place name to check the weather."}
            reply = _reply_text("weather_alert", result)
            return _envelope("weather_alert", intent, result, reply, farmer_id, session_id, text)
        try:
            result = get_pincode_data(str(location))
            reply = _answer_weather_question(text, result)
            return _envelope("weather_alert", intent, result, reply, farmer_id, session_id, text)
        except Exception as exc:
            _log.warning("weather_alert failed farmer=%s location=%s err=%s", farmer_id, location, exc)
            result = {"error": str(exc)}
            reply = _reply_text("weather_alert", result)
            return _envelope("weather_alert", intent, result, reply, farmer_id, session_id, text)

    # Fallback for everything else: FETCH_ANIMAL_DETAILS, CREATE_ANIMAL,
    # UPDATE_ANIMAL (read-only here, see module docstring), general farm
    # questions, and advisory/recommendation asks (no dedicated intent yet).
    result = process_query(text, farmer_id)
    reply = _reply_text("query_agent", result)
    return _envelope("query_agent", intent, result, reply, farmer_id, session_id, text)
