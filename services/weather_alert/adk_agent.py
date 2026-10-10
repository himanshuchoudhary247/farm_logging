"""ADK-native rebuild of the weather branch's orchestration (Phase 2 of the
plan at /Users/sudhanshu/.claude/plans/elegant-roaming-river.md).

Deliberately does NOT touch services/pincode_store or services/weather_alert
themselves -- both are this session's already-hardened data layer (LRU
cache, non-ASCII PIN fix, lock) and have nothing to do with orchestration.
The old chat_orchestrator/router.py this was built alongside (with its own
WEATHER_ALERT branch) has since been removed -- this is the only
implementation now.

Mirrors query_agent's adk_agent.py shape: farmer_id is bound into the tool
closure at construction time, never a parameter the model can pass, so the
model can only ever resolve a location (from what the farmer said or the
farmer's own saved default) -- never redirect at another farmer's data (not
that pincode data is farmer-scoped, but the pattern is kept consistent).
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.genai import types

from services.llm_service.bedrock_adapter import TaskTier, model_for_task
from services.pincode_store import get_pincode_data
from storage import animals_for_farmer, get_farmer_by_id, health_logs_for_farmer
from services.advisory.llm_advisory import summarize_livestock
from services.advisory.personalized import recent_issues
from services.llm_service.adk_model import build_adk_model

_INSTRUCTION = """You are a livestock weather and farm-advisory assistant.

Rules:
- Use the get_weather_context tool to fetch weather/seasonal/feed-market data for the farmer's location, then answer their specific question using that data.
- If the farmer's message names a PIN code or place, pass it as the location argument. Otherwise pass an empty string -- the tool will use the farmer's saved default location.
- Always call get_weather_context before answering, follow-up questions included. If the new message names no PIN code or place but an earlier message in this chat did, pass that same place instead of an empty string.
- If the tool returns {"error": "no_location", ...}, tell the farmer you need a PIN code or place name to check the weather -- do not guess a location.
- Keep your answer short, 1-3 sentences.
- If the tool result includes "your_farm", make the advice specific to this farmer's own animals (species, young animals, recent health issues). Never name medicines or doses; if an animal is sick, tell them to consult a vet. Without "your_farm", give general advice.
- Recent health issues in "your_farm" are recorded for the farm as a whole, not for a species or age group: never say which animals have them.
- Base your answer only on the data the tool returns. Never invent numbers, prices, or facts not present in the data.
- If the data doesn't contain what the farmer asked, say so simply, then give the closest relevant fact from the data instead of repeating an unrelated summary.
- Never mention JSON, fields, tools, or any technical/database terms in your answer -- speak like a farm advisor.
- If the farmer's message contains a greeting word ("hello", "namaste", "hi") alongside their actual question, answer the question directly -- do NOT prepend "hello"/"namaste" or a "thank you" to your answer. Go straight to the answer.

Your answer is shown as text AND read aloud by text-to-speech -- these can differ. The text answer can include the specific numbers/advisories the farmer asked for. The spoken version must be even shorter -- the single most important fact and action, nothing else.

