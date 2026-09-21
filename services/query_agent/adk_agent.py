"""ADK-native rebuild of query_agent's orchestration (Phase 1 of the plan at
/Users/sudhanshu/.claude/plans/elegant-roaming-river.md).

Deliberately does NOT touch db.py or schema.py -- those are the deterministic,
already-hardened data layer (thread-safety fix, LRU cache, blocked-keyword
fix, all from this session's robustness audit) and have nothing to do with
orchestration. The old agent.py this was built alongside (which had unrelated
uncommitted work from another concurrent session) has since been removed --
this is the only implementation now.

farmer_id is bound into the tool closure, never exposed as a parameter the
model could pass -- same principle as every other scoping fix this session
(auth/tenant-scoping is a correctness invariant, not something to trust an
LLM-driven tool call with).
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from google.adk import Agent
from google.adk.agents.invocation_context import LlmCallsLimitExceededError
from google.adk.agents.run_config import RunConfig
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

from services.llm_service.bedrock_adapter import TaskTier, model_for_task
from services.query_agent.db import execute_query
from services.query_agent.schema import generate_schema_for_prompt

_INSTRUCTION_TEMPLATE = """You are a livestock data analyst answering one farmer's questions about \
their own farm records.

Database schema:
{schema}

Rules:
- Use the run_sql_query tool to answer. Never answer from memory/guesswork.
- The query MUST be a single SQLite SELECT statement.
- Use COUNT(*) when counting; GROUP BY when the farmer wants a breakdown by category; ORDER BY for listing/sorting.
- Use LOWER() for case-insensitive text filtering.
- If run_sql_query returns success=false, read the error and try a corrected query -- do not give up after one attempt, and do not repeat the exact same failing query.
- If asking for a single total/count, give just the number in your answer.
- If asking for a breakdown by category, show EACH group with its count -- never summarize or say "ranging from"/"most are" when specific data was requested.
- Otherwise, give a natural conversational answer.
- Never mention SQL, tables, columns, or any technical/database terms in your final answer -- speak like a farm advisor, not a database.
- A bare greeting ("hi", "hello", "hey") with NO real question attached gets a plain greeting back, under 10 words, e.g. "Hi! What would you like to know about your farm?" -- do NOT list your capabilities (animal counts, health records, appointments, etc.) unless the farmer's message actually asked what you can do.
- If the farmer's message contains a greeting word ("hello", "namaste", "hi") ALONGSIDE a real question (e.g. "hello, how many animals do I have"), answer the question directly -- do NOT prepend a greeting/"hello"/"namaste" to the answer. One farmer message, one direct answer; the greeting word was just how they opened their sentence, not a separate thing to reply to.
- Never open an answer with "thank you"/"धन्यवाद" or similar courtesy filler either -- go straight to the answer.

Your answer is shown as text AND read aloud by text-to-speech -- these can differ. The text answer can be as detailed as the question needs (full breakdowns, full lists). The spoken version must always be short, since a farmer listening doesn't want a list of 5+ numbers read out loud one by one.

So: after your full text answer, on its own line, write exactly `---SPOKEN---` followed by a short, spoken-friendly summary of the same answer -- one sentence, no itemized lists, no reading out every number in a breakdown (say "you have 53 animals across 5 species" instead of naming each species and count). If your text answer is already one short sentence, the spoken version can repeat it as-is. Always include the `---SPOKEN---` line, even for a greeting."""


def _make_run_sql_query_tool(farmer_id: str):
    def run_sql_query(sql: str) -> dict[str, Any]:
        """Run a single read-only SQL SELECT query against this farmer's own livestock database.

        Args:
            sql: A single SQLite SELECT statement. Do not add a farmer_id
                filter -- the database already contains only this farmer's rows.

        Returns:
            On success: {"success": true, "columns": [...], "rows": [...], "row_count": int, "truncated": bool}.
            On failure: {"success": false, "error": "..."} -- read the error and retry with a corrected query.
        """
        try:
            return execute_query(sql, farmer_id)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

    return run_sql_query


def build_query_agent(farmer_id: str) -> Agent:
    """One Agent per farmer_id -- farmer_id is baked into the tool closure
    above, not passed through the model, so no prompt can ever redirect a
    query at a different farmer's data."""
    model_spec = model_for_task(TaskTier.GENERATION)
    schema = generate_schema_for_prompt()

    return Agent(
        name="query_agent",
        description=(
            "Answers a farmer's questions about their own livestock data -- "
            "animal counts, health logs, appointments, vaccination records, "
            "farm details -- by querying the farm database. Use this for any "
            "'how many'/'list'/'show me'/'when was'/data-lookup question "
            "about the farmer's own animals or records."
        ),
        model=LiteLlm(model=f"bedrock/{model_spec['id']}", temperature=model_spec["temperature"]),
        instruction=_INSTRUCTION_TEMPLATE.format(schema=schema),
        tools=[_make_run_sql_query_tool(farmer_id)],
    )


