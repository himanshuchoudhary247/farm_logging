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

from services.animal_registration import default_supervisor as _animal_registration_supervisor
from services.appointment_supervisor import default_supervisor as _appointment_supervisor
from services.llm_service.bedrock_adapter import TaskTier, model_for_task
from services.query_agent.adk_agent import process_query_adk
from services.voice_agent.session_store import get_session, update_session
from services.voice_agent.tts import synthesize_speech
from services.weather_alert.adk_agent import process_weather_query_adk

_log = logging.getLogger("chat_orchestrator.adk_router")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)


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
              include_audio: bool = False, language: str = "en-IN",
              speech_text: "str | None" = None) -> dict[str, Any]:
    """Single exit point for route_turn_adk -- logs the actual question/
    answer text and builds the response envelope in one place.

    Real bug, found live: appointment_supervisor.turn() already synthesizes
    speech internally and nests it as result["response_audio_base64"] --
    but the weather and query branches never called synthesize_speech() at
    all, so a voice turn landing in either of them got no spoken reply back
    regardless of include_audio. Frontend already checks both a top-level
    response_audio_base64 and result.response_audio_base64 (confirmed with
    the UI side), so this adds the top-level one here for exactly the
    branches that don't already embed it.

    The skip check below is structural, not agent-name-based: any
    supervisor that already did its own internal synthesis puts a
    "response_audio_base64" key in `result` (both appointment_supervisor's
    and animal_registration's _response() always include that key, even
    as None) -- so this method skips top-level synthesis automatically
    for it. Originally this was a hardcoded tuple of agent names, which
    was a footgun: the next agent added with internal audio synthesis
    would silently get double-synthesized here unless someone remembered
    to add its name. Checking for the key itself makes that impossible to
    forget -- confirmed weather_alert/adk_agent.py and
    query_agent/adk_agent.py never emit this key in their result dicts.

    speech_text lets a caller give audio a shorter script than what's
    displayed -- text can stay fully detailed (full breakdowns, full
    figures) while audio stays a short, listenable summary. Defaults to
    reply_text (old behavior: audio == text) when a branch doesn't have a
    separate spoken version."""
    _log.info(
        "chat_orchestrator turn farmer=%s session=%s agent=%s intent=%s text=%r reply=%r",
        farmer_id, session_id, agent, intent, text[:200], reply_text[:200],
    )
    envelope: dict[str, Any] = {"agent": agent, "intent": intent, "result": result, "reply_text": reply_text}
    if include_audio and "response_audio_base64" not in result:
        spoken = (speech_text if speech_text is not None else reply_text).strip()
        if spoken:
            audio, audio_error = synthesize_speech(spoken, target_lang=language.split("-")[0].lower())
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


def _has_active_registration_draft(farmer_id: str, session_id: str) -> bool:
    """Same sticky-routing pattern as _has_active_booking_draft, for the
    animal-registration flow -- a mid-registration turn (e.g. a bare
    breed name, or a date answering "date of birth?") must not get
    re-classified away by the router."""
    path = _animal_registration_supervisor._path(farmer_id, session_id)
    if not path.exists():
        return False
    try:
        draft = _animal_registration_supervisor._load(session_id, farmer_id, "en-IN")
        return draft.get("state") != "CANCELLED" and not draft.get("submitted", False)
    except Exception:
        return False


_ROUTE_INSTRUCTION = """Classify what area of a livestock farm-management app a farmer's message belongs to, then call record_route exactly once with your decision. Never answer the farmer directly yourself -- only classify.

Categories:
- "appointment": booking a vet appointment, reporting a sick/injured animal, requesting a farm visit or treatment, OR reporting/logging a health event for an animal ALREADY on the farm (a treatment given, a vaccination done, a symptom noticed, a checkup completed).
- "add_animal": registering a brand-new animal that isn't on the farm's records yet -- the farmer wants to ADD it as a new entry (a new goat/sheep they bought, were given, or that was born). This is about the animal's identity itself (ID, species, breed, sex), not a health event.
- "weather": weather, rain, temperature, heat/cold stress, whether to move animals indoors, or feed-price/market questions tied to weather/season.
- "query": LOOKING UP the farmer's own EXISTING animals or records -- counts, lists, history, "how many", "when was", past vaccination records, past health logs, past appointments, general greetings, or anything unclear. This category is READ-ONLY -- it can only look up data that's already saved, never record something new. If a message could be read as either reporting a new event or asking about past ones, and it describes something that just happened, prefer "appointment" or "add_animal" (whichever fits) -- a farmer telling you what happened wants it recorded, not silently discarded.

"appointment" vs "add_animal": both can write data, but about different things -- "my goat has a fever" or "book a vet visit" is "appointment" (an EXISTING animal's health). "I got a new goat, register it" or "add a new sheep to my farm" is "add_animal" (the animal's own identity record, brand new).

When genuinely ambiguous with no hint of a new event to record, prefer "query" -- it is the general-purpose fallback."""

