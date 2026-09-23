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

# Matches SUPPORTED_LANGUAGES elsewhere (appointment_supervisor,
# animal_registration) -- kept to the same 5, not adding a 6th
# (Malayalam) here alone, since that would give query_agent language
# coverage the rest of the app (booking, registration) doesn't have.
_NATIVE_DIGITS = {
    "hi": "०१२३४५६७८९",
    "ta": "௦௧௨௩௪௫௬௭௮௯",
    "te": "౦౧౨౩౪౫౬౭౮౯",
    "kn": "೦೧೨೩೪೫೬೭೮೯",
}

# Unicode script ranges, checked in order -- first match wins. A query with
# no script-specific characters (Latin/English, or a bare number) falls
# through to "en", where digit conversion is a no-op.
_SCRIPT_RANGES = (
    ("hi", (0x0900, 0x097F)),  # Devanagari
    ("ta", (0x0B80, 0x0BFF)),
    ("te", (0x0C00, 0x0C7F)),
    ("kn", (0x0C80, 0x0CFF)),
)


def detect_language(text: str) -> str:
    """Script-based detection for the one thing the model can't be trusted
    to do consistently on its own: converting digits to native numerals
    within an otherwise-correct-language reply (verified live -- the model
    replies in Hindi/Tamil/etc fine, but leaves numbers as plain Western
    digits inconsistently). Deterministic post-processing, not a second
    LLM call -- same "LLM for judgment, code for correctness" split this
    codebase already uses for dates, PINs, and breed validation."""
    for lang, (lo, hi) in _SCRIPT_RANGES:
        if any(lo <= ord(ch) <= hi for ch in text):
            return lang
    return "en"


def _to_native_digits(text: str, lang: str) -> str:
    digits = _NATIVE_DIGITS.get(lang)
    if not digits or not isinstance(text, str):
        return text
    return text.translate(str.maketrans("0123456789", digits))


def _localize_numbers(value: Any, lang: str) -> Any:
    """Recurse through a query result (string / int / float / dict / list)
    converting every digit to the target language's native numerals. A
    no-op for English. Applied to the model's text/speech answer AND the
    raw SQL result rows, so a table of numbers is localized the same way
    the spoken summary is."""
    if lang == "en":
        return value
    if isinstance(value, str):
        return _to_native_digits(value, lang)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return _to_native_digits(str(value), lang)
    if isinstance(value, dict):
        return {k: _localize_numbers(v, lang) for k, v in value.items()}
    if isinstance(value, list):
        return [_localize_numbers(v, lang) for v in value]
    return value


# Static translation catalog for the fixed, known column names a SELECT
# against animals/health_logs/appointments actually returns -- reuses the
# same labels already established in animal_registration/appointment_
# supervisor's own _LABELS catalogs for the overlapping fields, so a
# farmer sees the identical word for "breed" everywhere in the app.
# Deliberately NOT an LLM call: an aggregate/alias column (COUNT(*), AS
# total, ...) isn't in this dict and is left as-is in English rather than
# guessed at -- same "don't invent, leave it out" principle used
# throughout this codebase. Covers the common case (a farmer asking for
# raw fields); an aliased query is the one case this doesn't localize.
_COLUMN_LABELS = {
    "hi": {
        "species": "प्रजाति", "breed": "नस्ल", "sex": "लिंग", "tag_or_name": "टैग/नाम",
        "status": "स्थिति", "birth_date": "जन्म तिथि", "current_location": "स्थान",
        "age_years": "उम्र (वर्ष)", "issue": "समस्या", "notes": "नोट्स",
        "date": "तारीख", "time": "समय",
    },
    "ta": {
        "species": "இனம்", "breed": "இனவகை", "sex": "பாலினம்", "tag_or_name": "டேக்/பெயர்",
        "status": "நிலை", "birth_date": "பிறந்த தேதி", "current_location": "இடம்",
        "age_years": "வயது (ஆண்டுகள்)", "issue": "பிரச்சினை", "notes": "குறிப்புகள்",
        "date": "தேதி", "time": "நேரம்",
    },
    "te": {
        "species": "జాతి", "breed": "బ్రీడ్", "sex": "లింగం", "tag_or_name": "ట్యాగ్/పేరు",
        "status": "స్థితి", "birth_date": "పుట్టిన తేదీ", "current_location": "స్థానం",
        "age_years": "వయస్సు (సంవత్సరాలు)", "issue": "సమస్య", "notes": "గమనికలు",
        "date": "తేదీ", "time": "సమయం",
    },
    "kn": {
        "species": "ಪ್ರಭೇದ", "breed": "ತಳಿ", "sex": "ಲಿಂಗ", "tag_or_name": "ಟ್ಯಾಗ್/ಹೆಸರು",
        "status": "ಸ್ಥಿತಿ", "birth_date": "ಜನನ ದಿನಾಂಕ", "current_location": "ಸ್ಥಳ",
        "age_years": "ವಯಸ್ಸು (ವರ್ಷಗಳು)", "issue": "ಸಮಸ್ಯೆ", "notes": "ಟಿಪ್ಪಣಿಗಳು",
        "date": "ದಿನಾಂಕ", "time": "ಸಮಯ",
    },
}