After your full text answer, on its own line, write exactly `---SPOKEN---` followed by a short, spoken-friendly one-sentence version (e.g. "Yes, heavy rain expected today -- move animals to shelter." rather than a sentence packed with mm/kph figures). If your text answer is already one short sentence, the spoken version can repeat it as-is. Always include the `---SPOKEN---` line."""


def _farm_context(farmer_id: str) -> Optional[dict[str, Any]]:
    """This farmer's own animals (short summary) and recent health issues,
    so the weather answer can be specific to their farm. farmer_id is bound
    at construction, never taken from the model, same as the location
    lookup. Best effort: a storage error just means a general answer."""
    try:
        livestock = summarize_livestock(animals_for_farmer(farmer_id))
        issues = recent_issues(health_logs_for_farmer(farmer_id))
    except Exception as exc:
        logging.getLogger("weather_alert.adk_agent").warning(
            "farm context unavailable farmer=%s: %s", farmer_id, exc,
        )
        return None
    if not livestock and not issues:
        return None
    return {"livestock": livestock, "recent_health_issues": issues}


def _make_get_weather_context_tool(farmer_id: str):
    def get_weather_context(location: str = "") -> dict[str, Any]:
        """Fetch weather, seasonal-advisory, and feed-market data for a location.

        Args:
            location: A PIN code or place name the farmer mentioned. Pass an
                empty string to use the farmer's saved default location instead.

        Returns:
            On success: the weather/seasonal/feed_market data dict.
            On failure: {"error": "no_location", "message": "..."} if no
                location could be resolved at all, or {"error": "<message>"}
                if the location couldn't be looked up.
        """
        loc = (location or "").strip()
        if not loc:
            farmer = get_farmer_by_id(farmer_id)
            loc = str(getattr(farmer, "weather_location", "") or "") if farmer else ""
        if not loc:
            return {"error": "no_location", "message": "Need a PIN code or place name to check the weather."}
        try:
            data = get_pincode_data(loc)
        except Exception as exc:
            return {"error": str(exc)}
        farm = _farm_context(farmer_id)
        # A new dict: the pincode data is cached and shared by all farmers,
        # so this farmer's details must never be written into it.
        return {**data, "your_farm": farm} if farm else data

    return get_weather_context


def build_weather_agent(farmer_id: str) -> LlmAgent:
    model_spec = model_for_task(TaskTier.GENERATION)
    from services.common.adk_telemetry import make_adk_callbacks
    return LlmAgent(
        name="weather_agent",
        description=(
            "Answers a farmer's weather, seasonal-advisory, and feed-market "
            "price questions for their farm's location -- forecasts, heat/cold "
            "stress risk, whether to move animals indoors, feed price trends. "
            "Use this for any weather- or season-related question."
        ),
        model=build_adk_model(TaskTier.GENERATION, model_spec["id"], temperature=model_spec["temperature"]),
        instruction=_INSTRUCTION,
        tools=[_make_get_weather_context_tool(farmer_id)],
        **make_adk_callbacks("weather_agent"),
    )


_SPOKEN_MARKER = "---SPOKEN---"


def _split_text_and_speech(answer_text: str) -> tuple[str, str]:
    """Same rationale as query_agent's identical helper: text and audio can
    legitimately differ (specific figures in text, a short actionable
    sentence spoken), generated in one call via a marker rather than a
    second LLM call per turn. Degrades to using the full text for speech
    too if the model ever omits the marker."""
    if _SPOKEN_MARKER in answer_text:
        text_part, _, speech_part = answer_text.partition(_SPOKEN_MARKER)
        text_part = text_part.strip()
        speech_part = speech_part.strip()
        return text_part, (speech_part or text_part)
    return answer_text, answer_text


_APP_NAME = "farmer_chat_weather_agent"

# One session store for the whole process, same pattern as query_agent
# (PR #28). Before this every weather turn got a fresh, empty session, so a
# follow-up like "will it rain?" right after "weather in 411001?" did not
# know the place and asked for the PIN again (seen live).
_IN_MEMORY_SESSIONS = InMemorySessionService()

# Upper bound on events kept in one ADK session. Past this the session is
# restarted, so a long chat does not keep growing every LLM call's prompt.
_MAX_SESSION_EVENTS = 40


def _db_engine_kwargs(db_url: str) -> dict:
    """Same as query_agent's: NullPool for a real database, nothing extra for
    an in-memory SQLite URL or a URL that does not parse (ADK then raises its
    own error with the password redacted)."""
    from sqlalchemy.engine import make_url
    from sqlalchemy.pool import NullPool

    try:
        url = make_url(db_url)
    except Exception:
        return {}
    if url.get_backend_name() == "sqlite" and url.database in (None, "", ":memory:"):
        return {}
    return {"poolclass": NullPool}


def _session_service() -> BaseSessionService:
    """In-memory by default. ADK_SESSION_DB_URL (a SQLAlchemy URL) keeps
    sessions across restarts -- the same setting query_agent uses; app_name
    keeps the two agents' sessions apart. Built per call because each turn
    runs in its own asyncio.run event loop (see query_agent)."""
    db_url = os.getenv("ADK_SESSION_DB_URL", "").strip()
    if db_url:
        from google.adk.sessions import DatabaseSessionService
        return DatabaseSessionService(db_url=db_url, **_db_engine_kwargs(db_url))
    return _IN_MEMORY_SESSIONS


async def _get_or_create_session(service: BaseSessionService, user_id: str, session_id: Optional[str]):
    """Reuses the chat's own session when the caller passes its session_id.
    Keyed by user_id (farmer-<id>) too, so one farmer never sees another
    farmer's session even with the same session_id. No session_id: a fresh
    one-off session, as before."""
    if not session_id:
        return await service.create_session(app_name=_APP_NAME, user_id=user_id)
    session = await service.get_session(app_name=_APP_NAME, user_id=user_id, session_id=session_id)
    if session is not None and len(session.events) <= _MAX_SESSION_EVENTS:
        return session
    if session is not None:
        await service.delete_session(app_name=_APP_NAME, user_id=user_id, session_id=session_id)
    return await service.create_session(app_name=_APP_NAME, user_id=user_id, session_id=session_id)


async def _run_weather_async(query: str, farmer_id: str, session_id: Optional[str] = None) -> dict[str, Any]:
    agent = build_weather_agent(farmer_id)
    service = _session_service()
    runner = Runner(agent=agent, app_name=_APP_NAME, session_service=service)
    user_id = f"farmer-{farmer_id}"
    session = await _get_or_create_session(service, user_id, session_id)
    message = types.Content(role="user", parts=[types.Part(text=query)])

    answer_text: str | None = None
    last_tool_result: dict[str, Any] | None = None

    async for event in runner.run_async(user_id=user_id, session_id=session.id, new_message=message):
        for fr in event.get_function_responses():
            if fr.name == "get_weather_context" and isinstance(fr.response, dict):
                last_tool_result = fr.response
        if event.is_final_response() and event.content and event.content.parts:
            answer_text = "".join(p.text for p in event.content.parts if p.text)

    result = last_tool_result if last_tool_result is not None else {"error": "no_location", "message": "Need a PIN code or place name to check the weather."}
    text_answer, speech_text = _split_text_and_speech(answer_text or "")
    return {"result": result, "answer": text_answer, "speech_text": speech_text}


def process_weather_query_adk(query: str, farmer_id: str, session_id: Optional[str] = None) -> dict[str, Any]:
    """Drop-in replacement for chat_orchestrator's WEATHER_ALERT branch
    (get_pincode_data + _answer_weather_question), routed through an ADK
    Agent. Returns {"result": <pincode data or error dict>, "answer": str,
    "speech_text": str}.

    session_id (optional): the chat's session id. When given, the same ADK
    session is reused across turns, so the agent remembers earlier turns of
    this chat (e.g. the PIN given a message ago). Without it, a fresh
    session per call, as before."""
    return asyncio.run(_run_weather_async(query, farmer_id, session_id))
