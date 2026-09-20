"""ADK-native rebuild of chat_orchestrator's dispatch (Phase 3 of the plan at
/Users/sudhanshu/.claude/plans/elegant-roaming-river.md).

Reuses router.py's own helpers (_appointment_supervisor, _has_active_booking_
draft, _envelope, _reply_text) rather than duplicating them -- this module
only replaces HOW the routing decision gets made and how weather/query get
answered, not the deterministic sticky-routing guard or the response
envelope shape flokiquser already depends on.

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
from typing import Any

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

from services.chat_orchestrator.router import (
    _appointment_supervisor,
    _envelope,
    _has_active_booking_draft,
    _reply_text,
)
from services.llm_service.bedrock_adapter import TaskTier, model_for_task
from services.query_agent.adk_agent import process_query_adk
from services.weather_alert.adk_agent import process_weather_query_adk

_log = logging.getLogger("chat_orchestrator.adk_router")

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
        return _envelope("appointment_supervisor", None, result, reply, farmer_id, session_id, text)

    intent = asyncio.run(_classify_intent_async(text))
    _log.info("adk_router classified farmer=%s session=%s text=%r intent=%s", farmer_id, session_id, text[:200], intent)

    if intent == "appointment":
        result = _appointment_supervisor.turn(farmer_id, session_id, text, language, include_audio=include_audio)
        reply = _reply_text("appointment_supervisor", result)
        return _envelope("appointment_supervisor", intent, result, reply, farmer_id, session_id, text)

    if intent == "weather":
        weather = process_weather_query_adk(text, farmer_id)
        result = weather["result"]
        reply = weather["answer"] or _reply_text("weather_alert", result)
        return _envelope("weather_alert", intent, result, reply, farmer_id, session_id, text)

    result = process_query_adk(text, farmer_id)
    reply = result.get("answer") or ""
    return _envelope("query_agent", intent, result, reply, farmer_id, session_id, text)