_SPOKEN_MARKER = "---SPOKEN---"


def _split_text_and_speech(answer_text: str) -> tuple[str, str]:
    """Text and audio can legitimately differ (full breakdown in text, one
    short sentence spoken) -- the instruction asks the model to emit both
    in one call, separated by a marker, rather than a second LLM call per
    turn. Degrades gracefully if the model ever omits the marker: the full
    text is used for speech too rather than crashing or losing the answer."""
    if _SPOKEN_MARKER in answer_text:
        text_part, _, speech_part = answer_text.partition(_SPOKEN_MARKER)
        text_part = text_part.strip()
        speech_part = speech_part.strip()
        return text_part, (speech_part or text_part)
    return answer_text, answer_text


# Real bug, found in code review: the old hand-rolled loop had
# MAX_RETRIES=2 (at most 3 SQL-generation attempts) with a clean fallback
# message on exhaustion. The ADK migration dropped that cap entirely --
# ADK's own default is 500 LLM calls per run, and process_query_adk never
# caught the exception it raises on exceeding it, so a persistently
# failing/ambiguous query could drive up to 500 calls before crashing
# unhandled instead of failing cleanly. Explicit, much lower cap here,
# matching the old bound's spirit (a handful of real attempts, not
# hundreds) while still allowing for ADK's own tool-call/response
# round-trips per attempt.
_MAX_LLM_CALLS = 8


async def _run_query_async(query: str, farmer_id: str) -> dict[str, Any]:
    agent = build_query_agent(farmer_id)
    runner = InMemoryRunner(agent=agent, app_name="farmer_chat_query_agent")
    user_id = f"farmer-{farmer_id}"
    session = await runner.session_service.create_session(app_name="farmer_chat_query_agent", user_id=user_id)
    message = types.Content(role="user", parts=[types.Part(text=query)])

    answer_text: str | None = None
    last_successful_result: dict[str, Any] | None = None

    try:
        async for event in runner.run_async(
            user_id=user_id, session_id=session.id, new_message=message,
            run_config=RunConfig(max_llm_calls=_MAX_LLM_CALLS),
        ):
            for fr in event.get_function_responses():
                if fr.name == "run_sql_query" and isinstance(fr.response, dict) and fr.response.get("success"):
                    last_successful_result = fr.response
            if event.is_final_response() and event.content and event.content.parts:
                answer_text = "".join(p.text for p in event.content.parts if p.text)
    except LlmCallsLimitExceededError:
        fallback = "I encountered an error trying to answer that. Please try rephrasing your question."
        return {"answer": fallback, "sql": None, "data": None, "speech_text": fallback}

    if not answer_text:
        return {"answer": "I couldn't understand the query. Please rephrase.", "sql": None, "data": None, "speech_text": "I couldn't understand the query. Please rephrase."}

    text_answer, speech_text = _split_text_and_speech(answer_text)

    if last_successful_result is None:
        return {"answer": text_answer, "sql": None, "data": None, "speech_text": speech_text}

    return {
        "answer": text_answer,
        "sql": last_successful_result.get("sql"),
        "data": {
            "columns": last_successful_result.get("columns"),
            "rows": last_successful_result.get("rows"),
            "row_count": last_successful_result.get("row_count"),
            "truncated": last_successful_result.get("truncated", False),
        },
        "speech_text": speech_text,
    }


def process_query_adk(query: str, farmer_id: str) -> dict[str, Any]:
    """Drop-in replacement for agent.py's process_query(), same return shape
    ({"answer", "sql", "data"}), routed through an ADK Agent instead of the
    hand-rolled generate-SQL/execute/format/retry loop. Sync wrapper because
    every caller in this codebase (chat_orchestrator, appointment_supervisor's
    off-topic probe) is itself sync."""
    return asyncio.run(_run_query_async(query, farmer_id))
