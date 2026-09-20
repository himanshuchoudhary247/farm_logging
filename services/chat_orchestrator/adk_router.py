"""ADK-native chat orchestrator -- the sole routing/dispatch implementation
(the old chat_orchestrator/router.py this was built alongside has been
removed now that this path is verified equivalent; see
/Users/sudhanshu/.claude/plans/elegant-roaming-river.md).

Deliberate design choice, not an oversight: the coordinator ONLY classifies
which area a message belongs to. It never generates the farmer-facing text
itself. appointment_supervisor.turn()'s result is returned completely
untouched, exactly as router.py does today -- that flow's response_text,
language-specific wording, and UI pills/options are this session's own
tested contract, and letting an LLM "helpfully" rephrase them on the way out
would risk silently breaking a contract 24 dedicated regression tests exist
to protect. ADK's sub_agents/transfer_to_agent delegation (where a sub-agent
generates the final reply itself) was considered and rejected for the
appointment case specifically for this reason -- see the plan's "Decision"
section. Weather and query DO let their own ADK agents phrase the final
answer (services/weather_alert/adk_agent.py, services/query_agent/
adk_agent.py) since those never had a fixed-wording contract to protect.
"""
from __future__ import annotations

import asyncio
import logging
from base64 import b64encode
from typing import Any

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

from services.appointment_supervisor import AppointmentSupervisor
from services.llm_service.bedrock_adapter import TaskTier, model_for_task
from services.query_agent.adk_agent import process_query_adk
from services.voice_agent.tts import synthesize_speech
from services.weather_alert.adk_agent import process_weather_query_adk

_log = logging.getLogger("chat_orchestrator.adk_router")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)

_appointment_supervisor = AppointmentSupervisor()


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


def _envelope(agent: str, intent: "str | None", result: dict[str, Any], reply_text: str,
              farmer_id: str, session_id: str, text: str,
              include_audio: bool = False, language: str = "en-IN") -> dict[str, Any]:
    """Single exit point for route_turn_adk -- logs the actual question/
    answer text and builds the response envelope in one place.

    Real bug, found live: appointment_supervisor.turn() already synthesizes
    speech internally and nests it as result["response_audio_base64"] --
    but the weather and query branches never called synthesize_speech() at
    all, so a voice turn landing in either of them got no spoken reply back
    regardless of include_audio. Frontend already checks both a top-level
    response_audio_base64 and result.response_audio_base64 (confirmed with
    the UI side), so this adds the top-level one here for exactly the two
    agents that don't already embed it -- appointment_supervisor keeps its
    existing nested field untouched, no double-synthesis."""
    _log.info(
        "chat_orchestrator turn farmer=%s session=%s agent=%s intent=%s text=%r reply=%r",
        farmer_id, session_id, agent, intent, text[:200], reply_text[:200],
    )
    envelope: dict[str, Any] = {"agent": agent, "intent": intent, "result": result, "reply_text": reply_text}
    if include_audio and agent != "appointment_supervisor" and reply_text.strip():
        audio, audio_error = synthesize_speech(reply_text, target_lang=language.split("-")[0].lower())
        envelope["response_audio_base64"] = b64encode(audio).decode("ascii") if audio else None
        envelope["audio_error"] = audio_error
    return envelope


def _has_active_booking_draft(farmer_id: str, session_id: str) -> bool:
    """Cheap file-existence check, no LLM call -- an in-progress
    (unsubmitted) appointment/health-log draft always routes straight back
    to appointment_supervisor, so a mid-flow "yes"/"tomorrow morning" isn't
    reclassified by the router and doesn't risk being sent somewhere else."""
    path = _appointment_supervisor._path(farmer_id, session_id)
    if not path.exists():
        return False
    try:
        draft = _appointment_supervisor._load(session_id, farmer_id, "en-IN")
        # A cancelled draft is just as "done" as a submitted one -- without
        # this, a farmer who cancels a booking gets every future message on
        # that session_id permanently routed back into appointment_supervisor.
        return draft.get("state") != "CANCELLED" and not draft.get("submitted", False)
    except Exception:
        return False

