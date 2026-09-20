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
from typing import Any

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

from services.llm_service.bedrock_adapter import TaskTier, model_for_task
from services.pincode_store import get_pincode_data
from storage import get_farmer_by_id

_INSTRUCTION = """You are a livestock weather and farm-advisory assistant.

Rules:
- Use the get_weather_context tool to fetch weather/seasonal/feed-market data for the farmer's location, then answer their specific question using that data.
- If the farmer's message names a PIN code or place, pass it as the location argument. Otherwise pass an empty string -- the tool will use the farmer's saved default location.
- If the tool returns {"error": "no_location", ...}, tell the farmer you need a PIN code or place name to check the weather -- do not guess a location.
- Keep your answer short, 1-3 sentences.
- Base your answer only on the data the tool returns. Never invent numbers, prices, or facts not present in the data.
- If the data doesn't contain what the farmer asked, say so simply, then give the closest relevant fact from the data instead of repeating an unrelated summary.
- Never mention JSON, fields, tools, or any technical/database terms in your answer -- speak like a farm advisor.
"""


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
            return get_pincode_data(loc)
        except Exception as exc:
            return {"error": str(exc)}

    return get_weather_context


def build_weather_agent(farmer_id: str) -> Agent:
    model_spec = model_for_task(TaskTier.GENERATION)
    return Agent(
        name="weather_agent",
        description=(
            "Answers a farmer's weather, seasonal-advisory, and feed-market "
            "price questions for their farm's location -- forecasts, heat/cold "
            "stress risk, whether to move animals indoors, feed price trends. "
            "Use this for any weather- or season-related question."
        ),
        model=LiteLlm(model=f"bedrock/{model_spec['id']}", temperature=model_spec["temperature"]),
        instruction=_INSTRUCTION,
        tools=[_make_get_weather_context_tool(farmer_id)],
    )


async def _run_weather_async(query: str, farmer_id: str) -> dict[str, Any]:
    agent = build_weather_agent(farmer_id)
    runner = InMemoryRunner(agent=agent, app_name="farmer_chat_weather_agent")
    user_id = f"farmer-{farmer_id}"
    session = await runner.session_service.create_session(app_name="farmer_chat_weather_agent", user_id=user_id)
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
    return {"result": result, "answer": answer_text or ""}


def process_weather_query_adk(query: str, farmer_id: str) -> dict[str, Any]:
    """Drop-in replacement for chat_orchestrator's WEATHER_ALERT branch
    (get_pincode_data + _answer_weather_question), routed through an ADK
    Agent. Returns {"result": <pincode data or error dict>, "answer": str}."""
    return asyncio.run(_run_weather_async(query, farmer_id))
