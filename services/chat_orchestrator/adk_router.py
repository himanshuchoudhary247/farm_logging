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
import os
from base64 import b64encode
from typing import Any, Optional

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types

from services.animal_registration import default_supervisor as _animal_registration_supervisor
from services.appointment_supervisor import default_supervisor as _appointment_supervisor
from services.chat_orchestrator.intents import VALID_INTENTS, build_route_instruction
from services.common.name_match import find_name_mentions
from services.llm_service.bedrock_adapter import TaskTier, model_for_task
from services.query_agent.adk_agent import process_query_adk
from services.voice_agent.session_store import get_session, update_session
from services.voice_agent.tts import synthesize_speech
from services.weather_alert.adk_agent import process_weather_query_adk
from services.llm_service.adk_model import build_adk_model
from storage import animals_for_farmer

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


# Both derived from the shared catalog (services/chat_orchestrator/intents.py).
# _ROUTE_INSTRUCTION is byte-identical to the pre-refactor hand-written
# string (see test_intents_catalog.py::test_route_instruction_byte_identical).
_ROUTE_INSTRUCTION = build_route_instruction()
_VALID_INTENTS = VALID_INTENTS


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


def _build_classifier_agent(captured: dict[str, str]) -> LlmAgent:
    model_spec = model_for_task(TaskTier.EXTRACTION)
    from services.common.adk_telemetry import make_adk_callbacks
    return LlmAgent(
        name="router_classifier",
        model=build_adk_model(TaskTier.EXTRACTION, model_spec["id"], temperature=0),
        instruction=_ROUTE_INSTRUCTION,
        tools=[_make_record_route_tool(captured)],
        **make_adk_callbacks("router_classifier"),
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


def _looks_like_pin(text: str) -> bool:
    """A bare 6-digit PIN, spaces allowed ("411001", "411 001")."""
    compact = "".join(ch for ch in (text or "") if not ch.isspace())
    return compact.isascii() and compact.isdigit() and len(compact) == 6


def _weather_session_key(farmer_id: str, session_id: str) -> str:
    return f"{farmer_id}:{session_id}:weather_pending"


# Side questions during an open booking/registration. A farmer in the middle
# of a booking asked "how many goats do I have?" or "what's the weather in
# Pune today?" and the booking took the message: the question went
# unanswered, and "today" became the booking date (seen live in en/hi/ta).
# The open flow now asks the classifier (only on a turn that adds nothing to
# it) and hands weather/query questions back here, untouched. Kill switch:
# CHAT_SIDE_QUESTIONS=0 sends every sticky turn to the open flow as before.
_SIDE_QUESTIONS_ENV = "CHAT_SIDE_QUESTIONS"


def _side_questions_on() -> bool:
    return os.getenv(_SIDE_QUESTIONS_ENV, "1").strip().lower() not in ("0", "false", "no", "off")


def _side_question_label(text: str) -> Optional[str]:
    """The classifier's intent when it names another agent that can answer
    on its own (weather, query), or the other flow (appointment, add_animal)
    when switching between flows is on; None otherwise. Each flow ignores
    its own intent and acts only on the others."""
    intent = asyncio.run(_classify_intent_async(text))
    _log.info("adk_router side-question check text=%r intent=%s", text[:200], intent)
    if intent in ("weather", "query"):
        return intent
    if intent in _FLOW_AGENTS and _switch_on(_FLOW_SWITCH_ENV):
        return intent
    return None


# Farmers change their mind in the middle of a flow (found by the evals
# suite, layer 4, in all 7 languages). Kill switches, "0" = old behaviour:
# CHAT_FLOW_SWITCH -- a booking request while a registration is open (or a
#   registration request while a booking is open) closes the open draft
#   unsaved and starts the other flow with the same message. Before, the
#   open flow just asked its own question again.
# CHAT_CANCEL_THEN_ROUTE -- "cancel the booking and tell me how many cows I
#   have" / "forget the vet, I want to register a goat" / "forget this, MOTI
#   is limping, vet tomorrow 11 am": after the cancel, the same message goes
#   to the agent it is meant for, and both replies are shown. Before, only
#   "cancelled" came back and the rest of the message was lost.
_FLOW_SWITCH_ENV = "CHAT_FLOW_SWITCH"
_CANCEL_THEN_ROUTE_ENV = "CHAT_CANCEL_THEN_ROUTE"
_FLOW_AGENTS = {"appointment": "appointment_supervisor", "add_animal": "animal_registration"}


def _switch_on(name: str) -> bool:
    return os.getenv(name, "1").strip().lower() not in ("0", "false", "no", "off")


def _then(first_text: str, follow: dict[str, Any], farmer_id: str, session_id: str, text: str,
          include_audio: bool, language: str) -> dict[str, Any]:
    """The closed flow's message, then the next agent's reply, as one reply
    (shown and spoken). `follow` is that agent's envelope, built without
    audio; the agent and intent are the follow-up's, so the app shows the
    flow that is open now."""
    result = dict(follow.get("result") or {})
    result.pop("response_audio_base64", None)
    result.pop("audio_error", None)
    follow_reply = str(follow.get("reply_text") or "")
    reply = f"{first_text}\n\n{follow_reply}".strip() if first_text else follow_reply
    result["response_text"] = reply
    speech = result.get("speech_text")
    speech = f"{first_text} {speech}".strip() if speech else None
    return _envelope(follow.get("agent"), follow.get("intent"), result, reply, farmer_id, session_id, text,
                     include_audio, language, speech)


def _route_after_cancel(agent: str, flow_intent: str, result: dict[str, Any], farmer_id: str, session_id: str,
                        text: str, language: str, allowed) -> "dict[str, Any] | None":
    """The envelope for what the rest of a cancelling message asks for, or
    None when it asks for nothing else (a plain "cancel it"). Runs after the
    cancelled flow's own turn has finished, so its lock is free."""
    if result.get("cancel_with_details") and agent == "appointment_supervisor" and allowed("appointment"):
        _log.info("adk_router cancel then new booking farmer=%s session=%s", farmer_id, session_id)
        result = _appointment_supervisor.turn(farmer_id, session_id, text, language, include_audio=False,
                                              fresh_start=True)
        return _envelope("appointment_supervisor", "appointment", result, _reply_text("appointment_supervisor", result),
                         farmer_id, session_id, text, False, language)
    try:
        intent = asyncio.run(_classify_intent_async(text))
    except Exception as exc:  # the cancel itself is done; never fail the turn over the extra check
        _log.warning("adk_router after-cancel check skipped farmer=%s session=%s: %s", farmer_id, session_id, exc)
        return None
    _log.info("adk_router after-cancel check farmer=%s session=%s text=%r intent=%s",
              farmer_id, session_id, text[:200], intent)
    if intent == flow_intent or intent not in _DISPATCH_TABLE or not allowed(intent):
        return None
    if intent == "query":
        follow = _dispatch_query(farmer_id, session_id, text, language, False, "query")
        # Only a real database answer counts ("cancel it" alone is no question).
        return follow if follow["result"].get("sql") and follow["result"].get("data") else None
    return _DISPATCH_TABLE[intent](farmer_id, session_id, text, language, False, intent)


def _waiting_weather_pin(farmer_id: str, session_id: str, text: str) -> "int | None":
    """Asks so far when this text is a bare PIN and the weather agent is
    waiting for one (it asked during an open booking/registration), else
    None. Without this the PIN went to the open flow, not to weather."""
    if not _looks_like_pin(text):
        return None
    state = get_session(_weather_session_key(farmer_id, session_id))
    return int(state.get("asks") or 1) if state.get("awaiting_location") else None


def _side_question_envelope(agent: str, intent: str, result: dict[str, Any], side_reply: str,
                            farmer_id: str, session_id: str, text: str,
                            include_audio: bool, language: str) -> dict[str, Any]:
    """The other agent's answer, then the open flow's reminder, as one
    reply (shown and spoken). `agent` stays the open flow so the app keeps
    showing that flow's state; `intent` says what was answered."""
    reminder = str(result.get("reminder") or "")
    reply = f"{side_reply}\n\n{reminder}".strip() if side_reply else reminder
    result = dict(result)
    result["response_text"] = reply
    return _envelope(agent, intent, result, reply, farmer_id, session_id, text, include_audio, language)


# The animal the farmer was just talking about. "What breed is KAALI?" then
# "she is limping, book a vet for her": the booking asked for the animal
# again (seen live in en/hi). After a farm-data question that names exactly
# one of the farmer's own stored animals (in the question or the answer, any
# script or spelling), that name is kept for the NEXT turn only; a new
# booking started on that turn uses it when it names no animal itself. Any
# other turn clears it. Kill switch: CHAT_RECENT_ANIMAL=0.
_RECENT_ANIMAL_ENV = "CHAT_RECENT_ANIMAL"


def _recent_animal_on() -> bool:
    return os.getenv(_RECENT_ANIMAL_ENV, "1").strip().lower() not in ("0", "false", "no", "off")


def _recent_animal_key(farmer_id: str, session_id: str) -> str:
    return f"{farmer_id}:{session_id}:recent_animal"


def _take_recent_animal(farmer_id: str, session_id: str) -> Optional[str]:
    """The animal kept by the previous turn, cleared on read so it lasts one turn."""
    if not _recent_animal_on():
        return None
    key = _recent_animal_key(farmer_id, session_id)
    name = get_session(key).get("name")
    if name:
        update_session(key, {"name": None})
    return name or None


def _remember_animal(farmer_id: str, session_id: str, *texts: str) -> None:
    """Keep the one stored animal named in these texts, if exactly one is."""
    if not _recent_animal_on():
        return
    try:
        names = [a.tag_or_name for a in animals_for_farmer(farmer_id)]
        found = {m.name for t in texts for m in find_name_mentions(t or "", names, include_exact=True)}
    except Exception as exc:
        _log.warning("adk_router recent animal lookup failed farmer=%s: %s", farmer_id, exc)
        return
    if len(found) == 1:
        name = found.pop()
        update_session(_recent_animal_key(farmer_id, session_id), {"name": name})
        _log.info("adk_router recent animal farmer=%s session=%s animal=%s", farmer_id, session_id, name)


def _side_question_reply(intent: str, result: dict[str, Any], farmer_id: str, session_id: str,
                         text: str, language: str, previous_asks: int = 0) -> str:
    """Answer text for a side question: the query agent's answer the open
    flow already got, or a fresh weather answer (which may ask for a PIN;
    the next turn's PIN then reaches weather via _waiting_weather_pin)."""
    if intent == "query":
        return str(result.get("side_answer") or "")
    weather = _run_weather(farmer_id, session_id, text, "weather", False, language, previous_asks=previous_asks)
    return str(weather.get("reply_text") or "")


# The weather and query agents pick their reply language from the text
# itself, so a language-neutral message (a bare PIN like "411001", a tag
# number) came back in English even when the farmer's app language is
# Marathi or Hindi. The app always sends the farmer's language, so pass
# it on explicitly.
# Weather asks for a PIN/place at most this many times in a row before
# the farmer's messages go back to normal intent classification.
_MAX_LOCATION_ASKS = 3
_REPLY_LANGUAGE_NAMES = {"hi": "Hindi", "ta": "Tamil", "te": "Telugu", "kn": "Kannada", "mr": "Marathi", "ml": "Malayalam"}


def _with_reply_language(text: str, language: str) -> str:
    name = _REPLY_LANGUAGE_NAMES.get((language or "").split("-")[0].lower())
    if not name:
        return text
    return f"{text}\n\n(Reply in {name}.)"


def _run_weather(farmer_id: str, session_id: str, text: str, intent: "str | None",
                  include_audio: bool, language: str, previous_asks: int = 0) -> dict[str, Any]:
    weather = process_weather_query_adk(_with_reply_language(text, language), farmer_id, session_id=session_id)
    result = weather["result"]
    # Real bug, found live testing the flokiquser test-conversation set:
    # unlike appointment_supervisor, weather has zero multi-turn memory --
    # every turn is classified from scratch with no idea a location was
    # just asked for. "what's the weather" -> "I need a PIN code" ->
    # farmer replies with a bare PIN (even a real, valid one) -> the
    # classifier sees a bare number with no weather-sounding words and
    # sends it to query_agent instead, which has no idea what to do with
    # it either. Bounded sticky fix, mirroring _has_active_booking_draft's
    # pattern.
    #
    # Capped at _MAX_LOCATION_ASKS asks in a row, not one: with a
    # one-turn cap, "weather?" -> PIN asked -> "will it rain?" -> PIN
    # asked again -> "411001" had lost the sticky flag and went to
    # query_agent (seen live). The cap still stops a farmer who has moved
    # on from being trapped in weather.
    weather_key = _weather_session_key(farmer_id, session_id)
    asks = previous_asks + 1
    # Any error, not only no_location: in Marathi the model sometimes
    # passed a Marathi word ("आज") as the place, the lookup failed with a
    # different error, it asked for the PIN anyway, and the PIN then went
    # to query_agent (seen live).
    if result.get("error") and asks < _MAX_LOCATION_ASKS:
        update_session(weather_key, {"awaiting_location": True, "asks": asks})
    else:
        update_session(weather_key, {"awaiting_location": False})
    reply = weather["answer"] or _reply_text("weather_alert", result)
    return _envelope("weather_alert", intent, result, reply, farmer_id, session_id, text, include_audio, language, weather.get("speech_text"))


def _blocked_envelope(intent: "str | None", farmer_id: str, session_id: str, text: str, language: str) -> dict[str, Any]:
    """Stub response for the allowed_intents gate: agent=None signals the
    caller ("this intent isn't allowed on this channel") without dispatching
    the actual agent (which would advance its draft state as a side effect).
    Matches the standard envelope shape so callers do not need special
    branches to handle it."""
    _log.info(
        "adk_router blocked intent=%s farmer=%s session=%s text=%r (allowed_intents gate)",
        intent, farmer_id, session_id, text[:200],
    )
    return {"agent": None, "intent": intent, "result": None, "reply_text": ""}


def route_turn_adk(
    farmer_id: str,
    session_id: str,
    text: str,
    language: str = "en-IN",
    include_audio: bool = True,
    allowed_intents: "Optional[set[str]]" = None,
) -> dict[str, Any]:
    """Drop-in replacement for router.py's route_turn(), same envelope
    shape ({"agent", "intent", "result", "reply_text", ...}) -- routing
    decision now comes from an ADK classifier agent instead of reusing
    process_text_input's own intent field, and the weather/query branches
    are answered by their own ADK agents instead of a direct
    get_pincode_data/process_query call.

    allowed_intents (optional): when set, the router refuses to dispatch
    any intent (classified OR sticky) not in the set, returning the
    blocked stub instead. This is what lets a transport layer (e.g. the
    WhatsApp channel) constrain which agents a channel can reach without
    the caller having to run the classifier itself. When None (existing
    callers -- the app, voice), behavior is exactly unchanged."""
    def _allowed(intent_name: str) -> bool:
        return allowed_intents is None or intent_name in allowed_intents

    def _side_question(question: str) -> Optional[str]:
        label = _side_question_label(question)
        return label if label and _allowed(label) else None

    side_question = _side_question if _side_questions_on() else None
    recent_animal = _take_recent_animal(farmer_id, session_id)

    for agent, flow_intent, supervisor, has_draft in (
        ("appointment_supervisor", "appointment", _appointment_supervisor, _has_active_booking_draft),
        ("animal_registration", "add_animal", _animal_registration_supervisor, _has_active_registration_draft),
    ):
        if not has_draft(farmer_id, session_id):
            continue
        if not _allowed(flow_intent):
            return _blocked_envelope(flow_intent, farmer_id, session_id, text, language)
        if side_question is not None and _allowed("weather"):
            asks = _waiting_weather_pin(farmer_id, session_id, text)
            if asks is not None:
                pinned = {"reminder": supervisor.reminder(farmer_id, session_id, language)}
                side_reply = _side_question_reply("weather", pinned, farmer_id, session_id, text, language, previous_asks=asks)
                return _side_question_envelope(agent, "weather", pinned, side_reply, farmer_id, session_id, text, include_audio, language)
        if side_question is not None:
            result = supervisor.turn(farmer_id, session_id, text, language, include_audio=include_audio, side_question=side_question)
        else:
            result = supervisor.turn(farmer_id, session_id, text, language, include_audio=include_audio)
        side = result.get("side_question")
        if side in _FLOW_AGENTS and side != flow_intent:
            closed = supervisor.confirm(farmer_id, session_id, "cancel", include_audio=False)
            _log.info("adk_router flow switch farmer=%s session=%s from=%s to=%s", farmer_id, session_id, flow_intent, side)
            follow = _DISPATCH_TABLE[side](farmer_id, session_id, text, language, False, side)
            return _then(str(closed.get("response_text") or ""), follow, farmer_id, session_id, text, include_audio, language)
        if side:
            side_reply = _side_question_reply(side, result, farmer_id, session_id, text, language)
            return _side_question_envelope(agent, side, result, side_reply, farmer_id, session_id, text, include_audio, language)
        if result.get("state") == "CANCELLED" and _switch_on(_CANCEL_THEN_ROUTE_ENV):
            follow = _route_after_cancel(agent, flow_intent, result, farmer_id, session_id, text, language, _allowed)
            if follow is not None:
                return _then(_reply_text(agent, result), follow, farmer_id, session_id, text, include_audio, language)
        reply = _reply_text(agent, result)
        return _envelope(agent, None, result, reply, farmer_id, session_id, text, include_audio, language)

    weather_key = _weather_session_key(farmer_id, session_id)
    weather_state = get_session(weather_key)
    if weather_state.get("awaiting_location"):
        # Sticky while weather is still waiting for a location, capped at
        # _MAX_LOCATION_ASKS asks in a row (see _run_weather): clear first;
        # _run_weather re-arms only if it asks again and the cap allows,
        # so a farmer who has moved on is never locked into weather.
        update_session(weather_key, {"awaiting_location": False})
        # A bare PIN goes straight to weather. Anything else is classified:
        # a location answer ("Pune") comes back as weather or query and stays
        # with weather, but a different request ("register a goat", "book a
        # vet") goes to its own agent. Seen live: "register a goat" sent while
        # weather waited for the PIN was answered by weather, used up an ask,
        # and the PIN that followed went to query_agent.
        sticky_intent = "weather" if _looks_like_pin(text) else asyncio.run(_classify_intent_async(text))
        if sticky_intent == "query" and _allowed("query"):
            # Real bug, found in whole-branch review: "query" here used to
            # mean only "the classifier called a bare location reply
            # ('Pune') query instead of weather" (seen live, as common as
            # it calling the same text 'weather'). But 'query' is ALSO the
            # genuine catch-all intent -- a real database question ("how
            # many goats do I have") asked while weather waits for a PIN
            # classified the same way and was swallowed by weather,
            # producing a nonsensical weather reply to it. Dispatch for
            # real and check: a genuine SQL+data result is strong evidence
            # this was an answerable question, not a location reply --
            # same pattern as appointment_supervisor's own off-topic-probe
            # fix. No SQL/data (the common case for "Pune") falls through
            # to the weather branch below, same as before.
            probe = _dispatch_query(farmer_id, session_id, text, language, include_audio, "query")
            if probe["result"].get("sql") and probe["result"].get("data"):
                return probe
        if sticky_intent in ("weather", "query"):
            if not _allowed("weather"):
                return _blocked_envelope("weather", farmer_id, session_id, text, language)
            return _run_weather(farmer_id, session_id, text, "weather", include_audio, language,
                                previous_asks=int(weather_state.get("asks") or 1))
        _log.info("adk_router left weather wait farmer=%s session=%s text=%r intent=%s",
                  farmer_id, session_id, text[:200], sticky_intent)
        if not _allowed(sticky_intent):
            return _blocked_envelope(sticky_intent, farmer_id, session_id, text, language)
        handler = _DISPATCH_TABLE.get(sticky_intent) or _DISPATCH_TABLE["query"]
        return handler(farmer_id, session_id, text, language, include_audio, sticky_intent)

    intent = asyncio.run(_classify_intent_async(text))
    _log.info("adk_router classified farmer=%s session=%s text=%r intent=%s", farmer_id, session_id, text[:200], intent)

    if not _allowed(intent):
        return _blocked_envelope(intent, farmer_id, session_id, text, language)

    # Dispatch table lookup replaces the 4-way if-elif chain. Fallback to
    # `query` for anything unrecognized -- matches _make_record_route_tool's
    # own "unknown -> query" guard, so one behavior in one place instead of
    # two places drifting.
    if intent == "appointment" and recent_animal:
        return _dispatch_appointment(farmer_id, session_id, text, language, include_audio, intent,
                                     recent_animal=recent_animal)
    handler = _DISPATCH_TABLE.get(intent) or _DISPATCH_TABLE["query"]
    return handler(farmer_id, session_id, text, language, include_audio, intent)


# Per-intent dispatch handlers. Each takes the same fully-resolved
# arguments as the sticky-routing block at the top of route_turn_adk and
# returns the standard envelope shape. Sticky-routed dispatches at the
# top pass intent=None; classified dispatches pass the classifier's
# chosen intent so telemetry/envelope include it. Kept as small named
# functions so the dispatch table below is a plain literal a reader can
# eyeball at a glance.

def _dispatch_appointment(farmer_id, session_id, text, language, include_audio, intent, recent_animal=None):
    if recent_animal:
        result = _appointment_supervisor.turn(farmer_id, session_id, text, language, include_audio=include_audio,
                                              recent_animal=recent_animal)
    else:
        result = _appointment_supervisor.turn(farmer_id, session_id, text, language, include_audio=include_audio)
    reply = _reply_text("appointment_supervisor", result)
    return _envelope("appointment_supervisor", intent, result, reply, farmer_id, session_id, text, include_audio, language)


def _dispatch_animal_registration(farmer_id, session_id, text, language, include_audio, intent):
    result = _animal_registration_supervisor.turn(farmer_id, session_id, text, language, include_audio=include_audio)
    reply = _reply_text("animal_registration", result)
    return _envelope("animal_registration", intent, result, reply, farmer_id, session_id, text, include_audio, language)


def _dispatch_weather(farmer_id, session_id, text, language, include_audio, intent):
    return _run_weather(farmer_id, session_id, text, intent, include_audio, language)


def _dispatch_query(farmer_id, session_id, text, language, include_audio, intent):
    # session_id forwarded so query_agent can reuse the chat's ADK session
    # and remember earlier turns (PR #28 integration into the post-#30
    # dispatch-table shape; this exact collision was flagged in the code
    # review and would silently disappear under a naive git merge).
    result = process_query_adk(
        _with_reply_language(text, language), farmer_id,
        session_id=session_id, app_language=language,
    )
    reply = result.get("answer") or ""
    _remember_animal(farmer_id, session_id, text, reply)
    return _envelope("query_agent", intent, result, reply, farmer_id, session_id, text, include_audio, language, result.get("speech_text"))


_DISPATCH_TABLE = {
    "appointment": _dispatch_appointment,
    "add_animal": _dispatch_animal_registration,
    "weather": _dispatch_weather,
    "query": _dispatch_query,
}