_VALID_INTENTS = ("appointment", "add_animal", "weather", "query")


def _make_record_route_tool(captured: dict[str, str]):
    def record_route(intent: str) -> dict[str, Any]:
        """Record which area the farmer's message belongs to.

        Args:
            intent: one of "appointment", "add_animal", "weather", "query".

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


def _weather_session_key(farmer_id: str, session_id: str) -> str:
    return f"{farmer_id}:{session_id}:weather_pending"


def _run_weather(farmer_id: str, session_id: str, text: str, intent: "str | None",
                  include_audio: bool, language: str, allow_rearm: bool = True) -> dict[str, Any]:
    weather = process_weather_query_adk(text, farmer_id)
    result = weather["result"]
    # Real bug, found live testing the flokiquser test-conversation set:
    # unlike appointment_supervisor, weather has zero multi-turn memory --
    # every turn is classified from scratch with no idea a location was
    # just asked for. "what's the weather" -> "I need a PIN code" ->
    # farmer replies with a bare PIN (even a real, valid one) -> the
    # classifier sees a bare number with no weather-sounding words and
    # sends it to query_agent instead, which has no idea what to do with
    # it either. Bounded sticky fix, mirroring _has_active_booking_draft's
    # pattern but capped to exactly ONE follow-up turn total, not
    # indefinite -- allow_rearm=False on the sticky-routed call below
    # means a second consecutive miss falls back to normal classification
    # instead of trapping the farmer in weather if they've actually moved
    # on to something else.
    if allow_rearm:
        weather_key = _weather_session_key(farmer_id, session_id)
        if result.get("error") == "no_location":
            update_session(weather_key, {"awaiting_location": True})
        else:
            update_session(weather_key, {"awaiting_location": False})
    reply = weather["answer"] or _reply_text("weather_alert", result)
    return _envelope("weather_alert", intent, result, reply, farmer_id, session_id, text, include_audio, language, weather.get("speech_text"))


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

    if _has_active_registration_draft(farmer_id, session_id):
        result = _animal_registration_supervisor.turn(farmer_id, session_id, text, language, include_audio=include_audio)
        reply = _reply_text("animal_registration", result)
        return _envelope("animal_registration", None, result, reply, farmer_id, session_id, text, include_audio, language)

    weather_key = _weather_session_key(farmer_id, session_id)
    if get_session(weather_key).get("awaiting_location"):
        # Sticky, exactly once: clear immediately so a second consecutive
        # miss (e.g. two bad PINs in a row) falls back to normal
        # classification rather than locking the farmer into weather
        # indefinitely if they've actually moved on to something else.
        update_session(weather_key, {"awaiting_location": False})
        return _run_weather(farmer_id, session_id, text, "weather", include_audio, language, allow_rearm=False)

    intent = asyncio.run(_classify_intent_async(text))
    _log.info("adk_router classified farmer=%s session=%s text=%r intent=%s", farmer_id, session_id, text[:200], intent)

    if intent == "appointment":
        result = _appointment_supervisor.turn(farmer_id, session_id, text, language, include_audio=include_audio)
        reply = _reply_text("appointment_supervisor", result)
        return _envelope("appointment_supervisor", intent, result, reply, farmer_id, session_id, text, include_audio, language)

    if intent == "add_animal":
        result = _animal_registration_supervisor.turn(farmer_id, session_id, text, language, include_audio=include_audio)
        reply = _reply_text("animal_registration", result)
        return _envelope("animal_registration", intent, result, reply, farmer_id, session_id, text, include_audio, language)

    if intent == "weather":
        return _run_weather(farmer_id, session_id, text, intent, include_audio, language)

    result = process_query_adk(text, farmer_id)
    reply = result.get("answer") or ""
    return _envelope("query_agent", intent, result, reply, farmer_id, session_id, text, include_audio, language, result.get("speech_text"))