def _localize_columns(columns: "list[str] | None", lang: str) -> "list[str] | None":
    if not columns or lang not in _COLUMN_LABELS:
        return columns
    labels = _COLUMN_LABELS[lang]
    return [labels.get(c, c) for c in columns]


_INSTRUCTION_TEMPLATE = """You are a livestock data analyst answering one farmer's questions about \
their own farm records.

Database schema:
{schema}

Rules:
- Use the run_sql_query tool to answer. Never answer from memory/guesswork.
- The query MUST be a single SQLite SELECT statement.
- Use COUNT(*) when counting; GROUP BY when the farmer wants a breakdown by category; ORDER BY for listing/sorting.
- Use LOWER() for case-insensitive text filtering.
- The database stores species/breed/status and other enum-like values in English only (e.g. 'goat', 'sheep', 'active'). Regardless of what language the farmer's question is in, any such value used in a WHERE clause must be the English database value, never translated or transliterated -- e.g. a Hindi question about "बकरी" must filter species = 'goat', not species = 'बकरी'.
- If run_sql_query returns success=false, read the error and try a corrected query -- do not give up after one attempt, and do not repeat the exact same failing query.
- If asking for a single total/count, give just the number in your answer.
- If asking for a breakdown by category, show EACH group with its count -- never summarize or say "ranging from"/"most are" when specific data was requested.
- Otherwise, give a natural conversational answer.
- Never mention SQL, tables, columns, or any technical/database terms in your final answer -- speak like a farm advisor, not a database.
- A bare greeting ("hi", "hello", "hey") with NO real question attached gets a plain greeting back, under 10 words, e.g. "Hi! What would you like to know about your farm?" -- do NOT list your capabilities (animal counts, health records, appointments, etc.) unless the farmer's message actually asked what you can do.
- If the farmer's message contains a greeting word ("hello", "namaste", "hi") ALONGSIDE a real question (e.g. "hello, how many animals do I have"), answer the question directly -- do NOT prepend a greeting/"hello"/"namaste" to the answer. One farmer message, one direct answer; the greeting word was just how they opened their sentence, not a separate thing to reply to.
- Never open an answer with "thank you"/"धन्यवाद" or similar courtesy filler either -- go straight to the answer.
- You are a farm/livestock assistant ONLY -- not a general-purpose chatbot. If the farmer's message has nothing to do with their farm, animals, or records (general knowledge, world facts, other topics entirely), do NOT answer it from your own knowledge even if you know the answer. Say plainly that you can only help with questions about their farm, and ask what they'd like to know about it instead. This applies however confidently you could answer -- being able to answer something is not the same as it being in scope.

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

    # Deterministic post-processing: the model replies in the right
    # language but is inconsistent about native-digit numerals within it
    # (verified live) -- fix that in code rather than trusting the model,
    # same split used throughout this codebase. English is a no-op.
    lang = detect_language(query)
    text_answer = _localize_numbers(text_answer, lang)
    speech_text = _localize_numbers(speech_text, lang)

    if last_successful_result is None:
        return {"answer": text_answer, "sql": None, "data": None, "speech_text": speech_text}

    return {
        "answer": text_answer,
        "sql": last_successful_result.get("sql"),
        "data": {
            "columns": _localize_columns(last_successful_result.get("columns"), lang),
            "rows": _localize_numbers(last_successful_result.get("rows"), lang),
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