_ROUTE_INSTRUCTION = """Classify what area of a livestock farm-management app a farmer's message belongs to, then call record_route exactly once with your decision. Never answer the farmer directly yourself -- only classify.

Categories:
- "appointment": booking a vet appointment, reporting a sick/injured animal, requesting a farm visit or treatment.
- "weather": weather, rain, temperature, heat/cold stress, whether to move animals indoors, or feed-price/market questions tied to weather/season.
- "query": anything else about the farmer's own animals or records -- counts, lists, history, "how many", "when was", vaccination records, health logs, past appointments, general greetings, or anything unclear.

When genuinely ambiguous, prefer "query" -- it is the general-purpose fallback."""

_VALID_INTENTS = ("appointment", "weather", "query")


def _make_record_route_tool(captured: dict[str, str]):
    def record_route(intent: str) -> dict[str, Any]:
        """Record which area the farmer's message belongs to.

        Args:
            intent: one of "appointment", "weather", "query".

        Returns:
            Confirmation that the routing decision was recorded.
        """
        captured["intent"] = intent if intent in _VALID_INTENTS else "query"
        return {"recorded": captured["intent"]}

    return record_route


def _build_classifier_agent(captured: dict[str, str]) -> Agent:
    model_spec = model_for_task(TaskTier.EXTRACTION)
    return Agent(
        name="router_classifier",
        model=LiteLlm(model=f"bedrock/{model_spec['id']}", temperature=0),
        instruction=_ROUTE_INSTRUCTION,
        tools=[_make_record_route_tool(captured)],
    )


async def _classify_intent_async(text: str) -> str:
    captured: dict[str, str] = {}
    agent = _build_classifier_agent(captured)
    runner = InMemoryRunner(agent=agent, app_name="farmer_chat_router_classifier")
    session = await runner.session_service.create_session(app_name="farmer_chat_router_classifier", user_id="router")
    message = types.Content(role="user", parts=[types.Part(text=text)])
    async for _event in runner.run_async(user_id="router", session_id=session.id, new_message=message):
        pass
    return captured.get("intent", "query")


def route_turn_adk(
    farmer_id: str,
    session_id: str,
    text: str,
    language: str = "en-IN",
    include_audio: bool = True,
) -> dict[str, Any]:
    """Drop-in replacement for router.py's route_turn(), same envelope
    shape ({"agent", "intent", "result", "reply_text", ...}) -- routing
    decision now comes from an ADK classifier agent instead of reusing
    process_text_input's own intent field, and the weather/query branches
    are answered by their own ADK agents instead of a direct
    get_pincode_data/process_query call."""
    if _has_active_booking_draft(farmer_id, session_id):
        result = _appointment_supervisor.turn(farmer_id, session_id, text, language, include_audio=include_audio)
        reply = _reply_text("appointment_supervisor", result)
        return _envelope("appointment_supervisor", None, result, reply, farmer_id, session_id, text, include_audio, language)

    intent = asyncio.run(_classify_intent_async(text))
    _log.info("adk_router classified farmer=%s session=%s text=%r intent=%s", farmer_id, session_id, text[:200], intent)

    if intent == "appointment":
        result = _appointment_supervisor.turn(farmer_id, session_id, text, language, include_audio=include_audio)
        reply = _reply_text("appointment_supervisor", result)
        return _envelope("appointment_supervisor", intent, result, reply, farmer_id, session_id, text, include_audio, language)

    if intent == "weather":
        weather = process_weather_query_adk(text, farmer_id)
        result = weather["result"]
        reply = weather["answer"] or _reply_text("weather_alert", result)
        return _envelope("weather_alert", intent, result, reply, farmer_id, session_id, text, include_audio, language)

    result = process_query_adk(text, farmer_id)
    reply = result.get("answer") or ""
    return _envelope("query_agent", intent, result, reply, farmer_id, session_id, text, include_audio, language)
