"""ADK-native rebuild of query_agent's orchestration (Phase 1 of the plan at
/Users/sudhanshu/.claude/plans/elegant-roaming-river.md).

Deliberately does NOT touch db.py or schema.py -- those are the deterministic,
already-hardened data layer (thread-safety fix, LRU cache, blocked-keyword
fix, all from this session's robustness audit) and have nothing to do with
orchestration. Also deliberately does NOT edit the existing agent.py in
place -- that file has unrelated uncommitted work from another concurrent
session (structured count/frequency formatting) that this migration must not
clobber. This module is the new path; agent.py remains the old path until
Phase 4 verifies they're equivalent, per the plan's "reversible, not a single
cutover" requirement.

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
"""


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


async def _run_query_async(query: str, farmer_id: str) -> dict[str, Any]:
    agent = build_query_agent(farmer_id)
    runner = InMemoryRunner(agent=agent, app_name="farmer_chat_query_agent")
    user_id = f"farmer-{farmer_id}"
    session = await runner.session_service.create_session(app_name="farmer_chat_query_agent", user_id=user_id)
    message = types.Content(role="user", parts=[types.Part(text=query)])

    answer_text: str | None = None
    last_successful_result: dict[str, Any] | None = None

    async for event in runner.run_async(user_id=user_id, session_id=session.id, new_message=message):
        for fr in event.get_function_responses():
            if fr.name == "run_sql_query" and isinstance(fr.response, dict) and fr.response.get("success"):
                last_successful_result = fr.response
        if event.is_final_response() and event.content and event.content.parts:
            answer_text = "".join(p.text for p in event.content.parts if p.text)

    if not answer_text:
        return {"answer": "I couldn't understand the query. Please rephrase.", "sql": None, "data": None}

    if last_successful_result is None:
        return {"answer": answer_text, "sql": None, "data": None}

    return {
        "answer": answer_text,
        "sql": last_successful_result.get("sql"),
        "data": {
            "columns": last_successful_result.get("columns"),
            "rows": last_successful_result.get("rows"),
            "row_count": last_successful_result.get("row_count"),
            "truncated": last_successful_result.get("truncated", False),
        },
    }


def process_query_adk(query: str, farmer_id: str) -> dict[str, Any]:
    """Drop-in replacement for agent.py's process_query(), same return shape
    ({"answer", "sql", "data"}), routed through an ADK Agent instead of the
    hand-rolled generate-SQL/execute/format/retry loop. Sync wrapper because
    every caller in this codebase (chat_orchestrator, appointment_supervisor's
    off-topic probe) is itself sync."""
    return asyncio.run(_run_query_async(query, farmer_id))
